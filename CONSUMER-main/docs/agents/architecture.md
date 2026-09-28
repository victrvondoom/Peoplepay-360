# Agent Architecture

PROXY now runs the healthcare workflow through a real LangGraph `StateGraph`.

## Optimized Runtime Path

```text
FastAPI
  -> LangGraph StateGraph
  -> Supervisor Start              # no LLM
  -> Planner                       # rule-based, no LLM
  -> Qdrant Retrieval              # tool call, no LLM generation
  -> Neo4j Graph Node              # tool call only when useful
  -> Web Search Node               # reserved, no LLM; skipped unless configured
  -> Domain Specialist Agents      # selected Gemini reasoning calls only
  -> Negotiator                    # only for multi-specialist routes, no LLM by default
  -> Response Agent                # reuses specialist output by default
  -> Human Approval Gate
```

The compiled graph lives in `backend/app/agents/orchestrator/case_workflow.py`. If LangGraph is not installed in a deployment, the same nodes run through a deterministic fallback sequence so the API remains functional.

## Cost Contract

- Supervisor: no LLM call.
- Planner: no LLM call.
- Retrieval: no LLM generation call.
- Neo4j graph lookup: no LLM call.
- Selected specialist: 1 Gemini reasoning call per selected specialist.
- Negotiator: no LLM by default.
- Response: no LLM by default; optional `GEMINI_RESPONSE_MODEL` call only when `RESPONSE_AGENT_LLM_ENABLED=true`.

`llm_call_count`, `workflow_engine`, `agent_trace`, and `specialist_outputs` are returned in agent run responses for observability.

## Health Insurance Specialists

- Policy Agent: coverage, exclusions, waiting periods, riders, policy wording.
- Claims Agent: denials, cashless, reimbursement, preauthorization, claim workflow.
- Medical Agent: diseases, procedures, treatment context, medical necessity.
- Legal/Regulations Agent: IRDAI, complaints, policyholder rights, ombudsman.
- FAQ/General Agent: general explanations and missing-document guidance.

## Example

Question: `Does Star Health cover cataract surgery?`

Expected route:

```text
planner:policy
retrieval:qdrant
specialist:policy:gemini_reasoning
specialist:medical:gemini_reasoning
negotiator:merged-specialists
response:final
```

That uses two reasoning calls because the question needs both policy interpretation and medical procedure context. A simple claim-denial question routes only to Claims Agent and uses one reasoning call.

Critical product rule: no external filing or negotiation should happen without explicit user approval.
