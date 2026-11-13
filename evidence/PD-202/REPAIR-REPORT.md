# PD-202 — Repair report (PR 3220)

Branch: `pd/fl26-closing-gates--hold-d22`
Repo: `trevorotts1/openclaw-onboarding`
Date: 2026-11-13

## 1. The conflict as given

Source (read-only): `_batch-merger/runs/openclaw-onboarding-20261113-145033/evidence/3220-CONFLICT.txt`

```
Auto-merging 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_presentation_job.py
CONFLICT (content): Merge conflict in 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_presentation_job.py
Automatic merge failed; fix conflicts and then commit the result.
```

## 2. What was merged

| Item | SHA / value |
|---|---|
| PRE (remote branch head before repair) | `44831325646ca4c86583a43f44aff5db4e8d231e` |
| origin/main merged in | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` |
| merge base | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| merged head | `a52901fb4bf5ae714f1d1ab97730abdbf2b6e369` |
| merge commit parents | `4483132…` (branch), `ebf5c76…` (main) |

`git merge origin/main` completed with **`Merge made by the 'ort' strategy`, rc=0, zero conflicts.**

## 3. The conflict did not reproduce

The named file was **not** changed on `main` since the merge base:

| Revision | blob | sha256 |
|---|---|---|
| merge base `1a476d2` | `dbbef51bed5cb0a82f146bf638f424246600ba31` | `59a8a12ad7…84e6` |
| `origin/main` `ebf5c76` | `dbbef51bed5cb0a82f146bf638f424246600ba31` | `59a8a12ad7…84e6` |
| branch `4483132` | `30260f48715baa379b44afc4c70c74babfdeb001` | `ae5821e501…74a1` |

`blob@merge-base == blob@main` byte-for-byte. `git log 1a476d2..origin/main -- <file>` returns **0 commits**. The conflict recorded in the batch-merger evidence was against an older `main` snapshot; against the current `origin/main` there is no conflicting hunk.

**No resolution was invented.** The merge took the branch blob unchanged. At the merged head the file blob is still `30260f48715baa379b44afc4c70c74babfdeb001` — identical to the branch — and no conflict markers exist anywhere in the tree.

## 4. Unit files byte-identical before and after

All seven paths the unit touches (`git diff --name-status merge-base..PRE`) have identical sha256 before checkout of the merge and at the merged head:

```
IDENTICAL 9dfd6e2f864df2f095b14ac99c4ae97efe592fe34fe58e2f92ad8128e1a14234  presentation_job/gates.py
IDENTICAL 95c1876ae30863086f57ee5b3faa0a5a018cd18c829ba2f12e51d702df819146  presentation_job/waivers.py
IDENTICAL 8334c58f1d340df829959860f0e56b70d4a357b74bfdb8f66ccef88d0f10f119  tests/test_gates.py
IDENTICAL 11976d1f3fdc1694d271cad58f735e81d903c0b82f9f64477a0df1bef4d0eafe  tests/test_pd_waivers.py
IDENTICAL ae5821e50162452fe9f9835b0eb4c3c2f6febf3a8afd5e71a1e1b9a0c26b74a1  tests/test_presentation_job.py
IDENTICAL d90294af795a7bec9b33dab470c154c4c9f2817ddc5cd44337f8015130e4694a  tests/test_upload_gate.py
IDENTICAL 154b495e61f9c790e9c435a7e0ce930f8b2e5f3534de82c7722d2d8c86e24d1f  tests/test_waivers.py
```

## 5. Acceptance rows at the merged head `a52901fb4`

Environment: Python 3.14.7, pytest 9.0.3. CWD `…/presentations/scripts`.

### PD-202 rows — `tests/test_pd_waivers.py` — 15 passed

```
test_the_field_map_comes_from_the_bank_and_names_the_decline_questions PASSED
test_the_waiver_is_rejected_for_length PASSED                       # "the" -> rejected
test_a_20_character_quote_of_three_words_is_still_too_short PASSED
test_a_30_character_quote_from_an_unlisted_field_is_rejected_naming_the_rule PASSED
test_a_gate_with_no_decline_question_cannot_be_waived_from_an_intake_field PASSED
test_a_qualifying_quote_from_a_listed_field_is_accepted PASSED
test_an_unparseable_captured_at_is_rejected PASSED
test_ocr_readback_is_still_rejected PASSED
============================== 15 passed in 0.05s ==============================
```

PD-317b companion rows A1/A2/A3 in the same file: all PASSED (see the 15 above).

### Wider suite most likely to carry unit intent — 4 files — 93 passed, 4 failed

```
tests/test_gates.py tests/test_waivers.py tests/test_upload_gate.py tests/test_presentation_job.py
========================= 4 failed, 93 passed in 7.25s =========================
```

Failures:
```
FAILED tests/test_presentation_job.py::TestOCRReadbackGateBlocks::test_close_succeeds_with_fully_checked_readback
FAILED tests/test_presentation_job.py::TestQCGateBlocks::test_close_succeeds_with_genuine_passing_qc_report
FAILED tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done
FAILED tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_genuine_client_quoted_waiver_still_closes_done
```

### Same suite at the base commit `448313256…` (PRE)

```
========================= 4 failed, 93 passed in 7.31s =========================
```

The failure set is **identical** (`diff` of sorted FAILED lines → empty). These 4 failures are **pre-existing at the base commit**, unchanged by the merge. They are not caused by this repair.

## 6. Ancestry proof

```
$ git merge-base --is-ancestor 44831325646ca4c86583a43f44aff5db4e8d231e a52901fb4bf5ae714f1d1ab97730abdbf2b6e369
rc=0
```

PRE is an ancestor of the merged head. No history was rewritten; no rebase; no force-push.

## 7. Remote-head proof

```
$ git ls-remote --heads origin pd/fl26-closing-gates--hold-d22
a52901fb4bf5ae714f1d1ab97730abdbf2b6e369	refs/heads/pd/fl26-closing-gates--hold-d22
```

Matches local `HEAD` at 40 characters. Push output was `448313256..a52901fb4  HEAD -> pd/fl26-closing-gates--hold-d22` — a fast-forward, no `+` (forced) prefix.

## 8. What could not be proved

- The exact `main` snapshot the batch-merger conflicted against is not recoverable. Evidence only names the file, not the main SHA. The conflict is therefore explained as main-advanced-since; the specific older blob is unknown.
- The 4 failing tests are pre-existing, but this report does not diagnose their root cause — it proves only that they fail identically before and after the merge.
- No CI run was observed on the pushed head; only local pytest evidence exists.
