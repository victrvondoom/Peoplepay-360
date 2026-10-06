# PeoplePay error remediation — 6 October 2026

## Outcome

The reference Unified Journey completes requirement → native-output adapters →
SDK normalization → ECHO/FalkorDB → exact human approval → Gateway → merchant
checkout/order → final delivery discrepancy → preserved PROXY draft. This pass
repairs recovery and validation errors and provides repeatable isolated setups.
The Extension SDK remains version 1.0.0. Original projects and routes are retained.

## Findings and fixes

| Finding / reproduction | Cause and repair | Verification |
|---|---|---|
| An order commits, then Gateway's journey checkpoint fails | Lookup the merchant's durable order by actor and transaction; reconcile only an exact approved decision/version/hash/terms and completed checkout | Fault injection after merchant commit; approval retry with ECHO offline; refresh preserves approved v1 while evaluating v2 |
| Replaying recovery can duplicate audit events | Deduplicate matching ledger event kind and detail | One authorization and one checkout event after interrupted-order recovery |
| A renewed ECHO decision has a new decision ID | Checkout update incorrectly required the old ID; allow the new ID only with a higher version and unchanged actor/transaction | Repriced v2 checkout completes; another actor or transaction is rejected |
| Completed-order retries bypass strict approval fields | Validate exact keys, integer version, SHA-256 digest and explicit confirmations before replay | Boolean versions, extra fields, bad digests and different terms are refused |
| Missing native PROXY configuration traps a retained discrepancy | Separate configuration checks from external handoff; persist the bundle and expose an owner-scoped safe retry | HTTP retry rejects another owner and evidence overrides; the retained hash is unchanged; no extra delivery event |
| An ambiguous native case request could be repeated | Retain handoff/reconciliation state and any known case ID; prohibit another automatic external call | Failed external handoff invoked once across delivery and draft retries |
| Error screens keep stale journey state | Reload the selected saved record after an operation fails; show draft pending and disable final delivery input | Browser: incomplete configuration retains the draft bundle and displays its safe retry button |
| ECHO outage/nonobject or invalid UTF-8 response escapes the expected boundary | Validate bounded response objects and classify unreadable responses as unavailability | HTTP malformed-response tests; browser retains order and approval through ECHO outage/restart |
| Missing or conflicting sustainability scores can influence selection | Preserve unavailable scores as null; require matching supported claims when sustainability is prioritized | Real graph tests for absent, boolean, out-of-scale, enormous or conflicting scores; UI handles null scores |
| Duplicate supplier domains silently pick the first representation | Treat duplicate supplier matches as ambiguous and ineligible | Real graph ambiguity regression |
| Malformed second-provider proposals partially ingest the first | Normalize and validate both receipts, reviewed versions and shipment context before graph mutation | Real graph count remains unchanged for malformed claims, wrong versions, modes, products and quantities |
| SDK claim/estimate shape and support links are weakly checked | Reject invalid proposal lists, claim subjects/kinds, missing estimate identity and missing/duplicate evidence links | 24 evidence recovery tests, including native provider context and timestamp checks |
| Price receipts can obscure historical or invalid source time | Require unique item/observation identity, snapshot retrieval time, known kind and matching year; label future, stale and archived observations | Duplicate identity, missing time, year/kind and future/historical price regressions; no invented merchant quote |
| Corrupted historical decision/approval or graph outage returns an uncontrolled error | Check snapshot identity/hash and stored approval equality; return sanitized conflict/unavailability responses | Real graph tampering and all four journey route outage tests |
| Dispute bundle/native response can carry inconsistent authority | Bind requirement, selected supplier, approved decision, terms, transaction/order and final delivery arithmetic; validate native owner, case ID, open status, document ID and draft state | Checkout/PROXY hardening tests reject mismatched authority, submitted/foreign analyses, duplicate JSON keys, nonfinite values, surrogate text and nesting beyond 12 levels |
| Shared Python dependencies conflict | Add clean Gateway and native GreenChain development requirement files; keep ECHO separately pinned; restore Beacon's declared agent pins in its existing review overlay | Gateway, ECHO and GreenChain isolated environments each pass `pip check`; native ML assets load |
| ECHO contract and TestClient emit compatibility warnings | Preserve public `model_provenance` with a narrower protected namespace; install declared HTTPX2 TestClient dependency | Root and ECHO suites pass without these warnings |
| PROXY auth test passes only after another test creates its local folder | Collection constructs the singleton before the temporary working-directory fixture; bind the singleton's store/caches inside the isolated fixture | Auth file alone: 4 passed; complete PROXY suite: 65 passed |
| Broader ECHO typing check reports 35 errors | Correct optional execution narrowing, context types, literal error-code annotations, typed demo data, inventory script variables and YAML stubs | Mypy with `--check-untyped-defs`: 77 source files pass, including all ECHO code/tests/scripts |

## Verification matrix

These are local results, not proof of hosted services or live payments.

| Scope | Command / environment | Result |
|---|---|---|
| Root integration + Extension SDK | `.venv-journey-review`, `pytest -q`, `REQUIRE_JOURNEY_GRAPH=1`, `REQUIRE_NATIVE_CAPTURE=1` | **373 passed; no skips** |
| ECHO, real FalkorDB | `.venv-echo`, `pytest -q echo/tests`, required journey graph | **131 passed; no skips** |
| Beacon backend | `.venv-beacon-review`, declared agent pins and local model-cost map | **451 passed** |
| GreenChain backend | `.venv-greenchain-review`, native declared ML requirements, `pytest -q backend/tests` from its app root | **54 passed** |
| InflationForge | Its existing runtime, `pytest -q` from its app root | **18 passed** |
| PROXY backend | Existing runtime, `pytest -q` from `CONSUMER-main` | **65 passed** |
| Rumi | `bun run typecheck`, `bun run lint`, `bun test` | **Passed; 438 tests** |
| GreenChain frontend | Frozen npm installation, `npm run typecheck`, `npm run lint` | Passed |
| Beacon frontend | `npm run typecheck` | Passed |
| PROXY frontend | Local TypeScript, `tsc --noEmit` | Passed |
| InHeir frontend | Frozen Bun installation, local TypeScript, `tsc --noEmit` | Passed |
| Root, SDK and ECHO static checks | Ruff; mypy with `--check-untyped-defs`; both Gateway JS syntax checks | Passed; **77 files** type checked |
| Dependency consistency | `pip check` in Gateway, ECHO and GreenChain clean environments | No broken requirements |
| ECHO inventory / advisory refresh | `echo/scripts/refresh_supply_chain.py` in `.venv-echo` | **37 packages**, no matching OSV advisory IDs at scan time |
| Preservation | `scripts/verify_zero_deletion.py` | All **1,945 baseline paths** retained |
| LFS | `git lfs fsck` | Passed |

The executed suites contain **1,530 passing tests**. Beacon's overlay retains
14 dependency/metrics warnings; native GreenChain retains one upstream
Starlette/AnyIO deprecation warning; PROXY retains one upstream multipart
deprecation warning. These are not failed tests. Frozen frontend installs
changed no lockfiles. The global Python environment still has unrelated
cross-project conflicts; it is not the supported combined Gateway setup.

### Browser proof

Playwright completed the 300-chair preset, compared A/B/C, selected B at
INR 17,70,000, created the reference checkout/order, recorded 260/300 delivered
and received the automatic 40-chair dispute draft. Historical explanation
continued to use approval version 1 after evidence refresh.

Fault injection stopped only the local ECHO preview process. The portal retained
the approved order, showed bounded unavailability, kept delivery disabled after
its final event and recovered after restarting ECHO with the same graph. A
second reference journey with incomplete native PROXY configuration visibly
retained its bundle and enabled **Retry preserved dispute draft**. Restoring
the reference configuration and clicking retry completed that retained draft
after a Gateway restart. No new delivery event was requested.

Expected HTTP 503 console entries occurred during deliberate outages. A fresh
page load had zero console errors/warnings. At a 390-pixel viewport, document
width stayed 390; the comparison table scrolls inside its card. Browser artifacts
remain local under ignored `output/playwright/`.

## Remaining limits

- Merchant checkout, order references and recorded delivery are reference
  simulation. No PSP, live payment, courier webhook or complaint submission ran.
- GreenChain capture exercises the preserved native scoring implementation on
  explicitly synthetic supplier inputs. Real supplier discovery/certification
  requires configured upstream services and source verification.
- InflationForge does not track ergonomic chairs. The chair price is the
  merchant simulator's authoritative quote; no INR conversion or chair price
  observation was invented.
- Native PROXY contract tests use controlled endpoint responses. Real case
  persistence, session mapping, LLM drafting and filing need configured services.
  An ambiguous external case requires operator reconciliation; automated native
  reconciliation is not implemented.
- OPEN identity is loopback development only. Enterprise identity, distributed
  authorization, migration/backup tooling and multi-instance coordination remain
  production work. Live Rumi/Convex/Clerk was not deployed.
- InHeir backend requires Python 3.13 and has no substantive test suite; its
  configured native runtime remains unverified. Its frontend type check passed.
- License and legal-content freshness limits in the earlier review remain.
  The ECHO OSV snapshot covers this Python environment at one time, not the full
  repository, containers, datasets, browser dependencies or future advisories.

Specialist agents contributed the recovery, commerce and evidence findings.
Their final independent review sessions could not run because their authentication
tokens were revoked. The primary agent completed the fixes, regression matrix
and browser fault injection directly; no completed independent final review is
claimed.

Installation and operation: [Unified Journey guide](unified-journey-v1.md).
