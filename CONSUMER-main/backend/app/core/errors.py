import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.errors")


class ProxyError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "proxy_error"):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class LLMUnavailableError(ProxyError):
    """Raised after the ModelRouter exhausts the primary model and its
    fallback. Carries a generic, user-safe message — never the underlying
    provider error text (which may contain endpoint URLs, model ids, or
    other internal detail that shouldn't reach the frontend)."""

    def __init__(self, message: str = "The assistant is temporarily unavailable. Please try again shortly.") -> None:
        super().__init__(message, status_code=503, code="llm_unavailable")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProxyError)
    async def proxy_error_handler(_: Request, exc: ProxyError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Previously this returned a generic 500 with zero server-side trace
        # of what actually failed -- every unhandled exception (an NVIDIA
        # timeout, a bad response shape, anything) was silently swallowed,
        # making these errors unreproducible after the fact.
        logger.exception("unhandled_error path=%s method=%s", request.url.path, request.method)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Unexpected server error"}},
        )
