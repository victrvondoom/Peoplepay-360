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
