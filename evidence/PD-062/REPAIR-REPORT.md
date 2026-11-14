# PD-062 — REPAIR REPORT (ejected merge member)

**Unit:** PD-062 · **Lane:** FL04 · **Decision:** D-12 **HOLD** — repaired to mergeable, **not merged**
**Repo:** `trevorotts1/openclaw-onboarding` · **PR:** 3340
**Branch:** `pd/fl04-manifest--hold-d12`
**Repairer:** deepseek-chain · **Repaired:** 2026-11-13, 10:18 AM Eastern
**Method:** merge `origin/main` INTO the branch (no rebase, no force-push), resolve only the
named conflict.

---

## 1. The conflict as the engine gave it

Verbatim from the run ledger:

```
real conflict in: 23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md
```

## 2. What I merged

| Item | Value |
|---|---|
| Branch head before repair | `11ce373dffdea8b0ccd31df5317512047c9e9417` (== remote head before repair) |
| `origin/main` merged in | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` ("Merge pull request #3244 …batch…20261113-013042") |
| Merge base | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| Merge commit | `f0157e92cfab163eea76ca2c7a2b8a3dded24cde` — parents `11ce373df` + `ebf5c769a` |
| Merge outcome | **clean, exit 0** — 66 files changed, +/-6769/65, **zero conflicted paths** |
| Branch was behind | 14 commits behind `origin/main`, 3 ahead |

Merge performed in a private worktree of the base clone:
`/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-062/work.KD8seA/wt`
(created with `git worktree add -b pd-062-repair … 11ce373df`).

## 3. Resolution per hunk

**There were no conflicted hunks.** `git merge origin/main` returned rc=0 and wrote no conflict
markers (`git grep -nE '^(<<<<<<<|>>>>>>>|=======$)' -- 23-ai-workforce-blueprint universal-sops`
returned nothing).

The named file is not a real two-sided conflict against current `origin/main`:

```
base blob  1a476d2cb:pptx-assembly-specialist.md = 50fe3cb2ca6d51a7f6f875e70c019df55699b224
main blob  origin/main:pptx-assembly-specialist.md = 50fe3cb2ca6d51a7f6f875e70c019df55699b224   <- identical
unit blob  11ce373df:pptx-assembly-specialist.md   = a4fe1c5f605f43c494e8d48be871f8bbfceabaf0
```

`git diff --numstat 1a476d2c..origin/main -- <file>` is empty, and `git log 1a476d2c..origin/main --
<file>` lists no commit. Main never touched this file, so nothing of main's could be lost and the
unit's single-line change stands as written:

```
(manifest_version 76, 56 phases)     <- unit's edit (was 75)
```

### Why the engine still saw it — and the real collision partner

`git log --all` shows two commits on a **sibling, unmerged lane branch** that rewrite the *same*
line of the *same* file:

```
e9fb04930 PD-093: header states the manifest version is read from the file
66bf69c97 PD-093: assembly procedure follows the engine it actually dispatches
```

PD-093 replaces `manifest_version 76` with `(manifest version: read it from the file; the live
read at regeneration was manifest_version 75, 56 phases)`. PD-062 and PD-093 are therefore a true
one-line collision, but the collision is with **PD-093's unmerged work**, not with `origin/main`.

I did **not** import PD-093's wording. Two reasons: (a) the card's method is to merge
`origin/main` and resolve only what that merge conflicts on; PD-093 is not in `main`, and copying
another unit's unmerged hunk into this branch would delete PD-093's own commit's purpose and
misattribute authorship; (b) the unit's intent ("the header states the version this manifest
actually is") is *correct and verified* at the merged tree — see §4. Both intents are legitimate
and both survive: whoever lands second re-runs `phase_doc_sync.py --write`, and the generator will
restamp every version marker from the manifest as it then stands. **Merge order note for the
merge-writer:** if PD-093 lands before PD-062, re-run
`scripts/ci/phase_doc_sync.py --write` + `scripts/hash-universal-sops-manifest.py` after the
merge rather than hand-resolving that line.

## 4. Row-by-row re-proof at the merged tree (`f0157e92c`)

Working dir: `23-ai-workforce-blueprint/templates/role-library/presentations`, Python 3.14.7.

**Acceptance rows are A3 and A4** (per the unit's BUILD-REPORT §1). `/bin/pytest -v` on the
unit's own suite, at the merged tree:

```
scripts/tests/test_pd_manifest_assembly_notes.py::test_a3_notes_sync_writes_notes_into_the_delivered_deck PASSED
scripts/tests/test_pd_manifest_assembly_notes.py::test_a3_control_without_speech_the_panes_stay_empty PASSED
scripts/tests/test_pd_manifest_assembly_notes.py::test_a4_valid_stub_deck_exits_zero_and_is_not_rewritten PASSED
scripts/tests/test_pd_manifest_assembly_notes.py::test_a4_control_no_deck_and_no_renders_exits_non_zero_naming_what_is_missing PASSED
scripts/tests/test_pd_manifest_assembly_notes.py::test_a4_invalid_deck_is_rebuilt_from_the_banked_renders PASSED
scripts/tests/test_pd_manifest_assembly_notes.py::test_a4_slide_count_mismatch_fails_loudly PASSED
scripts/tests/test_pd_manifest_assembly_notes.py::test_manifest_wires_both_steps_to_scripts_and_moves_every_consumer PASSED
============================== 7 passed in 2.84s ===============================
```

| Row | Test id(s) | Merged-tree result |
|---|---|---|
| **A3** notes land in the delivered deck | `test_a3_notes_sync_writes_notes_into_the_delivered_deck` | PASSED |
| **A3 control** no speech → panes stay empty | `test_a3_control_without_speech_the_panes_stay_empty` | PASSED |
| **A4** valid stub deck → exit 0, file not rewritten | `test_a4_valid_stub_deck_exits_zero_and_is_not_rewritten` | PASSED |
| **A4 control** no deck, no renders → non-zero naming what is missing | `test_a4_control_no_deck_and_no_renders_exits_non_zero_naming_what_is_missing` | PASSED |
| **A4** invalid deck rebuilt from renders | `test_a4_invalid_deck_is_rebuilt_from_the_banked_renders` | PASSED |
| **A4** slide-count mismatch fails loudly | `test_a4_slide_count_mismatch_fails_loudly` | PASSED |
| Manifest wiring (both phases `kind: script`, every `*-FINAL.pptx` consumer retargeted) | `test_manifest_wires_both_steps_to_scripts_and_moves_every_consumer` | PASSED |

Manifest lock at the merged tree:

```
sync_check.py            -> manifest_version: 76 | phases: 56 | IN SYNC | rc=0
phase_doc_sync.py --check-> PHASE_DOC_SYNC_PASS: every phase table and version marker matches
                            manifest_version 76 (56 phases). | rc=0
```

So the unit's `manifest_version 76` marker in the conflicted file agrees with the merged manifest,
and the merge did not disturb the lock.

**Merge did not alter a single unit blob** (pre-merge `11ce373df` vs merged `HEAD`):

```
SAME pd_assemble_step.py                         6038b9165adac2c9722bcbfec9810c5cc065df7c
SAME tests/test_pd_manifest_assembly_notes.py    21f4789b27820c195d2e256bd6809e09505630e2
SAME PIPELINE-MANIFEST.json                      68d840635f891a910f2512822e0437cbcec57d29
SAME MANIFEST-SOURCE.txt                         57a3e469313cc8a385fb5dd56a9ce4a6fcbe87d5
SAME universal-sops/_content-manifest.json       643b594b686baf7c6453516ce5ab157b40df1718
```

## 5. Commits

```
f0157e92cfab163eea76ca2c7a2b8a3dded24cde  Merge remote-tracking branch 'origin/main' into pd-062-repair
11ce373dffdea8b0ccd31df5317512047c9e9417  PD-062: correct the A3 AFTER transcript to the stub speech used
27356f83c…                                PD-062: build report with commit sha, files and captured check output
195202d55…                                PD-062: give the assembly and notes steps an executor
```

Pushed to `refs/heads/pd/fl04-manifest--hold-d12` (fast-forward from `11ce373df`, no force).

## 6. Remote-head proof

```
$ git ls-remote --heads origin refs/heads/pd/fl04-manifest--hold-d12
7ba1de5335c104269048788ecf6127ca390cdd3d	refs/heads/pd/fl04-manifest--hold-d12

$ git rev-parse HEAD
7ba1de5335c104269048788ecf6127ca390cdd3d
MATCH=yes
```

Pre-repair remote head was `11ce373dffdea8b0ccd31df5317512047c9e9417`; the push was a
fast-forward (`11ce373df..7ba1de533`), no force. This report is then its own next commit on the
same branch; at that push `git rev-parse HEAD` and `git ls-remote --heads origin
refs/heads/pd/fl04-manifest--hold-d12` were compared again and matched, full 40 characters.

## 7. What I could not prove — stated plainly

1. **`presentations-drift-gates.sh` does not exit 0 on this Mac.** It returns rc=11 with
   `DRIFT=1 FAILED=0`. The only failing gate is **GATE-D (FIX 113)**, which compares the repo
   `scripts/` tree against the *live department copy on this box*
   (`/Users/blackceomacmini/.openclaw/workspace/departments/Presentations/scripts`):

   ```
   SCRIPTS-TREE DRIFT: 2 file(s) differ between the repo copy and the department copy (FIX 113):
     - pd_assemble_step.py — MISSING from the department copy (repo sha256=35d7afa8446cb13c…)
     - tests/test_pd_manifest_assembly_notes.py — MISSING from the department copy (repo sha256=1ab85c0661a5baa9…)
   ```

   This is box state, not branch state: both files are byte-identical before and after the merge
   (blob proof in §4), `origin/main` touched no path under `presentations/`, and the sanctioned
   repair is the reinstall/update roll (`refresh-dept-scripts.py`), which I did not run — it
   mutates the department install and is outside this unit. The unit's BUILD-REPORT §5 claims
   "ALL GATES PASSED (GATE 1..9) exit 0"; that claim does **not** reproduce from a fresh worktree
   on this box at either the pre-merge head or the merged head. I am not asserting which
   environment produced the original green; I am saying it is not reproducible here.
2. **The engine's reported conflict is not reproducible against current `origin/main`.** I can
   prove the honest negative only against `origin/main` (blob equality, §3). I cannot see the
   engine's exact base tree, so I cannot prove *which* commit pair it merged. The PD-093 commits
   are the only same-line collision I found in `--all` history; that is the best-supported
   explanation, not a certainty.
3. **The wider suites were not re-run.** The BUILD-REPORT documents a 12-file manifest-shape set
   at 119 passed / 3 pre-existing failures; `origin/main` touches none of those files (empty
   `git diff --stat 1a476d2c..origin/main` over the presentations tree), so those rows cannot have
   changed, but I am quoting the unit's numbers rather than re-running them.
4. **D-12 remains unanswered.** Per the card this branch is repaired to mergeable and **left
   unmerged**.
