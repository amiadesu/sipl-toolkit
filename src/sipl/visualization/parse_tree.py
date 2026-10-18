from __future__ import annotations

import json
from dataclasses import dataclass, field

from lark import Token, Tree

from sipl.ast import SourceSpan
from sipl.grammar import RULES
from sipl.parser import parse_tree

CATEGORIES = {
    "P": "<програма>",
    "S": "<оператор>",
    "A": "<вираз>",
    "B": "<умова>",
    "NV": "<змінна>",
    "NN": "<число>",
}

@dataclass
class ParseNode:
    label: str  # category for nonterminals, the token itself for terminals
    span: SourceSpan
    text: str  # source fragment covered by the node
    rule: str | None = None  # course rule (e.g. "S1"); None for terminals
    children: list[ParseNode] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.rule is None

def category(rule: str) -> str:
    return CATEGORIES.get(rule) or CATEGORIES[rule[0]]

def build(source: str) -> ParseNode:
    return _convert(parse_tree(source, keep_all_tokens=True), source)

def _convert(node: Tree | Token, source: str) -> ParseNode:
    if isinstance(node, Token):
        span = SourceSpan(node.line, node.column, node.end_line, node.end_column)
        return ParseNode(str(node), span, str(node))

    rule = RULES[node.data]
    meta = node.meta
    return ParseNode(
        label=category(rule),
        span=SourceSpan(meta.line, meta.column, meta.end_line, meta.end_column),
        text=source[meta.start_pos:meta.end_pos],
        rule=rule,
        children=[_convert(child, source) for child in node.children],
    )

def _label(node: ParseNode, rules: bool) -> str:
    if rules and not node.is_terminal:
        return f"{node.label} {node.rule}"
    return node.label

# ---- Text ----

def to_text(root: ParseNode, *, rules: bool = False) -> str:
    lines = [_label(root, rules)]
    _text_children(root, "", lines, rules)
    return "\n".join(lines)

def _text_children(node: ParseNode, prefix: str, lines: list[str], rules: bool) -> None:
    for index, child in enumerate(node.children):
        last = index == len(node.children) - 1
        lines.append(prefix + ("└── " if last else "├── ") + _label(child, rules))
        _text_children(child, prefix + ("    " if last else "│   "), lines, rules)

# ---- JSON ----

def to_dict(node: ParseNode) -> dict:
    return {
        "kind": "terminal" if node.is_terminal else "nonterminal",
        "label": node.label,
        "rule": node.rule,
        "text": node.text,
        "span": node.span.to_dict(),
        "children": [to_dict(child) for child in node.children],
    }

def to_json(root: ParseNode, *, indent: int | None = 2) -> str:
    return json.dumps(to_dict(root), ensure_ascii=False, indent=indent)

# ---- DOT (Graphviz) ----

def _dot_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'

def to_dot(root: ParseNode, *, rules: bool = False) -> str:
    lines = [
        "digraph parse_tree {",
        "    ordering=out;",
        '    node [shape=plaintext, fontname="Helvetica"];',
    ]
    _dot_node(root, [0], lines, rules)
    lines.append("}")
    return "\n".join(lines)

def _dot_node(node: ParseNode, counter: list[int], lines: list[str], rules: bool) -> str:
    node_id = f"n{counter[0]}"
    counter[0] += 1

    # The tooltip links the node to its source fragment (shown on hover in SVG).
    span = node.span
    tooltip = f"{span.line}:{span.column}-{span.end_line}:{span.end_column}\n{node.text}"
    attributes = [f"label={_dot_string(_label(node, rules))}", f"tooltip={_dot_string(tooltip)}"]
    if node.is_terminal:
        attributes.append('fontcolor="#1f5fbf"')
    lines.append(f"    {node_id} [{', '.join(attributes)}];")

    for child in node.children:
        child_id = _dot_node(child, counter, lines, rules)
        lines.append(f"    {node_id} -> {child_id};")
    return node_id