from __future__ import annotations

from sipl.ast import SourceSpan

class SiplError(Exception):
    # An error in a SIPL program (not in the toolkit itself).
    stage = "unknown"

    def __init__(self, message: str, span: SourceSpan | None = None):
        super().__init__(message)
        self.message = message
        self.span = span

    def __str__(self) -> str:
        if self.span is None:
            return self.message
        return f"{self.span.line}:{self.span.column}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "span": self.span.to_dict() if self.span else None,
        }

class SiplSyntaxError(SiplError):
    stage = "parse"

class SiplRuntimeError(SiplError):
    stage = "run"

class ExecutionLimitExceeded(SiplRuntimeError):
    # The program ran out of its step budget (most likely an infinite loop).
    pass