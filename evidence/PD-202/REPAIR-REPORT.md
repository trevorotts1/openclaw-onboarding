# PD-202 — Repair report (PR 3220) — sibling-aware repair

Branch: `pd/fl26-closing-gates--hold-d22`
Repo: `trevorotts1/openclaw-onboarding`
Date: 2026-11-13
Lane: REPAIR PD-202, redo after the main-only repair was ejected a second time.

## 0. Summary

The first repair merged `origin/main` only and was ejected again. The batch engine ejects
on collision with the other pull requests in the same batch, not only with `main`. This
run joins `main` (already an ancestor — nothing to merge) and then tests and clears the
two in-batch siblings, importing only the one that actually collides.

| Item | Value |
|---|---|
| PRE (remote head before this repair) | `b70fc1457455a3594a7cc4d3dd4064bea42025e4` |
| `origin/main` | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` (matches required) |
| Sibling A `pd/fl05-engine-reporting` (PR #3179) | `fbfc1cf390dfc992a4601536b5ffcc1a1e629f57` |
| Sibling B `pd/fl05-flawless-six-exec-stamp` (PR #3346) | `6fb3da91688bd0d563126ac074d13e38372ed8ba` |
| Merge of sibling A | `a7bebc40a373e87e33b49ceea58ab58cef321c9d` |
| Test reconciliation commit (code head) | `110713146b2b2095800734e973b0e8651759cc5c` |
| Merge base PRE↔sibling A | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |

## 1. The original ejection

The ejection this run repairs is the second one: the earlier repair report (commit
`b70fc1457`) merged `origin/main` cleanly and was still ejected. Recorded evidence is a
single-file content conflict on

`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_presentation_job.py`

The previous report showed `main` had not moved that file, so `main` could not have been
the colliding side. This run tests the in-batch siblings directly.

## 2. Merge with main — nothing to merge, and that is proved

```
$ git merge origin/main
Already up to date.

$ git merge-base --is-ancestor origin/main b70fc1457455a3594a7cc4d3dd4064bea42025e4
rc=0
$ git merge-base b70fc1457455a3594a7cc4d3dd4064bea42025e4 origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac
$ git rev-list --count origin/main..b70fc1457455a3594a7cc4d3dd4064bea42025e4
7
```

`origin/main` is an ancestor of PRE at the required SHA `ebf5c76…`. The 7 commits PRE
carries ahead of main are the unit's own work plus the earlier repair merge. No
resolution was invented, and no merge commit was created for main in this run.

Blob shas for the named file, which is why main could not produce the conflict:

| Revision | blob |
|---|---|
| merge base `1a476d2` | `dbbef51bed5cb0a82f146bf638f424246600ba31` |
| `origin/main` `ebf5c76` | `dbbef51bed5cb0a82f146bf638f424246600ba31` |
| PRE `b70fc14` | `30260f48715baa379b44afc4c70c74babfdeb001` |
| sibling A `fbfc1cf` | `319c0f40db38499f229b3eb0481c081614d0934f` |

`git log 1a476d2..origin/main -- <file>` → **0 commits**. Byte-identical at merge base and
at main. `git log 1a476d2..fbfc1cf -- <file>` → **1 commit**. The collision is the sibling.

## 3. Sibling test — BEFORE the repair, at PRE

`git merge-tree --write-tree b70fc1457 origin/<sibling>` — touches no branch, creates no commit.

| Sibling | exit | result |
|---|---|---|
| `pd/fl05-engine-reporting` (#3179) | **1** | **CONFLICT** `test_presentation_job.py` (`merge-tree` tree `2be3f751e…`; stages 1/2/3 = `dbbef51…` / `30260f4…` / `319c0f4…`) |
| `pd/fl05-flawless-six-exec-stamp` (#3346) | **0** | clean (tree `01caca44f…`) — **not imported** |

## 4. What was imported, and why

`pd/fl05-engine-reporting` only. It conflicted, so per the repair rules it had to be
merged in and re-proved clean. `pd/fl05-flawless-six-exec-stamp` was already clean and was
deliberately left out so no unrelated work rides this PR.

The sibling changed exactly one region in that file since the merge base — a single
append-only hunk (`git diff dbbef51 319c0f4` → one hunk, 137 added lines: class
`TestDoneMessageOnNormalClose`, PD-313, "say ready on the normal close"). PD-202 changed an
earlier region of the same file (qc-waiver rows). Git reported one conflict block at lines
1098–1239, where the two changes met at EOF.

Resolution keeps both sides with nothing dropped:

- ours: `assert engine.state["gates"]["ghl_upload"]["state"] == "waived"` (PD-202's rewrite
  of the client-quoted waiver row)
- theirs: the whole PD-313 block, appended unchanged

The resolved file is byte-verified as **ours plus the sibling's appended block, nothing
else**: `diff ours resolved` → a single `1098a1099,1235` addition. Zero conflict markers
remain. No side was deleted, no test skipped, renamed, weakened or xfailed.

## 5. Semantic collision the merge cannot see — and the fix

`git merge-tree` was clean after the textual merge, but three imported rows went red at the
merged head. All three pass on the sibling's own head, so the import caused them:

- `TestDoneMessageOnNormalClose::test_a_run_that_passes_every_gate_first_time_records_one_report_done`
- `TestDoneMessageOnNormalClose::test_a_waived_check_is_named_in_the_ready_message`
- `TestDoneMessageOnNormalClose::test_no_verified_destination_withholds_the_ready_message`

Root cause is a real cross-branch design collision, not a bad merge:

1. The sibling seeds `final_qc_report.json` with `{"average": 9.2}`. On this branch the qc
   gate accepts only an aggregate report carrying `"schema": "final_qc_report/v1"` and an
   overall pass flag (`presentation_job/gates.py`, `QC_REPORT_SCHEMA`), so close refused:
   `EXIT 3 — qc: QC report carries no 'final_qc_report/v1' schema (field 'schema' is None)`.
2. The sibling waives `qc` from the `skip_qc` intake field. PD-202 exists to forbid exactly
   that: `qc` has no decline question in the question bank, so a qc waiver from an intake
   field is `EXIT_WAIVER_INVALID` (9). That row failed with `expected EXIT_OK, got 9`.

Both intents kept, in one commit (`11071314`), test-side only — no production code touched
by this repair:

- seed the real report shape: `{"schema": "final_qc_report/v1", "pass": True, "average": 9.2}`
- run the waived-checks row on `ghl_upload`, a gate the bank does ask the client to decline
  (`ghl_upload_declined_reason`), which is the same adaptation PD-202 already applied to the
  older equivalent row. The row's own intent — the waived-checks sentence, exactly one
  `report.done` — is unchanged.

All three now pass: `3 passed in 0.92s`.

## 6. Sibling test — AFTER the repair

At code head `11071314`:

| Sibling | exit | result |
|---|---|---|
| `pd/fl05-engine-reporting` (#3179) | **0** | clean (tree `9d6204b9485b98df292e4f39ac7977fd494d9dbb`) |
| `pd/fl05-flawless-six-exec-stamp` (#3346) | **0** | clean (tree `6dae23f11c930892b6206457f392ea23ba31b071`) |

Both pairs are clean. Neither sibling needs a further import.

## 7. Acceptance rows at the repaired head

Unit's own rows — `tests/test_pd_waivers.py` — Python 3.14.7, pytest 9.0.3, CWD
`…/presentations/scripts`:

```
...............                                                          [100%]
15 passed in 0.10s
```

Includes the PD-202 rows (`test_the_field_map_comes_from_the_bank_and_names_the_decline_questions`,
length/3-word/unlisted-field rejections, `test_a_gate_with_no_decline_question_cannot_be_waived_from_an_intake_field`,
`test_a_qualifying_quote_from_a_listed_field_is_accepted`, `test_an_unparseable_captured_at_is_rejected`,
`test_ocr_readback_is_still_rejected`) — all green.

Wider suite carrying unit intent — `tests/test_gates.py tests/test_waivers.py tests/test_upload_gate.py tests/test_presentation_job.py`:

```
HEAD  4 failed, 96 passed in 7.73s
PRE   4 failed, 93 passed in 8.04s
```

`diff` of the sorted FAILED lists → **empty (identical)**:

```
TestOCRReadbackGateBlocks::test_close_succeeds_with_fully_checked_readback
TestQCGateBlocks::test_close_succeeds_with_genuine_passing_qc_report
TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done
TestQCAggregatePhaseEndToEnd::test_genuine_client_quoted_waiver_still_closes_done
```

Those four are **pre-existing at PRE** and unchanged by this repair. Observed reasons at
both revisions: three fail `EXIT 3` on the qc gate, one fails on an AF-EXEC-STAMP
`copy_qc_report.json` reason. This repair does not diagnose or touch them. The `+3 passed`
at HEAD is the imported PD-313 class.

## 8. Ancestry proof (no rewrite)

```
$ git merge-base --is-ancestor b70fc1457455a3594a7cc4d3dd4064bea42025e4 110713146b2b2095800734e973b0e8651759cc5c
rc=0
```

## 9. Remote-head proof

```
$ git push origin HEAD:refs/heads/pd/fl26-closing-gates--hold-d22
   b70fc1457..110713146  HEAD -> pd/fl26-closing-gates--hold-d22     # fast-forward, no '+'

$ git ls-remote --heads origin pd/fl26-closing-gates--hold-d22
110713146b2b2095800734e973b0e8651759cc5c	refs/heads/pd/fl26-closing-gates--hold-d22
```

Matches local code head at 40 characters. No rebase, no force-push, `main` untouched.

## 10. What could not be proved

- The batch engine's own ejection record for this second ejection was not re-read; the
  sibling-collision premise comes from the repair instruction, and this report proves the
  sibling collisions directly rather than reproducing the engine's verdict.
- The four pre-existing failures are proved identical before and after, not root-caused.
- No CI run was observed on the pushed head; only local pytest evidence exists.
- The merge commit message for `a7bebc40` misnames the imported sibling's pull request
  number as #3346. The correct mapping is `pd/fl05-engine-reporting` = **#3179**,
  `pd/fl05-flawless-six-exec-stamp` = **#3346**. The message text is not rewritten
  (that would need a force-push); this table is authoritative.
