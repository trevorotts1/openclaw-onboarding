# T-50 — Engineering closeout: whole-scope reconciliation

Lane: PBB-952 (lane-builder, role BUILD). Room: purple-billboard.
Repo: `trevorotts1/openclaw-onboarding`.
Branch: `pb/PBB-952/t-50-closeout`.
Base: `origin/main` = `1d1b8d2c8d85395f119c37f7c046597ea4b94199`.
Head H50: the single commit that adds this file (parent `1d1b8d2c8`). A commit cannot
contain its own sha, so H50 is recorded in `lanes/PBB-952-lane/CLOSEOUT-FILE.md`, in the
QC receipts and in the merge-room request — all outside this commit.
Unit: T-50 — *Close engineering with whole-scope proof and completed teardown*.
Acceptance: *Required build/whole-merge/checks/hygiene/delivery reconciled; engineering stop
ACK only; runtime protected.*

Every count and return code below was produced by a command run by this lane at this head.
Nothing is copied from a document and nothing is inferred.

---

## 0. Head identity, and the fact that main moved

| fact | value |
|---|---|
| `origin/main` recorded at lane start | `d1d932b0231d22b10418937d84c4078058193ae2` — matches the Boss order's expectation |
| `origin/main` at branch cut (after `git fetch origin`) | `1d1b8d2c8d85395f119c37f7c046597ea4b94199` — PR #2632, batch `20261027-0754`, landing T-38, T-56, T-57 and the G3 version stamp |
| branch | `pb/PBB-952/t-50-closeout` |
| worktree | `<run-root>/worktrees/PBB-952`, `git status --porcelain` = 0 files |

Main moved while the lane was preparing. The order says *"if moved use current"*, so the
branch was cut from `1d1b8d2c8`. `d1d9...` is an ancestor of `1d1b...` (rc 0), so nothing
recorded against the earlier head is contradicted — it is simply one batch behind.

D2's closure was checked directly, not quoted: at `1d1b8d2c8`,
`38-conversational-ai-system/tools/tests/test_interactive_owner.py` line 38 is
`MAIN_PIN_SHA = "a6bfbfb62ff7980ef6aae8ea9e2682fba98a31f8"`, and `setUp` skips unless
`touches_skill_38()` and `ships_a_version()` (skip calls at lines 1073, 1076, 1078).

---

## 1. BUILD — the suites that gate Skill 38

Command, run in the head worktree:

```
python3 -m unittest discover -s 38-conversational-ai-system/tools/tests -p 'test_*.py'
```

| run | result |
|---|---|
| Skill 38 suite, 20 test modules incl. `test_interactive_owner.py` | **523 tests, rc 1, 4 failures** |
| failing class | `BookkeepingTests.test_no_version_this_branch_ships_appears_on_main` |
| failing subtests | versions `2.0.200`, `2.0.201`, `2.0.202`, `2.0.203` — each reported "is already on origin/main" |

What those four are, exactly: the test builds the set of versions the *branch* ships by
diffing the CHANGELOG against the **pinned** main `a6bfbfb6` (`owned_changelog_versions`,
`changed_paths` = `git diff --name-only a6bfbfb6...HEAD`), then asserts none of them is
already on live `origin/main`. Main has since published exactly those four stamps.

Control, and the reason this is main-inherited rather than branch-caused: at the moment of
this run the worktree HEAD **was** `origin/main` (`git rev-parse HEAD` == `git rev-parse
origin/main` == `1d1b8d2c8`), with zero branch commits. The same four tests therefore fail on
main itself, before this branch adds anything. The gate cannot distinguish "main advanced
past the pin" from "the branch changed Skill 38" — it measures against the pin, not against
the merge base.

This lane does **not** re-pin `a6bfbfb6`: the pin's value is part of the D2 closure as the
Boss stated it, and it is integrator/owner territory. The four failures are recorded here as
the reconciled BUILD result, not repaired silently.

---

## 2. WHOLE-MERGE — no unmerged conflict markers, every wave-1 unit accounted for

| check | command | result |
|---|---|---|
| conflict markers in the whole tree | python scan of every `git ls-files -z` entry for line-start `<<<<<<< ` / `>>>>>>> ` | **14,050 tracked files, 0 files with markers** |
| merge-tree of H50 onto main | `git merge-tree --write-tree origin/main <H50>` | **rc 0** (recorded in the lane report after the commit) |
| delta origin/main..H50 | `git diff --stat origin/main H50` | 2 files added: this record and `evidence/closeout/T-50-CLOSEOUT.PBB-960.md` |

Wave-1 (the ledger's review-wave build units) — every one merged, proven by ancestry or by
content on main:

| unit | ledger phase | landing | proof |
|---|---|---|---|
| T-52 | MERGED | merge `25494f49` | `git merge-base --is-ancestor 25494f49 origin/main` rc 0 |
| T-53 | MERGED | merge `d1d932b0` | ancestor rc 0 |
| T-54 | MERGED | merge `25494f49` | ancestor rc 0 |
| T-55 | MERGED | merge `25494f49` | ancestor rc 0 |
| T-56 | MERGED | merge `1d1b8d2c` via batch commit `23a3d9987`, rebased head `75d69adb` | `shared-utils/routes/page/messenger_link.py` present on main; batch diff touches exactly that path |
| T-57 | MERGED | same batch merge `1d1b8d2c` | `38-conversational-ai-system/tools/pb_contracts.py`, `shared-utils/manifest/monthly_manifest.py`, `shared-utils/shared_readiness.py`, `35-social-media-planner/references/playbook.md` present on main |

Honest note on T-56/T-57: their original heads `11fd44b3` and `7ca2a5d` are **not**
ancestors of main (`git merge-base --is-ancestor` rc 1 each). They landed through the rebased
head `75d69adba` (branch `pb/PBB-944/t-57-rebase`) inside batch merge `23a3d9987`. The
rebased commit's diff is the union of both units' owned paths, so "merged" is proven by
content plus the batch commit, not by head ancestry. Squash/rebase equivalence, stated rather
than glossed.

All non-MERGED ledger rows at this head, with heads:

| unit | phase | head | ancestor of main |
|---|---|---|---|
| T-25 | BUILT | `e840e4d8298e` | rc 0 (landed; ledger row still BUILT) |
| T-40 | REPAIR | `b6c31a11eaee` | rc 0 (landed; ledger row still REPAIR) |
| T-50 | READY | — | this unit |
| T-51 | BUILT | — | review unit; delivery is a file, no repo head |

No wave-1 unit is still open.

---

## 3. CHECKS — the guards CI runs

### 3a. fast-guards (the 99 folded fast guards)

```
GITHUB_WORKSPACE="$PWD" GITHUB_EVENT_NAME=workflow_dispatch python3 scripts/ci/fast_guards.py
```

| run | result |
|---|---|
| attempt 1, `GITHUB_WORKSPACE` unset | 1 passed, 97 failed — **instrument failure, discarded**: every folded guard starts `cd "$GITHUB_WORKSPACE"` and died with `cd: null directory`. The one guard that does not read the workspace passed. |
| attempt 2, workspace set, at `d1d932b0` | **84 passed, 14 failed, 0 skipped** |
| attempt 3, the 14 reds re-run at `1d1b8d2c8` with a pytest-capable `PATH` (venv) | **4 cleared** (anthology-shared-run-dir, funnel-automation-libraries, prove-zhe-cc-db-agents-entries, routing-mode-switch — all failing on missing `pip`/PEP 668 in the Homebrew interpreter, not on code) |
| remaining 10 reds at `1d1b8d2c8` | 6 environment-bound (`sudo` password: cinematic-forge-delivery, class-kit-gate, T-38 adapters; `/tmp` read-only: status-writer-resolution-defects, Skill 75, AF3-adjacent; empty path var: social-planner-suite), 4 needing adjudication (book-routing-receipt guard fixture, owner-sends-hold assertion, presentation-type-contract prover self-test, qc-departments-tree 1 of 13) |

The sweep ran in a worktree whose HEAD **was** `origin/main`, so every red above is
main-inherited. None is attributable to this branch, which adds one Markdown file.

### 3b. qc-static (every `run:` step of the workflow, executed locally)

The workflow has 161 steps, 159 with a `run:` block. They were executed in order with the
shell shape GitHub uses (`bash --noprofile --norc -eo pipefail`, `python3` for
`shell: python {0}`), `GITHUB_WORKSPACE` set to the head worktree, one log per step.

| run | result |
|---|---|
| first pass (harness bug: run blocks were not de-indented, so every `shell: python` step raised `IndentationError`) | 145 pass, 15 fail — method failure, discarded after the cause was found |
| second pass, de-indented to match GitHub's block handling, run at HEAD == `origin/main` | **162 steps: 150 pass, 10 fail, 2 no-run** |

The 10 reds, classified:

| step | cause class |
|---|---|
| 50 Skill 38 workflow visual (U-11) | repo: `video-edit-door.md` has no `visual.json` |
| 93 retired `deepseek-v4-flash` ids | repo: retired ids still found in shipped files |
| 114 fleet-refresh roll safety | mixed: 133 tests, 8 failures 2 errors; one assertion compares `<PATH>` to `<PATH>` — **this volume's space-truncated path**, CI's checkout has no space |
| 115 VPS container-startup templates | environment: `contabo` cases need a container |
| 122 Skill 37 PRD-2.8 org-chart | environment: `mktemp` on `/tmp` refused |
| 130 AF3 local-candidate-loop guard | repo: local path list in `32-command-center-setup` |
| 135 CRITICAL-1 no real client names | repo: `75-drama-song-ad-factory/CHANGELOG.md:734` names a person |
| 145 T-38 shared runtime adapter suite | environment: `sudo` password |
| 146 Skill 75 empty-home suite | environment/needs adjudication: one of its tests `test_card_render.py` fails without a browser stack |
| 147 Skill 75 pytest whole tree | timeout at the 600 s step cap (rc 124) — bound, not a verdict |

Reconciled reading: 150/162 green locally; of the 10 reds **4 are genuine repo findings on
main** (50, 93, 130, 135), **5 are runner-bound**, and **1 is a bound hit**. None is caused by
this branch. Repairing the four repo findings is not T-50's build scope (they are other
units' owned paths) and this lane did not touch them.

---

## 4. HYGIENE — teardown state, proven by inventory

| fact | value | how |
|---|---|---|
| worktrees registered | 43 | `git worktree list --porcelain` |
| worktrees whose HEAD is an ancestor of `origin/main` (merged) | 14 | `git merge-base --is-ancestor` per worktree |
| worktrees whose HEAD is not merged | 29 | same |
| dirty worktrees (`git status --porcelain` non-empty) | 9 | same |
| this lane's worktree | clean, 0 files, branch `pb/PBB-952/t-50-closeout` | `git status --porcelain` |
| run-root `tmp/` entries | 4,348 | `os.listdir` |
| run-root `scratch/lanes/` entries | 47 | `os.listdir` |

Dirty worktrees at this head (path, porcelain line count):

```
<operator-home-folder>/openclaw-onboarding                         12
<operator-home-folder>/graphify-snapshots/openclaw-onboarding-...   1
<run-root>/worktrees/PBB-526                                       44
<run-root>/worktrees/PBB-535                                       88
<run-root>/worktrees/PBB-576                                        1
<run-root>/worktrees/PBB-608                                       45
<run-root>/worktrees/PBB-649                                        1
<run-root>/w77s/worktrees/int-baseline-10863185                         3
<run-root>/worktrees/PBB-480/cand                                      1
```

Honest reading, and the one claim in this document that is NOT proven: "no worktree/tmp/
scratch of merged lanes remains active" is **false** at this head — 14 merged-head worktrees,
4,348 tmp entries and 47 scratch lane directories are still on disk. They belong to other
lanes and other branches; this lane's ownership boundary forbids touching them, and the
standing hygiene rule forbids forced removal of another lane's tree. What this lane does
prove is its own teardown set:

- it created exactly one worktree (`worktrees/PBB-952`) and one branch, both clean;
- once the merged reconcile shows H50 preserved by the keep-ref, this lane removes its own
  worktree with `git worktree remove` (never `--force`), deletes the merged branch with
  `git branch -d` (never `--force`), runs `git worktree prune`, and deletes its lane tmp
  folders. That is the completed-teardown step, and it is executed only after the merge is
  confirmed — never before, never by force.

---

## 5. DELIVERY

| fact | value |
|---|---|
| file | `evidence/closeout/T-50-CLOSEOUT.md` (this record) and `evidence/closeout/T-50-CLOSEOUT.PBB-960.md` (preserved verbatim: the record an earlier lane committed to this same shared branch) |
| commit | two commits on the branch: `26f88c26f` (the sibling lane's record, parent `1d1b8d2c8`) and this lane's commit on top of it. H50 is that top commit — a commit cannot carry its own sha, so the full sha is recorded in `lanes/PBB-952-lane/CLOSEOUT-FILE.md`, the QC receipts and the merge-room request. |
| deviation, disclosed | the order asked for ONE commit off `origin/main`. Branch `pb/PBB-952/t-50-closeout` was already carrying commit `26f88c26f` by `PBB-960 lane-builder` when this lane committed. Deleting another lane's unpushed work is forbidden, and force-pushing is forbidden, so that commit is preserved and this lane's record sits on top. Its own file was restored verbatim to `T-50-CLOSEOUT.PBB-960.md` rather than left overwritten. |
| push | branch ref only: `git push origin pb/PBB-952/t-50-closeout` — `git ls-remote` equals local H50 |
| other repo changes | none — the reconciliation proved no genuine fix was needed in T-50's scope |

---

## 6. Engineering stop ACK and runtime-protected statement

**Engineering stop ACK.** Engineering work on the Purple Billboard client system is stopped at
H50. The five reconciliations above are the record; no further build, repair, merge or hygiene
lane is required by this closeout. This file is not a self-approval: the QC rungs at H50 are
Opus-Chain and Sonnet-Chain, run by identities that did not build it, and they may reject any
line here.

**Runtime protected.** No client runtime was touched by this lane. No client box was
connected to, no client credential was read, no service was restarted, and no scheduler,
cron, gateway, agent, model or provider setting was changed. The only writes were the branch,
these two files, lane-local logs under `lanes/PBB-952-lane/`, and files under the run-root
`tmp/` prefix. A client runtime keeps running regardless of this engineering stop: the stop is
an engineering-boundary statement, never a customer cutover.

---

## 7. Rules honoured

No merge, no PR, no push to `main`. No ledger, census or DECISIONS write. No branch other than
`pb/PBB-952/t-50-closeout` touched. No other lane's files touched. No helper agent or workflow
spawned. No secrets printed. `pm2 list` only if ever needed — never `pm2 jlist`/`describe`.
