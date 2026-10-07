# Live provider tests (gated)

Run only with real credentials; skipped (with a clear reason) otherwise. Normal CI never needs them.

```
PEOPLEPAY_LIVE_TESTS=1 OPENAI_API_KEY=... pytest packages/peoplepay-model-gateway/tests/live -v
```
Each test is skipped unless its credential/endpoint is present: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`,
AWS credentials + `BEDROCK_REGION`, reachable Ollama (`OLLAMA_HOST` or 127.0.0.1:11434), `JEV_BASE_URL`, `LAYA_BASE_URL`.
