"""Task-specific benchmark harness. No universal "intelligence score".

Each task has a deterministic checker; we record pass/fail, total latency and TTFT.
Run only on explicit user action: it invokes (possibly paid) models.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .canonical import InferenceRequest, Message, ModelSelection
from .gateway import ModelGateway


@dataclass
class BenchTask:
    category: str
    prompt: str
    check: Callable[[str], bool]


DEFAULT_TASKS = [
    BenchTask("intent routing", "Classify the intent as exactly one word: BUY, DISPUTE or INFO. Text: 'my order never arrived'.", lambda t: "dispute" in t.lower()),
    BenchTask("structured extraction", "Extract the quantity as digits only: 'Order 300 chairs for INR 17.7 lakh'.", lambda t: "300" in t),
    BenchTask("evidence relevance", "Answer YES or NO: is a supplier's own brochure independent evidence of its delivery times?", lambda t: "no" in t.lower()),
]


def run_benchmark(gw: ModelGateway, owner: str, route_keys: list[str], tasks: list[BenchTask] | None = None) -> list[dict]:
    out = []
    for key in route_keys:
        for task in tasks or DEFAULT_TASKS:
            req = InferenceRequest(messages=[Message.user(task.prompt)], selection=ModelSelection("model", key, one_shot=True),
                                   stream=True, max_output_tokens=64, task="background")
            t0 = time.perf_counter()
            ttft, text, err = None, [], None
            for ev in gw.stream(owner, req):
                if ev.type == "text.delta":
                    ttft = ttft if ttft is not None else (time.perf_counter() - t0) * 1000
                    text.append(ev.data["text"])
                elif ev.type == "error":
                    err = ev.data.get("code")
            out.append({"route": key, "category": task.category, "passed": err is None and task.check("".join(text)),
                        "ttft_ms": ttft, "total_ms": (time.perf_counter() - t0) * 1000, "error": err})
    return out
