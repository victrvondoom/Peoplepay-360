# Prior art and novelty review

**Method limit.** Only two external pages were fetched during this work (GitLab custom-flow docs; the World Bank API). Everything below about other
projects is from general knowledge and was **not re-verified against current documentation or licences**. Verify before citing.

| Idea in HYPERGRID | Existing practice (from general knowledge) | Classification | What is actually different here | Could something simpler do as well? |
|---|---|---|---|---|
| Dependency-tracked recomputation with early cutoff | Make/Bazel (action caches), Salsa/Adapton (incremental computation), differential dataflow, Dagster asset invalidation | Common engineering practice | Dependencies observed from reads against a knowledge-time store; cutoff gates a paid LLM step | A per-series dirty flag is simpler, but cannot ignore no-op republications or tolerate sub-bucket changes, and over-invalidates (measured: see S3, S4, S6) |
| Vintage / real-time datasets | ALFRED/FRED vintages, point-in-time databases | Common practice in macro-econometrics | Making a snapshot a first-class compute input for decision batches | n/a |
| Small-model-first with verifier and escalation | FrugalGPT, RouteLLM-style cascades, LiteLLM routing | Advanced implementation of a known technique | Verifier is a deterministic check over structured facts; last resort is deterministic text | A cascade without validation is cheaper but measurably less accurate (E2 ablation) |
| Deterministic-first | Rules/templates before ML | Common practice | none | this *is* the simple solution |
| Exact-match cache on structured facts | Standard | Common practice | cache key built from facts, segregated by data class | n/a |
| Bounded worker pool, retries, DLQ | Celery, Temporal, Ray | Common practice | none; deliberately small | Ray/Temporal would add capability (multi-host, durable workflows) and operating weight |
| Provenance-root de-duplication | Citation/lineage graphs | Pre-existing in ECHO | not reimplemented here | |

**Verdict.** No research novelty is claimed. The defensible contribution is an *integration* and a *measured, assumption-swept evaluation* that reports quality and tail latency next to cost.
Features that should be removed if time is short: nothing in the package is speculative, but `GatewayBackend` is only mock-tested and the `incremental_parallel` path only pays off above ~2,000 stale decisions.

**Strongest counter-arguments.** (1) The headline cost ratio is driven by assumed prices/accuracies; (2) the simulated model errors are shaped to be partly detectable; (3) the corpus is synthetic and its price spread sets the hard share; (4) one-machine scaling says nothing about cluster behaviour; (5) a warm cache already captures most model-call savings of incremental recomputation.
**What would disprove the claims.** A live calibration where real small-model explanations pass the validator while being wrong at a rate well above the assumed 20% of errors; a corpus where most decisions read one hot series.
