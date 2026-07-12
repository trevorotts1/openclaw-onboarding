# Changelog — Skill 50 (email-engine)

## 1.1.3 — 2026-07-12 — P2-07: mc_board.py never silently drops an unrecognized department_slug

### Fixed
- **`mc_board.py` — an UNRECOGNIZED `department_slug`** (a typo, a regressed
  hardcoded fake slug like the historical `funnels`/`books`/`email` family, or an
  empty string) is now caught client-side before the ingest POST, logged loudly to
  stderr, and RE-ROUTED to the `general-task` catch-all department with the
  original bad slug annotated on the card description and on `begin_run`'s initial
  board event note. Never silently dropped. Recognized slugs (the 22 mandatory + 6
  universal-primary floor departments + known variant aliases, mirrored from
  `23-ai-workforce-blueprint/scripts/department-floor.py:116-158`) pass through
  unchanged. Applied identically to the shared `mc_board.py` family
  (49/50/53/54/55/56/57).

### Added
- **`test_cc_contract.py`** — six new regression cases: an unrecognized slug
  reroutes to `general-task`, an empty slug reroutes, a known slug
  (`web-development`) and `general-task` itself pass through unchanged, the
  reroute logs loudly to stderr, and `begin_run`'s initial advance note records the
  original bad slug as a board-visible event.

## 1.1.1 — 2026-07-08 — board card routes to a REAL department (Command Center routing fix)

### Fixed
- **`run_email_engine.py` `_mc_board_begin` — the Command Center card was opened with
  `department="email"`, but `"email"` is NOT a seeded department anywhere in the fleet**
  (not one of the 22 mandatory canonical departments, not one of the 6 universal-primary
  vertical departments, and not a variant alias — the CRM department's one-liner merely
  mentions the word "email"). Every Email Engine card therefore silently stranded
  unrouted/misrouted since the board hook shipped — the same class of defect as Skill 55's
  old `"product-bio"` and Skill 53's `"books"`. Now routes to Skill 50's PRIMARY owning
  department **`marketing`** — the ground truth in `23-ai-workforce-blueprint/skill-department-map.json`
  (skill 50 `departments: ["marketing","crm"]`, PRIMARY role `email-campaign-strategist`
  in `marketing`; corroborated by `EMAIL-MANIFEST.json`'s `role_reconciliation_note`).
  Mirrors the sibling Skill 55 fix (`product-bio` → `marketing`). Board work stays
  fail-soft; this is board-routing METADATA only — **no email content changed and the
  deterministic `certificate_sha` is unchanged** (the golden `PROCESS-CERTIFICATE.json`
  sha `6f9a3507…` reproduces byte-for-byte).

### Added
- **`test_department_routing.py`** — a stdlib-only, AST **static** regression guard (never
  imports/runs the orchestrator). Parses `run_email_engine.py`, extracts the `department=`
  literal passed to `mc_board.begin_run`, and asserts it is a plain string, is exactly
  `marketing`, is a member of the canonical fleet department set (loaded live from
  `department-naming-map.json`, with a hardcoded 22+6 floor fallback), and is **NEVER**
  `"email"`. A companion assertion proves the canonical set has teeth (includes
  `marketing`, excludes `email`). Wired into `verify.sh`.

### Changed
- Re-pinned **`ENGINE-PIN.sha256`** over the changed enforcement set
  (`prove-email.py` + `run_email_engine.py` + `EMAIL-MANIFEST.json`), per the front-door
  GATE-3 hash pin. `verify.sh` stays fully green.

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

## 1.0.6 — merge-train T-w1-board-and-54 (Wave-1)
- **FIX-XC-06** — on a fail-closed gate the run now marks its Command Center card
  `blocked` (failing phase + AF code as the note, via the shared
  `mc_board.block_run` wrapper) instead of leaving it at in_progress. Also closed the
  `--upto` truthy hole: the card now completes to `review` whenever the executed
  phase set INCLUDES P4-DEPLOY (a `--upto P4-DEPLOY` run deployed the sequence yet
  never moved the card before). Board work stays fail-soft — never affects exit code.

## 1.0.5 — 2026-07-05
Wave-0 merge-train **T-50-email-engine** (fixes: FIX-XC-11d, FIX-XC-12a, FIX-S36-46, FIX-S36-47, FIX-S36-48). Scope is limited to `50-email-engine/`.

- **FIX-XC-11d — EMAIL-MANIFEST.json owning_role reconcile.** Renamed the four phantom `owning_role` slugs to the REGISTERED role-library seats (identical to `universal-sops/email-craft/EMAIL-PIPELINE-MANIFEST.json`): P1-SELECT `email-strategist`→`email-campaign-strategist`, P2-GENERATE `email-copywriter`→`conversion-copywriter`, P3-QC `email-qc-specialist`→`qc-specialist--marketing`, P4-DEPLOY `convert-and-flow-operator`→`automation-workflow-specialist`. Added `role_reconciliation_note` + `phase_reconciliation_note` documenting how this 4-phase machine spine folds the universal manifest's P0-INTAKE (into P1's brief preflight) and P5-APPROVE (into P4's approval preflight).
- **FIX-XC-12a — client-exact overrides honored only when logged in the LOCKED brief.** `tools/prove-email.py` no longer reads `word_band_override` / `expected_preview_count` / `subject_mode` off the authoring-written email as authority. A `--brief` argument threads the LOCKED brief's `locked_overrides` channel; an override is honored ONLY when its identical value is echoed there, else it is refused (`AF-EMAIL-OVERRIDE-UNLOGGED`) and the SACRED default (150-300 words / sequence-declared preview count / inferred subject mode) re-applies. `run_email_engine.py` passes the brief through the P3 gate; the honored override's source is recorded on the process certificate (`overrides.source`).
- **FIX-S36-46 — deploy requires the REAL process certificate.** `_chk_deploy_approval` now triggers on the deploy ARTIFACT's presence (`working/deploy/build-plan.json`), not a self-set flag: when present, a valid `delivery/PROCESS-CERTIFICATE.json` with `all_phases_pass:true` AND a `certificate_sha` that RECOMPUTES (shared `_certificate_sha` helper, so writer and verifier can never drift) is mandatory. An inline self-signed dict is never accepted; a forged/tampered sha fails closed (`AF-PROCESS-INTEGRITY`).
- **FIX-S36-47 — one-block intake verified independently when a ledger is exported.** `evaluate_intake` derives the one-block property from an INDEPENDENT `conversation_ledger` export when the brief carries one (authoritative — counts the actual assistant intake turns), and only falls back to the self-attested flags when no export is present (now explicitly labeled attestation-based). The P1 preflight label + autofail trigger were corrected to admit this.
- **FIX-S36-48 — declared artifacts enforced + owner-skip approvals preserved.** (i) P3-QC now WRITES its declared `working/qc/email_qc_report.json` (the prover's `--json` report); a new P4 preflight `_chk_build_plan` validates a present `working/deploy/build-plan.json` against `schema/build-plan.schema.json`'s contract (stdlib-only, no jsonschema dep) → `AF-EMAIL-DEPLOY-PLAN-INVALID`. (ii) `_write_proc` is now read-modify-write: it PRESERVES the operator's logged `owner_skip_approvals` (the ONLY sanctioned skip mechanism) instead of destroying them on every phase, and mirrors them to a separate operator-owned `owner_skip_approvals.json`.
- Re-pinned `ENGINE-PIN.sha256` over the changed enforcement set (prove-email.py + run_email_engine.py + EMAIL-MANIFEST.json). Extended both built-in self-tests (`prove-email.py --self-test`, `run_email_engine.py --self-test`) with fixtures for every new behavior; `verify.sh` stays green.

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
