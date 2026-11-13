# PD-319a — REPAIR REPORT (redo: main + in-batch siblings)

- Unit: PD-319a · Lane FL35 · Repo `trevorotts1/openclaw-onboarding`
- Branch: `pd/fl35-sealed-record` · PR 3320
- Repairer: deepseek-chain
- Method: merge `origin/main` and the colliding sibling into the branch. NO rebase, NO force-push, never pushed to `main`.
- Branch head at start (PRE): `791487803fda1faba03f7a2066775558d0f557fd`
- `origin/main`: `ebf5c769a2ad5b2582bf2256588095cbef20cfac` (the sha the task named — matched exactly)
- Merge base with main: `ebf5c769a2ad5b2582bf2256588095cbef20cfac` (main was already an ancestor of PRE)
- Merge base with sibling fl17: `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
- Sibling merged: `pd/fl17-phase-checks` (`1b24dacaf9138314e4e1350e360907788474e8d4`)
- Sibling NOT merged (already clean): `pd/fl35-sealed-record--hold-d37` (`bf7ecc029814205a8c17d713495beabc8c7f0571`)

---

## 1. The ejection that caused this redo

The earlier repair merged `origin/main` only and was ejected again. The batch
engine ejects a PR against its **in-batch siblings**, not only against `main`.
This redo therefore clears both: main, and every sibling named on the card.

## 2. Merge with main — nothing to merge, proven with blob shas

```
$ git merge-base HEAD origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac     # == origin/main
$ git merge origin/main --no-edit
Already up to date.
```

`origin/main` is an ancestor of the branch head (`git merge-base --is-ancestor
origin/main HEAD` → rc 0), so the main leg of the collision was already closed by
the earlier repair and carries no unresolved hunk.

Non-destructive check of the same pair, before touching anything:

```
$ git merge-tree --write-tree origin/pd/fl35-sealed-record origin/main
dc30ea325cedad55ed21c4bba124e09cc10a8fbe           # rc 0, no conflict lines
```

### The one file that ever conflicts, main side

```
$ git rev-parse 1a476d2c:<T>   # merge base
d8a7676be1c122f1cc5bc8dd3917b6a2b7070340
$ git rev-parse ebf5c769:<T>   # origin/main
d8a7676be1c122f1cc5bc8dd3917b6a2b7070340
$ git diff 1a476d2c origin/main -- <T>
(empty)
```

`main` has not moved `<T>` since the merge base — the blob is identical
(`d8a7676b…`). `<T>` =
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_intake_provenance.py`.

## 3. Sibling test — `git merge-tree --write-tree <head> origin/<sibling>`

No branch touched, no commit created. Exit code 1 = reported conflict.

### BEFORE (at PRE `791487803`)

| Sibling | rc | Result | Tree |
|---|---|---|---|
| `pd/fl17-phase-checks` | **1** | CONFLICT in `<T>` (stages 1/2/3: `d8a7676b` / `5a0986f8` / `33e49b0b`) | `cdcfb6ba26907f53a1231368966adf05228a8ee0` |
| `pd/fl35-sealed-record--hold-d37` | 0 | CLEAN | `7ce9a881b2420295e1ba15f52efc3562bee5c6a8` |

### AFTER (at the repair head, before this report commit `06c0757d0`)

| Sibling | rc | Result | Tree |
|---|---|---|---|
| `pd/fl17-phase-checks` | 0 | CLEAN | `903ec0d38dd3e3d121ac548bba10cef7af9c249b` |
| `pd/fl35-sealed-record--hold-d37` | 0 | CLEAN | `4b3bce8fbe88317b10ea39464ec11326f8e3af9d` |

## 4. What was imported, and why

Only `pd/fl17-phase-checks`, and only because it conflicted. Merged with
`git merge --no-edit origin/pd/fl17-phase-checks` (merge commit `06c0757d0`,
parents `791487803` and `1b24daca`).

`pd/fl35-sealed-record--hold-d37` was **not** imported: it was clean against the
head before and after, and importing it would drag unrelated work into this PR.

### Why the pair conflicted

- fl17 changed `<T>` at `cb8028e04` ("PD-921: an unbound provenance binding
  refuses instead of passing"), `+18 −1` on top of the merge base.
- This branch changed `<T>` at `c234ab314` ("PD-099a"), `+43 −9`.
- Both sides rewrote the same 2c block inside `test_engine_doors_refuse`, and
  `main` had touched neither, so git had no third version to arbitrate.

### Resolution — both intents kept verbatim

One conflict region (`<<<<<<< HEAD` at 199 → `>>>>>>> origin/pd/fl17-phase-checks`
at 278). Resolution, in order:

1. **This branch's PD-099a block, byte-for-byte** — the sealed-record refusal
   probe: hide `presentation_job.runfacts`, drop the stale package attribute,
   block re-import, and assert the funnel *refuses*
   (`2c runfacts is unimportable (control)`,
   `2c2 funnel refuses the consumer with runfacts unimportable`).
2. **fl17's PD-921 block, byte-for-byte** — the unbound-binding refusals:
   `2c runfacts re-importable after probe`, `2c2 unbound funnel refuses instead
   of passing`, `2c2b unbound funnel refuses producers too (door parity)`,
   `2c3 binding restored for the bound cases below`.
3. One copy of the shared comment `# producer exemption lives in the funnel`,
   which both sides carried, followed by the untouched shared tail
   (`2d producer exempt in funnel`, `2e funnel refuses consumer naming sha`).

Nothing was deleted wholesale, renamed, weakened, skipped or xfailed. Both
blocks execute in sequence and both were observed passing (section 5).

Honest note: the merged function now issues two checks whose labels both start
`2c2` (PD-099a's and PD-921's). They are distinct assertions with distinct text
and both PASS; the labels were left exactly as each side wrote them rather than
renaming one side's test.

Files fl17 brought in with the merge are its own 33 files (script + test +
evidence changes listed by `git diff --name-only 1a476d2c origin/pd/fl17-phase-checks`);
the conflicted test file is the only file hand-edited.

## 5. Rows at the repaired head (real output)

Tree: `06c0757d066bc21a994eea55095d4e4c1dff1c7c`, run in
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts`.

### PD-319a A1 — one `FishTagInfo`

```
$ python3 -I -c "<ast walk over presentation_job/runfacts.py>"
A1 FishTagInfo definitions: 1 | total classes: 13
```

Expected `1 | 13` (the unit's build report). Got `1 | 13`.

### PD-319a A2 — the lane's three files

```
$ python3 -I -m pytest tests/test_intake_provenance.py \
      tests/test_pd_runfacts_306_execution_stamp.py \
      tests/test_pd_runfacts_317_missing_instrument.py -q
......................                                                   [100%]
22 passed in 0.52s
```

### PD-306 — 11 rows by id, all PASSED

```
tests/test_pd_runfacts_306_execution_stamp.py::test_keyed_hash_changes_when_the_row_changes_and_not_otherwise PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_edited_row_no_longer_verifies PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_run_key_mints_once_and_is_idempotent PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_ensure_run_key_persists_through_the_store PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_the_key_is_never_logged_or_printed PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_hashless_file_is_treated_as_today_and_logs_stamp_legacy PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_hashless_row_is_ignored_once_any_row_is_hashed PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_a_run_with_no_key_trusts_no_hashed_row PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_the_keyed_read_rejects_what_the_old_read_accepted PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_consumed_coverage_and_stale_units_use_trusted_rows PASSED
tests/test_pd_runfacts_306_execution_stamp.py::test_verdict_in_its_own_file_leaves_the_report_stamp_passing PASSED
============================== 11 passed in 0.14s ==============================
```

### PD-317 — 5 rows by id, all PASSED

```
tests/test_pd_runfacts_317_missing_instrument.py::test_notes_pane_missing_renderer_fails_naming_it PASSED
tests/test_pd_runfacts_317_missing_instrument.py::test_notes_pane_crashing_renderer_fails_naming_it PASSED
tests/test_pd_runfacts_317_missing_instrument.py::test_notes_pane_healthy_renderer_still_passes PASSED
tests/test_pd_runfacts_317_missing_instrument.py::test_pypdf_missing_fails_naming_pypdf PASSED
tests/test_pd_runfacts_317_missing_instrument.py::test_pypdf_missing_passes_only_under_the_pd201_rule PASSED
============================== 5 passed in 0.16s ===============================
```

### PD-099a — 6 rows by id, all PASSED

```
tests/test_intake_provenance.py::test_refusal_names_sha PASSED
tests/test_intake_provenance.py::test_engine_doors_refuse PASSED
tests/test_intake_provenance.py::test_approval_path_and_exact_consumers PASSED
tests/test_intake_provenance.py::test_sp_intake_never_matches PASSED
tests/test_intake_provenance.py::test_content_freshness_same_second PASSED
tests/test_intake_provenance.py::test_log_durability PASSED
============================== 6 passed in 0.27s ===============================
```

### Red seen, and why it is not this merge — the file's own `_check` sweep

`tests/test_intake_provenance.py` is also runnable directly, where `_check`
records failures and `main()` exits 1. That direct run is the honest instrument:
under pytest every `_check` failure prints FAIL but the test still reports
PASSED (no conftest, no raise), so the pytest line above is not by itself proof.

```
$ python3 -I tests/test_intake_provenance.py      # repaired head
FAILED: 7 case(s):
  - 4b P-CONSUMER reset to pending
  - 4c P-GLOB-CONSUMER (working/*/intake.json) reset to pending
  - 4f invalidated set == {P-CONSUMER, P-GLOB-CONSUMER} ([])
  - 4g intake_invalidated stamped in state
  - 5z5 bare-string consumes matches (manifest.py _as_list shape)
  - 5z6 plus-bundled consumes matches (manifest.py _split_artifact_patterns shape)
  - 5a same-second changed intake still invalidates (content rule) ([])
```

Same seven, same labels, at the pre-merge base `791487803` **and** at
`origin/main` `ebf5c769` — so they are pre-existing on main and are not caused by
the main merge or by importing fl17. Not fixed here: outside this repair's scope.

All 2c/2c2/2c2b/2c3 assertions the conflict touched PASS in that direct run
(`2c runfacts is unimportable (control)`, `2c2 funnel refuses the consumer with
runfacts unimportable`, `2c runfacts re-importable after probe`, `2c2 unbound
funnel refuses instead of passing`, `2c2b unbound funnel refuses producers too
(door parity)`, `2c3 binding restored for the bound cases below`).

### Red seen on the imported sibling's files

fl17's 21 test files + `test_runfacts.py` at the repaired head:
`5 failed, 148 passed in 35.96s`. All five are
`tests/test_fix17_verifier_import_failclosed.py::TestVerifierImportFailureAborts::*`.
Same five fail on the pre-merge base (`5 failed, 2 passed`), on fl17's own head
(`5 failed, 2 passed`) and on `origin/main` (`5 failed, 2 passed`). Class-wide on
main, not introduced by the union.

## 6. Ancestry and remote-head proof

```
$ git push origin HEAD:refs/heads/pd/fl35-sealed-record
   791487803..06c0757d0  HEAD -> pd/fl35-sealed-record     # fast-forward, no force

$ git rev-parse HEAD
06c0757d066bc21a994eea55095d4e4c1dff1c7c

$ git ls-remote --heads origin refs/heads/pd/fl35-sealed-record
06c0757d066bc21a994eea55095d4e4c1dff1c7c	refs/heads/pd/fl35-sealed-record

$ git merge-base --is-ancestor 791487803fda1faba03f7a2066775558d0f557fd HEAD
rc=0                                                      # PRE is an ancestor: no rewrite
```

Remote head equals local HEAD, 40 characters, literal, both
`06c0757d066bc21a994eea55095d4e4c1dff1c7c`.

This report can not contain the sha of the commit that carries it. That commit
is a fast-forward child of `06c0757d0` and adds this file only; the live head is
re-proven with:

```
$ git ls-remote --heads origin refs/heads/pd/fl35-sealed-record
```

## 7. What I could not prove

1. **That the engine's sibling list is complete.** I tested exactly the two
   siblings on the card (`pd/fl17-phase-checks`, `pd/fl35-sealed-record--hold-d37`).
   I did not enumerate the whole batch, so I cannot say no other PR riding the
   same batch touches `<T>`.
2. **Why the earlier repair was ejected.** Its report says it merged main and
   nothing conflicted; the card says the batch ejected it. The sibling leg is the
   only collision I can reproduce, and I reproduce it above. The engine's private
   run ledger was not read, so the exact trigger is undetermined.
3. **The seven pre-existing `_check` failures** in `test_intake_provenance.py`
   are proven present on `origin/main` and at the base, but not diagnosed or
   fixed — out of this repair's scope, and the file's pytest-runnability hides
   them (no conftest, `_check` does not raise), which the unit's own
   `22 passed` row has been silently relying on.
4. **The five `test_fix17_verifier_import_failclosed.py` failures** are proven
   pre-existing on main, on fl17 alone and at the base, but not diagnosed.
