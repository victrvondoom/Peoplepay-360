"""
build_db.py
-----------
Builds greenchain.db — the SQLite database backing all lookup tables and
the result cache.

Tables:
  ember_grid      — country electricity carbon intensity (gCO2/kWh)
  nd_gain_risk    — climate physical risk score per country
  glec_factors    — transport emission factors per mode
  port_distances  — port-to-port distance matrix (km)
  useeio_factors  — industry emission intensity by NAICS2
  result_cache    — cached scored comparisons (24hr TTL)

Run:
    python ml/build_db.py
Output:
    db/greenchain.db
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.reference_data import (
    EMBER_GRID_INTENSITY, ND_GAIN_RISK, GLEC_FACTORS,
    PORT_COORDINATES, COUNTRY_DEFAULT_PORT, USEEIO_FACTORS,
    get_port_distance
)

DB_PATH = "db/greenchain.db"


def build_db(db_path: str = DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Remove existing DB to rebuild clean
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # ── 1. Ember grid intensity ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE ember_grid (
            country_iso TEXT PRIMARY KEY,
            grid_gco2_kwh REAL NOT NULL,
            data_year INTEGER DEFAULT 2022,
            source TEXT DEFAULT 'Ember Climate 2023'
        )
    """)
    cur.executemany(
        "INSERT INTO ember_grid VALUES (?, ?, 2022, 'Ember Climate 2023')",
        [(k, v) for k, v in EMBER_GRID_INTENSITY.items()]
    )
    print(f"  ember_grid: {len(EMBER_GRID_INTENSITY)} rows")

    # ── 2. ND-GAIN risk ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE nd_gain_risk (
            country_iso TEXT PRIMARY KEY,
            risk_score  REAL NOT NULL,     -- 0=low risk, 100=high risk
            source TEXT DEFAULT 'ND-GAIN Country Index 2022'
        )
    """)
    cur.executemany(
        "INSERT INTO nd_gain_risk VALUES (?, ?, 'ND-GAIN Country Index 2022')",
        [(k, v) for k, v in ND_GAIN_RISK.items()]
    )
    print(f"  nd_gain_risk: {len(ND_GAIN_RISK)} rows")

    # ── 3. GLEC transport factors ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE glec_factors (
            mode        TEXT PRIMARY KEY,
            factor_kgco2_tonne_km REAL NOT NULL,
            source TEXT DEFAULT 'GLEC Framework v3'
        )
    """)
    cur.executemany(
        "INSERT INTO glec_factors VALUES (?, ?, 'GLEC Framework v3')",
        [(k, v) for k, v in GLEC_FACTORS.items()]
    )
    print(f"  glec_factors: {len(GLEC_FACTORS)} rows")

    # ── 4. Port distance matrix (compute all pairs) ──────────────────────────
    cur.execute("""
        CREATE TABLE port_distances (
            port_a      TEXT NOT NULL,
            port_b      TEXT NOT NULL,
            distance_km REAL NOT NULL,
            PRIMARY KEY (port_a, port_b)
        )
    """)
    ports = list(PORT_COORDINATES.keys())
    pairs = []
    for i, pa in enumerate(ports):
        for pb in ports[i:]:
            d = get_port_distance(pa, pb)
            pairs.append((pa, pb, d))
            if pa != pb:
                pairs.append((pb, pa, d))
    cur.executemany("INSERT INTO port_distances VALUES (?, ?, ?)", pairs)
    print(f"  port_distances: {len(pairs)} rows ({len(ports)} ports)")

    # ── 5. Country default port mapping ─────────────────────────────────────
    cur.execute("""
        CREATE TABLE country_ports (
            country_iso TEXT PRIMARY KEY,
            default_port TEXT NOT NULL
        )
    """)
    cur.executemany(
        "INSERT INTO country_ports VALUES (?, ?)",
        list(COUNTRY_DEFAULT_PORT.items())
    )
    print(f"  country_ports: {len(COUNTRY_DEFAULT_PORT)} rows")

    # ── 6. USEEIO emission factors ───────────────────────────────────────────
    cur.execute("""
        CREATE TABLE useeio_factors (
            naics2      TEXT PRIMARY KEY,
            sector_name TEXT NOT NULL,
            kgco2e_per_usdm REAL NOT NULL,
            source TEXT DEFAULT 'EPA USEEIO v2.0'
        )
    """)
    cur.executemany(
        "INSERT INTO useeio_factors VALUES (?, ?, ?, 'EPA USEEIO v2.0')",
        [(k, v[0], v[1]) for k, v in USEEIO_FACTORS.items()]
    )
    print(f"  useeio_factors: {len(USEEIO_FACTORS)} rows")

    # ── 7. Result cache ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE result_cache (
            cache_key   TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE search_jobs (
            job_id      TEXT PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'pending',
            product     TEXT,
            destination TEXT,
            filters_json TEXT,
            result_json  TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """)
    print("  result_cache: created (empty)")
    print("  search_jobs: created (empty)")

    conn.commit()
    conn.close()
    size_kb = os.path.getsize(db_path) / 1024
    print(f"\nDatabase built → {db_path}  ({size_kb:.1f} KB)")


def query_example(db_path: str = DB_PATH):
    """Quick sanity check queries."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    print("\n── Sanity checks ──")

    cur.execute("SELECT country_iso, grid_gco2_kwh FROM ember_grid WHERE country_iso IN ('CN','PT','SE','IN') ORDER BY grid_gco2_kwh")
    print("Grid intensity (CN/PT/SE/IN):", cur.fetchall())

    cur.execute("SELECT country_iso, risk_score FROM nd_gain_risk WHERE country_iso IN ('CN','PT','BD','DE') ORDER BY risk_score")
    print("Risk scores:", cur.fetchall())

    cur.execute("SELECT mode, factor_kgco2_tonne_km FROM glec_factors ORDER BY factor_kgco2_tonne_km")
    print("GLEC factors:", cur.fetchall())

    cur.execute("SELECT distance_km FROM port_distances WHERE port_a='CNSHA' AND port_b='USNYC'")
    row = cur.fetchone()
    print(f"Shanghai → New York: {row[0]:.0f} km" if row else "Not found")

    cur.execute("SELECT distance_km FROM port_distances WHERE port_a='PTLEI' AND port_b='USNYC'")
    row = cur.fetchone()
    print(f"Lisbon → New York: {row[0]:.0f} km" if row else "Not found")

    conn.close()


if __name__ == "__main__":
    build_db()
    query_example()
