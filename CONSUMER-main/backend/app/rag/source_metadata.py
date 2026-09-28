"""Looks up the sidecar metadata JSON every scrape/seed script writes next to
each source document (knowledge/<domain>/metadata/<subfolder>/<slug>.json),
so evidence scoring and citations can use authority/category/source_url even
for chunks indexed before the reindex pipeline started embedding this
metadata directly into the vector payload (see reindex_service.py)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.models.domain import Domain

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[3] / "knowledge"


def _sidecar_path(domain: Domain, source_path: str) -> Path:
    rel = Path(source_path)
    return KNOWLEDGE_ROOT / domain.value / "metadata" / rel.parent / f"{rel.stem}.json"


@lru_cache(maxsize=4096)
def _load_cached(domain_value: str, source_path: str) -> tuple[tuple[str, str], ...]:
    domain = Domain(domain_value)
    path = _sidecar_path(domain, source_path)
    if not path.exists():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    return tuple((str(k), str(v)) for k, v in data.items() if isinstance(v, (str, int, float)))


def load_source_metadata(domain: Domain, source_path: str) -> dict:
    """Best-effort sidecar lookup. Returns {} if no sidecar file exists (e.g.
    synthetic/seeded content that never had one, or a domain/path that moved)."""
    if not source_path:
        return {}
    return dict(_load_cached(domain.value, source_path))
