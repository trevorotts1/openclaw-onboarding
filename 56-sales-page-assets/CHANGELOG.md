# Changelog — Sales Page Assets (Skill 56)

## 1.1.3 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-XC-06** — re-dropped the shared `scripts/mc_board.py` byte-identical from the
  canonical copy (now carrying the fail-soft `block_run()` wrapper). Additive only;
  the sales-page-assets runner is unchanged.

## 1.1.2 — 2026-07-05 — persona grounding (P0) + client model-content receipt

Train **T-funnel-copy-engine** (Wave-0 merge-train). Fix IDs: FIX-XC-02a, FIX-XC-09e.

- **FIX-XC-02a** — `scripts/prove_sp_intake.py`: new fail-closed **AF-SP56-INTAKE-PERSONA-LOG** gate.
  A runtime brief may not unlock generation without a `persona-selection-log.md` (resolved from
  `--persona-log`, the brief's `persona_selection_log` ref, or a sibling file) that names a REGISTERED
  persona slug (mirrors FAB-QC D4). Wired the golden (`examples/golden-momentum/persona-selection-log.md`
  + `build_golden.py`), the orchestrator self-run, and `verify.sh` reproduce. Copy-persona Step-0 +
  Section-4 Task-Mode seam documented in `prompts/PROMPT-SEAMS.md` and
  `universal-sops/sales-page-craft/SOP-SALESPAGE-01-DR-ASSET-STACK.md`.
- **FIX-XC-09e** — `sales-page-assets-entry.sh` resolves the CLIENT's own execution-tier authoring model
  (role=content), writes `routing/model-content-receipt.json`, and gates it via
  `scripts/prove_sp_cert.py --model-receipt` (new **AF-SP56-MODEL-TIER** / **AF-SP56-MODEL-NOANTHROPIC**;
  execution/content tier required, Anthropic hard-banned by provider field).
- Re-minted `scripts/SPA-PROVER-PIN.sha256`; added the new AF codes to `SALESPAGE-MANIFEST.json`.

## 1.1.1 — 2026-07-05 — fix(Copy routing): baked-prompt hygiene + manifest

### FIX-COPY-04(iii) — junk baked prompts archived; runtime iterates a manifest
- Archived the two legacy non-runtime stubs `prompts/baked/13-test-prompt-airtable-mcp-demo.md` and
  `prompts/baked/14-empty-record.md` to `prompts/baked/_archive/` (an Airtable MCP test stub and an
  empty Airtable record — never real generation prompts).
- Added `prompts/baked/_index.json` — the canonical ordered manifest of the **12 active** runtime
  prompts. The runtime iterates this manifest instead of globbing the directory, so a stray/junk `.md`
  is never silently picked up.
- `prompts/PROMPT-SEAMS.md` updated to reflect the 12-active / 2-archived split.

No generation behavior changed; the 12 active prompts and their provers are unchanged.

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
