# Changelog — Signature Funnel (Skill 49)

## 1.0.9 — 2026-07-05 — image-set coverage cross-check (P2 prompts + P9 images)

Train **T-w1-49-signature-funnel** (Wave-1). Fix ID: FIX-IMG-07.

### Changed
- **FIX-IMG-07 — no coverage cross-check between copy sections, the prompt ledger, and the
  media ledger.** A 2-prompt ledger cleared P2 for a 12-section, 5-page funnel, and a 2-image
  media ledger certified a ~40-image funnel — images for a handful of ~40 slots minted a full
  certificate. Now closed:
  - `scripts/prove_sf_prompt_floor.py` — new **`--structure`** mode. It computes the REQUIRED
    `(page_type, section)` image set for the funnel size from `structure/funnel_structure.json`
    (`funnel_matrix[size]` + `profiles[page].sections` + the new `image_coverage.page_policies`)
    per MASTERDOC §4 — one image per numbered copy section, one celebratory hero for Thank-You,
    none for the Checkout order page — and fails closed listing every missing pair. It auto-detects
    the ledger kind: a `prompts` array is checked for **AF-FUN-PROMPT-COVERAGE**, an `images`
    array for **AF-FUN-IMG-COVERAGE**. Size resolves from `--funnel-size` or `--brief`; a ledger
    with neither array, or an unknown size, is fail-closed. Coverage self-test added for sizes 3/5/7.
  - `run_signature_funnel.py` — **P9-CERTIFY** now folds the image-coverage assert in beside the
    no-pitch/provenance gate: the media ledger must carry an image for every required slot for the
    brief's `funnel_size` or the run aborts with **AF-FUN-IMG-COVERAGE** and no certificate. The
    orchestrator self-test's valid run now emits the full image set, plus a new regression case:
    a partial media ledger aborts at P9.
  - `structure/funnel_structure.json` — added the `image_coverage` policy block (the required-set
    source) and registered both new AF codes in `autofail_codes`.
  - `examples/golden-daybreak/build_golden.py` — the committed golden is now a COMPLETE 7-step
    funnel: the prompt ledger and media ledger each cover all 45 required image slots (main 1-12,
    upsell/downsell/upsell-2/downsell-2 1-8, thank-you hero). Derived-page and thank-you prompts
    reuse the authored main-section bodies through the existing `_vary` de-templating layer (never
    machine filler); the golden certificate was re-minted. Also fixed a latent gap where the golden
    orchestrator run did not stage `persona-selection-log.md` (P0 fail-closed since 1.0.7).
  - `verify.sh` — golden reproduce now also asserts prompt + image coverage via `--structure`.
  - Re-minted `scripts/SF-PROVER-PIN.sha256`; registered the new AF codes in `FUNNEL-MANIFEST.json`.

## 1.0.8 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-XC-06** — added the fail-soft `block_run()` wrapper to the shared
  `scripts/mc_board.py` (the CANONICAL copy). It moves a run's card to the `blocked`
  status (reachable from any state in one hop, NEVER `done`) with the failing phase +
  AF code as the note, so a gate failure is VISIBLE on the board instead of stranding
  the card at in_progress. Re-dropped byte-identical into 50 / 53 / 55 / 56 / 57 and
  the new 54 copy. The signature-funnel runner itself is unchanged (purely additive).

## 1.0.7 — 2026-07-05 — persona grounding (P0) + client model-content receipt (P9)

Train **T-funnel-copy-engine** (Wave-0 merge-train). Fix IDs: FIX-XC-02a, FIX-XC-09e.

### Changed
- **FIX-XC-02a** — `scripts/prove_sf_intake.py`: new fail-closed **AF-FUN-INTAKE-PERSONA-LOG** gate.
  A runtime brief may not unlock generation without a `persona-selection-log.md` (resolved from
  `--persona-log`, the brief's `persona_selection_log` ref, or a sibling file) that names a REGISTERED
  persona slug (mirrors FAB-QC D4). Wired the golden (`examples/golden-daybreak/persona-selection-log.md`),
  the orchestrator self-run, and `verify.sh` reproduce. Copy-persona Step-0 + Section-4 Task-Mode seam
  documented in `prompts/funnel-copy-prompts.md` and `universal-sops/funnel-craft/SOP-FUNNEL-02-COPY.md`.
- **FIX-XC-09e** — `signature-funnel-entry.sh` resolves the CLIENT's own execution-tier authoring model
  (role=content), writes `routing/model-content-receipt.json`, and gates it via
  `scripts/prove_sf_cert.py --model-receipt` (new **AF-FUN-MODEL-TIER** / **AF-FUN-MODEL-NOANTHROPIC**;
  execution/content tier required, Anthropic hard-banned by provider field).
- Re-minted `scripts/SF-PROVER-PIN.sha256`; added the new AF codes to `FUNNEL-MANIFEST.json`.

## 1.0.6 — 2026-07-05 — artifact-backed phase gates + verbatim grade-block containment

Train **T-49-signature-funnel** (Wave-0). Fix IDs: FIX-XC-03a, FIX-IMG-05, FIX-IMG-06.

### Changed
- **FIX-XC-03a — P5–P8 were unconditional no-ops** (`_phase_gates` :99-106 passed
  `required_file=None`, so a PROCESS-CERTIFICATE could mint with ZERO pages built).
  Each phase now MEASURES a real artifact and fails closed:
  - **P5-HTML** — `run_signature_funnel._gate_html_fragments`: a non-empty
    `pages/<profile>.fragment.html` for every page in the brief's 3/5/7 matrix
    (`AF-FUN-HTML-FRAGMENT`).
  - **P6-COMPOSE** — new `scripts/prove_sf_graph.py`: validates `funnel_graph.json`
    against MASTERDOC §3 (node set == `funnel_structure.json:funnel_matrix`, unique
    thank-you terminal, no non-terminal dead ends, accept/decline one-click branch on
    every upsell, forward + terminal reachability). `AF-FUN-GRAPH-{SIZE,TYPE,NODES,EDGE,TERMINAL,BRANCH,REACH}`.
  - **P7-BUILD** — new `scripts/prove_sf_build.py`: requires `build_receipt.json` with a
    measured `qc_score >= 8.5` and a non-empty http(s) preview URL per page.
    `AF-FUN-BUILD-{MALFORMED,QC,PREVIEW,TYPE}`.
  - **P8-DERIVE** — `run_signature_funnel._gate_derived_pages`: requires a
    `derived_pages.json` ledger enumerating the U1/D1/U2/D2/TY derived set for the size
    (`AF-FUN-DERIVE-LEDGER`).
  - Both new provers carry a `--self-test` and are added to the front-door hash pin
    (`SF-PROVER-PIN.sha256` re-minted; entry self-test extended). The orchestrator
    self-test now proves P5 and P6 abort with NO certificate when their artifact is missing.
- **FIX-IMG-06 — grade-block "verbatim" was any-of-five short substrings**
  (`prove_sf_prompt_floor.py:47-53,:110-113` — the words "signature grade" alone cleared
  it). Replaced with normalized VERBATIM containment vs the canonical `_GRADE_BLOCK`:
  pass requires ≥85% of its sentences present OR a contiguous ≥600-normalized-char run;
  fingerprints kept only as a fast pre-check; the `AF-FUN-PROMPT-GRADE` detail now names
  the missing sentences. Added a `grade_fingerprint_only` negative fixture.
- **FIX-IMG-05 — SOP-FUNNEL-03 verify command was broken** (positional arg vs a
  `--ledger`-only prover; argparse rc=2 was indistinguishable from a real violation).
  `prove_sf_prompt_floor.py` now also accepts an optional positional ledger path
  (`nargs="?"`); `universal-sops/funnel-craft/SOP-FUNNEL-03-PROMPTS-IMAGES.md:51` fixed to
  `--ledger …`; the universal-sops content manifest re-stamped.

## 1.0.5 — 2026-07-05 — shared mc_board board review-skip root fix (FIX-XC-01a)

### Changed
- **`scripts/mc_board.py` (shared helper, byte-identical across 49/50/53/55/56/57):** the producer no
  longer PATCHes a run's Command Center card straight to `done`. `complete_run` now posts the terminal
  status `review` ("certified — awaiting QC promotion") with the deliverable link registered on the
  card; `card_advance(status="done")` is HARD-BLOCKED. `review -> done` is owned exclusively by the
  independent QC scorer (PASS >= 8.5). Ports the CC `LEGAL_TRANSITIONS` map + BFS legal-path walker +
  current-status GET from `48-facebook-ad-generator/scripts/cc_board.py`, and honors
  `CC_STATUS_PATH_TEMPLATE` / `CC_STATUS_METHOD` for route parity. Still fully fail-soft — the board is
  a VIEW, never a gate.
- **`run_signature_funnel.py`:** `orchestrate()` now calls `card_advance(phase_id, "in_progress")` per
  phase (a fail-soft board heartbeat); `_mc_board_done` moves the card to `review` (never `done`) and
  registers the deliverable link derived from the run's media ledger.

### Added
- **`scripts/test_cc_contract.py` (byte-identical):** stdlib contract test proving `complete_run` posts
  `review` and never `done`, the legal-path walk, route-template parity, and disabled-board no-op.
