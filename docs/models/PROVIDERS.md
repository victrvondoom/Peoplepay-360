# Providers

Always **Test** after connecting, then **Refresh models**: catalogs change. Capabilities marked “?” are inferred — use *Test* on the model.
Verification status per provider is shown on each connection card.

| Provider | Type | Credentials | Discovery | Verification in this repo |
|---|---|---|---|---|
| OpenAI | Direct | API key; optional base URL / org / project | `GET /models` (ids only → capabilities inferred, tagged weak) | CONTRACT + MOCK |
| Anthropic | Direct | API key | `GET /v1/models` (paginated; reads capability metadata when the catalog supplies it) | CONTRACT + MOCK |
| OpenRouter | Aggregator | API key; optional app referer/title | `GET /models` (rich: modalities, parameters, context, pricing) | CONTRACT + MOCK |
| Amazon Bedrock | Enterprise | region + default chain / profile / assume-role / static keys | `ListFoundationModels` + inference profiles | CONTRACT + MOCK (fake boto client) |
| NVIDIA NIM | Inference platform | API key (hosted) or none (self-hosted) + base URL | `GET /models` (ids) | CONTRACT + MOCK |
| Ollama | Local | base URL | `/api/tags` + `/api/show` (capabilities, context) | CONTRACT + MOCK + stub-server over real HTTP |
| OpenAI-compatible | Custom | base URL, optional key/headers, manual models | `GET {models_endpoint}` else manual list | CONTRACT + MOCK |
| JEV / Laya | Decision | base URL (+ key) | provider model list | MOCK only — **wire protocol unverified** |

**LIVE VERIFIED: none.** This repository's CI has no provider credentials. Gated live tests are described in `packages/peoplepay-model-gateway/tests/live/README.md`.

## OpenAI
Connect: AI & Models → Connect a provider → OpenAI → API key. Capabilities are inferred from the model id (static fallback, shown as “?”);
reasoning models get `reasoning_effort` mapped from FAST/STANDARD/DEEP and no `temperature`. Fallback: eligible on 429/5xx/timeouts.
## Anthropic
Direct Messages API. `max_tokens` is required by the API; PeoplePay sends 4096 when the request sets none. Structured output uses instruction +
gateway validation. Reasoning preference is not mapped automatically; pass `provider_options.anthropic.thinking` explicitly.
## OpenRouter
Treated as a catalog, not one model: each OpenRouter model is a route with provider-supplied modalities, parameters, context and pricing. The upstream
provider reported in the response is appended to the route label (`OpenRouter → Upstream`). Routing behavior can be passed via `provider_options.openrouter`.
## Amazon Bedrock
Uses the Converse / ConverseStream API so request schemas need not be model-specific. **Bedrock's catalog does not say whether your account has access to a
model**: a model without access fails at call time with `MODEL_UNAVAILABLE`, which is exactly how PeoplePay reports it. Prefer IAM roles (`default_chain`) over static keys. Models requiring an inference profile appear only when a profile is listed. Region is part of the route.
## NVIDIA NIM
Hosted (`integrate.api.nvidia.com`) or self-hosted. Self-hosted uses `/v1/health/ready`. Set the data boundary to *organization* or *local* for self-hosted NIM so privacy routing is right. Hosted trial terms can restrict personal data — check them.
## Ollama
See [LOCAL_MODELS.md](LOCAL_MODELS.md). Capabilities (vision, tools, thinking) and context length come from Ollama itself.
## OpenAI-compatible / custom
See [CUSTOM_ENDPOINTS.md](CUSTOM_ENDPOINTS.md).
## JEV and Laya
See [DECISION_MODELS.md](DECISION_MODELS.md). They are listed under typed decisions and cannot be picked for prose chat.
