# Licensing blockers

**Status:** Open. Two of five projects cannot be redistributed.
**Date:** 2026-09-27
**Verified:** by reading each project's `LICENSE` file and `package.json` on disk.

This file records what was found. It does not resolve anything, and per §37
**no licence was added to anybody else's project** to make integration easier.

---

## 1. Findings

| Project | Licence | Copyright holder | Integration status | Required action |
|---|---|---|---|---|
| `Beacon-main` | **Apache-2.0** | (standard Apache text; holder not named in file) | **Integrated.** Phase 1–4 code lives here. | None |
| `Inflation-Forge-main` | **MIT** | Kaushik Sivakumar (2026) | Not yet integrated | None for licensing. Attribution required on redistribution. |
| `inheir.ai-main` | **MIT** | InHeir.AI (2025) | Not yet integrated | None for licensing. Attribution required on redistribution. |
| `CONSUMER-main` (PROXY) | **NONE** | Unknown — not stated anywhere in the repo | **BLOCKED.** Pattern studied; no code copied. | Owner must add an explicit licence. |
| `rumi-main` | **NONE** | Unknown — not stated anywhere in the repo | **BLOCKED.** Not touched. | Owner must add an explicit licence. |

Checked for both blocked projects and found nothing to infer permission from:

- no `LICENSE` / `LICENCE` file at any level
- no `license` field in `package.json`
- no copyright header naming terms

Absent a licence grant, default copyright applies: **all rights reserved.** The
code may be read where it was lawfully obtained, but not copied, modified or
redistributed as part of a product.

---

## 2. What this blocked, concretely

Phase 3 needed PROXY's memory design. Because PROXY is unlicensed, the
implementation took the **only** route that does not copy protected expression:

- PROXY's `memory_service.py` was **read** to learn its *interface shape* — the
  three layers, and the four read functions.
- `beacon/peoplepay/memory.py` was then **written from scratch**, in Beacon's
  own repository under Apache-2.0, with its own implementation.
- The method names deliberately match (`get_conversation_memory`,
  `get_user_memory`, `format_for_prompt`) so a future adapter is a thin bridge.
  Names and interface facts are not the copyrightable part; the implementation
  is, and none of it was taken.

No line of PROXY or Rumi source is present in `beacon/peoplepay/`.

---

## 2a. Audit: `adapters/spatial.py` vs B1 — **CLEARED**

**Date:** 2026-09-27. Raised by `phase-1-4-report.md` §9 because this adapter
targets Rumi, which is unlicensed. Audited line by line.

**Finding: no copied expression. Safe to keep under §3's service-boundary rule.**

| Checked | Result |
|---|---|
| Geometry algorithms reimplemented in Python? | **No.** Zero `math.*` calls, no area/polygon computation. It defers to Rumi's `free-floor.ts` and `geometry/index.ts` by design and says so. |
| How does it obtain room data? | **HTTP only** — `urllib.request` via one private `_get()`. It is a client of a service Rumi's owners run. |
| Any Rumi source copied? | **No.** No TypeScript translated to Python. |
| Any Rumi values copied? | **One:** `RUMI_DOOR_CLEARANCE_M = 0.9`, matching `rumi-main/shared/planner/space.ts:52` (`DOOR_CLEARANCE = 0.9`). |

**On that one constant.** A single unadorned numeric fact — a 0.9 m door
clearance — is not protectable expression; it is a measurement, and it is
attributed to its source in a comment rather than passed off as ours. The
surrounding logic (`max(clearance, door_width)`) was written independently even
though Rumi computes the same thing, and the adapter names it as *mirroring*
Rumi rather than deriving from it.

**Residual risk: low, but not zero.** If Rumi's owners consider their clearance
rules proprietary, the honest fix is to fetch the value from Rumi's API instead
of hard-coding it. That is a one-line change and worth making if a licence
negotiation turns adversarial. Noted rather than pre-emptively done, because
fetching a constant over HTTP on every call has its own cost.

**Unchanged conclusion:** the adapter may stay. It must not grow a Python
reimplementation of Rumi's planner, which is the line §3 draws.

---

## 2b. Audit: `adapters/resolution.py` vs B1 — **CLEARED**

**Date:** 2026-09-27. `CONSUMER-main` (PROXY) is the *other* unlicensed project,
so its adapter needs the same audit the spatial one got.

**Finding: no copied expression. Safe under §3's service-boundary rule.**

| Checked | Result |
|---|---|
| PROXY's agent logic ported to Python? | **No.** No LangGraph, LangChain, Gemini or supervisor code. The only mention of that stack is a docstring noting it runs *in PROXY*, with PROXY's own credentials. |
| How does it reach PROXY? | **HTTP only** — `urllib.request`. A client of a service its owners operate. |
| Any prompt text or corpus copied? | **No.** |
| Interface facts recorded? | Yes — endpoint shapes only, which is what §3 permits. |

**A design property worth keeping.** The adapter caps every drafted artifact at
`EvidenceClass.UNVERIFIED` and sets `requires_human_review: True` — verified as
enforced at all six construction sites, not merely promised in the docstring. The
reasoning is right: *an appeal letter is an argument the user may choose to send,
not a fact about the world.* PROXY's deterministic citation verifier is carried
across as a separate, narrower signal rather than averaged into the draft's
credibility.

**Still blocked for distribution.** Clearing the adapter does not clear PROXY. The
capability only works when someone runs PROXY, and that party needs a licence to
do so lawfully as part of a product.

---

## 3. Rule going forward

Until a licence exists for `CONSUMER-main` and `rumi-main`:

1. **Do not copy their source** into Beacon or any distributable artifact.
2. Integrate them only across a **service boundary** — HTTP to a separately
   deployed process, which each owner runs under their own terms.
3. Record any interface learned from them here, as above.
4. **Never** add, change or infer a licence on their behalf (§37).

An HTTP call to a service someone else operates is not redistribution. Vendoring
their code into this repository would be.

---

## 4. Open questions for the owners

1. `rumi-main` — will it be licensed, and under what terms? Apache-2.0 or MIT
   both combine cleanly with Beacon.
2. `CONSUMER-main` — same question. This one matters more: PROXY is the
   dispute/resolution engine, and the resolution path is otherwise unimplemented.
3. For both: who holds copyright? Individual contributors, or an entity?
4. If either cannot be licensed, the capability must be rebuilt from scratch or
   dropped from scope. That is a product decision, not a technical one.
