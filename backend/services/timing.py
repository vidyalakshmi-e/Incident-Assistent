"""Per-stage latency measurement (LATENCY & COST section)."""
from __future__ import annotations

import time
from contextlib import contextmanager


class StageTimer:
    def __init__(self):
        self.timings_ms: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.timings_ms[name] = round(self.timings_ms.get(name, 0.0) + (time.perf_counter() - t) * 1000, 2)

    def merge(self, other: "StageTimer | dict") -> None:
        items = other.timings_ms if isinstance(other, StageTimer) else other
        for k, v in items.items():
            self.timings_ms[k] = round(self.timings_ms.get(k, 0.0) + v, 2)

    def total(self) -> float:
        return round(sum(self.timings_ms.values()), 2)
