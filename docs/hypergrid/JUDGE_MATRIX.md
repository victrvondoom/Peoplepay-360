# Judge evidence matrix

Contest criteria are **as named in the brief and unverified** (the rules page returned HTTP 403). Prize eligibility is not assessed beyond the blockers below; the brief itself warns prizes may not combine.

| Criterion (per brief) | Verified feature | Code | Proof artifact | Limitation | Likely objection |
|---|---|---|---|---|---|
| Technological implementation | Exact incremental recomputation; bounded worker grid; deterministic-first/cached/validated routing; mutation-tested correctness gate | `packages/peoplepay-hypergrid/src/hypergrid/*` | 32 tests; `results/SUMMARY.md`; `scripts/hypergrid_gate.py` | single machine; simulated models; in-memory store; not integrated with ECHO | "Where is the distributed system and the real model?" |
| Design | Small, separable mechanisms with explicit data-class labels; honest reporting of quality/tail-latency regressions | docs/hypergrid | ADR-001, STATUS.md | no UI/dashboard for HYPERGRID | "No demo surface" |
| Potential impact | One-series revision recomputes ~0.4% of decisions, exactly; ~24× lower simulated cost per verified output (24.2× in the generated report), and still ~4.8× at equal prices (sweep) | E3/E2/E5 | SUMMARY.md | impact figures rest on synthetic workload and assumed model behaviour | "Synthetic data; no real savings shown" |
| Innovation / idea | Integration of vintage store + early cutoff + cost-gated explanation | ADR-001 | PRIOR_ART.md | not novel as mechanisms | "This is a build system" (accurate) |
| Presentation | Reproducible command and generated report | `python -m hypergrid.bench` | SUMMARY.md | **no 3-minute demo, no deployment** | "Nothing live" |
| GitLab Duo / DevSecOps stages | **None verified.** `.gitlab-ci.yml` written, never run | `.gitlab-ci.yml` | none | NOT IMPLEMENTED: Duo agents/flows/MCP, nine stages, deploy, rollback, incident recovery | "This is a GitHub project with a CI file" (accurate) |

Blockers to any contest entry: GitLab Duo integration is absent; no deployment; Path B licensing is unresolved (STATUS.md §Licensing); rules unread.
