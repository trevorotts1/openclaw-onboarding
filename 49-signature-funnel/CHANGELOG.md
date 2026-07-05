# Changelog — Signature Funnel (Skill 49)

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
