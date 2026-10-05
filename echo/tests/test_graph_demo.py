
import pytest

from echo.engine import EchoEngine
from echo.graph_store import EchoGraphStore


@pytest.fixture()
def store():
    graph_store = EchoGraphStore()
    try:
        assert graph_store.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"FalkorDB is not available: {exc}")
    return graph_store


def test_fixture_recomputes_winner_from_falkordb_lineage(store):
    result = EchoEngine(store).run_false_consensus_demo()
    assert result["raw_winner_supplier_id"] == "supplier-alpha-demo"
    assert result["recommended_supplier_id"] == "supplier-beta-demo"
    candidates = {row["supplier_id"]: row for row in result["candidates"]}
    assert candidates["supplier-alpha-demo"]["provenance_root_count"] == 1
    assert candidates["supplier-alpha-demo"]["apparent_support_count"] == 8
    assert candidates["supplier-beta-demo"]["provenance_root_count"] == 3


def test_source_invalidation_changes_followup_decision(store):
    engine = EchoEngine(store)
    result = engine.run_false_consensus_demo()
    store.invalidate_source("source-beta-root-1", "synthetic test invalidation", "2026-10-05T00:00:00+00:00")
    reassessed = engine.analyze_requirement(result["requirement_id"],
                                            parent_decision_id=result["decision_id"])
    beta = next(row for row in reassessed["candidates"]
                if row["supplier_id"] == "supplier-beta-demo")
    assert beta["provenance_root_count"] == 2
    assert reassessed["recommended_supplier_id"] == "supplier-beta-demo"
