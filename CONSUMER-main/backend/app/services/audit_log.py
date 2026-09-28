"""Audit log for admin/privileged actions -- who did what, when, with what
result. Append-only jsonl, same durable-local-file pattern used elsewhere in
this project (see app.database.postgres.repositories.LocalRepositoryStore).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_PATH = Path("datasets") / "audit_log.jsonl"


def record_audit_event(actor_id: str, action: str, details: dict[str, Any] | None = None) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "action": action,
        "details": details or {},
    }
    with _LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True, default=str) + "\n")


def read_audit_log(limit: int = 200) -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    entries = []
    for line in _LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries[-limit:]
