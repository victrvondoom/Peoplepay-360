"""Evaluation framework — runs the existing per-domain synthetic_cases.jsonl
files (already used as test fixtures elsewhere in this project) as a
benchmark: domain-classification accuracy, specialist-routing accuracy,
retrieval hit rate/latency (cheap, no LLM calls, safe to run over every
case), plus citation accuracy and a keyword-overlap faithfulness proxy over
a small bounded sample per domain via the full case workflow (LLM calls,
deliberately capped to keep this affordable to run repeatedly).

Honest limitation: "faithfulness" here is keyword overlap between the final
answer and retrieved context, not an LLM-judged faithfulness score -- a
real evaluation pipeline would add an LLM-as-judge pass for that; this is a
cheap, always-available proxy, not a replacement for one.
"""
from __future__ import annotations

import statistics
import time
from pathlib import Path

from app.agents.role_agents.domain_router import classify_domains
from app.agents.role_agents.planner import build_plan
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.citation_engine import build_citations

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[3] / "knowledge"
DEEP_EVAL_SAMPLE_SIZE = 2


def _load_synthetic_cases(domain: Domain) -> list[dict]:
    path = KNOWLEDGE_ROOT / domain.value / "synthetic_cases" / f"{domain.value}_synthetic_cases.jsonl"
    if not path.exists():
        return []
    cases = []
    import json
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


def _case_query_text(case: dict) -> str:
    """Not every domain's synthetic cases have a "query" field (only
    healthcare does) -- banking/telecom/government/housing describe the
    case as structured facts instead. Normalize to a single query string."""
    facts = case.get("facts", {})
    if facts.get("query"):
        return str(facts["query"])
    return " ".join(str(v) for v in facts.values() if v is not None)


async def evaluate_domain_fast(domain: Domain) -> dict | None:
    """Structural checks over every synthetic case for a domain: no LLM
    calls, safe/cheap to run for all cases repeatedly."""
    cases = _load_synthetic_cases(domain)
    if not cases:
        return None

    correct_domain = 0
    routing_hits = 0
    retrieval_hits = 0
    retrieval_latencies_ms: list[float] = []

    for case in cases:
        query = _case_query_text(case)
        expected_agents = set(case.get("expected_agents", []))

        candidates = classify_domains(query)
        if candidates and candidates[0]["domain"] == domain:
            correct_domain += 1

        plan = build_plan({"case_summary": query, "domain": domain})
        if not expected_agents or set(plan.get("specialists", [])) & expected_agents:
            routing_hits += 1

        start = time.monotonic()
        hits = await qdrant_service.search_chunks(domain, query, top_k=5)
        retrieval_latencies_ms.append((time.monotonic() - start) * 1000)
        if hits:
            retrieval_hits += 1

    total = len(cases)
    return {
        "domain": domain.value,
        "total_cases": total,
        "domain_classification_accuracy": round(correct_domain / total, 3),
        "routing_accuracy": round(routing_hits / total, 3),
        "retrieval_hit_rate": round(retrieval_hits / total, 3),
        "avg_retrieval_latency_ms": round(statistics.mean(retrieval_latencies_ms), 1),
    }


def _faithfulness_proxy(final_answer: str, retrieved_context: str) -> float:
    """Crude keyword-overlap faithfulness proxy: what fraction of the final
    answer's distinctive words also appear in the retrieved context. Not an
    LLM-judged faithfulness score -- see module docstring."""
    answer_words = {w.lower() for w in final_answer.split() if len(w) > 5}
    if not answer_words:
        return 0.0
    context_lower = retrieved_context.lower()
    covered = sum(1 for w in answer_words if w in context_lower)
    return round(covered / len(answer_words), 3)


async def evaluate_domain_deep(domain: Domain, sample_size: int = DEEP_EVAL_SAMPLE_SIZE) -> dict | None:
    """Runs a small, bounded sample of cases through the full case workflow
    (real LLM calls) to measure citation accuracy, a faithfulness proxy, and
    end-to-end latency. Capped deliberately -- this is not meant to run over
    every case in every domain on every invocation."""
    from app.agents.orchestrator.case_workflow import case_workflow

    cases = _load_synthetic_cases(domain)[:sample_size]
    if not cases:
        return None

    citation_counts = []
    citation_accuracies = []
    faithfulness_scores = []
    latencies_ms = []

    for index, case in enumerate(cases):
        query = _case_query_text(case)
        start = time.monotonic()
        state = await case_workflow.run({
            "case_id": f"eval-{domain.value}-{index}",
            "user_id": "evaluation-benchmark",
            "domain": domain,
            "case_summary": query,
        })
        latencies_ms.append((time.monotonic() - start) * 1000)

        citations = state.get("structured_citations", [])
        citation_counts.append(len(citations))
        with_url_or_title = sum(1 for c in citations if c.get("url") or c.get("title") != "Untitled source")
        citation_accuracies.append(with_url_or_title / len(citations) if citations else 0.0)

        final_answer = state.get("final_answer", "")
        faithfulness_scores.append(_faithfulness_proxy(final_answer, state.get("retrieved_context", "")))

    return {
        "domain": domain.value,
        "sample_size": len(cases),
        "avg_citation_count": round(statistics.mean(citation_counts), 1),
        "avg_citation_accuracy": round(statistics.mean(citation_accuracies), 3),
        "avg_faithfulness_proxy": round(statistics.mean(faithfulness_scores), 3),
        "avg_latency_ms": round(statistics.mean(latencies_ms), 1),
    }
