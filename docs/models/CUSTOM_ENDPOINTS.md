# Custom OpenAI-compatible endpoints

For vLLM, LM Studio, self-hosted inference servers and organization gateways. Fields: name, base URL, optional API key, models endpoint (default `/models`),
manual model IDs (used when the server has no usable list), custom headers (advanced, sanitized), capability overrides (advanced), data boundary (`local` / `organization` / `cloud`).

* Treat endpoints as **untrusted external systems**: they see everything you send.
* Do not assume feature parity: tools, vision, structured output and streaming usage differ. Capabilities default to inferred (weak) — use **Test** on the model; overrides are labeled “user override” and a wrong one can make requests fail.
* Set the **data boundary honestly**: it drives Local-only and sensitive-data routing. A server on your LAN is `organization` or `local`; a third-party URL is `cloud`.
* Cloud deployments block private addresses (SSRF). Self-hosted deployments allow them; cloud-metadata addresses are always blocked.
* `max_tokens_param` and `stream_usage` can be set in the connection configuration for servers that reject the OpenAI defaults.
