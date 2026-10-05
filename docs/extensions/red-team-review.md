# ECHO extension integration challenge review

Review date: 5 October 2026. Scope: extension contract/runtime, graph ingestion,
decision lineage, authenticated routes, and gateway draft approval in this
checkout. This is an engineering challenge review, not a penetration test,
formal threat model, legal opinion, or production certification.

## Findings and dispositions

| Challenge | Disposition and evidence |
|---|---|
| Can a provider promote its own claim to an approved decision or mutate arbitrary Cypher? | The contract has bounded typed proposals and allowlisted labels/edges; adapters have no graph client. Core policy, identity, evidence traversal, and decision creation remain in ECHO. Runtime and ingestion adversarial tests cover spoofed producer, permissions, malformed output, cycles, and credential echo. |
| Can repeated observations or another provider make one upstream source look independent? | Canonical source IDs and observation hashes deduplicate the same source/content/time across providers. `OBSERVED` run edges preserve both producers. Controlled cross-extension demo confirms the shared root does not increase independent-root count. Unknown dependency branches block recommendations. |
| Can an expired or changed recommendation be approved using an earlier snapshot? | Approval reevaluates current evidence and compares the decision semantic snapshot, score policy, roots, freshness, and status before creating a gateway draft. Synthetic demo requirements and sources cannot be approved. Changed evidence, ownership, and uncertain create outcomes have regression coverage. |
| Can uncertain gateway creation cause automatic duplicate transactions? | An uncertain response persists `RECONCILIATION_REQUIRED`; retry returns conflict instead of creating another transaction. Confirmed transaction IDs are reused for plan retry. This is conservative, but requires operator reconciliation when the gateway accepted a create and the response was lost. |
| Does body validation cap the bytes read from mutating API requests? | The ASGI boundary now rejects declared oversize and incrementally reads at most 64 KiB plus the first over-limit chunk before returning 413. Regression test sends a 65,537-byte body. Reverse proxy/server limits are still needed for connection-level abuse controls. |
| Are provider timeouts and service origins bounded? | Runtime enforces per-provider concurrency, timeout/circuit state, validated HTTP(S) origins/hosts, fixed reviewed paths, no redirects, response caps, and per-provider secrets. DNS resolution can still occupy a bounded worker; exact host checks are not DNS pinning. |
| Can service manifests load arbitrary code or enable deferred adapters? | YAML is schema-validated; manifests cannot name Python modules or commands. Bootstrap explicitly registers only reviewed adapters. Deferred GreenChain, PROXY, and Rumi manifests cannot activate without a registered adapter. |
| Do the visible controls imply persistent settings or production identity? | No. Runtime toggles and approval locks are process-local; `ECHO_EXTENSIONS` is startup configuration. When the gateway secret is configured, caller identity derives from its signed token. The fallback trusts `X-Beacon-User` and is local-demo only. Multi-worker production needs shared authentication and distributed coordination. |

## Verification recorded

- `ECHO_REQUIRE_GRAPH_TESTS=1 .venv-echo/Scripts/python.exe -m pytest echo/tests -q` — 107 passed against local FalkorDB. A later targeted 65,537-byte body regression also passed.
- `echo.extensions.benchmark` — 15 isolated synthetic graph scenarios; outputs are preserved in `benchmark-results.json`.
- Playwright browser walkthrough — false-consensus demo, cross-extension demo, provider health listing, and extension settings rendered on `127.0.0.1:8090`; after adding the favicon route, page reload had zero console errors or warnings.
- OSV querybatch snapshot — 33 installed ECHO Python packages, zero matching advisory IDs at the recorded scan time. See `dependency-advisories.json`.

## Remaining risks

The builtin adapter trust boundary is code review, not a sandbox. Approval idempotency is process-local and remote uncertainty needs reconciliation. ECHO fallback identity is not production identity; service host checks do not pin DNS; integration tests use a local graph and providers are synthetic or mocked. InflationForge is disabled by default and only its narrow read-only adapter is implemented. No live purchase, external provider accuracy, hidden-copying detection, authentication deployment, multi-worker race test, or public-network penetration test was performed. Supplied briefs did not contain additional repository URLs, so no new upstream repositories were fetched or merged.
