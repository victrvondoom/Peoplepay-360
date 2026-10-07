# PeoplePay Multi-model AI

PeoplePay is **AI-provider agnostic**. There is one model gateway, many providers, many models, one
canonical conversation and one user experience.

> Use the AI you want. Connect your own cloud key, an enterprise platform, OpenRouter, a local Ollama, or any
> OpenAI-compatible endpoint. Pick an exact model — or leave it on **Auto**. If a provider hits its limit, switch
> to another. If privacy matters, stay **Local only**.

| Page | What it covers |
|---|---|
| [MODEL_GATEWAY.md](MODEL_GATEWAY.md) | Architecture, canonical conversation, routing, API |
| [PROVIDERS.md](PROVIDERS.md) | How to connect each provider, discovery, limits |
| [BYOK.md](BYOK.md) | Bring-your-own-key flow and the credential vault |
| [LOCAL_MODELS.md](LOCAL_MODELS.md) | Ollama, local-only mode, cloud vs self-hosted |
| [FALLBACKS.md](FALLBACKS.md) | Rate limits, health, fallback rules |
| [PRIVACY.md](PRIVACY.md) | Data classes, routing constraints, SSRF, logging |
| [CUSTOM_ENDPOINTS.md](CUSTOM_ENDPOINTS.md) | vLLM, LM Studio, org gateways |
| [DECISION_MODELS.md](DECISION_MODELS.md) | JEV / Laya typed decisions |
| [../../packages/peoplepay-model-gateway/MIGRATION.md](../../packages/peoplepay-model-gateway/MIGRATION.md) | Status of existing direct model clients |

## Quick start (self-hosted)

```bash
pip install -e packages/peoplepay-model-gateway[vault]
python -m peoplepay_models.vault                      # prints a vault key; export it as PEOPLEPAY_MODELS_VAULT_KEY
python -m gateway.app                                 # open http://127.0.0.1:8080/models  and  /ask
```

Open **AI & Models**, connect a provider, press *Connect and test*, then open **Ask**. With nothing connected,
PeoplePay still works; the chat page tells you to connect a provider.

## Verification vocabulary

Reports in this repository use three labels and never blur them:

* **MOCK VERIFIED** — exercised against deterministic in-repo fakes or stub servers.
* **CONTRACT VERIFIED** — adapter output checked against the provider's documented wire shapes using recorded-shape fixtures.
* **LIVE VERIFIED** — a real call to the real provider succeeded in this repository's test run. Nothing is LIVE VERIFIED until someone with credentials runs the gated tests (`PEOPLEPAY_LIVE_TESTS=1`).

## Model names are not hardcoded

Models shown in the UI come from provider discovery (cached; refresh manually) or your own configuration.
Docs use generic examples. Model catalogs change constantly: refresh your connected catalog rather than trusting any list.
