import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sipl.cli import (
    EXIT_INPUT_ERROR,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    EXIT_STEP_LIMIT,
    EXIT_SYNTAX_ERROR,
    EXIT_USAGE_ERROR,
    FORMAT_VERSION,
    main,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
POWER = str(EXAMPLES / "power.sipl")
GCD = str(EXAMPLES / "gcd.sipl")

def cli(capsys, *args, stdin: str | None = None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err

def cli_json(capsys, *args, **kwargs):
    code, out, err = cli(capsys, *args, "--json", **kwargs)
    assert err == ""
    data = json.loads(out)
    assert data["format_version"] == FORMAT_VERSION
    return code, data

@pytest.fixture
def program(tmp_path):
    # Writes a program to a temporary file and returns its path.
    def write(source: str) -> str:
        path = tmp_path / "program.sipl"
        path.write_text(source, encoding="utf-8")
        return str(path)
    return write

# ---- check ----

def test_check_ok(capsys):
    assert cli(capsys, "check", POWER) == (EXIT_OK, "OK\n", "")

def test_check_syntax_error(capsys, program):
    path = program("begin X = 1 end")
    code, out, err = cli(capsys, "check", path)
    assert code == EXIT_SYNTAX_ERROR
    assert out == ""
    assert err.startswith(f"{path}:1:9: помилка: ")

def test_check_json(capsys, program):
    assert cli_json(capsys, "check", POWER) == (EXIT_OK, {
        "format_version": FORMAT_VERSION, "command": "check", "status": "ok", "error": None,
    })
    code, data = cli_json(capsys, "check", program("begin X = 1 end"))
    assert code == EXIT_SYNTAX_ERROR
    assert data["status"] == "error"
    assert data["error"]["stage"] == "parse"
    assert data["error"]["span"] == {"line": 1, "column": 9, "end_line": 1, "end_column": 10}

# ---- parse ----

def test_parse_text(capsys, program):
    code, out, _ = cli(capsys, "parse", program("begin X := 1 + 2 end"))
    assert code == EXIT_OK
    assert out.splitlines() == [
        "Program",
        "└── body: Assign",
        "    ├── target: Var X",
        "    └── value: BinOp +",
        "        ├── left: Num 1",
        "        └── right: Num 2",
    ]

def test_parse_json(capsys, program):
    code, data = cli_json(capsys, "parse", program("begin X := 1 end"))
    assert code == EXIT_OK
    assignment = data["ast"]["body"]
    assert assignment["type"] == "Assign"
    assert assignment["target"] == {
        "type": "Var", "name": "X", "span": {"line": 1, "column": 7, "end_line": 1, "end_column": 8},
    }
    assert assignment["value"]["value"] == 1

def test_parse_json_syntax_error(capsys, program):
    code, data = cli_json(capsys, "parse", program("begin end"))
    assert code == EXIT_SYNTAX_ERROR
    assert data["ast"] is None

# ---- run ----

def test_run_prints_final_state(capsys):
    code, out, _ = cli(capsys, "run", POWER, "-s", "X=2", "--set", "Y=10")
    assert code == EXIT_OK
    assert out == "R = 1024\nX = 2\nY = 0\n"

def test_run_json(capsys):
    code, data = cli_json(capsys, "run", POWER, "-s", "X=3", "-s", "Y=4")
    assert code == EXIT_OK
    assert data == {
        "format_version": FORMAT_VERSION,
        "command": "run",
        "status": "ok",
        "state": {"R": 81, "X": 3, "Y": 0},
        "steps": 14,
        "error": None,
    }

def test_run_negative_initial_value(capsys):
    _, data = cli_json(capsys, "run", POWER, "-s", "X=-2", "-s", "Y=3")
    assert data["state"]["R"] == -8

def test_run_runtime_error_keeps_partial_state(capsys, program):
    path = program("begin X := 1;\n  Y := Z end")
    code, out, err = cli(capsys, "run", path)
    assert code == EXIT_RUNTIME_ERROR
    assert out == ""
    assert err == f"{path}:2:8: помилка: змінна 'Z' не має значення\n"

    code, data = cli_json(capsys, "run", path)
    assert code == EXIT_RUNTIME_ERROR
    assert data["state"] == {"X": 1}
    assert data["steps"] == 2
    assert data["error"]["stage"] == "run"

def test_run_step_limit(capsys, program):
    path = program("begin while 1 = 1 do skip end")
    code, _, err = cli(capsys, "run", path, "--max-steps", "100")
    assert code == EXIT_STEP_LIMIT
    assert "100" in err

def test_run_syntax_error_json(capsys, program):
    code, data = cli_json(capsys, "run", program("begin X := end"))
    assert code == EXIT_SYNTAX_ERROR
    assert data["state"] is None and data["steps"] is None

def test_run_from_stdin(capsys, monkeypatch):
    code, out, _ = cli(capsys, "run", "-", stdin="begin X := 2 * 3 end", monkeypatch=monkeypatch)
    assert (code, out) == (EXIT_OK, "X = 6\n")

def test_stdin_errors_are_reported_as_stdin(capsys, monkeypatch):
    _, _, err = cli(capsys, "check", "-", stdin="begin end", monkeypatch=monkeypatch)
    assert err.startswith("<stdin>:1:7: ")

# ---- trace ----

def test_trace_text(capsys, program):
    code, out, _ = cli(capsys, "trace", program("begin X := 1 end"))
    assert code == EXIT_OK
    lines = out.splitlines()
    assert len(lines) == 4
    assert "▶ assign" in lines[0]
    assert "X := 1" in lines[1]
    assert "◀ assign" in lines[2]
    assert "■ завершено" in lines[3]

def test_trace_text_shows_conditions_and_old_values(capsys):
    _, out, _ = cli(capsys, "trace", POWER, "-s", "X=3", "-s", "Y=1")
    assert "умова while: істина" in out
    assert "умова while: хиба" in out
    assert "R := 3  (було 1)" in out

def test_trace_json(capsys):
    code, data = cli_json(capsys, "trace", GCD, "-s", "A=4", "-s", "B=2")
    assert code == EXIT_OK
    events = data["events"]
    assert events[0]["event"] == "before_statement"
    assert events[-1]["event"] == "execution_finished"
    assert events[-1]["state"] == {"A": 2, "B": 2}

def test_trace_runtime_error_still_prints_events(capsys, program):
    path = program("begin X := 1; Y := Z end")
    code, out, err = cli(capsys, "trace", path)
    assert code == EXIT_RUNTIME_ERROR
    assert "■ помилка: змінна 'Z' не має значення" in out
    assert "помилка: змінна 'Z'" in err

    code, data = cli_json(capsys, "trace", path)
    assert code == EXIT_RUNTIME_ERROR
    assert data["status"] == "error"
    assert data["events"][-1]["status"] == "error"

def test_trace_step_limit(capsys, program):
    code, data = cli_json(capsys, "trace", program("begin while 1 = 1 do skip end"), "--max-steps", "10")
    assert code == EXIT_STEP_LIMIT
    assert data["events"][-1]["step"] == 11

def test_trace_syntax_error(capsys, program):
    code, data = cli_json(capsys, "trace", program("skip"))
    assert code == EXIT_SYNTAX_ERROR
    assert data["events"] is None

# ---- tree ----

def test_tree_text(capsys, program):
    code, out, _ = cli(capsys, "tree", program("begin skip end"))
    assert code == EXIT_OK
    assert out.splitlines() == ["<програма>", "├── begin", "├── <оператор>", "│   └── skip", "└── end"]

def test_tree_rules_and_dot(capsys, program):
    path = program("begin skip end")
    _, out, _ = cli(capsys, "tree", path, "--rules")
    assert out.splitlines()[0] == "<програма> P1"
    _, out, _ = cli(capsys, "tree", path, "--format", "dot")
    assert out.startswith("digraph parse_tree {")

def test_tree_json(capsys, program):
    code, data = cli_json(capsys, "tree", program("begin skip end"))
    assert code == EXIT_OK
    assert data["tree"]["label"] == "<програма>"
    assert data["tree"]["rule"] == "P1"

def test_tree_syntax_error(capsys, program):
    code, data = cli_json(capsys, "tree", program("begin end"))
    assert code == EXIT_SYNTAX_ERROR
    assert data["tree"] is None

# ---- Input and usage errors ----

def test_missing_file(capsys, tmp_path):
    missing = str(tmp_path / "missing.sipl")
    code, out, err = cli(capsys, "run", missing)
    assert code == EXIT_INPUT_ERROR
    assert out == ""
    assert "не вдалося прочитати" in err

    code, data = cli_json(capsys, "run", missing)
    assert code == EXIT_INPUT_ERROR
    assert data["error"]["stage"] == "input"
    assert data["error"]["span"] is None

@pytest.mark.parametrize("value", ["X", "X=abc", "1X=2", "=5"])
def test_invalid_initial_value_is_a_usage_error(capsys, value):
    with pytest.raises(SystemExit) as info:
        main(["run", POWER, "-s", value])
    assert info.value.code == EXIT_USAGE_ERROR
    assert "-s/--set" in capsys.readouterr().err

def test_unknown_command_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as info:
        main(["compile", POWER])
    assert info.value.code == EXIT_USAGE_ERROR

# ---- Real processes (the installed entry points) ----

def run_process(*command, stdin: str | None = None):
    return subprocess.run(command, input=stdin, capture_output=True, text=True, encoding="utf-8")

def test_python_dash_m(tmp_path):
    result = run_process(sys.executable, "-m", "sipl", "run", POWER, "-s", "X=2", "-s", "Y=5", "--json")
    assert result.returncode == EXIT_OK
    assert json.loads(result.stdout)["state"]["R"] == 32

def test_python_dash_m_exit_code_and_stdin():
    result = run_process(sys.executable, "-m", "sipl", "run", "-", stdin="begin X := Y end")
    assert result.returncode == EXIT_RUNTIME_ERROR
    assert "<stdin>:1:12: помилка: змінна 'Y' не має значення" in result.stderr

@pytest.mark.skipif(shutil.which("sipl") is None, reason="the sipl command is not installed")
def test_sipl_command():
    result = run_process("sipl", "check", GCD)
    assert (result.returncode, result.stdout) == (EXIT_OK, "OK\n")