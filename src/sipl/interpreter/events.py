from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import ClassVar

from sipl.ast import SourceSpan
from sipl.errors import SiplError

@dataclass(frozen=True)
class Event:
    kind: ClassVar[str] = "event"
    step: int
    span: SourceSpan | None

    def to_dict(self) -> dict:
        data = {"event": self.kind, "step": self.step}
        data.update(self._fields())
        data["span"] = self.span.to_dict() if self.span else None
        return data

    def _fields(self) -> dict:
        return {}

@dataclass(frozen=True)
class BeforeStatement(Event):
    kind: ClassVar[str] = "before_statement"
    statement: str  # "assign", "skip", "if" or "while"

    def _fields(self) -> dict:
        return {"statement": self.statement}

@dataclass(frozen=True)
class AfterStatement(Event):
    kind: ClassVar[str] = "after_statement"
    statement: str

    def _fields(self) -> dict:
        return {"statement": self.statement}

@dataclass(frozen=True)
class VariableChanged(Event):
    kind: ClassVar[str] = "variable_changed"
    name: str
    old: int | None  # None if the variable had no value before
    new: int

    def _fields(self) -> dict:
        return {"name": self.name, "old": self.old, "new": self.new}

@dataclass(frozen=True)
class ConditionChecked(Event):
    kind: ClassVar[str] = "condition_checked"
    statement: str  # "if" or "while"
    result: bool

    def _fields(self) -> dict:
        return {"statement": self.statement, "result": self.result}

@dataclass(frozen=True)
class ExecutionFinished(Event):
    kind: ClassVar[str] = "execution_finished"
    state: dict[str, int]  # final state, or the state at the moment of an error
    error: SiplError | None = field(default=None, compare=False)

    @property
    def ok(self) -> bool:
        return self.error is None

    def _fields(self) -> dict:
        return {
            "status": "ok" if self.ok else "error",
            "state": self.state,
            "error": self.error.to_dict() if self.error else None,
        }

def to_json(events: list[Event], *, indent: int | None = 2) -> str:
    return json.dumps([event.to_dict() for event in events], ensure_ascii=False, indent=indent)