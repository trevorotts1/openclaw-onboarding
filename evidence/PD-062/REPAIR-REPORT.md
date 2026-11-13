# PD-062 — REPAIR REPORT (ejected merge member, second repair)

**Unit:** PD-062 · **Lane:** FL04 · **Decision:** D-12 **HOLD** — repaired to mergeable, **not merged**
**Repo:** `trevorotts1/openclaw-onboarding` · **PR:** 3340
**Branch:** `pd/fl04-manifest--hold-d12`
**Repairer:** deepseek-chain · **Repaired:** 2026-11-13, US Eastern
**Method:** merge `origin/main` INTO the branch, then merge each colliding **in-batch sibling**
INTO the branch. No rebase. No force-push. Nothing pushed to `main`.

---

## 1. Why this is a second repair — the original ejection

The engine ejected PR 3340 as a conflicting merge member and named:

```
real conflict in: 23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md
```

**The first repair missed the actual partner.** It merged only `origin/main`
(`f0157e92c`), which came back clean, and concluded the conflict was not reproducible
against main. That conclusion was correct as far as it went and useless in practice: the
batch engine ejects a PR against its **in-batch siblings**, not only against `main`. The
first repair was ejected again after `f0157e92c` / `7ba1de533` / `638509cc5`.

This repair clears **both** surfaces: main, and every sibling the batch would carry.

---

## 2. Heads proved before touching anything

```
$ git ls-remote --heads origin pd/fl04-manifest--hold-d12
638509cc5486a992546e6d0a7fef3f6bfb7aac1b	refs/heads/pd/fl04-manifest--hold-d12   <- PRE

$ git rev-parse origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac      <- required value, matches

$ git ls-remote --heads origin pd/fl24-role-procedures-c
276762b420499f2fda50c0651667c3011d2bf588      <- the one sibling in this batch
```

---

## 3. Merge with `main`

```
$ git merge-base HEAD origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac      <- merge base IS origin/main

$ git merge origin/main
Already up to date.        rc=0, no commit created
```

**Main has not moved the conflicted file since the merge base** — proven by blob identity,
not by assertion:

```
base blob (1a476d2cb)    :pptx-assembly-specialist.md = 50fe3cb2ca6d51a7f6f875e70c019df55699b224
origin/main            :pptx-assembly-specialist.md = 50fe3cb2ca6d51a7f6f875e70c019df55699b224
$ git diff --numstat ebf5c769a origin/main -- <file>
(empty)
```

The branch blob is `a4fe1c5f605f43c494e8d48be871f8bbfceabaf0`, the unit's own edit
(`manifest_version 76, 56 phases`). So there is no main-side intent to keep or lose on
this file, and no invented resolution was needed.

---

## 4. Sibling collision — BEFORE

```
$ git merge-tree --write-tree HEAD origin/pd/fl24-role-procedures-c
rc=1
03d4e6a943aee1f25e535bba934d73da76419c8e
100644 50fe3cb2ca6d51a7f6f875e70c019df55699b224 1	<file>   (base)
100644 a4fe1c5f605f43c494e8d48be871f8bbfceabaf0 2	<file>   (PD-062 side)
100644 2ebf3512a9c4b52679746ef085fed4059ba88218 3	<file>   (sibling side)
Auto-merging <file>
CONFLICT (content): Merge conflict in <file>
```

`<file>` = `23-ai-workforce-blueprint/templates/role-library/presentations/pptx-assembly-specialist.md`.
Conflict surface was **one line**, in §9's Phase-Code Map.

- PD-062 side (stage 2): `(manifest_version 76, 56 phases)`
- Sibling side (stage 3, PD-093): `(manifest version: read it from the file; the live read at regeneration was manifest_version 75, 56 phases)`

The sibling branched at `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`, i.e. before PD-062's
bump to 76 — hence the stale `75`.

## 5. What I imported, and why

Merged `origin/pd/fl24-role-procedures-c` (`276762b42`) into the repair branch:

```
$ git merge origin/pd/fl24-role-procedures-c
CONFLICT (content): Merge conflict in <file>
commit 8907d276c0410d06b4950edbaab1e91ff1f9292b
parents: 638509cc5486… + 276762b42049…
20 files changed, 2273 insertions(+), 450 deletions(-)
```

Import was required, not optional: the pair was red, and a red pair is what the engine
ejects on. Nothing was imported from a sibling that was already clean.

**Resolution (both intents kept, neither side deleted):**

```markdown
> **Phase-Code Map (per FIX of the short-code reconciliation):** … in
> `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (manifest version: read it
> from the file; the live read at regeneration was manifest_version 76, 56 phases) exactly per
> the Director's Phase-Code Map …
```

- The sibling's **instruction** survives: "read the manifest version from the file" — that
  was PD-093's whole point (stop hard-coding a version that drifts).
- PD-062's **fact** survives: the merged `PIPELINE-MANIFEST.json` in this tree IS
  `manifest_version: 76`, 56 phases, verified by reading the file.

Resolved blob: `31904650f75bb8fcc3142220af3b3decad340ce9`. Zero conflict markers remain:

```
$ git grep -n '^<<<<<<< \|^>>>>>>> ' -- .     -> no output
```

## 6. Sibling collision — AFTER

```
$ git merge-tree --write-tree HEAD origin/pd/fl24-role-procedures-c
rc=0
fd512d470b9bd90b32c032ca036597c02828ed94     <- clean, no conflict report

$ git merge-tree --write-tree HEAD origin/main
rc=0
fd512d470b9bd90b32c032ca036597c02828ed94     <- clean
```

| Partner | BEFORE | AFTER |
|---|---|---|
| `origin/main` `ebf5c769a` | clean (already ancestor) rc=0 | clean rc=0 |
| `pd/fl24-role-procedures-c` `276762b42` (#3210) | **CONFLICT rc=1**, 1 file, 1 line | **clean rc=0** |

`merge-tree` touches no branch and creates no commit; both outputs above are the command's
own text.

---

## 7. Unit acceptance rows at the repaired head (`8907d276c`)

Rows are **A3** and **A4** per the unit's BUILD-REPORT §1, plus the manifest-wiring row.
Each run by test id, separately, real output:

| Row | Test id | Result |
|---|---|---|
| A3 — notes land in the delivered deck | `test_a3_notes_sync_writes_notes_into_the_delivered_deck` | PASSED (rc=0) |
| A3 control — no speech, panes stay empty | `test_a3_control_without_speech_the_panes_stay_empty` | PASSED (rc=0) |
| A4 — valid stub deck: exit 0, file not rewritten | `test_a4_valid_stub_deck_exits_zero_and_is_not_rewritten` | PASSED (rc=0) |
| A4 control — no deck, no renders: non-zero naming what is missing | `test_a4_control_no_deck_and_no_renders_exits_non_zero_naming_what_is_missing` | PASSED (rc=0) |
| A4 — invalid deck rebuilt from banked renders | `test_a4_invalid_deck_is_rebuilt_from_the_banked_renders` | PASSED (rc=0) |
| A4 — slide-count mismatch fails loudly | `test_a4_slide_count_mismatch_fails_loudly` | PASSED (rc=0) |
| Manifest wiring — both phases `kind: script`, every `*-FINAL.pptx` consumer retargeted | `test_manifest_wires_both_steps_to_scripts_and_moves_every_consumer` | PASSED (rc=0) |

Whole file in one run: `7 passed in 1.19s`. No row was skipped, renamed, weakened or xfailed.
Nothing failed, so there is no base-commit comparison to report.

Manifest lock re-checked at the repaired head (the merge touched a generator-owned doc):

```
$ python3 sync_check.py
manifest_version: 76 | phases: 56 | autofails: 196 | roles: 36
IN SYNC — …                                  rc=0

$ python3 scripts/ci/phase_doc_sync.py --check
PHASE_DOC_SYNC_PASS: every phase table and version marker matches manifest_version 76
(56 phases).                                 rc=0
```

That second line is the proof the resolved one-liner is consistent with the manifest, not
merely syntactically merged.

---

## 8. Ancestry — the push did not rewrite history

```
PRE   = 638509cc5486a992546e6d0a7fef3f6bfb7aac1b
$ git merge-base --is-ancestor 638509cc5486… 8907d276c041…
rc=0
```

`PRE` is an ancestor of the new head: fast-forward only, zero rewritten commits.

## 9. Remote-head proof

```
$ git ls-remote --heads origin pd/fl04-manifest--hold-d12
8907d276c0410d06b4950edbaab1e91ff1f9292b	refs/heads/pd/fl04-manifest--hold-d12

$ git rev-parse HEAD
8907d276c0410d06b4950edbaab1e91ff1f9292b
MATCH=yes (40 chars, literal)
```

Push line as the remote reported it: `638509cc5..8907d276c HEAD -> pd/fl04-manifest--hold-d12`
(fast-forward, no force).

This report is its own next commit on the same branch; the remote head is re-proved after
that commit in the commit message and must be read from the live ref, since a report cannot
contain the sha of the commit that contains it.

---

## 10. Prior attempt, recorded so it is not repeated

```
f0157e92c  Merge remote-tracking branch 'origin/main' into pd-062-repair   (clean, rc=0)
7ba1de533  PD-062: repair report for the ejected merge member
638509cc5  PD-062: record the remote-head proof in the repair report
```

That attempt correctly established main was not the partner (blob equality, §3) and then
**stopped there**, leaving the real collision — the PD-093 sibling line — unresolved. It is
superseded by `8907d276c`.

## 11. What I could not prove

1. **I cannot see the engine's exact ejection pair.** I proved the collision exists against
   `pd/fl24-role-procedures-c` because the card named it, and I proved it is gone. I cannot
   prove the engine used that same comparison, only that this is the only sibling on the
   card and the only same-line collision present.
2. **`presentations-drift-gates.sh` still does not exit 0 on this Mac** (rc=11,
   `DRIFT=1 FAILED=0`, GATE-D / FIX 113 — it compares the repo `scripts/` tree against the
   live department copy in `~/.openclaw/workspace/departments/Presentations/scripts`, where
   `pd_assemble_step.py` and its test are missing). That is box state, not branch state:
   both files are byte-identical before and after this repair, and the sanctioned fix is the
   department reinstall roll, which I did not run. It is not a claim about this branch.
3. **No wider suite was re-run.** The unit's BUILD-REPORT documents a 12-file
   manifest-shape set at 119 passed / 3 pre-existing failures. I re-ran the unit's own rows
   and the two lock checks, not that set.
4. **The sibling's own acceptance rows were not re-run here.** I proved the sibling merges
   clean and that its files arrived intact; I did not re-judge PD-093/PD-100/PD-101/PD-102/
   PD-108.
5. **D-12 remains unanswered.** Per the card this branch is repaired to mergeable and
   **left unmerged**. Nothing in this branch may enter a batch until Trevor says yes in
   `CORRECTIONS.md`.
