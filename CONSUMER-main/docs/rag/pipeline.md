# RAG Pipeline

Current healthcare-first pipeline:

1. Upload document through `/upload/{case_id}/documents`.
2. OCR/PDF parser extracts text.
3. `chunk_text` splits text into overlapping chunks.
4. Gemini embedding model embeds chunks.
5. Chunks are inserted into Qdrant collection `proxy_health_insurance`.
6. Research Agent retrieves case-relevant clauses and regulations.
7. Review Agent checks generated claims against retrieved citations.

Future domains use the same pipeline with separate collections:

- `proxy_banking`
- `proxy_telecom`
- `proxy_airlines`
- `proxy_healthcare_provider`
- `proxy_housing`
- `proxy_ecommerce`
- `proxy_government`
