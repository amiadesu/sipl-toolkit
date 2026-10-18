from __future__ import annotations

from collections.abc import Mapping

class State:
    def __init__(self, initial: Mapping[str, int] | None = None):
        self._values: dict[str, int] = dict(initial or {})

    def get(self, name: str) -> int | None:
        return self._values.get(name)

    def set(self, name: str, value: int) -> int | None:
        # Returns the previous value (None if there was none), which a trace needs.
        old = self._values.get(name)
        self._values[name] = value
        return old

    def snapshot(self) -> dict[str, int]:
        # Sorted copy, so JSON output and test comparisons are stable.
        return dict(sorted(self._values.items()))

    def __repr__(self) -> str:
        values = ", ".join(f"{name}={value}" for name, value in self.snapshot().items())
        return f"State({values})"