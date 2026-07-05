# Changelog — Sales Page Assets (Skill 56)

## 1.1.0 — real gates, image-prompt floor, copy/code split, routed department
Wave-0 merge-train **T-56-salespage** (master fix-plan 2026-07-05). Every change is scoped to
this skill's own directory (conflict-free merge).

- **FIX-XC-03b — artifact-backed P5/P6/P8/P9 gates.** `run_sales_page_assets.py` P5/P6/P8 were
  unconditional no-ops and P9 was existence-only; a certificate could mint with zero fragments,
  Docs, delivery record, or build receipt. Now each gate MEASURES a real artifact, fail-closed:
  P5 requires a non-empty fragment file per non-bump funnel-manifest step (`AF-SP56-FRAGMENT-MISSING`);
  P6 requires a `drive_docs.json` Track-1 manifest (`AF-SP56-DOCS-MISSING`); P8 requires a
  productionized (non-test) `delivery.json` subject + folder link (`AF-SP56-DELIVER-MISSING`/`-SUBJECT`);
  P9 requires a `build_receipt.json` with non-empty preview URLs and build QC >= 8.5
  (`AF-SP56-BUILD-RECEIPT`). Orchestrator self-test + golden reproducer materialize the artifacts.
- **FIX-XC-04c — split copy from code + per-section word bands.** `prompts/baked/01-starter-page-prompt.md`
  no longer writes copy AND a full HTML page in one completion: STEP A emits an approved per-section
  `copy_ledger.json` FIRST, STEP B renders the approved copy into HTML and authors nothing. The
  explicit MAIN 8-section copy spec (per-section intent + word band) is restored. Added SACRED
  per-section `word_min` floors to `structure/sales_page_structure.json` (main + upsell-1); the
  structure provers now MEASURE the stripped section copy (`AF-SP56-MAIN-SECTION-BAND`,
  `AF-SP56-UPSELL-SECTION-BAND`), measured-not-self-reported.
- **FIX-XC-04e — image-prompt strength gate.** New `scripts/prove_sp_prompt_floor.py` (cloned from
  Skill 49's two-floor gate): 5,000–19,000 stripped chars, >= 220 distinct words, a brand-grade
  block fingerprint PARAMETERIZED on `${INTAKE.primary_brand_color}` (`AF-SP56-PROMPT-BRANDCOLOR`),
  a `Do not…` negative block, em-dash ban, and typography lock. Wired as the second P1 gate; added
  to `SPA-PROVER-PIN.sha256` and the front-door self-test. `examples/golden-momentum/image_plan.json`
  re-authored with compliant >= 5,000-char, brand-graded prompts.
- **FIX-IMG-04 — routed board department.** `run_sales_page_assets.py` cards now route to the
  registered `funnels` department (shared with Skill 49) instead of the unrouted `sales-pages`
  catch-all; the choice is pinned in `SALESPAGE-MANIFEST.json` (`command_center_board`).
- Hash pin re-minted; `SALESPAGE-MANIFEST.json` autofail table + phase table extended; `verify.sh`
  green end-to-end (entry self-test + JSON + provider-purity + secret-scan + golden reproduce +
  broken-variant rejections).

## 1.0.2 — 2026-07-05 — shared mc_board board review-skip root fix (FIX-XC-01a)

### Changed
- **`scripts/mc_board.py` (shared helper, byte-identical across 49/50/53/55/56/57):** the producer no
  longer PATCHes a run's Command Center card straight to `done`. `complete_run` now posts the terminal
  status `review` ("certified — awaiting QC promotion") with the deliverable link registered on the
  card; `card_advance(status="done")` is HARD-BLOCKED. `review -> done` is owned exclusively by the
  independent QC scorer (PASS >= 8.5). Ports the CC `LEGAL_TRANSITIONS` map + BFS legal-path walker +
  current-status GET from `48-facebook-ad-generator/scripts/cc_board.py`, and honors
  `CC_STATUS_PATH_TEMPLATE` / `CC_STATUS_METHOD` for route parity. Still fully fail-soft — the board is
  a VIEW, never a gate.
- **`run_sales_page_assets.py`:** `orchestrate()` now calls `card_advance(phase_id, "in_progress")` per
  phase (a fail-soft board heartbeat); `_mc_board_done` moves the card to `review` (never `done`) and
  registers the deliverable link derived from the run's media ledger / funnel manifest.

### Added
- **`scripts/test_cc_contract.py` (byte-identical):** stdlib contract test proving `complete_run` posts
  `review` and never `done`, the legal-path walk, route-template parity, and disabled-board no-op.

## 1.0.1 — prior governed build
- Direct-Response asset-stack engine: canonical front door + no-skip orchestrator, the intake /
  image-slice / main-8 / upsell-9 / high-ticket / bump / bundle provers, signed PROCESS-CERTIFICATE,
  and the Golden Momentum worked example with broken-variant rejections.
