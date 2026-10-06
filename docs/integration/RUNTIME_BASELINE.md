# Extension runtime baseline — 2026-10-06

- Branch: `master`; HEAD: `68e22002c0902fdbfc4fbcc6cb242981a468c71b`.
- Working tree clean before work; 2,202 tracked paths.
- Existing preservation baseline: `634dd3db73586076bf92648d7e6c32b6260fc9eb`.
- `python scripts/verify_zero_deletion.py`: 1,945 baseline paths, zero missing.
- SDK v1: `packages/peoplepay-extension-sdk/src/peoplepay_sdk/contracts.py`.
- ECHO registry/runtime: `echo/extensions`; separate bounded graph proposal contracts.
- Journey invocation: procurement directly calls providers; assistance uses
  `journey/extension_runtime.py`. These paths need a common invocation gate.
- Existing ECHO manifests: demo-source-a, demo-source-b, inflationforge, civicmesh.
- SDK adapters: GreenChain, InflationForge, CivicMesh, PROXY. Procurement,
  assistance and aftersales have backend contracts; reference procurement is
  explicitly simulated. Native origins and provider credentials are configuration.
- Rumi and InHeir have existing handoff adapters, not general runtime registrations.
- Beacon owns existing action/authority logic; it is not yet a diagnostics provider.
- Specialist navigation and bundled code alone do not establish runtime integration.
- Root baseline suite runs in `.venv-journey-review`; independent specialist
  environments are retained. Results and service health belong in the final report.

Ownership: PeoplePay owns workflows, ECHO owns evidence and decision versions,
Gateway owns authorization/execution, reference merchant owns simulated external
orders. SDK providers return proposals and receive no canonical database handles.
