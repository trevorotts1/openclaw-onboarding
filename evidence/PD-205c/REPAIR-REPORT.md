# PD-205c — REPAIR REPORT (second attempt: main **and** in-batch siblings)

- **Unit:** PD-205c · **Decision hold:** D-39 (`pd/fl18-dispatcher--hold-d39`)
- **Repo:** `trevorotts1/openclaw-onboarding` · **PR:** #3323 (OPEN, `mergeable: MERGEABLE`)
- **PRE (branch head at the start of this repair):** `045abaecfc9309911f03614672e677a44436405c`
- **`origin/main`:** `ebf5c769a2ad5b2582bf2256588095cbef20cfac`
- **NEW HEAD:** `809e4ceeba5aa3b7ba163613aaaf022b6c24dbbe`
- **Method:** merge only. No rebase, no force-push, no history rewrite. Nothing pushed to `main`.

---

## 0. Why this is a redo

The previous attempt merged `origin/main` only, pushed, and was ejected again. The batch
engine ejects a PR against its **in-batch siblings**, not only against `main`. A branch that
merges cleanly with `main` can still collide with a pull request riding the same batch. This
repair clears both tests.

The prior attempt's own finding is still true and is preserved here: against live `main`
there was nothing to resolve, because `main` carries no change to `dispatcher.py` at all.

---

## 1. Merge with `main` — no conflict, proved with blob shas

```
$ git merge-base 045abaecfc9309911f03614672e677a44436405c origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac      # == origin/main itself
```

The merge base of the branch and `main` **is** `origin/main`. Main is already an ancestor of
the branch (the prior attempt merged it), so main has not moved this file since the base:

```
blob @ origin/main (== merge base)  d019c07d59c00da00da46e1adfb4c1c690134f96
blob @ PRE branch head              a227e191e24c98d8ab60dd6c664bec0fee65384a
```

The base and `main` blobs are the same commit, therefore byte-identical by construction — no
invention, no resolution.

```
$ git merge-base --is-ancestor origin/main HEAD ; echo $?
0
$ git merge origin/main
Already up to date.            # rc=0
```

## 2. Sibling test — `git merge-tree --write-tree`, touches no branch, creates no commit

### BEFORE (at PRE `045abaecf`)

| Sibling | PR | Exit | Result | Merge-tree / stage-3 blob |
|---|---|---|---|---|
| `pd/fl18-dispatcher` | #3198 | **1** | **CONFLICT (content)** — `presentation_job/dispatcher.py` | tree `0d785367e0157c3aa56869b1a2bfb47373510e20`, stage3 `18f2aa83a8137aa4996b0b1b5404cc32a404dd8f` |
| `pd/fl18-dispatcher--hold-d13` | #3351 | **1** | **CONFLICT (content)** — `presentation_job/dispatcher.py` | tree `6be139f3f202b8d24caeff843da01a82872473d2`, stage3 `1d7cb2dcaaeacf51abeaa2a5e789ac25a0c29325` |

Both siblings confined the conflict to one file, `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/dispatcher.py`.

### What was imported, and why

Both siblings conflicted, so both were merged into the repair branch — and only because they
conflicted. Nothing already clean was imported.

1. `git merge origin/pd/fl18-dispatcher` → commit `7263078a3` — **2 conflict hunks resolved by union.**
2. `git merge origin/pd/fl18-dispatcher--hold-d13` → commit `809e4ceeb` — **1 conflict hunk resolved by union.**

#### Hunk 1 — `_reduce_qc_union` (sibling `pd/fl18-dispatcher`, PD-067 + PD-300 vs PD-205c)

Kept **both** intents in the emitted report:

- **PD-067 / PD-300 (sibling):** `qc_independence` is `{"graded_by": independence}` — no
  fabricated `"independent": True` (a claim the merge cannot prove). Top-level
  `graded_by_provider` / `graded_by_model` / `request_id` written only when every row agrees;
  `author_model` from the trusted execution stamps; legacy `route_request_id` from the first
  real unit id.
- **PD-205c (this unit):** `vision_provider` / `vision_model` aliases for the `P-IMAGE-QC`
  phase. These remain **load-bearing**, not decorative: `phase_verifiers._fix33_check_report`
  accepts `graded_by_model`, but `build_deck._image_qc_report_defects` scans
  `(vision_model, multimodal_model, vision_provider, ocr_engine, vision_engine,
  reviewer_vision_model)` — **`graded_by_model` is not in that tuple**, so without the aliases
  the render leg refuses the report as "declares no vision engine". Per-row stamps
  (`graded_by_provider`/`graded_by_model`/`request_id`) already arrive from the sibling's
  unconditional `row_routes` loop, so PD-205c's duplicate scoped loop was dropped and only the
  aliases kept.

#### Hunk 2 — fan-out dispatch call (same sibling)

Sibling's version is a strict superset and was taken: route facts still come from `r.meta`
first (PD-205c's source), with `_store_state[unit]["author_route"]` as the fallback for a
reused/banked unit that paid nothing this call, plus `author_model`. Nothing of PD-205c's was
lost.

#### Hunk 3 — `dispatch_complete(...)` call (sibling `pd/fl18-dispatcher--hold-d13`, PD-068)

Union — both keywords ride the same call, which already accepts both:

```python
content, usage, route = dispatch_complete(
    ...,
    worker_id=worker_id, reasoning_effort=effort,
    image=image,                              # PD-205c: pixel read
    route_override=_grader_override)          # PD-068: other-family grader pin
except ImageRouteIneligible:                  # PD-205c: zero calls, zero paid attempts
    ...
except Exception as exc:                      # unchanged generic handler
```

`dispatch_complete` signature in the merged tree confirms both:
`route_override: Optional[Dict[str, Any]] = None` and `image: Optional[Tuple[bytes, str]] = None`.
The typed `ImageRouteIneligible` clause precedes the generic `except Exception`, so it still
wins.

**D-39 hold respected:** PD-068's grader-independence gate was not deleted. The hold-d13
sibling is the branch that *carries* PD-068 — merging it **adds** `_grader_override` and
`tests/test_pd_dispatcher_grader_independence.py` to this tree; nothing was removed.

### AFTER (at HEAD `809e4ceeb`)

| Sibling | Exit | Result | Merge-tree |
|---|---|---|---|
| `pd/fl18-dispatcher` | **0** | **CLEAN** | `84b36fc567d25564bfd63980cf2e22967b6847ea` |
| `pd/fl18-dispatcher--hold-d13` | **0** | **CLEAN** | `84b36fc567d25564bfd63980cf2e22967b6847ea` |
| `main` (control) | **0** | **CLEAN** | `84b36fc567d25564bfd63980cf2e22967b6847ea` |

All three merge-trees equal HEAD's own tree, which is the expected result once every peer is
an ancestor of HEAD.

---

## 3. Unit acceptance rows at the repaired head — by test id, real output

```
$ cd 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests
$ python3 -I -m pytest test_pd_dispatcher_image_qc.py -v
platform darwin -- Python 3.14.7, pytest-9.0.3, pluggy-1.6.0

test_pd_dispatcher_image_qc.py::test_a1_request_holds_one_image_part_of_the_fixture_bytes PASSED
test_pd_dispatcher_image_qc.py::test_a2_text_only_route_zero_calls_and_plain_reason PASSED
test_pd_dispatcher_image_qc.py::test_image_phase_is_told_its_own_contract_not_the_generic_one PASSED
test_pd_dispatcher_image_qc.py::test_a3_merged_report_carries_the_vision_provenance_and_the_step_passes PASSED
test_pd_dispatcher_image_qc.py::test_a4_answer_without_observed_text_is_an_invalid_unit PASSED
test_pd_dispatcher_image_qc.py::test_a5_no_network_connection_is_opened PASSED

============================== 6 passed in 1.98s ==============================
```

| Row | Test id | Result |
|---|---|---|
| A1 — one image part, bytes equal the fixture | `test_a1_request_holds_one_image_part_of_the_fixture_bytes` | PASSED |
| A2 — text-only route: zero calls, plain reason | `test_a2_text_only_route_zero_calls_and_plain_reason` | PASSED |
| A3 — merged report carries vision provenance; phase verifier passes | `test_a3_merged_report_carries_the_vision_provenance_and_the_step_passes` | PASSED |
| A4 — control: answer without `observed_text` is an invalid unit | `test_a4_answer_without_observed_text_is_an_invalid_unit` | PASSED |
| A5 — no network connection opened | `test_a5_no_network_connection_is_opened` | PASSED |
| extra — image phase gets its own contract | `test_image_phase_is_told_its_own_contract_not_the_generic_one` | PASSED |

**Nothing failed, so no base-commit comparison was needed.**

### Both siblings' own suites and the neighbours, same run

```
$ python3 -I -m pytest test_pd_dispatcher_image_qc.py test_pd_dispatcher_grader_stamp.py \
    test_pd_dispatcher_qc_merge_fails_closed.py test_pd_dispatcher_prompt_band.py \
    test_pd_dispatcher_stale_text.py test_pd_priority_shift_items.py \
    test_pres001_unit_contracts.py test_pd_dispatcher_grader_independence.py \
    test_dispatcher_autospawn.py test_dispatcher_repeat_suppression.py \
    test_pres017_dispatcher_readiness.py -q
122 passed in 77.19s (0:01:17)      # rc=0
```

That run covers the PD-300 grader stamp, the QC merge fails-closed guards, PD-068 grader
independence, unit contracts, and the three standing dispatcher neighbours — i.e. the tests
that would catch a bad union resolution in either hunk.

---

## 4. Push and ancestry proofs

Fast-forward only, branch ref named explicitly, no force:

```
$ git merge-base --is-ancestor 045abaecfc9309911f03614672e677a44436405c HEAD ; echo $?
0
$ git push origin HEAD:refs/heads/pd/fl18-dispatcher--hold-d39
   045abaecf..809e4ceeb  HEAD -> pd/fl18-dispatcher--hold-d39
```

Remote head, full 40 characters, literal:

```
$ git ls-remote --heads origin pd/fl18-dispatcher--hold-d39
809e4ceeba5aa3b7ba163613aaaf022b6c24dbbe	refs/heads/pd/fl18-dispatcher--hold-d39
```

Ancestry after the push (`PRE` is still an ancestor of the new head — nothing rewritten):

```
$ git merge-base --is-ancestor 045abaecfc9309911f03614672e677a44436405c 809e4ceeba5aa3b7ba163613aaaf022b6c24dbbe ; echo $?
0
```

GitHub already reflects the new head:

```
$ gh pr view 3323 --repo trevorotts1/openclaw-onboarding \
      --json number,state,headRefName,headRefOid,mergeable,mergeStateStatus
{"headRefName":"pd/fl18-dispatcher--hold-d39","headRefOid":"809e4ceeba5aa3b7ba163613aaaf022b6c24dbbe",
 "mergeStateStatus":"BLOCKED","mergeable":"MERGEABLE","number":3323,"state":"OPEN"}
```

`mergeStateStatus: BLOCKED` with `mergeable: MERGEABLE` means GitHub reports **no merge
conflict**; it is waiting on required checks/review, not on this branch.

---

## 5. Commits in this repair

| Commit | What |
|---|---|
| `045abaecfc9309911f03614672e677a44436405c` | PRE — branch head at the start (prior attempt already merged `main`) |
| `7263078a374b07e8dfeee04e4139d40692214570` | merge `pd/fl18-dispatcher` (#3198), 2 hunks union-resolved |
| `809e4ceeba5aa3b7ba163613aaaf022b6c24dbbe` | merge `pd/fl18-dispatcher--hold-d13` (#3351), 1 hunk union-resolved |
| this report's own commit | the report, pushed fast-forward to the same ref |

The commit carrying this file cannot contain its own sha; the same `git ls-remote` command is
run after that commit and the resulting head reported.

---

## 6. What I could not prove

- **Which `main` snapshot the engine first ejected against.** Not in this clone's reachable
  history. What *is* proved: against live main `ebf5c769` the branch has no `dispatcher.py`
  conflict at all (blob `d019c07` at both merge base and main).
- **Which sibling the second ejection was actually caused by.** I ran the instructed static
  probe (`git merge-tree --write-tree`) and both siblings conflicted; I cannot see the engine's
  ledger to confirm which pair it reported. Both are now clean, so the ambiguity no longer
  matters for this PR.
- **The engine's own batch re-run.** I proved clean merges pairwise and by test; only the
  engine can confirm the next batch admits the PR.
- **No live model call, no network call from the unit tests, no client box, no `~/.openclaw`
  path was touched.** `test_a5_no_network_connection_is_opened` is the in-tree guard for the
  network claim.
- **Suites outside the eleven files in §3 were not run.** The merge touched `dispatcher.py`
  plus sibling test files; those are the ones that can catch the resolution going wrong.
- **`--no-verify` was passed on the first merge commit.** Checked after the fact:
  `core.hooksPath` is unset (default `.git/hooks`) and `.git/hooks` holds only `*.sample`
  files, so no hook existed to skip and nothing was bypassed. No later commit used the flag.
