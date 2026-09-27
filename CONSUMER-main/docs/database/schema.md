# Database Schema

Primary database: Supabase PostgreSQL.

Tables:

- `profiles`: user metadata and role.
- `cases`: dispute record, domain, status, institution, jurisdiction, confidence fields.
- `case_documents`: uploaded document metadata and OCR/text extraction.
- `case_events`: case timeline/audit events.
- `agent_runs`: immutable record of agent workflow inputs/outputs/errors.
- `appeals`: generated complaint/appeal drafts and approval/submission state.

Security:

- Row Level Security is enabled on user-owned tables.
- Users can only manage their own cases, documents, and appeals.
- Agent runs and events are readable only through ownership of the parent case.

Schema file: `backend/app/database/postgres/schema.sql`.
