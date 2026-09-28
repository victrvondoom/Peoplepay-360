import pytest

from app.knowledge_graph.neo4j_graph_store import Neo4jGraphStore


@pytest.mark.asyncio
async def test_neo4j_store_replays_ecommerce_knowledge_events(monkeypatch):
    calls = []

    async def fake_entity(self, payload):
        calls.append(("entity", payload))
        return {"mode": "neo4j"}

    async def fake_relationship(self, payload):
        calls.append(("relationship", payload))
        return {"mode": "neo4j"}

    monkeypatch.setattr(Neo4jGraphStore, "upsert_knowledge_entity", fake_entity)
    monkeypatch.setattr(Neo4jGraphStore, "upsert_knowledge_relationship", fake_relationship)

    store = Neo4jGraphStore()
    await store.add_event("knowledge_entity", {"domain": "ecommerce", "label": "Refund", "name": "Refund"})
    await store.add_event(
        "knowledge_relationship",
        {"domain": "ecommerce", "source": "Return Request", "relation": "MAY_RESULT_IN", "target": "Refund"},
    )

    assert calls == [
        ("entity", {"domain": "ecommerce", "label": "Refund", "name": "Refund"}),
        (
            "relationship",
            {"domain": "ecommerce", "source": "Return Request", "relation": "MAY_RESULT_IN", "target": "Refund"},
        ),
    ]
