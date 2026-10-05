"""Executable requirement -> providers -> canonical graph -> decision proof."""

from uuid import uuid4

from echo.engine import EchoEngine
from echo.extensions.contracts import ExtensionRequest
from echo.extensions.ingestion import ExtensionIngestor
from echo.extensions.runtime import ExtensionRuntime
from echo.graph_store import EchoGraphStore
from echo.models import stable_id

SCOPE = "echo-cross-extension-demo-v1"


async def run_extension_demo(store: EchoGraphStore, runtime: ExtensionRuntime) -> dict:
    requirement_id = f"req-extension-demo-{uuid4().hex[:16]}"
    user_id = "echo-demo-user"
    store.upsert_node("User", {"id": user_id})
    store.upsert_node("Requirement", {
        "id": requirement_id, "user_id": user_id, "description": "Synthetic cross-extension sourcing comparison",
        "quantity": 300, "currency": "USD", "budget_minor": 3500000, "demo_scope": SCOPE,
    })
    store.link("User", user_id, "CREATED", "Requirement", requirement_id)
    suffix = requirement_id.replace("req-", "")
    for name, raw_score in (("alpha", 94.0), ("beta", 87.0), ("gamma", 78.0)):
        supplier_id = stable_id("supplier", f"{name}-{suffix}.example")
        policy_id = stable_id("candidate-policy", requirement_id, supplier_id)
        store.upsert_node("CandidatePolicy", {"id": policy_id, "requirement_id": requirement_id,
                                              "supplier_id": supplier_id, "raw_score": raw_score,
                                              "active": True, "demo_scope": SCOPE})
        store.link("Requirement", requirement_id, "HAS_POLICY", "CandidatePolicy", policy_id)
    request = ExtensionRequest(request_id=f"demo-event-{uuid4().hex}", capability="demo_evidence",
                               context={"requirement_id": requirement_id, "user_id": user_id})
    ingestor = ExtensionIngestor(store)
    runs = await runtime.execute_all(request)
    ingestions = []
    for execution in runs:
        record = runtime.registry.get(execution.extension_id)
        ingestions.append(ingestor.ingest(record.manifest, request, execution))
    decision = EchoEngine(store).analyze_requirement(requirement_id)
    return {**decision, "extension_runs": [run.model_dump(mode="json", exclude={"result"}) for run in runs],
            "ingestions": ingestions, "synthetic": True,
            "graph_reason": "Two synthetic extensions share Alpha's upstream release; repeated evidence is deduplicated in the canonical graph."}
