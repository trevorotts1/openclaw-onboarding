# PD-910 — BUILD REPORT

- Unit: PD-910 (added unit, not in the 164 lock), lane FL17
- Branch used: `pd/fl17-phase-checks`
  - The ledger records `pd/fl17-layout` for PD-910. That branch does not exist
    (`git branch -a | grep fl17` on the FL17 worktree lists only
    `pd/fl17-phase-checks`, its `--hold-*` children, and
    `pd/fl17-phase-checks--qc-merge`). Per the unit instruction, the FL17 lane's
    existing branch `pd/fl17-phase-checks` was used.
- Commit sha: `08a6cdcd78796b29716bace0750c28f2ad06c1fb`

## Files changed

1. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`
   - `_pu_check_receipt_identity` (~line 4421): the placeholder token rule now
     exempts the installer's documented unbound sentinel exactly
     (`loc_l != "unbound-test"`). Sentinel spelling unchanged (PD-048a keys on
     it). Real placeholder values still fail.
   - `_make_pu_verifier` (~line 4728): reasons are split into `NOTE:` notes and
     real failures. Real failures still return `False` (prefixed
     `AF-U-<phase>`); notes return `True` WITH the note, so a skipped GHL
     readback stays distinguishable from a verified pass.
2. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pres012_strict_pu_verifiers.py`
   - Added `TestPd910SentinelAndNoteReasons` (2 tests, +73 lines). No existing
     test was edited, weakened or deleted.

## Commands and results

All run with `TMPDIR=<LOOP_ROOT>/tmp` from
`.../FL17/23-ai-workforce-blueprint/templates/role-library/presentations/scripts`.

1. `python3 -m pytest tests/test_pres012_strict_pu_verifiers.py -q`
   → `20 passed in 0.38s` (18 pre-existing + 2 new).

2. New tests against the OLD `phase_verifiers.py` (HEAD version swapped in
   temporarily, then restored; `git diff --stat` confirmed the restore)
   → `2 failed, 18 passed`. Both new tests fail on the old code:
   - `test_unbound_sentinel_from_empty_env_is_not_a_placeholder`
   - `test_note_reason_passes_while_real_failure_still_fails`
     (old code: `AF-U-P-U-GHL-SALES: ghl_build_receipt.json: location_id
     'unbound-test' reads as a placeholder` plus
     `AF-U-P-U-GHL-SALES: NOTE: GHL readback skipped (env/import: no LOCATION
     PIT in this probe)`)

3. `python3 -m pytest tests/test_upsell_verifiers.py tests/test_pres011_ghl_external.py tests/test_defect3_presence_is_not_substance.py -q`
   → `3 failed, 76 passed in 4.87s`.

4. Same suites on the OLD `phase_verifiers.py` (baseline)
   → `3 failed, 76 passed in 1.41s`, byte-identical failure set:
   - `TestFix17FrozenArchiveRunner::test_fix17_frozen_archives_match_live_tree_parity`
   - `TestSkill06DryRunCompatibility::test_skill06_dry_run_accepts_lead_task`
   - `TestSkill06DryRunCompatibility::test_skill06_dry_run_accepts_sandbox_task`
   These three are pre-existing environment failures (a provider/model is not
   configured for `ghl_form_builder`), unchanged by this unit.

## What the tests prove

- `checkout_form_builder.resolve_scope(run_dir, intake, env={})` still returns
  `location_id == "unbound-test"`, `location_bound is False`; feeding that value
  to `_pu_check_receipt_identity` produces no placeholder reason, while
  `"test-location"` still produces one.
- `_make_pu_verifier("P-U-GHL-SALES", ...)` returns `(True, [NOTE: GHL readback
  skipped ...])` for a well-formed receipt whose remote readback cannot resolve
  (fake `ghl_media` with no LOCATION PIT), and returns `False` for the same
  receipt with `page_id` removed — with the note still present in the failure
  reasons.

## Scope

Touched only the two files above. No merge, no push to main, no client box, no
live system, no other room's branch or worktree.
