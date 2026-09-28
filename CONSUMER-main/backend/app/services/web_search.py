from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx

from app.core.config import get_settings


class WebSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._minute_bucket: dict[str, list[float]] = {}

    def _redis_client(self):
        try:
            import redis

            return redis.from_url(self.settings.redis_url, socket_connect_timeout=2)
        except Exception:
            return None

    def _cache_key(self, query: str) -> str:
        normalized = " ".join(query.lower().split())
        return f"web_search:{hashlib.sha256(normalized.encode()).hexdigest()}"

    def _rate_limit(self) -> None:
        now = time.time()
        window = self._minute_bucket.setdefault("global", [])
        self._minute_bucket["global"] = [stamp for stamp in window if now - stamp < 60]
        if len(self._minute_bucket["global"]) >= self.settings.web_search_rate_limit_per_minute:
            raise RuntimeError("Web search rate limit exceeded")
        self._minute_bucket["global"].append(now)

    def _read_cache(self, key: str) -> list[dict[str, Any]] | None:
        client = self._redis_client()
        if client is None:
            return None
        raw = client.get(key)
        if not raw:
            return None
        return json.loads(raw)

    def _write_cache(self, key: str, results: list[dict[str, Any]]) -> None:
        client = self._redis_client()
        if client is None:
            return
        client.setex(key, self.settings.web_search_cache_ttl_seconds, json.dumps(results))

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        if not self.settings.tavily_api_key:
            return []
        cache_key = self._cache_key(query)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        self._rate_limit()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            }
            for item in payload.get("results", [])
        ]
        self._write_cache(cache_key, results)
        return results


web_search_service = WebSearchService()
