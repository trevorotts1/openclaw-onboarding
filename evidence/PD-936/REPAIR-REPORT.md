# PD-936 — REPAIR REPORT (redo: batch-sibling conflict cleared)

**Unit:** PD-936 · lane FL02 · branch `pd/fl02-intake-driver` · PR 3203
**Repo:** `trevorotts1/openclaw-onboarding`
**Repair worker:** deepseek-chain, PD-936 repair lane
**Date:** 2026-11-13 (redo — the first repair merged `origin/main` only and was ejected again)

---

## 0. Why this is a redo, and what the last attempt missed

The first repair (`evidence/PD-936/REPAIR-REPORT.md`, now superseded by this file) merged
`origin/main` cleanly and **declined to import the sibling** PR, recording its resolution as a
table for "the batch room." That was the wrong call. The batch engine ejects a PR against its
**in-batch siblings**, not only against `main`. A branch that merges cleanly with `main` can still
collide with a pull request riding the same batch. The conflict must be cleared in this branch.

The real collision is, and always was, `pd/fl28-model-router` (#3185) — **not** `main`.

---

## 1. Proven heads (literal, 40 hex)

```
PRE   (before this repair)  pd/fl02-intake-driver = 8b72fe4da2e3ec1b2b6edf53346157b9c90c6a00
origin/main                                       = ebf5c769a2ad5b2582bf2256588095cbef20cfac
sibling  pd/fl28-model-router                     = c98c0f375d85653756ef714294aba476eb92839e
```

`origin/main` == the required `ebf5c769a2ad5b2582bf2256588095cbef20cfac`. ✅

---

## 2. The merge with `origin/main`

`origin/main` is **already an ancestor** of the PRE head (the first repair merged it at
`0bb4cbd38`). Measured, not assumed:

```
$ git merge-base --is-ancestor origin/main HEAD      ; rc = 0
$ git rev-list --count origin/main..HEAD             ; 20
$ git rev-list --count HEAD..origin/main             ; 0
$ git merge origin/main                              ; "Already up to date."
```

**Main has not touched the conflicted file since the merge base.** Blob shas:

```
merge-base (1a476d2cb) blob = a941646b271da5e05e1b1eff30f1d4951f2c499e
origin/main            blob = a941646b271da5e05e1b1eff30f1d4951f2c499e   (identical)
our branch HEAD        blob = 0262d6a4256e3926d85e19b59c8dfda4892bc415   (+2/−1, PD-936's retarget)
```

So there is no main-side resolution to invent: `main` still carries the pre-FIX-61 literal on the
one line PD-936 retargeted, and nowhere else. Blob equality is the proof.

---

## 3. Sibling test — `git merge-tree --write-tree` (no branch touched, no commit made)

### 3.1 BEFORE (at PRE head `8b72fe4`)

```
$ git merge-tree --write-tree repair/pd-936 origin/pd/fl28-model-router
exit=1
tree 956206ec541d530ca5da396e325c4b6cfcbea3aa
conflict path: 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_u3_standard_ceiling_restored.py
  stage1 (base)   a941646b271da5e05e1b1eff30f1d4951f2c499e
  stage2 (ours)   0262d6a4256e3926d85e19b59c8dfda4892bc415
  stage3 (theirs) 60104a301e35f7035f88eb370ff2982419ddd3c8
CONFLICT (content): Merge conflict in .../test_u3_standard_ceiling_restored.py
```

**CONFLICT.** One file, one hunk.

### 3.2 AFTER (at repaired head, sibling imported)

```
$ git merge-tree --write-tree repair/pd-936 origin/pd/fl28-model-router
exit=0
tree 3e27ad2f172717ca42e3135795c51f084ea9fdec
```

**CLEAN.** Control: `git merge-tree --write-tree repair/pd-936 origin/main` → `exit=0`.

### 3.3 Per-sibling verdict

| sibling branch | PR | BEFORE | AFTER |
|---|---|---|---|
| `pd/fl28-model-router` | #3185 | **CONFLICT** (test_u3…, 1 hunk) | **CLEAN** (exit 0) |

---

## 4. What was imported, and why

The sibling branch `pd/fl28-model-router` carries three commits since the merge base — and they
touch **only two files** (measured `git diff --stat`):

```
c98c0f375 PD-219b: align router text with the live mode ceilings
e0d0cb5c4 PD-905: test_u3 asserts the live width axis
6ac2b4d4e PD-214: remove the undefined ROUTER_CATALOG fallback in ultra mode

 .../scripts/presentation_job/model_router.py          | 61 ++++++---------
 .../tests/test_u3_standard_ceiling_restored.py        | 66 +++++++-------
 2 files changed, 63 insertions(+), 64 deletions(-)
```

Because the pair **conflicted**, the sibling head was merged into the repair branch per the card:

```
$ git merge origin/pd/fl28-model-router
Auto-merging .../test_u3_standard_ceiling_restored.py
CONFLICT (content): Merge conflict in .../test_u3_standard_ceiling_restored.py
-- model_router.py auto-merged clean (67 lines applied)
```

Merge commit `b81cafa3ac6ea2fadb1a55e50fe3dee4f37d658c`, parents `8b72fe4da` (PRE) and
`c98c0f375` (sibling).

### 4.1 The conflict as given

The single hunk, in `test_the_launcher_banner_carries_it_end_to_end`:

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

### 4.2 Resolution — both intents kept

```
    assert record["concurrency"]["concurrency"] == 400, record["concurrency"]
    assert record["mode_axis"]["in_force"] is True, record["mode_axis"]
    # FIX 61 (7e5c4d6f3): the global operator ceiling is 400.
    assert record["concurrency"]["operator_ceiling"] == model_router.ULTRA_OPERATOR_CEILING
```

| line | keep | why |
|---|---|---|
| `concurrency` | sibling `== 400` | PD-905's live-axis world; FIX 61 runs ultra at `ULTRA_OPERATOR_CEILING` = 400. The PRE `== 100` was inherited base text, not PD-936's edit. |
| `mode_axis.in_force` | sibling `is True` | under FIX 61.5 shares differ (ultra 400 / standard 25 / economy 100), so the axis genuinely differentiates. |
| `operator_ceiling` | **ours, constant-named** | both sides assert the same contract (400). PD-936's form names `model_router.ULTRA_OPERATOR_CEILING` and cites FIX 61 `7e5c4d6f3`; the sibling's bare `400` re-stales the moment the constant moves — the exact defect PD-936 exists to remove. `ULTRA_OPERATOR_CEILING = 400` in the merged `model_router.py`, so the symbolic form is value-identical. |

No assertion weakened, deleted, renamed, skipped or xfailed. Both sides assert 400.

`git diff --cached --stat` against PRE = exactly those two files.

---

## 5. Unit acceptance rows at the repaired head `b81cafa3a` (real output)

Row A1 (the ledger note; there is no PD-936 spec section or brief — see `BUILD-REPORT.md` §0).

```
$ python3 -m pytest -q \
  "intake/interview-app/test/test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars" \
  "scripts/tests/test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance" \
  "scripts/tests/test_fix11_mode_axis.py::test_a_client_measured_at_2500_is_capped_at_100_under_ultra" \
  "scripts/tests/test_fix11_mode_axis.py::test_provider_advertising_never_raises_the_operator_ceiling" \
  "scripts/tests/test_u3_standard_ceiling_restored.py::test_the_standard_mode_ceiling_constant_is_the_operators_100"
.F...
1 failed, 4 passed in 5.39s
```

| row | test id | repaired head | PRE `8b72fe4` | `origin/main` `ebf5c76` | verdict |
|---|---|---|---|---|---|
| A1-a | `test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars` | **PASS** | PASS | — | green |
| A1-b | `test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance` | **FAIL** | **FAIL** | **FAIL** | **PRE-EXISTING** — not caused by this repair |
| pin-1 | `test_fix11_mode_axis.py::test_a_client_measured_at_2500_is_capped_at_100_under_ultra` | **PASS** | PASS | — | green |
| pin-2 | `test_fix11_mode_axis.py::test_provider_advertising_never_raises_the_operator_ceiling` | **PASS** | PASS | — | green |
| pin-3 | `test_u3_standard_ceiling_restored.py::test_the_standard_mode_ceiling_constant_is_the_operators_100` | **PASS** | PASS | — | green |

A1-b failure at all three heads, identical:

```
E       AssertionError: no .mode-plan.json:
scripts/tests/test_fix11_client_run_mode_path.py:375: AssertionError
```

Its `_poller_rig` subprocess exits 0 but writes no `.mode-plan.json` — an environment/engine-route
defect present on pristine `origin/main`, independent of PD-936 and of the sibling import.

### 5.1 The three retargeted-but-unreached lines (unchanged by repair)

```
$ python3 -m pytest -q \
  "scripts/tests/test_f15f16_mode_truth.py::test_the_launcher_banner_and_sidecar_carry_the_notice" \
  "scripts/tests/test_fix11_mode_axis.py::test_the_mode_is_recorded_and_handed_to_the_engine" \
  "scripts/tests/test_u3_standard_ceiling_restored.py::test_the_launcher_banner_carries_it_end_to_end"
3 failed in 3.11s   (HEAD)     3 failed in 1.87s   (PRE)   — same three ids, same cause
```

All three fail earlier at `launcher.dispatch(...) == 0` with rc 3:
`MODEL PLAN REFUSED: ultra: phase 'P-STYLE-PREVIEW' (capability 'image_render') has no eligible
route`. Pre-existing environment/route refusal, identical on PRE and HEAD. The retargeted ceiling
line is never reached; a different unit fixes the route.

---

## 6. Push and ancestry proof

**Push (fast-forward only, no force, never to main):**

```
$ git push origin HEAD:refs/heads/pd/fl02-intake-driver
To https://github.com/trevorotts1/openclaw-onboarding.git
   8b72fe4da..b81cafa3a  HEAD -> pd/fl02-intake-driver
```

**Remote head read back, literal, 40 hex:**

```
REMOTE = b81cafa3ac6ea2fadb1a55e50fe3dee4f37d658c
LOCAL  = b81cafa3ac6ea2fadb1a55e50fe3dee4f37d658c      EQUAL = YES
```

**No rewrite — PRE is an ancestor of the new head:**

```
$ git merge-base --is-ancestor 8b72fe4da2e3ec1b2b6edf53346157b9c90c6a00 HEAD
rc = 0
```

---

## 7. What I could not prove / did not do

1. **A1-b is red at HEAD, PRE, and `origin/main` — pre-existing, not proven fixed.** The cause is
   the missing `.mode-plan.json` from `_poller_rig`; fixing it is a different unit. I did not
   weaken or remove the test.
2. **The three rc-3 rows are not execution-proven at the retargeted line.** Identical failure on
   PRE and HEAD; the retarget is correct by inspection and by the two proven constant-named sites,
   but those three never reach it.
3. **`git merge-tree` is a static merge, not a full rebase or build.** It proves the pair no longer
   textual-conflicts; it does not run the suite on the combined tree. The suite was run on this
   branch's own HEAD.
4. **Only one sibling was listed on the card** (`pd/fl28-model-router` #3185). If another PR rides
   the same batch, it was not named to me and was not tested.
5. **`model_router.py:993` stale comment** (`"...100 -- and it is load-bearing"`) still describes
   `ULTRA_OPERATOR_CEILING`; PD-936 is test-only and did not change router behaviour. Left untouched.
6. The final head after this documentation commit is proven with `git ls-remote`; this file cannot
   contain its own future commit SHA.
