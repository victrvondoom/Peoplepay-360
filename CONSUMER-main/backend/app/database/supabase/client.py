from functools import lru_cache
from app.core.config import get_settings


class SupabaseGateway:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_service_role_key)

    def client(self):
        if self._client is not None:
            return self._client
        if not self.configured:
            return None
        try:
            from supabase import create_client

            self._client = create_client(self.settings.supabase_url, self.settings.supabase_service_role_key)
            return self._client
        except Exception:
            return None

    async def upsert(self, table: str, payload: dict, on_conflict: str | None = None) -> dict:
        client = self.client()
        if client is None:
            return {"table": table, **payload}
        query = client.table(table).upsert(payload, on_conflict=on_conflict) if on_conflict else client.table(table).upsert(payload)
        result = query.execute()
        rows = getattr(result, "data", None) or []
        return rows[0] if rows else payload

    async def upsert_many(self, table: str, payloads: list[dict], on_conflict: str | None = None, batch_size: int = 100) -> int:
        if not payloads:
            return 0
        client = self.client()
        if client is None:
            return len(payloads)
        written = 0
        for start in range(0, len(payloads), batch_size):
            batch = payloads[start : start + batch_size]
            query = client.table(table).upsert(batch, on_conflict=on_conflict) if on_conflict else client.table(table).upsert(batch)
            query.execute()
            written += len(batch)
        return written

    async def insert(self, table: str, payload: dict) -> dict:
        client = self.client()
        if client is None:
            return {"table": table, **payload}
        result = client.table(table).insert(payload).execute()
        rows = getattr(result, "data", None) or []
        return rows[0] if rows else payload

    async def delete(self, table: str, filters: dict) -> None:
        client = self.client()
        if client is None:
            return
        query = client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        query.execute()

    async def select(self, table: str, filters: dict | None = None, limit: int | None = None) -> list[dict]:
        client = self.client()
        if client is None:
            return []
        query = client.table(table).select("*")
        for key, value in (filters or {}).items():
            query = query.eq(key, value)
        if limit:
            query = query.limit(limit)
        result = query.execute()
        return getattr(result, "data", None) or []

    async def select_owned(self, table: str, user_id: str, filters: dict | None = None) -> list[dict]:
        merged_filters = {"user_id": user_id, **(filters or {})}
        return await self.select(table, merged_filters)

    async def upload_storage(self, bucket: str, path: str, content: bytes, content_type: str) -> str:
        client = self.client()
        if client is None:
            return path
        client.storage.from_(bucket).upload(
            path,
            content,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return path

    async def create_signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        client = self.client()
        if client is None:
            return ""
        result = client.storage.from_(bucket).create_signed_url(path, expires_in)
        if isinstance(result, dict):
            return result.get("signedURL") or result.get("signed_url") or ""
        return ""

    async def download_storage(self, bucket: str, path: str) -> bytes:
        client = self.client()
        if client is None:
            return b""
        return client.storage.from_(bucket).download(path)


@lru_cache
def get_supabase() -> SupabaseGateway:
    return SupabaseGateway()
