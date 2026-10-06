# Adding an ECHO extension

ECHO owns requirements, canonical claims and entities, evidence, FalkorDB,
source correlation, decisions, human approval, and transaction lineage.
An extension supplies bounded proposals to that core. The extension does not
receive a graph connection, approve a purchase, or execute a transaction.

The implemented platform has two modes: `builtin` for reviewed first-party
adapter code and `service` for a separately operated HTTP service. Other modes
from the design brief, including CLI, arbitrary library loading, and automatic
repository installation, are not implemented.

## 1. Assess the repository before implementing an adapter

Create `docs/extensions/intake/<extension-id>.md`. Record the requested URL,
resolved full upstream commit, actual inputs and outputs, public entrypoints,
runtime and model dependencies, state stores, authentication, egress, test
results, and maintenance evidence. Distinguish verified upstream identity from
a README link or a bundled PeoplePay tree hash.

Explain the additional capability and its overlap with ECHO and existing
providers. Choose one primary category from `ExtensionCategory` in
`echo/extensions/contracts.py`. State `INTEGRATE`, `DEFER`, or `REJECT`, the
integration mode, expected graph benefit, risks, and a measurable acceptance
case. A service with a useful read-only endpoint is preferable to importing
another application's core into ECHO.

Create `docs/extensions/licenses/<extension-id>.md`. Inspect the license file,
copyright, NOTICE requirements, and data/model licenses separately. Record
`LICENSE_UNKNOWN` when permission is unclear; do not copy upstream source in
that state. A first-party independently written adapter does not establish
permission to redistribute the upstream application. The current bundled
project findings are in [the intake dossier](extensions/intake/bundled-projects.md).

Inspect install scripts, binaries, dependency locks, dynamic execution,
subprocesses, network and filesystem access, credentials, browser privileges,
unsafe deserialization, and CI. Describe a risk classification and the
evidence behind it. An unrun advisory scan is `UNKNOWN`, not a clean scan.
See [the implemented security boundary](extensions/security.md).

## 2. Create a manifest owned by the core

Put the manifest in `extensions/<extension-id>/extension.yaml`. The directory
name must match `id`. The loader reads this one directory level, limits each
manifest to 32 KiB and the registry to 64 entries, rejects escaping symlinks,
uses safe YAML loading, validates the typed schema, and rejects unknown fields.

This example is deliberately disabled and makes no assertion about an
upstream repository or license. Replace the identity and review records with
verified information before activation.

```yaml
schema_version: "1"
id: reviewed-price-provider
name: Reviewed price provider
version: 1.0.0
type: PRICE_INTELLIGENCE
enabled: false
priority: 100
upstream:
  repository: null
  commit: null
license:
  spdx: LICENSE_UNKNOWN
  notice_required: false
  source_reused: false
runtime:
  mode: service
  language: python
  url_env: ECHO_EXT_REVIEWED_PRICE_URL
  allowed_hosts: [127.0.0.1]
  timeout_seconds: 8
  max_concurrency: 2
  max_failures: 3
  cooldown_seconds: 30
capabilities: [price_intelligence]
permissions:
  network: true
  filesystem: false
  subprocess: false
graph:
  read: []
  write: [Product, Claim, Evidence, Source]
secrets: []
healthcheck:
  path: /health
dependencies: []
```

`graph.write` is an allowlist of proposals the core may ingest. It never grants
direct Cypher access. Supported proposal entities are `Supplier`, `Product`,
`Organization`, and `Place`; claims, evidence, and sources have separate typed
records. Decision, approval, transaction, and deletion permissions cannot be
requested. `graph.read` records intended schema dependencies; the platform
does not provide an arbitrary graph-read interface.

Filesystem and subprocess permissions are rejected. `service` requires
explicit network permission; the supported `builtin` mode rejects network
permission. These checks do not sandbox Python code: only reviewed adapter
objects may be wired into the core.

## 3. Implement and register the reviewed adapter

Write a small adapter in `echo/extensions/adapters/<extension-id>.py`. Inherit
`ManifestAdapter` for core-owned `metadata()` and `capabilities()` helpers.
Implement asynchronous `health()` returning `ExtensionHealth` and
`execute(request)` returning `NormalizedResult` or its JSON-compatible object.
The adapter converts upstream output into the typed contract; the runtime then
validates it again before ingestion.

Wire the adapter explicitly in `echo/extensions/bootstrap.py`. A manifest has
no Python module, install command, executable, or Cypher field. Adding a
manifest alone cannot import code. The registry attaches reviewed objects and
checks declared capabilities when objects are registered; use that same
capability agreement when wiring through bootstrap.

Use `ExtensionRegistry.find(capability)` to discover providers. Lower numeric
`priority` wins; equal priorities sort by extension ID. `ExtensionRuntime.execute`
uses this order with fallback after a failed provider. `execute_all` collects
enabled providers concurrently. Ensemble output must pass through source
correlation; the number of providers is not evidence independence.

## 4. Preserve provenance in every decision signal

`ExtensionRequest` API v1 contains `request_id`, `capability`, `context`,
`input`, `constraints`, and `trace`. Ingestion requires the context's
`requirement_id` and `user_id` to identify an existing owned requirement.
The request does not carry credentials, a graph handle, or canonical write
instructions. Requests are limited to 64 KiB of serialized JSON, depth 12,
100 items per JSON array, and bounded strings and keys.

`NormalizedResult` carries the producer ID and version plus `sources`,
`entities`, `claims`, `evidence`, `source_dependencies`, `observations`,
`warnings`, optional confidence, optional `raw_reference`, and optional model
provenance. Results are limited to 256 KiB, 100 records per proposal collection,
and 30 warnings. Extra fields, nonfinite numbers, duplicate references,
dangling references, and cyclic source dependency proposals are rejected.

Every claim needs an `entity_ref`, a bounded `predicate`, a JSON value, text,
and kind (`fact`, `estimate`, `inference`, or `model_output`). This proposal
type does not mean the core has verified the statement. A claim marked
`KNOWN` must have supporting evidence marked `KNOWN`. Known evidence must
reference a known source and include a timezone-aware observation timestamp.
Known sources require an HTTP(S) URL without credentials or an upstream
document ID, plus their observation timestamp. Use `PROVENANCE_UNKNOWN` and
nullable fields when information is missing; never invent a capture time,
publisher, source hash, or source URL.

Source records can preserve `published_at`, `original_observed_at`,
`retrieved_at`, `cache_age_seconds`, `content_hash`, and `snapshot_text`.
Cached data with a cache age must also carry original and retrieval timestamps.
Evidence has separate validity bounds and its own observation timestamp. A
retrieval time is not proof that a claim is current. Record provider, model,
generation timestamp, and prompt version in `model_provenance` where available.
Model output without supporting sources remains model output.

Source dependencies use `DERIVED_FROM`, `CITES`, or `MIRRORS`, and record
`evidence_mode` (`explicit` or `inferred`), confidence, and an explanation.
An adapter must not invent links merely because two answers sound similar.
The core decides which proposals influence traversal and decisions.

## 5. Let the core resolve entities and write the graph

`ExtensionIngestor` assigns canonical IDs. Supplier and organization
representations with an exact `official_domain` identifier can resolve to the
same canonical node. This is identifier matching, not proof of company
ownership or a general fuzzy entity resolver. A display name by itself stays
an unresolved `EntityRepresentation`; unresolved products are retained as
representations rather than silently becoming canonical suppliers.

Source URLs are normalized without fetching them. Shared normalized URLs
therefore share source identity across providers; returned derivation links
join those sources in one graph. The core records `Extension`,
`ExtensionVersion`, `ExtensionRun`, `SourceSnapshot`, and `IngestionEvent`
alongside claims and evidence. `PRODUCED`, `OBSERVED`, `HAS_VERSION`, and
`EXECUTED` links retain producer and version provenance. Two extensions
retrieving the same upstream source do not create two independent roots.

The ingestion event identity binds provider version, requirement, and
`request_id`. Replaying the same envelope returns the prior applied summary;
reusing its ID with different input returns `IDEMPOTENCY_CONFLICT`. Keep
request IDs stable for deliberate retries and issue a new ID for a new
observation. The current in-process lock does not coordinate multiple API
workers; operate a single ECHO API worker until cross-process coordination is
implemented. Follow the actual graph batch validation when adding node types.

Core-owned candidate policy and the decision engine remain separate from
extension claims. An upstream rank, confidence, or suggestion is not a
canonical utility score or authorization. Synthetic adapters only ingest into
synthetic requirements; the core marks their scope and blocks synthetic
decisions from transaction creation.

## 6. Configure a service and enable only the intended providers

Set the URL named by the manifest in the ECHO process environment. URLs must
use HTTP(S), contain no user information, query, or fragment, and use an exact
hostname from `allowed_hosts`. Network location is operator configuration,
never request input. Paths and methods are selected by reviewed adapter code;
the transport rejects network paths, path traversal, redirects, compressed
responses, oversized bodies, and non-JSON responses. It accepts JSON objects
by default; adapters must explicitly request `expected_response="array"` for
array endpoints. It supports GET and POST only.

For service bearer authentication, declare a dedicated environment variable
in `secrets` and name it in `runtime.auth_secret_env`. The transport reads only
that declared bearer value for the request; it does not forward the ECHO API
token or every environment variable to the service. Never put secrets in a
manifest, request, result, trace, graph record, or log.

If `ECHO_EXTENSIONS` is absent, each manifest's `enabled` default applies.
When the variable is present, it replaces those defaults with the comma
separated IDs listed there. An empty value disables all providers; an unknown
ID rejects configuration. With the included manifests:

```powershell
# Default: two synthetic providers; InflationForge is disabled.
Remove-Item Env:ECHO_EXTENSIONS -ErrorAction SilentlyContinue

# Include the optional, separately started InflationForge service.
$env:ECHO_EXT_INFLATIONFORGE_URL = "http://127.0.0.1:8010"
$env:ECHO_EXTENSIONS = "demo-source-a,demo-source-b,inflationforge"

# Preserve only the two synthetic providers.
$env:ECHO_EXTENSIONS = "demo-source-a,demo-source-b"
```

Restart ECHO after changing process environment. Runtime toggles are
process-local; configuration in the process environment or reviewed manifests
controls the next restart. A dependency must also be enabled and attached.
An entry may retain requested-enabled configuration while its adapter is
missing; it remains unavailable and cannot execute. The toggle API rejects
activation when no reviewed adapter is attached.

The InflationForge adapter requires explicit `snapshot_id`, `item_id`, and
`city_id`, and reads only the filtered observation endpoint and health.
It preserves historical receipt dates and unknown source metadata. A city
price observation is not a supplier quote or a supported procurement offer.
See the adapter and intake dossier for the exact inspected interface.

### Versioned API and caller identity

The routes are implemented in `echo/extensions/api.py`:

| Route | Purpose | Authorization |
|---|---|---|
| `GET /echo/v1/extensions` | Manifests, enabled state, configuration, health | PeoplePay caller |
| `POST /echo/v1/extensions/{id}/enabled` | Process-local toggle with `{"enabled": true}` or `false` | Caller plus ECHO administrator token |
| `POST /echo/v1/extensions/execute?extension_id={id}` | Execute one provider and ingest its normalized proposals | Caller owning request requirement |
| `POST /echo/v1/extensions/execute` | Capability selection and fallback | Caller owning request requirement |
| `GET /echo/v1/extensions/runs` | The caller's most recent 50 persisted runs | PeoplePay caller |
| `POST /echo/demo/extensions/run` | Create a synthetic requirement and run cross-provider provenance proof | Local synthetic demo route |

The caller verifier is shared with `gateway.auth`. With
`BEACON_GATEWAY_SECRET` configured, a signed expiring PeoplePay bearer token
is required; its verified user ID determines ownership, and a bare
`X-Beacon-User` does not override it. Without that secret the reported mode is
`OPEN`: `X-Beacon-User` is accepted for local development and can be spoofed.
This is not OIDC, a login service, or a production identity deployment.

The toggle route additionally requires `ECHO_ADMIN_TOKEN` configured in the
ECHO process and supplied through `X-Echo-Admin-Token`. Missing administrator
configuration returns 503, a wrong token returns 403, and an unregistered
extension returns 404. Keep this administrator token separate from service
credentials. The execute route requires `context.user_id` to equal the caller
and an existing requirement owned by that caller; other users' requirements
are not accessible by changing the envelope.

For a local OPEN-mode session, after ECHO is started on loopback:

```powershell
$echoHeaders = @{ "X-Beacon-User" = "local-reviewer" }
Invoke-RestMethod http://127.0.0.1:8090/echo/v1/extensions -Headers $echoHeaders

$requirement = Invoke-RestMethod http://127.0.0.1:8090/echo/requirements `
  -Method Post -Headers $echoHeaders -ContentType "application/json" `
  -Body (@{ user_id="local-reviewer"; description="Review city price receipts"; quantity=1 } | ConvertTo-Json)

$extensionRequest = @{
  schema_version="1"
  request_id="receipt-review-001"
  capability="price_intelligence"
  context=@{ requirement_id=$requirement.requirement.id; user_id="local-reviewer" }
  input=@{ snapshot_id="replace-with-existing-snapshot"; city_id="austin"; item_id="milk" }
}
Invoke-RestMethod "http://127.0.0.1:8090/echo/v1/extensions/execute?extension_id=inflationforge" `
  -Method Post -Headers $echoHeaders -ContentType "application/json" `
  -Body ($extensionRequest | ConvertTo-Json -Depth 8)

Invoke-RestMethod http://127.0.0.1:8090/echo/v1/extensions/runs -Headers $echoHeaders
```

The snapshot ID is a placeholder for a real record in the separately running
InflationForge instance. Enabling that provider does not create the instance,
its snapshots, or its credentials. This call records observations; it does not
create a supplier quote or a canonical procurement policy. For verified mode,
supply the caller's signed token in the Authorization header.

## 7. Test contract, graph impact, and failure isolation

Use the isolated ECHO environment from the repository root:

```powershell
python -m venv .venv-echo
.venv-echo/Scripts/python.exe -m pip install -r echo/requirements-dev.txt
.venv-echo/Scripts/python.exe -m pytest -q echo/tests/test_extension_runtime.py

docker compose -f compose.echo.yaml up -d falkordb
$env:ECHO_FALKORDB_PORT = "16380"
$env:ECHO_REQUIRE_GRAPH_TESTS = "1"
.venv-echo/Scripts/python.exe -m pytest -q echo/tests
```

Graph tests must create and delete only their own uniquely named disposable
graphs. `ECHO_REQUIRE_GRAPH_TESTS=1` makes unavailable FalkorDB a failing check
instead of a skipped integration suite. A skipped graph suite is not proof of
successful ingestion or decision integration.

Add a meaningful contract test, health test, timeout test, malformed-output
test, disable test, provenance trace test, and requirement-to-decision graph
test. Exercise stale and future evidence, duplicate data, unknown entities,
unsupported output fields, conflicting claims, source invalidation, and
malicious HTML treated as text. Include two providers that return the same
upstream source: prove that graph root count does not grow merely because a
second provider repeats it. Then compare useful signal coverage, independent
roots, decision changes, trace completeness, and latency with and without the
extension. Label synthetic measurements and report missing live-provider
proof explicitly.

## 8. Preserve attribution and update evidence

Record adapter work separately from upstream functionality. Preserve original
license texts and copyright notices; update [third-party notices](../THIRD_PARTY_NOTICES.md)
and [the installed environment inventory](extensions/sbom.json) when
dependencies change. Pin an inspected upstream revision for any reused source
or model. Recheck the diff, schema, licensing, credentials, permissions, and
tests before changing an upstream version. Do not update an upstream service
silently if its output schema is part of the reviewed contract.


## Real bounded-service example: CivicMesh

`extensions/civicmesh` demonstrates explicit registration, typed/minimized request, jurisdiction coverage, health, deadline, result validation, producer trace, SDK-to-ECHO translation and UI follow-up without rewriting the provider. `journey/extension_runtime.py` uses the existing SDK registry; ECHO uses its existing manifest/runtime/ingestion boundary. SDK v1 request/result schemas remain unchanged; program claims/estimates use entity attributes, and question/paths use the bounded receipt envelope. Conceptual assistance.eligibility maps to the existing snake_case capability assistance_eligibility. See the adapter README and native boundary tests.
