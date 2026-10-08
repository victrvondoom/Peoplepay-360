"""Dependency-tracked incremental recomputation with early cutoff.

Prior art, stated plainly: this is the build-system / incremental-computation idea (Make, Bazel,
Salsa, Adapton, differential dataflow) applied to evidence-backed decisions. What is specific here
is the dependency *source* (observed reads against a bitemporal vintage store) and the early-cutoff
boundary (a coarse recommendation summary that gates paid explanation work).

Correctness contract (verified by ``verify_against_full``): after ``apply_revisions`` the results
must equal a from-scratch recomputation at the same knowledge time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .procurement import DecisionResult, Requirement, compute_decision
from .vintage import Snapshot, TrackingReader, VintageStore


@dataclass
class ImpactReport:
    revised_keys: int
    candidates: int                 # decisions whose recorded dependencies include a revised key
    recomputed: int                 # candidates whose observed fingerprint actually differs
    summary_changed: int            # recomputed AND recommendation summary changed (early cutoff boundary)
    unchanged_after_recompute: int
    compute_seconds: float
    changed_ids: list[int] = field(default_factory=list)
    recomputed_ids: list[int] = field(default_factory=list)


class IncrementalEngine:
    def __init__(self, store: VintageStore, reqs: list[Requirement], draws: int = 1000):
        self.store, self.reqs, self.draws = store, reqs, draws
        self.results: list[DecisionResult | None] = [None] * len(reqs)
        self.deps: list[dict[int, int] | None] = [None] * len(reqs)   # decision -> {key: fingerprint seen}
        self.rev: dict[int, list[int]] = {}                           # key -> decisions that read it
        self.t: float | None = None

    # -- build
    def _compute(self, i: int, snap: Snapshot):
        rd = TrackingReader(snap)
        return compute_decision(self.reqs[i], rd, self.draws), rd.seen

    def install(self, i: int, result: DecisionResult, seen: dict[int, int]) -> None:
        """Record a result (also used by the parallel grid, which computes in worker processes)."""
        old = self.deps[i]
        if old is not None:
            for k in old.keys() - seen.keys():
                self.rev[k].remove(i)
        for k in seen.keys() - (old.keys() if old else set()):
            self.rev.setdefault(k, []).append(i)
        self.results[i], self.deps[i] = result, seen

    def full_run(self, t: float) -> float:
        t0 = time.perf_counter()
        snap = self.store.snapshot(t)
        for i in range(len(self.reqs)):
            self.install(i, *self._compute(i, snap))
        self.t = t
        return time.perf_counter() - t0

    # -- incremental
    def stale_candidates(self, revised: list[tuple[str, int]], t_new: float) -> tuple[set[int], list[int]]:
        """(revised keys, decisions whose observed dependencies really changed). A republished identical
        value changes no fingerprint and therefore invalidates nothing."""
        keys = {self.store.key(s, p) for s, p in revised}
        candidates = sorted({i for k in keys for i in self.rev.get(k, ())})
        snap = self.store.snapshot(t_new)
        stale_ids = []
        for i in candidates:
            for k in keys & self.deps[i].keys():
                s, p = self.store.key_parts(k)
                o = snap.read(s, p)
                if (o.fingerprint() if o else 0) != self.deps[i][k]:
                    stale_ids.append(i)
                    break
        self._last_candidates = len(candidates)
        return keys, stale_ids

    def apply_revisions(self, revised: list[tuple[str, int]], t_new: float, workers: int = 1,
                        parallel_threshold: int = 2000) -> ImpactReport:
        """``workers`` > 1 recomputes the stale set on the worker grid when it is large enough to pay for it."""
        t0 = time.perf_counter()
        keys, stale_ids = self.stale_candidates(revised, t_new)
        snap = self.store.snapshot(t_new)
        changed, same = [], 0
        if workers > 1 and len(stale_ids) >= parallel_threshold:
            from .grid import run_grid
            rep = run_grid(self.store, self.reqs, stale_ids, t_new, workers=workers, draws=self.draws,
                           chunk=max(50, len(stale_ids) // (workers * 8)), track=True)
            computed = [(i, *rep.results[i]) for i in stale_ids]
        else:
            computed = [(i, *self._compute(i, snap)) for i in stale_ids]
        for i, res, seen in computed:
            if res.summary() != self.results[i].summary():
                changed.append(i)
            else:
                same += 1
            self.install(i, res, seen)
        self.t = t_new
        return ImpactReport(len(keys), self._last_candidates, len(stale_ids), len(changed), same,
                            time.perf_counter() - t0, changed, list(stale_ids))

    # -- verification
    def verify_against_full(self, t: float | None = None) -> tuple[bool, list[int]]:
        """Recompute everything from scratch and compare exactly. Returns (ok, mismatching ids)."""
        snap = self.store.snapshot(self.t if t is None else t)
        bad = []
        for i in range(len(self.reqs)):
            fresh = compute_decision(self.reqs[i], snap, self.draws)
            if fresh != self.results[i]:
                bad.append(i)
        return (not bad, bad)
