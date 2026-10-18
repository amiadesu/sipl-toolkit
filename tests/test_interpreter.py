from pathlib import Path

import pytest

from sipl.ast import Program, Skip, SourceSpan
from sipl.errors import ExecutionLimitExceeded, SiplRuntimeError
from sipl.interpreter.interpreter import DEFAULT_MAX_STEPS, Interpreter, run
from sipl.interpreter.state import State
from sipl.parser import parse

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

POWER = (EXAMPLES / "power.sipl").read_text(encoding="utf-8")
FACTORIAL = (EXAMPLES / "factorial.sipl").read_text(encoding="utf-8")
GCD = (EXAMPLES / "gcd.sipl").read_text(encoding="utf-8")

def execute(source: str, **state) -> dict:
    return run(parse(source), state)

def stmt(source: str, **state) -> dict:
    return execute(f"begin {source} end", **state)

def value(expression: str, **state) -> int:
    return stmt(f"Z := {expression}", **state)["Z"]

def holds(condition: str, **state) -> bool:
    return stmt(f"if {condition} then R := 1 else R := 0", **state)["R"] == 1

# ---- Whole programs ----

@pytest.mark.parametrize("x, y, expected", [(2, 10, 1024), (3, 0, 1), (-2, 3, -8), (0, 5, 0)])
def test_power(x, y, expected):
    assert execute(POWER, X=x, Y=y) == {"R": expected, "X": x, "Y": min(y, 0)}

@pytest.mark.parametrize("n, expected", [(0, 1), (1, 1), (5, 120)])
def test_factorial(n, expected):
    assert execute(FACTORIAL, N=n)["F"] == expected

def test_factorial_uses_unbounded_integers():
    assert execute(FACTORIAL, N=25)["F"] == 15511210043330985984000000

@pytest.mark.parametrize("a, b, expected", [(48, 18, 6), (7, 7, 7), (17, 5, 1)])
def test_gcd(a, b, expected):
    assert execute(GCD, A=a, B=b) == {"A": expected, "B": expected}

# ---- Statements (S1-S6) ----

def test_assign_creates_and_overwrites_variables():
    assert stmt("X := 1") == {"X": 1}
    assert stmt("X := 1; X := X + 1") == {"X": 2}

def test_sequence_runs_in_order():
    assert stmt("X := 1; Y := X; X := 5") == {"X": 5, "Y": 1}

@pytest.mark.parametrize("x, expected", [(5, 5), (-5, 5), (0, 0)])
def test_if_chooses_branch(x, expected):
    assert stmt("if 0 > X then X := 0 - X else skip", X=x)["X"] == expected

def test_while_does_not_run_body_when_condition_is_false():
    assert stmt("while X > 0 do X := X - 1", X=0) == {"X": 0}

def test_while_runs_until_condition_is_false():
    assert stmt("S := 0; while N > 0 do begin S := S + N; N := N - 1 end", N=4) == {"N": 0, "S": 10}

def test_block_and_skip_do_not_change_state():
    assert stmt("begin skip end; skip", X=7) == {"X": 7}

# ---- Expressions (A1-A6) and conditions (B1-B5) ----

@pytest.mark.parametrize(
    "expression, expected",
    [
        ("7", 7),
        ("-7", -7),
        ("7 + 2", 9),
        ("7 - 2", 5),
        ("2 - 7", -5),
        ("7 * -2", -14),
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("8 - 4 - 2", 2),
        ("X * X - X", 6),
    ],
)
def test_arithmetic(expression, expected):
    assert value(expression, X=3) == expected

@pytest.mark.parametrize(
    "condition, expected",
    [
        ("1 = 1", True),
        ("1 = 2", False),
        ("2 > 1", True),
        ("1 > 1", False),
        ("1 = 2 ∨ 2 = 2", True),
        ("1 = 2 ∨ 2 = 3", False),
        ("¬ 1 = 2", True),
        ("¬ (1 = 1 ∨ 2 = 3)", False),
        ("not 1 > 2 or 1 = 2", True),
        ("X + 1 > X * 2", False),
    ],
)
def test_conditions(condition, expected):
    assert holds(condition, X=3) is expected

# ---- State ----

def test_initial_state_is_copied_not_mutated():
    initial = {"N": 3}
    run(parse(FACTORIAL), initial)
    assert initial == {"N": 3}

def test_unrelated_initial_variables_are_kept():
    assert stmt("X := 1", Other=42) == {"Other": 42, "X": 1}

def test_state_object():
    state = State({"B": 2})
    assert state.get("A") is None
    assert state.set("A", 1) is None
    assert state.set("A", 5) == 1
    assert state.snapshot() == {"A": 5, "B": 2}
    assert list(state.snapshot()) == ["A", "B"]
    assert repr(state) == "State(A=5, B=2)"

# ---- Runtime errors ----

def test_reading_unassigned_variable_is_an_error_with_position():
    with pytest.raises(SiplRuntimeError) as info:
        execute("begin\n  X := 1;\n  Y := Z + X\nend")
    error = info.value
    assert "'Z'" in error.message
    assert error.span == SourceSpan(3, 8, 3, 9)
    assert error.to_dict()["stage"] == "run"

def test_both_sides_of_disjunction_are_evaluated():
    # The left side is true, but the right one reads an unassigned variable.
    with pytest.raises(SiplRuntimeError, match="'Z'"):
        stmt("if X = 1 ∨ Z = 1 then skip else skip", X=1)

def test_unassigned_variable_in_condition():
    with pytest.raises(SiplRuntimeError, match="'N'"):
        execute(FACTORIAL)

# ---- Step limit ----

def test_infinite_loop_hits_step_limit():
    with pytest.raises(ExecutionLimitExceeded) as info:
        run(parse("begin while 1 = 1 do skip end"), max_steps=1_000)
    error = info.value
    assert "1000" in error.message
    assert error.span == SourceSpan(1, 7, 1, 26)  # the loop that ran out of steps
    assert isinstance(error, SiplRuntimeError)

def test_program_within_limit_runs_normally():
    assert run(parse(POWER), {"X": 2, "Y": 10}, max_steps=1_000)["R"] == 1024

def test_default_limit():
    assert Interpreter(parse("begin skip end")).max_steps == DEFAULT_MAX_STEPS

@pytest.mark.parametrize(
    "source, steps",
    [
        ("begin skip end", 1),
        ("begin X := 1; Y := 2 end", 2),
        ("begin begin skip end end", 1),  # begin/end costs nothing
        ("begin if 1 = 1 then skip else skip end", 2),  # condition + branch
        ("begin while 1 > 2 do skip end", 1),  # one failed condition check
    ],
)
def test_step_counting(source, steps):
    interpreter = Interpreter(parse(source))
    interpreter.run()
    assert interpreter.steps == steps

def test_power_step_count():
    # R := 1 (1) + 5 condition checks + 4 iterations of 2 assignments (8)
    interpreter = Interpreter(parse(POWER), {"X": 3, "Y": 4})
    interpreter.run()
    assert interpreter.steps == 14

def test_limit_is_exact():
    program = parse("begin X := 1; X := 2; X := 3 end")
    assert run(program, max_steps=3) == {"X": 3}
    with pytest.raises(ExecutionLimitExceeded):
        run(program, max_steps=2)

# ---- Defensive checks ----

class _Unknown:
    span = None

@pytest.mark.parametrize("method", ["_execute", "_eval", "_test"])
def test_unknown_node_type_is_rejected(method):
    interpreter = Interpreter(Program(Skip()))
    with pytest.raises(TypeError):
        getattr(interpreter, method)(_Unknown())