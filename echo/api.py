"""PeoplePay ECHO HTTP API and small, graph-backed demonstration UI."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, StrictBool

from echo.demo_data import DEMO_SCOPE, REQUIREMENT_ID
from echo.engine import EchoEngine
from echo.graph_store import EchoGraphStore
from echo.models import Requirement
from echo.auth import caller, administrator, identity_mode
from echo.approval import approve
from echo.extensions.bootstrap import build_registry
from echo.extensions.runtime import ExtensionRuntime
from echo.extensions.api import ExtensionPlatform, build_router
from echo.journey import build_journey_router

logger = logging.getLogger("peoplepay.echo")
class BoundedBodyMiddleware:
    """Reject oversized mutating requests before retaining their full body."""

    def __init__(self, app, limit: int = 65536):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        declared = headers.get(b"content-length")
        if declared:
            try:
                if int(declared) > self.limit:
                    response = JSONResponse({"detail": "request body exceeds 64 KiB"}, status_code=413)
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse({"detail": "invalid content length"}, status_code=400)
                await response(scope, receive, send)
                return
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                response = JSONResponse({"detail": "request body exceeds 64 KiB"}, status_code=413)
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)


app = FastAPI(
    title="PeoplePay ECHO",
    version="0.1.0",
    description="Correlation-aware procurement evidence and decision provenance.",
)
web = Path(__file__).parent / "web"
store = EchoGraphStore()
engine = EchoEngine(store)
registry = build_registry()
runtime = ExtensionRuntime(registry)
app.include_router(build_router(ExtensionPlatform(store, registry, runtime)))
app.include_router(build_journey_router(store))


app.add_middleware(BoundedBodyMiddleware)


def owned_requirement(requirement_id: str, identity: str) -> None:
    rows = store.read_only_rows("MATCH (r:Requirement {id: $id, user_id: $user}) RETURN r.id",
                                {"id": requirement_id, "user": identity})
    if not rows:
        raise HTTPException(status_code=404, detail="requirement not found")


def owned_decision(decision_id: str, identity: str) -> None:
    rows = store.read_only_rows("MATCH (d:Decision {id: $id}) RETURN d.user_id, d.demo_scope", {"id": decision_id})
    if not rows or (not rows[0][1] and rows[0][0] != identity):
        raise HTTPException(status_code=404, detail="decision not found")


class CreateRequirement(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1000)
    quantity: int = Field(gt=0, le=100000)
    budget_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    delivery_days: int | None = Field(default=None, gt=0, le=3650)


class InvalidateSource(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ApproveDecision(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    human_confirmation: StrictBool


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(web / "index.html")


@app.get("/app.js", include_in_schema=False)
def javascript() -> FileResponse:
    return FileResponse(web / "app.js", media_type="text/javascript")


@app.get("/styles.css", include_in_schema=False)
def stylesheet() -> FileResponse:
    return FileResponse(web / "styles.css", media_type="text/css")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(web / "favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        return {"status": "ok", "service": "peoplepay-echo", "graph": store.ping(),
                "graph_name": store.graph_name, "identity_mode": identity_mode()}
    except Exception as exc:  # noqa: BLE001
        logger.exception("ECHO graph health check failed")
        raise HTTPException(status_code=503, detail="FalkorDB is unavailable") from exc


@app.post("/echo/requirements", status_code=201)
def create_requirement(body: CreateRequirement, identity: str = Depends(caller)) -> dict[str, Any]:
    if body.user_id != identity:
        raise HTTPException(status_code=403, detail="user_id must match the authenticated caller")
    requirement = Requirement(id=f"req-{uuid4().hex}", **body.model_dump())
    record = requirement.model_dump(mode="json")
    try:
        store.upsert_node("User", {"id": requirement.user_id})
        store.upsert_node("Requirement", record)
        store.link("User", requirement.user_id, "CREATED", "Requirement", requirement.id)
        return {"requirement": record}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Requirement could not be persisted")
        raise HTTPException(status_code=503, detail="FalkorDB write failed") from exc


@app.post("/echo/demo/run")
def run_demo() -> dict[str, Any]:
    """Seed and evaluate the named, synthetic false-consensus fixture."""
    try:
        return engine.run_false_consensus_demo()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Synthetic ECHO demonstration failed")
        raise HTTPException(status_code=503, detail="ECHO graph evaluation failed") from exc


@app.post("/echo/requirements/{requirement_id}/evaluate")
def evaluate_requirement(requirement_id: str, identity: str = Depends(caller)) -> dict[str, Any]:
    owned_requirement(requirement_id, identity)
    try:
        return engine.analyze_requirement(requirement_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Requirement evaluation failed")
        raise HTTPException(status_code=503, detail="ECHO graph evaluation failed") from exc


@app.get("/echo/decisions/{decision_id}/trace")
def decision_trace(decision_id: str, identity: str = Depends(caller)) -> dict[str, Any]:
    owned_decision(decision_id, identity)
    try:
        rows = store.query_file("05_decision_trace.cypher", {"decision_id": decision_id})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Decision trace query failed")
        raise HTTPException(status_code=503, detail="ECHO graph read failed") from exc
    if not rows:
        raise HTTPException(status_code=404, detail="decision not found")
    return {"decision_id": decision_id, "decision_status": rows[0][1], "recommended_supplier_id": rows[0][2], "candidates": [
        {
            "decision_status": row[1],
            "recommended_supplier_id": row[2],
            "candidate_id": row[3],
            "supplier_id": row[4],
            "supplier_name": row[5],
            "raw_score": row[6],
            "robust_score": row[7],
            "evidence_trace": json.loads(row[8]) if row[8] else [],
        } for row in rows if row[3] is not None
    ]}


@app.post("/echo/decisions/{decision_id}/approve", status_code=201)
def approve_decision(decision_id: str, body: ApproveDecision, request: Request,
                     identity: str = Depends(caller)) -> dict[str, Any]:
    if body.user_id != identity:
        raise HTTPException(status_code=403, detail="approval must identify the authenticated caller")
    if body.human_confirmation is not True:
        raise HTTPException(status_code=400, detail="explicit human confirmation is required")
    return approve(store, engine, decision_id, identity, request)


@app.post("/echo/sources/{source_id}/invalidate")
def invalidate_source(source_id: str, body: InvalidateSource, identity: str = Depends(administrator)) -> dict[str, Any]:
    try:
        store.invalidate_source(source_id, body.reason, datetime.now(timezone.utc).isoformat())
        rows = store.query_file("06_impacted_decisions.cypher", {"source_id": source_id})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="source not found") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Source invalidation or impact query failed")
        raise HTTPException(status_code=503, detail="ECHO graph invalidation failed") from exc
    affected = [
        {"decision_id": row[0], "transaction_id": row[1], "transaction_state": row[2]}
        for row in rows
    ]
    revaluations = []
    for item in {item["decision_id"]: item for item in affected}.values():
        store.graph.query("MATCH (d:Decision {id: $id}) SET d.evidence_stale = true", params={"id": item["decision_id"]})
        requirement = store.read_only_rows(
            "MATCH (d:Decision {id: $id}) RETURN d.requirement_id",  # fixed, parameterized read
            {"id": item["decision_id"]},
        )
        if requirement and requirement[0][0]:
            revaluations.append(engine.analyze_requirement(
                requirement[0][0], parent_decision_id=item["decision_id"]
            ))
    return {
        "source_id": source_id,
        "invalidation_status": "RECORDED",
        "affected_decisions": affected,
        "revaluations": revaluations,
        "completed_transactions_reversed": False,
    }


@app.get("/echo/demo/lineage")
def demo_lineage() -> dict[str, Any]:
    try:
        rows = store.query_file("03_dependency_clusters.cypher", {"demo_scope": DEMO_SCOPE})
        candidates = store.query_file("10_candidate_evidence_diversity.cypher",
                                     {"requirement_id": REQUIREMENT_ID})
    except Exception as exc:  # noqa: BLE001
        logger.exception("ECHO demo graph traversal failed")
        raise HTTPException(status_code=503, detail="FalkorDB is unavailable") from exc
    return {"dependency_clusters": rows, "candidate_evidence": candidates,
            "source": "FalkorDB traversal", "terminology": "provenance-distinct roots"}
