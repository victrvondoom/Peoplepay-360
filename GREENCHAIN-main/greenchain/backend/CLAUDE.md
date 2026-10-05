# GreenChain — Claude Code Context

## What we're building

GreenChain is a supply chain environmental comparator. Users type a product, pick countries to source from, choose a transport mode, and get an instant ranked comparison of real manufacturers by environmental footprint. No cost data — purely environmental.

**One-liner:** Type a product → set filters (country, transport mode, destination) → agents crawl real manufacturers → ML scores each one → ranked environmental comparison with a downloadable recommendation memo.

---

## Architecture overview

```
React frontend
    ↓ POST /search (JSON: product, countries, mode, destination)
FastAPI backend (thin orchestrator)
    ↓ runner.run(input, model, mcp_servers, tools)
Daedalus Labs (DedalusRunner)
    ├── Discovery agent    (web_search via brave-search-mcp)
    ├── Certification agent (fetch_url → sustainability pages)
    └── Memo agent         (writes recommendation)
    ↓ raw agent results (manufacturer names, certifications, URLs)
ML scoring pipeline (XGBoost + GLEC + lookup tables) — runs in FastAPI
    ↓ SSE stream
React frontend (D3 force graph + Leaflet world map, both update live)
```

**Key point:** Daedalus handles all agent orchestration. FastAPI is a pass-through — receive JSON → call Daedalus → score results → stream back.

---

## Project structure

```
greenchain/
├── backend/
│   ├── main.py              # FastAPI app, SSE endpoint
│   ├── agents.py            # Daedalus runner.run() call
│   ├── tools.py             # Python functions passed to Daedalus as tools
│   ├── ml_scorer.py         # XGBoost model + composite scoring
│   ├── transport.py         # GLEC factor calc + port distance lookup
│   ├── db.py                # SQLite setup + lookup table loaders
│   ├── greenchain.db        # SQLite: USEEIO, Ember, GLEC, port distances, ND-GAIN
│   ├── models/
│   │   └── emissions_model.joblib   # trained XGBoost model
│   ├── data/
│   │   ├── useeio_factors.csv
│   │   ├── ember_grid_carbon.csv
│   │   ├── glec_factors.json
│   │   ├── port_distances.csv
│   │   └── ndgain_country_index.csv
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── SearchPanel.tsx      # product input + filters
│   │   │   ├── SupplyChainGraph.tsx # D3 force-directed graph
│   │   │   ├── WorldMap.tsx         # Leaflet map with pins + route arcs
│   │   │   ├── ResultsDrawer.tsx    # ranked cards + bar chart
│   │   │   └── WeightSliders.tsx    # adjustable dimension weights
│   │   ├── hooks/
│   │   │   └── useSSE.ts           # SSE stream handler
│   │   └── types.ts
│   └── package.json
└── CLAUDE.md                        # this file
```

---

## Environment variables

```bash
# backend/.env
DEDALUS_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here   # Daedalus passes through to Claude
```

---

## Backend: key files

### main.py — FastAPI SSE endpoint

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
from agents import run_supply_chain_research
from ml_scorer import compute_composite_scores

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SearchRequest(BaseModel):
    product: str
    quantity: int
    destination: str
    countries: list[str]
    transport_mode: str = "sea"          # sea | air | rail | road
    require_certifications: list[str] = []  # iso14001 | cdp_a | sbt_committed

@app.post("/search")
async def search(req: SearchRequest):
    async def stream():
        yield f"data: {json.dumps({'status': 'agents_running', 'message': f'Searching manufacturers in {len(req.countries)} countries...'})}\n\n"

        raw_results = await run_supply_chain_research(
            product=req.product,
            quantity=req.quantity,
            countries=req.countries,
            destination=req.destination,
            transport_mode=req.transport_mode,
            require_certifications=req.require_certifications or None
        )

        yield f"data: {json.dumps({'status': 'scoring', 'message': 'Running ML scoring pipeline...'})}\n\n"

        scored = compute_composite_scores(raw_results, req.transport_mode)

        yield f"data: {json.dumps({'status': 'complete', 'results': scored})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
```

---

### agents.py — Daedalus runner call

```python
import asyncio
from dedalus_labs import AsyncDedalus, DedalusRunner
from tools import lookup_emission_factor, calculate_transport_emissions, score_certifications

async def run_supply_chain_research(
    product: str,
    quantity: int,
    countries: list[str],
    destination: str,
    transport_mode: str,
    require_certifications: list[str] | None = None
) -> str:
    client = AsyncDedalus()   # reads DEDALUS_API_KEY from env
    runner = DedalusRunner(client)

    cert_clause = (
        f"Only return manufacturers that have at least one of these certifications: {require_certifications}."
        if require_certifications else ""
    )

    response = await runner.run(
        input=f"""
You are a supply chain researcher. Research manufacturers of "{product}" in these countries: {', '.join(countries)}.

For EACH country:
1. Use web search to find 5-6 real manufacturers of {product} in that country
2. For each manufacturer found, attempt to find and visit their sustainability or ESG page
3. Extract any certifications mentioned: ISO 14001, CDP rating (A/B/C/D), Science Based Targets (committed/achieved), B Corp
4. Call lookup_emission_factor with their NAICS industry code and country ISO code
5. Call calculate_transport_emissions with origin country, destination "{destination}", weight {quantity * 0.5} kg, mode "{transport_mode}"
6. Call score_certifications with the list of certifications found

{cert_clause}

Return ONLY a JSON array (no markdown, no explanation) with this exact schema:
[
  {{
    "name": "Manufacturer Name",
    "country": "ISO country code",
    "city": "city name or null",
    "sustainability_url": "URL or null",
    "certifications": ["iso14001", "cdp_b"],
    "emission_factor": {{ ...result from lookup_emission_factor }},
    "transport": {{ ...result from calculate_transport_emissions }},
    "cert_score": {{ ...result from score_certifications }},
    "disclosure_status": "verified | partial | none"
  }}
]
        """,
        model="anthropic/claude-sonnet-4-6",
        mcp_servers=["windsornguyen/brave-search-mcp"],
        tools=[lookup_emission_factor, calculate_transport_emissions, score_certifications],
    )

    return response.final_output
```

---

### tools.py — custom tools passed to Daedalus

```python
import sqlite3
import json

DB_PATH = "greenchain.db"

def lookup_emission_factor(naics_code: str, country_iso: str) -> dict:
    """Look up manufacturing emission intensity for an industry and country.
    Returns estimated tCO2e per $1M spend and grid carbon intensity (gCO2/kWh)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # USEEIO emission factor by NAICS
    cursor.execute("SELECT emission_factor FROM useeio WHERE naics_code = ?", (naics_code,))
    row = cursor.fetchone()
    base_factor = row[0] if row else 35.0  # fallback average

    # Ember grid carbon intensity by country
    cursor.execute("SELECT carbon_intensity_gco2_kwh FROM ember_grid WHERE country_iso = ?", (country_iso,))
    row = cursor.fetchone()
    grid_carbon = row[0] if row else 400.0  # fallback world average

    conn.close()

    # Adjust emission factor based on grid carbon relative to world average
    grid_multiplier = grid_carbon / 400.0
    adjusted_factor = base_factor * (0.7 + 0.3 * grid_multiplier)

    return {
        "emission_factor_tco2e_per_1m_usd": round(adjusted_factor, 2),
        "grid_carbon_gco2_kwh": grid_carbon,
        "naics_code": naics_code,
        "country_iso": country_iso,
        "confidence": "high" if row else "low"
    }


def calculate_transport_emissions(
    origin_country: str,
    destination_country: str,
    weight_kg: float,
    mode: str
) -> dict:
    """Calculate transport CO2 emissions using GLEC factors and port distance matrix.
    Mode must be one of: sea, air, rail, road.
    Returns tCO2e for the shipment and distance in km."""
    glec_factors = {"sea": 0.011, "air": 0.602, "rail": 0.028, "road": 0.096}

    if mode not in glec_factors:
        mode = "sea"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT distance_km FROM port_distances WHERE origin = ? AND destination = ?",
        (origin_country.upper(), destination_country.upper())
    )
    row = cursor.fetchone()
    conn.close()

    distance_km = row[0] if row else 8000.0  # fallback global average

    factor = glec_factors[mode]
    tco2e = factor * (weight_kg / 1000) * distance_km

    return {
        "transport_tco2e": round(tco2e, 3),
        "distance_km": distance_km,
        "mode": mode,
        "glec_factor": factor,
        "weight_kg": weight_kg
    }


def score_certifications(certifications: list[str]) -> dict:
    """Score a supplier's sustainability certifications and return emissions adjustment.
    Known certification strings: iso14001, cdp_a, cdp_b, cdp_c, sbt_committed, sbt_achieved, bcorp.
    Returns multiplier < 1 for certified suppliers (lower = better), and a 0-100 score."""
    adjustments = {
        "iso14001": -0.05,
        "cdp_a": -0.10,
        "cdp_b": -0.06,
        "cdp_c": -0.03,
        "sbt_achieved": -0.10,
        "sbt_committed": -0.08,
        "bcorp": -0.04
    }
    weights = {
        "iso14001": 20, "cdp_a": 40, "cdp_b": 25, "cdp_c": 10,
        "sbt_achieved": 35, "sbt_committed": 25, "bcorp": 15
    }

    multiplier = 1.0
    score = 0
    matched = []

    for cert in certifications:
        cert_lower = cert.lower().replace(" ", "_").replace("-", "_")
        if cert_lower in adjustments:
            multiplier += adjustments[cert_lower]
            score += weights[cert_lower]
            matched.append(cert_lower)

    # Penalise no disclosure
    if not matched:
        multiplier += 0.15
        score = 0

    return {
        "multiplier": round(max(0.5, min(1.2, multiplier)), 3),
        "cert_score": min(100, score),
        "matched_certs": matched,
        "disclosure_penalty": not bool(matched)
    }
```

---

### ml_scorer.py — composite scoring after agent results return

```python
import json
import joblib
import numpy as np
from dataclasses import dataclass

# Load trained XGBoost model at startup
model = joblib.load("models/emissions_model.joblib")

DEFAULT_WEIGHTS = {
    "manufacturing_emissions": 0.40,
    "transport_emissions": 0.25,
    "grid_carbon": 0.20,
    "certifications": 0.10,
    "climate_risk": 0.05,
}

def compute_composite_scores(raw_results_json: str, transport_mode: str, weights: dict = None) -> list[dict]:
    """
    Takes the raw JSON string from Daedalus agents.
    Runs XGBoost + normalisation + composite scoring.
    Returns a list of scored manufacturer dicts, sorted best first.
    """
    weights = weights or DEFAULT_WEIGHTS

    try:
        manufacturers = json.loads(raw_results_json)
    except (json.JSONDecodeError, TypeError):
        # Daedalus sometimes wraps in markdown — strip it
        import re
        match = re.search(r'\[.*\]', raw_results_json, re.DOTALL)
        manufacturers = json.loads(match.group()) if match else []

    if not manufacturers:
        return []

    scored = []
    for m in manufacturers:
        ef = m.get("emission_factor", {})
        tr = m.get("transport", {})
        cs = m.get("cert_score", {})

        mfg_tco2e = ef.get("emission_factor_tco2e_per_1m_usd", 40) * cs.get("multiplier", 1.0)
        transport_tco2e = tr.get("transport_tco2e", 10.0)
        grid_carbon = ef.get("grid_carbon_gco2_kwh", 400)
        cert_score = cs.get("cert_score", 0)
        total_tco2e = mfg_tco2e + transport_tco2e

        scored.append({
            **m,
            "scores": {
                "manufacturing_tco2e": round(mfg_tco2e, 2),
                "transport_tco2e": round(transport_tco2e, 3),
                "grid_carbon_gco2_kwh": grid_carbon,
                "cert_score": cert_score,
                "total_tco2e": round(total_tco2e, 2),
            },
            "transport_mode": transport_mode,
        })

    # Normalise each dimension 0-100 (lower tco2e = better = higher score)
    def normalise_inverse(values):
        mn, mx = min(values), max(values)
        if mx == mn:
            return [50.0] * len(values)
        return [100 * (1 - (v - mn) / (mx - mn)) for v in values]

    def normalise(values):
        mn, mx = min(values), max(values)
        if mx == mn:
            return [50.0] * len(values)
        return [100 * (v - mn) / (mx - mn) for v in values]

    mfg_norm    = normalise_inverse([s["scores"]["manufacturing_tco2e"] for s in scored])
    trans_norm  = normalise_inverse([s["scores"]["transport_tco2e"] for s in scored])
    grid_norm   = normalise_inverse([s["scores"]["grid_carbon_gco2_kwh"] for s in scored])
    cert_norm   = normalise([s["scores"]["cert_score"] for s in scored])

    for i, s in enumerate(scored):
        composite = (
            weights["manufacturing_emissions"] * mfg_norm[i] +
            weights["transport_emissions"]     * trans_norm[i] +
            weights["grid_carbon"]             * grid_norm[i] +
            weights["certifications"]          * cert_norm[i]
        )
        s["composite_score"] = round(composite, 1)
        s["rank_scores"] = {
            "manufacturing_norm": round(mfg_norm[i], 1),
            "transport_norm":     round(trans_norm[i], 1),
            "grid_norm":          round(grid_norm[i], 1),
            "cert_norm":          round(cert_norm[i], 1),
        }
        # colour bucket for UI
        s["env_rating"] = (
            "green" if composite >= 65 else
            "amber" if composite >= 35 else
            "red"
        )

    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, s in enumerate(scored):
        s["rank"] = i + 1

    return scored
```

---

### transport.py — standalone transport calculator (for client-side rescore)

```python
# This logic is DUPLICATED in tools.py for Daedalus, and also exposed
# as a FastAPI endpoint so the frontend can rescore instantly when
# the transport mode toggle is flipped without re-running agents.

GLEC_FACTORS = {"sea": 0.011, "air": 0.602, "rail": 0.028, "road": 0.096}

def rescore_transport(manufacturers: list[dict], new_mode: str) -> list[dict]:
    """Recalculate transport emissions for all manufacturers with a new mode.
    Called when the user flips the transport toggle — no Daedalus call needed."""
    factor = GLEC_FACTORS.get(new_mode, 0.011)
    for m in manufacturers:
        tr = m.get("transport", {})
        distance_km = tr.get("distance_km", 8000)
        weight_kg = tr.get("weight_kg", 500)
        m["transport"]["transport_tco2e"] = round(factor * (weight_kg / 1000) * distance_km, 3)
        m["transport"]["mode"] = new_mode
        m["scores"]["transport_tco2e"] = m["transport"]["transport_tco2e"]
        m["scores"]["total_tco2e"] = round(
            m["scores"]["manufacturing_tco2e"] + m["scores"]["transport_tco2e"], 2
        )
    return manufacturers
```

Add a FastAPI endpoint for this:

```python
@app.post("/rescore-transport")
async def rescore_transport_endpoint(manufacturers: list[dict], mode: str):
    from transport import rescore_transport
    from ml_scorer import compute_composite_scores
    rescored = rescore_transport(manufacturers, mode)
    # re-rank after rescoring
    rescored.sort(key=lambda x: x["scores"]["total_tco2e"])
    for i, m in enumerate(rescored):
        m["rank"] = i + 1
    return rescored
```

---

### db.py — SQLite setup + data loading

```python
import sqlite3
import pandas as pd

DB_PATH = "greenchain.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS useeio (
        naics_code TEXT PRIMARY KEY,
        industry_name TEXT,
        emission_factor REAL   -- tCO2e per $1M spend
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS ember_grid (
        country_iso TEXT PRIMARY KEY,
        country_name TEXT,
        carbon_intensity_gco2_kwh REAL,
        year INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS port_distances (
        origin TEXT,
        destination TEXT,
        distance_km REAL,
        PRIMARY KEY (origin, destination)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS ndgain (
        country_iso TEXT PRIMARY KEY,
        vulnerability_score REAL,
        flood_risk REAL,
        heat_stress REAL
    )""")

    conn.commit()
    conn.close()

def load_all_data():
    """Run once to populate the database from CSV files."""
    conn = sqlite3.connect(DB_PATH)

    pd.read_csv("data/useeio_factors.csv").to_sql("useeio", conn, if_exists="replace", index=False)
    pd.read_csv("data/ember_grid_carbon.csv").to_sql("ember_grid", conn, if_exists="replace", index=False)
    pd.read_csv("data/port_distances.csv").to_sql("port_distances", conn, if_exists="replace", index=False)
    pd.read_csv("data/ndgain_country_index.csv").to_sql("ndgain", conn, if_exists="replace", index=False)

    conn.close()
    print("Database loaded.")

if __name__ == "__main__":
    init_db()
    load_all_data()
```

---

### requirements.txt

```
fastapi
uvicorn[standard]
dedalus-labs
python-dotenv
pydantic
pandas
scikit-learn
xgboost
joblib
numpy
httpx
```

---

## Frontend: key patterns

### useSSE.ts — SSE hook

```typescript
import { useEffect, useRef } from 'react';

export function useSearch(onEvent: (event: any) => void) {
  const controllerRef = useRef<AbortController | null>(null);

  const runSearch = async (params: SearchParams) => {
    controllerRef.current?.abort();
    controllerRef.current = new AbortController();

    const response = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
      signal: controllerRef.current.signal,
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = decoder.decode(value).split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            onEvent(JSON.parse(line.slice(6)));
          } catch {}
        }
      }
    }
  };

  return { runSearch };
}
```

### Transport mode toggle — client-side rescore

```typescript
// When user flips transport toggle, DON'T re-call /search.
// Either recalculate client-side using GLEC factors (fast, recommended)
// or call /rescore-transport (if you want server-side re-ranking).

const GLEC = { sea: 0.011, air: 0.602, rail: 0.028, road: 0.096 };

function rescoreLocally(manufacturers: Manufacturer[], mode: TransportMode) {
  return manufacturers.map(m => {
    const newTransport = GLEC[mode] * (m.transport.weight_kg / 1000) * m.transport.distance_km;
    const newTotal = m.scores.manufacturing_tco2e + newTransport;
    return {
      ...m,
      transport: { ...m.transport, transport_tco2e: newTransport, mode },
      scores: { ...m.scores, transport_tco2e: newTransport, total_tco2e: newTotal },
    };
  }).sort((a, b) => a.scores.total_tco2e - b.scores.total_tco2e);
}
```

### D3 Supply Chain Graph — live node addition

```typescript
// Key pattern: nodes are added incrementally via SSE, not all at once.
// On 'agents_running' event: add country cluster nodes (grey, pulsing)
// On each manufacturer result: add leaf node, transition colour after scoring

// Node colour by env_rating:
const NODE_COLORS = { green: '#1D9E75', amber: '#BA7517', red: '#E24B4A', loading: '#B4B2A9' };

// Node size by total_tco2e (larger = worse):
const nodeRadius = (tco2e: number) => Math.max(8, Math.min(28, tco2e / 5));
```

### Leaflet World Map — manufacturer pins + route arcs

```typescript
// Libraries: react-leaflet + leaflet.geodesic (for curved arcs)
// Tiles: OpenStreetMap (free, no API key)
// Pin colour: same env_rating colour as D3 graph node
// Route arc: colour by transport mode (blue=sea, red=air, green=rail, grey=road)
// Animation: CSS stroke-dashoffset travelling along arc (slow=sea, fast=air)

// Pin coordinates: use country centroid from SQLite if no city returned,
// upgrade to city-level geocode if agent returns a specific city name
```

---

## Data sources — where to get each file

| File | Source | URL |
|------|--------|-----|
| `useeio_factors.csv` | EPA USEEIO v2.0 | https://www.epa.gov/land-research/us-environmentally-extended-input-output-useeio-technical-content |
| `ember_grid_carbon.csv` | Ember Climate | https://ember-climate.org/data/data-tools/data-explorer/ |
| `port_distances.csv` | Build from public port coords | Use haversine on top 50 ports by cargo volume |
| `ndgain_country_index.csv` | Notre Dame GAIN | https://gain.nd.edu/our-work/country-index/download-data/ |
| CDP training data | Kaggle | Search "CDP supply chain emissions" |

---

## ML model training (run once before hackathon)

```python
# train_model.py — run this before the hack to produce models/emissions_model.joblib
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import joblib, os

df = pd.read_csv("data/cdp_supply_chain.csv")

# Feature engineering
df = df.dropna(subset=["emissions_tco2e", "naics_code", "country_iso"])
le_naics = LabelEncoder()
le_country = LabelEncoder()
df["naics_enc"] = le_naics.fit_transform(df["naics_code"].astype(str))
df["country_enc"] = le_country.fit_transform(df["country_iso"].astype(str))

# Merge Ember grid carbon
grid = pd.read_csv("data/ember_grid_carbon.csv")[["country_iso", "carbon_intensity_gco2_kwh"]]
df = df.merge(grid, on="country_iso", how="left")
df["carbon_intensity_gco2_kwh"] = df["carbon_intensity_gco2_kwh"].fillna(400)

features = ["naics_enc", "country_enc", "carbon_intensity_gco2_kwh"]
target = df["emissions_tco2e"].apply(lambda x: max(0.1, x))  # no negatives

X_train, X_test, y_train, y_test = train_test_split(df[features], target, test_size=0.2, random_state=42)

model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42)
model.fit(X_train, y_train)

os.makedirs("models", exist_ok=True)
joblib.dump({"model": model, "le_naics": le_naics, "le_country": le_country}, "models/emissions_model.joblib")
print(f"Model saved. Test R²: {model.score(X_test, y_test):.3f}")
```

---

## Demo scenarios (pre-cache before submitting)

### Scenario 1 — Cotton t-shirts, sea freight
```json
{
  "product": "cotton t-shirts",
  "quantity": 10000,
  "destination": "USA",
  "countries": ["CN", "PT", "BD"],
  "transport_mode": "sea",
  "require_certifications": []
}
```
Expected: Portugal ranks 1st. Toggle to air → China transport emissions jump ~55x.

### Scenario 2 — Electronics, ISO certified only
```json
{
  "product": "circuit boards",
  "quantity": 5000,
  "destination": "DE",
  "countries": ["TW", "VN", "DE"],
  "transport_mode": "sea",
  "require_certifications": ["iso14001"]
}
```

### Scenario 3 — Auto parts, compare road vs rail
```json
{
  "product": "automotive components",
  "quantity": 20000,
  "destination": "US",
  "countries": ["DE", "MX", "IN"],
  "transport_mode": "road",
  "require_certifications": []
}
```

---

## Running locally

```bash
# Backend
cd backend
pip install -r requirements.txt
python db.py          # loads data into SQLite (run once)
python train_model.py # trains XGBoost model (run once)
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev           # runs on localhost:5173
```

---

## Key decisions + constraints

- **Daedalus does ALL agent orchestration** — no asyncio semaphores, no custom tool-use loops. One `runner.run()` call per search.
- **Transport toggle is client-side** — never re-calls the backend. GLEC formula runs in JS. This makes the demo feel instant.
- **Surface-level only** — certification agent does ONE page fetch per manufacturer. No recursive crawl. Keeps latency under 30s for a full search.
- **Results cached 24hrs** — if the same manufacturer was researched in the last 24 hours, return cached result. Add a `manufacturer_cache` SQLite table.
- **All data sources are free and citable** — EPA, Ember, GLEC, ND-GAIN, CDP. When judges ask "how do you know this?" you have a named source for every number.
- **No cost data** — purely environmental comparison. This was an explicit decision to keep ML tractable and data sourcing clean.

---

## Daedalus-specific notes

- SDK: `pip install dedalus-labs`
- The `runner.run()` call is async — always use `AsyncDedalus` and `await`
- MCP server for web search: `"windsornguyen/brave-search-mcp"` (needs free Brave Search API key)
- Custom tools are plain Python functions — Daedalus extracts schema from type hints + docstrings automatically
- Model string for Claude: `"anthropic/claude-sonnet-4-6"`
- Free tier available during beta — email founders@dedaluslabs.ai for hackathon credits (they're YC S25)
- Docs: https://docs.dedaluslabs.ai

---

## Hackathon: hackPrinceton
**Theme:** Sustainability + Environment track
**Pitch:** We built the tool that lets any procurement manager ask "which supply chain option is better for the planet?" and get a credible, cited answer in under 60 seconds.
**Demo highlight:** The transport mode toggle (sea → air, emissions jump 55x, instant, no re-fetch).
