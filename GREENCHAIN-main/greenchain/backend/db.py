"""
db.py
-----
SQLite schema + connection helpers for GreenChain.

Notes:
  - The ML layer (`ml/reference_data.py`) holds the authoritative lookup
    tables for Ember grid intensity, ND-GAIN risk, GLEC factors, and USEEIO
    factors. It loads them from CSVs at import time.
  - The SQLite DB here is used for:
      * discovery_cache        — TTL cache of agent manufacturer discovery
      * search_audit           — log of every /search request for replay
      * scenario_edit_history  — prompt-edit revisions per scenario
      * dataset_intakes        — uploaded scenario CSV metadata
  - The legacy schema (useeio / ember_grid / port_distances / ndgain) from
    CLAUDE.md is kept for compatibility / judges, but the runtime does not
    depend on it.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).parent / ".env")


def get_db_path() -> str:
    env_path = os.environ.get("DB_PATH")
    if env_path:
        return env_path
    # Fall back to local SQLite inside backend/.
    return str(Path(__file__).parent / "greenchain.db")

@contextmanager
def connect():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the runtime tables. Safe to call repeatedly."""
    with connect() as conn:
        c = conn.cursor()

        # Cache of agent discovery output, keyed by a hash of the discovery
        # parameters. TTL is enforced in Python (see cache_get).
        c.execute("""
            CREATE TABLE IF NOT EXISTS discovery_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS dataset_intakes (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS search_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                countries TEXT NOT NULL,
                transport_mode TEXT NOT NULL,
                destination TEXT NOT NULL,
                duration_seconds REAL,
                result_count INTEGER,
                created_at REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS scenario_edit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id TEXT NOT NULL,
                parent_id INTEGER,
                op_type TEXT NOT NULL,
                prompt_text TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_active INTEGER NOT NULL,
                FOREIGN KEY(parent_id) REFERENCES scenario_edit_history(id)
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_scenario_edit_history_scenario_active
            ON scenario_edit_history (scenario_id, is_active, id DESC)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_scenario_edit_history_parent
            ON scenario_edit_history (parent_id)
        """)

        # Legacy/CLAUDE.md schema — kept for parity. Runtime does NOT read these.
        c.execute("""
            CREATE TABLE IF NOT EXISTS useeio (
                naics_code TEXT PRIMARY KEY,
                industry_name TEXT,
                emission_factor REAL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ember_grid (
                country_iso TEXT PRIMARY KEY,
                country_name TEXT,
                carbon_intensity_gco2_kwh REAL,
                year INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS port_distances (
                origin TEXT,
                destination TEXT,
                distance_km REAL,
                PRIMARY KEY (origin, destination)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ndgain (
                country_iso TEXT PRIMARY KEY,
                vulnerability_score REAL,
                flood_risk REAL,
                heat_stress REAL
            )
        """)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def cache_ttl_seconds() -> float:
    """Discovery cache TTL from GREENCHAIN_DISCOVERY_CACHE_TTL_HOURS (default 24; 0 disables)."""
    raw = os.environ.get("GREENCHAIN_DISCOVERY_CACHE_TTL_HOURS", "").strip()
    try:
        hours = float(raw) if raw else 24.0
    except ValueError:
        hours = 24.0
    return max(hours, 0.0) * 60 * 60


def cache_get(cache_key: str) -> str | None:
    """Return the cached payload for `cache_key`, or None if missing/expired/disabled."""
    ttl = cache_ttl_seconds()
    if ttl <= 0:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT payload_json, created_at FROM discovery_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    if time.time() - row["created_at"] > ttl:
        return None
    return row["payload_json"]


def cache_put(cache_key: str, payload_json: str) -> None:
    if cache_ttl_seconds() <= 0:
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO discovery_cache (cache_key, payload_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key)
            DO UPDATE SET payload_json = excluded.payload_json, created_at = excluded.created_at
            """,
            (cache_key, payload_json, time.time()),
        )


def create_dataset_intake(
    *,
    intake_id: str,
    filename: str,
    stored_path: str,
    row_count: int,
    status: str,
    schema_version: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dataset_intakes
                (id, filename, stored_path, row_count, status, schema_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (intake_id, filename, stored_path, row_count, status, schema_version, time.time()),
        )


def audit_search(
    product: str,
    countries: list[str],
    transport_mode: str,
    destination: str,
    duration_seconds: float,
    result_count: int,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO search_audit
                (product, countries, transport_mode, destination,
                 duration_seconds, result_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product,
                ",".join(countries),
                transport_mode,
                destination,
                duration_seconds,
                result_count,
                time.time(),
            ),
        )


def get_active_scenario_revision(scenario_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, scenario_id, parent_id, op_type, prompt_text, snapshot_json, created_at, is_active
            FROM scenario_edit_history
            WHERE scenario_id = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (scenario_id,),
        ).fetchone()


def get_scenario_revision(revision_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, scenario_id, parent_id, op_type, prompt_text, snapshot_json, created_at, is_active
            FROM scenario_edit_history
            WHERE id = ?
            """,
            (revision_id,),
        ).fetchone()


def get_baseline_scenario_revision(scenario_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT id, scenario_id, parent_id, op_type, prompt_text, snapshot_json, created_at, is_active
            FROM scenario_edit_history
            WHERE scenario_id = ? AND op_type = 'baseline'
            ORDER BY id ASC
            LIMIT 1
            """,
            (scenario_id,),
        ).fetchone()


def ensure_scenario_history_baseline(
    scenario_id: str,
    snapshot_json: str,
    prompt_text: str = "[baseline]",
) -> sqlite3.Row:
    existing_baseline = get_baseline_scenario_revision(scenario_id)
    if existing_baseline is not None:
        return existing_baseline

    with connect() as conn:
        conn.execute(
            """
            UPDATE scenario_edit_history
            SET is_active = 0
            WHERE scenario_id = ?
            """,
            (scenario_id,),
        )
        cursor = conn.execute(
            """
            INSERT INTO scenario_edit_history
                (scenario_id, parent_id, op_type, prompt_text, snapshot_json, created_at, is_active)
            VALUES (?, NULL, 'baseline', ?, ?, ?, 1)
            """,
            (scenario_id, prompt_text, snapshot_json, time.time()),
        )
        revision_id = cursor.lastrowid

    row = get_scenario_revision(revision_id) if revision_id is not None else None
    if row is None:
        raise RuntimeError("Failed to create baseline scenario history revision.")
    return row


def append_scenario_revision(
    scenario_id: str,
    parent_id: int | None,
    op_type: str,
    prompt_text: str,
    snapshot_json: str,
) -> sqlite3.Row:
    with connect() as conn:
        conn.execute(
            """
            UPDATE scenario_edit_history
            SET is_active = 0
            WHERE scenario_id = ?
            """,
            (scenario_id,),
        )
        cursor = conn.execute(
            """
            INSERT INTO scenario_edit_history
                (scenario_id, parent_id, op_type, prompt_text, snapshot_json, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (scenario_id, parent_id, op_type, prompt_text, snapshot_json, time.time()),
        )
        revision_id = cursor.lastrowid

    row = get_scenario_revision(revision_id) if revision_id is not None else None
    if row is None:
        raise RuntimeError("Failed to append scenario history revision.")
    return row


def count_scenario_revisions(scenario_id: str) -> int:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS revision_count
            FROM scenario_edit_history
            WHERE scenario_id = ?
            """,
            (scenario_id,),
        ).fetchone()
    return int(row["revision_count"]) if row else 0


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {get_db_path()}")
