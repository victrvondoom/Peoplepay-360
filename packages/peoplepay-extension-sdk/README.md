# PeoplePay Extension SDK v1

This Python package defines stable, validated contracts for specialist
capability providers. It standardizes metadata, capabilities, health checks,
bounded request/context envelopes, entities, evidence, action proposals, and
raw provider results. It does not load plugins or grant access to ECHO's graph,
Gateway transactions, credentials, or payments.

The package also defines a correlation-bearing event envelope. The existing
Gateway event bus remains the in-process publisher and its transaction ledger
remains authoritative; this SDK type does not imply an outbox or broker has
been deployed.

```powershell
python -m pip install -e .
```

Implement `metadata()`, `capabilities()`, `health()` and async `execute()` on a
provider object, then register it explicitly with `ProviderRegistry`. The host
must still review the source, manifest, license, service identity, permissions,
timeouts and result mapping before registration. Action proposals require
separate policy and human approval. Evidence with unknown provenance remains
unknown; do not infer source verification from a provider response.

See [`examples/minimal_provider.py`](examples/minimal_provider.py) for a
provider shape that returns no fabricated records when a backend is absent.

`schema_version` is currently `1`. Breaking contract changes require a new
versioned API path/schema. Provider `version` identifies its own release.
