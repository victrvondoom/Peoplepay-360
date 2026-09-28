import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.knowledge_graph.jsonl_graph_store import JsonlGraphStore
from app.knowledge_graph.neo4j_graph_store import Neo4jGraphStore


def event_domain(event: dict) -> str | None:
    payload = event.get("payload", {})
    domain = payload.get("domain")
    if domain:
        return domain
    case = payload.get("case") or {}
    case_domain = case.get("domain")
    return getattr(case_domain, "value", case_domain)


async def migrate(domain: str | None = None) -> dict:
    jsonl = JsonlGraphStore()
    neo4j = Neo4jGraphStore()
    events = jsonl.iter_events()
    if domain:
        events = [event for event in events if event_domain(event) == domain]
    replayed = 0
    for event in events:
        await neo4j.add_event(event["event_type"], event["payload"])
        replayed += 1
    health = neo4j.health_check()
    return {"domain_filter": domain, "events_read": len(events), "events_replayed": replayed, "neo4j": health}


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description="Replay JSONL graph events to Neo4j.")
    parser.add_argument("--domain", help="Optional domain filter, for example ecommerce")
    args = parser.parse_args()
    result = asyncio.run(migrate(domain=args.domain))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
