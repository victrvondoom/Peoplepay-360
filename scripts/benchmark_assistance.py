"""Measure the local assistance boundary using fictional, consented profiles.

Creates local workflow/decision records. Requires the documented core plus
CivicMesh launcher and deliberately refuses non-loopback endpoints.
"""
import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from peoplepay_sdk import ExtensionContext, ExtensionRequest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extensions.civicmesh.adapter import normalize  # noqa: E402
from journey.sdk_bridge import to_echo_result  # noqa: E402


def summary(values):
    ordered = sorted(values)
    return {"samples": len(values), "p50_ms": round(statistics.median(values), 3),
            "p95_ms": round(ordered[math.ceil(len(values) * .95) - 1], 3),
            "max_ms": round(max(values), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8180")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", default="output/diagnostics/civicmesh-benchmark.json")
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}
            or parts.username or parts.password or parts.path or parts.query or parts.fragment):
        parser.error("Use a plain loopback HTTP origin")
    if not 1 <= args.samples <= 20:
        parser.error("Samples must be between 1 and 20")
    request = ExtensionRequest(request_id="assistance-test-v1", capability="assistance_eligibility",
        context=ExtensionContext(trace_id="assistance-test", transaction_id="assistance-test"),
        input={"jurisdiction": "US", "need": "eviction", "facts": {"age": 72, "income_annual": 14400}, "consent": True})
    captured = json.loads((ROOT / "tests/fixtures/civicmesh_native.json").read_text(encoding="utf-8"))
    adapter, bridge = [], []
    for _ in range(100):
        started = time.perf_counter()
        receipt = normalize(request, captured)
        adapter.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        to_echo_result(receipt)
        bridge.append((time.perf_counter() - started) * 1000)
    stages: dict[str, list[float]] = {"native_engine": [], "provider_health_http_and_sdk": [], "echo_request_including_graph": [], "end_to_end_http": []}
    actor = "benchmark-" + uuid4().hex
    headers = {"X-Beacon-User": actor}
    if os.getenv("PEOPLEPAY_BENCHMARK_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["PEOPLEPAY_BENCHMARK_TOKEN"]
    with httpx.Client(base_url=args.url, headers=headers, timeout=30, trust_env=False) as client:
        for _ in range(args.samples):
            started = time.perf_counter()
            response = client.post("/api/v1/assistance", json={"message": "My landlord is evicting me.",
                "jurisdiction": "US", "consent": True, "facts": {"age": 72, "income_annual": 14400}})
            response.raise_for_status()
            record = response.json()
            assert record["decision"]["money_moved"] is False
            stages["end_to_end_http"].append((time.perf_counter() - started) * 1000)
            metrics = record["metrics"]
            stages["native_engine"].append(metrics["native_engine_ms"])
            stages["provider_health_http_and_sdk"].append(metrics["provider_runtime_ms"])
            stages["echo_request_including_graph"].append(metrics["echo_request_ms"])
    report = {"scope": "Local warm service, fictional U.S. eviction profiles; not a production SLA",
        "normalization_only": {"native_to_sdk": summary(adapter), "sdk_to_echo": summary(bridge)},
        "live_http_stages": {key: summary(values) for key, values in stages.items()},
        "output_per_evaluation": {"programs": len(record["decision"]["options"]),
                                  "claims": record["decision"]["ingestion"]["claim_count"]}}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
