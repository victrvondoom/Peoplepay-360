# Decision models (JEV, Laya)

Typed fast-decision providers: `BOOLEAN`, `CHOICE`, `SCORE`, `RATING` questions about a state. They are used for classification, routing, gating and ranking — **not** prose.
They appear under typed decisions (never as chat models), have no `generate`/`stream`, and cannot be selected for chat (`NO_ROUTE`).

`gateway.decide(owner, state, questions)` validates every answer (boolean is a bool, choice is one of the choices, score is inside the scale; confidence in 0–1 or `None`) and
returns `origin: "MODEL_INFERENCE"`. `decide_or_escalate` runs the fast typed path and escalates to a deep generative route when confidence is below the threshold (default 0.7), is not
reported, or the provider is unavailable; the result records which path ran. A fast decision is never the sole authority for an irreversible action.

## Wire protocol status — read this

This repository contains **no specification** for JEV or Laya. Both adapters share `SystemOneStyleProvider`, which implements a documented *assumed* contract:

```
GET  {base}/health                   -> 200
GET  {base}/models                   -> {"models": [{"id", "name?", "question_types?": ["BOOLEAN", ...]}]}
POST {base}/decide  {"model", "state", "questions": [{"id","type","prompt","choices?","scale?"}]}
                                     -> {"answers": [{"id","value","confidence?"}]}
```

Paths are configurable (`paths: {models, decide, health}`); mapping to the real SystemOne-style protocol should be a change to that adapter, not to PeoplePay core. **Status: MOCK VERIFIED only.**
Do not present these integrations as working against the real services until verified. Laya reuses the JEV transport; manifests and configuration are separate (Laya's API key is optional).
