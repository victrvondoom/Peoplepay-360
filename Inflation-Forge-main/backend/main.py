from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.models.domain import InflationDashboard, PriceSnapshot, PriceSyncJob, TrackedItem, TrackedItemCreate
from backend.services.inflation import InflationForgeService
from backend.utils import stable_hash


app = FastAPI(
    title="InflationForge",
    version="1.0.0",
    description="Real item-level inflation, mapped city by city and governed by an extensible capability factory.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=500)
service = InflationForgeService(settings)
static_dir = settings.root / "frontend" / "static"


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
        return response


app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/social-preview.png", include_in_schema=False)
def social_preview() -> FileResponse:
    return FileResponse(
        settings.root / "docs" / "images" / "inflationforge-hero.png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "product": "InflationForge", "modes": service.modes().model_dump(mode="json")}


@app.get("/api/runtime")
def runtime(response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return {
        "map_tile_url": settings.map_tile_url,
        "map_attribution": settings.map_attribution,
        "map_max_zoom": settings.map_max_zoom,
        "signoz_ui_url": settings.signoz_ui_url,
    }


@app.get("/api/dashboard", response_model=InflationDashboard)
def dashboard(response: Response) -> InflationDashboard:
    result = service.dashboard()
    version = stable_hash(result.model_dump(mode="json"), 20)
    response.headers["Cache-Control"] = "public, max-age=15, s-maxage=60, stale-while-revalidate=300"
    response.headers["ETag"] = f'"{version}"'
    return result


@app.post("/api/prices/sync", response_model=PriceSnapshot)
async def sync_prices(force: bool = Query(default=False)) -> PriceSnapshot:
    try:
        return await service.sync(force=force)
    except Exception as exc:
        raise HTTPException(503, f"Live price sync failed: {exc}") from exc


@app.post("/api/prices/sync-async", response_model=PriceSyncJob, status_code=202)
async def sync_prices_async(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=True),
) -> PriceSyncJob:
    job = service.create_sync_job(force=force)
    background_tasks.add_task(service.run_sync_job, job.id)
    return job


@app.get("/api/prices/sync-jobs/{job_id}", response_model=PriceSyncJob)
def sync_job(job_id: str) -> PriceSyncJob:
    try:
        return service.sync_job(job_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/snapshots")
def snapshots() -> list[dict]:
    return service.db.list("price_snapshot", limit=50)


@app.get("/api/snapshots/{snapshot_id}/observations")
def observations(
    response: Response,
    snapshot_id: str,
    city_id: str | None = Query(default=None),
    item_id: str | None = Query(default=None),
) -> list[dict]:
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    rows = service.db.list("price_observation", parent_id=snapshot_id, limit=1000)
    if city_id:
        rows = [row for row in rows if row["city_id"] == city_id]
    if item_id:
        rows = [row for row in rows if row["item_id"] == item_id]
    return rows


@app.get("/api/factory")
def factory() -> dict:
    return {
        "items": [item.model_dump(mode="json") for item in service.factory.list()],
        "counts": service.factory.counts(),
        "source_catalog": [row.model_dump(mode="json") for row in service.source_catalog()],
        "events": [row.model_dump(mode="json") for row in service.factory.events()],
        "port_mode": service.modes().port,
    }


@app.post("/api/items", response_model=TrackedItem, status_code=201)
async def create_item(request: TrackedItemCreate) -> TrackedItem:
    try:
        return await service.create_item(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/items", response_model=list[TrackedItem])
def items(include_retired: bool = True) -> list[TrackedItem]:
    return service.factory.list(include_retired=include_retired)


@app.delete("/api/items/{item_id}", response_model=TrackedItem)
async def retire_item(item_id: str, actor: str = Query("inflation-research-lead")) -> TrackedItem:
    try:
        return await service.retire_item(item_id, actor)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/items/{item_id}/restore", response_model=TrackedItem)
async def restore_item(item_id: str, actor: str = Query("inflation-research-lead")) -> TrackedItem:
    try:
        return await service.restore_item(item_id, actor)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/telemetry")
def telemetry(limit: int = Query(40, ge=1, le=200)) -> list[dict]:
    return service.telemetry_tail(limit)
