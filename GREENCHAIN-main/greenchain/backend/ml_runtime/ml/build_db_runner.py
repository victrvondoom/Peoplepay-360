"""build_db_runner.py — runs from /tmp to avoid disk I/O restrictions."""
import os
import shutil
import sqlite3
import sys

# Resolve project root: this file lives at <project>/ml/build_db_runner.py
_THIS_DIR    = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ml.reference_data import (  # noqa: E402  (needs the sys.path entry above)
    EMBER_GRID_INTENSITY, ND_GAIN_RISK, GLEC_FACTORS,
    PORT_COORDINATES, COUNTRY_DEFAULT_PORT, USEEIO_FACTORS,
    get_port_distance
)

db_path = '/tmp/greenchain.db'
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cur  = conn.cursor()

cur.execute("CREATE TABLE ember_grid (country_iso TEXT PRIMARY KEY, grid_gco2_kwh REAL, data_year INTEGER DEFAULT 2022, source TEXT DEFAULT 'Ember Climate 2023')")
cur.executemany("INSERT INTO ember_grid VALUES (?,?,2022,'Ember Climate 2023')", list(EMBER_GRID_INTENSITY.items()))
print(f"ember_grid: {len(EMBER_GRID_INTENSITY)} rows")

cur.execute("CREATE TABLE nd_gain_risk (country_iso TEXT PRIMARY KEY, risk_score REAL, source TEXT DEFAULT 'ND-GAIN Country Index 2022')")
cur.executemany("INSERT INTO nd_gain_risk VALUES (?,?,'ND-GAIN Country Index 2022')", list(ND_GAIN_RISK.items()))
print(f"nd_gain_risk: {len(ND_GAIN_RISK)} rows")

cur.execute("CREATE TABLE glec_factors (mode TEXT PRIMARY KEY, factor_kgco2_tonne_km REAL, source TEXT DEFAULT 'GLEC Framework v3')")
cur.executemany("INSERT INTO glec_factors VALUES (?,?,'GLEC Framework v3')", list(GLEC_FACTORS.items()))
print(f"glec_factors: {len(GLEC_FACTORS)} rows")

cur.execute("CREATE TABLE port_distances (port_a TEXT NOT NULL, port_b TEXT NOT NULL, distance_km REAL, PRIMARY KEY (port_a, port_b))")
ports = list(PORT_COORDINATES.keys())
pairs = []
for i, pa in enumerate(ports):
    for j, pb in enumerate(ports):
        if i <= j:
            d = get_port_distance(pa, pb)
            pairs.append((pa, pb, d))
            if pa != pb:
                pairs.append((pb, pa, d))
cur.executemany("INSERT OR IGNORE INTO port_distances VALUES (?,?,?)", pairs)
print(f"port_distances: {len(pairs)} rows ({len(ports)} ports)")

cur.execute("CREATE TABLE country_ports (country_iso TEXT PRIMARY KEY, default_port TEXT)")
cur.executemany("INSERT INTO country_ports VALUES (?,?)", list(COUNTRY_DEFAULT_PORT.items()))
print(f"country_ports: {len(COUNTRY_DEFAULT_PORT)} rows")

cur.execute("CREATE TABLE useeio_factors (naics2 TEXT PRIMARY KEY, sector_name TEXT, kgco2e_per_usdm REAL, source TEXT DEFAULT 'EPA USEEIO v2.0')")
cur.executemany("INSERT INTO useeio_factors VALUES (?,?,?,'EPA USEEIO v2.0')", [(k, v[0], v[1]) for k, v in USEEIO_FACTORS.items()])
print(f"useeio_factors: {len(USEEIO_FACTORS)} rows")

cur.execute("CREATE TABLE result_cache (cache_key TEXT PRIMARY KEY, result_json TEXT, created_at TEXT, expires_at TEXT)")
cur.execute("CREATE TABLE search_jobs (job_id TEXT PRIMARY KEY, status TEXT DEFAULT 'pending', product TEXT, destination TEXT, filters_json TEXT, result_json TEXT, created_at TEXT, updated_at TEXT)")
print("result_cache + search_jobs: created")

conn.commit()

# Sanity
print("\n── Sanity checks ──")
rows = cur.execute("SELECT country_iso, grid_gco2_kwh FROM ember_grid WHERE country_iso IN ('CN','PT','SE','IN') ORDER BY grid_gco2_kwh").fetchall()
print("Grid intensity (sorted):", rows)
rows = cur.execute("SELECT mode, factor_kgco2_tonne_km FROM glec_factors ORDER BY factor_kgco2_tonne_km").fetchall()
print("GLEC factors:", rows)
row = cur.execute("SELECT distance_km FROM port_distances WHERE port_a='CNSHA' AND port_b='USNYC'").fetchone()
print(f"Shanghai to New York: {row[0]:.0f} km" if row else "port pair missing")
row = cur.execute("SELECT distance_km FROM port_distances WHERE port_a='PTLEI' AND port_b='USNYC'").fetchone()
print(f"Lisbon to New York: {row[0]:.0f} km" if row else "port pair missing")

conn.close()

dest_dir = os.path.join(_PROJECT_ROOT, 'db')
os.makedirs(dest_dir, exist_ok=True)
dest = os.path.join(dest_dir, 'greenchain.db')
try:
    shutil.copy(db_path, dest)
    print(f"\nDB copied to {dest}  ({os.path.getsize(dest)/1024:.1f} KB)")
except Exception as e:
    print(f"Copy failed: {e}  — DB is at {db_path}")
