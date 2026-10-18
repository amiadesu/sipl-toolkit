from __future__ import annotations

from lark import Token, Transformer, Tree, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken

from sipl import ast
from sipl.errors import SiplSyntaxError
from sipl.grammar import create_parser

_TERMINAL_NAMES = {
    "NAME": "ім'я змінної",
    "NUMBER": "число",
    "$END": "кінець програми",
}

def _span(meta) -> ast.SourceSpan | None:
    # Works for both Lark rule metadata and tokens.
    if getattr(meta, "empty", False) or getattr(meta, "line", None) is None:
        return None
    return ast.SourceSpan(meta.line, meta.column, meta.end_line, meta.end_column)

@v_args(meta=True)
class _ToAst(Transformer):
    def program(self, meta, children):
        (body,) = children
        return ast.Program(body, _span(meta))

    # ---- S ----

    def assign(self, meta, children):
        target, value = children
        return ast.Assign(target, value, _span(meta))

    def seq(self, meta, children):
        first, second = children
        return ast.Seq(first, second, _span(meta))

    def if_else(self, meta, children):
        cond, then_branch, else_branch = children
        return ast.If(cond, then_branch, else_branch, _span(meta))

    def while_do(self, meta, children):
        cond, body = children
        return ast.While(cond, body, _span(meta))

    def block(self, meta, children):
        (body,) = children
        return ast.Block(body, _span(meta))

    def skip(self, meta, children):
        return ast.Skip(_span(meta))

    # ---- a ----

    def var(self, meta, children):
        (name,) = children
        return ast.Var(str(name), _span(meta))

    def num(self, meta, children):
        (value,) = children
        return ast.Num(int(value), _span(meta))

    def a_num(self, meta, children):
        (node,) = children
        return node

    def a_var(self, meta, children):
        (node,) = children
        return node

    def aparen(self, meta, children):
        # Parentheses only affect the tree shape; the AST does not keep them.
        (node,) = children
        return node

    def add(self, meta, children):
        return ast.BinOp("+", *children, _span(meta))

    def sub(self, meta, children):
        return ast.BinOp("-", *children, _span(meta))

    def mul(self, meta, children):
        return ast.BinOp("*", *children, _span(meta))

    # ---- b ----

    def eq(self, meta, children):
        return ast.Compare("=", *children, _span(meta))

    def gt(self, meta, children):
        return ast.Compare(">", *children, _span(meta))

    def disj(self, meta, children):
        return ast.Or(*children, _span(meta))

    def neg(self, meta, children):
        (operand,) = children
        return ast.Not(operand, _span(meta))

    def bparen(self, meta, children):
        (node,) = children
        return node

def _describe_terminal(name: str) -> str:
    if name in _TERMINAL_NAMES:
        return _TERMINAL_NAMES[name]
    try:
        pattern = create_parser().get_terminal(name).pattern
    except KeyError:
        return name
    return f"'{pattern.value}'" if pattern.type == "str" else name

def _describe_expected(names) -> str:
    described = sorted({_describe_terminal(name) for name in names})
    return ", ".join(described)

def _end_of_source(source: str) -> ast.SourceSpan:
    # Position right after the last non-whitespace character.
    lines = source.rstrip().splitlines() or [""]
    line, column = len(lines), len(lines[-1]) + 1
    return ast.SourceSpan(line, column, line, column)

def _to_syntax_error(error: UnexpectedInput, source: str) -> SiplSyntaxError:
    if isinstance(error, UnexpectedCharacters):
        char = source[error.pos_in_stream]
        span = ast.SourceSpan(error.line, error.column, error.line, error.column + 1)
        return SiplSyntaxError(f"неочікуваний символ '{char}'", span)

    if isinstance(error, UnexpectedToken):
        # accepts() checks every terminal against the real parser state, so it
        # is more precise than `error.expected`, which LALR may over-report.
        expected = error.expected
        if error.interactive_parser is not None:
            expected = error.interactive_parser.accepts() or expected
        expected_text = _describe_expected(expected)

        token = error.token
        if token.type == "$END":
            return SiplSyntaxError(
                f"програма обривається; очікувалось: {expected_text}",
                _end_of_source(source),
            )
        return SiplSyntaxError(
            f"неочікуване '{token}'; очікувалось: {expected_text}",
            _span(token),
        )

    return SiplSyntaxError(str(error))

def parse_tree(source: str, *, keep_all_tokens: bool = False) -> Tree:
    # Concrete syntax: the derivation tree as built by the grammar.
    try:
        return create_parser(keep_all_tokens=keep_all_tokens).parse(source)
    except UnexpectedInput as error:
        raise _to_syntax_error(error, source) from None

def parse(source: str) -> ast.Program:
    # Abstract syntax: typed AST nodes from `sipl.ast` with their positions.
    return _ToAst().transform(parse_tree(source))