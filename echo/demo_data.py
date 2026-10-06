"""Synthetic, deterministic false-consensus fixture. No web data is implied."""

from __future__ import annotations

from typing import Any

from echo.models import stable_id, text_hash

DEMO_SCOPE = "echo-false-consensus-v1"
REQUIREMENT_ID = "req-echo-demo-ergonomic-chairs"
PRODUCT_ID = "product-echo-demo-office-chair"
DECISION_ID = "decision-echo-demo-false-consensus"


def _source(source_id: str, publisher: str, title: str, url: str,
            excerpt: str, source_type: str = "synthetic_demo") -> dict:
    return {
        "id": source_id,
        "publisher": publisher,
        "title": title,
        "source_url": url,
        "source_type": source_type,
        "source_published_at": "2026-09-20T00:00:00+00:00",
        "observed_at": "2026-10-01T12:00:00+00:00",
        "snapshot_text": excerpt,
        "content_hash": text_hash(excerpt),
        "active": True,
        "demo_scope": DEMO_SCOPE,
    }


def build_fixture() -> dict:
    requirement = {
        "id": REQUIREMENT_ID,
        "user_id": "echo-demo-user",
        "description": (
            "Source 300 ergonomic office chairs under $35,000, delivery within "
            "20 days, with strong sustainability evidence."
        ),
        "quantity": 300,
        "budget_minor": 3_500_000,
        "currency": "USD",
        "delivery_days": 20,
        "created_at": "2026-10-01T12:00:00+00:00",
        "demo_scope": DEMO_SCOPE,
    }
    product = {
        "id": PRODUCT_ID,
        "name": "Ergonomic office chair (synthetic demo product)",
        "identity_status": "MATCHED",
        "demo_scope": DEMO_SCOPE,
    }
    suppliers: list[dict[str, Any]] = [
        {"id": "supplier-alpha-demo", "name": "Supplier Alpha",
         "official_domain": "alpha.example", "identity_status": "MATCHED",
         "raw_score": 94.0, "mean_confidence": 0.90,
         "demo_scope": DEMO_SCOPE},
        {"id": "supplier-beta-demo", "name": "Supplier Beta",
         "official_domain": "beta.example", "identity_status": "MATCHED",
         "raw_score": 87.0, "mean_confidence": 0.90,
         "demo_scope": DEMO_SCOPE},
        {"id": "supplier-gamma-demo", "name": "Supplier Gamma",
         "official_domain": "gamma.example", "identity_status": "MATCHED",
         "raw_score": 78.0, "mean_confidence": 0.90,
         "demo_scope": DEMO_SCOPE},
    ]
    agents = [
        {"id": "agent-supplier-discovery", "name": "Supplier Discovery Agent",
         "version": "echo-demo-1", "demo_scope": DEMO_SCOPE},
        {"id": "agent-sustainability", "name": "Sustainability Evidence Agent",
         "version": "echo-demo-1", "demo_scope": DEMO_SCOPE},
        {"id": "agent-market-research", "name": "Market Research Agent",
         "version": "echo-demo-1", "demo_scope": DEMO_SCOPE},
        {"id": "agent-certification-review", "name": "Certification Review Agent",
         "version": "echo-demo-1", "demo_scope": DEMO_SCOPE},
    ]
    sources = [
        _source("source-alpha-root", "Supplier Alpha", "Supplier sustainability claim",
                "https://alpha.example/sustainability/chairs",
                "Synthetic demo: Alpha reports a low-carbon chair line.", "supplier"),
        _source("source-alpha-copy-1", "Furniture Trade Digest", "Supplier profile",
                "https://trade-digest.example/alpha-chair-profile",
                "Synthetic demo: Alpha reports a low-carbon chair line."),
        _source("source-alpha-copy-2", "Materials Weekly", "Chair sourcing round-up",
                "https://materials-weekly.example/chairs/alpha",
                "Synthetic demo: Alpha reports a low-carbon chair line."),
        _source("source-alpha-copy-3", "Procurement Notes", "Supplier comparison",
                "https://procurement-notes.example/alpha-sourcing",
                "Synthetic demo: Alpha reports a low-carbon chair line."),
        _source("source-alpha-copy-4", "Circular Office Blog", "Office chair guide",
                "https://circular-office.example/guides/chairs-alpha",
                "Synthetic demo: Alpha reports a low-carbon chair line."),
        _source("source-beta-root-1", "Independent Lab One", "Lifecycle summary",
                "https://lab-one.example/reports/beta-chair",
                "Synthetic demo: independent lifecycle summary for Beta."),
        _source("source-beta-root-2", "Standards Registry Two", "Material record",
                "https://registry-two.example/materials/beta-chair",
                "Synthetic demo: independent material record for Beta.", "standards_body"),
        _source("source-beta-root-3", "University Lab Three", "Transport study",
                "https://university-three.example/studies/beta-chair",
                "Synthetic demo: independent transport study for Beta.", "journalistic"),
        _source("source-gamma-root", "Supplier Gamma", "Product disclosure",
                "https://gamma.example/disclosures/chair",
                "Synthetic demo: Gamma product disclosure.", "supplier"),
    ]
    claim_by_supplier = {
        item["id"]: {
            "id": stable_id("claim", REQUIREMENT_ID, item["id"], "low_carbon"),
            "requirement_id": REQUIREMENT_ID,
            "predicate": "low_carbon_sourcing",
            "value": True,
            "polarity": "SUPPORTS",
            "created_at": "2026-10-01T12:00:00+00:00",
            "demo_scope": DEMO_SCOPE,
        }
        for item in suppliers
    }
    evidence = []
    alpha_sources = [s["id"] for s in sources[:5]]
    alpha_agent_runs = ["run-alpha-1", "run-alpha-2", "run-alpha-3", "run-alpha-4"]
    for index in range(8):
        source_id = alpha_sources[index % len(alpha_sources)]
        run_id = alpha_agent_runs[index % len(alpha_agent_runs)]
        excerpt = f"Synthetic demo observation {index + 1}: Alpha is described as low-carbon."
        evidence.append({
            "id": f"evidence-alpha-{index + 1}",
            "claim_id": claim_by_supplier["supplier-alpha-demo"]["id"],
            "source_id": source_id,
            "agent_run_id": run_id,
            "observed_at": "2026-10-01T12:00:00+00:00",
            "confidence": 0.90,
            "verification_state": "SYNTHETIC_DEMO",
            "excerpt": excerpt,
            "content_hash": text_hash(excerpt),
            "active": True,
            "demo_scope": DEMO_SCOPE,
        })
    beta_source_ids = [s["id"] for s in sources[5:8]]
    for index, source_id in enumerate(beta_source_ids):
        excerpt = f"Synthetic demo independent evidence {index + 1}: Beta supports the claim."
        evidence.append({
            "id": f"evidence-beta-{index + 1}",
            "claim_id": claim_by_supplier["supplier-beta-demo"]["id"],
            "source_id": source_id,
            "agent_run_id": f"run-beta-{index + 1}",
            "observed_at": "2026-10-01T12:00:00+00:00",
            "confidence": 0.90,
            "verification_state": "SYNTHETIC_DEMO",
            "excerpt": excerpt,
            "content_hash": text_hash(excerpt),
            "active": True,
            "demo_scope": DEMO_SCOPE,
        })
    gamma_excerpt = "Synthetic demo evidence for Gamma."
    evidence.append({
        "id": "evidence-gamma-1",
        "claim_id": claim_by_supplier["supplier-gamma-demo"]["id"],
        "source_id": "source-gamma-root",
        "agent_run_id": "run-gamma-1",
        "observed_at": "2026-10-01T12:00:00+00:00",
        "confidence": 0.90,
        "verification_state": "SYNTHETIC_DEMO",
        "excerpt": gamma_excerpt,
        "content_hash": text_hash(gamma_excerpt),
        "active": True,
        "demo_scope": DEMO_SCOPE,
    })
    runs = []
    for index, run_id in enumerate(alpha_agent_runs):
        runs.append({"id": run_id, "requirement_id": REQUIREMENT_ID,
                     "agent_id": agents[index]["id"], "created_at": requirement["created_at"],
                     "status": "SUCCEEDED", "demo_scope": DEMO_SCOPE})
    for index in range(1, 4):
        runs.append({"id": f"run-beta-{index}", "requirement_id": REQUIREMENT_ID,
                     "agent_id": agents[index - 1]["id"], "created_at": requirement["created_at"],
                     "status": "SUCCEEDED", "demo_scope": DEMO_SCOPE})
    runs.append({"id": "run-gamma-1", "requirement_id": REQUIREMENT_ID,
                 "agent_id": "agent-market-research", "created_at": requirement["created_at"],
                 "status": "SUCCEEDED", "demo_scope": DEMO_SCOPE})
    run_agent = {run["id"]: run["agent_id"] for run in runs}
    dependencies = [
        {"source_id": "source-alpha-copy-1", "root_id": "source-alpha-root",
         "relationship": "DERIVED_FROM", "evidence_mode": "EXPLICIT_SYNTHETIC"},
        {"source_id": "source-alpha-copy-2", "root_id": "source-alpha-root",
         "relationship": "CITES", "evidence_mode": "EXPLICIT_SYNTHETIC"},
        {"source_id": "source-alpha-copy-3", "root_id": "source-alpha-root",
         "relationship": "MIRRORS", "evidence_mode": "EXPLICIT_SYNTHETIC"},
        {"source_id": "source-alpha-copy-4", "root_id": "source-alpha-root",
         "relationship": "DERIVED_FROM", "evidence_mode": "EXPLICIT_SYNTHETIC"},
    ]
    return {
        "requirement": requirement,
        "product": product,
        "suppliers": suppliers,
        "agents": agents,
        "runs": runs,
        "run_agent": run_agent,
        "sources": sources,
        "claims": list(claim_by_supplier.values()),
        "claim_by_supplier": {key: value["id"] for key, value in claim_by_supplier.items()},
        "evidence": evidence,
        "dependencies": dependencies,
        "raw_winner": "supplier-alpha-demo",
    }
