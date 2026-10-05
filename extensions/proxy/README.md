# PROXY: deferred extension dossier

This is a deferred `DISPUTE_ASSISTANCE` capability, not a working ECHO adapter.
The independent PROXY application remains in `CONSUMER-main`.
ECHO has not copied its source or activated a case workflow.

Activation needs application/corpus permission, verified caller identity,
owned case mapping, authorized document transfer and a draft-only contract
that preserves source excerpts and review metadata. The actual default API
prefix is `/api/v1`; its case/agent routes require bearer authentication.
Neither an environment variable nor the old root adapter resolves those gates.
See [the dossier](../../docs/extensions/intake/bundled-projects.md) and
[license gate](../../docs/extensions/licenses/proxy.md).

README-declared upstream: `https://github.com/rakeshselvaraj0108/Proxy`.
Upstream commit unproven; local tree
`5406fc4b91469f2b221897191416f775de2f35a7`. A deferred `0.0.0` manifest is a
dossier version, not the application version. No hosts, graph permissions,
external submissions or transaction-resolution authority are authorized.
