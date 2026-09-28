create extension if not exists "uuid-ossp";

create type case_domain as enum (
  'health_insurance', 'banking', 'telecom', 'airlines',
  'healthcare_provider', 'housing', 'ecommerce', 'government'
);

create type case_status as enum (
  'draft', 'intake', 'analyzing', 'review_required',
  'ready_for_approval', 'submitted', 'resolved', 'closed'
);

create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  role text not null default 'user',
  created_at timestamptz not null default now()
);

create table if not exists cases (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain case_domain not null default 'health_insurance',
  title text not null,
  institution_name text not null,
  summary text not null,
  jurisdiction text not null default 'US',
  status case_status not null default 'intake',
  risk_score numeric(5,2),
  strategy_confidence numeric(5,2),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists case_documents (
  id uuid primary key default uuid_generate_v4(),
  case_id uuid not null references cases(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  mime_type text,
  storage_path text not null,
  text_extract text,
  indexed boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists case_events (
  id uuid primary key default uuid_generate_v4(),
  case_id uuid not null references cases(id) on delete cascade,
  actor text not null default 'system',
  event_type text not null,
  title text not null,
  body text,
  created_at timestamptz not null default now()
);

create table if not exists agent_runs (
  id uuid primary key default uuid_generate_v4(),
  case_id uuid not null references cases(id) on delete cascade,
  workflow_name text not null,
  status text not null,
  input jsonb not null default '{}'::jsonb,
  output jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now()
);

create table if not exists appeals (
  id uuid primary key default uuid_generate_v4(),
  case_id uuid not null references cases(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  version integer not null default 1,
  title text not null,
  content text not null,
  status text not null default 'draft',
  approved_at timestamptz,
  submitted_at timestamptz,
  created_at timestamptz not null default now()
);

alter table cases enable row level security;
alter table case_documents enable row level security;
alter table case_events enable row level security;
alter table agent_runs enable row level security;
alter table appeals enable row level security;

create policy "Users can manage own cases" on cases for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can manage own documents" on case_documents for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can read own events" on case_events for select using (exists (select 1 from cases where cases.id = case_events.case_id and cases.user_id = auth.uid()));
create policy "Users can read own agent runs" on agent_runs for select using (exists (select 1 from cases where cases.id = agent_runs.case_id and cases.user_id = auth.uid()));
create policy "Users can manage own appeals" on appeals for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index if not exists idx_cases_user_domain on cases(user_id, domain);
create index if not exists idx_cases_institution on cases(domain, institution_name);
create index if not exists idx_documents_case on case_documents(case_id);
create index if not exists idx_events_case_created on case_events(case_id, created_at desc);

create table if not exists knowledge_sources (
  id uuid primary key default uuid_generate_v4(),
  source_id text not null unique,
  domain case_domain not null,
  title text not null,
  source_path text not null,
  filename text,
  category text,
  authority text,
  final_url text,
  content_sha256 text,
  metadata jsonb not null default '{}'::jsonb,
  collected_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists knowledge_chunks (
  id uuid primary key default uuid_generate_v4(),
  source_id text not null references knowledge_sources(source_id) on delete cascade,
  chunk_index integer not null,
  text text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(source_id, chunk_index)
);

alter table knowledge_sources enable row level security;
alter table knowledge_chunks enable row level security;

create policy "Authenticated users can read knowledge sources" on knowledge_sources for select using (auth.role() = 'authenticated');
create policy "Authenticated users can read knowledge chunks" on knowledge_chunks for select using (auth.role() = 'authenticated');

create index if not exists idx_knowledge_sources_domain_category on knowledge_sources(domain, category);
create index if not exists idx_knowledge_chunks_source on knowledge_chunks(source_id);
