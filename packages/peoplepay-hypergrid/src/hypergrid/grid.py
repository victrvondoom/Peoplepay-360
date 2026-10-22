"""Bounded worker grid for CPU-bound numerics (multiprocessing; ``fork`` where available, ``spawn`` otherwise).

Mechanisms, all exercised by tests: bounded in-flight chunks (backpressure/admission control),
microbatching, idempotent chunk keys (a duplicate completion is ignored), retry budget with
exponential-free immediate retry, dead-letter queue, cancellation, injectable faults.

The shared read-only context (snapshot, requirements, draws, faults) reaches each worker through the pool
initializer. Under ``fork`` that is inherited copy-on-write with no copying; under ``spawn`` (Windows, and
macOS by default) it is pickled once per worker. Results are identical either way because nothing in a result
depends on process state: seeds are CRC32 of the facts, fingerprints are content digests and dependency keys
are ``(series, period)`` tuples.

Deliberately NOT a distributed system: one machine, one process pool. Multi-host scheduling,
work stealing and autoscaling are not implemented (see docs/hypergrid/STATUS.md).
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import threading
import time
import zlib
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field

from .procurement import DecisionResult, compute_decision
from .vintage import TrackingReader

_CTX: dict = {}          # per-process, filled by ``_init_worker`` in each worker

#: ProcessPoolExecutor on Windows cannot exceed 61 workers (WaitForMultipleObjects limit).
_MAX_WORKERS = 61 if sys.platform == "win32" else 1 << 16


def _init_worker(ctx: dict) -> None:
    _CTX.clear()
    _CTX.update(ctx)


def _mp_context():
    return mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")


class TransientFault(Exception):
    pass


@dataclass
class FaultPlan:
    """Deterministic fault injection: a chunk fails on its first ``fail_attempts`` attempts."""
    rate: float = 0.0
    fail_attempts: int = 1
    seed: int = 0

    def should_fail(self, chunk_id: int, attempt: int) -> bool:
        if self.rate <= 0 or attempt >= self.fail_attempts:
            return False
        return (zlib.crc32(f"{self.seed}|{chunk_id}".encode()) % 10_000) / 10_000 < self.rate


def _work(chunk_id: int, idxs: list[int], attempt: int, track: bool):
    ctx = _CTX
    plan: FaultPlan = ctx["faults"]
    if plan.should_fail(chunk_id, attempt):
        raise TransientFault(f"injected fault in chunk {chunk_id}")
    snap, reqs, draws = ctx["snap"], ctx["reqs"], ctx["draws"]
    out = []
    for i in idxs:
        if track:
            rd = TrackingReader(snap)
            res = compute_decision(reqs[i], rd, draws)
            out.append((i, res, rd.seen))
        else:
            out.append((i, compute_decision(reqs[i], snap, draws), None))
    return chunk_id, out


@dataclass
class GridReport:
    workers: int
    chunks: int
    completed: int
    retries: int
    dead_lettered: list[int]
    seconds: float
    max_in_flight: int
    cancelled: bool = False
    results: dict = field(default_factory=dict)       # idx -> (result, seen|None)


def run_grid(store, reqs, indices, t: float, *, workers: int, draws: int = 1000, chunk: int = 200,
             retry_budget: int = 2, max_in_flight: int | None = None, faults: FaultPlan | None = None,
             track: bool = False, cancel: threading.Event | None = None) -> GridReport:
    shared = dict(snap=store.snapshot(t), reqs=reqs, draws=draws, faults=faults or FaultPlan())
    workers = max(1, min(workers, _MAX_WORKERS))
    chunks = {c: indices[c * chunk:(c + 1) * chunk] for c in range((len(indices) + chunk - 1) // chunk)}
    limit = max_in_flight or workers * 2
    t0 = time.perf_counter()
    rep = GridReport(workers, len(chunks), 0, 0, [], 0.0, 0)
    attempts = {c: 0 for c in chunks}
    pending = list(chunks)
    inflight: dict = {}
    done_chunks: set[int] = set()
    with ProcessPoolExecutor(max_workers=workers, mp_context=_mp_context(),
                             initializer=_init_worker, initargs=(shared,)) as pool:
        while pending or inflight:
            while pending and len(inflight) < limit and not (cancel and cancel.is_set()):
                c = pending.pop(0)
                inflight[pool.submit(_work, c, chunks[c], attempts[c], track)] = c
                rep.max_in_flight = max(rep.max_in_flight, len(inflight))
            if cancel and cancel.is_set():
                rep.cancelled = True
                pending.clear()
            if not inflight:
                break
            done, _ = wait(inflight, return_when=FIRST_COMPLETED)
            for f in done:
                c = inflight.pop(f)
                try:
                    cid, out = f.result()
                except TransientFault:
                    attempts[c] += 1
                    if attempts[c] > retry_budget:
                        rep.dead_lettered.append(c)
                    else:
                        rep.retries += 1
                        pending.insert(0, c)
                    continue
                if cid in done_chunks:          # idempotent: duplicate completion ignored
                    continue
                done_chunks.add(cid)
                rep.completed += 1
                for i, res, seen in out:
                    rep.results[i] = (res, seen)
    rep.seconds = time.perf_counter() - t0
    return rep
