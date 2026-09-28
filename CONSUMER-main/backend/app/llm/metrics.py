from __future__ import annotations

from collections import defaultdict
from typing import Any


class MetricsStore:
    """In-process counters/latency tracker for LLM calls.

    Mirrored to Redis (best-effort, non-blocking) by app.services.cache so
    counts survive restarts and are visible across workers when Redis is
    configured; falls back to purely in-memory numbers otherwise.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._latency_sum_ms: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)
        self._token_totals: dict[str, int] = defaultdict(int)

    def increment(self, key: str, amount: int = 1) -> None:
        self._counters[key] += amount

    def record_latency(self, key: str, milliseconds: float) -> None:
        self._latency_sum_ms[key] += milliseconds
        self._latency_count[key] += 1

    def add_tokens(self, key: str, amount: int | None) -> None:
        if amount:
            self._token_totals[key] += amount

    def average_latency_ms(self, key: str) -> float | None:
        count = self._latency_count.get(key, 0)
        if not count:
            return None
        return round(self._latency_sum_ms[key] / count, 1)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(sorted(self._counters.items())),
            "average_latency_ms": {
                key: self.average_latency_ms(key) for key in sorted(self._latency_count)
            },
            "token_totals": dict(sorted(self._token_totals.items())),
        }

    def reset(self) -> None:
        self._counters.clear()
        self._latency_sum_ms.clear()
        self._latency_count.clear()
        self._token_totals.clear()


metrics = MetricsStore()
