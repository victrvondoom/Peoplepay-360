"""
One-off backfill: existing cases outside health_insurance were created
before institution-name extraction existed, so almost all of them (67 of 67
non-health_insurance cases as of this run) have institution_name literally
set to "Not specified" -- which meant Institution Intelligence had nothing
real to query against for 7 of the app's 8 domains. Re-runs the same
extraction now used for new cases (multi_domain_workflow._extract_institution_name)
against each existing case's stored summary, and updates both the case
record and the knowledge-graph case_graph entry so pattern/similar-case
lookups pick up the corrected name too.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.orchestrator.multi_domain_workflow import _extract_institution_name
from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph


async def main():
    cases = case_repository.local.read("cases")
    targets = [c for c in cases if c.get("institution_name") == "Not specified" and c.get("domain") != "health_insurance"]
    print(f"Found {len(targets)} cases to re-check.")

    updated = 0
    for case in targets:
        await asyncio.sleep(1.2)  # stay under the NVIDIA API rate limit
        summary = case.get("summary") or case.get("title") or ""
        name = await _extract_institution_name(summary)
        if name != "Not specified":
            case["institution_name"] = name
            case_repository.local.upsert("cases", "id", case)
            await knowledge_graph.upsert_case_graph(case)
            updated += 1
            print(f"  [{case.get('domain')}] {case['id'][:8]}... -> {name}")

    print(f"\nDone. Updated {updated} of {len(targets)} cases with a real institution name.")


if __name__ == "__main__":
    asyncio.run(main())
