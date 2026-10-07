# Migration status of existing direct model clients

Additive migration: nothing was removed; standalone projects keep their own configuration. Classification:

| Where | Direct AI use | Status |
|---|---|---|
| PeoplePay Gateway (`gateway/`) | none previously (no model client existed) | **MIGRATED** — new `/ask`, `/models`, `/api/v1/chat`, `/api/v1/models/*` run entirely on the Model Gateway |
| ECHO (`echo/`) | no model calls | **N/A** — provenance contract (`ModelGateway.provenance`) ready for future extraction/explanation |
| Environment variables `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `OLLAMA_HOST`, `JEV_*`, `LAYA_*`, AWS/Bedrock | read by specialist projects | **COMPATIBILITY MODE** — also registered as system ProviderConnections by `bootstrap.register_env_connections`; same variables, no change required |
| Beacon (`Beacon-main/src/beacon`: litellm → Bedrock Nova, Strands) | triage, prefetch, voice | **STANDALONE ONLY** (deployed as AWS Lambda; own budget/fallback chain) |
| CONSUMER / PROXY (`CONSUMER-main/backend/app/llm/providers/nvidia_provider.py`, `LLM_PROVIDER`) | own provider abstraction + NVIDIA | **STANDALONE ONLY**; candidate for the `ModelsClient` once its dispute-drafting flow is routed through PeoplePay |
| CivicMesh (`civicmesh/llm/*.jac`, litellm Router with NIM/Groq chains, cmguard budget) | narrator, translation | **STANDALONE ONLY**; own budget guard and zero-retry pinning |
| InHeir, Rumi (Convex), GreenChain, InflationForge | provider-specific or no LLM | **DEFERRED** |
| Extension SDK v1 | no inference surface | **COMPATIBLE** — optional `ModelsClient` is opt-in; SDK untouched |

Order of migration: Model Gateway stable → PeoplePay primary chat (done) → ECHO explanation/extraction → shared services → new extensions → specialist projects one at a time.
Specialist projects have independent retry/fallback chains; integrated mode should route them through `ModelsClient` so retries are not stacked.
