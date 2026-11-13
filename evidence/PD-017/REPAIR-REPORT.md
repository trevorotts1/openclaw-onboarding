# PD-017 — REPAIR REPORT (red required check)

Unit: **PD-017** · PR **#3317** · branch `pd/fl08-buddy-procedure--hold-d2`
Repo: `trevorotts1/openclaw-onboarding`
Failing required check repaired: **`QC static invariants`** (plus the two other reds on the
same PR, which share PD-017's own two root causes — see §6).

All scratch work lived under the loop-control scratch root; this report contains no
host-specific absolute paths (repo guard D-27 bans them in added lines).

---

## 1. The failing check, quoted

`gh pr checks 3317` showed four reds. The named one:

```
QC static invariants   fail   1m12s   run 43430636369 / job 131902940166
```

`gh run view 43430636369 --log-failed` → tail of the `QC static invariants` job:

```
=== T1: CLEAN REPO PASSES ===
  FAIL: clean repo should exit 0, got rc=6
=== T2: MISSING ROSTER FAILS ===
  PASS: deleted marketing roster -> exit 5
...
=== T8: LATER-DEFERRAL LITERAL FAILS (Issue #7 regression) ===
  PASS: 'ask me again in 90 days' deferral literal -> exit 7

--------------------------------------------
RESULT: 7 passed, 1 failed
REPO-CONSISTENCY FIXTURE TEST FAILURES
##[error]Process completed with exit code 1.
```

The step's own command, from the log (`.github/workflows/qc-static.yml`):

```
bash 23-ai-workforce-blueprint/scripts/test-repo-consistency.sh
```

T1 runs `qc-assert-repo-consistency.py --skill-dir 23-ai-workforce-blueprint` with **no
`--only` filter**, so both sub-gates run. Consistency passed; the artifact sub-gate
returned rc 6.

## 2. Local reproduction (same command, same tree)

```
cd <clone-at-PRE>
python3 -I 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py \
        --skill-dir 23-ai-workforce-blueprint
rc=6
...
CONTENT-HASH        DRIFT   content-manifest drift (2): role presentations/brainstorming-buddy-presentations: S...
                            sop presentations/brainstorming-buddy-presentations-sops: STALE content_sha — re-run hash-content-manifest.py
dimensions: 9 OK, 1 DRIFT   |   failures: 1
RESULT: FAIL — 1 artifact dimension(s) with drift, 1 problem(s) (rc=6)
```

Exact gate detail:

```
[CONTENT-HASH] content-manifest drift (2): role presentations/brainstorming-buddy-presentations:
STALE content_sha (stored sha256:7ea00a26a4b…, file sha256:9462eb580f4…) — re-run
hash-content-manifest.py; sop presentations/brainstorming-buddy-presentations-sops: STALE content_sha
— re-run hash-content-manifest.py
```

## 3. Cause

PD-017 edited two library artifacts:

```
23-ai-workforce-blueprint/templates/role-library/presentations/brainstorming-buddy-presentations.md
23-ai-workforce-blueprint/templates/role-library/presentations/sops/brainstorming-buddy-presentations-sops.md
```

…but never regenerated `templates/role-library/_index.json`'s content manifest. The gate
requires `content_sha` to equal the live file's canonical hash, so the two edited artifacts
read as stale and the artifact dimension reported `CONTENT-HASH DRIFT`.

Nothing was wrong with the two SOP files themselves, and no check was weakened — the check
correctly caught a missing restamp.

## 4. Fix

Regenerated the manifest with the project's own canonical tool (not hand-edited):

```
python3 -I 23-ai-workforce-blueprint/scripts/hash-content-manifest.py
  roles hashed: 538 · dept content_shas: 68 · dept-level sops: 148 · personas hashed: 19
  content_versions bumped (sha changed): 2
```

The tool stamps every entry with a fresh `content_hashed_at` (779 changed lines for a
2-artifact change), so the timestamps on entries whose `content_sha` did **not** change were
restored to their prior values. `--check` and the gate verify `content_sha` only, so the
result is behaviourally identical and the diff stays reviewable. Final manifest diff — 4
logical changes, 9 lines:

| entry | field | before → after |
|---|---|---|
| role `presentations/brainstorming-buddy-presentations` | `content_sha` | `sha256:7ea00a26a4b…` → `sha256:9462eb580f4…` |
| role `presentations/brainstorming-buddy-presentations` | `content_version` | `1.0.13` → `1.0.14` |
| sop `brainstorming-buddy-presentations-sops` | `content_sha` | `sha256:80d5cfeb1cba…` → `sha256:ceec0b8dc207…` |
| sop `brainstorming-buddy-presentations-sops` | `content_version` | `1.0.4` → `1.0.5` |
| dept `presentations` | `content_sha` | rollup refreshed (member role sha changed) |
| header `content_manifest.generated_at` | timestamp | restamped |

## 5. Green re-run (same commands the workflow runs)

```
$ python3 -I 23-ai-workforce-blueprint/scripts/hash-content-manifest.py --check
✓ content-manifest CHECK PASS — 538 roles + 148 sops + 19 personas all carry
content_sha/content_version; every stored sha matches the live file; no token leaks.
rc=0

$ python3 -I 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py --skill-dir 23-ai-workforce-blueprint
CONTENT-HASH        OK      content-manifest present + current: 538 roles + 148 sops + 19 personas …
dimensions: 10 OK, 0 DRIFT   |   failures: 0
RESULT: PASS — every downstream artifact covers all 29 floor departments; skills + versions + bootstrap consistent (rc=0)
rc=0

$ bash 23-ai-workforce-blueprint/scripts/test-repo-consistency.sh
=== T1: CLEAN REPO PASSES ===
  PASS: clean repo exits 0 (rc=0)
…
RESULT: 8 passed, 0 failed
ALL REPO-CONSISTENCY FIXTURE TESTS PASSED
rc=0
```

T1 now passes and T2–T8 still bite (exit 5 / 5 / 5 / 5 / 7 / 7 / 7) — the gate was not
softened, only the drift it named was cleared.

## 6. The other two reds on this PR (same unit, same two causes)

**a. `fast-guards (all folded guards)` — same root cause, fixed by §4.**
Failure was the folded `library-lockstep` guard:

```
✗ content-manifest CHECK FAIL — 2 problem(s):
library-lockstep: FAIL (15s)  ::error::library-lockstep failed (was workflow library-lockstep.yml)
7 passed, 1 failed, 94 skipped
```

`scripts/ci/fast-guards.d/library-lockstep.sh` runs
`register-library-additions.py --check`, `test-library-register.sh`, and
`hash-content-manifest.py --check`. Only the third step failed, on the same two stale
entries. Post-fix local run:

```
$ GITHUB_WORKSPACE=<repo> bash scripts/ci/fast-guards.d/library-lockstep.sh
✓ content-manifest CHECK PASS — 538 roles + 148 sops + 19 personas …
rc=0
```

**b. `Enforce binding laws on the pull request range` — branch was behind main.**
Quoted from run 43430636434:

```
"law": …  "check": "ancestry_from_base",  "kind": "tree",  "status": "FAIL",
"detail": ["merge-base --is-ancestor ebf5c769a2ad5b2582bf2256588095cbef20cfac
           e0813cf5485fb300eb43b5e0bf62044384b194d7 returned 1;
           the branch is not on top of the base ref"]
```

Fixed the way the repair procedure allows — merged `origin/main` in (no rebase, no force):

```
$ git merge-tree --write-tree HEAD origin/main
1613ecf2c97dabe7a8024b0438397355c7175bcf      (rc=0, clean — no conflicts)
$ git merge --no-ff --no-edit origin/main
merge rc=0   (14 commits from main, no conflicts)
```

**c. `Judge this PR's added lines` — PD-017's own BUILD-REPORT added host paths.**
Quoted from run 43430636106:

```
base=origin/main head=e0813cf5485fb300eb43b5e0bf62044384b194d7 added_lines=460 users_hits=0 volumes_hits=5
  VOLUMES diff <redacted>/role-section9.md \
  VOLUMES Temp files: `<redacted>` (via `mktemp -p "$TMPDIR"`).
  VOLUMES Scratch: `<redacted>`. No host temp-root path used.
  VOLUMES `<redacted>`
  VOLUMES `<redacted>`
GATE FAIL: banned absolute paths (VOL_ROOT, USER_ROOT) present in added lines
```

All five hits were in `evidence/PD-017/BUILD-REPORT.md`, which the builder wrote with host
absolute paths. Fixed by replacing each host path with the placeholder
`<host-scratch-root>` (5 lines; no prose or evidence removed, no check touched). The
guard's own rule (`tools/gate-added-paths.sh`, owner decision D-27) bans the literal roots in
ADDED lines only.

## 7. Sibling test

No sibling branches were named in the repair ticket, so none were merged. The only
integration point tested is the merge base every batch item shares:

| ref | `git merge-tree --write-tree` | result |
|---|---|---|
| `origin/main` | `1613ecf2c97dabe7a8024b0438397355c7175bcf` | **clean**, rc 0 |

Per-sibling result: **not applicable — no siblings named.**

## 8. Ancestry and remote-head proofs

```
PRE  (before this repair)
  $ git ls-remote --heads origin pd/fl08-buddy-procedure--hold-d2
  e0813cf5485fb300eb43b5e0bf62044384b194d7

origin/main
  $ git ls-remote --heads origin main
  ebf5c769a2ad5b2582bf2256588095cbef20cfac
```

Post-push proofs are recorded in §9 (new head, remote head equality, and
`git merge-base --is-ancestor <PRE> <new-head>` exit 0). Push was fast-forward only — no
rebase, no force-push, nothing pushed to `main`.

## 9. Post-push proof

```
$ git push origin HEAD:refs/heads/pd/fl08-buddy-procedure--hold-d2
   e0813cf5485f..<new-head>  HEAD -> pd/fl08-buddy-procedure--hold-d2      (fast-forward)

$ git rev-parse HEAD
<new-head>

$ git ls-remote --heads origin pd/fl08-buddy-procedure--hold-d2
<new-head>   refs/heads/pd/fl08-buddy-procedure--hold-d2                  (identical)

$ git merge-base --is-ancestor e0813cf5485fb300eb43b5e0bf62044384b194d7 <new-head>
rc=0
```

## 10. What I could not prove

- **CI-side green is not proven from here.** Every result above is a local run of the exact
  commands the workflows execute, on the exact tree being pushed. Only the GitHub run on the
  new head can confirm the required checks turn green. That run had not completed when this
  report was written.
- **`fast-guards` totality.** I proved `library-lockstep` (the guard that actually failed on
  the failing run) green locally. The other 101 folded guards that `fast-guards` SKIPs for a
  non-matching diff were not re-run individually; the folding harness decides that set.
- **macOS vs ubuntu.** Local runs are on macOS (darwin, bash 3.2 class). CI runs
  `ubuntu-latest` / `/usr/bin/bash`. The gate, the manifest tool and the fixture script are
  Python/bash with no platform-conditional branches on the paths touching this fix, but the
  platform difference is unproven by construction.
- **No sibling branches were supplied**, so no per-sibling merge result exists beyond `main`.
