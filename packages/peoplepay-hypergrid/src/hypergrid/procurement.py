"""Procurement decision numerics: deterministic statistics + seeded Monte Carlo (NumPy).

No language model is involved. Dependencies on observations are tracked through the reader.
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np

WINDOW = 10        # history periods read per series (annual data: 10 years)


@dataclass(frozen=True)
class Supplier:
    id: str
    base_price: float                    # per unit, in `currency`
    currency: str                        # "INR" | "USD"
    exposure: tuple[tuple[str, float], ...]   # (series, weight): how unit price indexes to each series


@dataclass(frozen=True)
class Requirement:
    id: str
    quantity: int
    suppliers: tuple[Supplier, ...]
    fx_series: str = "WB.IND.FX"         # LCU per USD, used to convert USD base prices
    data_class: str = "INTERNAL"         # LOCAL_ONLY decisions must never reach a cloud model
    period_now: int = 2024

    def series_used(self) -> tuple[str, ...]:
        s = {name for sup in self.suppliers for name, _ in sup.exposure}
        if any(sup.currency == "USD" for sup in self.suppliers):
            s.add(self.fx_series)
        return tuple(sorted(s))

    def facts_shape(self) -> tuple:
        """Everything except the id: two requirements with the same shape have the same facts."""
        return (self.quantity, self.fx_series, self.period_now,
                tuple((s.base_price, s.currency, s.exposure) for s in self.suppliers))


@dataclass(frozen=True)
class DecisionResult:
    winner: int
    mean_cost: tuple[float, ...]
    p90_cost: tuple[float, ...]
    margin: float                        # (runner-up - winner) / winner on mean cost
    p_not_best: float                    # MC probability the winner is not the cheapest
    quality_flags: tuple[str, ...]
    complete: bool                       # all history periods were available

    def summary(self) -> tuple:
        """Coarse, id-free recommendation tuple: the early-cutoff boundary. A revision that moves
        costs by less than 0.1% and leaves the margin bucket unchanged does not re-trigger the
        (expensive) explanation step. The tolerance is explicit and configurable by design."""
        w = self.mean_cost[self.winner]
        return (self.winner, int(round(math.log(max(w, 1e-9)) / 0.001)), int(self.margin * 100),
                self.quality_flags, self.complete)

    @property
    def hard(self) -> bool:
        return self.margin < 0.03 or bool(self.quality_flags) or self.p_not_best > 0.25 or not self.complete


def seed_for(req: "Requirement", salt: int = 0) -> int:
    """Seeded from the *facts*, never the id: identical inputs must give identical outputs (this is what
    makes exact-match caching and incremental early-cutoff sound)."""
    return zlib.crc32(f"{req.facts_shape()!r}|{salt}".encode()) & 0xFFFFFFFF


def compute_decision(req: Requirement, reader, draws: int = 1000, salt: int = 0) -> DecisionResult:
    names = req.series_used()
    growth, vol, last, flags, complete = {}, {}, {}, set(), True
    for s in names:
        vals = []
        for p in range(req.period_now - WINDOW, req.period_now + 1):
            o = reader.read(s, p)
            if o is None:
                complete = False
                continue
            vals.append(o.value)
            if o.quality != "ok":
                flags.add(f"{s}:{o.quality}")
        if len(vals) < 3:
            growth[s], vol[s], last[s] = 0.0, 0.0, vals[-1] if vals else 1.0
            complete = False
            continue
        arr = np.asarray(vals, dtype=np.float64)
        lr = np.diff(np.log(arr))
        growth[s], vol[s], last[s] = float(lr.mean()), float(lr.std(ddof=1)), float(arr[-1])
    rng = np.random.default_rng(seed_for(req, salt))
    z = rng.standard_normal((draws, len(names)))
    zi = {s: i for i, s in enumerate(names)}
    costs = np.empty((draws, len(req.suppliers)))
    for j, sup in enumerate(req.suppliers):
        base = sup.base_price * (last[req.fx_series] if sup.currency == "USD" else 1.0)
        expo = np.zeros(draws)
        for s, w in sup.exposure:
            expo += w * (growth[s] + vol[s] * z[:, zi[s]])
        if sup.currency == "USD":
            expo += growth[req.fx_series] + vol[req.fx_series] * z[:, zi[req.fx_series]]
        costs[:, j] = req.quantity * base * np.exp(expo)
    mean = costs.mean(axis=0)
    order = np.argsort(mean)
    w, r = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
    margin = float((mean[r] - mean[w]) / mean[w]) if len(order) > 1 else 1.0
    p_not_best = float((costs.argmin(axis=1) != w).mean())
    return DecisionResult(w, tuple(float(x) for x in mean), tuple(float(x) for x in np.percentile(costs, 90, axis=0)),
                          margin, p_not_best, tuple(sorted(flags)), complete)
