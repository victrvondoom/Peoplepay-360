# PeoplePay error review - 2 October 2026

This review covers the root gateway/integration layer and checks available in the five bundled projects. It is not a claim that every possible defect has been eliminated or that live payment/provider flows have been verified.

## Fixed findings

| Finding | Repair | Verification |
|---|---|---|
| PROXY cannot import its workflows: LangGraph nodes collide with `strategy` and `final_report` state keys | Rename internal nodes and their incoming, outgoing and retry edges; retain public state keys | Both workflows collect and execute in the backend suite |
| Gateway accepts non-text consent input after coercion | Require non-empty text for `raw_utterance` | HTTP regression rejects numbers, lists and objects |
| Timeline URL matching permits extra path segments | Match exactly three segments | Real HTTP regressions require 404 for unknown and extra routes |
| NaN/infinite timeouts bypass positive-value validation | Require finite positive timeout values | Three new parameterized regressions |
| Root mypy misses errors inside untyped tests | Correct dynamic handler test typing and narrow optional saved plans | `mypy --check-untyped-defs` passes |
| PROXY tests overwrite checkout datasets | Run relative local stores in a temporary working directory; restore only data modified by this review | Dataset files remain unchanged after test run |
| PROXY tests depend on absent registries and implicit seed content | Supply synthetic test-only registries and explicitly index synthetic retrieval data | Collector and retrieval tests pass without production data |
| PROXY workflow call-count assertions omit the response synthesis call | Update expected counts to include response generation | Both routing tests pass |
| Beacon AWS history typing | Replace dynamic TypedDict indexing with explicit state-entered/state-exited keys; preserve precedence | Strict mypy passes; 156 affected tests pass |
| Beacon lint line length | Wrap the error-response dictionary without changing behavior | Beacon Ruff passes |
| InHeir frozen install rejects stale lockfile | Regenerate lockfile to match the already-declared Next 15.3.8 dependency | Frontend TypeScript passes; frozen reinstall passes |
| Async fixture scope warnings | Set function fixture scope in PROXY and InflationForge | Warning removed |
| Rumi offline typecheck pulls in tests requiring generated bindings | Exclude reconstruction-job and design-UI integration tests from the shared check | Shared typecheck passes; full check remains separate |

Additional recovery: `.gitattributes` now lists the existing 16 LFS dataset paths so hydrated files remain represented by their original pointers in Git. Source assets were recovered without overwriting existing knowledge files.

## Verified checks

| Scope | Result |
|---|---|
| Root `python -m pytest -q` | 225 passed |
| Root Ruff | Passed |
| Root mypy with `--check-untyped-defs` | Passed, 26 files |
| Gateway JavaScript syntax | Passed |
| Beacon frontend TypeScript | Passed |
| InflationForge tests | 18 passed |
| PROXY backend tests | 65 passed after recovery of original corpora and LFS data |
| PROXY frontend TypeScript | Passed |
| InHeir frontend TypeScript | Passed |
| InHeir backend syntax compilation | Passed; no substantive tests; required Python 3.13 runtime unverified |
| Beacon backend tests | 451 passed in `.venv-beacon-review` with pinned image requirements; 14 dependency/metrics warnings |
| Beacon strict mypy | Passed, 52 source files with required AWS stubs installed |
| Beacon affected-test rerun | 156 passed after the final typing/formatting repairs |
| Beacon Ruff and formatting | Passed for src, tests and scripts from `Beacon-main` |
| Beacon CloudFormation lint | Passed for all four templates with the repository-prescribed W1011 exclusion |
| Rumi lint | Passed |
| Rumi shared TypeScript | Passed |
| Rumi offline tests | 385 passed across 32 files |
| Rumi full suite | 438 passed; full TypeScript, lint and shared TypeScript passed |
| Git whitespace check | Passed |

All executed test suites now pass in their documented environments: root 225, Beacon 451, PROXY 65, InflationForge 18 and Rumi 438 (1,197 tests total). InHeir has no substantive backend suite.

Certificate failures initially blocked Python/Bun downloads. Checks used a temporary CA bundle exported from the Windows trusted certificate stores, with TLS verification kept enabled. Rumi dependencies installed from its frozen lockfile. Beacon also used the downloaded tokenizer cache and its local model-cost map. This is local environment setup, not a committed trust configuration.

## Remaining limitations and project cons

1. **Live payments are unavailable.** `/checkout` returns 503. Sandbox orders move no money and contact no merchant. The project does not yet complete a real purchase.
2. **Identity is trusted in local OPEN mode.** `X-Beacon-User` can be supplied by any caller. Loopback binding limits exposure, but production needs verified identity, TLS and a production HTTP server.
3. **Evidence is limited.** Cart prices are self-reported; delivery is manually recorded; disputes are unsubmitted drafts. Provider integrations need real upstream configuration and verification.
4. **Knowledge freshness still needs governance.** Telecom/ecommerce corpora and two health-insurance registries were recovered from upstream commit `a8ccc5c62cd14875f5cd757df6edfc38b2ed55b2`. All 16 LFS datasets were restored from hash-verified local LFS objects. Source recovery establishes provenance, not current regulatory accuracy. See `recovered-corpus-provenance.json` for 341 file hashes.
5. **Dedicated dependency environments are required.** Beacon now passes all 451 tests with its image pins in `.venv-beacon-review`; the shared interpreter still has incompatible versions. The verification environment overlays pinned runtime packages on available development dependencies. A clean production image build was not run.
6. **Live Rumi behavior remains unverified.** Local bindings were generated using the installed CLI offline codegen path, and all 438 tests pass. Live chat/capture still requires owned Convex and Clerk configuration. No backend deployment was created or synced. The new `convex:codegen:offline` command is documented in `rumi-main/convex-workflow.md`.
7. **Scaling is limited.** The gateway serializes mutations with one process-wide lock, including capability calls. Slow upstream requests block other mutations. SQLite and process-local rate limits do not provide a coordinated multi-instance payment service.
8. **Persistence operations need more tooling.** Schema-version-1 databases require migration, but there is no migration framework. Backup, restore, retention and disaster recovery need documented, tested procedures before production use.
9. **Bundled projects complicate maintenance.** Different Python versions, package managers and external services make a single reproducible setup difficult. InHeir backend requires Python 3.13; this review's interpreter is Python 3.12. Its backend has no substantive tests.
10. **Licensing remains unresolved in repository documentation.** No LICENSE/LICENCE files were found outside dependencies in PROXY or Rumi. See `licensing-blockers.md`; this review does not grant or change license terms.

The gateway is usable as a local sandbox. Passing local tests does not establish production payment readiness, live provider correctness or complete upstream project health.
