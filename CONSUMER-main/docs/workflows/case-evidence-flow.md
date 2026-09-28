# Case Evidence Flow

This is the current healthcare MVP backend flow after a user creates a case.

```text
User uploads denial/policy/notes
  -> FastAPI upload endpoint
  -> StorageService
  -> text extraction for .txt/.md/.csv/.json/text/*
  -> Qdrant case/domain chunk indexing
  -> Neo4j knowledge document node
  -> timeline event
```

Then:

```text
POST /agents/run-case
  -> loads case summary
  -> appends uploaded evidence text
  -> LangGraph-ready workflow
  -> saves agent run
  -> saves appeal draft
  -> marks case ready_for_approval
```

The user approval gate remains mandatory before any external filing or negotiation.
