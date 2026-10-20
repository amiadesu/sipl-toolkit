from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sipl import ast
from sipl.errors import SiplSyntaxError
from sipl.interpreter.interpreter import trace
from sipl.parser import parse
from sipl.visualization import parse_tree

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = ROOT / "examples"
FRONTEND_DIST = ROOT / "web" / "frontend" / "dist"

DEFAULT_MAX_STEPS = 10_000
MAX_STEPS_LIMIT = 100_000
MAX_EVENTS = 5_000

_JS_SAFE_INTEGER = 2**53 - 1

app = FastAPI(title="SIPL sandbox")

class SourceRequest(BaseModel):
    source: str

class RunRequest(SourceRequest):
    initial_state: dict[str, int] = {}
    max_steps: int = Field(DEFAULT_MAX_STEPS, ge=1, le=MAX_STEPS_LIMIT)

def _js_safe(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > _JS_SAFE_INTEGER else value
    if isinstance(value, dict):
        return {key: _js_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_js_safe(item) for item in value]
    return value

def _response(data: dict) -> JSONResponse:
    return JSONResponse(_js_safe(data))

@app.post("/api/analyze")
def analyze(request: SourceRequest) -> JSONResponse:
    # Both trees for the editor; called on every edit.
    try:
        tree = parse_tree.build(request.source)
        program = parse(request.source)
    except SiplSyntaxError as error:
        return _response({"parse_tree": None, "ast": None, "error": error.to_dict()})
    return _response({
        "parse_tree": parse_tree.to_dict(tree),
        "ast": ast.to_dict(program),
        "error": None,
    })

@app.post("/api/run")
def run(request: RunRequest) -> JSONResponse:
    try:
        program = parse(request.source)
    except SiplSyntaxError as error:
        return _response({
            "state": None, "steps": None, "events": None, "truncated": False,
            "error": error.to_dict(),
        })
    events = trace(program, request.initial_state, request.max_steps)
    finished = events[-1]
    truncated = len(events) > MAX_EVENTS
    if truncated:
        events = [*events[: MAX_EVENTS - 1], finished]
    return _response({
        "state": finished.state,
        "steps": finished.step,
        "events": [event.to_dict() for event in events],
        "truncated": truncated,
        "error": finished.error.to_dict() if finished.error else None,
    })

@app.get("/api/examples")
def examples() -> list[dict]:
    return [
        {"name": path.stem, "source": path.read_text(encoding="utf-8")}
        for path in sorted(EXAMPLES_DIR.glob("*.sipl"))
    ]

# After `npm run build`, the same server also serves the frontend.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")