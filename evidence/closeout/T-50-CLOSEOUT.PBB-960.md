# T-50 — Engineering closeout reconciliation

Unit T-50, kind `closeout-gate`. Lane PBB-960 (role BUILD). Repo of record
`trevorotts1/openclaw-onboarding`. Branch `pb/PBB-952/t-50-closeout`.

Acceptance clause, verbatim from `ledger.json` unit T-50:

> "Required build/whole-merge/checks/hygiene/delivery reconciled; engineering
> stop ACK only; runtime protected."

Title, verbatim: "Close engineering with whole-scope proof and completed teardown".

Every row below was produced by a command run in this lane; the exit code is
recorded with the row. Nothing here is inherited from a prior report, and no
merge SHA is claimed: this branch is a candidate awaiting independent QC and a
batch merge, and it does not approve itself.

Base (`origin/main`) at the time of this record:
`1d1b8d2c8d85395f119c37f7c046597ea4b94199`.

This file is the only change in this branch's single commit above that base.

---

## R1 BUILD — reconciled

| command | result | rc |
|---|---|---|
| `python3 -I -m unittest discover -s 38-conversational-ai-system/tools/tests -p 'test_*.py'` (in this tree) | Ran 523 tests, failures=4, skipped=1 | 1 |

Disposition of the 4 reds, stated rather than hidden: all four are the four
`BookkeepingTests.test_no_version_this_branch_ships_appears_on_main` subtests
(versions 2.0.200-2.0.203). That gate is branch-scoped by construction: its
`changed_paths()` is `git diff --name-only <MAIN_PIN_SHA>...HEAD`, and its
`setUp` arms only when the diff touches `38-conversational-ai-system` and ships a
version. In a tree whose HEAD **is** `origin/main`, the three-dot diff against
the pin is main's own post-pin history, so the gate arms and then finds main's
own versions on main by definition. The red is an instrument artefact of
measuring main as if it were a branch, not a code defect: the same tree is the
one CI passes on (R3). It is recorded as a known, named limitation of this row,
not suppressed.

## R2 WHOLE-MERGE — reconciled, zero gaps

Every ledger unit with a resolvable commit was tested in its own repository
against that repository's `origin/main`: `git merge-base --is-ancestor <head|
merge_commit> origin/main`. 55 ledger rows; 53 have a resolvable sha; all 53
returned rc 0 in at least one of the two recorded fields. 0 gaps.

| class | n |
|---|---|
| landed via `head` | 41 |
| landed only via `merge_commit` (rebased/squash equivalence) | 9 |
| repo field literal `null`, sha resolved by presence to `openclaw-onboarding` | 3 (T-28, T-40, T-41; each rc 0) |
| excluded | 2: T-50 (this unit), T-51 (review unit, file deliverable, no repo head) |

Repo tips measured: `openclaw-onboarding` `1d1b8d2c8`, `999-setup`
`b449b180ff`, `blackceo-command-center` `3244d5cd77`.

Instrument controls, run in each of the three repos: main tip against main
`rc 0`; a dead sha (`0000...0001`) against main `rc 128`. The instrument
discriminates in all three, so the rc 0 rows above are not vacuous.

`git merge-tree --write-tree origin/main HEAD` in this worktree: tree
`23fc28154a4497017701dd868feb48d5eb83efb6`, rc 0.

## R3 CHECKS — reconciled

Required CI on the main tip, read from the remote rather than from a local
replay: `gh api repos/trevorotts1/openclaw-onboarding/commits/1d1b8d2c8/check-runs`
returned `total_count` 41 with conclusions `{success: 41}`, rc 0.

Targeted static guard affected by a documentation change,
`bash scripts/qc-assert-no-client-names.sh`: rc 1 both before and after this
change (pre-existing on the base tree; this record adds no identifier, and the
guard's own output names the pre-existing hits). The change therefore adds no
new red to it.

Not checked, named rather than implied: the folded 98-guard local replay
(`scripts/ci/fast_guards.py`) was started in this lane at the base tree and did
not complete inside the lane's time budget - one guard aborts on
`externally-managed-environment` when it tries a `pip install`, and the run is
slow. It is therefore **not** cited as a passing row. The authoritative checks
row above is the remote CI on the main tip.

## R4 HYGIENE — reconciled as typed inventory and disposition (teardown NOT claimed complete)

Measured, `git worktree list --porcelain` plus one `git status --porcelain` per
tree:

| fact | value |
|---|---|
| worktrees registered on `openclaw-onboarding` | 42 |
| whose HEAD is an ancestor of `origin/main` (merged) | 13 |
| whose HEAD is not merged | 29 |
| dirty (porcelain non-empty) | 9 |
| run-root `tmp/` entries | 6467 |
| run-root `scratch/lanes/` entries | 47 |
| run-root `lanes/` entries | 268 |

Per the hygiene contract (`HYGIENE.md`), dirty and unmerged items defer
individually and are never force-removed, and another lane's tree is not this
lane's to delete. So the whole-run-root teardown is **not** complete and is not
claimed here; those items remain owed. What this lane can and does prove is its
own teardown set: it created no worktree and no branch, reused the pre-existing
`worktrees/PBB-952` on `pb/PBB-952/t-50-closeout`, and preserved - without
discarding and without committing - the two dirty entries it found there, as a
patch plus a byte copy in its lane folder.

## R5 DELIVERY — reconciled; this record is the delivery

Before this commit, on the base tree:
`git cat-file -e origin/main:evidence/closeout/T-50-CLOSEOUT.md` -> rc 128
(absent); positive control on a known-present path `evidence/acceptance/999.json`
-> rc 0; dead-sha control `0000...0000:evidence/acceptance/999.json` -> rc 128;
`git ls-tree -r --name-only origin/main -- evidence/closeout` -> empty, rc 0.
So the delivery artefact was genuinely missing and is supplied by this one file.

## R6 Engineering stop — ACK only, not a completed stop

Engineering work on this client system is acknowledged as stopped at this
candidate head. This is an ACK, not a completed stop: no product check is
promoted by it, no ledger row is closed by it, and the open obligations named in
R1/R4 stay owed. Closure is granted by independent QC and a batch merge, not by
this file.

## R7 Runtime protected

No client runtime was touched: no box was connected to, no credential read, no
service, scheduler, cron, gateway or agent process started, stopped or
reconfigured, and no model or provider setting changed. All writes made by this
lane are this file, its own lane-folder receipts, and run-root `tmp/` scratch.

---

## What was not checked

Repositories outside the three named above; CI state other than the main tip;
the PR queue; issue trackers; client-runtime live state; the folded 98-guard
local replay (see R3). Absence claims above name their source and their control.
