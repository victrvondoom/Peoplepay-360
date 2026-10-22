"""Procurement decision numerics: deterministic statistics + seeded Monte Carlo (NumPy).

No language model is involved. Dependencies on observations are tracked through the reader.

Inputs are validated where they enter (see ``validation``): a non-finite or non-positive number is refused or
flagged, never allowed to travel through ``np.log`` and come out as a ``nan`` cost.
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

import numpy as np

from .validation import InsufficientData, InvalidInput, finite, positive, positive_int
from .vintage import PERIOD_LIMIT

WINDOW = 10        # history periods read per series (annual data: 10 years)

#: Currencies the model can convert. Any other code is refused: treating an unknown currency as INR would be a
#: silent unit error.
CURRENCIES = ("INR", "USD")


@dataclass(frozen=True)
class Supplier:
    id: str
    base_price: float                    # per unit, in `currency`
    currency: str                        # "INR" | "USD"
    exposure: tuple[tuple[str, float], ...]   # (series, weight): how unit price indexes to each series

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise InvalidInput("supplier id must be a non-empty string")
        positive(f"supplier {self.id}: base_price", self.base_price)
        if self.currency not in CURRENCIES:
            raise InvalidInput(f"supplier {self.id}: unsupported currency {self.currency!r}; supported: {CURRENCIES}")
        for entry in self.exposure:
            try:
                name, weight = entry
            except (TypeError, ValueError):
                raise InvalidInput(f"supplier {self.id}: exposure entries must be (series, weight) pairs") from None
            if not isinstance(name, str) or not name:
                raise InvalidInput(f"supplier {self.id}: exposure series must be a non-empty string")
            finite(f"supplier {self.id}: exposure weight for {name}", weight)


@dataclass(frozen=True)
class Requirement:
    id: str
    quantity: int
    suppliers: tuple[Supplier, ...]
    fx_series: str = "WB.IND.FX"         # LCU per USD, used to convert USD base prices
    data_class: str = "INTERNAL"         # LOCAL_ONLY decisions must never reach a cloud model
    period_now: int = 2024

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise InvalidInput("requirement id must be a non-empty string")
        positive_int(f"requirement {self.id}: quantity", self.quantity)
        if not self.suppliers:
            raise InvalidInput(f"requirement {self.id}: at least one supplier is required")
        ids = [s.id for s in self.suppliers]
        if len(set(ids)) != len(ids):
            raise InvalidInput(f"requirement {self.id}: supplier ids must be unique")
        if (isinstance(self.period_now, bool) or not isinstance(self.period_now, int)
                or not WINDOW <= self.period_now < PERIOD_LIMIT):
            raise InvalidInput(f"requirement {self.id}: period_now must be an integer in [{WINDOW}, {PERIOD_LIMIT})")

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


def _log_returns(levels: dict[int, float]) -> np.ndarray:
    """One-period log-returns between ADJACENT periods only.

    A missing period is not bridged. The return across a gap spans several periods, and counting it as one
    inflates both the drift and the volatility estimate (a clean 5%/yr series with one missing year would
    otherwise show non-zero volatility).
    """
    periods = sorted(levels)
    if len(periods) < 2:
        return np.empty(0)
    logs = np.log(np.asarray([levels[p] for p in periods], dtype=np.float64))
    adjacent = np.diff(np.asarray(periods)) == 1
    return np.diff(logs)[adjacent]


def compute_decision(req: Requirement, reader, draws: int = 1000, salt: int = 0) -> DecisionResult:
    positive_int("draws", draws)
    names = req.series_used()
    growth, vol, last, flags, complete = {}, {}, {}, set(), True
    for s in names:
        levels: dict[int, float] = {}
        for p in range(req.period_now - WINDOW, req.period_now + 1):
            o = reader.read(s, p)
            if o is None:
                complete = False
                continue
            if o.value <= 0.0:
                # A log-return is undefined at or below zero. Flag it and leave the point out; never hand it to np.log.
                flags.add(f"{s}:invalid_value")
                complete = False
                continue
            levels[p] = o.value
            if o.quality != "ok":
                flags.add(f"{s}:{o.quality}")
        last[s] = levels[max(levels)] if levels else None
        rets = _log_returns(levels)
        if len(rets) < 2:
            growth[s], vol[s] = 0.0, 0.0
            complete = False
            continue
        growth[s], vol[s] = float(rets.mean()), float(rets.std(ddof=1))
    if any(sup.currency == "USD" for sup in req.suppliers) and last[req.fx_series] is None:
        # Converting at an assumed rate would be inventing a market price.
        raise InsufficientData(f"no usable observation of {req.fx_series}: USD-priced suppliers cannot be converted")
    rng = np.random.default_rng(seed_for(req, salt))
    z = rng.standard_normal((draws, len(names)))
    zi = {s: i for i, s in enumerate(names)}
    costs = np.empty((draws, len(req.suppliers)))
    with np.errstate(over="ignore", invalid="ignore"):
        for j, sup in enumerate(req.suppliers):
            base = sup.base_price * (last[req.fx_series] if sup.currency == "USD" else 1.0)
            expo = np.zeros(draws)
            for s, w in sup.exposure:
                expo += w * (growth[s] + vol[s] * z[:, zi[s]])
            if sup.currency == "USD":
                expo += growth[req.fx_series] + vol[req.fx_series] * z[:, zi[req.fx_series]]
            costs[:, j] = req.quantity * base * np.exp(expo)
    if not np.isfinite(costs).all():
        raise InvalidInput(f"requirement {req.id}: non-finite cost (the exposure model overflowed)")
    mean = costs.mean(axis=0)
    order = np.argsort(mean)
    w, r = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
    margin = float((mean[r] - mean[w]) / mean[w]) if len(order) > 1 else 1.0
    p_not_best = float((costs.argmin(axis=1) != w).mean())
    return DecisionResult(w, tuple(float(x) for x in mean), tuple(float(x) for x in np.percentile(costs, 90, axis=0)),
                          margin, p_not_best, tuple(sorted(flags)), complete)
