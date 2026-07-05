# Changelog — Skill 50 (email-engine)

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
