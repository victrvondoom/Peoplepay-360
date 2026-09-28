from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.startup import run_startup_checks
from app.middleware.request_context import RequestContextMiddleware

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_startup_checks()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="PROXY consumer advocacy backend: healthcare first, multi-domain by design.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)

from app.api.routes.admin_llm import router as admin_llm_router
from app.api.routes.admin_panel import router as admin_panel_router
from app.api.routes.component_health import router as component_health_router

app.include_router(admin_llm_router, prefix="/admin", tags=["admin"])
app.include_router(admin_panel_router, prefix="/admin", tags=["admin panel"])
app.include_router(component_health_router, prefix="/health", tags=["system"])


@app.get("/health/live", tags=["system"])
async def health_live() -> dict:
    """Liveness only: is the process itself up, with no dependency checks.
    Kubernetes liveness probes should hit this, not /health -- a transient
    Qdrant/Neo4j blip must not cause a perfectly healthy pod to be killed
    and restarted, only pulled out of rotation (that's what readiness is for)."""
    return {"status": "alive"}


@app.get("/health", tags=["system"])
async def health() -> dict:
    from app.core.startup import collect_health_status

    status = await collect_health_status()
    overall = "ok" if all(
        component.get("status") in {"ready", "configured", "disabled", "not_configured", "skipped"}
        for component in status.values()
    ) else "degraded"
    return {"status": overall, "service": settings.app_name, "environment": settings.environment, **status}
