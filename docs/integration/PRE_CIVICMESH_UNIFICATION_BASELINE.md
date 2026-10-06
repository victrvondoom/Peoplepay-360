# Pre-CivicMesh unification baseline

Captured 2026-10-06 before CivicMesh integration code edits.

- Baseline commit: `53e22eebceb7e194fb3769eff4a3d10979fca4e5`
- Tracked paths: 1987
- Added CivicMesh files: 167 (untracked user supplied source, preserved separately).
- Source path: `CivicMesh-main/`; no nested .git metadata was supplied.
- Core: `journey/`; trust core: `echo/`; action authority: `gateway/`, `transaction/`; SDK: `packages/peoplepay-extension-sdk/`.
- Bounded projects: GreenChain, InflationForge, Rumi, PROXY (CONSUMER), InHeir, Beacon, CivicMesh.
- Existing journey: GreenChain + InflationForge -> ECHO -> version-bound approval -> sandbox merchant -> PROXY; CivicMesh has no integration at capture.
- Latest reproduced root check: 373 passed. Existing published check counts are historical; each changed component will be checked again.
- Existing failures under repair: native PROXY lint setup prompt; Beacon missing lint command; InHeir client lifecycle/lint and backend document/client bugs; InflationForge typing/collection failures; IDE mixed Python environments.
- Existing changes below were in progress before the CivicMesh mission; none are discarded.

## Commands

`git rev-parse HEAD`, `git ls-files`, `git status --short`, `python scripts/verify_zero_deletion.py`, `git lfs fsck`.

## Working changes at capture

```text
 M .gitignore
 M Beacon-main/web/package-lock.json
 M Beacon-main/web/package.json
 M CONSUMER-main/frontend/package-lock.json
 M CONSUMER-main/frontend/package.json
 M Inflation-Forge-main/backend/main.py
 M Inflation-Forge-main/backend/services/factory/items.py
 M Inflation-Forge-main/backend/services/inflation/collector.py
 M Inflation-Forge-main/backend/services/inflation/service.py
 M inheir.ai-main/frontend/package.json
 M inheir.ai-main/frontend/src/app/home/case/[id]/page.tsx
 M inheir.ai-main/frontend/src/app/home/layout.tsx
 M inheir.ai-main/frontend/src/app/home/new/case/page.tsx
 M inheir.ai-main/frontend/src/app/home/page.tsx
 M inheir.ai-main/frontend/src/app/home/report/dashboard/page.tsx
 M inheir.ai-main/frontend/src/app/page.tsx
 M inheir.ai-main/frontend/src/lib/components/AuthForm.tsx
 M inheir.ai-main/frontend/src/lib/components/Cases.tsx
 M inheir.ai-main/frontend/src/lib/components/Chatbot.tsx
 M inheir.ai-main/frontend/src/lib/components/CreateCaseForm.tsx
?? Beacon-main/web/eslint.config.js
?? CONSUMER-main/frontend/eslint.config.mjs
?? CivicMesh-main/
?? Inflation-Forge-main/backend/tests/test_collection_recovery.py
?? inheir.ai-main/backend/pytest.ini
?? inheir.ai-main/backend/tests/test_native_services.py
?? output/
```

The existing zero-deletion checker uses the earlier 1945-path baseline. The JSON companion additionally captures all 1987 current tracked paths and every supplied CivicMesh file with its SHA-256 for preservation checks.
