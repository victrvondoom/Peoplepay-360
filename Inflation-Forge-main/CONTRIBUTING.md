# Contributing to InflationForge

Thanks for helping make public price intelligence more inspectable.

## Ground rules

- Never invent, interpolate, or silently substitute price observations.
- Preserve the exact source URL, raw label, raw price, timestamp, and normalization multiplier.
- Keep validation and source-acceptance rules deterministic.
- Label fallbacks truthfully in the API, UI, and telemetry.
- Add fast tests for parsing, comparison, factory, or telemetry behavior.

## Development

```bash
cp .env.example .env
make install
make test
make demo
```

Before opening a pull request, run `make test`, describe the data-source implications, and include a screenshot for visual changes.

Good first contributions include source adapters, broader city coverage, additional deterministic normalizations, accessibility improvements, and SigNoz dashboards.
