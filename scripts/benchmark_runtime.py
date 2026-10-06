"""Deterministic platform overhead; explicit captured-provider replay, no models."""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def summary(values):
    ordered = sorted(values)
    return {"runs": len(values), "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3)}


async def measure(runs):
    from journey.extension_runtime import CapabilityRuntime
    from journey.providers import GreenChainProvider, InflationForgeProvider, reference_provider_clients
    from journey.sdk_bridge import to_echo_result
    from peoplepay_sdk import ExtensionContext, ExtensionRequest
    clients = reference_provider_clients()
    host = CapabilityRuntime().load(ROOT / "extensions")
    host.register(GreenChainProvider(clients[0], mode="reference"))
    host.register(InflationForgeProvider(clients[1], mode="reference"))
    timings = {"routing": [], "parallel_reference_invocation": [], "normalization": []}
    for index in range(runs):
        started = time.perf_counter()
        host.resolve("supplier.discovery", "IN")
        host.resolve("price.observe", "IN")
        timings["routing"].append((time.perf_counter()-started)*1000)
        requests = [ExtensionRequest(request_id=f"benchmark-{index}-{cap}", capability=cap,
            context=ExtensionContext(trace_id="benchmark"), input={"product": "ergonomic office chairs", "quantity": 300, "destination": "Bengaluru"},
            constraints={"budget_minor": 200000000, "currency": "INR", "delivery_days": 30})
            for cap in ("supplier.discovery", "price.observe")]
        started = time.perf_counter()
        receipts = await asyncio.gather(*(host.invoke(req, "IN") for req in requests))
        if any(result is None for result, _ in receipts):
            raise RuntimeError("benchmark invocation failed")
        timings["parallel_reference_invocation"].append((time.perf_counter()-started)*1000)
        started = time.perf_counter()
        for result, _ in receipts:
            to_echo_result(result)
        timings["normalization"].append((time.perf_counter()-started)*1000)
    return {"mode": "deterministic captured-provider replay; excludes HTTP, ECHO graph, Gateway and models",
        "timings": {key: summary(values) for key, values in timings.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()
    if not 20 <= args.runs <= 1000:
        parser.error("20 to 1000 runs required for percentile reporting")
    print(json.dumps(asyncio.run(measure(args.runs)), indent=2))
