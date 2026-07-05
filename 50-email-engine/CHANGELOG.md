# Changelog — Skill 50 (email-engine)

## 1.1.0 — 2026-07-05 — F4.3 email-style ↔ canonical persona crosswalk (train DEP-7)

Train **DEP-7**. Fix IDs: F4.3.

### Added
- **`tools/persona_canonical.py`** — crosswalks the resolved email tone-STYLE id to a REAL
  canonical persona id via `shared-utils/persona-crosswalk.json` `email_persona_styles` (the same
  crosswalk mechanism skills 06/44 use), so an email selection joins the persona
  adherence/learning loop. The email matcher keeps its role as the style-tier chooser.
- The **PROCESS-CERTIFICATE** now carries a `canonical_persona` block (id + name + Section-4
  excerpt) when the resolved style maps to a library persona. Not part of `certificate_sha`
  (computed over the explicit sha source), so determinism is unchanged.

### Notes
- Only styles with a genuine canonical counterpart are mapped (7 of 12). A style with no library
  persona (e.g. Tony Robbins ≠ the library's Mel Robbins; Iyanla / Les Brown / Lisa Nichols /
  Gladwell / Brené have no library persona) is intentionally unmapped and keeps its style-tier
  behavior — never a fabricated mapping.

## 1.0.4 — 2026-07-05 — shared mc_board board review-skip root fix (FIX-XC-01a)

### Changed
- **`mc_board.py` (shared helper, byte-identical across 49/50/53/55/56/57):** the producer no longer
  PATCHes a run's Command Center card straight to `done`. `complete_run` now posts the terminal status
  `review` ("certified — awaiting QC promotion") with the deliverable link registered on the card;
  `card_advance(status="done")` is HARD-BLOCKED. `review -> done` is owned exclusively by the
  independent QC scorer (PASS >= 8.5). Ports the CC `LEGAL_TRANSITIONS` map + BFS legal-path walker +
  current-status GET from `48-facebook-ad-generator/scripts/cc_board.py`, and honors
  `CC_STATUS_PATH_TEMPLATE` / `CC_STATUS_METHOD` for route parity. Still fully fail-soft — the board
  is a VIEW, never a gate.

### Added
- **`test_cc_contract.py` (byte-identical):** stdlib contract test proving `complete_run` posts
  `review` and never `done`, the legal-path walk, route-template parity, and disabled-board no-op.
