"""PeoplePay-owned assistance workflow; ECHO owns its decision snapshots."""
import asyncio
import os
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from peoplepay_sdk import ExtensionContext, ExtensionRequest, PeoplePayEvent

from extensions.civicmesh.adapter import CivicMeshProvider
from extensions.civicmesh.contracts import Facts
from journey.capability_router import route_need
from journey.extension_runtime import CapabilityRuntime
from journey.providers import HttpSourceClient
from journey.service import EchoClient, JourneyUnavailable
from journey.store import JourneyStore


class CreateAssistance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=1000)
    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
    facts: Facts = Field(default_factory=Facts)
    consent: bool = False
    payment_option: dict | None = None


class AssistanceService:
    def __init__(self, *, store=None, echo=None, runtime=None):
        self.store = store or JourneyStore(os.getenv("PEOPLEPAY_ASSISTANCE_DB", "peoplepay-assistance.sqlite3"))
        self.echo = echo or EchoClient(os.getenv("PEOPLEPAY_ECHO_URL", "http://127.0.0.1:8090"))
        self.runtime = runtime or CapabilityRuntime()
        self.lock = threading.RLock()
        if runtime is None and os.getenv("PEOPLEPAY_CIVICMESH_API_URL"):
            provider = CivicMeshProvider(HttpSourceClient(os.environ["PEOPLEPAY_CIVICMESH_API_URL"],
                token=os.getenv("PEOPLEPAY_CIVICMESH_TOKEN"), timeout_seconds=15))
            self.runtime.register(provider, jurisdictions={"US"}, input_fields={"jurisdiction", "language", "need", "facts", "consent"})

    @staticmethod
    def _event(record, name, payload):
        event = PeoplePayEvent(event_id="event-" + uuid4().hex, event_type=name, occurred_at=datetime.now(timezone.utc),
            producer="peoplepay", subject_id=record["id"], correlation_id=record["id"], actor_id=record["actor_id"], payload=payload)
        record["events"] = [*record.get("events", [])[-99:], event.model_dump(mode="json")]

    def providers(self):
        return [{"id": identifier, "metadata": self.runtime.registry.get(identifier).metadata().model_dump(mode="json"),
                 "jurisdictions": sorted(coverage["jurisdictions"]),
                 "health": self.runtime.health.get(identifier, {"status": "not_checked"})}
                for identifier, coverage in sorted(self.runtime.coverage.items())]

    def create(self, actor, body, authorization=None):
        inputs = CreateAssistance.model_validate(body)
        route = route_need(inputs.message, inputs.jurisdiction)
        if route["intent"] != "assistance":
            return {"status": "ROUTED_TO_PROCUREMENT" if route["intent"] == "procurement" else "UNSUPPORTED", "route": route, "url": "/journey", "money_moved": False}
        if not inputs.consent:
            raise ValueError("Consent is required before structured assistance facts are sent to a policy provider")
        if inputs.payment_option is not None and (set(inputs.payment_option) != {"amount_minor", "currency"}
            or type(inputs.payment_option["amount_minor"]) is not int or inputs.payment_option["amount_minor"] < 0 or inputs.payment_option["currency"] != "USD"):
            raise ValueError("payment comparison requires a nonnegative integer USD amount")
        with self.lock:
            record = {"id": "assistance-" + uuid4().hex, "actor_id": actor, "created_at": datetime.now(timezone.utc).isoformat(),
                "input": {"jurisdiction": inputs.jurisdiction, "language": inputs.language, "need": route["need"],
                          "facts": inputs.facts.model_dump(), "consent": True}, "route": route,
                "payment_option": inputs.payment_option, "decisions": [], "decision": None, "pending_receipt": None,
                "phase": "COLLECTING_EVIDENCE", "money_moved": False}
            self.store.put(record)
            self._event(record, "assistance.evaluation_requested", {"need": route["need"], "jurisdiction": inputs.jurisdiction})
            return self._evaluate(record, authorization)

    def _evaluate(self, record, authorization):
        version = len(record["decisions"]) + 1
        request = ExtensionRequest(request_id=f"{record['id']}-v{version}", capability="assistance_eligibility",
            context=ExtensionContext(transaction_id=record["id"], trace_id=record["id"]), input=record["input"])
        if record.get("pending_receipt") is None:
            result, trace = asyncio.run(self.runtime.invoke(request, record["input"]["jurisdiction"]))
            record["trace"] = trace
            self._event(record, "assistance.evaluation_completed", trace)
            record["route"].update(providers=trace.get("providers", []), civicmesh_invoked="civicmesh" in trace.get("providers", []))
            if result is None:
                record["phase"] = trace["status"]
                self.store.put(record)
                return record
            record["pending_receipt"] = result.model_dump(mode="json")
            self.store.put(record)
        echo_started = time.perf_counter()
        try:
            decision = self.echo.request("POST", "/echo/v1/assistance/evaluate", record["actor_id"], authorization,
                {"workflow_id": record["id"], "version": version, "provider": record["pending_receipt"], "payment_option": record["payment_option"]})
        except (JourneyUnavailable, ValueError):
            record["phase"] = "ECHO_UNAVAILABLE_OR_REJECTED"
            self.store.put(record)
            return record
        record["decisions"].append({"id": decision["decision_id"], "version": decision["version"], "hash": decision["decision_hash"]})
        record["decision"] = decision
        record["metrics"] = {"provider_runtime_ms": record.get("trace", {}).get("duration_ms"),
            "native_engine_ms": record["pending_receipt"]["raw_result"].get("duration_ms"),
            "echo_request_ms": round((time.perf_counter() - echo_started) * 1000, 3)}
        record["phase"] = decision["status"]
        record["pending_receipt"] = None
        self._event(record, "decision.updated", {"decision_id": decision["decision_id"], "version": version})
        if decision.get("question", {}).get("key"):
            self._event(record, "information.requested", {"key": decision["question"]["key"]})
        self.store.put(record)
        return record

    def update(self, identifier, actor, body, authorization=None):
        with self.lock:
            record = self.store.get(identifier, actor)
            if set(body) != {"facts"}:
                raise ValueError("follow-up accepts only structured facts")
            if record.get("pending_receipt") is not None:
                raise ValueError("retry the pending ECHO decision before changing facts")
            updates = Facts.model_validate(body["facts"]).model_dump(exclude_unset=True)
            # Facts not mentioned in this answer retain the same workflow context.
            record["input"]["facts"] = Facts.model_validate({**record["input"]["facts"], **updates}).model_dump()
            self.store.put(record)
            return self._evaluate(record, authorization)

    def retry(self, identifier, actor, authorization=None):
        with self.lock:
            return self._evaluate(self.store.get(identifier, actor), authorization)

    def explain(self, identifier, actor, authorization=None):
        record = self.store.get(identifier, actor)
        snapshots = [self.echo.request("GET", "/echo/v1/assistance/decisions/" + item["id"], actor, authorization) for item in record["decisions"]]
        changes = []
        if len(snapshots) > 1:
            for name in ("policy_date", "policy_version", "options", "question"):
                if snapshots[0].get(name) != snapshots[-1].get(name):
                    changes.append({"field": name, "original": snapshots[0].get(name), "current": snapshots[-1].get(name)})
        return {"workflow_id": identifier, "historical_decisions": snapshots, "changes": changes,
                "note": "Changes compare preserved evaluation versions; current policy is not refreshed until a new evaluation."}
