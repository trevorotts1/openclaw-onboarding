# PD-038 — repair lane report, second pass (PR 3204)

Branch: `pd/fl04-manifest`
Lane: repair (mergeable again, no history rewrite, no force-push)

This supersedes the first repair report. That attempt merged only `origin/main`, proved the pair clean against
`main`, and was ejected again — because the batch engine tests a PR against its **in-batch siblings**, not only
against `main`. The sibling test is now part of the repair.

## 1. Original ejection

From `_batch-merger/runs/openclaw-onboarding-20261113-145033/evidence/3204-CONFLICT.txt`:

```
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
CONFLICT (content): Merge conflict in 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
Automatic merge failed; fix conflicts and commit the result.
```

## 2. Refs proven at the start (STEP 1)

| Ref | SHA | How proven |
|---|---|---|
| PRE — branch head | `2a2b072fbf057a588c7754fc4bbca994b07b295f` | `git ls-remote --heads origin pd/fl04-manifest` |
| `origin/main` | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` | `git rev-parse origin/main` — equals the expected sha |
| sibling `pd/fl05-engine-reporting` | `fbfc1cf390dfc992a4601536b5ffcc1a1e629f57` | `git ls-remote --heads` |

## 3. Merge with main (STEP 2)

```
$ git checkout -B repair-pd-038 2a2b072fbf057a588c7754fc4bbca994b07b295f
$ git merge origin/main
Already up to date.
rc=0
```

`main` is already an ancestor of PRE: `git merge-base origin/main origin/pd/fl04-manifest` = `ebf5c769...`, i.e.
`origin/main` itself. The earlier repair's merge commit is in this branch already, and `main` has not moved since.

**Main did not move the conflicting file since the merge base.** Blob shas for
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py`:

| Side | Blob |
|---|---|
| merge base (`ebf5c76`) | `a218d121b81f4da98b3dbb9ee55c14496278d904` |
| `origin/main` (`ebf5c76`) | `a218d121b81f4da98b3dbb9ee55c14496278d904` |
| branch head (`2a2b072fb`) | `7e08c9806f7267ee5fff962969fc11c5ecd4e495` |

Base blob == main blob, so no main-side conflict exists for that path and none was invented.

## 4. Sibling test — BEFORE (STEP 3)

Command (touches no branch, creates no commit):

```
$ git merge-tree --write-tree 2a2b072fbf057a588c7754fc4bbca994b07b295f origin/pd/fl05-engine-reporting
ba4333ae05ba598d1a09aad39f2d1d472a7950a1
100644 a218d121b81f4da98b3dbb9ee55c14496278d904 1	.../tests/test_engine_client_report.py
100644 7e08c9806f7267ee5fff962969fc11c5ecd4e495 2	.../tests/test_engine_client_report.py
100644 4bd24e971889ac6a2d8076474b8b11193a1974d0 3	.../tests/test_engine_client_report.py
CONFLICT (content): Merge conflict in .../tests/test_engine_client_report.py
rc=1
```

**Result: CONFLICT** (sibling merge-base with PRE = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`). All three sides
differ — base `a218d12`, ours `7e08c98`, sibling `4bd24e9`.

### Why they conflict, and what each side means

- **Ours (PD-038 lane, FL04 manifest):** the manifest declares `client_label` on every phase and every template was
  moved from `{name}` to `{client_label}`; the manifest is 56 phases at version 75. The test was updated to pin the
  template contract and sweep for raw tokens.
- **Sibling (FL05 engine):** `_render_client_report_msg` is taught to fill `{client_label}`, to count **rendered**
  phases (16/17 rather than the deck-filtered 46/50/47), to return an empty string for a deferred phase, to expose
  `_phase_client_meta` / `_client_rendered_phases`, and adds a `_labelled_step_line` helper that rejects the
  empty-label leak form.

Both intents are real and complementary; neither is optional.

## 5. Sibling import — what and why

Only the one sibling was imported, and only because it conflicted:

```
$ git merge --no-ff --no-edit origin/pd/fl05-engine-reporting
Auto-merging .../tests/test_engine_client_report.py
CONFLICT (content): Merge conflict in .../tests/test_engine_client_report.py
rc=1
```

One conflict hunk (lines 308–351 of the resolved file), resolved by union — no side dropped, no test weakened:

- kept the sibling's exact rendered assertions: `"Step 1 of 16 — Researching your topic — starting"` /
  `... — complete`, plus `assert ph.name not in msg` (PD-018b's intent);
- kept ours: the raw-token sweep over `("{k}", "{N}", "{name}", "{client_label}")`, the manifest template proof
  (`"{client_label}" in template`, `"{name}" not in template`), and the brace sweep on the rendered line;
- merged `test_name_field_used_not_bare_phase_id` into one test carrying both proofs: sibling's
  `_phase_client_meta` label check (`Creating your slide images`), ours' template declaration check, and both leak
  assertions (`ph.name`, `ph.id`, `{name}`, `{client_label}`, `{`/`}`).

Nothing was deleted, renamed, skipped or marked xfail.

Merge commit (first parent = PRE, second = sibling):

```
a12d14f9e1ed1eb49a3d4b7c03f46c43cd3a31f2
```

The merge brought 22 paths: the sibling's engine changes (`__main__.py`, `heal.py`, `phases.py`, `report.py`,
`state.py`), its 10 test files, its 6 evidence reports, and the resolved `test_engine_client_report.py`.

**Nothing of ours was lost.** Our unique paths are byte-identical at PRE and at the merged head:

```
IDENTICAL 85318f9d65285239e7c15757339ada1a01d074ad scripts/ci/pd_manifest_order_check.py
IDENTICAL 1c0af9bb00902c9341df1484068ad417f30aaad3 scripts/ci/presentations-drift-gates.sh
IDENTICAL 215d5f327bbbc5532cf553d8622dad11a5fcfef6 universal-sops/_content-manifest.json
IDENTICAL 0ee3538408a10fa2fae822063bcd1b52acae22cb universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
IDENTICAL f5bb1daa11d327af98e928d5e4ae4483dd4504e8 .../tests/test_pd_manifest_defer_trap.py
IDENTICAL bcff1a1d74ec700702382b57aac2b8373ae7f1aa .../tests/test_pd_manifest_sop_refs.py
```

## 6. Sibling test — AFTER (STEP 3, re-proof)

```
$ git merge-tree --write-tree a12d14f9e1ed1eb49a3d4b7c03f46c43cd3a31f2 origin/pd/fl05-engine-reporting
3c44c292ae8c5b0d6161b0a8a61585748cf5cd94
rc=0
```

```
$ git merge-tree --write-tree a12d14f9e1ed1eb49a3d4b7c03f46c43cd3a31f2 origin/main
3c44c292ae8c5b0d6161b0a8a61585748cf5cd94
rc=0
```

Both clean, both the same tree — the pair and `main` now agree.

## 7. Acceptance rows at the repaired head (STEP 4)

Working directory `23-ai-workforce-blueprint/templates/role-library/presentations/scripts`, Python 3.14.7,
pytest 9.0.3.

### Row A1 — `test_declined_sales_branch_defers_the_build_and_the_run_succeeds`

```
$ python3 -m pytest tests/test_pd_manifest_defer_trap.py -v
tests/test_pd_manifest_defer_trap.py::test_declined_sales_branch_defers_the_build_and_the_run_succeeds PASSED [ 50%]
tests/test_pd_manifest_defer_trap.py::test_ungated_build_phase_is_stranded_on_the_non_optional_edge PASSED [100%]
============================== 2 passed in 2.67s ===============================
rc=0
```

### Row A2 — `test_ungated_build_phase_is_stranded_on_the_non_optional_edge`
Same run, PASSED (the control row — a defers-only implementation fails it).

### Row A3 — GATE 10: manifest defer-trap

```
$ python3 -I scripts/ci/pd_manifest_order_check.py --manifest universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json
... INFO rows only ...
PASS: no DEFER_TRAP or NO_PRODUCER row in any election set.
rc=0
```

### Row A4 — the formerly conflicted file + the SOP-reference rows

```
$ python3 -m pytest tests/test_engine_client_report.py tests/test_pd_manifest_sop_refs.py -v
tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_counted_phase_substitutes_real_k_n_name PASSED
tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_name_field_used_not_bare_phase_id PASSED
tests/test_pd_manifest_sop_refs.py::test_the_webinar_video_names_its_webinar_procedure PASSED
============================== 32 passed in 1.51s ==============================
rc=0
```

All four rows green. No base-commit comparison was needed for these.

### Row A5 — the imported sibling suite (honesty row, not a unit row)

The imported sibling tests were run at the merged head so the import is not a hidden break:

```
$ python3 -m pytest tests/test_pd_engine_*.py tests/test_pd_report_*.py tests/test_presentation_job.py \
    tests/test_fix29_style_pick_human_stage.py -q
1 failed, 102 passed in 71.53s
FAILED tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done
```

**That failure is pre-existing on the sibling head, not caused by this merge.** Same test, same assertion, same
blocking reason at `origin/pd/fl05-engine-reporting` in a clean detached worktree:

```
$ git worktree add --detach wt-sibling origin/pd/fl05-engine-reporting
$ python3 -m pytest "tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done" -q
1 failed in 1.65s
AssertionError: {'average': None, 'blocking_reasons': ['Copy QC (P1Q-COPY-QC): AF-EXEC-STAMP: working/qc/copy_qc_report.json has no AC...
```

It was not weakened, skipped or xfail-ed here. It belongs to the FL05 lane and should be fixed there.

## 8. Ancestry proof (STEP 5)

```
$ git push origin HEAD:refs/heads/pd/fl04-manifest
   2a2b072fb..a12d14f9e  HEAD -> pd/fl04-manifest
$ git merge-base --is-ancestor 2a2b072fbf057a588c7754fc4bbca994b07b295f HEAD
rc=0
$ git rev-list --count 2a2b072fbf057a588c7754fc4bbca994b07b295f..HEAD
21
```

PRE is an ancestor of the new head: fast-forward only, no rebase, no force-push, history not rewritten. The 21
commits are the merge commit plus the sibling's 20.

## 9. Remote-head proof (STEP 5)

```
$ git ls-remote --heads origin pd/fl04-manifest
a12d14f9e1ed1eb49a3d4b7c03f46c43cd3a31f2	refs/heads/pd/fl04-manifest
$ git rev-parse HEAD
a12d14f9e1ed1eb49a3d4b7c03f46c43cd3a31f2
```

Remote head equals local head, 40 characters, literal.

## 10. What could not be proven

- **The batch engine's own verdict.** Only the git-level pair test is proven (`merge-tree` rc=0 against the sibling
  and against `main`). Whether the merger accepts PR 3204 on its next run is not observable from this lane.
- **GitHub-side mergeability and CI.** Not re-queried here; only ref equality and ancestry are proven.
- **Why the first repair was ejected.** Its report proved the pair clean against `main`; it did not test the sibling.
  That the sibling is the cause is inferred from the mandate and from the reproduced conflict, not from the merger's
  own log line.
- **The FL05 red row.** It is pre-existing and proven so, but it is red on this head too; this PR now carries that
  red row.
- **No other sibling was tested.** Only `pd/fl05-engine-reporting` was named for this batch; any other PR riding the
  same batch is untested here.
