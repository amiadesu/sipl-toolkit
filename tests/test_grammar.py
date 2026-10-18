from pathlib import Path

import pytest
from lark import Token, Tree
from lark.exceptions import UnexpectedInput

from sipl.grammar import RULES, create_parser, grammar_text

CASES = Path(__file__).resolve().parent / "grammar"
VALID = sorted((CASES / "valid").glob("*.sipl"))
INVALID = sorted((CASES / "invalid").glob("*.sipl"))

def parse(source: str) -> Tree:
    return create_parser().parse(source)

def shape(node):
    # Tree as nested tuples: ('add', ('a_num', ('num', '1')), ...)
    if isinstance(node, Token):
        return str(node)
    return (node.data, *(shape(child) for child in node.children))

def stmt(source: str):
    # Shape of the single statement in `begin <source> end`.
    return shape(parse(f"begin {source} end").children[0])

def aexp(source: str):
    return stmt(f"Z := {source}")[2]

def bexp(source: str):
    return stmt(f"while {source} do skip")[1]

def num(value: str):
    return ("a_num", ("num", value))

def var(name: str):
    return ("a_var", ("var", name))

ASSIGN_X1 = ("assign", ("var", "X"), num("1"))

# ---- Program corpus ----

def test_corpus_is_large_enough():
    assert len(VALID) >= 10
    assert len(INVALID) >= 10

@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_program_is_accepted(path):
    tree = parse(path.read_text(encoding="utf-8"))
    assert tree.data == "program"

@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_program_is_rejected_with_position(path):
    with pytest.raises(UnexpectedInput) as info:
        parse(path.read_text(encoding="utf-8"))
    assert info.value.line >= 1
    assert info.value.column >= 1

def test_every_course_rule_is_used_by_valid_programs():
    used = set()
    for path in VALID:
        tree = parse(path.read_text(encoding="utf-8"))
        used.update(subtree.data for subtree in tree.iter_subtrees())
    assert set(RULES) - used == set() # all course rules are used by at least one valid program.

def test_every_course_rule_exists_in_grammar():
    text = grammar_text()
    for node_name, course_rule in RULES.items():
        assert node_name in text, f"{course_rule} ({node_name}) is missing from the grammar"

# ---- Statements (P1, S1-S6) ----

def test_program_must_be_a_begin_end_block():
    assert parse("begin skip end").data == "program"
    with pytest.raises(UnexpectedInput):
        parse("skip")

def test_assignment():
    assert stmt("X := 1") == ASSIGN_X1

def test_sequence_is_left_associative():
    assert stmt("X := 1; X := 1; skip") == ("seq", ("seq", ASSIGN_X1, ASSIGN_X1), ("skip",))

def test_while_body_ends_at_semicolon():
    assert stmt("while X > 0 do X := 1; skip") == (
        "seq", ("while_do", ("gt", var("X"), num("0")), ASSIGN_X1), ("skip",),
    )

def test_then_branch_may_contain_sequence():
    assert stmt("if X > 0 then X := 1; skip else skip") == (
        "if_else", ("gt", var("X"), num("0")), ("seq", ASSIGN_X1, ("skip",)), ("skip",),
    )

def test_else_branch_ends_at_semicolon():
    tree = stmt("if X > 0 then skip else X := 1; skip")
    assert tree[0] == "seq"
    assert tree[1][0] == "if_else"

def test_nested_block():
    assert stmt("begin skip end") == ("block", ("skip",))

# ---- Arithmetic expressions (A1-A6) ----

def test_multiplication_binds_tighter_than_addition():
    assert aexp("1 + 2 * 3") == ("add", num("1"), ("mul", num("2"), num("3")))

def test_subtraction_is_left_associative():
    assert aexp("8 - 4 - 2") == ("sub", ("sub", num("8"), num("4")), num("2"))

def test_parentheses_override_precedence():
    assert aexp("(1 + 2) * 3") == ("mul", ("aparen", ("add", num("1"), num("2"))), num("3"))

@pytest.mark.parametrize(
    "source, expected",
    [
        ("-1", num("-1")),
        ("X-1", ("sub", var("X"), num("1"))),
        ("X - -1", ("sub", var("X"), num("-1"))),
        ("3 * -4", ("mul", num("3"), num("-4"))),
    ],
)
def test_negative_number_versus_subtraction(source, expected):
    assert aexp(source) == expected

# ---- Conditions (B1-B5) ----

def test_comparisons():
    assert bexp("X = 1") == ("eq", var("X"), num("1"))
    assert bexp("X > 1") == ("gt", var("X"), num("1"))

def test_negation_binds_tighter_than_disjunction():
    assert bexp("¬ X = 1 ∨ X > 1") == (
        "disj", ("neg", ("eq", var("X"), num("1"))), ("gt", var("X"), num("1")),
    )

def test_disjunction_is_left_associative():
    a, b, c = (("eq", var(name), num("0")) for name in "ABC")
    assert bexp("A = 0 ∨ B = 0 ∨ C = 0") == ("disj", ("disj", a, b), c)

def test_parenthesised_condition_and_expression():
    assert bexp("(X > 1)") == ("bparen", ("gt", var("X"), num("1")))
    assert bexp("(X + 1) > 2") == ("gt", ("aparen", ("add", var("X"), num("1"))), num("2"))

def test_ascii_and_unicode_logic_are_equivalent():
    assert bexp("not (X = 0) or X > 1") == bexp("¬(X = 0) ∨ X > 1")

# ---- Lexical rules ----

@pytest.mark.parametrize(
    "name", ["ending", "doX", "iff", "orr", "notX", "skip1", "end_1", "X_2"]
)
def test_names_that_start_like_keywords_are_variables(name):
    assert stmt(f"{name} := 1") == ("assign", ("var", name), num("1"))

@pytest.mark.parametrize(
    "keyword", ["begin", "end", "if", "then", "else", "while", "do", "skip", "or", "not"]
)
def test_keywords_cannot_be_variables(keyword):
    with pytest.raises(UnexpectedInput):
        parse(f"begin {keyword} := 1 end")

def test_whitespace_and_newlines_are_insignificant():
    assert stmt("X:=1") == stmt("X\n  :=\n\t1")

def test_keep_all_tokens_preserves_terminals():
    tree = create_parser(keep_all_tokens=True).parse("begin skip end")
    terminals = [str(t) for t in tree.scan_values(lambda v: isinstance(v, Token))]
    assert terminals == ["begin", "skip", "end"]