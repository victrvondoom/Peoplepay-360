"""Translate actual CivicMesh outputs into SDK proposals, never approvals."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Literal

import httpx
from peoplepay_sdk import ActionProposal, Capability, Entity, Evidence, ExtensionHealth, ExtensionMetadata, ExtensionRequest, ExtensionResult

from extensions.civicmesh.contracts import AssistanceInput


def identifier(prefix, *parts):
    return prefix + "-" + sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:24]


class CivicMeshProvider:
    def __init__(self, client):
        self.client = client

    def capabilities(self):
        return [Capability(name="assistance_eligibility", description="U.S. policy eligibility, next question and action routes; advisory only.")]

    def metadata(self):
        return ExtensionMetadata(id="civicmesh", name="CivicMesh assistance", version="1.0.0",
                                 description="Original deterministic Jac policy engine over minimized structured facts.", capabilities=self.capabilities())

    async def health(self):
        status: Literal["healthy", "degraded", "unavailable"]
        try:
            value = await self.client.request("GET", "/health")
            status = "degraded" if value.get("engine") == "ENGINE_OK" else "unavailable"
        except Exception:
            status = "unavailable"
        return ExtensionHealth(extension_id="civicmesh", status=status, checked_at=datetime.now(timezone.utc),
                               message="Deterministic engine only; model enrichment disabled; U.S. coverage.")

    async def execute(self, request: ExtensionRequest):
        if request.capability != "assistance_eligibility":
            raise ValueError("unsupported CivicMesh capability")
        inputs = AssistanceInput.model_validate(request.input)
        if inputs.jurisdiction != "US":
            return ExtensionResult(request_id=request.request_id, extension_id="civicmesh", extension_version="1.0.0",
                                   status="partial", warnings=["UNSUPPORTED_JURISDICTION"])
        workflow = request.context.transaction_id or request.context.trace_id
        try:
            raw = await self.client.request("POST", "/api/v1/evaluate", json={**inputs.model_dump(), "request_id": request.request_id, "workflow_id": workflow})
            return normalize(request, raw)
        except (httpx.TimeoutException, TimeoutError):
            code = "TIMEOUT"
        except httpx.HTTPStatusError as exc:
            code = {401: "AUTH_FAILURE", 429: "RATE_LIMIT", 503: "EXTENSION_UNAVAILABLE"}.get(exc.response.status_code, "INVALID_RESPONSE")
        except (ValueError, KeyError, TypeError):
            code = "INVALID_RESPONSE"
        except httpx.HTTPError:
            code = "EXTENSION_UNAVAILABLE"
        return ExtensionResult(request_id=request.request_id, extension_id="civicmesh", extension_version="1.0.0",
                               status="partial", warnings=["ASSISTANCE_PROVIDER_UNAVAILABLE", code])


def normalize(request, raw):
    if (not isinstance(raw, dict) or raw.get("request_id") != request.request_id
            or raw.get("workflow_id") != (request.context.transaction_id or request.context.trace_id)
            or raw.get("provider") != "civicmesh" or raw.get("provider_version") != "1.0.0"
            or raw.get("jurisdiction") != "US" or raw.get("calibrated_probability") is not False):
        raise ValueError("invalid CivicMesh receipt binding")
    observed = datetime.fromisoformat(raw["observed_at"])
    if observed.tzinfo is None or observed > datetime.now(timezone.utc):
        raise ValueError("invalid observation time")
    for field in ("policy_date", "policy_last_verified"):
        date.fromisoformat(raw[field])
    if (not isinstance(raw.get("question"), dict) or not isinstance(raw.get("plan"), dict)
            or not isinstance(raw["plan"].get("steps"), list) or len(raw["plan"]["steps"]) > 6
            or not isinstance(raw.get("routes"), list) or len(raw["routes"]) > 3
            or type(raw.get("crisis")) is not bool
            or not isinstance(raw["question"].get("key"), str)
            or not isinstance(raw["question"].get("text"), str)):
        raise ValueError("invalid CivicMesh plan or question")
    entities, evidence, actions = [], [], []
    programs = raw["programs"]
    if not isinstance(programs, list) or not 1 <= len(programs) <= 6:
        raise ValueError("bounded program results required")
    for item in programs:
        if (not isinstance(item, dict) or not isinstance(item.get("rule"), dict)
                or not isinstance(item["rule"].get("rule_id"), str)
                or not isinstance(item.get("criteria"), list)):
            raise ValueError("invalid program assessment")
        program_id = identifier("program", item["rule"]["rule_id"])
        evidence_id = identifier("policy", request.request_id, program_id)
        # The engine checked bundled policy data, not the current publisher page.
        # URL attribution never masquerades as live verification.
        evidence.append(Evidence(id=evidence_id, source_uri=item["online_url"] or None,
            source_name="CivicMesh bundled policy catalog", observed_at=observed, provenance_state="unknown",
            excerpt=json.dumps({"rule": item["rule"], "policy_version": raw["policy_version"],
                                "policy_date": raw["policy_date"]}, sort_keys=True)[:1200],
            uncertainty="Bundled policy reference; live source and local availability need review."))
        claim = {"id": identifier("eligibility", request.request_id, program_id), "predicate": "eligibility_assessment",
                 "kind": "inference", "value": {"tier": item["tier"], "criteria": item["criteria"],
                    "policy_date": raw["policy_date"], "policy_version": raw["policy_version"],
                    "policy_last_verified": raw["policy_last_verified"], "rule_id": item["rule"]["rule_id"],
                    "rule": item["rule"], "policy_definition": item.get("policy_definition", {}), "benefit": item.get("benefit", {})},
                 "text": item["resource_name"] + ": " + item["tier"], "evidence_ids": [evidence_id]}
        estimate = {"id": identifier("score", request.request_id, program_id), "kind": "eligibility_score",
                    "value": item["p_eligible"], "calibrated_probability": False,
                    "coverage": item["coverage"], "rank_score": item["rank_score"], "evidence_ids": [evidence_id]}
        if type(estimate["value"]) not in {float, int} or not 0 <= estimate["value"] <= 1:
            raise ValueError("invalid heuristic score")
        entities.append(Entity(id=program_id, entity_type="program", name=item["resource_name"],
            identifiers={"civicmesh_rule_id": item["rule"]["rule_id"]},
            attributes={"claims": [claim], "estimates": [estimate], "evidence_ids": [evidence_id]}))
    for i, step in enumerate(raw["plan"]["steps"]):
        actions.append(ActionProposal(id=identifier("action", request.request_id, i), action_type="seek_assistance",
            summary=step["agency_name"] + ": " + step["action_description"], parameters=step, requires_human_approval=True))
    # Retain selected policy output, never raw profile, conversation or credentials.
    receipt = {key: raw[key] for key in ("engine_fingerprint", "policy_version", "policy_date", "policy_sources",
               "policy_last_verified", "question", "plan", "routes", "crisis", "duration_ms")}
    receipt.update(received_at=datetime.now(timezone.utc).isoformat(), mode="live",
                   input_fact_hash=sha256(json.dumps(request.input, sort_keys=True).encode()).hexdigest(),
                   run_id=identifier("civic-run", request.request_id), calibrated_probability=False)
    receipt["policy_context"] = raw.get("policy_context", {})
    return ExtensionResult(request_id=request.request_id, extension_id="civicmesh", extension_version="1.0.0", status="partial",
                           entities=entities, evidence=evidence, action_proposals=actions, raw_result=receipt, warnings=raw["warnings"])
