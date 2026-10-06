"""Versioned extension execution and settings routes, owned by ECHO."""

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from echo.auth import administrator, caller
from echo.extensions.contracts import ExtensionRequest
from echo.extensions.demo import run_extension_demo
from echo.extensions.ingestion import ExtensionIngestor, IngestionRejected
from echo.extensions.registry import ExtensionRegistry
from echo.extensions.runtime import ExtensionRuntime
from echo.graph_store import EchoGraphStore


class ToggleExtension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@dataclass
class ExtensionPlatform:
    store: EchoGraphStore
    registry: ExtensionRegistry
    runtime: ExtensionRuntime


def build_router(platform: ExtensionPlatform) -> APIRouter:
    router = APIRouter()
    ingestor = ExtensionIngestor(platform.store)

    @router.get("/echo/v1/extensions")
    async def extension_list(identity: str = Depends(caller)) -> dict[str, Any]:
        rows = platform.registry.describe()
        checks = await asyncio.gather(*(platform.runtime.health(row["id"]) for row in rows))
        for row, check in zip(rows, checks, strict=True):
            row["health"] = check.model_dump(mode="json")
        return {"schema_version": "1", "extensions": rows,
                "configuration_scope": "process; ECHO_EXTENSIONS sets startup selection"}

    @router.post("/echo/v1/extensions/{extension_id}/enabled")
    def toggle(extension_id: str, body: ToggleExtension,
               identity: str = Depends(administrator)) -> dict[str, Any]:
        try:
            record = platform.registry.get(extension_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="extension not found") from exc
        if body.enabled and record.adapter is None:
            raise HTTPException(status_code=409, detail="no reviewed adapter is registered")
        platform.registry.set_enabled(extension_id, body.enabled)
        return {"id": extension_id, "enabled": record.enabled, "configuration_scope": "process"}

    @router.post("/echo/v1/extensions/execute")
    async def execute(body: ExtensionRequest, extension_id: str | None = None,
                      identity: str = Depends(caller)) -> dict[str, Any]:
        if body.context.user_id != identity or not body.context.requirement_id:
            raise HTTPException(status_code=403, detail="request must identify the caller's requirement")
        rows = platform.store.read_only_rows(
            "MATCH (r:Requirement {id: $id, user_id: $user}) RETURN r.id",
            {"id": body.context.requirement_id, "user": identity},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="requirement not found")
        providers = [platform.registry.get(extension_id)] if extension_id is not None and extension_id in {
            item["id"] for item in platform.registry.describe() if item["status"] != "INVALID_CONFIGURATION"
        } else platform.registry.find(body.capability)
        if extension_id and not any(record.manifest.id == extension_id for record in providers):
            raise HTTPException(status_code=404, detail="extension not found")
        try:
            # An applied event is replayed without rerunning providers or consuming API quota.
            for record in providers:
                previous = ingestor.existing(record.manifest, body)
                if previous:
                    return {"schema_version": "1", "execution": None, "ingestion": previous}
            execution, attempts = await platform.runtime.execute_with_attempts(body, extension_id=extension_id)
            for attempt in attempts:
                if attempt.run_id != execution.run_id and attempt.extension_id and attempt.result is None:
                    ingestor.ingest(platform.registry.get(attempt.extension_id).manifest, body, attempt)
            ingestion = None
            if execution.extension_id:
                record = platform.registry.get(execution.extension_id)
                ingestion = ingestor.ingest(record.manifest, body, execution)
            return {"schema_version": "1", "execution": execution.model_dump(mode="json", exclude={"result"}),
                    "ingestion": ingestion}
        except IngestionRejected as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.get("/echo/v1/extensions/runs")
    def runs(identity: str = Depends(caller)) -> dict[str, Any]:
        rows = platform.store.read_only_rows(
            "MATCH (run:ExtensionRun {user_id: $user}) RETURN run.id, run.extension_id, run.extension_version, "
            "run.request_id, run.requirement_id, run.status, run.duration_ms, run.started_at, run.error_code "
            "ORDER BY run.started_at DESC LIMIT 50", {"user": identity},
        )
        fields = ["run_id", "extension_id", "extension_version", "request_id", "requirement_id",
                  "status", "duration_ms", "started_at", "error_code"]
        return {"runs": [dict(zip(fields, row, strict=True)) for row in rows]}

    @router.post("/echo/demo/extensions/run")
    async def demo() -> dict[str, Any]:
        return await run_extension_demo(platform.store, platform.runtime)

    return router
