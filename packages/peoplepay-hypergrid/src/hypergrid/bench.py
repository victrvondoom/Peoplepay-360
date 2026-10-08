"""Matched-baseline experiments. Run:  python -m hypergrid.bench --out results/

What is MEASURED (real code, this machine): numerics wall-clock, worker scaling, invalidation counts,
recompute counts, cache hits, validator outcomes, prompt-size estimates, fault-recovery behaviour.
What is SIMULATED (assumptions, swept in E5): model prices, latencies, accuracies, silent-error share.
Every output row says which. Nothing here is a claim about real LLM providers.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .corpus import LAST_PERIOD, T0, build_world
from .grid import FaultPlan, run_grid
from .incremental import IncrementalEngine
from .procurement import compute_decision
from .routing import (DEFAULT_PROFILES, Config, Router, SimulatedBackend)
from .vintage import Observation

CPU_USD_PER_HOUR = 0.04        # ASSUMPTION: price of one vCPU-hour for infra cost lines


def pct(xs, q):
    return float(np.percentile(xs, q)) if len(xs) else 0.0


def lpt_makespan(durations, workers):
    """Virtual-time makespan of FIFO list scheduling on `workers` identical workers."""
    h = [0.0] * workers
    heapq.heapify(h)
    for d in durations:
        heapq.heappush(h, heapq.heappop(h) + d)
    return max(h)


def env_record():
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        sha = "unknown"
    return {"git_sha": sha, "python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform(),
            "cpu_count": os.cpu_count(), "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# ---------------------------------------------------------------- E1 scaling (MEASURED)
def e1_scaling(n, workers_list, reps, draws):
    store, reqs, _ = build_world(n)
    rows, base = [], None
    for w in workers_list:
        times = []
        for _ in range(reps):
            r = run_grid(store, reqs, list(range(n)), T0 + 0.5, workers=w, draws=draws, chunk=max(50, n // (w * 8)))
            times.append(r.seconds)
        med = statistics.median(times)
        base = base or med
        rows.append({"experiment": "E1_scaling", "kind": "MEASURED", "workers": w, "decisions": n, "median_s": round(med, 3),
                     "min_s": round(min(times), 3), "max_s": round(max(times), 3), "throughput_per_s": round(n / med, 1),
                     "speedup_vs_1": round(base / med, 2), "efficiency": round(base / med / w, 2),
                     "oversubscribed": w > (os.cpu_count() or 1)})
    return rows, base


# ---------------------------------------------------------------- E2 configurations (MEASURED counts + SIMULATED model)
def configs():
    A = Config("A_sequential_single_model", "single_large")
    B = Config("B_parallel_single_model", "single_large")
    C = Config("C_static_routing", "static")
    H = Config("H_hypergrid", "adaptive", "compact", det_first=True, cache=True, validate_escalate=True)
    return A, B, C, H


def run_config(cfg, reqs, results, compute_ms, workers, backend=None, profiles=None, incremental_explained=None, router=None):
    router = router or Router(cfg, backend, profiles)
    lat, cost, in_tok, out_tok, calls_by = [], 0.0, 0, 0, {}
    verified_correct = accepted_wrong = unverified = priv = hits = templates = 0
    idxs = range(len(reqs)) if incremental_explained is None else incremental_explained
    for i in idxs:
        o = router.explain(reqs[i], results[i])
        t = compute_ms / 1000 + sum(c.latency_s for c in o.calls)
        lat.append(t)
        for c in o.calls:
            cost += c.cost; in_tok += c.in_tok; out_tok += c.out_tok
            calls_by[c.model] = calls_by.get(c.model, 0) + 1
        verified_correct += o.correct
        accepted_wrong += (not o.correct)
        unverified += (not o.verified)
        priv += o.privacy_violation
        hits += o.cache_hit
        templates += (o.path == "template")
    n = len(lat)
    infra = n * compute_ms / 1000 * CPU_USD_PER_HOUR / 3600
    total = cost + infra
    return {"config": cfg.name, "tasks": n, "model_calls": sum(calls_by.values()), "calls_by_model": calls_by,
            "input_tokens": in_tok, "output_tokens": out_tok, "cache_hits": hits,
            "cache_hit_rate": round(hits / max(1, router.cache_lookups), 4) if cfg.cache else None,
            "deterministic_template_tasks": templates, "model_cost_usd": round(cost, 4), "infra_cost_usd": round(infra, 4),
            "total_cost_usd": round(total, 4), "correct": verified_correct, "accepted_wrong": accepted_wrong,
            "unverified_outputs": unverified, "privacy_violations": priv,
            "cost_per_verified_correct_usd": round(total / max(1, verified_correct), 6),
            "task_latency_p50_s": round(pct(lat, 50), 3), "task_latency_p95_s": round(pct(lat, 95), 3),
            "task_latency_p99_s": round(pct(lat, 99), 3),
            "makespan_virtual_s": round(lpt_makespan(lat, workers), 2), "workers_virtual": workers,
            "kind": "counts MEASURED; cost/latency SIMULATED (assumed prices, accuracies)"}


def e2_configs(reqs, results, compute_ms, workers, backend=None, profiles=None):
    A, B, C, H = configs()
    rows = [run_config(A, reqs, results, compute_ms, 1, backend, profiles),
            run_config(B, reqs, results, compute_ms, workers, backend, profiles),
            run_config(C, reqs, results, compute_ms, workers, backend, profiles),
            run_config(H, reqs, results, compute_ms, workers, backend, profiles)]
    abl = []
    for field_ in ("det_first", "cache", "validate_escalate"):
        c = replace(H, name=f"H_minus_{field_}", **{field_: False})
        abl.append(run_config(c, reqs, results, compute_ms, workers, backend, profiles))
    abl.append(run_config(replace(H, name="H_minus_compact_prompt", prompt_style="verbose"), reqs, results, compute_ms, workers, backend, profiles))
    # add-one-component-to-baseline-B
    for name, kw in (("B_plus_det_first", dict(mode="single_large", det_first=True)),
                     ("B_plus_cache", dict(mode="single_large", cache=True)),
                     ("B_plus_compact_prompt", dict(mode="single_large", prompt_style="compact")),
                     ("B_plus_adaptive_validate", dict(mode="adaptive", validate_escalate=True))):
        abl.append(run_config(Config(name, **kw), reqs, results, compute_ms, workers, backend, profiles))
    return rows, abl


# ---------------------------------------------------------------- E3 incremental vs full (MEASURED)
def verify_parallel(eng, t, workers):
    rep = run_grid(eng.store, eng.reqs, list(range(len(eng.reqs))), t, workers=workers, draws=eng.draws,
                   chunk=max(50, len(eng.reqs) // (workers * 8)))
    bad = [i for i, (res, _) in rep.results.items() if res != eng.results[i]]
    return not bad, len(bad)


def revise(store, series, period, factor, t_new, source="injected-revision"):
    o = store.as_of(series, period, t_new - 1e-6)
    store.append(Observation(series, period, o.value * factor, known_at=t_new, source_id=source, root_id=o.root_id,
                             quality=o.quality, origin=o.origin))
    return (series, period)


def e3_incremental(n, workers, draws, full_seq_seconds):
    store, reqs, syn = build_world(n)
    eng = IncrementalEngine(store, reqs, draws)
    rep = run_grid(store, reqs, list(range(n)), T0 + 0.5, workers=workers, draws=draws,
                   chunk=max(50, n // (workers * 8)), track=True)
    for i, (res, seen) in rep.results.items():
        eng.install(i, res, seen)
    eng.t = T0 + 0.5
    full_par = rep.seconds
    A, B, C, H = configs()
    compute_ms = full_seq_seconds / n * 1000
    # full sequential recompute timed the SAME way as the incremental path (in-process, with dependency tracking)
    seq_eng = IncrementalEngine(store, reqs, draws)
    full_seq_inproc = seq_eng.full_run(T0 + 0.5)
    del seq_eng
    rows, t = [], T0 + 1.0
    busiest = max(syn, key=lambda s: len(eng.rev.get(store.key(s, LAST_PERIOD), ())))
    scenarios = [
        ("S1 late revision: one synthetic series, latest period +2%", "SYNTHETIC", lambda t: [revise(store, syn[3], LAST_PERIOD, 1.02, t)]),
        ("S2 revision of REAL World Bank India CPI 2024, +1.5% (value INJECTED, series real)", "HISTORICAL+INJECTED", lambda t: [revise(store, "WB.IND.CPI", LAST_PERIOD, 1.015, t)]),
        ("S3 no-op republish: same value, later vintage", "SYNTHETIC", lambda t: [revise(store, syn[10], LAST_PERIOD, 1.0, t)]),
        ("S4 old-period revision (2016) of one synthetic series, +3%", "SYNTHETIC", lambda t: [revise(store, syn[20], 2016, 1.03, t)]),
        ("S5 bulk: five synthetic series revised +1%", "SYNTHETIC", lambda t: [revise(store, syn[30 + k], LAST_PERIOD, 1.01, t) for k in range(5)]),
        ("S6 tiny revision (+0.01%) of the most widely used synthetic series", "SYNTHETIC", lambda t: [revise(store, busiest, LAST_PERIOD, 1.0001, t)]),
        ("S7 revision of REAL World Bank India FX 2024, +2% (INJECTED)", "HISTORICAL+INJECTED", lambda t: [revise(store, "WB.IND.FX", LAST_PERIOD, 1.02, t)]),
    ]
    # one warm router: it has already explained the pre-revision world, as a long-running deployment would have
    # Two independent, identically pre-warmed routers so the full and incremental paths cannot share cache fills.
    warm_full, warm_inc = Router(H), Router(H)
    for i in range(n):
        warm_full.explain(reqs[i], eng.results[i])
    warm_inc.cache = dict(warm_full.cache)
    for name, cls, fn in scenarios:
        revised = fn(t)
        # Parallel-incremental timing: the same stale set recomputed on the grid (dry run, not installed)
        _, stale = eng.stale_candidates(revised, t)
        par_s = None
        if len(stale) >= 50:
            par_s = run_grid(store, reqs, stale, t, workers=workers, draws=draws, chunk=max(20, len(stale) // (workers * 8)),
                             track=True).seconds
        impact = eng.apply_revisions(revised, t)
        ok, bad = verify_parallel(eng, t, workers)
        cold_full = run_config(H, reqs, eng.results, compute_ms, workers)                       # explain everything, empty cache
        warm_full_row = run_config(H, reqs, eng.results, compute_ms, workers, router=warm_full)          # explain everything, warm cache
        inc = run_config(H, reqs, eng.results, compute_ms, workers, incremental_explained=impact.changed_ids, router=warm_inc)
        rows.append({"experiment": "E3_incremental", "kind": "MEASURED (numerics) / SIMULATED (model $)", "scenario": name,
                     "data_class": cls, "decisions": n, "revised_keys": impact.revised_keys, "candidates_by_dependency_index": impact.candidates,
                     "recomputed": impact.recomputed, "summary_changed": impact.summary_changed,
                     "early_cutoff_saved": impact.unchanged_after_recompute,
                     "incremental_compute_s": round(impact.compute_seconds, 4),
                     "incremental_parallel_s": None if par_s is None else round(par_s, 4), "full_recompute_sequential_s": round(full_seq_inproc, 3),
                     "full_recompute_parallel_s": round(full_par, 3),
                     "speedup_vs_full_sequential": round(full_seq_inproc / max(impact.compute_seconds, 1e-6), 1),
                     "recompute_fraction": round(impact.recomputed / n, 5),
                     "exact_vs_full_recompute": ok, "mismatches": bad,
                     "explain_tasks_incremental": impact.summary_changed, "explain_tasks_full": n,
                     "model_calls_incremental_warm_cache": inc["model_calls"],
                     "model_calls_full_reexplain_warm_cache": warm_full_row["model_calls"],
                     "model_calls_full_reexplain_cold_cache": cold_full["model_calls"]})
        t += 1.0
    return rows


# ---------------------------------------------------------------- E4 faults (MEASURED)
def e4_faults(n, workers, draws):
    store, reqs, _ = build_world(n)
    clean = run_grid(store, reqs, list(range(n)), T0 + 0.5, workers=workers, draws=draws, chunk=100)
    rows = []
    for name, plan, budget in (("transient faults on ~20% of chunks, retry budget 2", FaultPlan(0.2, 1, 3), 2),
                               ("persistent faults on ~10% of chunks (5 attempts), retry budget 2", FaultPlan(0.1, 5, 4), 2)):
        r = run_grid(store, reqs, list(range(n)), T0 + 0.5, workers=workers, draws=draws, chunk=100, faults=plan, retry_budget=budget)
        same = all(r.results[i][0] == clean.results[i][0] for i in r.results)
        rows.append({"experiment": "E4_faults", "kind": "MEASURED", "scenario": name, "chunks": r.chunks, "completed": r.completed,
                     "retries": r.retries, "dead_lettered_chunks": len(r.dead_lettered),
                     "decisions_missing": n - len(r.results), "completed_results_identical_to_clean_run": same,
                     "max_in_flight": r.max_in_flight, "in_flight_bound": workers * 2, "seconds": round(r.seconds, 3)})
    import threading
    ev = threading.Event(); ev.set()
    r = run_grid(store, reqs, list(range(n)), T0 + 0.5, workers=workers, draws=draws, chunk=100, cancel=ev)
    rows.append({"experiment": "E4_faults", "kind": "MEASURED", "scenario": "cancelled before submission", "chunks": r.chunks,
                 "completed": r.completed, "cancelled": r.cancelled, "decisions_missing": n - len(r.results)})
    return rows


# ---------------------------------------------------------------- E5 sensitivity (assumption sweeps)
def e5_sensitivity(n, draws, workers):
    out = []
    def one(label, world_kw, backend=None, profiles=None):
        store, reqs, _ = build_world(n, **world_kw)
        rep = run_grid(store, reqs, list(range(n)), T0 + 0.5, workers=workers, draws=draws, chunk=100)
        results = [rep.results[i][0] for i in range(n)]
        hard = sum(r.hard for r in results) / n
        rows, _ = e2_configs(reqs, results, 0.9, workers, backend, profiles)
        by = {r["config"].split("_")[0]: r for r in rows}
        out.append({"experiment": "E5_sensitivity", "kind": "SIMULATED assumptions", "assumption": label, "hard_share": round(hard, 3),
                    **{f"cpvc_{k}": by[k]["cost_per_verified_correct_usd"] for k in "ABCH"},
                    "H_vs_B_cost_ratio": round(by["H"]["cost_per_verified_correct_usd"] / by["B"]["cost_per_verified_correct_usd"], 3),
                    "H_vs_C_cost_ratio": round(by["H"]["cost_per_verified_correct_usd"] / by["C"]["cost_per_verified_correct_usd"], 3),
                    "H_correct_share": round(by["H"]["correct"] / n, 4), "C_correct_share": round(by["C"]["correct"] / n, 4)})
    for rr in (0.0, 0.15, 0.30, 0.60):
        one(f"repeat_rate={rr}", {"repeat_rate": rr})
    for sp in (0.10, 0.25):
        one(f"price_spread=±{int(sp * 100)}%", {"spread": sp})
    for acc in (0.3, 0.55, 0.8):
        one(f"small_model_accuracy_on_hard={acc}", {}, backend=SimulatedBackend(accuracy_override={("small", True): acc}))
    for ss in (0.0, 0.2, 0.5):
        one(f"silent_error_share={ss}", {}, backend=SimulatedBackend(silent_error_share=ss))
    flat = {k: replace(v, price_in=DEFAULT_PROFILES["large"].price_in, price_out=DEFAULT_PROFILES["large"].price_out) if k == "small" else v
            for k, v in DEFAULT_PROFILES.items()}
    one("NO price gap: small model priced like the large one", {}, backend=SimulatedBackend(flat), profiles=flat)
    flatall = {k: replace(v, price_in=DEFAULT_PROFILES["large"].price_in, price_out=DEFAULT_PROFILES["large"].price_out) for k, v in DEFAULT_PROFILES.items()}
    one("NO price gap at all: every model priced like the large one", {}, backend=SimulatedBackend(flatall), profiles=flatall)
    one("validator blind: every model error is silent (share=1.0)", {}, backend=SimulatedBackend(silent_error_share=1.0))
    cheap = {k: replace(v, price_in=v.price_in * 0.25, price_out=v.price_out * 0.25) if k == "large" else v for k, v in DEFAULT_PROFILES.items()}
    one("large_model_price_x0.25 (price gap shrinks)", {}, backend=SimulatedBackend(cheap), profiles=cheap)
    return out


def write_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in r.items()})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", type=int, default=20000)
    ap.add_argument("--sensitivity-decisions", type=int, default=5000)
    ap.add_argument("--workers", default="1,2,4,8")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--virtual-workers", type=int, default=8)
    ap.add_argument("--out", default="results")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    if a.quick:
        a.decisions, a.sensitivity_decisions, a.reps, a.workers = 2000, 1000, 1, "1,2,4"
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    wl = [int(x) for x in a.workers.split(",")]
    best_w = min(max(wl), os.cpu_count() or 1)
    log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    result = {"environment": env_record(), "parameters": vars(a), "labels": {
        "HISTORICAL": "World Bank annual series (3), retrieved snapshot",
        "SYNTHETIC": "all requirements/suppliers/prices and 197 category series",
        "INJECTED": "revisions applied to real series are injected experiments, not observed provider revisions",
        "SIMULATED": "model prices/latency/accuracy are assumptions, not provider measurements",
        "NOT_PRESENT": "no DELAYED or LIVE market data; no real LLM call"}}
    log("E1 scaling"); e1, base = e1_scaling(a.decisions, wl, a.reps, a.draws); result["E1"] = e1
    log("E2 configurations")
    store, reqs, _ = build_world(a.decisions)
    rep = run_grid(store, reqs, list(range(a.decisions)), T0 + 0.5, workers=best_w, draws=a.draws, chunk=100)
    results = [rep.results[i][0] for i in range(a.decisions)]
    compute_ms = base / a.decisions * 1000
    result["workload"] = {"decisions": a.decisions, "hard_share": round(sum(r.hard for r in results) / a.decisions, 3),
                          "local_only_share": round(sum(r.data_class == "LOCAL_ONLY" for r in reqs) / a.decisions, 3),
                          "measured_compute_ms_per_decision_1worker": round(compute_ms, 4)}
    e2, abl = e2_configs(reqs, results, compute_ms, a.virtual_workers); result["E2"], result["E2_ablation"] = e2, abl
    log("E3 incremental"); result["E3"] = e3_incremental(a.decisions, best_w, a.draws, base)
    log("E4 faults"); result["E4"] = e4_faults(min(a.decisions, 5000), best_w, a.draws)
    log("E5 sensitivity"); result["E5"] = e5_sensitivity(a.sensitivity_decisions, a.draws, best_w)
    (out / "results.json").write_text(json.dumps(result, indent=1, default=str))
    for k in ("E1", "E2", "E2_ablation", "E3", "E4", "E5"):
        write_csv(out / f"{k}.csv", result[k])
    log(f"wrote {out}/results.json and CSVs")
    return result


if __name__ == "__main__":
    main()
