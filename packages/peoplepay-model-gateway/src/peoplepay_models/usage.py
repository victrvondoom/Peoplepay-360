"""Usage aggregation from recorded invocations. Unknown stays unknown."""
from __future__ import annotations

from collections import defaultdict
from .store import ModelStore


def aggregate(store: ModelStore, owner: str | None, since: float | None = None) -> dict:
    rows = store.usage_rows(owner, since)
    per: dict[str, dict] = defaultdict(lambda: {"requests": 0, "errors": 0, "fallbacks": 0, "input_tokens": 0,
                                               "output_tokens": 0, "tokens_reported": 0, "cost": 0.0, "cost_known": 0,
                                               "latency_sum": 0.0, "latency_n": 0, "local": False, "provider_id": None})
    for r in rows:
        p = per[r["connection_id"] or "unknown"]
        p["provider_id"], p["local"] = r["provider_id"], bool(r["local"])
        p["requests"] += 1
        p["errors"] += r["status"] != "ok"
        p["fallbacks"] += r["fallback_parent"] is not None
        if r["input_tokens"] is not None or r["output_tokens"] is not None:
            p["tokens_reported"] += 1
            p["input_tokens"] += r["input_tokens"] or 0
            p["output_tokens"] += r["output_tokens"] or 0
        if r["est_cost"] is not None:
            p["cost"] += r["est_cost"]; p["cost_known"] += 1
        if r["latency_ms"] is not None and r["status"] == "ok":
            p["latency_sum"] += r["latency_ms"]; p["latency_n"] += 1
    out = {}
    for cid, p in per.items():
        out[cid] = {"provider_id": p["provider_id"], "requests": p["requests"], "errors": p["errors"],
                    "fallbacks": p["fallbacks"],
                    "input_tokens": p["input_tokens"] if p["tokens_reported"] else None,
                    "output_tokens": p["output_tokens"] if p["tokens_reported"] else None,
                    "estimated_cost": round(p["cost"], 6) if p["cost_known"] else None,
                    "cost_note": ("local hardware inference; no cloud API quota" if p["local"] else
                                  None if p["cost_known"] else "cost unknown (no reliable pricing)"),
                    "avg_latency_ms": round(p["latency_sum"] / p["latency_n"], 1) if p["latency_n"] else None,
                    "quota": "Quota information unavailable."}
    return {"providers": out, "total_requests": sum(v["requests"] for v in out.values())}
