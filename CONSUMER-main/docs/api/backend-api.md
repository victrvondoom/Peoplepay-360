# REST API Specification

Base path: `/api/v1`

All protected endpoints require:

```http
Authorization: Bearer <supabase-jwt>
```

During local development, the bearer token is treated as a user id placeholder.

## Auth

- `GET /auth/me` returns the current user.

## Domains

- `GET /domains` returns all registered domains and whether each is active.

## Cases

- `POST /cases` creates a case. Currently only `health_insurance` is active.
- `GET /cases` lists user cases. Optional query: `domain`.
- `GET /cases/{case_id}` returns a case.
- `POST /cases/{case_id}/events` appends a timeline event.

## Upload And Case Evidence

- `POST /upload/{case_id}/documents` uploads a document.
- `GET /upload/{case_id}/documents` lists uploaded documents.

Text-like uploads (`.txt`, `.md`, `.csv`, `.json`, or `text/*`) are extracted immediately, indexed into Qdrant under the case/domain, and mirrored into Neo4j as knowledge document nodes. PDF/OCR support should be added behind the same storage service boundary.

## Timeline

- `GET /timeline/{case_id}` lists case lifecycle events: case creation, document upload, agent run, appeal draft, and future submission events.

## Appeals

- `GET /appeals/{case_id}` lists generated appeal drafts for a case.

Appeals are drafts until the user approves them. No external submission should happen automatically.

## Search/RAG

- `POST /search` searches domain-scoped Qdrant knowledge.

## Knowledge Graph

- `GET /graph/patterns?domain=health_insurance&institution_name=...` returns institutional memory patterns.

## Knowledge Ingestion

- `POST /knowledge/ingest?domain=health_insurance` ingests files from `knowledge/<domain>/` into Qdrant and Neo4j.

## Agents

- `POST /agents/run-case` runs Research, Graph enrichment, Evidence, Strategy, Negotiation, and Review agents.
- `GET /agents/runs/{case_id}` lists persisted agent runs.

Agent runs now use uploaded document text as additional case evidence. The output is persisted as an agent run, and the negotiation draft is saved as an appeal draft when requested.

## WebSockets

- `WS /ws/cases/{case_id}` streams case updates. Current scaffold echoes messages and confirms connection.
