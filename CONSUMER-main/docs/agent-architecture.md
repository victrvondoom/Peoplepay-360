# Supervisor Agent Architecture

PROXY uses a two-layer agent model executed by a real LangGraph `StateGraph`.

## Optimized Runtime Flow

Default flow for a user question:

1. Supervisor start: no LLM call.
2. Planner: deterministic intent plan, no LLM call.
3. Qdrant Retrieval: vector search, no LLM generation call.
4. Neo4j Query: graph lookup only when useful, no LLM call.
5. Web Search: reserved node, skipped unless configured.
6. Domain Specialist: selected specialist only, usually 1 Gemini reasoning call.
7. Negotiator: runs only when multiple specialists are selected, no LLM by default.
8. Response: reuses specialist output by default; optional 1 Gemini response call when `RESPONSE_AGENT_LLM_ENABLED=true`.

The compiled graph is in `backend/app/agents/orchestrator/case_workflow.py`. API responses expose `workflow_engine`, `agent_trace`, `route`, `specialist_outputs`, and `llm_call_count` so the frontend can show exactly what ran.

## Model Roles

| Purpose | Default model | LLM call by default | Why |
| --- | --- | --- | --- |
| Main reasoning: Policy, Claims, Medical, Legal, FAQ | `gemini-2.5-flash` | Yes, selected specialists only | Best balance of quality, speed, and cost |
| Supervisor / Router | Rule-based, `gemini-2.5-flash-lite` reserved | No | Routing should be cheap and predictable |
| Planner | Rule-based, `gemini-2.5-flash-lite` reserved | No | Lightweight intent planning is enough |
| Response generation | Same specialist response; optional `gemini-2.5-flash` | No by default | Avoids an extra call unless polished final prose is needed |
| Document summarization | `gemini-2.5-flash-lite` | Only when explicitly called | Fast for summarizing retrieved text |
| OCR/Image understanding | `gemini-2.5-flash` | Only for image/PDF OCR workflows | Multimodal-capable model role |

Configure these with:

```env
GEMINI_REASONING_MODEL=gemini-2.5-flash
GEMINI_ROUTER_MODEL=gemini-2.5-flash-lite
GEMINI_PLANNER_MODEL=gemini-2.5-flash-lite
GEMINI_RESPONSE_MODEL=gemini-2.5-flash
GEMINI_SUMMARIZATION_MODEL=gemini-2.5-flash-lite
GEMINI_OCR_MODEL=gemini-2.5-flash
RESPONSE_AGENT_LLM_ENABLED=false
DISABLE_EXTERNAL_LLM=false
```

Use `DISABLE_EXTERNAL_LLM=true` for fast local tests that should not spend Gemini calls.

## Layer 1: Role-Based Agents

These agents are shared across all domains:

- Supervisor: starts and completes the graph run.
- Planner: deterministically classifies intent and chooses specialists/tools.
- Retrieval: fetches relevant chunks from Qdrant, with local vector fallback.
- Knowledge Graph: queries Neo4j only when institution/history context is useful.
- Web Search: reserved for current/live information requests.
- Negotiator: combines multiple specialist outputs only when more than one specialist was selected.
- Response: builds the final user-facing answer and case workflow fields.

## Layer 2: Domain Specialist Agents

Health insurance currently has:

- Policy Agent: coverage, exclusions, waiting periods, riders, policy wording.
- Claims Agent: denials, cashless, reimbursement, preauthorization, claim workflow.
- Medical Agent: diseases, procedures, treatment context, medical necessity.
- Legal/Regulations Agent: IRDAI, complaints, policyholder rights, ombudsman.
- FAQ/General Agent: general explanations and missing-document guidance.

Future domains should add specialists under `backend/app/agents/domain_agents/<domain>/` and register them in the supervisor graph domain node.
