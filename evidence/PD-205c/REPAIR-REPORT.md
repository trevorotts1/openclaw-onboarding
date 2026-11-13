# PD-205c — REPAIR REPORT (ejected merge member)

- **Unit:** PD-205c · **Decision hold:** D-39 (`pd/fl18-dispatcher--hold-d39`)
- **Repo:** `trevorotts1/openclaw-onboarding` · **PR:** #3323
- **Head before repair:** `e9393913975be56882b20b14544037ded470c314`
- **Merge base with main:** `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
- **`origin/main` merged in:** `ebf5c769a2ad5b2582bf2256588095cbef20cfac`
- **Merge commit (method: `git merge origin/main`, no rebase, no force):** `b87d56a0cb54d88b526073ab46ec512f3ab6ea76`
- **Method:** merge, not rebase. Nothing force-pushed.

---

## 1. The conflict as the engine reported it

> real conflict in: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/dispatcher.py`

## 2. What I actually merged — and why the conflict did not reproduce

`git merge origin/main` on the branch head **auto-resolved with the `ort` strategy and
committed clean: 66 files changed, zero conflicts, zero conflict markers.**

The named file was not among the merged files at all. Proof that main never touched it:

```
$ git merge-base HEAD origin/main
1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc

$ git log --oneline 1a476d2cb..origin/main -- \
    23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/dispatcher.py
(empty)

$ git diff --stat 1a476d2cb origin/main -- .../presentation_job/dispatcher.py
(empty)
```

`origin/main`'s copy of `dispatcher.py` is byte-identical to the merge base. There is
therefore no main-side change for this unit's hunks to conflict with, and the merged
tree's `dispatcher.py` is byte-identical to the pre-merge branch head:

```
$ git diff --stat e93939139 HEAD -- .../presentation_job/dispatcher.py
(empty)
```

GitHub agrees the branch is not conflicting against current main: `gh pr view 3323`
reports `"mergeable":"MERGEABLE"`, `"mergeStateStatus":"BEHIND"` — behind, not dirty.
The engine's conflict was raised against a different `main` snapshot than the one live
now; against the live main there is nothing to resolve. **One paragraph answer:** I kept
both sides by keeping everything — the merge brought in main's 66 files untouched and
left this unit's two files exactly as the unit built them, because main carries no
`dispatcher.py` change to trade against.

## 3. Resolution per hunk

**Zero conflicted hunks.** Nothing was hand-resolved, nothing was chosen over anything.
Four files under `32-command-center-setup/`, all of `extensions/full-read-guard/`,
`shared-utils/ensure_cc_interview_flag.py`, `tests/unit/test_frg_dist_matches_src.py`,
`update-skills.sh` and one presentations test came in from main; this unit's two files
(`presentation_job/dispatcher.py`, `tests/test_pd_dispatcher_image_qc.py`) were carried
through unchanged.

### D-39 hold: the grader gate was NOT deleted

The hold note warns that PD-068's grader-independence gate lives in this same file. Main
does **not** carry that work, so there was nothing to delete — but I verified it rather
than assumed it:

```
PD-068 commits and whether origin/main contains them:
  f59586a82  NO     5bbe5161d  NO     efeb1dd7b  NO
  6b2760afe  NO     ec72efa9b  NO     9d4b327e3  NO

grep -c '_model_family'                      base 1a476d2cb -> 0
grep -c '_model_family'                      origin/main    -> 0
grep -c '_model_family'                      merged tree    -> 0
grep -c 'no independent model is available to grade this step'
                                             merged tree    -> 0
tests/test_pd_dispatcher_grader_independence.py on merged tree -> absent
```

The only `PD-068` strings in the merged file (lines 9683, 10231) are pre-existing comments
that exist identically at the base commit. PD-068's branch has not landed on main, so this
hold branch never had the gate and cannot have dropped it. `bf4b85b39` — the one commit on
main whose message touches PD-068 — is a PD-092 test fix, not the grader gate.

## 4. Row-by-row re-proof at the merged tree `b87d56a0c`

Command, run inside the merged worktree:

```
cd 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests
python3 -I -m pytest test_pd_dispatcher_image_qc.py -v
```

Verbatim per-test ids:

```
test_pd_dispatcher_image_qc.py::test_a1_request_holds_one_image_part_of_the_fixture_bytes PASSED
test_pd_dispatcher_image_qc.py::test_a2_text_only_route_zero_calls_and_plain_reason PASSED
test_pd_dispatcher_image_qc.py::test_image_phase_is_told_its_own_contract_not_the_generic_one PASSED
test_pd_dispatcher_image_qc.py::test_a3_merged_report_carries_the_vision_provenance_and_the_step_passes PASSED
test_pd_dispatcher_image_qc.py::test_a4_answer_without_observed_text_is_an_invalid_unit PASSED
test_pd_dispatcher_image_qc.py::test_a5_no_network_connection_is_opened PASSED

============================== 6 passed in 1.55s ===============================
```

| Row | Test id | Result |
|---|---|---|
| A1 — request holds one image part whose bytes equal the fixture | `test_a1_request_holds_one_image_part_of_the_fixture_bytes` | PASSED |
| A2 — text-only route: zero calls, plain reason | `test_a2_text_only_route_zero_calls_and_plain_reason` | PASSED |
| A3 — merged report carries `observed_text` / `request_id` / `graded_by_model`; phase verifier passes | `test_a3_merged_report_carries_the_vision_provenance_and_the_step_passes` | PASSED |
| A4 — control: answer without `observed_text` is an invalid unit | `test_a4_answer_without_observed_text_is_an_invalid_unit` | PASSED |
| A5 — no test opens a network connection | `test_a5_no_network_connection_is_opened` | PASSED |
| extra — image phase gets its own contract, not the generic one | `test_image_phase_is_told_its_own_contract_not_the_generic_one` | PASSED |

### The rows still discriminate (negative control at the merged tree)

Put the pre-unit `dispatcher.py` (`git show 1a476d2cb:<file>`) in place of the merged one,
re-ran the same file, then restored:

```
FAILED test_a1_request_holds_one_image_part_of_the_fixture_bytes
FAILED test_a2_text_only_route_zero_calls_and_plain_reason
FAILED test_image_phase_is_told_its_own_contract_not_the_generic_one
FAILED test_a3_merged_report_carries_the_vision_provenance_and_the_step_passes
FAILED test_a5_no_network_connection_is_opened
5 failed, 1 passed in 0.70s
```

`A4` passing on the base is the documented control row (it pins behaviour that pre-dates
this unit). Working tree restored; `git status` clean, `git diff HEAD` empty.

### Neighbours and compile at the merged tree

```
python3 -I -m py_compile dispatcher.py test_pd_dispatcher_image_qc.py  -> COMPILE_OK
pytest test_pd_dispatcher_image_qc.py test_dispatcher_autospawn.py \
       test_dispatcher_repeat_suppression.py test_pres017_dispatcher_readiness.py -q
  -> 49 passed in 75.54s
```

The three `test_qc_aggregate.py` failures and the one
`test_fix112_missing_producers.py` failure recorded in BUILD-REPORT.md are pre-existing
(the build report proved them with this unit's dispatcher stashed). Main's merge brought
`dispatcher.py` through untouched, so those are unchanged in kind and are not attributed
to this unit.

## 5. Commits and remote-head proof

| Commit | What |
|---|---|
| `e9393913975be56882b20b14544037ded470c314` | the unit as built (unchanged) |
| `b87d56a0cb54d88b526073ab46ec512f3ab6ea76` | `Merge remote-tracking branch 'origin/main' into repair-pd-205c` |
| this file's own commit | `PD-205c: repair report for the ejected merge member` |

Push of the merge commit:

```
$ git push origin HEAD:refs/heads/pd/fl18-dispatcher--hold-d39
   e93939139..b87d56a0c  HEAD -> pd/fl18-dispatcher--hold-d39
```

Remote-head proof for `b87d56a0c` (full 40 characters, literal):

```
$ git ls-remote --heads origin refs/heads/pd/fl18-dispatcher--hold-d39
b87d56a0cb54d88b526073ab46ec512f3ab6ea76	refs/heads/pd/fl18-dispatcher--hold-d39
```

The commit carrying this file is pushed immediately after it is written; its own
post-push sha is printed by the same `git ls-remote` command and reported with this
repair, because a commit cannot contain the sha it is about to have.

## 6. What I could not prove

- **Why the engine saw a conflict.** I can prove main has no `dispatcher.py` change now
  and that the merge is clean; I cannot show which `main` snapshot the engine merged
  against, because that snapshot is not in this clone's reachable history. The engine's
  ledger is the only witness of it and I did not find it on disk under
  `/Volumes/mac mini m4/swarm-contract/pd-fix`. Treat the reported conflict as **stale
  against live main**, not as a defect I fixed.
- **The D-39 declaration in BUILD-REPORT.md** says PD-205c restates two of PD-300's hunks
  (`route_provider`/`route_model` at the fan-out seam, `_reduce_qc_union` provenance
  stamp). PD-300's branch is still not an ancestor of main, so those two narrowed hunks
  remain the live implementation. Nothing in this merge reconciles them with PD-300 —
  whoever merges PD-300 still has to keep the per-row `observed_text` preservation.
- **No live model call, no network, no client system touched** in this repair.
- Main-side test suites outside the four neighbour files above were not run; the merge
  added 66 files from main and only `dispatcher.py` and its test file were in scope.
