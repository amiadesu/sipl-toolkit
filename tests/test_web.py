import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="web dependencies are not installed (pip install -e .[web])")

from fastapi.testclient import TestClient

from sipl import ast
from sipl.parser import parse
from sipl.visualization import parse_tree

ROOT = Path(__file__).resolve().parent.parent
POWER = (ROOT / "examples" / "power.sipl").read_text(encoding="utf-8")
FACTORIAL = (ROOT / "examples" / "factorial.sipl").read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("sipl_web_app", ROOT / "web" / "backend" / "main.py")
web = importlib.util.module_from_spec(_spec)
sys.modules["sipl_web_app"] = web
_spec.loader.exec_module(web)

@pytest.fixture
def client():
    return TestClient(web.app)

# ---- /api/analyze ----

def test_analyze_returns_both_trees(client):
    data = client.post("/api/analyze", json={"source": POWER}).json()
    assert data["error"] is None
    assert data["parse_tree"] == parse_tree.to_dict(parse_tree.build(POWER))
    assert data["ast"] == ast.to_dict(parse(POWER))

def test_analyze_syntax_error(client):
    data = client.post("/api/analyze", json={"source": "begin X = 1 end"}).json()
    assert data["parse_tree"] is None and data["ast"] is None
    assert data["error"]["stage"] == "parse"
    assert data["error"]["span"] == {"line": 1, "column": 9, "end_line": 1, "end_column": 10}

# ---- /api/run ----

def test_run_returns_state_steps_and_trace(client):
    data = client.post("/api/run", json={"source": POWER, "initial_state": {"X": 2, "Y": 10}}).json()
    assert data["error"] is None
    assert data["state"] == {"R": 1024, "X": 2, "Y": 0}
    assert data["steps"] == 32
    assert data["truncated"] is False
    assert data["events"][0]["event"] == "before_statement"
    assert data["events"][-1] == {
        "event": "execution_finished", "step": 32, "status": "ok",
        "state": {"R": 1024, "X": 2, "Y": 0}, "error": None, "span": data["events"][-1]["span"],
    }

def test_run_accepts_initial_values_as_strings(client):
    data = client.post("/api/run", json={"source": POWER, "initial_state": {"X": "3", "Y": "2"}}).json()
    assert data["state"]["R"] == 9

def test_big_integers_are_sent_as_strings(client):
    data = client.post("/api/run", json={"source": FACTORIAL, "initial_state": {"N": 25}}).json()
    assert data["state"] == {"F": "15511210043330985984000000", "N": 1}

def test_run_runtime_error_keeps_partial_state(client):
    data = client.post("/api/run", json={"source": "begin X := 1; Y := Z end"}).json()
    assert data["error"]["stage"] == "run"
    assert data["state"] == {"X": 1}
    assert data["events"][-1]["status"] == "error"

def test_run_syntax_error(client):
    data = client.post("/api/run", json={"source": "begin end"}).json()
    assert data["error"]["stage"] == "parse"
    assert data["events"] is None and data["state"] is None

def test_long_trace_is_truncated_but_keeps_final_event(client):
    data = client.post(
        "/api/run", json={"source": "begin while 1 = 1 do skip end", "max_steps": 50_000}
    ).json()
    assert data["truncated"] is True
    assert len(data["events"]) == web.MAX_EVENTS
    assert data["events"][-1]["event"] == "execution_finished"
    assert data["events"][-1]["status"] == "error"
    assert data["steps"] == 50_001

@pytest.mark.parametrize("max_steps", [0, web.MAX_STEPS_LIMIT + 1])
def test_max_steps_is_validated(client, max_steps):
    response = client.post("/api/run", json={"source": POWER, "max_steps": max_steps})
    assert response.status_code == 422

# ---- /api/examples ----

def test_examples(client):
    examples = client.get("/api/examples").json()
    assert [example["name"] for example in examples] == ["factorial", "gcd", "power"]
    assert examples[2]["source"] == POWER

# ---- JSON safety ----

def test_js_safe_converts_only_big_integers():
    limit = 2**53 - 1
    assert web._js_safe({"a": [limit, limit + 1, -limit - 1], "b": True, "c": None, "d": "x"}) == {
        "a": [limit, str(limit + 1), str(-limit - 1)], "b": True, "c": None, "d": "x",
    }