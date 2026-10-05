# Zero-deletion and integration verification

Audit date: 5 October 2026. Baseline commit:
`634dd3db73586076bf92648d7e6c32b6260fc9eb` (`master`).

## Preservation result

`python scripts/verify_zero_deletion.py` reported:

```text
Baseline paths: 1945; currently tracked: 1945; missing from worktree: 0
Zero-deletion check passed.
```

The checker compares the baseline Git tree with both the current index and the
working-tree paths, so an unstaged deletion is detected too. The baseline tree
is the complete filename inventory. This check does not assert that tracked
file contents or application behavior are unchanged; reviewed project tests
cover behavior separately.

Git LFS verification completed with `git lfs fsck` → `Git LFS fsck OK`.

## Integration work in this change

- Added the additive `packages/peoplepay-extension-sdk/` Python package with
  bounded versioned request/result, health, metadata/capability, evidence,
  entity, action-proposal and event-envelope contracts.
- Added SDK conformance tests to the root integration test collection and a
  minimal provider example that returns no fabricated results.
- Added the project catalog, baseline, and preservation manifest. The existing
  Gateway workspace and specialist links are documented at their implemented
  scope; no claim is made that every linked app shares a session or forms an
  automated purchase workflow.
- No original project source path was deleted. Original project contents were
  not bulk-copied, flattened, or history-rewritten.

## Verification run

| Scope | Result |
|---|---|
| `python -m pytest -q` | **230 passed** (225 original root tests plus 5 SDK conformance tests). |
| `.venv-echo/Scripts/python.exe -m pytest -q echo/tests` | **107 passed**, one Starlette/httpx deprecation warning. |
| `.venv-echo/Scripts/python.exe -m pip install --no-deps -e packages/peoplepay-extension-sdk` | Editable package build/install passed; provider example imported with SDK version `1`. |
| `python -m compileall -q packages/peoplepay-extension-sdk` | Passed. |
| `git diff --check` | Passed. |
| `git lfs fsck` | Passed. |
| `.venv-echo/Scripts/python.exe -m ruff check ...` | Not run: Ruff is not installed in `.venv-echo`. |

Beacon, GreenChain, InflationForge, PROXY/CONSUMER, Rumi, and InHeir test suites
were not rerun in this change because their sources were not modified. Their
last recorded suite results remain historical; see
[`../test-baseline.md`](../test-baseline.md) and
[`../project-review.md`](../project-review.md). A green integration suite does
not establish production readiness, shared SSO, real merchant checkout, or
end-to-end operation of every specialist service.
