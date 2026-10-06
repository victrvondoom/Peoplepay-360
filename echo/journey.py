"""ECHO's concrete Journey v1 normalization, reconciliation, policy and approval.

This policy is deliberately separate from the existing correlation benchmark:
reference evidence can authorize only a simulated merchant order. Live evidence
with unresolved identity or provenance makes this journey abstain.
"""

from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from redis.exceptions import RedisError

from echo.auth import caller
from echo.graph_store import EchoGraphStore
from echo.models import stable_id
from echo.extensions.contracts import ExtensionExecution, ExtensionRequest, ExtensionContext
from echo.extensions.ingestion import ExtensionIngestor, domain_identity
from journey.models import ProcurementRequirement, digest
from peoplepay_sdk import ExtensionResult

LOCK = threading.RLock()


def _score(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100 and math.isfinite(value):
        return float(value)
    return None


class MerchantQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    supplier_id: str = Field(min_length=1, max_length=128)
    product_id: str = Field(min_length=1, max_length=128)
    quantity: int = Field(gt=0, le=10000)
    currency: Literal["INR"]
    unit_price_minor: int = Field(gt=0, le=10**12)
    shipping_minor: int = Field(ge=0, le=10**12)
    tax_minor: int = Field(ge=0, le=10**12)
    total_minor: int = Field(gt=0, le=10**14)
    delivery_days: int = Field(gt=0, le=3650)
    budget_minor: int = Field(gt=0, le=10**12)
    max_delivery_days: int = Field(gt=0, le=365)

    @model_validator(mode="after")
    def correct_total(self):
        if self.total_minor != self.unit_price_minor * self.quantity + self.shipping_minor + self.tax_minor:
            raise ValueError("merchant quote total does not match its line amounts")
        return self


class EvaluateJourney(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    journey_id: str = Field(pattern=r"^journey-[a-f0-9]{32}$")
    transaction_id: str = Field(min_length=1, max_length=128)
    version: int = Field(gt=0)
    mode: Literal["reference", "live"]
    requirement: ProcurementRequirement
    providers: list[ExtensionResult] = Field(min_length=2, max_length=2)
    merchant_quotes: list[MerchantQuote] = Field(max_length=20)

    @model_validator(mode="after")
    def unique_quotes(self):
        ids = [item.supplier_id for item in self.merchant_quotes]
        if len(ids) != len(set(ids)):
            raise ValueError("journey quotes must have unique supplier identities")
        return self


class ApproveJourney(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_version: int = Field(gt=0)
    supplier_id: str = Field(min_length=1, max_length=128)
    human_confirmation: StrictBool
    confirm_reference: StrictBool


def reconcile_entities(results: list[ExtensionResult]) -> list[dict[str, Any]]:
    """Exact domain/GTIN identifiers reconcile aliases; names alone never merge."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        for entity in result.entities:
            domain = entity.identifiers.get("domain")
            if entity.entity_type in {"supplier", "organization"} and domain:
                key = (entity.entity_type, domain_identity(domain))
            elif entity.entity_type == "product" and entity.identifiers.get("gtin"):
                key = ("product", entity.identifiers["gtin"])
            else:
                key = (result.extension_id, entity.id)
            group = groups.setdefault(key, {
                "canonical_id": stable_id(*key), "identity_method": "EXACT_IDENTIFIER" if key[0] in {"supplier", "organization", "product"} else "UNRESOLVED",
                "identity_verified": False, "aliases": [], "representations": [],
            })
            if entity.name not in group["aliases"]:
                group["aliases"].append(entity.name)
            group["representations"].append({"extension_id": result.extension_id, "entity_id": entity.id})
    return list(groups.values())


class JourneyEcho:
    def __init__(self, store: EchoGraphStore, clock=None) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def get(self, decision_id: str, actor: str) -> dict[str, Any]:
        self.store.ping()  # A fresh graph must exist before FalkorDB read-only queries.
        rows = self.store.read_only_rows(
            "MATCH (d:Decision {id: $id, user_id: $user}) RETURN d.journey_snapshot_json",
            {"id": decision_id, "user": actor},
        )
        if not rows or not rows[0][0]:
            raise KeyError("decision not found")
        try:
            snapshot = json.loads(rows[0][0])
            if not isinstance(snapshot, dict):
                raise ValueError("snapshot is not an object")
            expected = snapshot.pop("decision_hash")
            if (not isinstance(expected, str) or len(expected) != 64 or digest(snapshot) != expected
                    or snapshot.get("decision_id") != decision_id or snapshot.get("actor_id") != actor):
                raise ValueError("snapshot binding or digest is invalid")
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
            raise ValueError("historical decision snapshot failed its integrity check") from exc
        snapshot["decision_hash"] = expected
        return snapshot

    def evaluate(self, body: EvaluateJourney, actor: str) -> dict[str, Any]:
        from journey.sdk_bridge import to_echo_result, reviewed_manifest

        self.store.ping()

        if {result.extension_id for result in body.providers} != {"greenchain", "inflationforge"}:
            raise ValueError("the journey requires exactly GreenChain and InflationForge receipts")
        # Validate every receipt before creating requirements or ingesting any
        # provider. Malformed second-provider output must not partially mutate
        # the graph on its way to a rejected decision.
        normalizations = [to_echo_result(item) for item in body.providers]
        manifests = [reviewed_manifest(item.extension_id) for item in body.providers]
        for sdk_result, manifest in zip(body.providers, manifests):
            if sdk_result.extension_version != manifest.version:
                raise ValueError("journey receipt does not match the reviewed provider version")
            mode = sdk_result.raw_result.get("mode")
            if mode is not None and mode != body.mode:
                raise ValueError("provider receipt mode does not match the journey")
            context = sdk_result.raw_result.get("request_context")
            if context is not None:
                if not isinstance(context, dict) or context.get("product") != body.requirement.product:
                    raise ValueError("provider receipt product context does not match the requirement")
                if sdk_result.extension_id == "greenchain" and (
                        context.get("quantity") != body.requirement.quantity or context.get("destination") != body.requirement.destination):
                    raise ValueError("GreenChain receipt shipment context does not match the requirement")
        reconciliation = reconcile_entities(body.providers)
        receipt_hash = digest(body.model_dump(mode="json"))
        decision_id = stable_id("journey-decision", actor, body.journey_id, str(body.version))
        with LOCK:
            prior = self.store.read_only_rows("MATCH (d:Decision {id: $id}) RETURN d.journey_input_hash", {"id": decision_id})
            if prior:
                if prior[0][0] != receipt_hash:
                    raise ValueError("decision version was already used with different receipts")
                return self.get(decision_id, actor)
            owners = self.store.read_only_rows("MATCH (r:Requirement {id: $id}) RETURN r.user_id, r.journey_version",
                                              {"id": body.journey_id})
            if owners and (owners[0][0] != actor or body.version != (owners[0][1] or 0) + 1):
                raise ValueError("journey owner/version does not match its current requirement")
            if not owners and body.version != 1:
                raise ValueError("first journey decision must be version 1")
            now = self.clock().isoformat()
            requirement_props = {
                "id": body.journey_id, "user_id": actor, **body.requirement.model_dump(),
                "demo_scope": body.journey_id if body.mode == "reference" else "",
                "transaction_id": body.transaction_id, "journey_mode": body.mode,
                "journey_requirement_hash": digest(body.requirement.model_dump()),
            }
            requirement_rows = self.store.graph.query(
                "MERGE (r:Requirement {id: $id}) ON CREATE SET r += $props "
                "WITH r WHERE r.user_id = $user AND r.journey_mode = $mode "
                "AND r.transaction_id = $transaction AND r.journey_requirement_hash = $hash RETURN r.id",
                params={"id": body.journey_id, "props": requirement_props, "user": actor, "mode": body.mode,
                        "transaction": body.transaction_id, "hash": requirement_props["journey_requirement_hash"]}, timeout=5000,
            ).result_set
            if not requirement_rows:
                raise ValueError("journey requirement, mode or transaction binding cannot change")
            ingest = []
            normalized = []
            for sdk_result, result, manifest in zip(body.providers, normalizations, manifests):
                request = ExtensionRequest(request_id=sdk_result.request_id,
                    capability=manifest.capabilities[0], context=ExtensionContext(requirement_id=body.journey_id, user_id=actor),
                    input={"sdk_receipt_hash": digest(sdk_result.model_dump(mode="json"))})
                execution = ExtensionExecution(run_id=stable_id("journey-run", decision_id, sdk_result.extension_id),
                    request_id=request.request_id, capability=request.capability,
                    extension_id=result.extension_id, extension_version=result.extension_version,
                    status=result.status, result=result, started_at=self.clock(), finished_at=self.clock(), duration_ms=0)
                ingest.append(ExtensionIngestor(self.store).ingest(manifest, request, execution))
                normalized.append(result.model_dump(mode="json"))
            greenchain = next(item for item in body.providers if item.extension_id == "greenchain")
            warnings = list(dict.fromkeys([warning for result in normalizations for warning in result.warnings]))
            candidates = []
            for typed_quote in body.merchant_quotes:
                quote = typed_quote.model_dump()
                domain = f"{quote.get('supplier_id')}.example" if body.mode == "reference" else quote.get("supplier_domain")
                matches = [entity for entity in greenchain.entities if entity.entity_type == "supplier" and domain
                           and entity.identifiers.get("domain") and domain_identity(entity.identifiers["domain"]) == domain]
                supplier = matches[0] if len(matches) == 1 else None
                violations = []
                if not supplier:
                    violations.append("SUPPLIER_IDENTITY_AMBIGUOUS" if len(matches) > 1 else "SUPPLIER_IDENTITY_UNRESOLVED")
                if quote.get("currency") != body.requirement.currency:
                    violations.append("CURRENCY_MISMATCH")
                if type(quote.get("total_minor")) is not int or quote["total_minor"] > body.requirement.budget_minor:
                    violations.append("BUDGET_EXCEEDED_OR_UNKNOWN")
                if type(quote.get("delivery_days")) is not int or quote["delivery_days"] > body.requirement.delivery_days:
                    violations.append("DELIVERY_LIMIT_EXCEEDED_OR_UNKNOWN")
                if quote.get("quantity") != body.requirement.quantity:
                    violations.append("QUANTITY_MISMATCH")
                if quote["budget_minor"] != body.requirement.budget_minor or quote["max_delivery_days"] != body.requirement.delivery_days:
                    violations.append("QUOTE_CONSTRAINT_MISMATCH")
                if body.mode == "live":
                    # Native GreenChain discovery + city-basket observations cannot
                    # certify a chair order; procurement verification remains required.
                    violations.append("LIVE_MERCHANT_AND_SUPPLIER_VERIFICATION_REQUIRED")
                attrs = supplier.attributes if supplier else {}
                provider_score = attrs.get("provider_score")
                raw_score = _score(provider_score)
                raw = round(raw_score, 4) if raw_score is not None else None
                estimates = attrs.get("estimates", [])
                carbon = next((item.get("value") for item in estimates
                               if "emission" in item.get("kind", "").lower() or "carbon" in item.get("kind", "").lower()), None)
                sustainability = attrs.get("sustainability_score")
                sustainability_basis = "EXPLICIT_PROVIDER_SUSTAINABILITY_SCORE"
                if sustainability is None:
                    sustainability = next((claim.get("value") for claim in attrs.get("claims", [])
                                           if claim.get("predicate") == "sustainability_score"), None)
                if sustainability is None:
                    sustainability, sustainability_basis = raw, "GREENCHAIN_ENVIRONMENTAL_COMPOSITE_PROXY"
                sustainability = _score(sustainability)
                score_claims = [claim for claim in attrs.get("claims", [])
                                if claim.get("predicate") in {"environmental_score", "sustainability_score"}
                                and claim.get("evidence_ids")]
                if body.requirement.prioritize_sustainability:
                    if sustainability is None:
                        violations.append("SUSTAINABILITY_SCORE_UNAVAILABLE")
                    elif not any(claim.get("value") == sustainability for claim in score_claims):
                        violations.append("SUSTAINABILITY_SCORE_EVIDENCE_MISSING_OR_CONFLICTING")
                # Policy weights are fixed by ECHO; upstream composite score is audit context.
                price_score = max(0, 100 * (1 - quote.get("total_minor", body.requirement.budget_minor) / body.requirement.budget_minor))
                score = round((0.8 * (sustainability or 0) + 0.2 * price_score) if body.requirement.prioritize_sustainability else price_score, 4)
                candidates.append({"supplier_id": quote.get("supplier_id"), "supplier_name": supplier.name if supplier else quote.get("supplier_id"),
                    "canonical_entity_id": stable_id("supplier", domain) if domain else None,
                    "raw_provider_score": raw, "echo_score": score, "sustainability_score": sustainability,
                    "sustainability_score_basis": sustainability_basis,
                    "carbon_estimate": carbon, "terms": quote, "terms_hash": digest(quote),
                    "evidence_ids": attrs.get("evidence_ids", []),
                    "evidence_references": [{"extension_id": "greenchain", "evidence_id": identifier,
                        "request_id": greenchain.request_id,
                        "source_id": next(item for item in ingest if item["extension_id"] == "greenchain")["source_ids"].get("src-" + identifier)}
                        for identifier in attrs.get("evidence_ids", [])],
                    "price_context_evidence_ids": [item.id for provider in body.providers if provider.extension_id == "inflationforge" for item in provider.evidence],
                    "price_context_warnings": next(item.warnings for item in body.providers if item.extension_id == "inflationforge"),
                    "policy_violations": violations,
                    "eligible": not violations})
            candidates.sort(key=lambda item: (-item["echo_score"], str(item["supplier_id"])))
            eligible = [item for item in candidates if item["eligible"]]
            if body.mode == "reference":
                warnings += ["REFERENCE_SUPPLIERS_NOT_VERIFIED", "SUSTAINABILITY_ESTIMATES_NOT_CERTIFIED", "MERCHANT_SIMULATOR_NO_MONEY_MOVED"]
            decision = {"decision_id": decision_id, "decision_version": body.version, "journey_id": body.journey_id,
                "transaction_id": body.transaction_id, "actor_id": actor, "mode": body.mode,
                "evaluated_at": now, "requirement": body.requirement.model_dump(),
                "status": "REFERENCE_RECOMMEND" if eligible and body.mode == "reference" else "ABSTAIN",
                "policy_outcome": "REFERENCE_ONLY" if eligible and body.mode == "reference" else "RESEARCH_REQUIRED",
                "model_version": "echo-journey-policy-v1", "policy": {
                    "sustainability_weight": 0.8 if body.requirement.prioritize_sustainability else 0,
                    "price_weight": 0.2 if body.requirement.prioritize_sustainability else 1,
                    "amount_unit": "integer minor units", "live_authorization": False},
                "recommended_supplier_id": eligible[0]["supplier_id"] if eligible else None,
                "candidates": candidates, "alternatives": [item["supplier_id"] for item in eligible[1:]],
                "warnings": list(dict.fromkeys(warnings)), "reconciliation": reconciliation,
                "normalized_results": normalized, "provider_receipts": [item.model_dump(mode="json") for item in body.providers],
                "ingestion": ingest, "input_hash": receipt_hash}
            decision["decision_hash"] = digest(decision)
            decision_props = {"id": decision_id, "user_id": actor, "requirement_id": body.journey_id,
                "journey_input_hash": receipt_hash, "journey_snapshot_json": json.dumps(decision, sort_keys=True),
                "created_at": now, "model_version": decision["model_version"], "status": decision["status"],
                "demo_scope": body.journey_id if body.mode == "reference" else ""}
            # One graph statement seals the immutable snapshot and advances its
            # current pointer. Concurrent workers cannot overwrite the receipt.
            sealed = self.store.graph.query(
                "MATCH (r:Requirement {id: $requirement, user_id: $user}) "
                "WHERE coalesce(r.journey_version, 0) = $previous "
                "MERGE (d:Decision {id: $id}) ON CREATE SET d += $props "
                "WITH r, d WHERE d.journey_input_hash = $hash "
                "SET r.journey_version = $version, r.current_journey_decision_id = $id "
                "MERGE (r)-[:HAS_EVENT {id: $edge}]->(d) RETURN d.id",
                params={"requirement": body.journey_id, "user": actor, "previous": body.version - 1,
                        "id": decision_id, "props": decision_props, "hash": receipt_hash, "version": body.version,
                        "edge": stable_id("edge", body.journey_id, decision_id)}, timeout=5000,
            ).result_set
            if not sealed:
                raise ValueError("journey decision was concurrently updated; reload its current version")
            return self.get(decision_id, actor)

    def approve(self, decision_id: str, actor: str, body: ApproveJourney) -> dict[str, Any]:
        with LOCK:
            decision = self.get(decision_id, actor)
            if decision["decision_hash"] != body.decision_hash or decision["decision_version"] != body.decision_version:
                raise ValueError("approval does not match the exact decision version/hash")
            rows = self.store.read_only_rows("MATCH (r:Requirement {id: $id, user_id: $user}) RETURN r.current_journey_decision_id",
                                            {"id": decision["journey_id"], "user": actor})
            if not rows or rows[0][0] != decision_id:
                raise ValueError("decision was superseded; review the current decision")
            if not body.human_confirmation or not body.confirm_reference or decision["policy_outcome"] != "REFERENCE_ONLY":
                raise ValueError("explicit human approval of reference-only terms is required")
            candidate = next((item for item in decision["candidates"] if item["supplier_id"] == body.supplier_id), None)
            if not candidate or not candidate["eligible"]:
                raise ValueError("supplier does not meet the decision policy")
            action_id = stable_id("journey-approval", actor, decision_id)
            action = {"action_id": action_id, "actor_id": actor, "decision_id": decision_id,
                "decision_version": decision["decision_version"], "decision_hash": decision["decision_hash"],
                "transaction_id": decision["transaction_id"], "terms": candidate["terms"], "terms_hash": candidate["terms_hash"],
                "mode": "reference", "authority": "ECHO_HUMAN_APPROVAL", "money_moved": False}
            rows = self.store.graph.query(
                "MATCH (r:Requirement {id: $req, user_id: $user}), (d:Decision {id: $decision, user_id: $user}) "
                "WHERE r.current_journey_decision_id = $decision "
                "MERGE (a:Approval {id: $id}) ON CREATE SET a.user_id = $user, a.action_json = $action, a.terms_hash = $terms "
                "WITH d, a WHERE a.terms_hash = $terms MERGE (d)-[:HAS_APPROVAL {id: $edge}]->(a) RETURN a.action_json",
                params={"req": decision["journey_id"], "user": actor, "decision": decision_id, "id": action_id,
                        "action": json.dumps(action, sort_keys=True), "terms": action["terms_hash"],
                        "edge": stable_id("edge", decision_id, action_id)}, timeout=5000,
            ).result_set
            if not rows:
                raise ValueError("the decision has a different existing approval or was superseded")
            try:
                persisted_action = json.loads(rows[0][0])
            except (ValueError, TypeError) as exc:
                raise ValueError("stored approval failed its integrity check") from exc
            if persisted_action != action:
                raise ValueError("stored approval failed its exact decision binding check")
            return persisted_action


def build_journey_router(store: EchoGraphStore) -> APIRouter:
    router = APIRouter()
    engine = JourneyEcho(store)

    @router.post("/echo/v1/journeys/evaluate")
    def evaluate(body: EvaluateJourney, identity: str = Depends(caller)):
        try:
            return engine.evaluate(body, identity)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        except (RedisError, OSError) as exc:
            raise HTTPException(503, detail="ECHO graph service is unavailable") from exc

    @router.get("/echo/v1/journeys/decisions/{decision_id}")
    def get(decision_id: str, identity: str = Depends(caller)):
        try:
            return engine.get(decision_id, identity)
        except KeyError as exc:
            raise HTTPException(404, detail="decision not found") from exc
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        except (RedisError, OSError) as exc:
            raise HTTPException(503, detail="ECHO graph service is unavailable") from exc

    @router.get("/echo/v1/journeys/{journey_id}/current")
    def current(journey_id: str, identity: str = Depends(caller)):
        try:
            store.ping()
            rows = store.read_only_rows("MATCH (r:Requirement {id: $id, user_id: $user}) RETURN r.current_journey_decision_id",
                                        {"id": journey_id, "user": identity})
            if not rows or not rows[0][0]:
                raise KeyError("current journey decision not found")
            return engine.get(rows[0][0], identity)
        except KeyError as exc:
            raise HTTPException(404, detail="current journey decision not found") from exc
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        except (RedisError, OSError) as exc:
            raise HTTPException(503, detail="ECHO graph service is unavailable") from exc

    @router.post("/echo/v1/journeys/decisions/{decision_id}/approve")
    def approve(decision_id: str, body: ApproveJourney, identity: str = Depends(caller)):
        try:
            return engine.approve(decision_id, identity, body)
        except KeyError as exc:
            raise HTTPException(404, detail="decision not found") from exc
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        except (RedisError, OSError) as exc:
            raise HTTPException(503, detail="ECHO graph service is unavailable") from exc

    return router
