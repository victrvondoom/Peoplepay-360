# Zero-deletion preservation manifest

Baseline: `634dd3db73586076bf92648d7e6c32b6260fc9eb`, 5 October 2026,
1,945 tracked paths. The full original tree remains in Git history and must be
preserved. Changes are additive or targeted modifications; no project directory
is to be flattened or removed.

| Project / tracked paths at baseline | Preserve source, entrypoint, UI, tests, docs and standalone use | PeoplePay role |
|---|---|---|
| `CONSUMER-main/` — 752 | YES | PROXY after-sales/dispute specialist. |
| `GREENCHAIN-main/` — 385 | YES | Supplier discovery and sustainability/logistics analysis. |
| `rumi-main/` — 265 | YES | Room/design and product discovery specialist. |
| `Beacon-main/` — 237 | YES | Internal platform operations and assurance. |
| `inheir.ai-main/` — 129 | YES | Property/legal specialist vertical. |
| `Inflation-Forge-main/` — 65 | YES | Price-context service and scoped ECHO adapter. |
| `echo/` — 46 | YES | Canonical evidence/provenance and decision service. |
| `gateway/`, `transaction/`, `adapters/` — 19 combined | YES | User journey, action coordination, existing transaction lifecycle and service adapters. |
| `tests/` — 10 | YES | Existing root regression coverage. |
| `extensions/` — 6 | YES | Reviewed manifests and provider documentation. |
| `docs/` — 25 | YES | Preserve historical reports and project instructions; add unification records. |
| Root configuration and metadata — 6 | YES | Preserve build, test, LFS, license, and repository configuration. |

## Compatibility policy

- Keep each specialist's original directory, language, dependency lockfiles,
  README, routes, entrypoints, and standalone launch instructions.
- Integrate through adapters, versioned contracts, deep links, and events.
- Use a project's own documented API; if no suitable stable API or license is
  available, record the blocker and keep the integration at a lower level.
- Keep model outputs, estimates, facts, observations, and proposals distinct.
- Never treat a provider manifest as permission to load arbitrary code or
  write graph/transaction state.
- Do not rewrite Git history or force-push. Existing public commits remain the
  provenance record.

## Verification

Run `.venv-echo/Scripts/python.exe scripts/verify_zero_deletion.py` before
finalizing. It compares baseline tracked paths with the current worktree index
and fails if any original tracked path has disappeared. This verifies path
preservation; it does not prove unchanged file contents or behavioral
compatibility. Use the per-project test matrix for those claims.
