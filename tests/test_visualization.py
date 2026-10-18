import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sipl.errors import SiplSyntaxError
from sipl.visualization.parse_tree import build, category, to_dict, to_dot, to_json, to_text

CASES = Path(__file__).resolve().parent / "grammar"
VALID = sorted((CASES / "valid").glob("*.sipl"))

POWER = """\
begin
  R := 1;
  while Y > 0 do
  begin
    R := R * X;
    Y := Y - 1
  end
end"""

def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)

def leaves(node):
    return [n.label for n in walk(node) if n.is_terminal]

def fragment(source: str, span) -> str:
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: span.line - 1]) + span.column - 1
    end = sum(len(line) for line in lines[: span.end_line - 1]) + span.end_column - 1
    return source[start:end]

# ---- Tree structure ----

def test_leaves_are_the_program_tokens_in_order():
    assert leaves(build(POWER)) == [
        "begin", "R", ":=", "1", ";", "while", "Y", ">", "0", "do", "begin",
        "R", ":=", "R", "*", "X", ";", "Y", ":=", "Y", "-", "1", "end", "end",
    ]

def test_nodes_are_labelled_with_course_categories():
    root = build(POWER)
    assert root.label == "<програма>"
    assert [child.label for child in root.children] == ["begin", "<оператор>", "end"]

    first = root.children[1].children[0]  # R := 1
    assert [child.label for child in first.children] == ["<змінна>", ":=", "<вираз>"]
    assert first.children[2].children[0].label == "<число>"

def test_nonterminals_keep_course_rule():
    root = build(POWER)
    assert root.rule == "P1"
    assert root.children[1].rule == "S2"
    assert root.children[1].children[0].rule == "S1"
    assert root.children[0].rule is None  # `begin` is a terminal

def test_parentheses_stay_in_the_tree():
    value = build("begin X := (1) end").children[1].children[2]
    assert value.rule == "A6"
    assert [child.label for child in value.children] == ["(", "<вираз>", ")"]

    cond = build("begin while (X > 0) do skip end").children[1].children[1]
    assert cond.rule == "B5"
    assert [child.label for child in cond.children] == ["(", "<умова>", ")"]

@pytest.mark.parametrize(
    "rule, expected",
    [("P1", "<програма>"), ("S4", "<оператор>"), ("A6", "<вираз>"),
     ("B3", "<умова>"), ("NV", "<змінна>"), ("NN", "<число>")],
)
def test_category(rule, expected):
    assert category(rule) == expected

def test_syntax_error_is_raised():
    with pytest.raises(SiplSyntaxError):
        build("begin X = 1 end")

# ---- Link to the source ----

@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_every_node_text_matches_its_span(path):
    source = path.read_text(encoding="utf-8")
    for node in walk(build(source)):
        assert node.text == fragment(source, node.span)

def test_node_text_and_span():
    root = build(POWER)
    assignment = root.children[1].children[0]
    assert assignment.text == "R := 1"
    assert (assignment.span.line, assignment.span.column) == (2, 3)

    loop = root.children[1].children[2]
    assert loop.text.startswith("while Y > 0 do")
    assert loop.text.endswith("end")

# ---- Text ----

def test_text_output():
    assert to_text(build("begin X := 1 end")) == "\n".join([
        "<програма>",
        "├── begin",
        "├── <оператор>",
        "│   ├── <змінна>",
        "│   │   └── X",
        "│   ├── :=",
        "│   └── <вираз>",
        "│       └── <число>",
        "│           └── 1",
        "└── end",
    ])

def test_text_output_with_rules():
    text = to_text(build("begin skip end"), rules=True)
    assert text.splitlines() == ["<програма> P1", "├── begin", "├── <оператор> S6", "│   └── skip", "└── end"]

# ---- JSON ----

def test_json_round_trip():
    data = json.loads(to_json(build(POWER)))
    assert data == to_dict(build(POWER))
    assert data["label"] == "<програма>"
    assert data["kind"] == "nonterminal"
    assert data["span"] == {"line": 1, "column": 1, "end_line": 8, "end_column": 4}

def test_json_terminal_node():
    begin = to_dict(build("begin skip end"))["children"][0]
    assert begin == {
        "kind": "terminal",
        "label": "begin",
        "rule": None,
        "text": "begin",
        "span": {"line": 1, "column": 1, "end_line": 1, "end_column": 6},
        "children": [],
    }

def test_json_keeps_cyrillic_readable():
    assert "<програма>" in to_json(build("begin skip end"))

# ---- DOT ----

def test_dot_has_a_node_per_tree_node_and_an_edge_per_child():
    root = build(POWER)
    dot = to_dot(root)
    count = len(list(walk(root)))
    assert dot.startswith("digraph parse_tree {")
    assert dot.count("[label=") == count
    assert dot.count(" -> ") == count - 1

def test_dot_tooltip_links_node_to_source():
    dot = to_dot(build("begin\n  skip\nend"))
    assert 'tooltip="2:3-2:7\\nskip"' in dot
    assert 'tooltip="1:1-3:4\\nbegin\\n  skip\\nend"' in dot  # newlines are escaped

def test_dot_with_rules():
    assert 'label="<оператор> S6"' in to_dot(build("begin skip end"), rules=True)

@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz is not installed")
def test_dot_renders_with_graphviz():
    result = subprocess.run(
        ["dot", "-Tsvg"], input=to_dot(build(POWER)), capture_output=True, text=True, check=True
    )
    assert "<svg" in result.stdout
    assert "&lt;програма&gt;" in result.stdout