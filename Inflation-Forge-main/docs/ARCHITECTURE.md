# Architecture

InflationForge is backend-first. The browser only maps persisted comparisons; it never invents or recalculates source evidence.

## Collection trace

```text
inflationforge.sync
├── bright_data.discover
├── city.fetch.current × 16
├── archive.resolve/cache_hit × 16
├── city.fetch.previous × 16
├── price.normalize
├── snapshot.persist
└── port.sync
```

Each `PriceObservation` contains city, item, year, normalized USD value, original source row, original price, conversion multiplier, exact URL, retrieval timestamp, observation timestamp, and archive timestamp. A `CityPriceComparison` is created only when both years exist.

`CityInflationSummary` is computed at read time from each city's active item comparisons. It is an equal-weight geometric mean of price relatives and is explicitly labeled as a derived basket, not official CPI.

## Failure contract

- Bright Data discovery failure → live public source collection continues and the mode says `BRIGHT DATA FALLBACK ACTIVE`.
- A city’s current or historical page fails → the city is named in `failed_cities`; no placeholder prices are created.
- Port write failure → identical payloads go to `artifacts/port-events.jsonl` and the UI says `PORT FALLBACK ACTIVE`.
- SigNoz failure → local JSONL evidence remains active.

## Capability Factory

An item is configuration: source label, display name, category, canonical unit, multiplier, owner, version and hash. Creation requires an exact match in the latest live source catalog. Retirement is soft, so evidence remains reproducible.
