"""Seeded workload generator + World Bank replay.

DATA CLASSES (never blurred):
  HISTORICAL  the three World Bank series (annual, retrieved snapshot in fixtures/; NOT vintage-aware:
              the provider exposes only the latest value, so revisions in experiments are INJECTED and labelled)
  SYNTHETIC   category index series and every requirement/supplier/price: random but seeded
There is no DELAYED or LIVE data in this repository.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from .procurement import Requirement, Supplier
from .vintage import Observation, VintageStore

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "worldbank_snapshot.json"
FIRST_PERIOD, LAST_PERIOD = 2014, 2024        # window of 10 + current
REAL_SERIES = ("WB.IND.CPI", "WB.USA.CPI", "WB.IND.FX")
T0 = 2025.0                                   # initial knowledge time for all first vintages


def load_worldbank(store: VintageStore, path: Path = FIXTURE) -> dict:
    snap = json.loads(Path(path).read_text())
    for sid, s in snap["series"].items():
        for year, value in s["observations"].items():
            y = int(year)
            if FIRST_PERIOD <= y <= LAST_PERIOD:
                store.append(Observation(sid, y, float(value), known_at=T0, source_id="worldbank.org",
                                         root_id=f"worldbank:{s['indicator']}:{s['country']}", origin="HISTORICAL"))
    return snap


def add_synthetic_series(store: VintageStore, n: int, seed: int, stale_rate: float = 0.02) -> list[str]:
    rng = np.random.default_rng(seed)
    names = []
    for k in range(n):
        name = f"SYN.CAT{k:03d}"
        names.append(name)
        level = 100.0
        drift, vol = rng.normal(0.03, 0.02), abs(rng.normal(0.05, 0.03)) + 0.005
        stale = rng.random() < stale_rate
        for p in range(FIRST_PERIOD, LAST_PERIOD + 1):
            level *= float(np.exp(drift + vol * rng.standard_normal()))
            q = "stale" if (stale and p == LAST_PERIOD) else "ok"
            store.append(Observation(name, p, level, known_at=T0, source_id="synthetic", root_id=f"synthetic:{name}",
                                     quality=q, origin="SYNTHETIC"))
    return names


def build_requirements(n: int, synthetic: list[str], seed: int, repeat_rate: float = 0.30,
                       local_only_rate: float = 0.05, spread: float = 0.10) -> list[Requirement]:
    """Mix: 40% domestic INR, 40% USD imports, 20% mixed. ``repeat_rate`` of requirements are exact
    repeats of an earlier requirement's facts (new id): this is an ASSUMPTION that drives cache hit
    rate and is swept in the sensitivity experiment."""
    rnd = random.Random(seed)
    reqs: list[Requirement] = []
    for i in range(n):
        if reqs and rnd.random() < repeat_rate:
            src = reqs[rnd.randrange(len(reqs))]
            reqs.append(Requirement(f"R{i:06d}", src.quantity, src.suppliers, src.fx_series,
                                    "LOCAL_ONLY" if rnd.random() < local_only_rate else "INTERNAL"))
            continue
        kind = rnd.random()
        cat = rnd.choice(synthetic)
        sups = []
        base = rnd.uniform(500, 50000)
        for j in range(rnd.randint(3, 5)):
            cur = "INR" if kind < 0.4 else "USD" if kind < 0.8 else rnd.choice(["INR", "USD"])
            price = base * rnd.uniform(1 - spread, 1 + spread) / (80 if cur == "USD" else 1)
            expo = [(cat, round(rnd.uniform(0.4, 1.0), 2))]
            expo.append(("WB.IND.CPI", 0.3) if cur == "INR" else ("WB.USA.CPI", 0.3))
            sups.append(Supplier(f"S{j + 1}", round(price, 2), cur, tuple(expo)))
        reqs.append(Requirement(f"R{i:06d}", rnd.choice([10, 50, 100, 300, 1000, 5000]), tuple(sups),
                                data_class="LOCAL_ONLY" if rnd.random() < local_only_rate else "INTERNAL"))
    return reqs


def build_world(n_decisions: int, n_synthetic: int = 197, seed: int = 7, **kw):
    store = VintageStore()
    load_worldbank(store)
    syn = add_synthetic_series(store, n_synthetic, seed)
    return store, build_requirements(n_decisions, syn, seed + 1, **kw), syn
