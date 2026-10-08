# ADR-001: Dependency-tracked incremental recomputation over a bitemporal evidence store

Status: accepted for the vertical slice. Scope: what was built and measured here, not the full HYPERGRID vision.

## Hidden problem

When economic evidence is revised after decisions were made from it, a decision system either recomputes everything, ignores the revision, or re-explains everything with a paid model.

What ECHO already does (corrected after a first draft of this ADR wrongly said otherwise; verified by reading `echo/api.py:229-258`, `echo/graph_store.py:265`, `echo/queries/06_impacted_decisions.cypher`, `echo/queries/01_claim_support.cypher`):

* **Source-level invalidation with revaluation.** `POST /echo/sources/{id}/invalidate` marks a source inactive, finds decisions that used it (`06_impacted_decisions.cypher`), flags them `evidence_stale`, and calls `engine.analyze_requirement` for each.
* **Temporal filtering.** Evidence queries take `$as_of` and filter on `valid_from`, `valid_until` and `observed_at`.

What it does not do (read from code; NOT run here because ECHO needs a live FalkorDB):

* Granularity is the *source*, not the (series, period) observation, and there is no value fingerprint, so a republished identical value or a sub-tolerance change still triggers full revaluation of every dependent decision.
* No early cutoff: every revaluation proceeds regardless of whether the conclusion changed, so any downstream paid work would repeat.
* No revision history for numeric observations (knowledge-time vintages), so a batch cannot be replayed "as known at time T".
* Revaluations run sequentially inside the HTTP request handler, so invalidating a widely used source does N analyses in one request (a hazard by inspection, not measured).

Also absent: the Model Gateway (previous change) had no pricing-aware ranking, result cache or deterministic-first path.

## Root cause, bottleneck, mechanism

Root cause: dependencies between observations and decisions are implicit. Bottleneck: full recomputation scales with decision count, not with the number of revisions; and paid explanation work is repeated for unchanged conclusions.
Mechanism: (1) bitemporal (knowledge-time) store + snapshots; (2) observed-dependency tracking and a reverse index; (3) fingerprint check so a republished identical value invalidates nothing; (4) early cutoff on a coarse recommendation summary, gating the explanation step; (5) exactness check against full recomputation, used as a CI gate and proven by a mutation test to fail when invalidation is broken.

## Not novel

This is the incremental-computation idea behind Make/Bazel, Salsa, Adapton and differential dataflow, and "vintage" data is standard in macroeconomics (ALFRED). Cascade routing with a verifier is established (FrugalGPT, RouteLLM style). The contribution here is the *integration* and the measurement, not the mechanisms. Prior-art notes in PRIOR_ART.md were written from general knowledge and not re-verified against current documentation during this work.

## Why not the alternatives (for this slice)

Dagster/Prefect/Temporal/Flink/Ray/vLLM/KEDA solve orchestration, streaming, serving and autoscaling problems that this slice does not have yet. None was integrated or benchmarked; choosing one now would add operating weight without a measured bottleneck. The measured bottleneck on one machine was CPU-bound numerics, scaling linearly to the core count.

## Expected vs measured (full numbers: results/SUMMARY.md)

* Expected: recompute fraction ≈ fraction of decisions reading the revised series. Measured: matches (82 of 20,000 for one rarely used series; 59% for the India CPI series).
* Expected: large speedup for narrow revisions. Measured: ~250× vs full sequential recomputation for a single rarely used series; ~1.7× for a ubiquitous one. Sequential incremental can be *slower* than a 4-worker full recompute for broad revisions, so the engine can run its stale set on the grid.
* Expected: early cutoff saves explanation work. Measured: yes, relative to re-explaining with a warm cache (e.g. 2,433 vs 5,502 model calls for the India CPI revision), at the price of tolerating explanations that are stale within the 0.1% cost bucket.
* Not expected, found: with a warm cache, most of the model-call saving of incremental recomputation is already provided by the cache; incremental's main win is numerics compute.

## Hackathon requirements

Not satisfied by this ADR's scope: GitLab Duo agent/flow automation (NOT IMPLEMENTED), public deployment (NOT IMPLEMENTED), MIT licensing for Path B (BLOCKED, see STATUS.md). The contest rules page could not be fetched (HTTP 403), so no eligibility claim is made.

## Integration status with ECHO: NOT IMPLEMENTED

HYPERGRID uses its own in-memory `VintageStore`. It is not connected to ECHO/FalkorDB, and no HYPERGRID result has been written into the ECHO graph. The intended seam is ECHO's invalidation endpoint: HYPERGRID computes the observation-level stale set and ECHO records provenance and revaluation. That seam is a proposal only.
