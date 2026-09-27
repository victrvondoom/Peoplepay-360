from __future__ import annotations

import time


class CircuitBreaker:
    """Per-key (e.g. per model) circuit breaker.

    Opens after `failure_threshold` consecutive failures and stays open for
    `cooldown_seconds`, during which callers should skip the primary path and
    go straight to a fallback. After the cooldown it half-opens (next call is
    allowed to try again); a success closes it and resets the failure count.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 60) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1, cooldown_seconds)
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def is_open(self, key: str) -> bool:
        opened_at = self._opened_at.get(key)
        if opened_at is None:
            return False
        if time.monotonic() - opened_at >= self.cooldown_seconds:
            # Cooldown elapsed -> half-open: allow one probe attempt through.
            del self._opened_at[key]
            return False
        return True

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
        self._opened_at.pop(key, None)

    def record_failure(self, key: str) -> None:
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count >= self.failure_threshold and key not in self._opened_at:
            self._opened_at[key] = time.monotonic()

    def state(self, key: str) -> dict[str, object]:
        return {
            "consecutive_failures": self._failures.get(key, 0),
            "open": self.is_open(key),
        }

    def snapshot(self) -> dict[str, dict[str, object]]:
        keys = set(self._failures) | set(self._opened_at)
        return {key: self.state(key) for key in sorted(keys)}
