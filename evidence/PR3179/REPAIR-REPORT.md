# PR 3179 — repair report

Branch: `pd/fl05-engine-reporting`
Repo: `trevorotts1/openclaw-onboarding`
Date: 2026-11-13

## 1. The ejection, quoted

Source: `$SCRATCH_ROOT/Downloads/git trees and automations/batch-merger/runs/openclaw-onboarding-20261113-160036/evidence/3179-CONFLICT.txt`

```
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/phases.py
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
CONFLICT (content): Merge conflict in 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_fix29_style_pick_human_stage.py
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/test_presentation_job.py
Automatic merge failed; fix conflicts and then commit the result.
```

Note: the evidence file echoes `test_presentation_job.py` on the fourth
`Auto-merging` line. The file in this tree is
`.../scripts/tests/test_presentation_job.py`. The quoted line is reproduced
verbatim above and is not corrected here.

## 2. Heads

| What | SHA |
|---|---|
| PRE (`git ls-remote --heads origin pd/fl05-engine-reporting`) | `fbfc1cf390dfc992a4601536b5ffcc1a1e629f57` |
| `origin/main` | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` |
| merge base (PRE, main) | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| new head (merge of main into PRE) | `3d11af69917717b6808d037a49df1e54712a434b` |

`git rev-parse HEAD^1` = `fbfc1cf390dfc992a4601536b5ffcc1a1e629f57` (PRE).
`git rev-parse HEAD^2` = `ebf5c769a2ad5b2582bf2256588095cbef20cfac` (main).
The new head is a two-parent merge commit, so PRE is its first parent.

## 3. The named file vs main

Path: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_engine_client_report.py`

| Ref | Blob |
|---|---|
| HEAD (PRE) | `4bd24e971889ac6a2d8076474b8b11193a1974d0` |
| `origin/main` | `a218d121b81f4da98b3dbb9ee55c14496278d904` |
| merge base | `a218d121b81f4da98b3dbb9ee55c14496278d904` |

`origin/main`'s blob for the file is byte-identical to the merge base's blob.
Main has not touched this file since the merge base, so no content resolution
was invented or needed for it: the branch's side is the only side that changed.
`git merge origin/main` completed with no conflict in that file.

## 4. Sibling test — `git merge-tree --write-tree`

Command shape: `git merge-tree --write-tree <ref> origin/<sibling>`

### Before (at PRE `fbfc1cf39`)

| Sibling | rc | Resulting tree |
|---|---|---|
| `pd/fl05-engine-reporting--hold-d10` (`ea0be3cc9`) | 0 | `875cc3984c74ea42bd8ee98a8fd9ab25d762f12c` |
| `pd/fl04-manifest` (`f07abfe9a`) | 0 | `352727c40e4059a22733ead8374f69ead448f5b1` |
| `pd/fl26-closing-gates--hold-d22` (`fa8095000`) | 0 | `27fc0ba347a0e5764313ca9a7831017fda57121e` |
| `main` (`ebf5c769a`) | 0 | `3ded0ae80bd9d5720e1bbeb3415bba1061aa214b` |

### After (at new head `3d11af699`)

| Sibling | rc | Resulting tree |
|---|---|---|
| `pd/fl05-engine-reporting--hold-d10` | 0 | `875cc3984c74ea42bd8ee98a8fd9ab25d762f12c` |
| `pd/fl04-manifest` | 0 | `352727c40e4059a22733ead8374f69ead448f5b1` |
| `pd/fl26-closing-gates--hold-d22` | 0 | `27fc0ba347a0e5764313ca9a7831017fda57121e` |
| `main` | 0 | `3ded0ae80bd9d5720e1bbeb3415bba1061aa214b` |

All four pairs are clean, before and after, with identical resulting tree
objects. The merge with main therefore changed no merge outcome against any
named sibling.

### Imports

None. All four siblings are clean, and importing a clean sibling would drag
unrelated work into this PR. Nothing was imported.

Note for the room: `pd/fl04-manifest` carries a different blob for the named
file (`af254e2a00e5fd4aca590f3c7235328edaf5d9c3`) than this branch
(`4bd24e97...`); the two edits land in different regions and merge cleanly
(rc 0 both before and after).

## 5. Rows

Run from `23-ai-workforce-blueprint/templates/role-library/presentations/scripts`,
Python 3.14.7, `python3 -m pytest ... -q -p no:cacheprovider`.

Files: `tests/test_engine_client_report.py`,
`tests/test_fix29_style_pick_human_stage.py`,
`tests/test_pd_engine_client_copy.py`,
`tests/test_pd_engine_client_messages.py`,
`tests/test_pd_engine_eta.py`,
`tests/test_pd_engine_operator_review.py`,
`tests/test_pd_engine_pd045_structured_facts.py`,
`tests/test_pd_engine_process_certificate.py`,
`tests/test_pd_report_sanitize.py`,
`tests/test_pd_report_throttle.py`,
`tests/test_presentation_job.py`.

| Head | Result |
|---|---|
| PRE `fbfc1cf39` | 14 failed, 117 passed |
| New head `3d11af699` | 14 failed, 117 passed |

Identical failure sets at both heads, so every red row is pre-existing on the
branch and none was introduced or exposed by the merge.

Red rows (identical at PRE and new head):

- `tests/test_engine_client_report.py::TestClientPhaseIndexConsistency::test_counted_phase_gets_a_real_k_within_n`
- `tests/test_engine_client_report.py::TestClientPhaseIndexConsistency::test_deferred_phase_gets_k_none_but_real_n`
- `tests/test_engine_client_report.py::TestClientPhaseIndexConsistency::test_every_visible_phase_has_a_unique_k_covering_1_to_n_exactly`
- `tests/test_engine_client_report.py::TestClientPhaseIndexConsistency::test_unknown_phase_id_returns_k_none_n_real`
- `tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_counted_phase_substitutes_real_k_n_name`
- `tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_name_field_used_not_bare_phase_id`
- `tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_eta_placeholder_empty_when_no_eta_declared`
- `tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_eta_substituted_when_present`
- `tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_malformed_template_falls_back_to_default_not_a_crash_or_leak`
- `tests/test_engine_client_report.py::TestRenderClientReportMsgNoLiteralBraces::test_no_template_declared_uses_plain_default`
- `tests/test_pd_engine_client_copy.py::TestEveryTemplateFillsItsOwnLabel::test_all_112_templates_render_with_the_manifest_label`
- `tests/test_pd_engine_client_copy.py::TestEveryTemplateFillsItsOwnLabel::test_the_rendered_step_line_reads_as_a_step`
- `tests/test_pd_engine_client_copy.py::TestEveryTemplateFillsItsOwnLabel::test_hidden_phase_is_silent_and_unnumbered`
- `tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done`

Sample real output (one red row, `test_unknown_phase_id_returns_k_none_n_real`):

```
        k, n = eng._client_phase_index("P-DOES-NOT-EXIST", eng.manifest.phases)
        assert k is None
>       assert n == 16
E       assert 0 == 16
tests/test_engine_client_report.py:261: AssertionError
```

The suites were not weakened, skipped, renamed, or xfailed. No test file was
edited by this repair.

## 6. Ancestry and remote proofs

- Push: `git push origin HEAD:refs/heads/pd/fl05-engine-reporting` (fast-forward)
- `git ls-remote --heads origin pd/fl05-engine-reporting` equals local HEAD (40 chars)
- `git merge-base --is-ancestor fbfc1cf390dfc992a4601536b5ffcc1a1e629f57 <new-head>` exits 0

## 7. What could not be proven

- The exact ref or cumulative in-batch state that produced the room's
  `CONFLICT (content)` was not identified. The evidence file names the file but
  not the merge target. All four named siblings merge clean against both PRE and
  the new head, and main's blob for the named file is identical to the merge
  base's, so the conflict did not come from any of those four in their current
  state.
- A blob scan across every remote head for the named file was started and
  stopped (too many refs to finish in the window). Ref count aside, it was not
  completed, so "no other remote ref carries a conflicting version" is NOT
  proven here.
- The 14 red rows are pre-existing on this branch. Their cause was not repaired
  here; this task was conflict repair only.
