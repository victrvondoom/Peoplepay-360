"""Concrete Gateway coordinator: provider receipts -> ECHO -> approved order -> PROXY."""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from beacon.assurance import EventKind, State
from beacon.peoplepay.authority import Permission
from beacon.peoplepay.transaction import Transaction
from gateway.merchant import ReferenceMerchant, default_reference_catalog
from journey.models import ProcurementRequirement, digest
from journey.store import JourneyStore
from peoplepay_sdk import ExtensionContext, ExtensionRequest, ExtensionResult


class JourneyUnavailable(RuntimeError):
    pass


class EchoClient:
    def __init__(self, origin: str) -> None:
        self.origin = origin.rstrip("/")
        parts = urlsplit(self.origin)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path):
            raise ValueError("ECHO origin must be an operator-configured HTTP(S) origin")
        if parts.scheme == "http" and parts.hostname != "localhost":
            try:
                loopback = ipaddress.ip_address(parts.hostname).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise ValueError("ECHO caller tokens require HTTPS outside loopback")
        self.parts = parts
        self.hostname = parts.hostname

    def request(self, method: str, path: str, actor: str, authorization: str | None,
                body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "X-Beacon-User": actor}
        if authorization:
            headers["Authorization"] = authorization
        conn_type = http.client.HTTPSConnection if self.parts.scheme == "https" else http.client.HTTPConnection
        conn = conn_type(self.hostname, self.parts.port, timeout=30)
        try:
            raw = json.dumps(body, allow_nan=False).encode() if body is not None else None
            if raw is not None and len(raw) > 65536:
                raise ValueError("normalized journey input exceeds the ECHO body limit")
            conn.request(method, path, body=raw, headers=headers)
            response = conn.getresponse()
            raw_response = response.read(524289)
            if len(raw_response) > 524288:
                raise JourneyUnavailable("ECHO response exceeded the journey limit")
            value = json.loads(raw_response)
            if response.status == 404:
                raise KeyError("ECHO decision not found")
            if response.status == 409:
                raise ValueError(value.get("detail", "ECHO rejected the decision/approval"))
            if response.status not in {200, 201} or not isinstance(value, dict):
                raise JourneyUnavailable("ECHO rejected the journey request")
            return value
        except (OSError, json.JSONDecodeError, http.client.HTTPException) as exc:
            raise JourneyUnavailable("ECHO is unavailable; no order was authorized") from exc
        finally:
            conn.close()


class JourneyService:
    def __init__(self, gateway, *, store: JourneyStore | None = None,
                 merchant: ReferenceMerchant | None = None, echo=None,
                 provider_factory=None, proxy_factory=None) -> None:
        self.gateway = gateway
        path = os.getenv("PEOPLEPAY_JOURNEY_DB", "peoplepay-journey.sqlite3")
        self.store = store or JourneyStore(path)
        self.merchant = merchant or ReferenceMerchant(path, default_reference_catalog())
        self.echo = echo or EchoClient(os.getenv("PEOPLEPAY_ECHO_URL", "http://127.0.0.1:8090"))
        self.provider_factory = provider_factory
        self.proxy_factory = proxy_factory
        self.lock = threading.RLock()

    def _providers(self, mode: str, actor: str):
        if self.provider_factory:
            return self.provider_factory(mode, actor)
        from journey.providers import GreenChainProvider, InflationForgeProvider, HttpSourceClient, reference_provider_clients
        if mode == "reference":
            clients = reference_provider_clients()
            return [GreenChainProvider(clients[0], mode="reference"), InflationForgeProvider(clients[1], mode="reference")]
        green = os.getenv("PEOPLEPAY_GREENCHAIN_API_URL")
        inflation = os.getenv("PEOPLEPAY_INFLATIONFORGE_API_URL")
        if not green or not inflation:
            raise JourneyUnavailable("Native provider API origins are not configured; select the reference journey explicitly")
        return [GreenChainProvider(HttpSourceClient(green), mode="live"),
                InflationForgeProvider(HttpSourceClient(inflation), mode="live")]

    async def _collect(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        async def call(provider):
            metadata = provider.metadata()
            req = record["requirement"]
            request = ExtensionRequest(
                request_id=f"{record['id']}-v{len(record['decisions'])+1}-{metadata.id}",
                capability=provider.capabilities()[0].name,
                context=ExtensionContext(user_id=record["actor_id"], transaction_id=record["transaction_id"], trace_id=record["id"]),
                input={"product": req["product"], "quantity": req["quantity"], "destination": req["destination"]},
                constraints={"budget_minor": req["budget_minor"], "currency": req["currency"], "delivery_days": req["delivery_days"]},
            )
            try:
                result = await asyncio.wait_for(provider.execute(request), timeout=30)
                result = ExtensionResult.model_validate(result.model_dump(mode="json"))
                if result.extension_id != metadata.id or result.request_id != request.request_id:
                    raise ValueError("provider receipt is not bound to its invocation")
                return result.model_dump(mode="json")
            except Exception:
                return ExtensionResult(request_id=request.request_id, extension_id=metadata.id,
                    extension_version=metadata.version, status="partial", warnings=["PROVIDER_UNAVAILABLE_OR_INVALID_RESULT"]).model_dump(mode="json")
        return await asyncio.gather(*(call(provider) for provider in self._providers(record["mode"], record["actor_id"])))

    def _evaluate(self, record: dict[str, Any], authorization: str | None) -> dict[str, Any]:
        txn = self.gateway.store.get(record["transaction_id"])
        txn.assert_owned_by(record["actor_id"])
        if txn.state is State.CANCELLED or not txn.permissions.allows(Permission.DISCOVERY) or not txn.permissions.allows(Permission.PLANNING):
            raise ValueError("discovery and planning permissions are required to evaluate evidence")
        try:
            recovered = self.echo.request("GET", f"/echo/v1/journeys/{record['id']}/current", record["actor_id"], authorization)
        except KeyError:
            recovered = None
        if recovered and recovered["decision_version"] == len(record["decisions"]) + 1:
            if recovered["transaction_id"] != record["transaction_id"] or recovered["requirement"] != record["requirement"]:
                raise ValueError("recoverable ECHO decision does not match this journey")
            decision = recovered
        else:
            decision = None
        receipts = asyncio.run(self._collect(record)) if decision is None else []
        req = record["requirement"]
        quotes = [self.merchant.quote(item["supplier_id"], item["product_id"], req["quantity"],
                                      req["budget_minor"], req["delivery_days"]) for item in self.merchant.get_catalog()]
        decision = decision or self.echo.request("POST", "/echo/v1/journeys/evaluate", record["actor_id"], authorization, {
            "journey_id": record["id"], "transaction_id": record["transaction_id"], "version": len(record["decisions"]) + 1,
            "mode": record["mode"], "requirement": req, "providers": receipts, "merchant_quotes": quotes})
        record["decisions"].append({"id": decision["decision_id"], "version": decision["decision_version"], "hash": decision["decision_hash"]})
        record["decision"] = decision
        record["phase"] = "AWAITING_APPROVAL" if decision["recommended_supplier_id"] else "RESEARCH_REQUIRED"
        record["last_error"] = None
        self.store.put(record)
        self._ledger(record, EventKind.POLICY_EVALUATED, {"decision_id": decision["decision_id"], "decision_hash": decision["decision_hash"],
                     "outcome": decision["policy_outcome"]})
        return record

    def create(self, actor: str, body: dict[str, Any], authorization: str | None) -> dict[str, Any]:
        if set(body) - {"requirement", "mode"}:
            raise ValueError("unexpected journey input fields")
        mode = body.get("mode", "reference")
        if mode not in {"reference", "live"}:
            raise ValueError("journey mode must be reference or live")
        requirement = ProcurementRequirement.model_validate(body.get("requirement"))
        with self.lock:
            txn = Transaction.create(user_id=actor, raw_utterance=requirement.description, actor=f"gateway:{actor}")
            self.gateway.store.put(txn)
            self.gateway.bus.publish_ledger_tail(txn.ledger, source="gateway")
            record = {"id": f"journey-{uuid4().hex}", "actor_id": actor, "transaction_id": txn.transaction_id,
                "mode": mode, "requirement": requirement.model_dump(), "created_at": datetime.now(timezone.utc).isoformat(),
                "phase": "COLLECTING_EVIDENCE", "decisions": [], "decision": None, "approval": None,
                "checkout": None, "order": None, "delivery_event": None, "dispute": None}
            self.store.put(record)
            try:
                return self._evaluate(record, authorization)
            except (JourneyUnavailable, ValueError):
                record["phase"] = "EVIDENCE_BLOCKED"
                record["last_error"] = "Evidence/ECHO evaluation failed; retry from the preserved requirement."
                self.store.put(record)
                raise

    def _ledger(self, record: dict[str, Any], kind: EventKind, payload: dict[str, Any]) -> None:
        txn = self.gateway.store.get(record["transaction_id"])
        txn.assert_owned_by(record["actor_id"])
        before = len(txn.ledger)
        txn.context["journey"] = {"id": record["id"], "phase": record["phase"],
                                   "decision_id": record["decision"]["decision_id"] if record["decision"] else None,
                                   "external_order_ref": record["order"].get("external_order_ref") if record["order"] else None}
        txn.ledger.append(kind, actor=f"gateway:{record['actor_id']}", detail={"journey_id": record["id"], **payload})
        self.gateway.store.put(txn)
        self.gateway.bus.publish_ledger_tail(txn.ledger, source="unified-journey", since_seq=before)

    def approve(self, journey_id: str, actor: str, body: dict[str, Any], authorization: str | None) -> dict[str, Any]:
        with self.lock:
            record = self.store.get(journey_id, actor)
            txn = self.gateway.store.get(record["transaction_id"])
            txn.assert_owned_by(actor)
            if txn.state is State.CANCELLED or not txn.permissions.allows(Permission.PLANNING):
                raise ValueError("the transaction is cancelled or its planning authorization was revoked")
            if body.get("human_confirmation") is not True or body.get("confirm_reference") is not True:
                raise ValueError("explicit human confirmation of the simulated order is required")
            if record["order"]:
                prior = record["approval"]
                if (body.get("decision_hash") != prior["decision_hash"] or body.get("supplier_id") != prior["terms"]["supplier_id"]
                        or body.get("decision_version") != prior["decision_version"]):
                    raise ValueError("an order already exists under different approved terms")
                return record
            if record["mode"] != "reference" or not record["decision"]:
                raise ValueError("only an evaluated reference journey can create a simulated order")
            decision = record["decision"]
            action = self.echo.request("POST", f"/echo/v1/journeys/decisions/{decision['decision_id']}/approve", actor, authorization, body)
            if (action["actor_id"] != actor or action["transaction_id"] != record["transaction_id"]
                    or action["decision_id"] != decision["decision_id"] or action["decision_hash"] != decision["decision_hash"]
                    or action["decision_version"] != decision["decision_version"] or digest(action["terms"]) != action["terms_hash"]):
                raise ValueError("ECHO approval does not bind this transaction and exact decision")
            record["approval"] = action
            record["approved_decision"] = decision
            record["phase"] = "APPROVED"
            self.store.put(record)
            self._ledger(record, EventKind.AUTHORIZATION_GRANTED, {"action_id": action["action_id"], "terms_hash": action["terms_hash"], "reference_only": True})
            checkout = self.merchant.create_session(action, f"{action['action_id']}-create", f"req-{uuid4().hex}")
            record["checkout"] = checkout
            self.store.put(record)
            completed = self.merchant.complete_session(checkout["id"], action, f"{action['action_id']}-complete", f"req-{uuid4().hex}")
            record["checkout"] = completed
            if completed["status"] != "completed":
                record["phase"] = "REAPPROVAL_REQUIRED"
                self.store.put(record)
                return record
            record["order"] = completed["order"]
            record["phase"] = "ORDER_CREATED"
            self.store.put(record)
            self._ledger(record, EventKind.CHECKOUT_OBSERVED, {"checkout_session_id": completed["id"],
                "external_order_ref": completed["external_order_ref"], "money_moved": False})
            return record

    def _proxy_draft(self, bundle: dict[str, Any], actor: str) -> dict[str, Any]:
        from journey.proxy import NativeProxyAdapter, create_draft
        if self.proxy_factory:
            return self.proxy_factory(bundle, actor)
        origin = os.getenv("PEOPLEPAY_PROXY_API_URL")
        session_file = os.getenv("PEOPLEPAY_PROXY_SESSION_FILE")
        if not origin and not session_file:
            return create_draft(bundle)
        if not origin or not session_file:
            raise JourneyUnavailable("Native PROXY needs both its API origin and an actor session mapping")
        path = Path(session_file)
        if path.stat().st_size > 65536:
            raise ValueError("PROXY session mapping exceeds its size limit")
        sessions = json.loads(path.read_text(encoding="utf-8"))
        mapped = sessions.get(actor) if isinstance(sessions, dict) else None
        if not isinstance(mapped, dict) or not mapped.get("bearer_token") or not mapped.get("proxy_user_id"):
            raise JourneyUnavailable("No native PROXY session is mapped for this PeoplePay actor")
        return NativeProxyAdapter(origin).create_draft(bundle, bearer_token=mapped["bearer_token"], proxy_user_id=mapped["proxy_user_id"])

    def delivery(self, journey_id: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
        from journey.proxy import build_bundle
        with self.lock:
            record = self.store.get(journey_id, actor)
            if not record["order"] or record["mode"] != "reference":
                raise ValueError("delivery simulation requires a reference merchant order")
            if set(body) - {"delivered_quantity", "event_id"}:
                raise ValueError("unexpected delivery fields")
            quantity = body.get("delivered_quantity")
            if type(quantity) is not int:
                raise ValueError("delivered_quantity must be an integer")
            key = body.get("event_id")
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ValueError("an event_id is required for delivery idempotency")
            order_ref = record["checkout"]["external_order_ref"]
            delivered = self.merchant.record_delivery(order_ref, quantity, key, f"req-{uuid4().hex}", final=True)
            record["delivery_event"] = delivered["event"]
            record["order"] = delivered["order"]
            self.store.put(record)
            if not delivered["discrepancy"]:
                record["phase"] = "DELIVERED"
                self.store.put(record)
                return record
            if record["dispute"]:
                return record
            if record.get("proxy_requires_reconciliation") or record.get("proxy_handoff_started"):
                raise JourneyUnavailable("The previous native PROXY handoff may have created a case; reconcile it before another handoff")
            approved = record["approved_decision"]
            selected = next(item for item in approved["candidates"] if item["supplier_id"] == record["approval"]["terms"]["supplier_id"])
            bundle = build_bundle(requirement=record["requirement"], decision=approved,
                selected_supplier={"name": selected["supplier_name"], **selected}, approved_terms=record["approval"]["terms"],
                transaction_reference=record["transaction_id"], merchant_order_reference=order_ref,
                delivery_event=record["delivery_event"], actor_id=actor, correlation_id=record["id"])
            record["dispute_bundle"] = bundle
            record["phase"] = "DISPUTE_DRAFT_PENDING"
            record["proxy_handoff_started"] = True
            self.store.put(record)
            try:
                record["dispute"] = self._proxy_draft(bundle, actor)
            except Exception as exc:
                record["last_error"] = "PROXY draft handoff failed. Evidence bundle is retained; reconcile native case before retry."
                record["proxy_requires_reconciliation"] = True
                case_id = getattr(exc, "case_id", None)
                if case_id:
                    record["native_proxy_case_id"] = case_id
                self.store.put(record)
                raise JourneyUnavailable("PROXY draft handoff failed; order and evidence are retained") from None
            record["phase"] = "DISPUTE_DRAFT_READY"
            self.store.put(record)
            self._ledger(record, EventKind.DISPUTE_OPENED, {"bundle_hash": bundle["bundle_hash"], "submitted": False,
                                                         "merchant_event_id": record["delivery_event"].get("event_id")})
            return record

    def refresh(self, journey_id: str, actor: str, authorization: str | None) -> dict[str, Any]:
        with self.lock:
            record = self.store.get(journey_id, actor)
            original = record.get("approved_decision") or record["decision"]
            phase = record["phase"]
            self._evaluate(record, authorization)
            current = record["decision"]
            changes = []
            old = {item["supplier_id"]: item for item in original["candidates"]} if original else {}
            for candidate in current["candidates"]:
                previous = old.get(candidate["supplier_id"])
                if previous:
                    for field in ("terms", "raw_provider_score", "echo_score", "policy_violations"):
                        if previous[field] != candidate[field]:
                            changes.append({"supplier_id": candidate["supplier_id"], "field": field,
                                            "at_decision": previous[field], "current": candidate[field]})
                else:
                    changes.append({"supplier_id": candidate["supplier_id"], "field": "new_candidate"})
            current_ids = {item["supplier_id"] for item in current["candidates"]}
            for supplier_id in old.keys() - current_ids:
                changes.append({"supplier_id": supplier_id, "field": "removed_candidate"})
            previous_providers = {item["extension_id"]: item for item in original["provider_receipts"]} if original else {}
            for provider in current["provider_receipts"]:
                previous = previous_providers.get(provider["extension_id"], {})
                # Retrieval/request ids change on refresh. Distinguish those from
                # changed observed facts, evidence excerpts or provider warnings.
                for field in ("entities", "evidence", "warnings"):
                    def comparable(value):
                        if isinstance(value, dict):
                            return {key: comparable(child) for key, child in value.items()
                                    if key not in {"id", "evidence_ids", "received_at", "retrieved_at"}}
                        if isinstance(value, list):
                            return [comparable(child) for child in value]
                        return value
                    if comparable(previous.get(field, [])) != comparable(provider.get(field, [])):
                        changes.append({"extension_id": provider["extension_id"], "field": field,
                                        "at_decision": previous.get(field, []), "current": provider.get(field, [])})
            record["changes"] = {"historical_decision_id": original["decision_id"] if original else None,
                "current_decision_id": current["decision_id"], "historical_evaluated_at": original["evaluated_at"] if original else None,
                "current_evaluated_at": current["evaluated_at"], "changes": changes,
                "warnings_at_decision": original["warnings"] if original else [], "warnings_now": current["warnings"],
                "historical_snapshot_preserved": True}
            if record["order"]:
                record["phase"] = phase
            else:
                record["approval"] = None
                record.pop("approved_decision", None)
            self.store.put(record)
            return record

    def explain(self, journey_id: str, actor: str, authorization: str | None) -> dict[str, Any]:
        record = self.store.get(journey_id, actor)
        historical = record.get("approved_decision") or record["decision"]
        if not historical:
            raise ValueError("the journey has no evaluated decision")
        snapshot = self.echo.request("GET", f"/echo/v1/journeys/decisions/{historical['decision_id']}", actor, authorization)
        chosen = record["approval"]["terms"]["supplier_id"] if record["approval"] else snapshot["recommended_supplier_id"]
        candidate = next((item for item in snapshot["candidates"] if item["supplier_id"] == chosen), None)
        return {"decision_id": snapshot["decision_id"], "decision_version": snapshot["decision_version"],
            "evaluated_at": snapshot["evaluated_at"], "decision_hash": snapshot["decision_hash"],
            "supplier_id": chosen, "candidate": candidate, "warnings": snapshot["warnings"],
            "explanation": "The preserved decision applied budget and delivery limits, then ranked eligible candidates using the recorded sustainability estimate and merchant quote. " +
                           ("Human approval selected these exact terms." if record["approval"] else "This recommendation has not been approved."),
            "approved_terms": record["approval"]["terms"] if record["approval"] else None,
            "provider_receipts": snapshot["provider_receipts"], "normalized_results": snapshot["normalized_results"]}
