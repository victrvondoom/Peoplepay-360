# Public launch: 50,000 daily visitors

50,000 visits per day averages less than one page visit per second, but InflationForge is designed for short launch-day bursts rather than the average.

## What is already in the application

- Dashboard responses are CDN-cacheable for 60 seconds and can be served stale for five minutes during origin trouble.
- Immutable observation receipts are cacheable for one year.
- Static assets are cacheable and every response over 500 bytes is compressed.
- Live collection is single-flight and a complete snapshot is reused for five minutes, so visitors do not trigger a scrape each.
- Map tile URL, attribution, and maximum zoom are deployment configuration, not hard-coded application logic.
- Price collection, normalization, persistence, and cache hits remain visible in SigNoz.

## Recommended launch topology

```text
Visitors → CDN / WAF → InflationForge API → SQLite (single origin)
                  ↘ commercial or self-hosted map tile CDN

Scheduled collector → Bright Data + live pages + Internet Archive
                  ↘ SigNoz OTLP
                  ↘ Port catalog
```

Put Cloudflare, Fastly, or an equivalent CDN in front of the single origin. Cache `GET /api/dashboard` using its response headers, cache `/static/*`, allow normal browser caching for map tiles, and rate-limit mutation routes. A scheduled process should call `POST /api/prices/sync`; public visitors only need reads.

For a multi-replica or zero-downtime deployment, replace SQLite with a shared database before scaling the API horizontally. The current single-origin SQLite setup is intentionally optimized for a reliable hackathon demo, not active-active writes.

## Map capacity

The default OpenStreetMap tile endpoint is suitable for local development only. Before a public launch, set `MAP_TILE_URL`, `MAP_ATTRIBUTION`, and `MAP_MAX_ZOOM` to a commercial plan or self-hosted tile service sized for the traffic. Do not remove visible OpenStreetMap attribution when the provider uses OSM data.
