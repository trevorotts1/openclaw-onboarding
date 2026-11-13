# PD-109 — REPAIR REPORT (red required check: "QC static invariants")

- Unit: **PD-109**
- Pull request: **#3192** — "PD-109: the doctrine files agree on status and names"
- Branch: **pd/fl25-doctrine**
- Repo: `trevorotts1/openclaw-onboarding`
- PRE (branch head when the repair started): `f1b2b41dbb8dcaeb5bf5a089c01de8c853d75255`
- Fix commit: `2c81a6ee5354aefa468d3899c40a93cb3305ec45` (the code change)
- Evidence commits carrying this report follow it; the branch tip is proven live with
  `git ls-remote --heads origin pd/fl25-doctrine` (see §6). A literal tip written here
  would be stale the moment this file lands.
- origin/main at repair time: `ebf5c769a2ad5b2582bf2256588095cbef20cfac`

## 1. The failing check, quoted

Job: `QC static invariants` — run `43311375162`, job `131508030574`
(<https://github.com/trevorotts1/openclaw-onboarding/actions/runs/43311375162/job/131508030574>)

The workflow step that failed (`.github/workflows/qc-static.yml`, "Skill 23 repo-consistency
gate (floor x roster x library x SOP x persona)", lines 1200-1228) runs:

```
python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py --only consistency
bash 23-ai-workforce-blueprint/scripts/test-repo-consistency.sh
```

The first command PASSED. The fixture test failed at T1:

```
=== T1: CLEAN REPO PASSES ===
  FAIL: clean repo should exit 0, got rc=6
...
RESULT: 7 passed, 1 failed
REPO-CONSISTENCY FIXTURE TEST FAILURES
##[error]Process completed with exit code 1.
```

T1 is the only fixture that runs the gate with **no** `--only` flag
(`test-repo-consistency.sh:94`, `run_gate "$SKILL_DIR"`), so it also runs the ARTIFACT
sub-gate — which the CI step's `--only consistency` skips. rc=6 is the artifact-drift code
(`qc-assert-repo-consistency.py:1701`).

## 2. Reproduction — exact cause

Bare invocation on the branch:

```
$ python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py
CONTENT-HASH        DRIFT   content-manifest drift (4): ...
RESULT: FAIL — 1 artifact dimension(s) with drift, 1 problem(s) (rc=6)
```

Full drift detail:

```
[CONTENT-HASH] content-manifest drift (4):
  sop presentations/SOP-INTEGRATION-00-LOADABLE-BLOCK-AND-VERIFICATION-GATE: STALE content_sha — re-run hash-content-manifest.py
  sop presentations/SOP-NORTHSTAR-00-ATTENTION-IS-THE-PRODUCT: STALE content_sha — re-run hash-content-manifest.py
  sop presentations/SOP-PRIORITY-01-SEVEN-P-MODEL-AND-DIAGNOSTIC: STALE content_sha — re-run hash-content-manifest.py
  sop presentations/SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE: STALE content_sha — re-run hash-content-manifest.py
```

Cause: the branch's doctrine edit changed exactly those four SOP files
(`git diff --stat origin/main...HEAD` = 4 files, 11 insertions / 11 deletions) but did not
re-stamp `23-ai-workforce-blueprint/templates/role-library/_index.json`. `CONTENT-HASH`
recomputes each artifact's `content_sha` from the live canonical file and compares it to the
stored one (`qc-assert-repo-consistency.py:1243-1281`, `hash-content-manifest.check_manifest`).
The branch was **not** behind main in any way that caused this.

Control (same instrument, same shell, answer known non-empty):

| Tree | bare gate | CONTENT-HASH |
|---|---|---|
| `origin/main` (`ebf5c769`) | **rc=0** | OK |
| `pd/fl25-doctrine` PRE | **rc=6** | DRIFT (4) |

`mergeStateStatus` was BEHIND, but `git merge-tree --write-tree HEAD origin/main` was clean
and main passes, so being behind was **not** the cause.

## 3. The fix

Re-stamped only the four stale entries, with the values
`hash-content-manifest.py` computes, in `_index.json`
(`content_sha`, `content_version`, `content_hashed_at` per entry):

- `presentations/SOP-INTEGRATION-00-LOADABLE-BLOCK-AND-VERIFICATION-GATE`
  `sha256:ca1982c8…` → `sha256:bc2546c2…`, v1.0.1 → v1.0.2
- `presentations/SOP-NORTHSTAR-00-ATTENTION-IS-THE-PRODUCT`
  `sha256:e3789f0a…` → `sha256:3cc9103d…`, v1.0.2 → v1.0.3
- `presentations/SOP-PRIORITY-01-SEVEN-P-MODEL-AND-DIAGNOSTIC`
  `sha256:a2f3c1a2…` → `sha256:0f583bdb…`, v1.0.2 → v1.0.3
- `presentations/SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE`
  `sha256:1dea8364…` → `sha256:aefe733b…`, v1.0.1 → v1.0.2

Diff: `+12 / -12` — four entries, nothing else. The gate, the test, and the workflow were
not touched. No `--no-verify`, no skipped check, no weakened assertion.

Note on method: running `hash-content-manifest.py` wholesale rewrote `render_sha` on 538
entries and `content_hashed_at` on 773 entries (machine-dependent churn, 1320 lines) for a
check that only compares `content_sha`. Only the four recomputed entries were applied, so
the invariant is satisfied with the minimal diff. The hasher's own `--check` mode is green
either way.

## 4. Green re-run (same commands the workflow runs)

```
$ python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py --check
✓ content-manifest CHECK PASS — 538 roles + 148 sops + 19 personas all carry
  content_sha/content_version; every stored sha matches the live file; no token leaks.
rc=0

$ python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py
RESULT: PASS — all 29 floor departments are consistent… (rc=0)
CONTENT-HASH        OK      content-manifest present + current: 538 roles + 148 sops + 19 personas…
RESULT: PASS — every downstream artifact covers all 29 floor departments… (rc=0)
rc=0

$ python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py --only consistency \
  && bash 23-ai-workforce-blueprint/scripts/test-repo-consistency.sh
  PASS: clean repo exits 0 (rc=0)          <- was: FAIL, got rc=6
  PASS T2..T8 (missing roster / unresolvable role / persona map / corrupt slug /
       stale floor literal / listings-universal / later-deferral)
RESULT: 8 passed, 0 failed
ALL REPO-CONSISTENCY FIXTURE TESTS PASSED
rc=0
```

## 5. Sibling results

No siblings were named in the task. Full-batch safety checked against the base branch:

| Comparison | Result |
|---|---|
| `git merge-tree --write-tree HEAD origin/main` | **clean** (rc=0) |

## 6. Ancestry and remote-head proofs

```
$ git push origin HEAD:pd/fl25-doctrine
   f1b2b41db..2c81a6ee5  HEAD -> pd/fl25-doctrine      (fast-forward, no force)
   2c81a6ee5..c8eacebb4  HEAD -> pd/fl25-doctrine      (fast-forward, report)
   ...                   HEAD -> pd/fl25-doctrine      (fast-forward, report correction)

$ git merge-base --is-ancestor f1b2b41dbb8dcaeb5bf5a089c01de8c853d75255 HEAD
rc=0
```

At the time of the last proof, local `git rev-parse HEAD` and
`git ls-remote --heads origin pd/fl25-doctrine` returned the same 40-character value, and
PRE `f1b2b41d…` was an ancestor of it. Re-run `git ls-remote --heads origin pd/fl25-doctrine`
for the current tip: every evidence commit is a plain fast-forward on top of the PRE line.

Local head == remote head, and PRE is an ancestor of the new head.

## 7. Same root cause in a second red check

`fast-guards (all folded guards)` (run `43311375422`) also fails on the identical four
entries — its `library-lockstep` guard runs the same content-manifest check:

```
✗ content-manifest CHECK FAIL — 4 problem(s):
    - sop presentations/SOP-INTEGRATION-00-LOADABLE-BLOCK-AND-VERIFICATION-GATE: STALE content_sha …
    - sop presentations/SOP-NORTHSTAR-00-ATTENTION-IS-THE-PRODUCT: STALE content_sha …
    - sop presentations/SOP-PRIORITY-01-SEVEN-P-MODEL-AND-DIAGNOSTIC: STALE content_sha …
    - sop presentations/SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE: STALE content_sha …
```

Its other failure axis, `FATAL: POSTFLIGHT COMPLETENESS GATE FAILED (AF-BUNDLE-COMPLETE)`,
is a separate guard and is **not** addressed here.

## 8. What could not be proven

- CI green on the new head: the verdict belongs to the run GitHub starts on
  `2c81a6ee…`; only the identical local commands were proven green here.
- `fast-guards` as a whole: the content-manifest half should clear, but the
  `AF-BUNDLE-COMPLETE` postflight failure in that job was not investigated — it is a
  different guard with a different cause.
- The other red checks on PR #3192 (`Enforce binding laws on the pull request range`,
  `Judge this PR's added lines`, `Check this PR's diff against scripts/binding-pairs.json`)
  were not diagnosed.
- Whether the branch needs `origin/main` merged in: not required for this check
  (`merge-tree` clean), so nothing was merged.
