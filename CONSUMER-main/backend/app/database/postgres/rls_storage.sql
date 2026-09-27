-- Apply in Supabase SQL editor after creating the private storage bucket `case-documents`.
-- Folder layout: {user_id}/{case_id}/{document_id}-{filename}

insert into storage.buckets (id, name, public)
values ('case-documents', 'case-documents', false)
on conflict (id) do update set public = false;

create policy "Users can upload own case documents"
on storage.objects for insert
with check (
  bucket_id = 'case-documents'
  and auth.uid()::text = (storage.foldername(name))[1]
);

create policy "Users can read own case documents"
on storage.objects for select
using (
  bucket_id = 'case-documents'
  and auth.uid()::text = (storage.foldername(name))[1]
);

create policy "Users can delete own case documents"
on storage.objects for delete
using (
  bucket_id = 'case-documents'
  and auth.uid()::text = (storage.foldername(name))[1]
);
