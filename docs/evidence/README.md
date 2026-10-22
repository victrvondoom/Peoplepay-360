# External demo evidence and submission boundary

Audit baseline: `7b31271379839364cfe3fcf0f1c7d4982dee6b80` (October 15, 2026),
confirmed as default-branch HEAD on October 22. PR #2 was merged October 8;
it is not the complete current tree. Later platform modules and regression
coverage do not turn simulated benchmarks into live measurements.

The canonical [claims.json](claims.json) generates [CLAIMS.md](CLAIMS.md).
[OFFLINE_RUN.json](OFFLINE_RUN.json) records checks from this audit. Historical
reports preserve their original results; their counts are not current reruns.

## Labels

| Label | Meaning |
|---|---|
| measured | Local execution or recorded numerical measurement, within its stated workload/environment |
| simulated | Depends on injected data or assumed model behavior, prices, latency or accuracy |
| mock-verified | Real application code exercised with fixture providers, fake transport, callbacks or sandbox money |
| live-verified | Actual named external service exercised with recorded environment/date/outcome; none established here |
| unverified | Missing execution evidence, incomplete integration or not implemented; boundary states which |
| blocked | Requires credentials, rights, rules access or another external prerequisite |

These labels are not an ordered maturity scale. A sandbox test is a measured
execution of a mock boundary; it does not verify actual payment settlement.
Source links identify inspectable evidence, not independently certified truth.

## One centralized offline workflow

Requires Python 3.11+; install in a virtual environment from the repository root:

```sh
python -m pip install pytest pytest-asyncio numpy pydantic cryptography httpx PyYAML
python scripts/demo_evidence.py --out demo-evidence.json
python scripts/demo_evidence.py --check
```

The command validates claim labels and paths, runs the HYPERGRID, Model Gateway,
sandbox-payment and runtime/workflow unit suites plus evidence regression tests,
then demonstrates a single evidence-revision pipeline: pinned historical and
synthetic inputs → dependency-tracked decisions → adaptive explanation routing
→ injected revision → recompute impacted decisions → re-explain changed summaries
→ exact comparison with full recomputation → content-bound receipt.

This implementation reuses existing engines rather than creating another
transaction authority. Its contribution is centralized reproducibility and
explicit claim boundaries. It makes no research-priority or scientific-novelty
claim. Runtime services and all specialist journeys are not thereby centralized.
No credentials, real models, real payments, graph service or deployment are used.
No payment HTTP handler is exposed by this command.

The receipt contains UTC time, HEAD at execution, Python version, per-file SHA256,
JUnit counts, simulated call counts, revision impact and exactness results. A
nonzero check, a demo exception or source changes during the run exits nonzero.
`--check` only checks manifest/table consistency. Neither mode certifies live
providers. The runner refuses to attest a `live-verified` label offline. A skipped
live test remains skipped. Hashes detect content changes; they are not signatures.
The run may precede the commit containing its own receipt; compare the recorded
source hashes, not only the recorded HEAD. Regenerate after code changes.

## Smallest changes for an honest demo

1. Use the claim table as the external claim index. Label dollar savings, model
   accuracy and model p95 as simulated wherever quoted; include the quality/tail
   tradeoff. Preserve historical benchmark provenance instead of silently
   replacing the 20k run with a quick run.
2. Demonstrate the offline revision workflow above. Describe it as an advisory,
   synthetic procurement experiment with historical World Bank snapshots. Model
   validation can accept unsupported qualitative claims; show both validator
   acceptance and synthetic-oracle correctness. Do not say verified = correct.
3. Show existing procurement/assistance only after separately running their
   graph/native-service acceptance tests. Generic ECHO/Gateway callbacks and
   specialist runtime migration remain incomplete; no full-platform claim.
4. Exclude payment HTTP from the demo. Before enabling it, add endpoint tests
   for checkout/webhook dispatch, serialization, unauthenticated requests,
   cross-owner get/list/capture/refund/cancel/checkout denial, server-side
   approval binding, request-body tampering and idempotent replay. Fix the
   shadowed checkout branch and unreachable webhook predicate. A service unit
   test or syntax check does not prove HTTP authorization.
5. Before any live claim, run opt-in provider tests against a named model,
   retain sanitized request/response IDs and measured timings/usage, represent
   missing prices as unknown, and record failures. Provider estimates are not
   billing evidence. Deployment needs a separate health/auth/restart smoke test.
6. Resolve aggregate licensing and read the actual contest rules before
   distributing bundled specialist code or asserting contest eligibility.

## Documentation corrections

`IMPLEMENTATION_STATUS.md` says payments are production-ready yet calls Gateway
integration unfinished. Current `gateway/app.py` contains dispatch code, and
`FINAL_INTEGRATION_REPORT.txt` says integration is complete but explicitly leaves
HTTP integration tests pending. Inspection shows reachable service code does not
prove all endpoints work or protect owner data. `FINAL_DELIVERY_REPORT.md` says all
components are working while the runtime report explicitly lists disconnected
callbacks and separate domain coordinators. Notices on historical reports now
point here; their original counts are retained only as historical observations.

## Honest submission wording

“PeoplePay demonstrates dependency-tracked procurement recomputation and
privacy-aware explanation routing in an offline, synthetic workload. Incremental
numerics are checked against full recomputation. LLM cost, latency and quality
comparisons use simulated assumptions. Model Gateway adapters are contract/mock
tested; no provider is live-certified. Sandbox money never settles. HYPERGRID's
ECHO seam, generic action callbacks and production deployment remain incomplete.”
