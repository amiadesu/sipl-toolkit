import importlib.util
import json
import sys
from pathlib import Path

import pytest

RUNNER_PATH = Path(__file__).resolve().parent.parent / "conformance" / "runner.py"

# The runner is a standalone script (not part of the sipl package), so load it by path.
_spec = importlib.util.spec_from_file_location("conformance_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(_spec)
sys.modules["conformance_runner"] = runner
_spec.loader.exec_module(runner)

THIS_IMPLEMENTATION = f'"{sys.executable}" -m sipl'

@pytest.fixture
def fake_implementation(tmp_path):
    # Writes a fake `sipl` that always prints the given output and exit code.
    def make(stdout: str, exit_code: int = 0) -> str:
        script = tmp_path / "fake_sipl.py"
        script.write_text(
            f"import sys\nsys.stdout.write({stdout!r})\nsys.exit({exit_code})\n", encoding="utf-8"
        )
        return f'"{sys.executable}" "{script}"'
    return make

# ---- The suite itself ----

def test_suite_passes_on_this_implementation(capsys):
    assert runner.main(["--cmd", THIS_IMPLEMENTATION]) == 0
    assert "0 failed" in capsys.readouterr().out

def test_cases_are_valid_and_cover_every_command():
    cases = runner.load_cases()
    assert len(cases) >= 15
    assert {case.command for case in cases} == set(runner.COMMANDS)
    for case in cases:
        assert case.program.is_file()
        assert case.expect, case.name

def test_runner_does_not_import_sipl():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "import sipl" not in source
    assert "from sipl" not in source

# ---- Detecting a wrong implementation ----

def test_wrong_output_fails(fake_implementation, capsys):
    cmd = fake_implementation(json.dumps({"status": "ok", "state": {}}))
    assert runner.main(["--cmd", cmd]) == 1
    out = capsys.readouterr().out
    assert "FAIL  run/power" in out
    assert "0 passed" in out

def test_wrong_exit_code_is_reported(fake_implementation):
    case = next(case for case in runner.load_cases() if case.name == "syntax/valid_program")
    cmd = fake_implementation('{"status": "ok", "error": null}', 1)
    result = runner.run_case(runner.split_command(cmd), case)
    assert result.problems == ["exit code: expected 0, got 1"]

def test_non_json_output_is_reported(fake_implementation):
    case = runner.load_cases()[0]
    result = runner.run_case(runner.split_command(fake_implementation("OK")), case)
    assert any("not JSON" in problem for problem in result.problems)

def test_missing_command_is_reported():
    case = runner.load_cases()[0]
    result = runner.run_case(["definitely-not-a-sipl-command"], case)
    assert result.problems == ["command not found: definitely-not-a-sipl-command"]

def test_split_command_posix(monkeypatch):
    monkeypatch.setattr(runner.os, "name", "posix")
    assert runner.split_command('"/opt/my python/python" -m sipl') == ["/opt/my python/python", "-m", "sipl"]

def test_split_command_windows_keeps_backslashes(monkeypatch):
    monkeypatch.setattr(runner.os, "name", "nt")
    assert runner.split_command('"C:\\Program Files\\Python\\python.exe" -m sipl') == [
        "C:\\Program Files\\Python\\python.exe", "-m", "sipl",
    ]

def test_empty_case_directory_fails(tmp_path, capsys):
    assert runner.main(["--cmd", THIS_IMPLEMENTATION, "--cases", str(tmp_path)]) == 1

# ---- Partial matching ----

def test_extra_keys_are_ignored():
    assert runner.mismatches({"a": 1}, {"a": 1, "message": "anything", "span": None}) == []

def test_nested_partial_match():
    expected = {"error": {"stage": "parse", "span": {"line": 1}}}
    actual = {"error": {"stage": "parse", "message": "...", "span": {"line": 1, "column": 9}}}
    assert runner.mismatches(expected, actual) == []

def test_missing_key_and_wrong_value():
    assert runner.mismatches({"a": 1, "b": 2}, {"a": 3}) == [
        "$.a: expected 1, got 3",
        "$.b: missing",
    ]

def test_state_must_match_exactly():
    assert runner.mismatches({"state": {"X": 1}}, {"state": {"X": 1}}) == []
    assert runner.mismatches({"state": {"X": 1}}, {"state": {"X": 1, "Y": 2}}) != []

def test_lists_must_have_same_length():
    assert runner.mismatches([1, 2], [1, 2]) == []
    assert runner.mismatches([1, 2], [1]) != []
    assert runner.mismatches([1, 2], [1, 3]) == ["$[1]: expected 2, got 3"]

def test_type_mismatches():
    assert runner.mismatches({"a": 1}, {"a": {"b": 1}}) == ['$.a: expected 1, got {"b": 1}']
    assert runner.mismatches({"a": {"b": 1}}, {"a": 1}) == ["$.a: expected an object, got 1"]
    assert runner.mismatches(True, 1) != []  # JSON true is not the number 1
    assert runner.mismatches(None, None) == []

# ---- Case files ----

def write_case(directory: Path, name: str, spec: dict, program: str | None = "begin skip end"):
    (directory / f"{name}.json").write_text(json.dumps(spec), encoding="utf-8")
    if program is not None:
        (directory / f"{name}.sipl").write_text(program, encoding="utf-8")

def test_case_with_options_builds_command(tmp_path):
    write_case(tmp_path, "c", {
        "command": "run",
        "initial_state": {"X": 2, "Y": -1},
        "max_steps": 50,
        "expect_exit": 0,
        "expect": {},
    })
    (case,) = runner.load_cases(tmp_path)
    assert runner.build_command(["sipl"], case) == [
        "sipl", "run", str(tmp_path / "c.sipl"), "--json",
        "--set", "X=2", "--set", "Y=-1", "--max-steps", "50",
    ]

@pytest.mark.parametrize(
    "spec, program, message",
    [
        ({"command": "run", "expect_exit": 0, "expect": {}}, None, "missing"),
        ({"command": "compile", "expect_exit": 0, "expect": {}}, "begin skip end", "'command'"),
        ({"command": "run", "expect": {}}, "begin skip end", "required"),
    ],
)
def test_invalid_case_files_are_rejected(tmp_path, spec, program, message):
    write_case(tmp_path, "bad", spec, program)
    with pytest.raises(ValueError, match=message):
        runner.load_cases(tmp_path)