from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass

@dataclass(frozen=True)
class SourceSpan:
    # Lines and columns start at 1; `end_*` points just past the last character.
    line: int
    column: int
    end_line: int
    end_column: int

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }

# `span` is excluded from equality, so tests can compare tree structure
# without spelling out positions.
def _span():
    return field(default=None, compare=False, repr=False)

# ---- a: arithmetic expressions ----

@dataclass(frozen=True)
class Num:  # A1
    value: int
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class Var:  # A2
    name: str
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class BinOp:  # A3-A5
    op: str  # "+", "-" or "*"
    left: Expr
    right: Expr
    span: SourceSpan | None = _span()

Expr = Num | Var | BinOp

# ---- b: conditions ----

@dataclass(frozen=True)
class Compare:  # B1-B2
    op: str  # "=" or ">"
    left: Expr
    right: Expr
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class Or:  # B3
    left: Cond
    right: Cond
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class Not:  # B4
    operand: Cond
    span: SourceSpan | None = _span()

Cond = Compare | Or | Not

# ---- S: statements ----

@dataclass(frozen=True)
class Assign:  # S1
    target: Var
    value: Expr
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class Seq:  # S2
    first: Stmt
    second: Stmt
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class If:  # S3
    cond: Cond
    then_branch: Stmt
    else_branch: Stmt
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class While:  # S4
    cond: Cond
    body: Stmt
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class Block:  # S5
    body: Stmt
    span: SourceSpan | None = _span()

@dataclass(frozen=True)
class Skip:  # S6
    span: SourceSpan | None = _span()

Stmt = Assign | Seq | If | While | Block | Skip

# ---- P: program ----

@dataclass(frozen=True)
class Program:  # P1
    body: Stmt
    span: SourceSpan | None = _span()

Node = Program | Stmt | Expr | Cond

def to_dict(node: Node) -> dict:
    # {"type": "BinOp", "op": "+", "left": {...}, "right": {...}, "span": {...}}
    data = {"type": type(node).__name__}
    for node_field in fields(node):
        if node_field.name == "span":
            continue
        value = getattr(node, node_field.name)
        data[node_field.name] = to_dict(value) if is_dataclass(value) else value
    data["span"] = node.span.to_dict() if node.span else None
    return data