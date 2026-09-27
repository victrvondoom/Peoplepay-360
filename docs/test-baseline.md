# Test baseline — before integration

Recorded 2026-09-27, immediately after `git init`, before any integration code.
Purpose: prove later that integration did not break what already worked (§39).

| Project | Result | Notes |
|---|---|---|
| **Beacon** | **307 passed, 1 failed, 12 errors** | `test_assurance_core.py` **79/79 green** — the layer we build on. Failures are environmental: 6 files fail at *collection* with `SSLError` (network fetch at import), `test_local_server.py` (6 errors) needs a live local server, `test_hardening.py::test_image_requirement_pins_match_the_tested_environment` fails on pinned-image drift. None are logic failures. |
| **InflationForge** | **18 passed** | Required installing `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http`, which were missing from the environment. Green after that. |
| **PROXY (CONSUMER)** | **38 passed, 3 failed** | 3 failures in `test_domain_corpora.py` — local corpora files absent. 3 files (`test_api`, `test_auth`, `test_case_analysis`) fail collection with a **pre-existing** bug: `ValueError: 'strategy' is already being used` (duplicate registration at import). Not caused by us. |
| **Rumi** | **NOT RUN — blocked** | Tests require `bun test`; **Bun is not installed** (node 24.14.0 / npm 11.14.1 available). 44 test files unexecuted. Integration against Rumi therefore goes through its `shared/` Zod contracts, read statically. |
| **InHeir** | **NO TESTS** | `backend/tests/` contains only `__init__.py`. Zero coverage — pre-existing. |

## Pre-existing defects found (not introduced by integration)

1. PROXY: duplicate `'strategy'` registration breaks 3 test files at collection.
2. Beacon: 6 test files perform network I/O at import time, so they cannot run offline.
3. InHeir: no test coverage at all, yet it is to be wired into a money path.
4. InflationForge: `opentelemetry` is imported transitively by every test via `services/telemetry/otel.py`, so one missing optional dep takes down the whole suite.
