# Local models and Local only

## The localhost problem

`http://127.0.0.1:11434` means *the machine the PeoplePay backend runs on*. A cloud-hosted PeoplePay cannot reach Ollama on your laptop, and PeoplePay does
not pretend otherwise.

| Deployment | What works |
|---|---|
| **Self-hosted PeoplePay** (`PEOPLEPAY_DEPLOYMENT=self_hosted`, default) | The backend reaches Ollama/vLLM at the configured address. Default probe: `http://127.0.0.1:11434`. |
| **Cloud PeoplePay** (`cloud`) | Private/loopback/link-local/metadata addresses are blocked (`CUSTOM_ENDPOINT_BLOCKED`). Use a reachable endpoint you operate and an administrator allow-lists (`PEOPLEPAY_MODELS_HOST_ALLOWLIST`), or run PeoplePay yourself. A desktop companion / local bridge is the intended future path (not built yet). Browser-direct inference is not implemented. |

## Ollama

Connect with the base URL. Discovery uses `/api/tags`, then `/api/show` per model (bounded to 60) for capabilities (`completion`, `vision`, `tools`, `thinking`) and
context length — all tagged `provider_metadata`. Local runs use your hardware: the UI shows “no cloud API quota”, not “unlimited”.
Run: `ollama serve` then `ollama pull <model>`; press **Refresh models** in PeoplePay.

## Local only

Setting it (Ask page, or AI & Models → Local models, or the *Local only* routing preference) makes the planner exclude every route whose privacy class is not `local`.
If no local model can answer, PeoplePay returns `LOCAL_PROVIDER_OFFLINE` with `ask_privacy_change: true`; the UI asks whether to change the privacy mode. **It never falls
back to a cloud provider on its own.** Tests assert the cloud adapter receives zero calls. Local only also applies to typed decisions, and a workflow needing a
capability with no local model stops and says so. PeoplePay as a whole is not claimed to work offline: only model inference is kept local.
