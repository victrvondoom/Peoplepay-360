# PROXY Architecture

PROXY is a multi-platform consumer advocacy system. Users enter through the web or mobile app, the FastAPI backend owns API/security/orchestration, LangGraph coordinates the agent workflow, and Supabase/Qdrant/Neo4j/Gemini provide persistence, retrieval, graph memory, and model intelligence.

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
                  |
      +-----------+-----------+
      |           |           |
      v           v           v
  Supabase     Qdrant       Neo4j
(Postgres,    (Vector     (Knowledge
 Auth,        Search)       Graph)
 Storage)
                  |
                  v
              LangGraph
                  |
                  v
              Gemini API
```

## Case Processing Pipeline

```text
Web / Mobile
    |
    v
FastAPI
    |
    v
LangGraph
    |
    v
Research Agent
    |
    v
Evidence Agent
    |
    v
Strategy Agent
    |
    v
Negotiation Agent
    |
    v
Review Agent
    |
    v
Human Approval Gate
    |
    v
Supabase + Qdrant + Neo4j + Gemini-backed outputs
```

## Current Domain Strategy

The active domain is healthcare/health insurance. The system already registers all future domains, but only `health_insurance` is active until knowledge is added and validated.

Future domains:

- airlines
- telecom
- banking
- healthcare provider billing
- housing
- ecommerce
- government

Each new domain should add documents to `knowledge/<domain>/`, index them into Qdrant under `proxy_<domain>`, add graph extraction rules for Neo4j, and then activate the domain in `backend/app/models/domain.py`.
