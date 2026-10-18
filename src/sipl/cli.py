from __future__ import annotations

import argparse
import json
import re
import sys

from sipl import ast
from sipl.errors import ExecutionLimitExceeded, SiplError, SiplRuntimeError, SiplSyntaxError
from sipl.interpreter.events import (
    AfterStatement,
    BeforeStatement,
    ConditionChecked,
    Event,
    ExecutionFinished,
    VariableChanged,
)
from sipl.interpreter.interpreter import DEFAULT_MAX_STEPS, Interpreter, trace
from sipl.parser import parse
from sipl.visualization import parse_tree

# Bumped only on incompatible changes to the JSON output (see docs/cli.md).
FORMAT_VERSION = 1

# ---- Exit codes (stable, see docs/cli.md) ----

EXIT_OK = 0
EXIT_SYNTAX_ERROR = 1
EXIT_USAGE_ERROR = 2  # also used by argparse itself
EXIT_RUNTIME_ERROR = 3
EXIT_STEP_LIMIT = 4
EXIT_INPUT_ERROR = 5

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

class _InputError(SiplError):
    stage = "input"

def _exit_code(error: SiplError) -> int:
    if isinstance(error, SiplSyntaxError):
        return EXIT_SYNTAX_ERROR
    if isinstance(error, ExecutionLimitExceeded):
        return EXIT_STEP_LIMIT
    if isinstance(error, SiplRuntimeError):
        return EXIT_RUNTIME_ERROR
    return EXIT_INPUT_ERROR

# ---- Arguments ----

def _parse_assignment(text: str) -> tuple[str, int]:
    name, sep, value = text.partition("=")
    name, value = name.strip(), value.strip()
    if not sep or not _NAME.fullmatch(name):
        raise argparse.ArgumentTypeError(f"очікувалось ІМ'Я=ЧИСЛО, отримано '{text}'")
    try:
        return name, int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"значення '{value}' не є цілим числом") from None

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sipl", description="Інструменти для мови SIPL.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text, description=help_text)
        sub.add_argument("file", help="файл програми SIPL або '-' для стандартного вводу")
        sub.add_argument("--json", action="store_true", help="вивести результат у форматі JSON")
        return sub

    def execution_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "-s", "--set",
            dest="assignments",
            action="append",
            default=[],
            type=_parse_assignment,
            metavar="ІМ'Я=ЧИСЛО",
            help="початкове значення змінної (можна вказати кілька разів)",
        )
        sub.add_argument(
            "--max-steps",
            type=int,
            default=DEFAULT_MAX_STEPS,
            help=f"ліміт кроків виконання (за замовчуванням {DEFAULT_MAX_STEPS})",
        )

    command("check", "перевірити синтаксис програми")
    command("parse", "побудувати AST програми")
    execution_options(command("run", "виконати програму й вивести кінцевий стан"))
    execution_options(command("trace", "виконати програму й вивести всі події виконання"))

    tree = command("tree", "побудувати дерево синтаксичного виводу")
    tree.add_argument(
        "--format", choices=["text", "dot"], default="text",
        help="формат без --json: текст або Graphviz DOT (за замовчуванням text)",
    )
    tree.add_argument("--rules", action="store_true", help="показати правила БНФ курсу")
    return parser

# ---- Input and output ----

def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except (OSError, UnicodeDecodeError) as error:
        raise _InputError(f"не вдалося прочитати '{path}': {error}") from None

def _print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))

def _envelope(command: str, error: SiplError | None, **payload) -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "command": command,
        "status": "error" if error else "ok",
        **payload,
        "error": error.to_dict() if error else None,
    }

def _print_error(path: str, error: SiplError) -> None:
    location = f"{error.span.line}:{error.span.column}:" if error.span else ""
    name = "<stdin>" if path == "-" else path
    print(f"{name}:{location} помилка: {error.message}", file=sys.stderr)

# ---- Text formatting ----

def _ast_text(node: dict, prefix: str = "", lines: list[str] | None = None) -> list[str]:
    lines = [] if lines is None else lines
    children = [(key, value) for key, value in node.items() if isinstance(value, dict) and "type" in value]
    scalars = [str(value) for key, value in node.items()
               if key not in ("type", "span") and not isinstance(value, dict)]
    if not lines:
        lines.append(" ".join([node["type"], *scalars]))
    for index, (role, child) in enumerate(children):
        last = index == len(children) - 1
        child_scalars = [str(value) for key, value in child.items()
                         if key not in ("type", "span") and not isinstance(value, dict)]
        label = " ".join([child["type"], *child_scalars])
        lines.append(f"{prefix}{'└── ' if last else '├── '}{role}: {label}")
        _ast_text(child, prefix + ("    " if last else "│   "), lines)
    return lines

def _event_text(event: Event) -> str:
    span = event.span
    where = f"{span.line}:{span.column}" if span else "-"
    match event:
        case BeforeStatement(statement=statement):
            text = f"▶ {statement}"
        case AfterStatement(statement=statement):
            text = f"◀ {statement}"
        case VariableChanged(name=name, old=old, new=new):
            text = f"  {name} := {new}" + ("" if old is None else f"  (було {old})")
        case ConditionChecked(statement=statement, result=result):
            text = f"  умова {statement}: {'істина' if result else 'хиба'}"
        case ExecutionFinished(error=error):
            text = "■ завершено" if error is None else f"■ помилка: {error.message}"
        case _:
            text = event.kind
    return f"{event.step:>6}  {where:<8} {text}"

def _state_text(state: dict[str, int]) -> str:
    return "\n".join(f"{name} = {value}" for name, value in state.items())

# ---- Commands ----

def _check(args, source: str) -> int:
    try:
        parse(source)
    except SiplSyntaxError as error:
        return _finish(args, error, {})
    if args.json:
        _print_json(_envelope("check", None))
    else:
        print("OK")
    return EXIT_OK

def _parse(args, source: str) -> int:
    try:
        tree = ast.to_dict(parse(source))
    except SiplSyntaxError as error:
        return _finish(args, error, {"ast": None})
    if args.json:
        _print_json(_envelope("parse", None, ast=tree))
    else:
        print("\n".join(_ast_text(tree)))
    return EXIT_OK

def _run(args, source: str) -> int:
    try:
        program = parse(source)
    except SiplSyntaxError as error:
        return _finish(args, error, {"state": None, "steps": None})
    interpreter = Interpreter(program, dict(args.assignments), args.max_steps)
    try:
        interpreter.run()
    except SiplRuntimeError as error:
        payload = {"state": interpreter.state.snapshot(), "steps": interpreter.steps}
        return _finish(args, error, payload)
    state = interpreter.state.snapshot()
    if args.json:
        _print_json(_envelope("run", None, state=state, steps=interpreter.steps))
    elif state:
        print(_state_text(state))
    return EXIT_OK

def _trace(args, source: str) -> int:
    try:
        program = parse(source)
    except SiplSyntaxError as error:
        return _finish(args, error, {"events": None})
    events = trace(program, dict(args.assignments), args.max_steps)
    error = events[-1].error
    if args.json:
        _print_json(_envelope("trace", error, events=[event.to_dict() for event in events]))
    else:
        print("\n".join(_event_text(event) for event in events))
        if error:
            _print_error(args.file, error)
    return _exit_code(error) if error else EXIT_OK

def _tree(args, source: str) -> int:
    try:
        root = parse_tree.build(source)
    except SiplSyntaxError as error:
        return _finish(args, error, {"tree": None})
    if args.json:
        _print_json(_envelope("tree", None, tree=parse_tree.to_dict(root)))
    elif args.format == "dot":
        print(parse_tree.to_dot(root, rules=args.rules))
    else:
        print(parse_tree.to_text(root, rules=args.rules))
    return EXIT_OK

def _finish(args, error: SiplError, payload: dict) -> int:
    # Reports a failed command: JSON envelope on stdout, or a message on stderr.
    if args.json:
        _print_json(_envelope(args.command, error, **payload))
    else:
        _print_error(args.file, error)
    return _exit_code(error)

_COMMANDS = {"check": _check, "parse": _parse, "run": _run, "trace": _trace, "tree": _tree}

def main(argv: list[str] | None = None) -> int:
    # Program text, JSON and messages are UTF-8 regardless of the system locale.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args(argv)
    try:
        source = _read_source(args.file)
    except _InputError as error:
        return _finish(args, error, {})
    return _COMMANDS[args.command](args, source)