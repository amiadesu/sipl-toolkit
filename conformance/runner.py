from __future__ import annotations

# SIPL conformance runner.
#
# Runs every case in conformance/cases against an implementation given as a
# command line, using only that command's CLI and JSON output (see
# conformance/README.md). It deliberately does not import `sipl`, so it can test
# any implementation that follows the same CLI contract.
#
#   python conformance/runner.py                      # tests the `sipl` command
#   python conformance/runner.py --cmd "python -m sipl"

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent / "cases"
COMMANDS = ("check", "parse", "run")
# Objects under these keys must match exactly, not partially (see mismatches()).
EXACT_KEYS = {"state"}
TIMEOUT_SECONDS = 30

@dataclass
class Case:
    name: str  # e.g. "run/power"
    program: Path
    command: str
    initial_state: dict[str, int]
    max_steps: int | None
    expect_exit: int
    expect: dict

@dataclass
class Result:
    case: Case
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems

# ---- Loading cases ----

def load_case(spec_path: Path, root: Path) -> Case:
    # Each case is a pair of files with the same name: NAME.sipl and NAME.json.
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    program = spec_path.with_suffix(".sipl")
    name = spec_path.relative_to(root).with_suffix("").as_posix()
    if not program.is_file():
        raise ValueError(f"{name}: program file {program.name} is missing")
    if spec.get("command") not in COMMANDS:
        raise ValueError(f"{name}: 'command' must be one of {', '.join(COMMANDS)}")
    if "expect" not in spec or "expect_exit" not in spec:
        raise ValueError(f"{name}: 'expect' and 'expect_exit' are required")
    return Case(
        name=name,
        program=program,
        command=spec["command"],
        initial_state=spec.get("initial_state", {}),
        max_steps=spec.get("max_steps"),
        expect_exit=spec["expect_exit"],
        expect=spec["expect"],
    )

def load_cases(root: Path = CASES_DIR) -> list[Case]:
    return [load_case(path, root) for path in sorted(root.rglob("*.json"))]

# ---- Comparing ----

def mismatches(expected, actual, path: str = "$") -> list[str]:
    # Partial match: every key in `expected` must be present in `actual` with a
    # matching value; extra keys in `actual` (spans, messages, ...) are ignored,
    # except under EXACT_KEYS, where the whole value must be equal.
    # Lists must have the same length and match element by element.
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected an object, got {json.dumps(actual, ensure_ascii=False)}"]
        problems = []
        for key, value in expected.items():
            if key not in actual:
                problems.append(f"{path}.{key}: missing")
            elif key in EXACT_KEYS and value != actual[key]:
                problems.append(
                    f"{path}.{key}: expected exactly {json.dumps(value, ensure_ascii=False)}, "
                    f"got {json.dumps(actual[key], ensure_ascii=False)}"
                )
            else:
                problems.extend(mismatches(value, actual[key], f"{path}.{key}"))
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected a list of {len(expected)}, got {json.dumps(actual, ensure_ascii=False)}"]
        problems = []
        for index, (item, actual_item) in enumerate(zip(expected, actual)):
            problems.extend(mismatches(item, actual_item, f"{path}[{index}]"))
        return problems
    # `True == 1` in Python, so compare types too for JSON booleans and numbers.
    if expected != actual or isinstance(expected, bool) != isinstance(actual, bool):
        return [
            f"{path}: expected {json.dumps(expected, ensure_ascii=False)}, "
            f"got {json.dumps(actual, ensure_ascii=False)}"
        ]
    return []

# ---- Running ----

def split_command(command: str) -> list[str]:
    # On Windows, backslashes in paths are not escapes, so use non-POSIX mode
    # and drop the quotes it keeps around quoted parts.
    if os.name == "nt":
        return [part.strip('"') for part in shlex.split(command, posix=False)]
    return shlex.split(command)

def build_command(base: list[str], case: Case) -> list[str]:
    command = [*base, case.command, str(case.program), "--json"]
    for name, value in case.initial_state.items():
        command += ["--set", f"{name}={value}"]
    if case.max_steps is not None:
        command += ["--max-steps", str(case.max_steps)]
    return command

def run_case(base: list[str], case: Case) -> Result:
    try:
        completed = subprocess.run(
            build_command(base, case),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return Result(case, [f"command not found: {base[0]}"])
    except subprocess.TimeoutExpired:
        return Result(case, [f"timed out after {TIMEOUT_SECONDS} s"])

    problems = []
    if completed.returncode != case.expect_exit:
        problems.append(f"exit code: expected {case.expect_exit}, got {completed.returncode}")
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError:
        problems.append(f"stdout is not JSON: {completed.stdout[:200]!r} (stderr: {completed.stderr[:200]!r})")
        return Result(case, problems)
    problems.extend(mismatches(case.expect, output))
    return Result(case, problems)

def run_all(base: list[str], cases: list[Case], verbose: bool = False) -> list[Result]:
    results = []
    for case in cases:
        result = run_case(base, case)
        results.append(result)
        if result.passed:
            if verbose:
                print(f"PASS  {case.name}")
        else:
            print(f"FAIL  {case.name}")
            for problem in result.problems:
                print(f"      {problem}")
    return results

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SIPL conformance suite.")
    parser.add_argument(
        "--cmd", default="sipl",
        help='command that starts the implementation (default: "sipl")',
    )
    parser.add_argument("--cases", type=Path, default=CASES_DIR, help="directory with test cases")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list passed cases")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    results = run_all(split_command(args.cmd), cases, args.verbose)
    failed = sum(not result.passed for result in results)
    print(f"{len(results) - failed} passed, {failed} failed, {len(results)} total")
    return 1 if failed or not results else 0

if __name__ == "__main__":
    sys.exit(main())