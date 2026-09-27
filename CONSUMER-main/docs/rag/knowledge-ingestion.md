# Knowledge Ingestion

PROXY is designed to activate domains one by one. The first active domain is `health_insurance`.

## CLI ingestion

```bash
python scripts/ingest_knowledge.py --domain health_insurance
```

By default this reads from:

```text
knowledge/<domain>/
```

Supported file types for the current ingestion path:

- `.md`
- `.txt`
- `.csv`
- `.json`

PDF/OCR ingestion should be added behind the same `KnowledgeIngestionService` boundary.

## API ingestion

```http
POST /api/v1/knowledge/ingest?domain=health_insurance
Authorization: Bearer <token>
```

This indexes chunks into Qdrant and creates knowledge document nodes in Neo4j when those services are configured. If Qdrant or Neo4j is offline, the service returns a successful offline result so local development is not blocked.

## Activating future domains

1. Put domain documents into `knowledge/<domain>/`.
2. Run ingestion for that domain.
3. Add domain-specific prompt guidance in `backend/app/prompts/consumer_advocacy.py`.
4. Add any special graph extraction rules.
5. Add the domain to `ACTIVE_DOMAINS` in `backend/app/models/domain.py`.
