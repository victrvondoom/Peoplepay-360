"""Real graph proof of canonical cross-provider ingestion and trust boundaries."""

import asyncio
from uuid import uuid4

import pytest

from echo.engine import EchoEngine
from echo.extensions.bootstrap import build_registry
from echo.extensions.contracts import ExtensionContext, ExtensionRequest, NormalizedResult
from echo.extensions.demo import run_extension_demo
from echo.extensions.ingestion import ExtensionIngestor, IngestionRejected
from echo.extensions.runtime import ExtensionRuntime
from echo.graph_store import EchoGraphStore


@pytest.fixture
def graph():
    store = EchoGraphStore(graph_name=f"echo_ingestion_test_{uuid4().hex}")
    store.ping()
    yield store
    store.graph.delete()


def seeded(graph):
    registry = build_registry()
    runtime = ExtensionRuntime(registry)
    result = asyncio.run(run_extension_demo(graph, runtime))
    return registry, runtime, result


def fresh_request(result, identifier="event-replay"):
    return ExtensionRequest(request_id=identifier, capability="demo_evidence",
                            context=ExtensionContext(requirement_id=result["requirement_id"], user_id="echo-demo-user"))


def test_two_providers_share_one_root_and_deduplicate_observation(graph):
    registry, _, result = seeded(graph)
    candidates = {c["supplier_name"]: c for c in result["candidates"]}
    assert candidates["Supplier Alpha"]["apparent_support_count"] == 8
    assert candidates["Supplier Alpha"]["provenance_root_count"] == 1
    assert candidates["Supplier Alpha"]["robust_score"] == 71
    assert candidates["Supplier Beta"]["robust_score"] == 85
    assert result["recommended_supplier_id"] == candidates["Supplier Beta"]["supplier_id"]
    # Both extension runs observed the same canonical source evidence.
    shared = graph.read_only_rows(
        "MATCH (run:ExtensionRun)-[:OBSERVED]->(e:Evidence) "
        "WHERE e.id IN $ids RETURN e.id, count(DISTINCT run)",
        {"ids": [p["evidence_id"] for p in candidates["Supplier Alpha"]["evidence_paths"]]},
    )
    assert sorted(count for _, count in shared) == [1, 1, 1, 1, 1, 1, 1, 2]
    assert len({p["extension_run_id"] for p in candidates["Supplier Alpha"]["evidence_paths"]}) == 2


def test_event_retry_is_idempotent_and_input_reuse_is_rejected(graph):
    registry, runtime, result = seeded(graph)
    request = fresh_request(result)
    execution = asyncio.run(runtime.execute(request, extension_id="demo-source-a"))
    ingestor = ExtensionIngestor(graph)
    manifest = registry.get("demo-source-a").manifest
    first = ingestor.ingest(manifest, request, execution)
    second = ingestor.ingest(manifest, request, execution)
    assert first["event_id"] == second["event_id"]
    assert second["idempotent_replay"] is True
    changed = request.model_copy(update={"input": {"changed": True}})
    with pytest.raises(IngestionRejected, match="another input"):
        ingestor.existing(manifest, changed)


def test_invalid_hash_or_canonical_self_loop_produces_no_partial_event(graph):
    registry, runtime, result = seeded(graph)
    request = fresh_request(result)
    execution = asyncio.run(runtime.execute(request, extension_id="demo-source-a"))
    raw = execution.result.model_dump(mode="json")
    raw["sources"][0]["content_hash"] = "0" * 64
    execution.result = NormalizedResult.model_validate(raw)
    with pytest.raises(IngestionRejected, match="hash"):
        ExtensionIngestor(graph).ingest(registry.get("demo-source-a").manifest, request, execution)
    assert not graph.read_only_rows("MATCH (r:ExtensionRun {id: $id}) RETURN r.id", {"id": execution.run_id})
    raw["sources"][0]["content_hash"] = None
    raw["sources"][1]["url"] = raw["sources"][0]["url"] + "?utm_source=mirror"
    execution.result = NormalizedResult.model_validate(raw)
    with pytest.raises(IngestionRejected, match="self-dependency"):
        ExtensionIngestor(graph).ingest(registry.get("demo-source-a").manifest, request, execution)


def test_unknown_entities_stay_representations_and_cannot_get_supplier_rank(graph):
    registry, runtime, result = seeded(graph)
    request = fresh_request(result)
    execution = asyncio.run(runtime.execute(request, extension_id="demo-source-a"))
    raw = execution.result.model_dump(mode="json")
    for entity in raw["entities"]:
        entity["external_ids"] = {}
    execution.result = NormalizedResult.model_validate(raw)
    summary = ExtensionIngestor(graph).ingest(registry.get("demo-source-a").manifest, request, execution)
    assert summary["resolved_entities"] == {}
    assert sorted(summary["unresolved_entity_refs"]) == ["alpha", "beta", "gamma"]
    representations = graph.read_only_rows(
        "MATCH (run:ExtensionRun {id: $id})-[:PRODUCED]->(r:EntityRepresentation) RETURN r.match_status",
        {"id": execution.run_id},
    )
    assert all(row[0] == "UNRESOLVED" for row in representations)


def test_two_extension_claims_that_disagree_block_recommendation(graph):
    registry, runtime, result = seeded(graph)
    request = fresh_request(result)
    execution = asyncio.run(runtime.execute(request, extension_id="demo-source-b"))
    raw = execution.result.model_dump(mode="json")
    for claim in raw["claims"]:
        if claim["entity_ref"] == "beta":
            claim["value"] = False
    execution.result = NormalizedResult.model_validate(raw)
    ExtensionIngestor(graph).ingest(registry.get("demo-source-b").manifest, request, execution)
    reassessed = EchoEngine(graph).analyze_requirement(result["requirement_id"])
    assert reassessed["decision_status"] == "ABSTAIN"
    assert graph.read_only_rows("MATCH (:Claim)-[r:CONTRADICTS]->(:Claim) RETURN count(r)", {})[0][0] >= 1


def test_source_invalidation_is_not_undone_by_new_extension_observation(graph):
    registry, runtime, result = seeded(graph)
    root = result["ingestions"][0]["source_ids"]["alpha-root"]
    graph.invalidate_source(root, "synthetic invalidation", "2026-10-05T00:00:00+00:00")
    request = fresh_request(result)
    execution = asyncio.run(runtime.execute(request, extension_id="demo-source-a"))
    ExtensionIngestor(graph).ingest(registry.get("demo-source-a").manifest, request, execution)
    assert graph.read_only_rows("MATCH (s:Source {id: $id}) RETURN s.active", {"id": root}) == [[False]]


def test_disabled_provider_preserves_existing_core_demo(graph):
    registry = build_registry()
    registry.set_enabled("demo-source-b", False)
    result = asyncio.run(run_extension_demo(graph, ExtensionRuntime(registry)))
    beta = next(c for c in result["candidates"] if c["supplier_name"] == "Supplier Beta")
    assert beta["provenance_root_count"] == 2
    assert result["decision_status"] == "RECOMMEND"
    legacy = EchoEngine(graph).run_false_consensus_demo()
    assert legacy["recommended_supplier_id"] == "supplier-beta-demo"
