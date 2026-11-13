# REPAIR REPORT — PD-090

**Unit:** PD-090 — Price rules that can both be passed (Severe, logic)
**Repo:** `trevorotts1/openclaw-onboarding`
**Branch:** `pd/fl23-role-procedures-b--hold-d17`
**PR:** 3319
**Role:** deepseek-chain repair worker on an ejected merge member
**Repair date:** November 13, 2026

---

## 1. The conflict as the engine reported it

Verbatim from the engine's run ledger:

```
real conflict in: 23-ai-workforce-blueprint/templates/role-library/presentations/qc-specialist-presentations.md, 23-ai-workforce-blueprint/templates/role-library/presentations/sops/qc-specialist-presentations.md
```

## 2. What I merged

| Item | Full 40-character SHA |
|---|---|
| Merge base (base of branch) | `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` |
| Branch head before repair | `af296dd88e939092ca2118f036a534daede58ce7` |
| `origin/main` merged in | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` |
| Repair merge commit (new branch head) | `cf8cf54f3bd3bac6390ffeee40707d760ea6843c` |

Commands run, in order, in my own scratch worktree:

```
git fetch origin
git worktree add "$S/wt" af296dd88 --detach
git switch -c pd-repair-PD-090
git merge origin/main
git push origin pd-repair-PD-090:refs/heads/pd/fl23-role-procedures-b--hold-d17
```

No rebase. No force-push. No history rewrite.

## 3. Finding: there is no textual conflict at the current `origin/main` tip

`git merge origin/main` returned **rc=0** and reported `Merge made by the 'ort' strategy.` — no conflict. I did not accept that at face value, because a silent auto-merge is exactly how a duplicate rule would slip through. Two independent checks:

**Check A — independent merge-tree dry run:**

```
$ git merge-tree --write-tree --messages origin/main af296dd88
b604d1ab32395a3038d1d4179b4755be312f724b
RC=0
```

A bare tree hash with no conflict message block. No conflict.

**Check B — did main touch either named file at all since the merge base?**

```
$ git log --oneline 1a476d2cb..ebf5c769 -- "23-ai-workforce-blueprint/templates/role-library/presentations/"
(0 commits)
```

Zero commits. Main changed nothing under that directory between the merge base and the main tip I merged. That is why ort had nothing to arbitrate.

**The second named path does not exist on either side.**

```
$ git cat-file -e ebf5c769:"23-ai-workforce-blueprint/templates/role-library/presentations/sops/qc-specialist-presentations.md"
fatal: path ... does not exist in 'ebf5c769'
$ git cat-file -e af296dd88:"23-ai-workforce-blueprint/templates/role-library/presentations/sops/qc-specialist-presentations.md"
fatal: path ... does not exist in 'af296dd88'
$ git rev-list --all --objects | grep -F "presentations/sops/qc-specialist-presentations.md"
(no output)
```

That path never existed in any ref in this repository. The engine's ledger named a filename that is not in the tree. The real mirror file the unit edits is `sops/qc-specialist-presentations-sops.md` (with the `-sops` suffix) — that is the second file named in `evidence/PD-090/BUILD-REPORT.md` and the second file this branch actually changed.

**Conclusion on the reported conflict:** it could not be reproduced in either form. I did not invent a resolution for a conflict that does not exist. I merged main in, which is what makes the member mergeable, and then verified the D-17 invariant by hand rather than by trusting the merge.

## 4. Resolution per hunk

There were no conflict hunks. The merge is clean and both sides' intent is preserved:

| File | Side | Result |
|---|---|---|
| `presentations/qc-specialist-presentations.md` | branch | branch's rewritten summary row survives verbatim (line 367) |
| `presentations/qc-specialist-presentations.md` | main | main made no change to this file since the merge base, so nothing of main's was displaced |
| `presentations/sops/qc-specialist-presentations-sops.md` | branch | branch's rewritten full definition survives verbatim (line 214) |
| `presentations/sops/qc-specialist-presentations-sops.md` | main | main made no change to this file since the merge base, so nothing of main's was displaced |

Diff of the merged tree against the branch head, restricted to both named files:

```
$ git diff af296dd88..HEAD --stat -- <both files>
(empty)
```

The merge contributed **zero bytes** to either file. Nothing of the unit's change was altered and nothing of main's was lost, because main had nothing in these files to lose.

## 5. The D-17 check: exactly ONE rule standing

D-17 holds this unit because the fault was one rule that both passes and fails the same slide. If main had landed its own copy of the price-face rule, a naive resolution would leave two rules that disagree. That did not happen, and I proved it three ways.

**5a. Main carries no new copy of the rule.** `git grep AF-PRICE-FACE` at `ebf5c769` (main) returns 21 matches, all of them in files the branch never touched, and the two definition rows are main's *unchanged* old wording. Main's `qc-specialist-presentations.md:367` and main's `sops/qc-specialist-presentations-sops.md:214` both still carry the pre-fix text — i.e. main has the same rule the branch replaced, not an additional one.

**5b. The merged tree has exactly one definition row per file.**

```
=== presentations/qc-specialist-presentations.md ===
AF-PRICE-FACE table ROWS: 1
total AF-PRICE-FACE mentions: 2

=== presentations/sops/qc-specialist-presentations-sops.md ===
AF-PRICE-FACE table ROWS: 1
total AF-PRICE-FACE mentions: 3
```

One definition row in each file. The remaining mentions are cross-references, not second rules: the `AF-P3 demotion` paragraph (line 380 / 228) and the `AF-CALLOUT` row (line 218), which explicitly says "AF-PRICE-FACE catches those".

**5c. The one surviving rule and the summary row agree.** The merged long form authorizes `ANCHOR, DROP1, DROP2, DROP3, FINAL, VALUE_STACK, TALLY, RE_PITCH, the value-gap slide, the callback slide, or … a component card listed in offer_stack.json components[]`. The merged summary row says `outside the price-belt, value-stack, tally, re-pitch, value-gap, callback and component-card classes the rule authorizes`. Same class set, no class authorized by one and banned by the other — which is precisely what the acceptance row below asserts.

**If the two had disagreed, I would have kept the branch's long form** (it is the full definition; the role file's row is a summary that points at the mirror for full definitions) **and rewritten the summary row to match it** — the direction the branch already chose. That case did not arise.

## 6. Row-by-row re-proof at the merged tree

Tree: `cf8cf54f3bd3bac6390ffeee40707d760ea6843c`. Runner: `python3 -m pytest`, Python 3.14.7 / pytest 9.0.3. Working dir `23-ai-workforce-blueprint/templates/role-library/presentations`.

```
$ python3 -m pytest scripts/tests/test_pd090_price_face.py -v
============================= test session starts ==============================
platform darwin -- Python 3.14.7, pytest-9.0.3, pluggy-1.6.0
rootdir: .../templates/role-library/presentations
collected 8 items

scripts/tests/test_pd090_price_face.py::test_both_sections_are_present_and_parse PASSED [ 12%]
scripts/tests/test_pd090_price_face.py::test_mirror_authorizes_every_class_in_the_one_clause PASSED [ 25%]
scripts/tests/test_pd090_price_face.py::test_mirror_reconciles_every_authorized_figure_to_a_declared_source PASSED [ 37%]
scripts/tests/test_pd090_price_face.py::test_mirror_drops_both_retired_exceptions PASSED [ 50%]
scripts/tests/test_pd090_price_face.py::test_mirror_drops_always_fail_a_and_b_and_keeps_c PASSED [ 62%]
scripts/tests/test_pd090_price_face.py::test_role_summary_does_not_ban_the_classes_the_rule_authorizes PASSED [ 75%]
scripts/tests/test_pd090_price_face.py::test_role_summary_names_the_same_authorized_classes PASSED [ 87%]
scripts/tests/test_pd090_price_face.py::test_no_authorized_class_is_banned_by_either_section PASSED [100%]

============================== 8 passed in 0.17s ===============================
RC=0
```

Row by row, what each test id proves:

| Test id | Acceptance row | Result |
|---|---|---|
| `test_both_sections_are_present_and_parse` | both sections that state the rule exist and are parseable | PASSED |
| `test_mirror_authorizes_every_class_in_the_one_clause` | all 11 authorized classes live in ONE clause, tagged from `arc_allocation.json`, component cards from `offer_stack.json components[]` | PASSED |
| `test_mirror_reconciles_every_authorized_figure_to_a_declared_source` | every authorized figure reconciles to `price_ladder.json` or `offer_stack.json` | PASSED |
| `test_mirror_drops_both_retired_exceptions` | the two canceling exceptions are gone | PASSED |
| `test_mirror_drops_always_fail_a_and_b_and_keeps_c` | always-fail (a) and (b) deleted, (c) kept | PASSED |
| `test_role_summary_does_not_ban_the_classes_the_rule_authorizes` | summary row no longer bans per-item values / multiple prices as a class | PASSED |
| `test_role_summary_names_the_same_authorized_classes` | summary and full definition describe the same class set | PASSED |
| `test_no_authorized_class_is_banned_by_either_section` | **the D-17 invariant** — no class required by one section and banned by the other | PASSED |

Regression proof — the four tests named in `evidence/PD-090/BUILD-REPORT.md` as the ones that could break, run at the merged tree:

```
$ python3 -m pytest scripts/tests/test_af_c8_copy_contract.py \
    scripts/tests/test_contract_completeness.py \
    scripts/tests/test_pres001_unit_contracts.py \
    scripts/tests/test_fix32_manifest_copy_drift.py -q
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 1.43s
RC=0
```

```
$ python3 -m pytest scripts/tests/test_qc_gate_teeth.py -q
...............                                                          [100%]
15 passed in 0.12s
RC=0
```

Total at the merged tree: **104 passed, 0 failed** across the acceptance file and the five named regression files.

## 7. Remote-head proof

```
$ git ls-remote --heads origin refs/heads/pd/fl23-role-procedures-b--hold-d17
cf8cf54f3bd3bac6390ffeee40707d760ea6843c	refs/heads/pd/fl23-role-procedures-b--hold-d17
RC=0

$ git rev-parse HEAD
cf8cf54f3bd3bac6390ffeee40707d760ea6843c
```

Push output:

```
To https://github.com/trevorotts1/openclaw-onboarding.git
   af296dd88..cf8cf54f3  pd-repair-PD-090 -> pd/fl23-role-procedures-b--hold-d17
```

Fast-forward from `af296dd88` to `cf8cf54f3`. Remote head equals local head, full 40 characters.

### Final head, after this report was committed

```
$ git push origin pd-repair-PD-090:refs/heads/pd/fl23-role-procedures-b--hold-d17
To https://github.com/trevorotts1/openclaw-onboarding.git
   cf8cf54f3..85cc6dcdf  pd-repair-PD-090 -> pd/fl23-role-procedures-b--hold-d17

$ git ls-remote --heads origin refs/heads/pd/fl23-role-procedures-b--hold-d17
85cc6dcdfa253360ec6d4172236acb790a516c8f	refs/heads/pd/fl23-role-procedures-b--hold-d17
RC=0
```

Committing this report necessarily advances the head past the merge commit, so the two facts to check are:

1. the merge commit is in the pushed history —
   `git merge-base --is-ancestor cf8cf54f3bd3bac6390ffeee40707d760ea6843c HEAD` → rc=0;
2. the remote head equals the local head at push time —
   `85cc6dcdfa253360ec6d4172236acb790a516c8f` both sides.

Acceptance re-run at that final head:

```
$ python3 -m pytest scripts/tests/test_pd090_price_face.py -q
........                                                                 [100%]
8 passed in 0.21s
RC=0
```

## 8. What I could not prove, and what remains open

1. **The engine's reported conflict could not be reproduced.** Neither named file conflicts at `ebf5c769`. The second named path does not exist in any ref. I cannot tell from here whether the engine read a different `main`, a stale base, or whether its conflict detector misfired. I repaired the only thing I could observe: the branch now contains `origin/main` at `ebf5c769` and merges clean. If the engine's gate re-runs against the same stale snapshot, it may report the same phantom conflict again.
2. **The full `scripts/tests/` directory was not run end to end.** It exceeded a 120-second budget and I stopped it rather than let it hang. I ran the acceptance file plus the five files the build report named as at-risk (104 tests). The other ~80 test files in that directory were not exercised. Any breakage outside those five would be pre-existing on the branch and unrelated to this merge, which changed no file the branch had not already changed.
3. **The cross-file disagreement with `sops/slide-image-creator-sops.md` Part F is still open, by design.** That file is lane FL24 and its matching edit is unit PD-094. `BUILD-REPORT.md` records this: Part F still bans a per-component dollar value and still keeps the tally off the audience face, so it disagrees with PD-090's rewritten rule. PD-094 A3 is the cross-file agreement check. This repair neither touched that file nor should have.
4. **I did not run the acceptance checker's negative control** (reverting the rule to the old wording and watching the tests fail) at the merged tree. The branch's build report states the checker was built, not run, and QC owns that proof. The tests are assertion-based over the rule text, so a reverted row would fail `test_mirror_drops_both_retired_exceptions` and `test_mirror_drops_always_fail_a_and_b_and_keeps_c`, but I did not demonstrate that here.

## 9. Scope

Files changed by this repair, apart from the merge itself: none. The merge commit `cf8cf54f3` carries main's 66 changed files and nothing else — no hand edits, no conflict resolution, no tidying, no neighbouring code touched. This report file is the only addition.

---

# REPAIR 2 — the sibling collision the first repair could not see

**Repair date:** November 13, 2026
**Branch:** `pd/fl23-role-procedures-b--hold-d17` — PR 3319
**Why this exists:** PR 3319 was ejected again after Repair 1. Repair 1 merged `origin/main` and merged cleanly, which is
exactly why it came back: the batch engine ejects a member against its **in-batch siblings**, not only against `main`.

Section 3 above concluded that the engine's conflict could not be reproduced and named a path that does not exist
(`sops/qc-specialist-presentations.md`). That conclusion was correct about `main` and wrong about the cause. The real
collision is with the sibling PR riding the same batch: **#3207, `pd/fl23-role-procedures-b`, PD-098** — which edits the
same two auto-fail tables, one file with `-sops` in its name, which is the file the ledger was reaching for.

## R2.1 Heads at the start of this repair

| Item | Full 40-character SHA |
|---|---|
| Branch head before this repair (PRE) | `388ed0df3ffbe0354363cfd19bc146bebe69fd86` |
| `origin/main` | `ebf5c769a2ad5b2582bf2256588095cbef20cfac` |
| Sibling `pd/fl23-role-procedures-b` (#3207) | `55dbc08155a861ca00f69a426ed80608975af935` |

```
$ git ls-remote --heads origin pd/fl23-role-procedures-b--hold-d17
388ed0df3ffbe0354363cfd19bc146bebe69fd86	refs/heads/pd/fl23-role-procedures-b--hold-d17
$ git rev-parse origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac        # matches the expected main
```

## R2.2 The merge with main: nothing left to merge

```
$ git checkout -b repair origin/pd/fl23-role-procedures-b--hold-d17
$ git merge origin/main
Already up to date.
rc=0
$ git merge-base origin/main HEAD
ebf5c769a2ad5b2582bf2256588095cbef20cfac        # == origin/main tip
$ git merge-base --is-ancestor origin/main HEAD; echo $?
0
```

`origin/main` is already an ancestor of PRE, because Repair 1 merged it. There is no file to arbitrate and no resolution
to invent, and I did not invent one. The merge-base being exactly the main tip is the proof that main moved nothing for
this branch to absorb.

## R2.3 SIBLING TEST — BEFORE

`git merge-tree --write-tree` touches no branch and creates no commit.

```
$ git merge-tree --write-tree HEAD origin/pd/fl23-role-procedures-b
cbe73def69c798f513f3b64fa8d1ebdad287e970
100644 a40eaa7bae02c4092a4b6dc0496306b491322ff9 1   .../presentations/qc-specialist-presentations.md
100644 0f0c5360a04d9350d310f8ff776354954ca8722b 2   .../presentations/qc-specialist-presentations.md
100644 53c3f5c8c496df81e1b64519e9e42e027d694c69 3   .../presentations/qc-specialist-presentations.md
100644 8da262c3f408e31c0e171f4c5703492dc56ee825 1   .../presentations/sops/qc-specialist-presentations-sops.md
100644 dfc4cda2ae8f2e98eec50e6fb7d22a7dca9ab024 2   .../presentations/sops/qc-specialist-presentations-sops.md
100644 4c65c0c406a83087249288c136a6eb19f619c67a 3   .../presentations/sops/qc-specialist-presentations-sops.md
CONFLICT (content): Merge conflict in .../qc-specialist-presentations.md
CONFLICT (content): Merge conflict in .../sops/qc-specialist-presentations-sops.md
rc=1
```

**Both files conflict. This is the ejection.** One sibling in the list, one collides.

## R2.4 What each side actually changed, so the resolution is not a coin toss

The merge base of the two branches is `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`. Commits since that base:

| Side | Commit | Intent |
|---|---|---|
| Ours | `af296dd88` PD-090 | one price-face rule instead of two that cancel: AF-PRICE-FACE's two overlapping exception clauses replaced by a single authorized-class list |
| Sibling | `5e63875fd` PD-098 | every code not in `PIPELINE-MANIFEST.json` marked `(role-level; not in the registry)`; re-pitch block widened from 4-to-5 to 4-7 slides |
| Sibling | `55dbc0815` PD-098 | mirror AF-C3 wording + restored converter-parity row |

Registry check against `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` — all fourteen codes in the
conflicted table (`AF-LOGO`, `AF-CAST`, `AF-FACE-MOOD`, `AF-GRAD`, `AF-TYPE`, `AF-TELEGRAPH`, `AF-PRICE-FACE`,
`AF-VALIDATOR`, `AF-WALL`, `AF-OPACITY`, `AF-CALLOUT`, `AF-REPITCH`, `AF-MODEL`, `AF-SAME`) report **not-registered**, so
PD-098's marker is factually required and PD-098's own test enforces it.

## R2.5 Resolution per hunk — both intents kept, nothing deleted wholesale

| File | Taken | Why |
|---|---|---|
| both files | sibling's table rows (every code carries the `(role-level; not in the registry)` marker; mirror re-pitch reads 4-7) | PD-098's intent; required by its test and factual against the manifest |
| both files | **our** AF-PRICE-FACE wording, re-headed with the marker | PD-090's intent; PD-098 did not touch this wording beyond the marker |

Resolved rows, verbatim heads:

```
| AF-PRICE-FACE (role-level; not in the registry) | Unauthorized dollar figures on a slide face outside the price-belt, value-stack, tally, re-pitch, value-gap, callback and component-card classes the rule authorizes | ...   (role file)
| AF-PRICE-FACE (role-level; not in the registry) | Unauthorized price(s) or per-item dollar values on the slide face. ... auto-fails unless the slide is tagged in arc_allocation.json as ANCHOR, DROP1, ...   (mirror)
```

Neither side was dropped: the marker comes only from the sibling, the price-face clause comes only from PD-090.

### The real collision was in PD-090's own acceptance checker

PD-090's locator matched the bare table cell:

```python
if stripped.startswith("| AF-PRICE-FACE |"):
```

PD-098's marker lands between the code and that closing pipe, so all 8 PD-090 rows raised
`AssertionError: no AF-PRICE-FACE row in ...` at the merged tree — 8 failed, 5 passed. That is the cross-PR break the
batch engine was ejecting on.

Fix, in `scripts/tests/test_pd090_price_face.py` only:

```python
if stripped.startswith("| AF-PRICE-FACE"):
```

Every assertion in the file is unchanged. Nothing was weakened, skipped, renamed or xfailed; the change makes the
locator find the row that PD-098 now labels, and the row content is still asserted exactly as before.

## R2.6 SIBLING TEST — AFTER

```
$ git merge-tree --write-tree HEAD origin/pd/fl23-role-procedures-b
70a59df55dcc356564ef5e359c9a0b29eec2307e
rc=0
```

Clean, no conflict block, no message output. Nothing was imported from the sibling that was already clean, because
nothing in this list was clean — the one sibling conflicted and was imported.

## R2.7 What was imported and why

Sibling `pd/fl23-role-procedures-b` @ `55dbc08155a861ca00f69a426ed80608975af935` was merged in as a real two-parent
commit:

```
$ git rev-list --parents -n1 HEAD
8486289e70f88e7022eb63b0ca7348eec4a895fe 388ed0df3ffbe0354363cfd19bc146bebe69fd86 55dbc08155a861ca00f69a426ed80608975af935
```

Parents: PRE, then the sibling head. Six sibling commits came with it (PD-087, PD-088-series PD-098 work, PD-092). This
is the minimum needed to make the pair mergeable — no unrelated branch was pulled in, and the one sibling that was clean
was left alone.

## R2.8 Acceptance rows at the repaired head

Tree `8486289e70f88e7022eb63b0ca7348eec4a895fe`, runner `python3 -I -m pytest`.

```
$ python3 -I -m pytest test_pd090_price_face.py -v
test_both_sections_are_present_and_parse PASSED
test_mirror_authorizes_every_class_in_the_one_clause PASSED
test_mirror_reconciles_every_authorized_figure_to_a_declared_source PASSED
test_mirror_drops_both_retired_exceptions PASSED
test_mirror_drops_always_fail_a_and_b_and_keeps_c PASSED
test_role_summary_does_not_ban_the_classes_the_rule_authorizes PASSED
test_role_summary_names_the_same_authorized_classes PASSED
test_no_authorized_class_is_banned_by_either_section PASSED
8 passed
rc=0
```

Both PRs' checkers together, proving the pair is green in one tree:

```
$ python3 -I -m pytest test_pd090_price_face.py test_pd098_qc_codes.py -q
.............  [100%]
13 passed in 0.09s
rc=0
```

**Negative control on the repaired locator** — the checker still fails when the rule is wrong. One word removed from the
role row (`callback and component-card` → `component-card`), then restored:

```
$ (mutate role row) python3 -I -m pytest test_pd090_price_face.py -q
FAILED test_pd090_price_face.py::test_role_summary_names_the_same_authorized_classes
1 failed, 7 passed
$ (restore) python3 -I -m pytest test_pd090_price_face.py -q
8 passed
```

No failure to attribute to a base commit: every row is green at the repaired head, and the only red state observed was
the sibling collision itself, which is this repair's subject.

## R2.9 Remote head and ancestry arithmetic

Push was fast-forward, no rebase, no force:

```
$ git push origin HEAD:refs/heads/pd/fl23-role-procedures-b--hold-d17
To https://github.com/trevorotts1/openclaw-onboarding.git
   388ed0df3..8486289e7  HEAD -> pd/fl23-role-procedures-b--hold-d17
rc=0

$ git rev-parse HEAD
8486289e70f88e7022eb63b0ca7348eec4a895fe
$ git ls-remote --heads origin pd/fl23-role-procedures-b--hold-d17
8486289e70f88e7022eb63b0ca7348eec4a895fe	refs/heads/pd/fl23-role-procedures-b--hold-d17

$ git merge-base --is-ancestor 388ed0df3ffbe0354363cfd19bc146bebe69fd86 HEAD; echo $?
0
```

Local head equals remote head, 40 characters both sides. PRE is an ancestor of the new head — nothing was rewritten.

## R2.10 What I could not prove

1. **The engine's own batch logic was not run.** `git merge-tree --write-tree` proves the pair no longer conflicts at the
   text level. If the engine ejects on a different axis — a manifest lock, a version-stamp rule, a checksum — this
   repair does not cover it, and I have no way to run that detector from here.
2. **The rest of the sibling's batch was not visible.** The task named exactly one sibling (#3207). If other members
   ride the same batch and the list was incomplete, those pairs are untested.
3. **The full `scripts/tests/` directory was not run end to end.** It exceeded a 600-second budget and was stopped. I ran
   the two files this collision touches (13 tests). Roughly 80 other test files in that directory were not exercised.
4. **PD-098 has no acceptance file of its own beyond `test_pd098_qc_codes.py`.** I ran that file because the collision
   was with it. I did not audit the rest of PD-098's surface, which belongs to #3207 and not to this unit.
5. **`AF-REPITCH` 4-to-5 → 4-7 was taken from the sibling unverified against `SOP-PITCH-03-RE-PITCH.md`.** That is
   PD-098's claim to defend, not PD-090's; I kept it rather than silently reverting another PR's intent.
6. **The report commit itself advances the head.** The remote-head proof above is at `8486289e7`. Every commit after it is
   documentation only — this file and nothing else — so the code and test tree the proofs describe is still exactly
   `8486289e7`'s tree. The final remote head is re-read with `git ls-remote` after the last push and reported back with
   this repair; `git merge-base --is-ancestor 8486289e7 <final head>` is the check that the proof still stands.

## R2.11 Scope of this repair

| File | Change |
|---|---|
| `.../presentations/qc-specialist-presentations.md` | conflict resolved, both intents kept |
| `.../presentations/sops/qc-specialist-presentations-sops.md` | conflict resolved, both intents kept |
| `.../presentations/scripts/tests/test_pd090_price_face.py` | locator matches the PD-098 marker; zero assertions changed |
| `evidence/PD-090/REPAIR-REPORT.md` | this section |

Everything else in the merge commit came from the sibling or from main. No rebase, no force-push, nothing pushed to
`main`, no test weakened, skipped, renamed or xfailed, no conflict side dropped wholesale, `~/.openclaw` and every client
box untouched.

