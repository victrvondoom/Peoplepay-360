# HYPERGRID

Evidence-aware incremental computation, a bounded worker grid and cost-aware model routing, with a benchmark harness that reports quality and tail latency
next to cost. Package: `packages/peoplepay-hypergrid`. Generated results: `packages/peoplepay-hypergrid/results/SUMMARY.md` (every number there is rendered from `results.json`).

**Read [STATUS.md](STATUS.md) first.** It lists, item by item, what is implemented, tested, measured, simulated, not implemented and blocked.

## What it is

* **`vintage`**: a knowledge-time observation store (ECHO already filters by valid/observed time; this adds revision history for numeric observations). Revisions are new records with a later *knowledge time*; reads happen against a snapshot pinned to one knowledge time, so a batch of decisions sees one consistent world.
* **`procurement`**: deterministic statistics plus seeded Monte Carlo (NumPy). No language model.
* **`incremental`**: dependencies are *observed* (every read is tracked), a reverse index finds affected decisions, a fingerprint check ignores no-op republications, and an *early cutoff* on a coarse recommendation summary decides whether the paid explanation step must run again. `verify_against_full` proves exactness against a from-scratch recompute.
* **`grid`**: a bounded `ProcessPoolExecutor` grid: backpressure, microbatching, idempotent chunks, retry budget, dead-letter queue, cancellation, fault injection. One machine; not a distributed cluster.
* **`routing`**: deterministic-first (templated explanation when the decision is not hard), exact-match cache keyed on the structured facts, compact structured context, cheapest-expected-verified-cost model ordering, a deterministic validator, escalation, and a deterministic last resort. `GatewayBackend` drives the real PeoplePay Model Gateway; local-only work is sent as RESTRICTED so the Gateway independently refuses cloud routes.
* **`bench`**: matched baselines A (sequential single model), B (parallel single model), C (static routing), H (HYPERGRID), ablations, scaling, incremental-vs-full, faults, sensitivity.

## Run

```bash
pip install -e packages/peoplepay-hypergrid
python -m hypergrid.bench --out results          # full default run, about 4 minutes on 4 cores
python -m hypergrid.bench --quick --out /tmp/q   # seconds
python scripts/hypergrid_report.py results/results.json
python scripts/hypergrid_gate.py results/results.json   # CI correctness gate
python -m pytest packages/peoplepay-hypergrid/tests
```

## What the evidence supports

See `SUMMARY.md`. In one paragraph: worker scaling is real up to the CPU count and flat beyond it; incremental recomputation is bit-exact and recomputes a tiny fraction when a rarely used series is revised, but gains collapse when a ubiquitous series (here the India CPI or FX series) is revised; the large cost reductions in the four-way comparison are real *given the assumed prices and accuracies* and survive a no-price-gap sweep at a smaller size, but quality drops against a single large model and tail latency worsens; and the result depends heavily on how well a deterministic validator catches real-model errors, which this repository cannot measure.

## What this is not

Not a distributed cluster, not a live market-data system, not a measurement of any real LLM provider, not GitLab Duo automation, not deployed. See STATUS.md.
