"""Canonical immutable assistance decisions built from SDK policy proposals.

Eligibility stays in CivicMesh. ECHO preserves evidence and separates heuristic
provider ordering from verified eligibility and user authorization.
"""
import json
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from peoplepay_sdk import ExtensionResult

from echo.auth import caller
from echo.extensions.contracts import ExtensionContext, ExtensionExecution, ExtensionRequest
from echo.extensions.ingestion import ExtensionIngestor
from echo.models import stable_id
from journey.models import digest
from journey.sdk_bridge import reviewed_manifest, to_echo_result

LOCK = threading.RLock()


class EvaluateAssistance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    version: int = Field(ge=1)
    provider: ExtensionResult
    payment_option: dict[str, Any] | None = None


class AssistanceDecisions:
    def __init__(self, store):
        self.store = store

    def get(self, identifier, actor):
        rows = self.store.read_only_rows("MATCH (d:Decision {id: $id, user_id: $actor}) RETURN d.assistance_snapshot_json", {"id": identifier, "actor": actor})
        if not rows or not rows[0][0]:
            raise KeyError("decision not found")
        try:
            snapshot = json.loads(rows[0][0])
            preserved_hash = snapshot.get("decision_hash")
            expected_id = stable_id("assistance-decision", actor, snapshot["workflow_id"], str(snapshot["version"]))
            if (snapshot["decision_id"] != identifier or expected_id != identifier
                    or preserved_hash != digest({k: v for k, v in snapshot.items() if k != "decision_hash"})):
                raise ValueError("invalid preserved assistance decision")
            return snapshot
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError("invalid preserved assistance decision") from None

    def evaluate(self, body, actor):
        provider = body.provider
        if body.payment_option is not None and (set(body.payment_option) != {"amount_minor", "currency"}
                or type(body.payment_option["amount_minor"]) is not int or body.payment_option["amount_minor"] < 0
                or body.payment_option["currency"] != "USD"):
            raise ValueError("payment comparison requires a nonnegative integer USD amount")
        if provider.extension_id != "civicmesh" or provider.extension_version != "1.0.0":
            raise ValueError("unreviewed assistance receipt")
        if provider.request_id != f"{body.workflow_id}-v{body.version}":
            raise ValueError("assistance receipt workflow or version conflict")
        if not provider.entities or provider.raw_result.get("calibrated_probability") is not False:
            raise ValueError("usable policy evidence is required")
        if (provider.confidence is not None or any(e.provenance_state != "unknown" for e in provider.evidence)
                or not isinstance(provider.raw_result.get("question"), dict)
                or not isinstance(provider.raw_result.get("plan"), dict)):
            raise ValueError("assistance evidence must remain advisory and unverified")
        for entity in provider.entities:
            claims = entity.attributes.get("claims")
            estimates = entity.attributes.get("estimates")
            if (entity.entity_type != "program" or not isinstance(claims, list) or len(claims) != 1
                    or not isinstance(estimates, list) or len(estimates) != 1
                    or not isinstance(claims[0], dict) or not isinstance(estimates[0], dict)
                    or claims[0].get("predicate") != "eligibility_assessment"
                    or claims[0].get("kind") != "inference"
                    or not isinstance(claims[0].get("value"), dict)
                    or estimates[0].get("calibrated_probability") is not False):
                raise ValueError("invalid assistance option assessment")
            assessment = claims[0]["value"]
            if (not isinstance(assessment.get("tier"), str)
                    or not isinstance(assessment.get("criteria"), list)
                    or any(not isinstance(c, dict) or any(not isinstance(c.get(key), str) for key in ("label", "status", "detail"))
                           for c in assessment["criteria"])):
                raise ValueError("invalid assistance option criteria")
        normalized = to_echo_result(provider)
        identifier = stable_id("assistance-decision", actor, body.workflow_id, str(body.version))
        input_hash = digest(body.model_dump(mode="json"))
        with LOCK:
            rows = self.store.read_only_rows("MATCH (d:Decision {id: $id}) RETURN d.user_id, d.assistance_input_hash", {"id": identifier})
            if rows:
                if rows[0] != [actor, input_hash]:
                    raise ValueError("decision version input conflict")
                snapshot = self.get(identifier, actor)
                # Recover a decision committed just before the version marker.
                marker = self.store.read_only_rows("MATCH (r:Requirement {id: $id, user_id: $actor}) RETURN r.assistance_version", {"id": body.workflow_id, "actor": actor})
                if marker and (marker[0][0] or 0) < body.version:
                    self.store.upsert_node("Requirement", {"id": body.workflow_id, "assistance_version": body.version})
                return snapshot
            prior = self.store.read_only_rows("MATCH (r:Requirement {id: $id}) RETURN r.user_id, r.assistance_version", {"id": body.workflow_id})
            if prior and (prior[0][0] != actor or body.version != (prior[0][1] or 0) + 1):
                raise ValueError("workflow owner or version conflict")
            if not prior and body.version != 1:
                raise ValueError("first assistance version must be 1")
            self.store.upsert_node("Requirement", {"id": body.workflow_id, "user_id": actor, "description": "Structured assistance evaluation", "demo_scope": ""})
            now = datetime.now(timezone.utc)
            request = ExtensionRequest(request_id=provider.request_id, capability="assistance_eligibility",
                context=ExtensionContext(requirement_id=body.workflow_id, user_id=actor), input={"sdk_receipt_hash": digest(provider.model_dump(mode="json"))})
            manifest = reviewed_manifest("civicmesh")
            execution = ExtensionExecution(run_id=stable_id("assistance-run", identifier), request_id=request.request_id,
                capability=request.capability, extension_id="civicmesh", extension_version="1.0.0", status=normalized.status,
                result=normalized, started_at=now, finished_at=now, duration_ms=provider.raw_result.get("duration_ms", 0))
            ingestion = ExtensionIngestor(self.store).ingest(manifest, request, execution)
            options = [{"id": entity.id, "type": "seek_assistance", "name": entity.name,
                        "assessment": entity.attributes["claims"][0]["value"], "estimate": entity.attributes["estimates"][0],
                        "evidence_ids": entity.attributes["evidence_ids"], "requires_review": True} for entity in provider.entities]
            if body.payment_option:
                options.append({"id": "manual-payment-option", "type": "pay", "name": "User supplied bill amount",
                                "terms": body.payment_option, "evidence_state": "MANUAL_INPUT_UNVERIFIED", "requires_review": True})
            state = "REVIEW_REQUIRED" if provider.raw_result.get("crisis") else "NEEDS_INFORMATION" if provider.raw_result.get("question", {}).get("key") else "REVIEW_REQUIRED"
            snapshot = {"decision_id": identifier, "workflow_id": body.workflow_id, "version": body.version,
                "created_at": now.isoformat(), "status": state, "policy_outcome": "ADVISORY_ONLY",
                "options": options, "question": provider.raw_result.get("question"), "plan": provider.raw_result.get("plan"),
                "paths": provider.raw_result.get("routes"), "policy_date": provider.raw_result.get("policy_date"),
                "policy_version": provider.raw_result.get("policy_version"), "warnings": provider.warnings,
                "ingestion": ingestion, "normalized": normalized.model_dump(mode="json"),
                "provider_receipt": provider.model_dump(mode="json"), "money_moved": False,
                "explanation": "CivicMesh ordered these advisory options using bundled policy and heuristic scores. ECHO preserved the evidence; local eligibility and availability require review."}
            snapshot["decision_hash"] = digest(snapshot)
            self.store.upsert_node("Decision", {"id": identifier, "user_id": actor, "requirement_id": body.workflow_id,
                "decision_version": body.version, "assistance_input_hash": input_hash,
                "assistance_snapshot_json": json.dumps(snapshot, sort_keys=True), "created_at": now.isoformat()})
            self.store.link("Requirement", body.workflow_id, "HAS_EVENT", "Decision", identifier)
            self.store.link("Decision", identifier, "HAS_EVENT", "ExtensionRun", execution.run_id)
            for row in self.store.read_only_rows("MATCH (run:ExtensionRun {id: $id})-[:PRODUCED]->(c:Claim) RETURN c.id", {"id": execution.run_id}):
                self.store.link("Decision", identifier, "USED_CLAIM", "Claim", row[0])
            self.store.upsert_node("Requirement", {"id": body.workflow_id, "assistance_version": body.version})
            return snapshot


def build_assistance_router(store):
    router = APIRouter(prefix="/echo/v1/assistance", tags=["assistance"])
    decisions = AssistanceDecisions(store)

    @router.post("/evaluate")
    def evaluate(body: EvaluateAssistance, actor: str = Depends(caller)):
        try:
            return decisions.evaluate(body, actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @router.get("/decisions/{identifier}")
    def get(identifier: str, actor: str = Depends(caller)):
        try:
            return decisions.get(identifier, actor)
        except KeyError:
            raise HTTPException(404, "decision not found") from None
        except ValueError:
            raise HTTPException(409, "invalid preserved assistance decision") from None

    return router
