# Bright Data

InflationForge uses Bright Data SERP API to discover and validate the public city-price source surface on every collection.

```bash
BRIGHT_DATA_API_TOKEN=...
BRIGHT_DATA_ZONE=serp_api1
```

The request uses `POST https://api.brightdata.com/request` with the configured zone. Success produces `BRIGHT DATA SERP DISCOVERY + LIVE WEB`. A rejected or unavailable query is attached to the trace and source status, and the UI explicitly reports the live-web fallback.

Price values are then fetched from the discovered public city pages and paired with Internet Archive captures. Bright Data is never claimed as the price transport when it did not answer.
