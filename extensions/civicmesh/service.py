"""Thin HTTP boundary over CivicMesh's original Jac deterministic functions.

Run in the isolated CivicMesh environment. No eligibility logic is duplicated;
no graph, LLM, downstream applications or payment credentials are loaded.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from starlette.responses import JSONResponse

from extensions.civicmesh.contracts import ServiceRequest

SOURCE = Path(__file__).resolve().parents[2] / "CivicMesh-main" / "civicmesh"
LOCK = threading.RLock()
NEED_TEXT = {"housing": "I need housing help", "eviction": "My landlord is evicting me",
             "food": "I need food", "healthcare": "I need healthcare",
             "medical_bill": "I cannot afford my hospital medical bill", "legal": "I need legal help",
             "crisis": "I want to kill myself", "domestic_violence": "My partner hits me"}


class NativeEngine:
    def __init__(self):
        # Import hook compiles .jac source in place; the source is never copied.
        sys.path.insert(0, str(SOURCE))
        import jaclang  # type: ignore[import-not-found]  # noqa: F401  # Isolated service runtime.
        self.parse = importlib.import_module("engine.parse")
        self.score = importlib.import_module("engine.score")
        self.plan = importlib.import_module("engine.plan")
        self.paths = importlib.import_module("engine.paths")
        self.policy = importlib.import_module("engine.policy")
        self.resources = json.loads((SOURCE / "data/resources.json").read_text(encoding="utf-8"))["resources"]
        self.edges = json.loads((SOURCE / "data/transitions.json").read_text(encoding="utf-8"))["transitions"]
        tracked = sorted(p for p in [* (SOURCE / "engine").glob("*.jac"), * (SOURCE / "data").glob("*.json")] if p.is_file())
        self.fingerprint = hashlib.sha256(b"".join(p.relative_to(SOURCE).as_posix().encode() + p.read_bytes() for p in tracked)).hexdigest()

    def evaluate(self, body: ServiceRequest):
        start = time.perf_counter()
        text = NEED_TEXT[body.need]
        profile = self.parse.parse_intake(text)
        profile["category"] = {"eviction": "housing", "medical_bill": "healthcare", "crisis": "healthcare", "domestic_violence": "housing"}.get(body.need, body.need)
        profile.update(body.facts.model_dump(exclude_none=True))
        profile["citizenship"] = {"permanent_resident": "eligible_immigrant", "refugee": "humanitarian", "asylee": "humanitarian"}.get(profile["citizenship"], profile["citizenship"])
        profile["language"] = body.language
        flags = list(profile.get("flags", []))
        if (body.facts.age or 0) >= 60 and "senior" not in flags:
            flags.append("senior")
        profile["flags"] = flags
        items = [{"resource": r, "rule": r["eligibility"], "form": r["form"]} for r in self.resources]
        # policy_today reads a process environment date; serialize evaluations.
        with LOCK:
            ranking = self.score.rank_resources(items, profile, text, 6, body.language)
            plan = self.plan.build_plan(ranking["ranked"], profile["urgency"], body.language)
            scores = {s["resource_name"]: float(s["p_eligible"]) * float(s["approval"]["mean"]) for s in ranking["ranked"]}
            starts = [s["resource_name"] for s in ranking["ranked"] if s["tier"] in {"likely", "possible"}]
            goals = {s["resource_name"]: 0.9 for s in ranking["ranked"] if s["capacity"] == "waitlist"}
            routes = self.paths.plan_routes(self.edges, scores, starts, goals, 3, 1)
            policy_date = self.policy.policy_today()
        by_name = {r["agency_name"]: r for r in self.resources}
        selected = [{**s, "rule": by_name[s["resource_name"]]["eligibility"],
                     "policy_definition": self.policy.PROGRAMS.get(by_name[s["resource_name"]]["eligibility"]["rule_id"], {})} for s in ranking["ranked"]]
        return {"request_id": body.request_id, "workflow_id": body.workflow_id, "provider": "civicmesh",
                "provider_version": "1.0.0", "engine_fingerprint": self.fingerprint,
                "policy_version": self.policy.POLICY_VERSION, "policy_date": policy_date,
                "policy_sources": self.policy.policy_sources(), "policy_last_verified": self.policy.POLICY_VERSION,
                "policy_context": {"snap_parameters": self.policy.snap_year()},
                "observed_at": datetime.now(timezone.utc).isoformat(), "jurisdiction": "US",
                "programs": selected, "plan": plan, "routes": routes,
                "question": {**ranking["ask"], "text": self.score.question_for(ranking["ask"]["key"], body.language)},
                "crisis": any(f in flags for f in {"self_harm", "self_harm_concern", "dv", "dv_concern"}),
                "calibrated_probability": False, "duration_ms": round((time.perf_counter() - start) * 1000, 3),
                "warnings": ["US_POLICY_ONLY", "HEURISTIC_SCORES_NOT_PROBABILITIES", "PROGRAM_AVAILABILITY_REQUIRES_REVIEW",
                             "POLICY_SOURCES_ARE_BUNDLED_REFERENCES_NOT_LIVE_VERIFICATION"]}


app = FastAPI(title="PeoplePay CivicMesh deterministic service", docs_url=None, redoc_url=None, openapi_url=None)


class BoundedEvaluationBody:
    """Bound the body before FastAPI decodes it, including chunked requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/v1/evaluate" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > 16_384:
                return await JSONResponse({"detail": "REQUEST_TOO_LARGE"}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        pending = True

        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BoundedEvaluationBody)
_engine = None
_hits: dict[str, deque[float]] = defaultdict(deque)


def engine():
    global _engine
    with LOCK:
        if _engine is None:
            _engine = NativeEngine()
        return _engine


@app.get("/health")
def health():
    try:
        native = engine()
        return {"status": "degraded", "engine": "ENGINE_OK", "model": "MODEL_ENRICHMENT_DISABLED",
                "version": "1.0.0", "jurisdictions": ["US"], "policy_version": native.policy.POLICY_VERSION,
                "engine_fingerprint": native.fingerprint}
    except Exception:
        raise HTTPException(503, "UNAVAILABLE") from None


@app.post("/api/v1/evaluate")
def evaluate(body: ServiceRequest, authorization: str = Header(default="")):
    expected = os.getenv("PEOPLEPAY_CIVICMESH_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "Service authentication is not configured")
    if not hmac.compare_digest(authorization.encode(), ("Bearer " + expected).encode()):
        raise HTTPException(401, "AUTH_FAILURE")
    if body.jurisdiction != "US":
        raise HTTPException(422, "UNSUPPORTED_JURISDICTION")
    with LOCK:
        now = time.monotonic()
        for key, times in list(_hits.items()):
            if not times or now - times[-1] >= 60:
                _hits.pop(key, None)
        if body.workflow_id not in _hits and len(_hits) >= 1000:
            raise HTTPException(429, "RATE_LIMIT")
        hits = _hits[body.workflow_id]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= 20:
            raise HTTPException(429, "RATE_LIMIT")
        hits.append(now)
    return engine().evaluate(body)
