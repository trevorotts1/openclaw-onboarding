# REPAIR-REPORT — PD-925 (PR 3324) — batch-merge ejection

- Unit: **PD-925** — PD-925: sealed-record retargets, mutation proofs, before and after
- PR: **3324** (https://github.com/trevorotts1/openclaw-onboarding/pull/3324), base `main`
- Branch: `pd/fl35-sealed-record--hold-d23-d24`
- Repair branch: `repair-PD-925` (local), pushed fast-forward onto the unit branch
- Reporter: `[deepseek-chain] PD-925 repair lane`
- Scratch: `TMPDIR=/Volumes/mac mini m4/swarm-contract/loop-control/pd-fix/tmp/PD-925/work.zgwkLd`

## 1. The conflict as given — and what the evidence actually says

The lane brief pointed at
`/Volumes/mac mini m4/swarm-contract/_batch-merger/runs/openclaw-onboarding-20261113-145033/evidence/3324-CONFLICT.txt`.

**That file does not exist.** Named sources checked:

- `ls` of `.../runs/openclaw-onboarding-20261113-145033/evidence/` → 16 files, all `*-CONFLICT.txt`:
  `3203, 3204, 3220, 3307, 3312, 3315, 3319, 3320, 3322, 3323, 3328, 3334, 3336, 3340, 3344, 3350`.
  No `3324-CONFLICT.txt`.
- `find` over the whole `_batch-merger` tree for `3324*` → one hit only,
  `mirrors/trevorotts1__openclaw-onboarding.git/refs/remotes/pr/3324`. No evidence artifact.
- Not checked: any merger state outside `/Volumes/mac mini m4/swarm-contract/_batch-merger`.

So **no conflicted path is named anywhere** — the engine recorded the ejection without a path.

What the run does record, verbatim:

`runs/openclaw-onboarding-20261113-145033/RESULT.json` → `members["3324"]`:

```json
{
 "state": "EJECTED",
 "sha": "91dc54bba92ec377c6a99ba6e59eb91329167535",
 "kind": "CONFLICT",
 "reason": "it is built on a pull request that was left out of this batch",
 "batch_pr": null,
 "merge_commit": null
}
```

`runs/openclaw-onboarding-20261113-145033/ledger.json` → member `3324`, and events:

```
"9:53 AM Eastern #3324 draft marked ready"
"9:55 AM Eastern EJECTED #3324 [CONFLICT] it is built on a pull request that was left out of this batch"
```

ledger member: `title` = `PD-925: sealed-record retargets, mutation proofs, before and after`,
`branch` = `pd/fl35-sealed-record--hold-d23-d24`, `cross` = `false`, `evidence` = `""` (empty).

**Reading:** the engine flagged a *stacking* condition, not a textual one — and recorded `cross: false`
and an empty `evidence` string, i.e. it produced no path. GitHub's own view of PR 3324 at repair time:
`mergeable: MERGEABLE`, `mergeStateStatus: BEHIND`, `baseRefName: main`, `headRefOid: 91dc54bba92e…`.
Base is `main`, not another PR head, so the "built on a PR left out of this batch" reason is **not
supported by the PR's base**. Whether that classification was stale or a misread of the batch
composition is **unproven** — see §7.

## 2. Shas merged

| Role | SHA |
|---|---|
| Unit head (PRE), proven by `git ls-remote --heads origin pd/fl35-sealed-record--hold-d23-d24` | `91dc54bba92ec377c6a99ba6e59eb91329167535` |
| `origin/main`, proven by `git rev-parse origin/main` | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` |
| Merge base | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| Merged head (NEW) | `cc025bcc9f85d53370c94a704dc5dbedd1c83110` |

`origin/main` equals the sha the brief named, byte for byte.

```
$ git merge origin/main
Merge made by the 'ort' strategy.
 66 files changed, 6769 insertions(+), 65 deletions(-)
$ echo $?
0
```

## 3. Conflict: it did not reproduce

`git merge origin/main` exited **0**. No `CONFLICT`, no unmerged path:

```
$ git status --porcelain
(empty)
```

**The conflict does not reproduce, and no resolution was invented.** Proof that it *cannot* reproduce
for this unit's files — every one of the 24 files the unit touches, classified against the merge base:

```
$ git diff --name-only 1a476d2cb 91dc54bba | ... blob/existence matrix
  12 main-untouched        # file exists at merge base AND at origin/main, blob sha IDENTICAL
  12 new-in-unit-only      # file absent at merge base AND absent at origin/main  → clean add
   0 main-MODIFIED
   0 ASYM
```

- **12 files** are byte-identical between the merge base and `origin/main` — main never touched them,
  so no hunk of the unit can collide with main on them.
- **12 files** are new in this unit (tests and the PD-300b/PD-306/PD-317/PD-925 reports) and do not
  exist on main at all — an add cannot collide with a modification.

Blob shas for the 12 pre-existing files (merge-base blob == main blob, i.e. unchanged by main):

| File | blob @merge-base == @main | blob @PRE == @merged |
|---|---|---|
| `…/presentation_job/dispatcher.py` | `d019c07d59` | `384c0584f1` == `384c0584f1` |
| `…/presentation_job/execution_stamp.py` | `e60ff386f2` | `0a7b767368` == `0a7b767368` |
| `…/presentation_job/parallel_prompt_worker.py` | `306b5e3d9a` | `1ecdbb2025` == `1ecdbb2025` |
| `…/presentation_job/phases.py` | `64cd8cfabe` | `fff2e658a4` == `fff2e658a4` |
| `…/presentation_job/runfacts.py` | `31f23642f3` | `2045843160` == `2045843160` |
| `…/presentation_job/state.py` | `6fb61c44cb` | `659739c7c6` == `659739c7c6` |
| `…/qc_aggregate.py` | `863c2d7a80` | `abb120e964` == `abb120e964` |
| `…/tests/negative_fixtures.py` | `9842f612e3` | `ff37feee9e` == `ff37feee9e` |
| `…/tests/test_intake_provenance.py` | `d8a7676be1` | `5a0986f871` == `5a0986f871` |
| `…/tests/test_pres001_unit_contracts.py` | `08ee7e2d85` | `4fea3050b0` == `4fea3050b0` |
| `…/tests/test_verifier_registry.py` | `208a8b19e0` | `db4d4cd4cf` == `db4d4cd4cf` |
| `…/verifier_registry.py` | `56b21e1435` | `24a915a051` == `24a915a051` |

(`…` = `23-ai-workforce-blueprint/templates/role-library/presentations/scripts`.)

### Resolution per hunk

**None.** Zero conflicted hunks, therefore zero resolutions. Both sides' intent is preserved by
construction, not by hand:

- **main's content stays** — all 66 files main brought in are present at the merged head, unmodified
  by the unit (main-side paths do not intersect the 12 pre-existing unit files; the 12 new unit files
  are additions main never had).
- **this unit's intent stays** — all 24 unit files are byte-identical at PRE and at the merged head
  (`blob @PRE == blob @merged`, 24/24 in the table above and its 12 new siblings).

Nothing was deleted from either side. No file was resolved by discarding one side wholesale.

## 4. Rows at the merged head — by test id

Working dir: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts`,
`TMPDIR` in scratch, no `/tmp`.

### 4.1 The unit's own three retargeted rows — MERGED HEAD `cc025bcc9`

```
$ python3 -m pytest \
    "tests/test_verifier_registry.py::test_slice2_priority_shift_both_directions" \
    "tests/test_verifier_registry.py::test_slice2_final_qc_both_directions" \
    "tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_control_clean" \
    "tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes" \
    -p no:cacheprovider -q
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes
1 failed, 3 passed in 0.12s
```

**The three PD-925 rows PASS** (all three are among the `3 passed`; the only `FAILED` is the fourth,
not one of the unit's three).

### 4.2 Both named test files — MERGED HEAD

```
$ python3 -m pytest tests/test_verifier_registry.py tests/test_negative_fixtures.py -p no:cacheprovider -q
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes
1 failed, 42 passed in 0.82s
```

### 4.3 The same rows at the unit base `91dc54bba` (PRE), for comparison

```
$ python3 -m pytest <the same four ids> -p no:cacheprovider -q
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes
1 failed, 3 passed in 0.44s

$ python3 -m pytest tests/test_verifier_registry.py tests/test_negative_fixtures.py -p no:cacheprovider -q
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes
1 failed, 42 passed in 0.48s
```

### 4.4 Verdict on the one red row

`tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes`
is **red at the base commit and red at the merged head, same id, same counts (1F/42P both sides)**.
It is **pre-existing**, not caused by this merge: `AF-EXEC-STAMP` on `renders/slide-01..04.png` at
`P-SHIFT-QC`, the same cause PD-925's own BUILD-REPORT §5.3 and PD-300b's §5.5 both name as red at
baseline. No test was weakened, skipped or removed to reach this state.

**Rows green:** 3 of 3 unit rows green; suite 42 passed. **Rows red:** 1, pre-existing and pre-dating
the merge (identical at base).

## 5. Ancestry proof

```
$ git merge-base --is-ancestor 91dc54bba92ec377c6a99ba6e59eb91329167535 cc025bcc9f85d53370c94a704dc5dbedd1c83110
$ echo $?
0
```

The PRE head is an ancestor of the new head. The push is therefore a fast-forward; no history was
rewritten. (After the report commit the new head moves again — the same check is re-run against the
final head in §6 and re-proven in §8.)

## 6. Remote-head proof

```
$ git ls-remote --heads origin pd/fl35-sealed-record--hold-d23-d24
<40-char sha>	refs/heads/pd/fl35-sealed-record--hold-d23-d24
```

The remote sha must equal the local `HEAD` sha exactly, and
`git merge-base --is-ancestor <PRE> <new-head>` must exit 0 — both re-proven after the report commit
and after the push (§8).

## 7. What I could NOT prove

- **No conflicted path was ever named.** `3324-CONFLICT.txt` does not exist in the run's `evidence/`
  directory or anywhere under `_batch-merger`; the ledger's `evidence` field for 3324 is empty. So the
  engine's own view of *which* path it thought conflicted cannot be recovered from this run.
- **Why the engine classified 3324 as `CONFLICT` is unproven.** The recorded reason ("built on a pull
  request that was left out of this batch") is not supported by the PR: `baseRefName` is `main`, not a
  PR head, and `cross` is `false`. Whether the classifier was stale, or read a batch-composition
  dependency as a textual conflict, is unknown. I did not read the merger's classifier source, so I
  cannot say which.
- **What the merger actually merged onto** is taken from this run's `RESULT.json` (`main: ebf5c769…`).
  I did not independently verify that no integration branch other than `main` was in play.
- **GitHub's required checks** on the new head were not observed. Only local pytest rows were run.

## 8. Push and re-proof

```
$ git push origin HEAD:refs/heads/pd/fl35-sealed-record--hold-d23-d24
```

(Fast-forward; output and re-proof of the 40-char remote head and the ancestry exit code are appended
below after the push.)
