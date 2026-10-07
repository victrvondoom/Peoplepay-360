# Fallbacks, rate limits and health

* Modes: **Ask before switching** · **Automatic** · **No fallback** (AI & Models → Fallbacks, or per request). Sensitive/Restricted data downgrades *Automatic* to *Ask* unless you explicitly allowed it.
* Fallback happens only for `RATE_LIMITED, QUOTA_EXHAUSTED, PROVIDER_UNAVAILABLE, MODEL_UNAVAILABLE, MODEL_NOT_FOUND, TIMEOUT, SERVER_ERROR, CONTEXT_TOO_LARGE, UNSUPPORTED_CAPABILITY, LOCAL_PROVIDER_OFFLINE, INVALID_RESPONSE`.
  Never for `INVALID_REQUEST, POLICY_REJECTED, AUTHORIZATION_REQUIRED, INVALID_CREDENTIALS, PRIVACY_POLICY_BLOCKED`.
* Candidates are pre-filtered, so a fallback always satisfies the same capabilities (vision, tools, files, context) and the same privacy constraints. Low-cost mode will not jump to a route above 2× the primary's known price, nor to an unknown price unless you allow it.
* No loops: each route is tried once; at most `max_attempts` (3). Cancellation stops further attempts.
* The answer records `requested`, `served_by` and `fallback_reason`; the chat shows “switched provider (rate limited)” subtly and developer mode shows all attempts.

## Health states

`HEALTHY · DEGRADED · RATE_LIMITED · AUTH_ERROR · UNAVAILABLE · DISABLED` (+ `UNKNOWN` before the first check). A 429 puts the connection in cooldown for `Retry-After` (else exponential 30 s → 5 min);
quota exhaustion cools for at least 5 min; repeated failures degrade then temporarily remove a route; model-level failures cool only that model; success heals. Cooldown expiry allows a probing
attempt. State is derived from observed outcomes — never invented. When a provider does not expose remaining quota the UI says *Quota information unavailable*.
