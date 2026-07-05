# Changelog — Skill 57 (social-media-in-a-box)

## 0.2.4 — 2026-07-05 — F4.3 C10 persona INPUT adapter SHIPPED (train DEP-7)

Train **DEP-7**. Fix IDs: F4.3.

### Added
- **C10 persona INPUT adapter IMPLEMENTED** (`scripts/persona_adapter.py`) — previously a
  fail-closed stub deferred to v0.5.0. `personaSource:adapter` now routes the week's brand/theme
  context through the ONE shared entry point `shared-utils/persona_for_job.py` (canonical 5-layer
  selection, LOGGED); `personaSource:client-choice` returns the client's expressly-named persona
  **verbatim, FINAL, never judged** (client sovereignty); `personaSource:config` is the unchanged
  baseline. The resolved persona is written to `working/copy/persona-selection.json` and surfaced
  on the certificate's creative block (`canonical_persona`) — ABSENT on the config path so a
  default week stays byte-for-byte identical.

### Changed
- `persona-adapter` removed from the DEFER map (`defer_stub.py`, `run_social_media._DEFERRED`,
  `SOCIAL-MANIFEST.json` AF-SM-DEFERRED text, `client-config.schema.json` personaSource doc). An
  explicitly-requested `adapter`/`client-choice` that cannot resolve fails CLOSED (never a silent
  no-op); baseline `config` is never blocked. Remaining deferrals (narrated-video C8, syndicate C9,
  memory-adapter C11) are unchanged.

## 0.2.3 — 2026-07-05 — shared mc_board board review-skip root fix (FIX-XC-01a)

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
