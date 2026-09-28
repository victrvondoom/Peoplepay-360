# PROXY Backend Architecture

PROXY backend is a FastAPI service for consumer dispute resolution. The current active domain is `health_insurance`; the system already models all eight planned domains so they can be activated one by one as knowledge is added.

## High-Level Topology

```text
                Users
                  |
        +---------+---------+
        |                   |
 Web App (Next.js)   Mobile App (Flutter)
        |                   |
        +---------+---------+
                  |
            FastAPI Backend
      +-----------+-----------+
      |           |           |
      v           v           v
  Supabase     Qdrant       Neo4j
                  |
              LangGraph
                  |
              Gemini API
```

## Runtime Layers

1. Client layer: Next.js web app and Flutter mobile app.
2. FastAPI layer: REST routes, WebSockets, request context, CORS, rate limiting, and API security.
3. Auth/data/storage layer: Supabase Auth, PostgreSQL, RLS, and Storage.
4. RAG layer: document chunking, embeddings, Qdrant retrieval, and domain-scoped collections.
5. Knowledge graph layer: Neo4j institution/case/evidence/regulation memory.
6. LangGraph layer: agent orchestration and state transitions.
7. LLM layer: Gemini prompts, drafting, review, and embeddings.
8. Background jobs: document indexing and graph sync hooks.

## Request Pipeline

```text
Web / Mobile
  -> FastAPI
  -> LangGraph
  -> Research Agent
  -> Evidence Agent
  -> Strategy Agent
  -> Negotiation Agent
  -> Review Agent
  -> Human Approval Gate
```

The Research Agent consults Qdrant and Neo4j. The Negotiation and Review agents use Gemini-generated outputs, but every external action must remain behind human approval.

## Domain Rollout

`health_insurance` is active first. Future domains are already registered: banking, telecom, airlines, healthcare provider billing, housing, ecommerce, and government.

To activate a domain:

1. Add domain knowledge documents under `knowledge/<domain>/`.
2. Ingest documents into Qdrant using domain-scoped collection `proxy_<domain>`.
3. Add graph node/edge extraction rules for that domain.
4. Add domain prompt instructions in `consumer_advocacy.py`.
5. Add the domain to `ACTIVE_DOMAINS`.
