import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.errors import ProxyError


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Combines request-context/metrics tracking and rate limiting in one
    dispatch pass. These were previously two separate BaseHTTPMiddleware
    subclasses stacked via two app.add_middleware() calls -- Starlette's
    BaseHTTPMiddleware wraps each layer's response in its own anyio stream,
    and nesting two of them is a known trigger for intermittent
    "anyio.WouldBlock" / "anyio.EndOfStream" crashes on longer-running
    requests (observed live: a multi-agent request that legitimately takes
    20+ seconds occasionally hit this). Merging into a single middleware
    removes the extra nesting layer entirely."""

    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        from app.llm.metrics import metrics

        settings = get_settings()
        if request.url.path not in {"/health", "/docs", "/openapi.json"}:
            key = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
            now = time.time()
            window = self.requests[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= settings.rate_limit_per_minute:
                raise ProxyError("Rate limit exceeded", status_code=429, code="rate_limited")
            window.append(now)

        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()
        # Group by route template (e.g. "/cases/{case_id}"), not the raw path
        # with its real ID, so latency/error stats aggregate per-endpoint.
        route_path = request.url.path
        for route in request.app.routes:
            if getattr(route, "path_regex", None) and route.path_regex.match(route_path):
                route_path = route.path
                break
        try:
            response = await call_next(request)
        except Exception:
            metrics.increment(f"api_errors.{request.method}.{route_path}")
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.record_latency(f"api.{request.method}.{route_path}", elapsed_ms)
        metrics.increment("api_requests_total")
        if response.status_code >= 400:
            metrics.increment(f"api_errors.{request.method}.{route_path}")
        response.headers["x-request-id"] = request_id
        response.headers["x-process-time-ms"] = str(round(elapsed_ms, 2))
        return response
