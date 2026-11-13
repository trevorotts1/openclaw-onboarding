# PD-319a — REPAIR REPORT

- Unit: PD-319a · Lane FL35 · Repo `trevorotts1/openclaw-onboarding`
- Branch: `pd/fl35-sealed-record` · PR 3320
- Repairer: deepseek-chain
- Method: merge `origin/main` INTO the branch. No rebase, no force-push.
- Branch head before repair: `74d48abe6581fe2a191e7e697d70a8b59348e797`
- `origin/main` merged: `ebf5c769a2ad5b2582bf2256588095cbef20cfac`
- Merge base: `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
- Merge commit: `94fd1c9182fd8d8a5dcf4c07a7bca3d5a4864415`

---

## 1. The conflict as given

Verbatim from the engine's run ledger:

```
real conflict in: 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_intake_provenance.py
```

## 2. What I merged

```
$ git fetch origin
$ git merge origin/main
Merge made by the 'ort' strategy.
 66 files changed, 6769 insertions(+), 65 deletions(-)
```

**No conflict was raised.** `git merge` exited 0 and did not write an
unmerged index. The reported conflict does not exist at the current
`origin/main`.

Why, proven rather than asserted — the named file is byte-identical at the
merge base and at `origin/main`:

```
$ git rev-parse 1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc:<T>   # merge base
d8a7676be1c122f1cc5bc8dd3917b6a2b7070340
$ git rev-parse ebf5c769a2ad5b2582bf2256588095cbef20cfac:<T>   # origin/main
d8a7676be1c122f1cc5bc8dd3917b6a2b7070340
$ git diff --stat 1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc origin/main -- <T>
(empty)
```

Only the branch changed that file (`+43 −9`, commit `c234ab314`, PD-099a).
`origin/main` still carries the older "FIX 17 pattern" probe at line 199; the
branch carries PD-099a's replacement. With one side unchanged, there is nothing
to arbitrate and git takes the changed side — which is the branch's.

## 3. Resolution per hunk

There is exactly one changed region in the file, and it is the branch's own
PD-099a hunk (`test_engine_doors_refuse`, the `2c` / `2c2` sealed-record
refusal probe that replaced the FIX-17 "is the symbol still importable"
probe with "does the funnel refuse"). Resolution: **kept the branch's PD-099a
version, byte-for-byte.** Nothing of main's was dropped, because main holds no
change to lose — its copy of the file is the merge base's copy.

```
$ git rev-parse 74d48abe:<T>   # branch head
5a0986f8710d27d2ab26cb51289ef03392ab536e
$ git rev-parse 94fd1c918:<T>  # merged tree
5a0986f8710d27d2ab26cb51289ef03392ab536e
```

Nothing outside the conflicted file was edited by hand. The merge commit is
git's own output plus a message amendment; every file it touches is a file
`origin/main` changed:

```
$ git diff --name-only 74d48abe 94fd1c918 | wc -l
66
$ git diff --name-only 1a476d2c origin/main | wc -l
66
$ comm -23 <(git diff --name-only 74d48abe 94fd1c918 | sort) \
           <(git diff --name-only 1a476d2c origin/main | sort) | wc -l
0
```

Set difference zero: the merge introduced main's 66 files and altered no file
the branch owns. PD-306 (`fcb901515`), PD-317 (`c78796b86`, `dc1a506de`) and
PD-099a (`c234ab314`) survive untouched.

## 4. Row-by-row re-proof at the merged tree

All commands run in
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts`, on
`94fd1c9182fd8d8a5dcf4c07a7bca3d5a4864415`.

### PD-319a A1 — the parser finds one `FishTagInfo`

```
$ python3 -I -c "import ast; ..."
A1 FishTagInfo definitions: 1 | total classes: 13

$ grep -c "^class FishTagInfo:" presentation_job/runfacts.py
1

$ python3 -I -m py_compile presentation_job/runfacts.py
py_compile OK
```

Expected `1` (build report line "A1 FishTagInfo definitions: 1 | total classes:
13"). Got `1`. Control for the instrument: at the pre-repair branch head the
same file gave `2`, so the counter discriminates.

### PD-319a A2 — the lane's three test files, same counts as before

```
$ python3 -I -m pytest tests/test_intake_provenance.py \
      tests/test_pd_runfacts_306_execution_stamp.py \
      tests/test_pd_runfacts_317_missing_instrument.py -q
......................                                                   [100%]
22 passed in 0.68s
```

Expected `22 passed` (build report: "Same 22 passed before and after; zero
failures either side"). Got `22 passed`. Exit code 0.

### PD-306 — accepted unit, not undone (11 tests)

```
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_keyed_hash_changes_when_the_row_changes_and_not_otherwise
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_edited_row_no_longer_verifies
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_run_key_mints_once_and_is_idempotent
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_ensure_run_key_persists_through_the_store
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_the_key_is_never_logged_or_printed
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_hashless_file_is_treated_as_today_and_logs_stamp_legacy
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_hashless_row_is_ignored_once_any_row_is_hashed
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_a_run_with_no_key_trusts_no_hashed_row
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_the_keyed_read_rejects_what_the_old_read_accepted
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_consumed_coverage_and_stale_units_use_trusted_rows
PASSED tests/test_pd_runfacts_306_execution_stamp.py::test_verdict_in_its_own_file_leaves_the_report_stamp_passing
11 passed in 0.08s
```

### PD-317 — accepted unit, re-checked at this head (5 tests)

```
PASSED tests/test_pd_runfacts_317_missing_instrument.py::test_notes_pane_missing_renderer_fails_naming_it
PASSED tests/test_pd_runfacts_317_missing_instrument.py::test_notes_pane_crashing_renderer_fails_naming_it
PASSED tests/test_pd_runfacts_317_missing_instrument.py::test_notes_pane_healthy_renderer_still_passes
PASSED tests/test_pd_runfacts_317_missing_instrument.py::test_pypdf_missing_fails_naming_pypdf
PASSED tests/test_pd_runfacts_317_missing_instrument.py::test_pypdf_missing_passes_only_under_the_pd201_rule
5 passed in 0.06s
```

### PD-099a — accepted unit, the file in the reported conflict (6 tests)

```
PASSED tests/test_intake_provenance.py::test_refusal_names_sha
PASSED tests/test_intake_provenance.py::test_engine_doors_refuse
PASSED tests/test_intake_provenance.py::test_approval_path_and_exact_consumers
PASSED tests/test_intake_provenance.py::test_sp_intake_never_matches
PASSED tests/test_intake_provenance.py::test_content_freshness_same_second
PASSED tests/test_intake_provenance.py::test_log_durability
6 passed in 0.35s
```

### No regression — like-for-like, with the class control run on the instrument

The seven-file set PD-317 used, same worktree, same interpreter:

| Tree | Result |
|---|---|
| merged `94fd1c918` | `3 failed, 117 passed in 15.67s` |
| `origin/main` `ebf5c769` (control) | `3 failed, 14 passed in 6.45s` in `test_trust_boundary_observability.py` |

The same three fail on both sides, with the same message:

```
FAILED tests/test_trust_boundary_observability.py::TestEndToEndCapture::test_tampered_run_detected_recorded_and_still_proceeds
FAILED tests/test_trust_boundary_observability.py::TestEnforcingIsOrthogonalToRecording::test_enforcing_on_still_gets_recorded_with_enforcing_true
FAILED tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
E   AssertionError: assert 'entries=62' in 'entries=63 divergences=0 ...'
```

The control is on `origin/main` itself: the instrument runs and passes 14 tests
there, so this is a real class-wide failure on main, not a broken check. It
predates this branch and is not caused by the merge. (The 117 vs. 122 count
difference from PD-317's report is only that `test_pd_runfacts_317_*.py` is
excluded from this run; it is run separately above at 5 passed.)

## 5. Remote-head proof

Push 1 — the merge commit:

```
$ git push origin HEAD:refs/heads/pd/fl35-sealed-record
   74d48abe6..94fd1c918  HEAD -> pd/fl35-sealed-record

$ git ls-remote --heads origin refs/heads/pd/fl35-sealed-record
94fd1c9182fd8d8a5dcf4c07a7bca3d5a4864415	refs/heads/pd/fl35-sealed-record
```

Push 2 — this report:

```
$ git push origin HEAD:refs/heads/pd/fl35-sealed-record
   94fd1c918..7da3a8e41  HEAD -> pd/fl35-sealed-record

$ git ls-remote --heads origin refs/heads/pd/fl35-sealed-record
7da3a8e41ef519ca5e5affd21744b4d49c27cbcf	refs/heads/pd/fl35-sealed-record
```

Current remote head, full 40 characters, literal:
`7da3a8e41ef519ca5e5affd21744b4d49c27cbcf`. Both pushes are fast-forwards
from `74d48abe6581fe2a191e7e697d70a8b59348e797`; no force anywhere.

## 6. What I could not prove

1. **Why the engine saw a conflict.** I can prove the conflict does not exist at
   `origin/main` `ebf5c769` (blob identity above). I cannot prove what
   `origin/main` sha the engine merged against — its run ledger gave a file
   path, not a base sha, and I did not read the engine's private run state. If
   it merged an older main, that older main is no longer the tip and the
   distance is unresolvable from here. Named as undetermined rather than
   guessed.
2. **The other lane units' own acceptance rows.** PD-306, PD-317 and PD-099a
   were re-run (above, 11 / 5 / 6 passed) to show the merge did not undo them.
   I did not re-derive their original acceptance text beyond what their
   `evidence/` reports and commit messages state, because this unit's card
   scopes me to PD-319a's rows.
3. **The three `test_trust_boundary_observability.py` failures** are proven
   pre-existing and present on `origin/main`, but not fixed here — out of this
   unit's scope and outside the conflicted file.
