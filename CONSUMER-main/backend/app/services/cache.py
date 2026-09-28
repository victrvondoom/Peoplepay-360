from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar
from urllib.parse import urlsplit, urlunsplit

from app.core.config import get_settings


def _redact_url(url: str) -> str:
    """Unlike Qdrant/Neo4j (whose API key/password are separate settings
    fields, never embedded in the URL shown by their health checks), a Redis
    connection string embeds the password inline (redis://user:pass@host) --
    returning it verbatim from a *public, unauthenticated* /health endpoint
    would leak the real credential to anyone who curls it."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.password and not parts.username:
        return url
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

logger = logging.getLogger("app.cache")

T = TypeVar("T")

# redis.asyncio connects lazily on first command, so a construction-time try/except
# never sees a dead Redis — every op must go through _guarded(), which opens an
# outage window on the first real failure so a down Redis costs one timeout, not one
# timeout per cache call.
_OUTAGE_RETRY_SECONDS = 30
_CONNECT_TIMEOUT_SECONDS = 0.5


def _hash(*parts: str) -> str:
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()[:32]


def embedding_cache_key(provider: str, model: str, text: str, input_type: str) -> str:
    return f"cache:embed:{provider}:{model}:{input_type}:{_hash(text)}"


def prompt_cache_key(provider: str, model: str, purpose: str, temperature: float, prompt: str) -> str:
    return f"cache:prompt:{provider}:{model}:{purpose}:{temperature}:{_hash(prompt)}"


def graph_cache_key(domain: str, institution_name: str) -> str:
    return f"cache:graph:{domain}:{_hash(institution_name)}"


def chunks_cache_key(domain: str, query: str, limit: int, filters: dict | None) -> str:
    filters_repr = json.dumps(filters or {}, sort_keys=True)
    return f"cache:chunks:{domain}:{limit}:{_hash(query, filters_repr)}"


class RedisCache:
    """Thin async Redis wrapper that degrades to a no-op when Redis is
    unreachable — caching is a performance optimization here, never a
    correctness dependency, so a down Redis must never break, or meaningfully
    slow down, a request. After the first failed call, further calls are
    skipped entirely for `_OUTAGE_RETRY_SECONDS` instead of retrying a
    connection on every single cache lookup."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        self._down_until = 0.0

    def _client_or_none(self):
        if time.monotonic() < self._down_until:
            return None
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(
                self.settings.redis_url,
                socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                socket_timeout=_CONNECT_TIMEOUT_SECONDS,
                decode_responses=True,
            )
        return self._client

    async def _guarded(self, op_name: str, fn: Callable[[Any], Awaitable[T]], default: T) -> T:
        if not self.settings.cache_enabled:
            return default
        client = self._client_or_none()
        if client is None:
            return default
        try:
            return await fn(client)
        except Exception as exc:
            self._down_until = time.monotonic() + _OUTAGE_RETRY_SECONDS
            logger.debug("redis_cache_%s_failed error=%s (disabling cache for %ss)", op_name, repr(exc), _OUTAGE_RETRY_SECONDS)
            return default

    async def get_json(self, key: str) -> Any | None:
        async def _op(client):
            raw = await client.get(key)
            return json.loads(raw) if raw is not None else None

        return await self._guarded("get", _op, None)

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        async def _op(client):
            await client.set(key, json.dumps(value), ex=max(1, ttl_seconds))

        await self._guarded("set", _op, None)

    async def incr(self, key: str, amount: int = 1) -> None:
        async def _op(client):
            await client.incrby(key, amount)

        await self._guarded("incr", _op, None)

    async def delete(self, key: str) -> None:
        async def _op(client):
            await client.delete(key)

        await self._guarded("delete", _op, None)

    async def health_check(self) -> dict[str, Any]:
        start = time.monotonic()

        async def _op(client):
            await client.ping()
            return True

        ok = await self._guarded("ping", _op, False)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        redacted_url = _redact_url(self.settings.redis_url)
        if ok:
            return {"status": "ready", "url": redacted_url, "latency_ms": latency_ms}
        return {"status": "unreachable", "url": redacted_url, "latency_ms": latency_ms}


redis_cache = RedisCache()
