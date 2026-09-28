from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("app.llm")


def is_retryable(exc: BaseException) -> bool:
    """Retry on timeouts, connection errors, and 429/5xx — never on 4xx auth/validation errors."""
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return False

    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def _classify_and_count(exc: BaseException) -> None:
    """Bump the relevant counter (timeout/429/503/other) for a failed call."""
    from app.llm.metrics import metrics

    try:
        import httpx
    except ImportError:  # pragma: no cover
        metrics.increment("error_count")
        return

    if isinstance(exc, httpx.TimeoutException):
        metrics.increment("timeout_count")
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            metrics.increment("http_429_count")
        elif status == 503:
            metrics.increment("http_503_count")
        elif status >= 500:
            metrics.increment("http_5xx_count")
        else:
            metrics.increment("http_4xx_count")
    else:
        metrics.increment("error_count")


def build_retrying(max_attempts: int) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(max(1, max_attempts)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(is_retryable),
        reraise=True,
    )


class RateLimiter:
    """Simple async token-bucket limiter, refilled once per rolling 60s window."""

    def __init__(self, requests_per_minute: int) -> None:
        self.requests_per_minute = max(0, requests_per_minute)
        self._timestamps: list[float] = []

    async def acquire(self) -> None:
        if self.requests_per_minute <= 0:
            return
        import asyncio

        while True:
            now = time.monotonic()
            self._timestamps = [t for t in self._timestamps if now - t < 60]
            if len(self._timestamps) < self.requests_per_minute:
                self._timestamps.append(now)
                return
            sleep_for = 60 - (now - self._timestamps[0])
            await asyncio.sleep(max(0.05, sleep_for))


@asynccontextmanager
async def log_llm_call(
    provider: str,
    operation: str,
    purpose: str | None = None,
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Times a provider call and logs latency/outcome; the caller can stash
    token-usage info into the yielded dict before the block exits."""
    from app.llm.metrics import metrics

    record: dict[str, Any] = {}
    start = time.monotonic()
    metric_key = f"{provider}.{operation}"
    try:
        yield record
    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        metrics.increment(f"{metric_key}.failure")
        metrics.record_latency(f"{metric_key}.failure", duration_ms)
        if record.get("retries"):
            metrics.increment(f"{metric_key}.retry", record["retries"])
        _classify_and_count(exc)
        logger.warning(
            "llm_call_failed provider=%s operation=%s purpose=%s model=%s duration_ms=%s retries=%s error=%s",
            provider, operation, purpose, model, duration_ms, record.get("retries", 0), repr(exc),
        )
        raise
    else:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        metrics.increment(f"{metric_key}.success")
        metrics.record_latency(metric_key, duration_ms)
        if record.get("retries"):
            metrics.increment(f"{metric_key}.retry", record["retries"])
        metrics.add_tokens(f"{provider}.prompt_tokens", record.get("prompt_tokens"))
        metrics.add_tokens(f"{provider}.completion_tokens", record.get("completion_tokens"))
        metrics.add_tokens(f"{provider}.total_tokens", record.get("total_tokens"))
        logger.info(
            "llm_call_ok provider=%s operation=%s purpose=%s model=%s duration_ms=%s retries=%s "
            "prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            provider, operation, purpose, model, duration_ms, record.get("retries", 0),
            record.get("prompt_tokens"), record.get("completion_tokens"), record.get("total_tokens"),
        )
