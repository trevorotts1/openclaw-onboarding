# T-09-BIND — bind the three PENDING rows (lane PBB-672)

| Field | Value |
|---|---|
| Unit | T-09 — "Repair current hook mapping upgrade behavior if gap reproduced" |
| Acceptance clause | "Fresh/existing mapping regressions; preserve unrelated config and actual versions." |
| Lane | PBB-672 (BUILD), branch `pb/PBB-672/t-09-bind` |
| Worktree | `<worktree-root-parent>/Purple-Billboard-Client-System-Build/worktrees/PBB-672` (locked, "portable drive") |
| Head measured | `99434b243a627c5c4fa7923bb2123650f9a137a5` (unchanged; the repair commit from lane PBB-658) |
| Digest (recomputed here) | `f238d12d6ac556e3c24453d5f758ed91fe3c9d09` |
| Base used by the digest recipe | `git merge-base origin/main HEAD` = `3d7135664326eeb7857252afcad5506c1381c3d5` |
| Live `origin/main` at measurement | `c994359d6329b6f958c217ee455b40cfb8a0543c` |
| Ahead / behind vs live main | `git rev-list --left-right --count origin/main...HEAD` = `40 10` (40 behind, 10 ahead) |
| Model | `opus-chain[1m]` (harness-reported model; the spawn harness agent token is `deepseek-direct` — both stated, neither invented) |
| Memory | GREEN (`memory_sample.json` `{"tier":"GREEN"}`); live 12 cores, 55% of 24 GiB free; heavy allowance `min(10, floor((13.2-4)/1.5))` = 6; **1 permit claimed**, sequential runs only |
| Verdict | **PASS — 3/3 rows bound** (with the limitations in section 6) |

## 0. What PBB-658 settled, cited and not redone

`control/T-09-REPAIR.md` and `control/qc/T-09.f238d12d6ac556e3c24453d5f758ed91fe3c9d09.json` record: BookkeepingTests rc 1 → rc 0 against a base reading rc 0 (D1 genuinely closed); the false CHANGELOG claims corrected at `CHANGELOG.md:32` and `:46` (D2, D3); the version moved to `skill-version.txt:1` = `v2.0.191` above main's `v2.0.178` and above the measured ceiling `v2.0.180`, main merged at `e5dc7dc3` (D4); D5 landed. Rows 1–5 PASS there. **This lane does not reopen any of the five defects and does not re-litigate that verdict.**

The three PENDING rows, quoted verbatim from that receipt's `rows_checked`:

1. Row 6 — `"required CI check C-09 (focused_artifact_or_required_ci, checks.json required:true)"`
2. Row 7 — `"required check C-F03 (Admission/crash/unknown send, minimal_focused_trace F-03)"`
3. Row 8 — `"required check C-F12 (Revision-safe upgrade/rollback, minimal_focused_trace F-12)"`

## 1. Instrument proof — both polarities, before any measurement

All commands run in the locked worktree at head `99434b24…`. `127`/`128` are treated as aborts, never as facts.

| Instrument | Expected | Command | rc | Observed |
|---|---|---|---|---|
| git ancestry | PASS | `git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main` | 0 | known-merged sha is an ancestor |
| git ancestry | FAIL | `git merge-base --is-ancestor c6182220934c3fb095a73afa56e169b4f565d132 origin/main` | 1 | unrelated sha is not an ancestor |
| git ancestry | PASS | `git merge-base --is-ancestor 569eee7a79397d34275b0bb0da22a6349bd47f2d HEAD` | 0 | T-39 merge (compat_guard) is in the candidate |
| git ancestry | FAIL | `git merge-base --is-ancestor origin/main HEAD` | 1 | live main is **not** an ancestor of the head (the 40-behind fact) |
| patch-id digest | PASS | `git diff -U0 75a5a26a a2c84b2d5 \| git patch-id --stable` | 0 | `d478c181987c206bf3741b2b488f98a37678b5f8` — reproduces the FAIL receipt's digest exactly |
| patch-id digest | FAIL | same diff against the wrong base `3d7135664` | 0 | `e98b7fba1930c7dcd005881488df9c75983cd60b` ≠ `d478c181…` |
| python unittest | PASS | `cd tmp/PBB-672 && python3 -m unittest -q test_ctl_pass.py` | 0 | `Ran 1 test` / `OK` |
| python unittest | FAIL | `python3 -m unittest -q test_ctl_fail.py` | 1 | `Ran 1 test` / `FAILED (failures=1)` |
| python unittest | ABORT | `python3 -m unittest -q nosuchmodule_zz9` | 1 | `FAILED (errors=1)` + ImportError — an abort, distinguishable from a failure by `errors=` |
| python unittest | ABORT | `python3 -I -m unittest -q test_ctl_pass.py` | 1 | `errors=1` ImportError: `-I` removes the loader path. Recorded as an abort, never as a result. |
| bash suite | PASS | `bash -c 'exit 0'` | 0 | — |
| bash suite | FAIL | `bash -c 'exit 1'` | 1 | — |
| bash suite | ABORT | `bash definitely-not-a-suite-zz9.test.sh` | **127** | `No such file or directory` — instrument abort |
| gh API | PASS (control) | `gh api repos/trevorotts1/openclaw-onboarding/commits/c994359d…/check-runs` | 0 | `"total_count":58` — authenticated and reading |
| gh API | FAIL (target) | `gh api …/commits/99434b24…/check-runs` | 422 body | `No commit found for SHA` |

## 2. Row 6 — C-09

**Row text:** `required CI check C-09 (focused_artifact_or_required_ci, checks.json required:true)`.
`live-ledgers/checks.json` C-09: `type: focused_artifact_or_required_ci`, `required: true`, scope "Fresh/existing mapping regressions; preserve unrelated config and actual versions.", tasks T-09, requirements R-24/R-27.

**Artefact that satisfies it.** The check type is a disjunction: a focused artifact at the exact candidate, **or** a required CI run. The focused-artifact limb exists at this head and was executed by this lane (not by the repair author). Project precedent for this exact type is focused-artifact-based: C-11 (`E-T11-QC-PASS` → `scratch/…/lanes/PBB-016-operator/QC-PASS.md`) and C-12 (`E-T12-QC-PASS` → probe log with `TOTAL=12 PASS=12 FAIL=0`) are both `status: PASS` with `candidate_sha` set and artifact receipts, with no CI evidence.

**Checks run, at head `99434b24…`, independently in this worktree:**

| # | Command | rc | Output that proves the verdict |
|---|---|---|---|
| A | `bash 38-conversational-ai-system/tests/qc-checklist-backend-predicate.test.sh` | 0 | `qc-checklist-backend-predicate.test.sh: 6 cases, all met.` (last cases: `ok deliver-true-model -> ERR:deliver-not-false`; `ok instrument: unreadable config -> ERR:cannot-parse-config`) |
| B | `bash 38-conversational-ai-system/tests/hook-mapping-contract.test.sh` | 0 | `hook-mapping-contract.test.sh: 11 rows, both gates agree on every one, expectations met.` |
| C | `bash 38-conversational-ai-system/tests/repair-inbound-hooks.test.sh` | 0 | `selftest ok` / `oct4_frontdoor.py --selftest: PASS` / `ok inbound-hooks repair` |
| D | `bash -n 38-conversational-ai-system/scripts/11-run-qc-checklist.sh && bash -n 38-conversational-ai-system/tests/qc-checklist-backend-predicate.test.sh` | 0 | no output (syntax clean) |
| E | `cd 38-conversational-ai-system/tools/tests && python3 -m unittest -q test_interactive_owner.BookkeepingTests` | 0 | `Ran 4 tests in 1.727s` / `OK` |

This re-measures, at the pinned head and by a lane that authored none of it, the same green the PBB-658 receipt recorded for the scope clause: fresh mapping, existing mapping, unrelated config (decoy rows inside suite B), actual versions (suite E).

**CI limb — observed and NOT greened.** The head is unpublished. Sources checked: `gh api …/commits/99434b24…/check-runs` → HTTP 422 `No commit found for SHA`; `gh api …/commits/99434b24…` → the same 422; `git ls-remote --heads origin` filtered for `PBB-672`/`PBB-658` → `NO PBB-672/PBB-658 BRANCH ON REMOTE`. The gh instrument was proved live by the positive control in section 1 (`total_count:58` on the published `c994359d`). Therefore no CI run exists for this head and none can exist without publishing, which this lane is forbidden to do.

**Result: PASS**, basis: the `focused_artifact` disjunct of the check type, executed at the exact head by an independent lane, with both-polarity instrument proof. The CI disjunct is **not** claimed. If the project owner rules that required CI is mandatory in addition to the focused artifact, this row reverts to PENDING and the verdict must follow — that ruling is not mine to make.

## 3. Row 7 — C-F03

**Row text:** `required check C-F03 (Admission/crash/unknown send, minimal_focused_trace F-03)`.
`checks.json` C-F03: `fixture_id: F-03`, `type: minimal_focused_trace`, `required: true`, tasks T-09/T-10/T-12, requirements R-23/R-24, `candidate_sha: null`, `evidence_ids: []`.

**Artefact that satisfies it.** A minimal focused trace of admission / crash / unknown send executed against the actual product handler at the exact head. The handler exists at this head and is real product code: `38-conversational-ai-system/tools/durable_store.py` (durable inbox dedupe + idempotency-keyed outbox, states, leases/fences) and `…/reconciliation.py` (unknown-effect resolution). Its focused trace is `…/tools/tests/test_durable_processing.py`, whose own docstring states: "INBOX the same provider event, delivered twice, has exactly one effect — across a restart and across two real processes… CRASH a real SIGKILL after the provider accepted and before the local receipt was written: the record becomes unknown, reconciliation resolves it, and the provider send log stays at exactly one line. CANCEL a canceled action cannot be dispatched by a racing worker, proven with two real worker processes."

**Package-gap statement (named, not papered over).** The run package holds **no F-03 case**: `fixtures/contract-traces.json` contains `F-04A…F-04D, F-05A…F-05C, F-06A, F-06B, F-07A, F-08A, F-12A` and no `F-03`; `fixtures/lifecycle-crash-traces.json` is `synthetic: true`, `status: EXPECTED_ONLY_NOT_EXECUTED` and carries no `fixture_id`; `live-ledgers/checks.json` C-F03 has `candidate_sha: null` and `evidence_ids: []`; `live-ledgers/evidence.json` has no evidence row naming C-F03 (its only related row, `E-SKILL38-GAPS`, is an `artifact_review` reproduction with `check_ids` including C-F03 and `candidate_revision: null`). The same field-read that finds `F-12A` in `contract-traces.json` finds no F-03 entry — the read discriminates. No fixture was created to close the gap.

**Check run (the real product handler's focused trace), at head `99434b24…`:**

| # | Command | rc | Output |
|---|---|---|---|
| F | `python3 38-conversational-ai-system/tools/tests/test_durable_processing.py` | 0 | `Ran 26 tests in 3.759s` / `OK` |

Named cases that carry the F-03 scope, quoted from the run log:
- admission: `test_same_event_twice_one_effect_across_restart`, `test_two_processes_deliver_same_event_one_effect`, `test_identical_body_different_event_ids_are_two_events`, `test_own_outgoing_is_excluded_by_direction_and_actor`
- crash: `test_real_sigkill_after_send_then_reconcile_never_resends`, `test_restart_sweep_makes_crash_explicitly_unknown_without_resend`, `test_crash_before_send_resolves_not_applied_then_retries_same_action`
- unknown send: `test_sender_exception_is_unknown_not_resent`, `test_unresolved_unknown_is_never_claimed_even_after_lease_expiry`, `test_failed_and_unknown_are_distinct`, `test_reconcile_after_ack_before_completion`

**The trace bites (mutation control).** In a throwaway copy under `tmp/PBB-672/mut-f03-root2/` (full skill tree plus the sibling `shared-utils/receipts` that `reconciliation.py` resolves via `Path(__file__).parents[2]/"shared-utils"/"receipts"`), one line of `durable_store.claim_for_dispatch` was changed from `WHERE action_id=? AND state='queued'` to `state IN ('queued','canceled')`:
`rc=1`, `Ran 26 tests … FAILED (failures=2)`, `FAIL: test_canceled_action_cannot_be_dispatched_by_racing_workers`, `FAIL: test_canceled_is_terminal_and_never_claimable`.
Honest note: an earlier single-line mutation of `begin_attempt`'s `state='queued'` **survived** (rc 0) because `claim_for_dispatch` refuses the canceled action first; that is recorded as a survived mutation, not as a pass.

**Result: PASS**, basis: the minimal focused trace of the F-03 scope executed green against the real product handler at the exact head, with the suite shown to bite. The fixture JSON remains expected-only and was not executed; this receipt is the binding record, and the missing F-03 case is named above rather than invented.

## 4. Row 8 — C-F12

**Row text:** `required check C-F12 (Revision-safe upgrade/rollback, minimal_focused_trace F-12)`.
`checks.json` C-F12: `fixture_id: F-12`, `type: minimal_focused_trace`, `required: true`, tasks T-09/T-39, requirements R-24/R-27, `candidate_sha: null`, `evidence_ids: []`.

**Artefact that satisfies it.** A minimal focused trace of revision-safe upgrade/rollback against the actual product handler at the exact head: `38-conversational-ai-system/tools/compat_guard.py` (added by the T-39 merge `569eee7a`, an ancestor of this head) and its focused trace `…/tools/tests/test_compat_guard.py`. The handler's own contract text covers the F-12 scope verbatim: "Rollback compares the revision the upgrade wrote; a newer client fix causes conflict/forward repair. Never roll back sent effects, contact facts, consent/suppression, counters or unknown-send reconciliation." and `forward_repair()` "reports: corrupt, newer than known, missing, protected-state, or migrated… nothing is repaired silently."

**Fixture relation, named.** `fixtures/contract-traces.json` case `F-12A` = `{"upgrade_wrote_config_revision":"rev_a","current_client_config_revision":"rev_b","expected":"CAS_CONFLICT_FORWARD_REPAIR"}` with file-level `status: UNVERIFIED_AGAINST_PRODUCT`. That file was **not** executed and is not claimed as executed. The trace below exercises the same semantics against its handler: a writer holding the stale revision is refused (`StaleWriteError`, record byte-identical), a newer record is refused rather than downgraded, and forward repair reports instead of repairing silently.

**Check run, at head `99434b24…`:**

| # | Command | rc | Output |
|---|---|---|---|
| G | `python3 38-conversational-ai-system/tools/tests/test_compat_guard.py` | 0 | `Ran 25 tests in 8.138s` / `OK` |

Named cases that carry the F-12 scope, quoted from the run log:
- CAS conflict / forward repair: `test_stale_writer_is_refused_and_writes_nothing`, `test_two_writers_at_one_generation_produce_exactly_one_write`, `test_write_that_lowers_the_generation_is_refused`
- revision-safe upgrade: `test_migration_racing_cas_never_regresses_the_generation`, `test_old_record_is_advanced_once_then_noop`, `test_second_run_is_byte_identical_noop`, `test_newer_record_is_refused_with_named_error`, `test_corrupt_record_is_reported_not_repaired`
- newer client state preserved: `test_cas_refuses_to_roll_back_protected_state`, `test_migration_may_not_drop_protected_state`, `test_cas_preserves_unknown_top_level_keys`

**The trace bites (mutation control).** In `tmp/PBB-672/mut-f12/tools/`, `cas_update`'s stale-generation guard `if actual != expected_generation:` was replaced with `if False:`:
`rc=1`, `Ran 25 tests … FAILED (failures=3)`, `FAIL: test_migration_racing_cas_never_regresses_the_generation`, `FAIL: test_two_writers_at_one_generation_produce_exactly_one_write`, `FAIL: test_stale_writer_is_refused_and_writes_nothing`.

**Result: PASS**, basis: the minimal focused trace of the F-12 scope executed green against the real CAS/forward-repair handler at the exact head, with the suite shown to bite. `F-12A`'s JSON remains expected-only and unexecuted; this receipt is the binding record.

## 5. Digest, recomputed here

```
git diff -U0 $(git merge-base origin/main HEAD) HEAD | git patch-id --stable
-> f238d12d6ac556e3c24453d5f758ed91fe3c9d09 0000000000000000000000000000000000000000
```

measured in the locked worktree whose HEAD is `99434b243a627c5c4fa7923bb2123650f9a137a5`, with `git merge-base origin/main HEAD` = `3d7135664326eeb7857252afcad5506c1381c3d5`. Not copied from the prior receipt; the prior receipt's digest was independently reproduced as a control using the old base/head pair (section 1). The head is unchanged since PBB-658, and the merge-base is unchanged, so the digest is stable while live main has advanced to `c994359d`.

## 6. Verdict and limitations

**Verdict: PASS — rows 6, 7 and 8 bind PASS; 3/3 bound; 0 FAIL; 0 unsatisfiable.**

Basis: row 6 on the `focused_artifact` disjunct of its check type at the exact head; rows 7 and 8 on minimal focused traces of their named scopes executed against the real product handlers at the exact head; every instrument proved in both polarities first; both traces shown to bite by mutation; the digest recomputed here.

Limitations, stated rather than buried:
1. **C-09's CI disjunct was not observed** and is not claimed. The head is unpublished (HTTP 422 against an authenticated API with a positive control at `total_count:58`), and this lane may not publish. A ruling that required CI is mandatory in addition to the focused artifact would revert row 6 to PENDING.
2. **The head is 40 behind live `origin/main`** (`c994359d`) and 10 ahead. The pinned digest is measured from the unchanged merge-base so it is stable, but merge readiness is a separate question for the merge train; a moved base invalidates affected evidence per BATCH-MERGE step 5.
3. **Fixture JSONs are still expected-only.** No F-03 case exists anywhere in the run package; `F-12A` exists as an expected shape with `status: UNVERIFIED_AGAINST_PRODUCT`. Neither file was edited, and neither was executed. The traces that were executed are the product handlers' own focused suites at the head.
4. **Checker identity:** this lane authored neither repair commit `99434b2`, nor merge `e5dc7dc3`, nor any product file. The registry-native agent id is unavailable (blocker B-11, registry read HTTP 401), so no native id is invented. The harness reports the model as `opus-chain[1m]`; the spawning harness token is `deepseek-direct`. Both facts are recorded for the reader.
5. The five defects PBB-658 closed were not reopened, and its FAIL verdict was not re-litigated.

## 7. Scope respected

No product code changed. No push, no PR, no merge, no force-push. No edit to `ledger.json`, `live-ledgers/`, `census.json`, `DECISIONS.md` or any LOCKED value. No test assertion edited or weakened. No fixture invented. Temporary trees live under `tmp/PBB-672/`; lane logs under `lanes/PBB-672-lane/`.
