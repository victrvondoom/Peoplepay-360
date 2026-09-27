"""Run the evaluation benchmark (fast structural checks over every synthetic
case, plus a small bounded deep-eval sample with real LLM calls) across
every domain that has a synthetic_cases.jsonl file, and print a report.

Usage:
    python scripts/run_evaluation_benchmark.py            # fast checks only
    python scripts/run_evaluation_benchmark.py --deep      # + deep eval sample
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.domain import ACTIVE_DOMAINS
from app.services.evaluation_service import evaluate_domain_deep, evaluate_domain_fast


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep", action="store_true", help="Also run the bounded deep-eval sample (real LLM calls)")
    args = parser.parse_args()

    fast_results = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        result = await evaluate_domain_fast(domain)
        if result:
            fast_results.append(result)

    print("=" * 70)
    print("FAST EVALUATION (no LLM calls) — every synthetic case per domain")
    print("=" * 70)
    print(json.dumps(fast_results, indent=2))

    if args.deep:
        deep_results = []
        for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
            result = await evaluate_domain_deep(domain)
            if result:
                deep_results.append(result)
        print()
        print("=" * 70)
        print("DEEP EVALUATION (real LLM calls, bounded sample per domain)")
        print("=" * 70)
        print(json.dumps(deep_results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
