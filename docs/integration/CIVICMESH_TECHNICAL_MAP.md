# CivicMesh technical map

Inspected from the supplied `CivicMesh-main/` source on 2026-10-06. Its original 167 files are unchanged.

| Native area | Entry / responsibility | PeoplePay boundary |
|---|---|---|
| Jac app | `civicmesh/app.jac`, `app.sv.jac`, `frontend.cl.jac`, `frontend.impl.jac`; React client and server walkers | Preserved standalone; PeoplePay has a native assistance page, not an iframe |
| Intake | `walkers/intake.jac`; parse, profile merge, bounded optional model routing, graph writes, eligibility, navigation, critique | The deterministic service receives a controlled need and minimal structured facts; no original conversation |
| Rules | `engine/policy.jac`, `data/resources.json`, `data/hud_income_limits.json`; dated poverty/HUD/SNAP/status rules and local estimates | Native policy functions remain authoritative for the provider; ECHO records references and version/date |
| Eligibility | `engine/score.jac`; hard gates, weighted soft fit, missing facts, tiers, counterfactuals, information value | Scores remain heuristic estimates; `calibrated_probability: false`, no verified eligibility claim |
| Plan and routes | `engine/plan.jac`, `engine/paths.jac`, `data/transitions.json`; ordered steps and graph routes | Advisory ActionProposals; no application submission or payment execution |
| Language | `engine/i18n.jac`, `facts_i18n.jac`, `messages.jac`, `data/i18n/*`, `llm/translate.jac` | Original catalogs preserved; reply-language preference is passed; PeoplePay routing currently uses English intent patterns |
| Memory and graph | `graph/nodes.jac`, `graph/edges.jac`, `walkers/memory.jac`, `critique.jac` | Native visitor graph is not mirrored. The integration endpoint is stateless and correlated by workflow ID |
| Safety/privacy | `engine/parse.jac`, `privacy.jac`, `cmguard/*`; crisis pins, redaction, budgets, tokens, private model behavior, anonymous visitor isolation | Native crisis rank/pin logic runs without a model. Service uses dedicated bearer authentication, bounded structured input, per-workflow rate limiting |
| Specialist HTTP | `cmguard/serve.py`, `gateway.py`, `jacbind.py`; guarded front door, internal Jac listener, generated secrets | Original full UI remains on its own runtime/7860; deterministic integration API uses 8092 |
| Optional models | `llm/stubs.jac`, `narrate.jac`, localization walkers; provider pools and bounded calls | Not imported or invoked by the deterministic PeoplePay integration |
| Tests | `tests/eval_engine.jac`, golden sets, schema/persona/privacy Jac tests, cmguard Python tests, browser/security scripts | Native deterministic evaluator and Python guard tests executed; full specialist graph/UI/model suites have separate dependencies |
| Portable export | `tools/eject_engine.sh`; `jac jac2py` export and no-Jac verification | Inspected, not selected. Integration imports original Jac modules through Jac's import hook |

The thin service in `extensions/civicmesh/service.py` invokes `parse_intake`, `rank_resources`, `build_plan`, `plan_routes`, `policy_today`, and `policy_sources` from these original modules. It does not reimplement eligibility or copy generated Python into ECHO.

Policy declarations and their cited verification date are upstream assertions. The integration marks them as bundled references, not live government verification. Native pseudoprobability fields are retained for audit with an explicit uncalibrated flag.
