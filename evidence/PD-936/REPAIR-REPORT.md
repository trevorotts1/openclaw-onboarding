# PD-936 — REPAIR REPORT (ejected batch merge member)

**Unit:** PD-936 · lane FL02 · branch `pd/fl02-intake-driver` · PR 3203
**Repo:** `trevorotts1/openclaw-onboarding`
**Repair worker:** deepseek-chain, PD-936 repair lane
**Date:** 2026-11-13

---

## 1. The conflict exactly as the engine gave it

> real conflict in:
> `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_u3_standard_ceiling_restored.py`

Context supplied with it: *PD-936's retarget of five stale `operator_ceiling == 100`
assertions to `model_router.ULTRA_OPERATOR_CEILING` (FIX 61 set 400), colliding with
whatever main now has in that same test.*

---

## 2. What I merged

Working tree: own scratch worktree of `origin/pd/fl02-intake-driver`, created fresh
from the live remote head with no local edits.

**Before (live remote, literal):**

```
$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
$ git ls-remote --heads origin refs/heads/pd/fl02-intake-driver
507e3ceb75a87a67c4dc7f990988ebed29365329	refs/heads/pd/fl02-intake-driver
```

**Merge performed (no rebase, no force):**

```
$ git merge origin/main
Merge made by the 'ort' strategy.
 66 files changed, 6769 insertions(+), 65 deletions(-)
```

Merge commit `0bb4cbd38b07630b7fa033be82b56acae8491d7d`,
parents `507e3ceb7` (branch head) and `ebf5c769a` (`origin/main`).

**The merge is CLEAN. Zero conflicted paths.** `git status --porcelain` is empty after it.

### Why: main has not touched this file since the merge base

```
$ git merge-base origin/main HEAD
ebf5c769a2ad5b2582bf2256588095cbef20cfac

$ git log --oneline ebf5c769a..origin/main -- <the file>
(no output)

$ git log --oneline ebf5c769a..origin/pd/fl02-intake-driver -- <the file>
f187aafa0 PD-936: retarget stale operator_ceiling assertions to FIX 61's 400
```

Only the branch changed the file. `main` still carries the pre-FIX-61 literal on the one
line PD-936 retargeted — and nowhere else in the file:

```
$ git diff origin/main HEAD -- <the file>
     assert record["concurrency"]["operator_ceiling"] == 100
->
+    # FIX 61 (7e5c4d6f3): the global operator ceiling is 400.
+    assert record["concurrency"]["operator_ceiling"] == model_router.ULTRA_OPERATOR_CEILING
```

That is the branch's entire diff against main in this file: +2 −1.

---

## 3. Where the reported conflict actually reproduces

It reproduces against **the other member of the batch pool**, not against `main`:
`origin/pd/fl28-model-router` (PD-905, commit `e0d0cb5c4` "PD-905: test_u3 asserts the
live width axis"). PD-905 rewrote this same file to the live FIX 61 axis and rewrote the
same line to a literal `400`.

Reproduced in a throwaway worktree (merge attempt only, nothing pushed):

```
$ git merge --no-commit --no-ff origin/pd/fl28-model-router
Auto-merging .../test_u3_standard_ceiling_restored.py
CONFLICT (content): Merge conflict in .../test_u3_standard_ceiling_restored.py
Automatic merge failed; fix conflicts and commit the result.
```

Conflicted paths: that one file. One hunk, at what is line 387 of the merged file:

```
<<<<<<< HEAD
    assert record["concurrency"]["concurrency"] == 100, record["concurrency"]
    assert record["mode_axis"]["in_force"] is False, record["mode_axis"]
    # FIX 61 (7e5c4d6f3): the global operator ceiling is 400.
    assert record["concurrency"]["operator_ceiling"] == model_router.ULTRA_OPERATOR_CEILING
=======
    assert record["concurrency"]["concurrency"] == 400, record["concurrency"]
    assert record["mode_axis"]["in_force"] is True, record["mode_axis"]
    assert record["concurrency"]["operator_ceiling"] == 400
>>>>>>> origin/pd/fl28-model-router
```

---

## 4. Resolution per hunk, with reasoning

**Hunk 1 — `test_the_launcher_banner_carries_it_end_to_end`, the three assertions.**

Resolution, if this pair is merged together:

| line | keep | why |
|---|---|---|
| `concurrency` | PD-905's `== 400` | PD-905's live-axis rewrite. FIX 61 runs ultra at `ULTRA_OPERATOR_CEILING` = 400; the branch's inherited `== 100` is the stale pre-FIX-61 body and is not PD-936's text (PD-936 changed only the ceiling line). |
| `mode_axis.in_force` | PD-905's `is True` | same: the mode axis really differentiates under FIX 61 (standard 25 / ultra 400 / economy 100), so `in_force` is True. The branch's `is False` is the retired U3 "cosmetic" world. |
| `operator_ceiling` | **PD-936's constant-named form** | both sides assert the **same contract** — the global operator ceiling is 400. PD-936's version names it (`model_router.ULTRA_OPERATOR_CEILING`) and cites FIX 61 commit `7e5c4d6f3`; PD-905's is a bare literal that re-stales the moment `ULTRA_OPERATOR_CEILING` moves again, exactly the defect PD-936 exists to remove. Per the repair card: keep the version that names the constant. |

So both intents survive: PD-905's live-axis body, PD-936's constant-named ceiling
assertion. No assertion is weakened, deleted, skipped or xfailed — the value asserted is
400 on both sides.

**This resolution was NOT applied to the branch.** The card's method is to merge
`origin/main`; `main` does not contain PD-905, so applying a sibling unit's rewrite here
would drag a different PR's text into PR 3203. The resolution above is recorded so the
batch room (or the next repair worker) applies it verbatim when the two pool members meet.

**Everything outside the conflicted file: untouched.** `git diff --stat` of this repair
against the pre-repair branch head is exactly `evidence/PD-936/REPAIR-REPORT.md`
(this file) plus the `origin/main` merge.

---

## 5. Row-by-row re-proof at the merged tree

The unit's acceptance row A1 is the retarget of the five `operator_ceiling == 100`
literals. Proven at `0bb4cbd38` (main + branch):

```
$ python3 -m pytest -q \
  "tests/test_u3_standard_ceiling_restored.py::test_the_standard_mode_ceiling_constant_is_the_operators_100" \
  "tests/test_fix11_mode_axis.py::test_a_client_measured_at_2500_is_capped_at_100_under_ultra" \
  "tests/test_fix11_mode_axis.py::test_provider_advertising_never_raises_the_operator_ceiling" \
  "tests/test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance"
....
4 passed in 2.39s

$ python3 -m pytest -q \
  "test/test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars"
.
1 passed in 0.77s
```

| row | test id | merged tree | note |
|---|---|---|---|
| A1-a | `test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars` | **PASS** | the retargeted line; was `assert 400 == 100` FAIL on base |
| A1-b | `test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance` | **PASS** | the retargeted line; was `assert 400 == 100` FAIL on base |
| pin-1 | `test_fix11_mode_axis.py::test_a_client_measured_at_2500_is_capped_at_100_under_ultra` | **PASS** | pins 400; unchanged by PD-936, still passing |
| pin-2 | `test_fix11_mode_axis.py::test_provider_advertising_never_raises_the_operator_ceiling` | **PASS** | pins 400; unchanged by PD-936, still passing |
| pin-3 | `test_u3_standard_ceiling_restored.py::test_the_standard_mode_ceiling_constant_is_the_operators_100` | **PASS** | pins 400; unchanged by PD-936, still passing |

**Zero-regression proof, same instrument both sides — the four-file suite
(`test_fix11_mode_axis.py test_u3_standard_ceiling_restored.py test_f15f16_mode_truth.py
test_fix11_client_run_mode_path.py`):**

```
pristine origin/main (ebf5c769a):    32 failed, 68 passed in 40.52s
merged tree    (0bb4cbd38):          31 failed, 69 passed in 42.84s

$ diff <(grep '^FAILED' main.out | sort) <(grep '^FAILED' head.out | sort)
< FAILED tests/test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance
```

Exactly one verdict moved, from FAIL to PASS, on the retargeted assertion. No new failure.

---

## 6. Remote-head proof

**Before any push:**

```
$ git ls-remote --heads origin refs/heads/pd/fl02-intake-driver
507e3ceb75a87a67c4dc7f990988ebed29365329	refs/heads/pd/fl02-intake-driver
```

**Push (fast-forward, no force):**

```
$ git push origin HEAD:refs/heads/pd/fl02-intake-driver
To https://github.com/trevorotts1/openclaw-onboarding.git
   507e3ceb7..d3e96a7ec  HEAD -> pd/fl02-intake-driver
```

**Remote read back, literal, full 40 characters:**

```
$ git ls-remote --heads origin refs/heads/pd/fl02-intake-driver
d3e96a7ecc5de6a814a833fe1b38eb2c36620925	refs/heads/pd/fl02-intake-driver

$ git rev-parse HEAD
d3e96a7ecc5de6a814a833fe1b38eb2c36620925
```

Equal: `d3e96a7ecc5de6a814a833fe1b38eb2c36620925`.

Commits landed by this repair:

| commit | what |
|---|---|
| `0bb4cbd38b07630b7fa033be82b56acae8491d7d` | `Merge origin/main into pd/fl02-intake-driver` (parents `507e3ceb7`, `ebf5c769a`) |
| `d3e96a7ecc5de6a814a833fe1b38eb2c36620925` | this report |
| `7720c27d358b2d5947001e25e60cbbc444b5f750` | the remote-head proof above, written into this report |

All five acceptance rows were re-run at `7720c27d3` as well: `4 passed in 1.00s` and
`1 passed in 0.68s`, identical verdicts.

This report has since received its own documentation-only follow-up commit; `git ls-remote`
is the live truth for the final head, and every push is repeated with the same literal
comparison.

---

## 7. What I could not prove / did not do

1. **The reported conflict does not exist against `origin/main`.** The merge is clean and
   the file's only divergence is PD-936's own +2/−1 hunk. I could not reproduce a
   main-side conflict, because `main` has no commit touching this file since the merge
   base — that is measured above, not assumed.
2. **The real collision is with PD-905's PR branch, and I did not merge it.** Pulling
   `origin/pd/fl28-model-router` into PR 3203 would put another unit's rewrite inside
   this PR. The resolution is stated in §4 in full; it is one table, three lines.
3. **Eleven assertions in this file are stale on `main` today** (U3 "cosmetic axis"
   / standard == 100 world, superseded by FIX 61). Measured identical on pristine main and
   on this branch:

   ```
   origin/main:                   11 failed, 7 passed
   origin/pd/fl02-intake-driver:  11 failed, 7 passed   (same 11 ids)
   ```

   These are not PD-936's hunks — PD-936 changed one line — and PD-905's rewrite is what
   repairs them. Not touched here; flagged so the batch room knows the file is red on
   main independent of this PR.
4. `model_router.py` was not touched. No production behaviour changed.
