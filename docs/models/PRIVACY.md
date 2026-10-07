# Privacy, security and routing constraints

**Data classes** — `PUBLIC`, `INTERNAL` (default), `SENSITIVE`, `RESTRICTED`. Routes have a privacy class: `local` < `organization` < `cloud`.
PUBLIC/INTERNAL may use any; SENSITIVE/RESTRICTED only local or organization (cloud for SENSITIVE only if you opt in; never for RESTRICTED). `OrgPolicy`
(allowed/denied providers and models, no external cloud, approved connections, regions, max price) is a contract that is enforced when supplied; the product has no organization model yet.
A fallback chain may only choose destinations the current constraints allow — it is the same filter, so the rule cannot be bypassed by fallback.

## Threat review (what was checked and how)

| Risk | Control | Test |
|---|---|---|
| API-key leakage | vault encryption, write-only secrets, `redact` on all errors/logs, no prompts in telemetry | `test_secrets_never_appear_…`, `test_redact_patterns` |
| Cross-user key/connection access | owner-scoped lookups return the same “not found” for foreign ids; vault AAD binds owner | `test_user_connections_are_private…`, `test_vault_encrypts_at_rest_and_binds_owner` |
| SSRF via custom base URL | scheme check, no embedded creds, DNS resolution + range blocking (private, loopback, link-local, CGNAT, metadata) in cloud mode, metadata always blocked, connection pinned to the validated IP, redirects never followed | `test_cloud_mode_blocks_…`, DNS-rebinding test, `test_redirects_are_not_followed` |
| Malicious local endpoint / provider impersonation | responses are validated (shape, tool-call JSON, decision answer types); output is data, rendered with `textContent` | contract + decision tests |
| Untrusted custom headers | header injection (CR/LF), Host/hop-by-hop/Authorization override and >10 headers dropped | `test_custom_headers_are_sanitized` |
| Prompt injection → tool abuse | tools are canonical; consequential tools return *pending approval*, never execute | `test_tool_call_never_authorizes_…` |
| Malformed tool calls | rejected as `INVALID_RESPONSE`, eligible for fallback | contract + `test_malformed_tool_call_triggers_fallback…` |
| Logs containing prompts | invocation telemetry holds operational metadata only; conversation text lives only in the conversation table | `record_invocation` columns |
| Attachment leakage | attachments are never sent to a route lacking the capability, and never silently dropped | switching tests |

**Identity.** Provider connections are scoped to the gateway's verified user id. With `BEACON_GATEWAY_SECRET` unset the gateway runs in OPEN mode (caller identity unverified, local use only); on a `cloud` deployment the Model Gateway therefore refuses to store credentials until verified auth is configured.

Residual risks: DNS pinning protects the connection but a hostname's *future* answers are only re-validated per request; webhook spoofing is not applicable (no inbound webhooks yet);
there is no vault key rotation tool; conversation text is stored unencrypted in the model database (as other PeoplePay records are); HTTP basic limits (body size 32 MB) are the only DoS control in the adapter layer.
