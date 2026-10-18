from __future__ import annotations

from collections.abc import Mapping

from sipl import ast
from sipl.errors import ExecutionLimitExceeded, SiplRuntimeError
from sipl.interpreter.state import State

DEFAULT_MAX_STEPS = 100_000

_ARITHMETIC = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
}

_COMPARISON = {
    "=": lambda a, b: a == b,
    ">": lambda a, b: a > b,
}

class Interpreter:
    # Executes a program directly on its AST. 
    # A step is one assignment, one `skip` or one condition check of `if`/`while`; 
    # `;` and begin/end cost nothing.

    def __init__(
        self,
        program: ast.Program,
        initial_state: Mapping[str, int] | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ):
        self.program = program
        self.state = State(initial_state)
        self.max_steps = max_steps
        self.steps = 0

    def run(self) -> State:
        self._execute(self.program.body)
        return self.state

    def _tick(self, node) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise ExecutionLimitExceeded(
                f"перевищено ліміт у {self.max_steps} кроків виконання "
                "(можливо, нескінченний цикл)",
                node.span,
            )

    # ---- S: statements ----

    def _execute(self, node: ast.Stmt) -> None:
        match node:
            case ast.Assign(target, value):
                self._tick(node)
                self.state.set(target.name, self._eval(value))
            case ast.Seq(first, second):
                self._execute(first)
                self._execute(second)
            case ast.If(cond, then_branch, else_branch):
                self._tick(node)
                self._execute(then_branch if self._test(cond) else else_branch)
            case ast.While(cond, body):
                while True:
                    self._tick(node)
                    if not self._test(cond):
                        break
                    self._execute(body)
            case ast.Block(body):
                self._execute(body)
            case ast.Skip():
                self._tick(node)
            case _:
                raise TypeError(f"unknown statement: {type(node).__name__}")

    # ---- a: arithmetic expressions ----

    def _eval(self, node: ast.Expr) -> int:
        match node:
            case ast.Num(value):
                return value
            case ast.Var(name):
                value = self.state.get(name)
                if value is None:
                    raise SiplRuntimeError(f"змінна '{name}' не має значення", node.span)
                return value
            case ast.BinOp(op, left, right):
                return _ARITHMETIC[op](self._eval(left), self._eval(right))
            case _:
                raise TypeError(f"unknown expression: {type(node).__name__}")

    # ---- b: conditions ----

    def _test(self, node: ast.Cond) -> bool:
        match node:
            case ast.Compare(op, left, right):
                return _COMPARISON[op](self._eval(left), self._eval(right))
            case ast.Or(left, right):
                # Both sides are always evaluated: if either one is undefined
                # (uses a variable without a value), so is the whole condition.
                first, second = self._test(left), self._test(right)
                return first or second
            case ast.Not(operand):
                return not self._test(operand)
            case _:
                raise TypeError(f"unknown condition: {type(node).__name__}")

def run(
    program: ast.Program,
    initial_state: Mapping[str, int] | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> dict[str, int]:
    # Runs the program and returns its final state.
    return Interpreter(program, initial_state, max_steps).run().snapshot()