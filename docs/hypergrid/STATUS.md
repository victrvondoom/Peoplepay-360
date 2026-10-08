# STATUS: what is real

Legend: **IMPLEMENTED** code exists · **TESTED** covered by automated tests · **MEASURED** numbers come from running the code here ·
**SIMULATED** result depends on assumed model behaviour · **PROPOSED** design only · **BLOCKED** cannot proceed without something outside this work · **NOT IMPLEMENTED**.

## Brief item → status

| Item | Status | Evidence / note |
|---|---|---|
| Repository forensics, test baseline | IMPLEMENTED, MEASURED | AUDIT.md. Root suite 549 passed / 15 skipped before this work; ECHO suite needs FalkorDB (7 errors without it). |
| Licensing inventory | IMPLEMENTED | AUDIT.md §Licensing. **Path B blocked as stated** (see below). |
| Contest rules verified | **BLOCKED** | Devpost rules page returned HTTP 403. Nothing about eligibility, dates, prizes or criteria was verified. |
| GitLab flow trigger limits | PARTIALLY VERIFIED | GitLab docs confirm user-initiated triggers (mention/assign/review of the flow service account); they do **not** state whether a flow/bot can trigger another flow. The brief's claim is unconfirmed. |
| Bitemporal evidence store | IMPLEMENTED, TESTED | `vintage.py`, `tests/test_vintage_and_incremental.py` |
| Incremental recomputation, early cutoff | IMPLEMENTED, TESTED, MEASURED | exactness vs full recompute in 7 scenarios + randomized sequences + mutation test |
| Worker grid (1 machine) | IMPLEMENTED, TESTED, MEASURED | scaling, backpressure, retries, DLQ, cancellation. **Not distributed**: no multi-host, no work stealing, no autoscaling, no Kubernetes. |
| Cost-aware routing | IMPLEMENTED, TESTED, SIMULATED | model behaviour is a seeded stand-in with assumed prices/accuracy; no real provider called |
| Gateway integration of routing | IMPLEMENTED, TESTED (mock provider only) | `GatewayBackend`; added `strict_selection` to the Model Gateway after a test found silent re-routing |
| Exact-match cache | IMPLEMENTED, TESTED, MEASURED(hit rate) | hit rate depends on the assumed repeat rate |
| Semantic cache, prefix caching, speculative decoding, continuous batching, contextual bandits | **NOT IMPLEMENTED** | prefix caching/batching need a serving stack (vLLM/SGLang) not present |
| Model disagreement / calibrated confidence | NOT IMPLEMENTED | only a deterministic validator exists |
| Real economic data | PARTIAL | 3 World Bank annual series (CC BY 4.0), snapshot replay. **No FRED, no RBI DBIE, no live/delayed market feed.** FRED needs an API key; RBI/DBIE licensing not checked. |
| Vintage-aware real data | NOT AVAILABLE | World Bank API exposes no revisions; revisions in experiments are **injected** and labelled |
| Inflation forecasting, FX/commodity sensitivity, Monte Carlo | PARTIAL | Monte Carlo cost distributions per decision (IMPLEMENTED). Out-of-sample forecasting accuracy: NOT IMPLEMENTED, **no prediction-accuracy claim is made** |
| ECHO / FalkorDB integration | **NOT IMPLEMENTED** | HYPERGRID does not read or write ECHO. See ADR-001. |
| Benchmark at 100,000 transactions | NOT RUN | ran 20,000 (scaling, E2, E3), 5,000 (E4), 5,000 (E5). 10,000 evidence records, 1,000 fault scenarios, 500 policy cases, 100 model-failure scenarios, 50 release-recovery trials: **NOT IMPLEMENTED** |
| Four-configuration comparison | IMPLEMENTED, MEASURED(counts), SIMULATED($, latency, accuracy) | SUMMARY.md E2 + ablation + E5 |
| Energy measurement | NOT IMPLEMENTED | |
| Charts | NOT IMPLEMENTED | raw JSON/CSV and a generated Markdown report only |
| GitLab Duo agents/flows/MCP | **NOT IMPLEMENTED** | no GitLab project or Duo access was available |
| `.gitlab-ci.yml` | IMPLEMENTED, **UNVERIFIED** | never run on a GitLab runner |
| Nine DevSecOps stages | NOT IMPLEMENTED | CI covers verify + secure (GitLab templates, unrun) + a correctness gate only |
| Autonomous incident recovery (detect → patch → MR → deploy → rollback) | **NOT IMPLEMENTED** | the *detection half* exists as a proven mutation test + `hypergrid_gate.py`; nothing diagnoses or patches |
| Google Cloud / Cloud Run deployment | NOT IMPLEMENTED | |
| Public demo / 3-minute story | NOT IMPLEMENTED | the S1 scenario is a real, reproducible command, not a recorded demo |
| Judge evidence matrix | IMPLEMENTED | JUDGE_MATRIX.md, with limitations |

## Licensing: Path B

The repository root has **no LICENSE file**. It aggregates Apache-2.0 (Beacon), MIT (InflationForge, CivicMesh, InHeir), **unlicensed** trees (CONSUMER-main/PROXY, rumi-main), GreenChain (README says MIT, no LICENSE file), and a SSPLv1 container image (FalkorDB). Nobody but the rights holders can declare this aggregate MIT, and no licence was added here. HYPERGRID and the Model Gateway packages are new code with no dependency on the unlicensed trees (HYPERGRID depends on NumPy only) and could be offered under MIT by their author, ideally from a repository containing only that code. Whether the contest's "originally MIT-licensed" requirement is satisfied by that depends on rules that could not be read.

## What would change these statuses

A GitLab project with Duo enabled (flows, MCP), a Google Cloud project, API keys (FRED; a real LLM provider for a live calibration of the simulated model), a running FalkorDB for the ECHO seam, and the contest rules text.
