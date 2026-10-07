"""Provider/model health with cooldowns. Injectable clock.

State is derived from observed outcomes -- never invented. RATE_LIMITED honours
Retry-After; repeated failures mark a route DEGRADED then temporarily UNAVAILABLE so
we stop sending every user request into a known failure; success heals it.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .canonical import Health
from .errors import ErrorCode, GatewayError

DEFAULT_RATE_COOLDOWN = 30.0
MAX_COOLDOWN = 300.0
DEGRADE_AFTER = 2
UNAVAILABLE_AFTER = 4


@dataclass
class _State:
    state: Health = Health.UNKNOWN
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_error: str | None = None
    last_ok_at: float | None = None
    last_checked_at: float | None = None
    latency_ms: float | None = None      # exponential moving average of observed latency
    rate_limit_count: int = 0


class HealthManager:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._conn: dict[str, _State] = {}
        self._model: dict[str, _State] = {}
        self._lock = threading.Lock()

    def _get(self, d: dict, key: str) -> _State:
        return d.setdefault(key, _State())

    def set_probe(self, connection_id: str, state: Health, latency_ms: float | None, detail: str = "") -> None:
        with self._lock:
            s = self._get(self._conn, connection_id)
            s.state, s.last_checked_at = state, self._clock()
            s.last_error = detail or None
            if state == Health.HEALTHY:
                s.consecutive_failures, s.last_ok_at = 0, self._clock()
                s.cooldown_until = 0.0
            if latency_ms is not None:
                s.latency_ms = latency_ms if s.latency_ms is None else 0.7 * s.latency_ms + 0.3 * latency_ms

    def disable(self, connection_id: str) -> None:
        with self._lock:
            self._get(self._conn, connection_id).state = Health.DISABLED

    def record_success(self, connection_id: str, model_key: str, latency_ms: float | None) -> None:
        with self._lock:
            for d, k in ((self._conn, connection_id), (self._model, model_key)):
                s = self._get(d, k)
                s.state, s.consecutive_failures, s.cooldown_until = Health.HEALTHY, 0, 0.0
                s.last_ok_at, s.last_error = self._clock(), None
                if latency_ms is not None:
                    s.latency_ms = latency_ms if s.latency_ms is None else 0.7 * s.latency_ms + 0.3 * latency_ms

    def record_failure(self, connection_id: str, model_key: str, err: GatewayError) -> None:
        now = self._clock()
        with self._lock:
            c, m = self._get(self._conn, connection_id), self._get(self._model, model_key)
            c.last_error = m.last_error = err.code.value
            if err.code in (ErrorCode.RATE_LIMITED, ErrorCode.QUOTA_EXHAUSTED):
                c.rate_limit_count += 1
                c.consecutive_failures += 1
                backoff = min(MAX_COOLDOWN, DEFAULT_RATE_COOLDOWN * (2 ** (c.consecutive_failures - 1)))
                wait = err.retry_after if err.retry_after is not None else backoff
                if err.code == ErrorCode.QUOTA_EXHAUSTED:
                    wait = max(wait, MAX_COOLDOWN)
                c.state, c.cooldown_until = Health.RATE_LIMITED, now + min(wait, 3600.0)
            elif err.code == ErrorCode.INVALID_CREDENTIALS:
                c.state = Health.AUTH_ERROR
            elif err.code in (ErrorCode.MODEL_NOT_FOUND, ErrorCode.MODEL_UNAVAILABLE):
                m.state, m.cooldown_until = Health.UNAVAILABLE, now + 120.0     # model-level, not provider-level
            elif err.code in (ErrorCode.PROVIDER_UNAVAILABLE, ErrorCode.LOCAL_PROVIDER_OFFLINE, ErrorCode.TIMEOUT,
                              ErrorCode.SERVER_ERROR):
                c.consecutive_failures += 1
                if c.consecutive_failures >= UNAVAILABLE_AFTER or err.code == ErrorCode.LOCAL_PROVIDER_OFFLINE:
                    c.state, c.cooldown_until = Health.UNAVAILABLE, now + min(MAX_COOLDOWN, 20.0 * c.consecutive_failures)
                elif c.consecutive_failures >= DEGRADE_AFTER:
                    c.state = Health.DEGRADED

    def _effective(self, s: _State | None) -> Health:
        if s is None:
            return Health.UNKNOWN
        if s.state in (Health.RATE_LIMITED, Health.UNAVAILABLE) and self._clock() >= s.cooldown_until:
            return Health.DEGRADED    # cooldown over: allow a probing attempt, but not "healthy" yet
        return s.state

    def connection_state(self, cid: str) -> Health:
        with self._lock:
            return self._effective(self._conn.get(cid))

    def model_state(self, model_key: str) -> Health:
        with self._lock:
            return self._effective(self._model.get(model_key))

    def blocked(self, cid: str, model_key: str) -> tuple[bool, str | None]:
        """True when the route should not be tried right now (and why)."""
        with self._lock:
            now = self._clock()
            for label, s in (("provider", self._conn.get(cid)), ("model", self._model.get(model_key))):
                if s is None:
                    continue
                if s.state == Health.DISABLED:
                    return True, "provider disabled"
                if s.state == Health.AUTH_ERROR:
                    return True, "credentials invalid"
                if s.state in (Health.RATE_LIMITED, Health.UNAVAILABLE) and now < s.cooldown_until:
                    why = "rate limited" if s.state == Health.RATE_LIMITED else "unavailable"
                    return True, f"{label} {why} (cooling down {int(s.cooldown_until - now)}s)"
        return False, None

    def latency(self, cid: str, model_key: str) -> float | None:
        with self._lock:
            m, c = self._model.get(model_key), self._conn.get(cid)
            return (m.latency_ms if m and m.latency_ms is not None else (c.latency_ms if c else None))

    def snapshot(self, cid: str) -> dict:
        with self._lock:
            s = self._conn.get(cid)
            if s is None:
                return {"state": Health.UNKNOWN.value}
            return {"state": self._effective(s).value, "last_error": s.last_error, "latency_ms": s.latency_ms,
                    "last_ok_at": s.last_ok_at, "last_checked_at": s.last_checked_at,
                    "cooldown_remaining_s": max(0.0, round(s.cooldown_until - self._clock(), 1)),
                    "rate_limit_count": s.rate_limit_count}
