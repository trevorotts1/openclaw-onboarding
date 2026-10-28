# T-24 — a landing check that can fail

Unit: **PBB-1707** (BUILD, rebuild lane). Ownership: this directory only.
Repo: `<PATH>`. Branch: `pb/PBB-1707/t-24-checks`.
Target: `origin/main` at `8cb74925ad94c05ce9eb639e7554d02fcd780e20`.
Base used: `git merge-base origin/main db7d809ab23c361187eef488c81d563c21730e5b`
= `5b3e8005ab2a6526bfe19f7d3bad4f2dbd744a76`.

Nothing here touches a CHANGELOG, a skill-version file, a CI workflow, or any
existing path. All three files are new and live under `QUALITY-CONTROL/pb-t24-landed/`.

## 1. Why a new check, and not the receipt's recorded check

T-24's live receipt
(`loop-control/Purple-Billboard-Client-System-Build/qc/T-24.25576e460a964b37d39523d50ed21e2e287c130c.json`)
records two non-zero exits. Both were re-run by me at this base, on the same
instrument, same shell mode, same repo:

```
git merge-base --is-ancestor dc3a1503c0819cc1a7fcf05faba34e752ae50bb3 origin/main   rc=0
git cat-file -e origin/main:README.md                                              rc=0
git cat-file -e origin/main:definitely-not-here-xyz-574.md                         rc=128
```

So the ancestry row is **stale, not broken**: it was recorded while T-24 was still
an open pull request, and the identical command now exits 0 because T-24 landed
through real two-parent merge commits, not a squash.

The `128` row is a deliberate instrument probe against a path literally named
`definitely-not-here-xyz-574.md`, recorded as `EXPECTED-FAIL known-absent` and paired
with an `EXPECTED-PASS known-present` row two lines earlier. It asserts nothing about
T-24 and can never be made 0 without lying. It is **removed**, not coerced. Its only
legitimate function — proving the instrument discriminates — is replaced below by
executable positive and negative controls that anyone can re-run.

## 2. The check

`check_t24_landed.py` — exit 0 landed / 1 not landed / 2 instrument error.

1. **Ancestry first.** `git merge-base --is-ancestor <head> <target>` rc=0 → LANDED.
   Correct invocation for the preserved-commit case proved above.
2. **Content fingerprint otherwise.** `git patch-id --stable` over the unit's diff
   (against the first parent when the head is a merge), compared against every commit
   on the target that touches the unit's paths. A squash rewrites the sha and keeps
   the patch-id, so content that survived a squash still passes.
3. Unresolvable revisions are rc=2 aborts, never verdicts.

## 3. The self-check, run at this base

```
python3 -I QUALITY-CONTROL/pb-t24-landed/test_check_t24_landed.py
```

```
positive  rc=0 LANDED: dc3a1503 is an ancestor of origin/main (commits preserved)
reshape   rc=0 LANDED: dc3a1503 carries 99bdd8de's content fingerprint 534c0e8608b3 (sha not preserved)
negative  rc=1 NOT LANDED: no commit on origin/main carries ec5ea51a's content fingerprint 572ebd6b8ee6
negative control FAILED the check as required, with a verdict not a crash
abort     rc=2 INSTRUMENT ERROR: 0000000000000000000000000000000000000000 does not name a commit
RESULT: PASS
```

`TEST_RC=0`.

- **reshape** is the squash-shaped positive: `git commit-tree` of `dc3a1503`'s own tree
  with its own parent, so identical content under a different sha that is **not** an
  ancestor of main. It passes through the fingerprint branch, so the positive is not the
  ancestry shortcut in disguise.
- **negative** is a real dangling commit object (`hash-object`/`mktree`/`commit-tree`)
  whose content is nowhere on main. The assertion requires the output to start
  `NOT LANDED`, so a Python traceback — also rc=1 — cannot masquerade as the control
  passing.

## 4. The test bites

Dead-check defect injected: `return 1` → `return 0` in the NOT LANDED branch.

```
negative  rc=0 NOT LANDED: no commit on origin/main carries 3e23d348's content fingerprint 7990846bca2f
RESULT: FAIL: negative control did not fail with a verdict (rc=0)
BROKEN_TEST_RC=1
```

Restored, re-run: `TEST_RC=0`. Both exit codes recorded above.

## 5. What this does not claim

Acceptance of T-24's receipt is **not** claimed. Every check in this directory can
exit 0 and does, but the receipt's own blockers are ledger reconciliation — a positive
`attempt`, a `change_author`, and a `base` that agrees with the receipt — and that is
another lane's work. This lane touches no receipt, no ledger, no marker, no census,
no changelog and no CI workflow.

## 6. Provenance

Written and verified in lane `PBB-1707`, worktree
`.../Purple-Billboard-Client-System-Build/lanes/PBB-1707-lane/`.

Model that answered: `deepseek-chain`, observed in this session's own environment
record. Transcript path: **null** — not resolvable from inside this lane, so it is
recorded as unknown rather than filled with a label.
