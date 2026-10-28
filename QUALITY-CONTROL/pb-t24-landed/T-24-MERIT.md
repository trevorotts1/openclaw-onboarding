# T-24 — merit review of its receipt's two non-zero exits

Unit: **PBB-688** (BUILD). Ownership: T-24's checks and my own verification files only.
Repo: `$HOME/openclaw-onboarding`. Branch: `pb/PBB-688/t-24-checks`.
Target: `origin/main` at `5b3e8005ab2a6526bfe19f7d3bad4f2dbd744a76`.

Everything below was run by me, at the real head, with exit codes captured.

## 1. Both failures reproduced

The live receipt is
`$HOME/loop-control/Purple-Billboard-Client-System-Build/qc/T-24.25576e460a964b37d39523d50ed21e2e287c130c.json`.

The two records carrying a non-zero `exit_code` are:

| # | recorded command | recorded exit | re-run at the real head |
|---|---|---|---|
| 1 | `git merge-base --is-ancestor dc3a1503c0819cc1a7fcf05faba34e752ae50bb3 origin/main` | 1 | **rc=0** |
| 2 | `git cat-file -e origin/main:definitely-not-here-xyz-574.md` | 128 | **rc=128** (reproduced) |

Controls run on the same instrument, same shell mode, same repo:

```
git merge-base --is-ancestor 75a5a26a6bf7298eb4e3e1adcd7465ea4c6ec7c2 origin/main   rc=0
git cat-file -e origin/main:README.md                                              rc=0
git cat-file -e origin/main:definitely-not-here-xyz-574.md                         rc=128
fatal: path 'definitely-not-here-xyz-574.md' does not exist in 'origin/main'
```

So the cat-file zero (128) is a real abort on an absent path, and the same instrument
returns 0 on a known-present path: it discriminates.

**Failure 1 is not reproducible as a failure.** It was recorded while T-24 was still an
open PR ("non-zero as required: unit not yet merged"). T-24 has since landed, and the
identical command now exits 0. Nothing needs rewriting — the record is stale.

## 2. The 76700ba3-versus-dc3a1503 premise is false at this head

The task brief states the ancestry check compares `merge_sha 76700ba3` to `origin/main`
while the unit head is `dc3a1503`, and that squash made that permanently impossible.
I tested both spellings rather than assuming:

```
git merge-base --is-ancestor dc3a1503c0819cc1a7fcf05faba34e752ae50bb3 origin/main   rc=0
git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main   rc=0
```

Both are ancestors of `origin/main`. **Squash confirmed: NO.** The landing was a chain of
real two-parent merge commits, all preserved:

```
76700ba36  parents 1e489119a 72bef6c57  Merge train: 2 PRs — T-22 + T-24 (#2582)
72bef6c57  parents 4f8796db4 1e489119a  Merge origin/main into batch/pbb582-t22t24
4f8796db4  parents 62790a363 dc3a1503c  Merge T-24 (dc3a1503c) into batch/pbb582-t22t24
dc3a1503c  parents c12c94da8             T-24: wire qc-pb-contracts.sh into qc-static.yml
```

`git rev-list --first-parent origin/main` puts `76700ba3` at index 8 — it is on main's
first-parent spine, not collapsed into a new sha. `git rev-list --ancestry-path
dc3a1503..76700ba3` returns exactly the three merge commits above.

Consequence for step 1 of the brief: the ancestry check **can** return 0 under the correct
invocation (plain `merge-base --is-ancestor <head> origin/main`), so per the brief I use
that invocation instead of designing a substitute. No content check is required to rescue
this receipt; one is supplied anyway for the case a real squash ever occurs.

## 3. The check that means something, and it can fail

`QUALITY-CONTROL/pb-t24-landed/check_t24_landed.py` — exit 0 landed / 1 not landed /
2 instrument error.

1. **Ancestry first.** `git merge-base --is-ancestor <head> <target>` rc=0 → LANDED.
   This is the proved invocation above.
2. **Content fingerprint otherwise.** Compute `git patch-id --stable` for the unit's diff
   (against its first parent when it is a merge), then compare it against every commit on
   the target that touches the unit's paths. A squash rewrites the sha but keeps the
   patch-id, so content that survived a squash still passes.
3. Unresolvable revisions are `rc=2` aborts, never verdicts.

Self-check: `python3 QUALITY-CONTROL/pb-t24-landed/test_check_t24_landed.py`

```
positive  rc=0 LANDED: dc3a1503 is an ancestor of origin/main (commits preserved)
reshape   rc=0 LANDED: dc3a1503 carries 34f6da7f's content fingerprint 534c0e8608b3 (sha not preserved)
negative  rc=1 NOT LANDED: no commit on origin/main carries 436c4687's content fingerprint 13ef9732f09a
negative control FAILED the check as required, with a verdict not a crash
abort     rc=2 INSTRUMENT ERROR: 0000000000000000000000000000000000000000 does not name a commit
RESULT: PASS
```

The **reshape** row is the squash-shaped positive: `git commit-tree` of `dc3a1503`'s own
tree with its own parent, so identical content under a different sha, not an ancestor of
main. It passes through the fingerprint branch, proving that branch works and that the
positive is not the ancestry shortcut in disguise.

The **negative** row is the required negative control: a real dangling commit object whose
content is nowhere on main. It fails with a verdict, and the test asserts the output starts
`NOT LANDED` so a Python traceback (also rc=1) cannot masquerade as the control passing —
that exact false-green appeared during development and was fixed (`errors="replace"` on the
git subprocess, plus the stdout assertion).

## 4. The `git cat-file -e` absent path: REMOVED, not replaced

Reading: it is a deliberate instrument probe, not a unit check. The path is literally named
`definitely-not-here-xyz-574.md`, it is recorded as `EXPECTED-FAIL known-absent`, and it is
paired two rows earlier with `git cat-file -e origin/main:README.md (EXPECTED-PASS
known-present)`. Its only job is to prove that `git cat-file` discriminates — an instrument
self-test living inside a unit receipt. It asserts nothing about T-24, so a `128` in that
row was never a defect and can never be made 0 without lying.

Decision: **remove** it. It is superseded by the real content check above, which is a
failing-capable verdict about the unit rather than a probe about the tool. Its legitimate
function (proving the instrument discriminates) is served by the positive/negative controls
in `test_check_t24_landed.py`, which are executable and re-runnable instead of a recorded
transcript.

I did not edit the live receipt: the brief forbids writing receipts, and the receipt belongs
to the ledger's reconciliation lane.

## 5. `receipt_problem` before and after

Run against the kit at `~/.claude/skills/swarm-control/swarmctl.py`, unit row from the live
ledger.

```
BEFORE  live root                       attempt=0 author=None  -> 'receipt missing author'   rc=1
```

I built a scratch candidate from the live receipt (in `scratch/lanes/PBB-688/`, never in
`control/qc/`) applying only my part: `command`/`exit_code` re-keyed to the kit's
`cmd`/`exit` schema, the re-run ancestry recorded at rc=0, the absent-path probe dropped,
`attempt` set to the positive integer the kit requires. 17 checks, none non-zero.

```
AFTER (receipt repaired, live ledger untouched)
                                        attempt=0 author=None  -> 'receipt attempt does not match the ledger'   rc=1
AFTER (same, plus a SIMULATED ledger carrying attempt=1, an author, and the receipt's base)
                                        attempt=1 author=...   -> None (ACCEPTED)                                  rc=0
```

The middle row is the honest "after": the receipt is no longer the blocker — the kit now
complains about the **ledger**, not the checks. The bottom row proves the repaired receipt
is fully acceptable to `receipt_problem`, but it required editing a *copy* of the ledger's
T-24 row (attempt, author, base). That is a simulation in my lane folder and is **not**
written back.

One further real mismatch surfaced: the receipt's `base` is `75a5a26a6bf7...` while the
ledger's `base` is `7477816d...`. Resolving which is authoritative is ledger reconciliation,
not a check repair.

Observed, not mine to fix: the live `ledger.json` changed under me mid-run — T-24 `attempt`
went 1 → 0 between two reads a few minutes apart. A concurrent reconcile is writing it. I
wrote to it nowhere.

## 6. What I did not do

No ledger, census, DECISIONS, marker, changelog, bundle or receipt was edited. `origin/main`
was not touched. The T-24 branch `pb/PBB-459/t-24-build` was not touched. The live receipt
was not rewritten. My files are new and live only under `QUALITY-CONTROL/pb-t24-landed/` on
`pb/PBB-688/t-24-checks`.

## 7. Acceptance still waits on the ledger

**Every check on T-24's receipt can now exit 0, and I proved it by running them.** The
ancestry record is fixed by re-running (rc=0, no rewrite needed), and the absent-path probe
is removed rather than coerced. But `receipt_problem` will keep refusing T-24 until the
LEDGER carries a positive `attempt`, a `change_author`, and a `base` that agrees with the
receipt. That is a separate lane's work and it is not mine to close. Acceptance is therefore
**not** claimed here.
