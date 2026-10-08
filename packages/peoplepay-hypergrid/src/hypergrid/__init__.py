"""PeoplePay HYPERGRID: do less work, prove it.

* vintage      - bitemporal (knowledge-time) observation store with revisions
* procurement  - deterministic + Monte Carlo procurement decision numerics
* incremental  - dependency-tracked recomputation with early cutoff
* grid         - bounded multiprocessing worker pool (backpressure, retries, DLQ)
* routing      - deterministic-first, cache-first, cost-aware model routing
* corpus       - seeded synthetic workload + real World Bank replay
* bench        - matched-baseline experiments; raw JSON/CSV out
"""
