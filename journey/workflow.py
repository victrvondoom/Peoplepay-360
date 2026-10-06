"""Small durable capability workflow engine, independent of specialist algorithms.

ECHO and Gateway callbacks are injected by the host. A capability result cannot
authorize an action. Durable snapshots use the existing owner-scoped store.
"""
import asyncio
import hashlib
import json
import threading
from datetime import datetime, timezone
from uuid import uuid4

from peoplepay_sdk import ExtensionContext, ExtensionRequest, PeoplePayEvent
from peoplepay_sdk.contracts import _bounded_json
from journey.store import JourneyStore

STATES = {"CREATED", "DISCOVERING", "WAITING_FOR_INFORMATION", "EVALUATING", "REVIEW_REQUIRED",
          "WAITING_FOR_APPROVAL", "AUTHORIZED", "EXECUTING", "COMPLETED", "PARTIAL", "FAILED", "CANCELED"}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class WorkflowEngine:
    def __init__(self, runtime, *, store=None, evaluate=None, execute=None):
        self.runtime = runtime
        self.store = store or JourneyStore()
        self.evaluate = evaluate
        self.execute = execute
        self.lock = threading.RLock()

    def _event(self, record, name, payload, event_id=None):
        event = PeoplePayEvent(event_id=event_id or "event-" + uuid4().hex,
            event_type=name, occurred_at=datetime.now(timezone.utc), producer="peoplepay",
            subject_id=record["id"], correlation_id=record["id"], actor_id=record["actor_id"], payload=payload)
        existing = next((e for e in record["events"] if e["event_id"] == event.event_id), None)
        if existing:
            if existing["event_type"] != name or existing["payload"] != payload:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return
        record["events"].append(event.model_dump(mode="json"))

    def create(self, actor, *, intent, jurisdiction, steps, context=None):
        if not isinstance(intent, str) or not 1 <= len(intent) <= 1000:
            raise ValueError("bounded intent required")
        if not steps or len(steps) > 20:
            raise ValueError("one to twenty capability steps required")
        validated = []
        for step in steps:
            if set(step) - {"capability", "input", "constraints", "requirement"}:
                raise ValueError("unknown step fields")
            requirement = step.get("requirement", "REQUIRED")
            if requirement not in {"REQUIRED", "OPTIONAL", "ENRICHMENT"}:
                raise ValueError("invalid failure policy")
            req = ExtensionRequest(request_id="validation", capability=step["capability"],
                context=ExtensionContext(trace_id="validation", jurisdiction=jurisdiction), input=step.get("input", {}), constraints=step.get("constraints", {}))
            validated.append({"capability": req.capability, "input": req.input, "constraints": req.constraints, "requirement": requirement})
        if context:
            raise ValueError("workflow context must be scoped to individual steps")
        record = {"id": "workflow-" + uuid4().hex, "actor_id": actor, "intent": intent,
            "jurisdiction": jurisdiction, "state": "CREATED", "steps": validated,
            "results": [], "decisions": [], "approval": None, "action": None, "events": [], "processed": {}}
        self._event(record, "workflow.created", {"capabilities": [s["capability"] for s in validated]})
        self.store.put(record)
        return record

    def run(self, identifier, actor, *, event_id):
        with self.lock:
            record = self.store.get(identifier, actor)
            if event_id in record["processed"]:
                if record["processed"][event_id] != "run":
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return record
            if record["state"] in {"CANCELED", "EXECUTING", "COMPLETED", "AUTHORIZED"}:
                raise ValueError("workflow cannot evaluate in this state")
            record["state"] = "DISCOVERING"
            record["evaluation_generation"] = record.get("evaluation_generation", 0) + 1
            self._event(record, "capability.requested", {}, event_id)
            self.store.put(record)

            async def collect():
                async def invoke(index, step):
                    request = ExtensionRequest(request_id=f"{identifier}-g{record['evaluation_generation']}-s{index}", capability=step["capability"],
                        context=ExtensionContext(trace_id=identifier, workflow_id=identifier, jurisdiction=record["jurisdiction"], user_id=actor),
                        input=step["input"], constraints=step["constraints"])
                    try:
                        result, trace = await self.runtime.invoke(request, record["jurisdiction"])
                        return {"capability": step["capability"], "requirement": step["requirement"],
                            "receipt": result.model_dump(mode="json") if result else None, "trace": trace}
                    except ValueError:
                        return {"capability": step["capability"], "requirement": step["requirement"],
                            "receipt": None, "trace": {"status": "PERMISSION_DENIED"}}
                return await asyncio.gather(*(invoke(i, s) for i, s in enumerate(record["steps"])))

            record["results"] = asyncio.run(collect())
            for result in record["results"]:
                self._event(record, "extension.invocation_completed", {"capability": result["capability"], "trace": result["trace"]})
            record["approval"] = None
            if any(r["receipt"] is None and r["requirement"] == "REQUIRED" for r in record["results"]):
                record["state"] = "PARTIAL"
            elif self.evaluate is None:
                record["state"] = "REVIEW_REQUIRED"
            else:
                record["state"] = "EVALUATING"
                self.store.put(record)
                try:
                    # Only an ECHO-owned host callback supplies the canonical decision.
                    decision = self.evaluate(record)
                    required = {"decision_id", "version", "action_scope", "status", "evidence_references"}
                    if not isinstance(decision, dict) or not required <= decision.keys() or decision["version"] != len(record["decisions"])+1:
                        raise ValueError("invalid ECHO decision")
                    if type(decision["version"]) is not int or not isinstance(decision["decision_id"], str) or not decision["decision_id"]:
                        raise ValueError("invalid ECHO decision identity")
                    if decision["status"] not in {"WAITING_FOR_INFORMATION", "ABSTAIN", "REVIEW_REQUIRED", "REQUIRES_APPROVAL"}:
                        raise ValueError("unsupported ECHO decision status")
                    _bounded_json(decision, maximum_bytes=65536)
                    if not isinstance(decision["action_scope"], dict) or not isinstance(decision["evidence_references"], list):
                        raise ValueError("invalid ECHO action scope or evidence references")
                    if decision["status"] == "REQUIRES_APPROVAL" and (not decision["action_scope"] or not decision["evidence_references"]):
                        raise ValueError("approval requires an evidence-backed action scope")
                    record["decisions"].append(decision)
                    record["state"] = "WAITING_FOR_INFORMATION" if decision["status"] == "WAITING_FOR_INFORMATION" else "REVIEW_REQUIRED" if decision["status"] in {"ABSTAIN", "REVIEW_REQUIRED"} else "WAITING_FOR_APPROVAL"
                    self._event(record, "decision.created", {"decision_id": decision["decision_id"], "version": decision["version"]})
                except Exception:
                    record["state"] = "REVIEW_REQUIRED"
                    self._event(record, "decision.failed", {"reason": "ECHO unavailable or invalid decision"})
            record["processed"][event_id] = "run"
            self.store.put(record)
            return record

    def input(self, identifier, actor, *, step_index, values, event_id):
        with self.lock:
            record = self.store.get(identifier, actor)
            binding = fingerprint({"step": step_index, "values": values})
            if event_id in record["processed"]:
                if record["processed"][event_id] != binding:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return record
            if record["state"] not in {"WAITING_FOR_INFORMATION", "REVIEW_REQUIRED", "PARTIAL", "WAITING_FOR_APPROVAL"}:
                raise ValueError("workflow does not accept new input")
            if type(step_index) is not int or not 0 <= step_index < len(record["steps"]):
                raise ValueError("invalid step index")
            step = record["steps"][step_index]
            updated = ExtensionRequest(request_id="validation", capability=step["capability"], context=ExtensionContext(trace_id=identifier), input={**step["input"], **values})
            step["input"] = updated.input
            record["approval"] = None
            record["state"] = "CREATED"
            record["processed"][event_id] = binding
            self._event(record, "information.received", {"step_index": step_index}, event_id)
            self.store.put(record)
            return record

    def approve(self, identifier, actor, *, decision_id, version, scope_hash, event_id):
        with self.lock:
            if type(version) is not int:
                raise ValueError("decision version must be an integer")
            record = self.store.get(identifier, actor)
            binding = fingerprint({"decision_id": decision_id, "version": version, "scope_hash": scope_hash})
            if event_id in record["processed"]:
                if record["processed"][event_id] != binding:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return record
            if record["state"] != "WAITING_FOR_APPROVAL" or not record["decisions"]:
                raise ValueError("human review required before approval")
            decision = record["decisions"][-1]
            if decision["decision_id"] != decision_id or decision["version"] != version or fingerprint(decision["action_scope"]) != scope_hash:
                raise ValueError("stale or different decision/action scope")
            record["approval"] = {"id": "approval-" + uuid4().hex, "actor": actor, "decision_id": decision_id,
                "version": version, "scope_hash": scope_hash, "created_at": datetime.now(timezone.utc).isoformat()}
            record["state"] = "AUTHORIZED"
            record["processed"][event_id] = binding
            self._event(record, "approval.granted", record["approval"], event_id)
            self.store.put(record)
            return record

    def cancel(self, identifier, actor, *, event_id):
        with self.lock:
            record = self.store.get(identifier, actor)
            if record["state"] in {"EXECUTING", "COMPLETED"}:
                raise ValueError("external action cannot be canceled locally")
            self._event(record, "workflow.canceled", {}, event_id)
            record["state"] = "CANCELED"
            record["approval"] = None
            self.store.put(record)
            return record

    def execute_authorized(self, identifier, actor, *, event_id):
        with self.lock:
            record = self.store.get(identifier, actor)
            if record["state"] == "COMPLETED" and record.get("execution_event_id") == event_id:
                return record
            if record["state"] not in {"AUTHORIZED", "EXECUTING"} or not record["approval"]:
                raise ValueError("consequential action requires authorization")
            if self.execute is None:
                raise ValueError("Gateway executor is not configured")
            if record.get("execution_event_id") not in {None, event_id}:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            # Validate the execution key and reserve a fresh event namespace
            # before calling an external authority, not after its side effect.
            PeoplePayEvent(event_id=event_id, event_type="external_action.started",
                occurred_at=datetime.now(timezone.utc), producer="peoplepay",
                subject_id=identifier, correlation_id=identifier, actor_id=actor)
            if event_id in record["processed"] or any(e["event_id"] == event_id for e in record["events"]):
                raise ValueError("IDEMPOTENCY_CONFLICT")
            record["execution_event_id"] = event_id
            record["state"] = "EXECUTING"
            self.store.put(record)
            # Gateway must independently validate authorization and deduplicate
            # this durable key, including recovery after an uncertain response.
            action = self.execute(record, event_id)
            if not isinstance(action, dict) or not action.get("external_authority_reference"):
                raise ValueError("Gateway result requires external authority reference")
            record["action"] = action
            record["state"] = "COMPLETED"
            self._event(record, "external_action.completed", {"external_authority_reference": action["external_authority_reference"]}, event_id)
            self.store.put(record)
            return record
