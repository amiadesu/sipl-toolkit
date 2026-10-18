from pathlib import Path

import pytest
from lark import Tree

from sipl.ast import (
    Assign,
    BinOp,
    Block,
    Compare,
    If,
    Not,
    Num,
    Or,
    Program,
    Seq,
    Skip,
    SourceSpan,
    Var,
    While,
)
from sipl.errors import SiplSyntaxError
from sipl.parser import parse, parse_tree

CASES = Path(__file__).resolve().parent / "grammar"
VALID = sorted((CASES / "valid").glob("*.sipl"))
INVALID = sorted((CASES / "invalid").glob("*.sipl"))

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
POWER = (EXAMPLES / "power.sipl").read_text(encoding="utf-8")

def body(source: str):
    return parse(f"begin {source} end").body

def expr(source: str):
    return body(f"Z := {source}").value

def cond(source: str):
    return body(f"while {source} do skip").cond

X = Var("X")
ASSIGN_X1 = Assign(X, Num(1))

# ---- parse() converts the Lark tree into own AST nodes ----

@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_every_valid_program_becomes_an_ast(path):
    program = parse(path.read_text(encoding="utf-8"))
    assert isinstance(program, Program)
    assert not isinstance(program, Tree)

def test_parse_tree_returns_concrete_syntax():
    tree = parse_tree("begin skip end", keep_all_tokens=True)
    assert isinstance(tree, Tree)
    assert tree.data == "program"

# ---- Statements ----

def test_power_example():
    assert parse(POWER) == Program(
        Seq(
            Assign(Var("R"), Num(1)),
            While(
                Compare(">", Var("Y"), Num(0)),
                Block(
                    Seq(
                        Assign(Var("R"), BinOp("*", Var("R"), Var("X"))),
                        Assign(Var("Y"), BinOp("-", Var("Y"), Num(1))),
                    )
                ),
            ),
        )
    )

def test_assign_and_skip():
    assert body("X := 1") == ASSIGN_X1
    assert body("skip") == Skip()

def test_sequence_is_binary_and_left_nested():
    assert body("X := 1; X := 1; skip") == Seq(Seq(ASSIGN_X1, ASSIGN_X1), Skip())

def test_if_else():
    assert body("if X > 0 then X := 1 else skip") == If(
        Compare(">", X, Num(0)), ASSIGN_X1, Skip()
    )

def test_while_body_is_single_statement():
    assert body("while X > 0 do X := 1; skip") == Seq(
        While(Compare(">", X, Num(0)), ASSIGN_X1), Skip()
    )

def test_block_is_kept():
    assert body("begin skip end") == Block(Skip())

# ---- Expressions and conditions ----

def test_arithmetic_precedence_and_associativity():
    assert expr("1 + 2 * 3") == BinOp("+", Num(1), BinOp("*", Num(2), Num(3)))
    assert expr("8 - 4 - 2") == BinOp("-", BinOp("-", Num(8), Num(4)), Num(2))

def test_parentheses_do_not_appear_in_ast():
    assert expr("(1 + 2) * 3") == BinOp("*", BinOp("+", Num(1), Num(2)), Num(3))
    assert expr("((X))") == X

def test_negative_numbers_are_values():
    assert expr("-1") == Num(-1)
    assert expr("X - -1") == BinOp("-", X, Num(-1))

def test_conditions():
    assert cond("X = 1") == Compare("=", X, Num(1))
    assert cond("¬ X = 1 ∨ X > 1") == Or(Not(Compare("=", X, Num(1))), Compare(">", X, Num(1)))
    assert cond("(X > 1)") == Compare(">", X, Num(1))

def test_ascii_and_unicode_logic_give_same_ast():
    assert cond("not (X = 0) or X > 1") == cond("¬(X = 0) ∨ X > 1")

# ---- Source spans ----

def test_spans_point_into_source():
    program = parse(POWER)
    assert program.span == SourceSpan(1, 1, 8, 4)

    first = program.body.first  # R := 1
    assert first.span == SourceSpan(2, 3, 2, 9)
    assert first.target.span == SourceSpan(2, 3, 2, 4)
    assert first.value.span == SourceSpan(2, 8, 2, 9)

    loop = program.body.second
    assert loop.span == SourceSpan(3, 3, 7, 6)
    assert loop.cond.span == SourceSpan(3, 9, 3, 14)

    multiply = loop.body.body.first.value  # R * X
    assert multiply.span == SourceSpan(5, 10, 5, 15)

def test_parenthesised_node_spans_its_inner_expression():
    value = expr("(1 + 2)")  # begin Z := (1 + 2) end
    assert value.span == SourceSpan(1, 13, 1, 18)  # `1 + 2`, without parentheses

def test_spans_do_not_affect_equality():
    assert parse("begin X := 1 end") == parse("begin\n\n   X   :=   1\nend")

def test_span_to_dict():
    assert SourceSpan(1, 2, 3, 4).to_dict() == {
        "line": 1, "column": 2, "end_line": 3, "end_column": 4,
    }

# ---- Syntax errors ----

@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_every_invalid_program_gives_syntax_error_with_span(path):
    with pytest.raises(SiplSyntaxError) as info:
        parse(path.read_text(encoding="utf-8"))
    assert info.value.span is not None

@pytest.mark.parametrize(
    "source, line, column, fragment",
    [
        ("X := 1", 1, 1, "'begin'"),
        ("begin X = 1 end", 1, 9, "':='"),
        ("begin\n  X := 1\n  Y := 2\nend", 3, 3, "';'"),
        ("begin if X > 0 then Y := 1 end", 1, 28, "'else'"),
        ("begin X := 1 $ 2 end", 1, 14, "'$'"),
        ("begin X := 4 / 2 end", 1, 14, "'/'"),
        ("begin X := 1", 1, 13, "обривається"),
        ("begin X := 1\n\n  ", 1, 13, "обривається"),
        ("", 1, 1, "обривається"),
        ("begin X := 1 end; skip", 1, 17, "кінець програми"),
        ("begin X := - 1 end", 1, 12, "число"),
    ],
)
def test_syntax_error_position_and_message(source, line, column, fragment):
    with pytest.raises(SiplSyntaxError) as info:
        parse(source)
    error = info.value
    assert (error.span.line, error.span.column) == (line, column)
    assert fragment in error.message

def test_syntax_error_formats():
    with pytest.raises(SiplSyntaxError) as info:
        parse("begin X = 1 end")
    error = info.value
    assert str(error).startswith("1:9: ")
    assert error.to_dict() == {
        "stage": "parse",
        "message": error.message,
        "span": {"line": 1, "column": 9, "end_line": 1, "end_column": 10},
    }