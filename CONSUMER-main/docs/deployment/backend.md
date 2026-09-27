# Deployment

Local services:

```bash
docker compose up --build
```

Backend only:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production checklist:

- Set Supabase project URL and service role key.
- Run `backend/app/database/postgres/schema.sql` in Supabase SQL editor.
- Create private Supabase Storage bucket `case-documents`.
- Configure Qdrant persistence and backups.
- Configure Neo4j password and private network access.
- Set Gemini API key or managed model provider.
- Replace development auth placeholder with Supabase JWT verification.
- Move rate limiting from in-memory middleware to Redis.
- Enable structured logs and error monitoring.
