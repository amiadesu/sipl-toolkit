import json
from pathlib import Path

import pytest

from sipl.ast import SourceSpan
from sipl.errors import ExecutionLimitExceeded, SiplRuntimeError
from sipl.interpreter.events import (
    AfterStatement,
    BeforeStatement,
    ConditionChecked,
    ExecutionFinished,
    VariableChanged,
    to_json,
)
from sipl.interpreter.interpreter import Interpreter, run, trace
from sipl.parser import parse

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
POWER = (EXAMPLES / "power.sipl").read_text(encoding="utf-8")

def events_of(source: str, **state):
    return trace(parse(source), state)

def short(events):
    # Events without positions, for compact comparisons.
    result = []
    for event in events:
        data = event.to_dict()
        del data["span"]
        result.append(data)
    return result

def of_type(events, event_type):
    return [event for event in events if isinstance(event, event_type)]

# ---- Event sequence ----

def test_assignment_and_skip():
    assert short(events_of("begin X := 1; skip end")) == [
        {"event": "before_statement", "step": 0, "statement": "assign"},
        {"event": "variable_changed", "step": 1, "name": "X", "old": None, "new": 1},
        {"event": "after_statement", "step": 1, "statement": "assign"},
        {"event": "before_statement", "step": 1, "statement": "skip"},
        {"event": "after_statement", "step": 2, "statement": "skip"},
        {"event": "execution_finished", "step": 2, "status": "ok", "state": {"X": 1}, "error": None},
    ]

def test_if_checks_condition_then_runs_one_branch():
    assert short(events_of("begin if X > 0 then X := 0 else skip end", X=5)) == [
        {"event": "before_statement", "step": 0, "statement": "if"},
        {"event": "condition_checked", "step": 1, "statement": "if", "result": True},
        {"event": "before_statement", "step": 1, "statement": "assign"},
        {"event": "variable_changed", "step": 2, "name": "X", "old": 5, "new": 0},
        {"event": "after_statement", "step": 2, "statement": "assign"},
        {"event": "after_statement", "step": 2, "statement": "if"},
        {"event": "execution_finished", "step": 2, "status": "ok", "state": {"X": 0}, "error": None},
    ]

def test_while_checks_condition_on_every_iteration():
    events = events_of(POWER, X=3, Y=4)
    checks = of_type(events, ConditionChecked)
    assert [check.result for check in checks] == [True, True, True, True, False]
    assert all(check.statement == "while" for check in checks)
    assert short(of_type(events, BeforeStatement))[1] == {
        "event": "before_statement", "step": 1, "statement": "while",
    }

def test_block_and_sequence_produce_no_events_of_their_own():
    assert short(events_of("begin begin skip end end")) == short(events_of("begin skip end"))

def test_every_before_has_a_matching_after():
    events = events_of(POWER, X=3, Y=4)
    depth = 0
    for event in events:
        if isinstance(event, BeforeStatement):
            depth += 1
        elif isinstance(event, AfterStatement):
            depth -= 1
            assert depth >= 0
    assert depth == 0

def test_steps_never_decrease_and_match_the_step_counter():
    events = events_of(POWER, X=3, Y=4)
    steps = [event.step for event in events]
    assert steps == sorted(steps)
    assert events[-1].step == 14  # same count as Interpreter.steps

# ---- Variable changes ----

def test_variable_changes_record_old_and_new_values():
    changes = of_type(events_of("begin X := 1; X := X + 1 end"), VariableChanged)
    assert [(c.name, c.old, c.new) for c in changes] == [("X", None, 1), ("X", 1, 2)]

def test_replaying_changes_gives_the_final_state():
    initial = {"X": 3, "Y": 4}
    events = trace(parse(POWER), initial)
    state = dict(initial)
    for change in of_type(events, VariableChanged):
        assert state.get(change.name) == change.old
        state[change.name] = change.new
    assert state == run(parse(POWER), initial) == events[-1].state

# ---- Finish and errors ----

def test_trace_ends_with_execution_finished():
    finished = events_of(POWER, X=2, Y=3)[-1]
    assert isinstance(finished, ExecutionFinished)
    assert finished.ok
    assert finished.state == {"R": 8, "X": 2, "Y": 0}

def test_runtime_error_ends_trace_instead_of_raising():
    events = events_of("begin X := 1;\n  Y := Z end")
    finished = events[-1]
    assert isinstance(finished, ExecutionFinished)
    assert not finished.ok
    assert isinstance(finished.error, SiplRuntimeError)
    assert finished.state == {"X": 1}  # state at the moment of the error
    assert finished.to_dict()["status"] == "error"
    assert finished.to_dict()["error"]["span"] == {"line": 2, "column": 8, "end_line": 2, "end_column": 9}

def test_step_limit_ends_trace():
    events = trace(parse("begin while 1 = 1 do skip end"), max_steps=50)
    finished = events[-1]
    assert isinstance(finished.error, ExecutionLimitExceeded)
    assert finished.step == 51

def test_interpreter_run_still_raises_and_reports_finish_to_listener():
    events = []
    interpreter = Interpreter(parse("begin X := Y end"), listener=events.append)
    with pytest.raises(SiplRuntimeError):
        interpreter.run()
    assert isinstance(events[-1], ExecutionFinished)
    assert not events[-1].ok

def test_listener_gets_the_same_events_as_trace():
    events = []
    Interpreter(parse(POWER), {"X": 2, "Y": 2}, listener=events.append).run()
    assert events == trace(parse(POWER), {"X": 2, "Y": 2})

def test_run_without_listener_is_unchanged():
    assert run(parse(POWER), {"X": 2, "Y": 10})["R"] == 1024

# ---- Positions ----

def test_events_point_to_source():
    events = events_of("begin\n  X := 1;\n  if X > 0 then skip else skip\nend")
    assert events[0].span == SourceSpan(2, 3, 2, 9)  # X := 1
    check = of_type(events, ConditionChecked)[0]
    assert check.span == SourceSpan(3, 6, 3, 11)  # X > 0
    assert events[-1].span == SourceSpan(1, 1, 4, 4)  # whole program

# ---- JSON ----

def test_json_round_trip():
    events = events_of("begin X := 1 end")
    data = json.loads(to_json(events))
    assert data == [event.to_dict() for event in events]
    assert data[0]["span"] == {"line": 1, "column": 7, "end_line": 1, "end_column": 13}

def test_json_keeps_cyrillic_readable():
    assert "не має значення" in to_json(events_of("begin X := Y end"))