# Official Healthcare Data Sources

The Health Insurance MVP must use official, authoritative sources only. The source registry lives at:

```text
knowledge/health_insurance/official_sources/source_registry.json
```

## Priority Sources

1. IRDAI Document Library: regulations, circulars, official documents.
2. IRDAI Health Department: health insurance guidance and FAQs.
3. IRDAI Policyholder Portal: consumer rights, health insurance FAQs, complaints, grievance guidance.
4. Official insurer websites: policy wordings, claim forms, network hospitals.
5. WHO and MedlinePlus: disease and treatment knowledge only.

## Collection Command

```bash
python scripts/collect_health_official_sources.py
```

Smoke test one source:

```bash
python scripts/collect_health_official_sources.py --limit 1 --skip-ingest
```

The collector:

- refuses non-allowlisted domains
- saves markdown text with source metadata front matter
- saves JSON metadata per source
- preserves citation URL and collection hash
- stores source/chunk records through the Supabase/Postgres repository boundary
- runs ingestion into Qdrant and Neo4j unless `--skip-ingest` is used

## API Visibility

```http
GET /api/v1/knowledge/sources?domain=health_insurance
```

## Important Rule

WHO and MedlinePlus can explain medical context. They should not be used as the basis for saying an insurer violated a claim rule. Insurance obligation arguments should come from IRDAI, policy wordings, claim forms, and policyholder guidance.
