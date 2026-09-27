# Port setup

Create these blueprints in order:

1. `blueprints/inflationforge_item.json`
2. `blueprints/inflationforge_price_snapshot.json`
3. `blueprints/inflationforge_city_comparison.json`

Then add the actions for live sync, item creation, and item retirement. Configure `INFLATIONFORGE_URL` so Port can reach FastAPI.

For the current Port workflow interface, import `workflows/sync_live_prices.json`. Its
manual trigger calls the asynchronous sync endpoint, which acknowledges the job before
Port's webhook deadline while the real collection and catalog publication continue in
the InflationForge worker. Add a scheduled trigger to the same webhook when daily
automatic collection is desired.

InflationForge upserts the governed item catalog, every price snapshot, and each city-item comparison. The Capability Factory’s add/retire operations are therefore visible as catalog state rather than an opaque UI mutation.

Set `PORT_CLIENT_ID`, `PORT_CLIENT_SECRET`, and the correct regional `PORT_API_URL`. Demo organizations that disable client-credential exchange can set `PORT_API_TOKEN` to a generated JWT. If writes fail, the same logical events are persisted to `artifacts/port-events.jsonl` and the app displays `PORT FALLBACK ACTIVE`.
