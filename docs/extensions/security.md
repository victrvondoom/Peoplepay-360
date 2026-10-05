# Implemented ECHO extension security boundary

This document describes the controls present in the checkout. It is not a
vulnerability audit or a claim that third-party code is sandboxed.

## Authority and code loading

Only ECHO core writes canonical graph data, scores decisions, and controls
approval and transaction lineage. Adapters return typed proposals. They
receive neither a FalkorDB client nor arbitrary Cypher access through the
extension contract. The schema has no decision, approval, transaction,
deletion, executable, module, or install-command field.

The manifest directory is selected by core bootstrap code. The loader uses
safe YAML parsing, typed validation with unknown fields rejected, a 32 KiB
per-file limit, a 64-extension limit, one directory level, directory/ID
agreement, and containment checks that reject escaping symlinks. A manifest
does not import its own Python code. Core bootstrap explicitly attaches
reviewed first-party adapter objects. Dependencies must be registered,
noncyclic, enabled, and attached before execution.

Builtin adapters execute in ECHO's Python process and can access whatever that
process can access if their code is changed. Manifest permissions are
validation policy, not an OS security boundary. Unreviewed code must remain
outside that process. Service mode preserves runtime separation, but the
platform does not install a container sandbox, restrict the service's own
filesystem or network, or remove its upstream mutation APIs. The operator
must isolate those services separately.

## Input and graph proposal control

Requests use API v1 schemas, bounded IDs, JSON values only, a 64 KiB serialized
limit, depth 12, bounded strings and keys, and at most 100 array elements.
Credential-bearing field names and nonfinite numbers are rejected. The API
must also control raw HTTP body size before parsing; typed validation alone
does not bound the body bytes received by the web server.

Normalized results have a 256 KiB serialized limit, at most 100 records in
each collection, and 30 warnings. Unknown fields, duplicate references,
dangling source/claim/entity references, cyclic source dependency proposals,
invalid temporal bounds, and timezone-free timestamps are rejected. Result
producer ID and version must match the reviewed manifest. Runtime and
ingestion compare proposed labels with `graph.write`; this is permission to
propose records, never permission to mutate the graph independently.

Known provenance requires source identity and an explicit observation time.
Unsupported metadata remains `PROVENANCE_UNKNOWN`; estimates and model
outputs retain their kind. Producer reliability and source reliability are
separate. Exact domain identifiers can join supplier representations, but
that matching does not verify domain ownership. Display names do not become
canonical suppliers. Core graph traversal still evaluates shared sources
across adapters.

Ingestion validates owned requirement context and binds an idempotency event
to extension version, requirement, and request ID. Different input under a
previous request ID is rejected. The present in-process ingestion lock is not
cross-process coordination; run one API worker until a distributed claim or
transactional coordination mechanism exists.

## Service egress and credential handling

Reviewed adapters select a fixed service path and GET or POST method. The URL
comes from a manifest-named operator environment variable, with exact hostname
allowlisting. HTTP(S) is required. User information, query, fragment, invalid
port, control characters, network paths, and traversal are rejected where
checked by the transport. Redirects are never followed. A source URL in
evidence is recorded as provenance; this transport does not fetch it.

Exact hostname checks are not a DNS pinning or DNS rebinding defense. The
operator controls the allowlist and URL configuration. Configure trusted
loopback services or trusted service DNS, and enforce egress at the container
or network level if a service must contact external origins. Do not add broad
hostnames merely to make a failing request succeed.

Only the dedicated `runtime.auth_secret_env` bearer credential is used for
service authentication, and it must appear in the manifest's `secrets` list.
No global environment dump or ECHO API credential is sent to the service.
Transport rejects credential-bearing JSON keys and an echoed bearer value;
runtime also rejects declared secrets found in decoded result strings. These
checks cover the declared credential values and conventional field names;
they are not a universal detector for every possible secret. Adapters must
avoid logging requests, raw upstream bodies, and exception text containing
credentials.

Core error messages are fixed strings. Arbitrary adapter exception text,
upstream response bodies, endpoint credentials, and unrecognized error codes
cannot escape through runtime errors. Health responses expose a core-owned
message rather than arbitrary upstream text.

## Failure isolation and resource limits

The runtime caps parallel executions per provider, includes queue time in the
execution deadline, cancels timed-out cooperative adapters, and isolates
failures as structured errors. Manifest configuration limits are:

| Control | Default | Allowed range |
|---|---:|---:|
| Timeout | 8 seconds | 0.01–60 seconds |
| Concurrent executions | 2 | 1–16 |
| Failures before circuit opens | 3 | 1–20 |
| Circuit cooldown | 30 seconds | 0.01–3600 seconds |

Provider priority gives an explicit fallback order. All-provider collection
is concurrent and does not treat provider count as independent evidence.
Disabled or missing providers degrade to structured failure; they do not
create canonical recommendations by themselves. Retained runtime observations
cover the most recent 100 runs; this in-memory view is not a durable audit
store. Ingested run provenance is persisted in FalkorDB.

The service transport also caps actual worker threads per extension. Coroutine
cancellation and a deadline timer interrupt the active socket. A cancelled
operation cannot implicitly reconnect and send a late HTTP request. Worker
capacity is retained until the underlying worker exits. An OS DNS lookup may
outlive the deadline because Python cannot force the resolver to stop; that
worker occupies its slot, and repeated calls receive `RATE_LIMITED` rather
than accumulating more active workers. This is tested with a blocked resolver.

Service responses require JSON, explicit object or array shape, bounded
content length and bytes read, and no compression. HTTP authentication errors,
rate limits, redirects, unsuccessful status, incomplete bodies, malformed
JSON, and oversized responses produce static structured failures. A reviewed
adapter can make multiple service calls within one runtime execution; the
runtime deadline bounds the whole cooperative adapter call.

An async builtin adapter that blocks the event loop or suppresses cancellation
can defeat cooperative runtime timing. Review it before activation; use a
separate service for potentially blocking or untrusted workloads. There is
no automatic subprocess runner or arbitrary upstream library loader.

## Activation and operational limits

External services are disabled by default. `ECHO_EXTENSIONS` is an explicit
comma separated replacement for manifest defaults; an empty value disables
all providers. Runtime toggles affect the current process only. The registry
reports readiness from validated service configuration, adapter availability,
dependency availability, and enabled status. Health and circuit status do not
certify evidence truth.

The included InflationForge adapter reads scoped city/item receipts and
health; it does not call snapshot creation, location mutation, or purchase
endpoints. Historical dates and absent source capture metadata are surfaced.
GreenChain, PROXY, and Rumi remain deferred for the activation blockers in
the intake dossier. No unlicensed source was imported into the ECHO adapter
platform.

The FalkorDB compose service is published only on loopback. Binding ECHO or
another specialist service to a public interface requires a separate deployment
assessment for user identity, tenant isolation, transport security, raw body
limits, rate controls, and the upstream service's own routes. A control API
bearer token is not proof of an authenticated end user's identity.

## Verification and supply chain record

`echo/tests/test_extension_runtime.py` exercises disabled-provider isolation,
timeout fallback and circuits, concurrency, schema rejection, producer spoof,
graph permissions, credential echo, safe errors, dependency toggles, manifest
loading, host/path restrictions, redirects, auth/rate errors, oversized
responses, array mode, and resolver cancellation. Graph integration tests use
disposable graph names and must be required with
`ECHO_REQUIRE_GRAPH_TESTS=1` for release evidence.

[sbom.json](sbom.json) records the inspected ECHO Python environment,
installed distribution metadata, and local license file hashes.
[dependency-advisories.json](dependency-advisories.json) is an OSV querybatch
snapshot for those package versions. The 2026-10-05 refresh found no matching
advisory IDs across its 33 listed distributions after pytest, pytest-asyncio,
FastAPI, and Starlette were upgraded in the isolated ECHO environment. Refresh
both files with `.venv-echo/Scripts/python.exe
echo/scripts/refresh_supply_chain.py` after dependency changes. This is a
point-in-time advisory lookup, not a signed artifact verification, complete
container SBOM, or full monorepo license audit.
[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) preserves direct
dependency notices and the local InflationForge attribution.
