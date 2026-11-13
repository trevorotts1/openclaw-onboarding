# PD-936 — BUILD REPORT: tests still asserting `operator_ceiling == 100`

**Unit:** PD-936 · lane FL02 · branch `pd/fl02-intake-driver`
**Repo:** `trevorotts1/openclaw-onboarding`
**Base head (before this unit):** `a2887c8977141451682da40485e0ef8e89854754` — proven equal to
`refs/heads/pd/fl02-intake-driver` on origin before any edit.
**This unit's commit:** `f187aafa04e1dcbaabb3a8d4ade286d3c8bacc93` (the retarget commit; this
report's SHA-recording commit is the branch head)
**Merge-base with `origin/main`:** `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
**Acceptance row:** A1 (from the ledger row's own `note`; there is no PD-936 brief or spec section — see §0)

---

## 0. Where the work order actually is

The dispatch names a section `### PD-936` in
`/Volumes/mac mini m4/swarm-contract/fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`.
That section does not exist. Measured:

```
$ grep -c "PD-936" .../FINAL/01-BUILD-SPEC.md
0
$ grep -c "PD-934" .../FINAL/01-BUILD-SPEC.md
0
$ ls .../loop-control/pd-fix/briefs/
PD-933-ready-brief.md
```

This matches PD-935's own report ("the brief file for PD-935 does not exist; `briefs/` holds only
PD-933"). A1 is therefore read from the ledger row's `note` plus the dispatch. The ledger text
implemented, quoted verbatim:

> RAISED FROM PD-934, a SECOND independent staleness it found. After the route is satisfied that
> test fails on mode_plan['ceiling']['operator_ceiling'] == 100 while the actual value is 400 - set
> by FIX 61 commit 7e5c4d6f3 at model_router.py:965 and pinned by test_fix11_mode_axis.py and
> test_u3_standard_ceiling_restored.py. So a test still expects the pre-FIX-61 ceiling. THE JOB:
> find every test still asserting operator_ceiling 100, decide for each whether it is stale
> (retarget to the FIX 61 value with the FIX 61 commit cited) or whether FIX 61 is wrong for that
> case, and prove the retarget discriminates. Do not silently change a product value to satisfy a
> test.

---

## 1. Verdict: the ASSERTION is stale; the code is correct

No production file was changed. The 400 is the ratified FIX 61 value, recorded in code:

```
$ grep -n "^ULTRA_OPERATOR_CEILING\|^STANDARD_MODE_CEILING" .../presentation_job/model_router.py
965:ULTRA_OPERATOR_CEILING = 400
984:STANDARD_MODE_CEILING = 25

$ sed -n '996,999p' .../presentation_job/model_router.py
996:MODE_OPERATOR_CEILING: Dict[str, int] = {
997-    "ultra": ULTRA_OPERATOR_CEILING,
998-    "standard": STANDARD_MODE_CEILING,
999-    # FIX 61.5: economy stays exactly as it is today (100), not ultra's 400.
```

FIX 61 commit `7e5c4d6f3590e653c456acb6e8c0d4804f640305` ("presentations: Fix 61 — Build real ultra
mode (D2)", Mon Sep 28 22:12 2026 -0400) is an ancestor of `origin/main` (`IN_MAIN`) and of this
branch (`git log origin/main..HEAD | grep -c 7e5c4d6f` = `0`). Its own diff:

```
45:-ULTRA_OPERATOR_CEILING = 100
46:+ULTRA_OPERATOR_CEILING = 400
54:-STANDARD_MODE_CEILING = 100
55:+STANDARD_MODE_CEILING = 25
```

Both producers of the key project the constant, not a literal:

```
1343:    operator = ULTRA_OPERATOR_CEILING      # mode_plan()
1466:    operator = ULTRA_OPERATOR_CEILING      # mode_ceiling()
```

So `.mode-plan.json`'s `ceiling.operator_ceiling` and `concurrency.operator_ceiling` are 400 by
design. The observed value in the failing test is 400. A test asserting 100 is asserting the
pre-FIX-61 world and is stale. FIX 61 is not wrong for any of the five sites found: the key is
documented at both producers as "the GLOBAL human-ratified maximum", and 400 is that maximum.

Two tests already pin 400 and pass **unchanged** (no edit to either file's assertions):

| test id | result on head |
|---|---|
| `tests/test_fix11_mode_axis.py::test_a_client_measured_at_2500_is_capped_at_100_under_ultra` | PASS |
| `tests/test_fix11_mode_axis.py::test_provider_advertising_never_raises_the_operator_ceiling` | PASS |
| `tests/test_u3_standard_ceiling_restored.py::test_the_standard_mode_ceiling_constant_is_the_operators_100` | PASS |

(The first id's name is historical; its body asserts `mode_ceiling(...)["ceiling"] == 400` and
`ULTRA_OPERATOR_CEILING == 400`.)

---

## 2. Files changed

Five **test** files. No production behaviour, launcher, or router line changed.

| file | change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app/test/test_operator_contract_handoff.py` | `mode_plan['ceiling']['operator_ceiling'] == 100` → `== model_router.ULTRA_OPERATOR_CEILING`, FIX 61 comment |
| `.../scripts/tests/test_fix11_client_run_mode_path.py` | `rec["ceiling"]["operator_ceiling"] == 100` → `== model_router.ULTRA_OPERATOR_CEILING`, FIX 61 comment |
| `.../scripts/tests/test_f15f16_mode_truth.py` | `record["concurrency"]["operator_ceiling"] == 100` → `== model_router.ULTRA_OPERATOR_CEILING`, FIX 61 comment |
| `.../scripts/tests/test_fix11_mode_axis.py` | `record["concurrency"]["operator_ceiling"] == 100` → `== model_router.ULTRA_OPERATOR_CEILING`, FIX 61 comment |
| `.../scripts/tests/test_u3_standard_ceiling_restored.py` | `record["concurrency"]["operator_ceiling"] == 100` → `== model_router.ULTRA_OPERATOR_CEILING`, FIX 61 comment |

`git diff --stat`: 5 files changed, 12 insertions(+), 6 deletions(-).

Enumeration that produced the five sites (`grep -rn "operator_ceiling" --include='*.py' | grep 100`):
the handoff test (263), `test_f15f16_mode_truth.py` (351), `test_fix11_client_run_mode_path.py`
(381), `test_fix11_mode_axis.py` (550), `test_u3_standard_ceiling_restored.py` (383). The only
other match is a **comment** in `model_router.py:993`, not a test — left untouched (see §9).

No assertion was weakened, deleted, renamed, skipped or xfailed.

---

## 3. A1 BEFORE — the failing assertion, by test id

```
$ python3 -m pytest -q \
  ".../test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars"
```

```
>       assert mode_plan['ceiling']['operator_ceiling'] == 100
E       assert 400 == 100
.../test_operator_contract_handoff.py:263: AssertionError
FAILED ...::test_launcher_writes_ultra_mode_and_client_route_sidecars
1 failed in 1.21s
```

Captured stdout includes the real sidecar line:
`launcher: run mode ULTRA (source: --mode) ... ceiling 400 ...; recorded in .mode-plan.json`.

The same stale literal in `test_fix11_client_run_mode_path.py` failed identically on base:
`assert rec["ceiling"]["operator_ceiling"] == 100` → `assert 400 == 100`.

---

## 4. A1 AFTER — passing, same ids

```
$ python3 -m pytest -q \
  ".../test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars" \
  "tests/test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance" \
  "tests/test_fix11_mode_axis.py::test_a_client_measured_at_2500_is_capped_at_100_under_ultra" \
  "tests/test_fix11_mode_axis.py::test_provider_advertising_never_raises_the_operator_ceiling" \
  "tests/test_u3_standard_ceiling_restored.py::test_the_standard_mode_ceiling_constant_is_the_operators_100"
.....
5 passed in 1.80s
```

The two retargeted tests flipped from FAIL to PASS; the three pinned tests stayed PASS unchanged.

---

## 5. Mutation proof — the new assertion can fail

Temporary mutation (reverted): in `model_router.py`, both producers changed
`operator = ULTRA_OPERATOR_CEILING` → `operator = 100`, leaving the constant at 400. The tests go
RED, proving the assertion still discriminates rather than always passing:

```
>       assert mode_plan['ceiling']['operator_ceiling'] == model_router.ULTRA_OPERATOR_CEILING
E       assert 100 == 400
E        +  where 400 = model_router.ULTRA_OPERATOR_CEILING
>       assert rec["ceiling"]["operator_ceiling"] == model_router.ULTRA_OPERATOR_CEILING
E       assert 100 == 400
2 failed in 1.28s
```

Reverted with `git checkout -- .../presentation_job/model_router.py`; `git status --porcelain` then
showed only the five test files, and `git diff --stat` for `model_router.py` is empty. Re-run after
revert: `5 passed`. `model_router.py` is byte-identical to `a2887c897`.

---

## 6. Test runs by id — base vs head

| test id | base `a2887c897` | head | note |
|---|---|---|---|
| `test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars` | **FAIL** `assert 400 == 100` | **PASS** | the PD-936 defect |
| `test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance` | **FAIL** `assert 400 == 100` | **PASS** | second reachable stale literal |
| `test_f15f16_mode_truth.py::test_the_launcher_banner_and_sidecar_carry_the_notice` | FAIL (dispatch rc 3, before the ceiling line) | FAIL (same rc 3) | retargeted line not reached — §9 |
| `test_fix11_mode_axis.py::test_the_mode_is_recorded_and_handed_to_the_engine` | FAIL (dispatch rc 3, before the ceiling line) | FAIL (same rc 3) | retargeted line not reached — §9 |
| `test_u3_standard_ceiling_restored.py::test_the_launcher_banner_carries_it_end_to_end` | FAIL (dispatch rc 3, before the ceiling line) | FAIL (same rc 3) | retargeted line not reached — §9 |

Full four-file suite (`test_fix11_mode_axis.py test_u3_standard_ceiling_restored.py
test_f15f16_mode_truth.py test_fix11_client_run_mode_path.py`), base vs head:

```
base: 32 failed, 68 passed in 60.66s
head: 31 failed, 69 passed in 33.70s
removed failures: FAILED tests/test_fix11_client_run_mode_path.py::test_new_branch_records_the_declared_mode_with_its_provenance
new failures:     (none)
```

Exactly one verdict moved, in the intended direction; zero regressions. The targeted handoff test
lives outside those four files and moved FAIL→PASS by itself.

---

## 7. Hunk attribution — merge-base `1a476d2cb` → base HEAD `a2887c897`

| commit | unit | files |
|---|---|---|
| `37fc849c2`, `5ff8a5f22` | PD-001 | `deck-intake-driver.py`, intake tests |
| `bb1ae8042` | PD-011 | `deck-intake-driver.py`, `test_pd_intake_complete_signing.py` |
| `44c9a0ea1` | PD-016 | `deck-intake-driver.py`, `test_pd_intake_frame_wording.py` |
| `f427a31b6` | PD-015 | `deck-intake-driver.py`, `test_pd_intake_owner_msg.py` |
| `27c667070` | PD-004b | `deck-intake-driver.py`, `intake_provenance.py`, two tests |
| `869d0637e` | PD-913 | `deck-intake-driver.py` + 9 script tests + `evidence/PD-913/` |
| `108b092bf` | PD-927 | `intake_bridge.py`, `test_pd927_operator_replay_atomic_turns.py` |
| `87e2458d4` | PD-930 | `test_operator_contract_handoff.py` (atomic fixtures) |
| `2c3d74b92` | PD-932 | `test_operator_contract_handoff.py` (workhorse_model retarget) |
| `7d21a9641` | PD-931 | `test_operator_contract_handoff.py` (`PD_CC_ROOT`) |
| `710ba6d36`, `a2887c897` | PD-935 | `test_operator_contract_handoff.py` (kie fixture), `evidence/PD-935/` |
| **this unit** | **PD-936** | five test files in §2, plus `evidence/PD-936/BUILD-REPORT.md` |

No hunk outside the five named test files and this unit's evidence directory is mine.

---

## 8. Remote-head proof

Before any push:

```
$ git ls-remote --heads origin refs/heads/pd/fl02-intake-driver
a2887c8977141451682da40485e0ef8e89854754	refs/heads/pd/fl02-intake-driver
```

Push of the two commits (retarget + SHA record):

```
$ git push origin HEAD:refs/heads/pd/fl02-intake-driver
To https://github.com/trevorotts1/openclaw-onboarding.git
   a2887c897..827a1b450  HEAD -> pd/fl02-intake-driver
```

Full 40-hex comparison, literal:

```
REMOTE_AFTER=827a1b450a1ddbcac3a154c005602339a8cc74d2
LOCAL_HEAD  =827a1b450a1ddbcac3a154c005602339a8cc74d2
```

Equal. This report has since received its own documentation-only commits; `git ls-remote` is the
live truth for the final head, and every push is repeated with the same literal comparison.

---

## 9. Unproved / carried, stated honestly

1. **Three retargeted lines are not execution-proven.** `test_f15f16_mode_truth.py:351`,
   `test_fix11_mode_axis.py:550`, `test_u3_standard_ceiling_restored.py:383` still fail earlier at
   `launcher.dispatch(...) == 0` (rc 3) — a separate, pre-existing ultra-launch refusal unrelated to
   the ceiling (same class of fixture/route defect PD-935 fixed in the handoff test). The literal→
   constant retarget is correct by inspection and consistent with the two proven sites, but those
   tests never reach the line, so the retarget cannot be shown to flip a verdict here. Fixing the
   rc-3 refusal is a different unit.
2. `model_router.py:993` still contains the comment `"100 -- and it is load-bearing"` describing
   `ULTRA_OPERATOR_CEILING`. It is a stale comment, not a test, and PD-936 is a test-only unit with
   a standing instruction not to change router behaviour. Left untouched.
3. The handoff file contains two CC-tsx-dependent tests documented by PD-935 as environment-gated
   (`PD_CC_ROOT`); they are outside this unit and were not run.
4. No PD-936 spec section or brief exists; the ledger note is the sole authoritative task text
   (§0). If a hidden spec section exists elsewhere, it was not found in
   `03-presentation-department/` (`grep "PD-936"` over that tree returns only PD-935's report).

---

## 10. Result

The assertion was stale; the code is right. Five `operator_ceiling == 100` literals now assert the
FIX 61 maximum via `model_router.ULTRA_OPERATOR_CEILING`, two reachable tests flipped FAIL→PASS,
the mutation turns them RED, zero new failures, and `model_router.py` is untouched.
