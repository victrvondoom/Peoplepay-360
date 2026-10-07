# Model Gateway architecture

```
PEOPLEPAY ──▶ CANONICAL CONVERSATION ──▶ MODEL GATEWAY
                                          ├─ ModelRegistry (cached discovery)   ├─ AutoRouter (policy.py)
                                          ├─ FallbackEngine                      ├─ HealthManager / cooldowns
                                          ├─ CredentialVault                     ├─ UsageTracker
                                          └─ ProviderRegistry ─▶ adapters: OpenAI · Anthropic · OpenRouter · Bedrock ·
                                                                  NVIDIA NIM · Ollama · OpenAI-compatible · mock
                                             DecisionProviders: JEV · Laya
```

Package: `packages/peoplepay-model-gateway/src/peoplepay_models` (standard library for transport; `cryptography` only to
persist credentials; `boto3` only for live Bedrock).

## Responsibilities

| Model Gateway owns | ECHO / PeoplePay Gateway own |
|---|---|
| provider integration, model selection, inference, fallback | evidence, provenance, trust, policy, decisions |
| capability detection, health, usage, stream normalization | authorization of payments, orders, submissions, operational changes |
| credential routing | exact human approval |

**No model output, and no model-selection result, can authorize an action.** `peoplepay_models.tools.ToolRegistry`
marks consequential tools; the model loop returns a *pending approval* marker instead of executing them. AI-derived claims
carry `Gateway.provenance(response, source=...)` = `{origin: "MODEL_INFERENCE", provider, model, route, timestamp, source}`,
which ECHO must keep distinct from `SOURCE_EVIDENCE`.

## Model vs. route

`ModelDefinition` (what the model is) is separate from `ProviderModelRoute` (how to reach it: provider connection, provider model id,
route label, privacy class, region, price, capabilities, availability, last discovery time). The same model can have several routes
(direct, Bedrock, OpenRouter) with different limits, prices and privacy. `canonical_model_id` links routes **conservatively**
(`heuristics.canonical_id`): a missed link is preferred to a wrong merge, and unknown fields stay `null`.

## Capabilities carry evidence

Every capability is stored with its evidence: `provider_metadata`, `capability_test`, `user_override`, or `static_fallback`
(name-pattern inference, used only where a catalog has no capability data, e.g. OpenAI-style `GET /models`). The UI marks weak
evidence with “?”; **Test** (vision / tools / structured output) upgrades it to `capability_test`. Routing reads capabilities and never
matches on model names. The only name patterns live in `heuristics.py`.

## Canonical conversation

`Conversation → Message(role, parts[], served_by) → TextPart | ImagePart | FilePart | ToolCallPart | ToolResultPart | StructuredPart`.
Adapters translate to and from provider formats; history is never stored provider-shaped. Each assistant message stores `served_by`
(provider, connection, canonical + provider model id, route, what was requested, fallback reason) so history survives model removal.

Switching models mid-chat keeps the history. `POST /api/v1/models/switch-check` previews warnings (images, files, context size).
Content the target cannot take is **never silently dropped**: the request is refused with `needs_consent` and the UI offers “choose another
model” or “continue without image context”. Over-long history is trimmed from the *oldest* messages with a visible note; the most recent
messages are never discarded (otherwise `CONTEXT_TOO_LARGE`).

## Routing (`policy.py` is the single place for preferences)

Pipeline: connection enabled → chat model → availability → provider health/cooldown → required capabilities (vision, files, tools) →
privacy admissibility for the request's data class → organization policy → context fit. Survivors are ordered by the routing policy
(Best quality / Balanced / Fastest / Low cost / Privacy first / Local only) using tier (user assignment > provider metadata >
weak name hint), measured latency, **known** price (unknown ≠ free), user favorites and preferred order. `POST /api/v1/models/explain`
returns requirements, selected route, and every exclusion with its reason (“Why this model?”).

## Retries

One policy: adapters and SDKs do **not** retry. The gateway makes at most `max_attempts` (default 3) attempts, each on a distinct route
(`A → B → A` is impossible), recorded in `attempts`. Cancellation stops further attempts. A stream that has already shown text to the user is
not transparently retried.

## HTTP API (mounted by `gateway/app.py`, same auth as the rest of the gateway)

`GET /api/v1/models/providers|connections|catalog|preferences|usage|health` · `POST /api/v1/models/connections` and
`/connections/{id}/test|refresh|update|remove` · `POST /api/v1/models/capability-test|explain|switch-check|decide|preferences` ·
`POST /api/v1/chat` (`stream: true` ⇒ SSE of canonical events `response.started`, `text.delta`, `tool.started`, `tool.completed`, `usage`,
`response.completed`, `error`) · `GET /health/models` (open; counts and catalog age only).

## Extensions

`peoplepay_models.client.ModelsClient(gateway, owner).generate("reasoning.deep" | "vision.analyze" | "text.fast" | …, prompt)` lets an
extension ask for a **capability** without a vendor or key. SDK v1 is unchanged and extensions keeping their own AI config keep working.

## Adding a provider

1. Write an adapter (`ProviderAdapter` or `DecisionProvider`) with a `ProviderManifest` (id, type, protocols, credential fields, discovery mode).
2. `registry.register(MyAdapter)` (one line in `registry.default_registry`).
3. Add it to the contract suite (`tests/test_adapter_contract.py` — add a fixture in `mg_fakes.py` and the kind to `KINDS`).
4. Document it in `PROVIDERS.md`.
No routing, fallback or UI file changes: the BYOK form is generated from the manifest.

## Beyond chat

`ProviderModelRoute.kind` already distinguishes `chat`, `decision`, `embedding`, `image_generation`, `audio`, `reranker`, `other`; non-chat kinds are discovered but never offered for chat. Image/video generation, speech, embeddings and reranking are not implemented; when needed they should get their own request/response schema on the same provider registry rather than being shoehorned into chat responses.

## Conversations created before the Model Gateway

PeoplePay had no chat store before this change, so there is nothing to migrate. Existing transactions, workflows and journeys are untouched.
