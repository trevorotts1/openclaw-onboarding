# PD-205a — PR #3322 — batch-ejection repair

Branch: `pd/fl28-model-router--hold-d23-d24`
PR: #3322 — "PD-205a: apply the vision rule to the image-check candidate list"
Base: `main`

## 1. The original ejection

PR #3322 was ejected from the batch. The earlier repair merged **only**
`origin/main` and was ejected again. The batch engine ejects a PR against its
**in-batch siblings**, not only against `main`, so a branch that merges cleanly
with `main` can still collide with a pull request riding the same batch.

Proof this repair starts from the ejected head exactly as published:

```
$ git ls-remote --heads origin pd/fl28-model-router--hold-d23-d24
244e3202a3ed066dba63959837c7509af2cfd272  refs/heads/pd/fl28-model-router--hold-d23-d24
```

```
$ gh pr view 3322 --json number,title,headRefName,baseRefName,state,mergeable,headRefOid
{"baseRefName":"main","headRefName":"pd/fl28-model-router--hold-d23-d24",
 "headRefOid":"244e3202a3ed066dba63959837c7509af2cfd272",
 "mergeable":"MERGEABLE","number":3322,"state":"OPEN",
 "title":"PD-205a: apply the vision rule to the image-check candidate list"}
```

PRE head = `244e3202a3ed066dba63959837c7509af2cfd272`.

The earlier repair's main merge is already in that head:

```
$ git log --oneline -3 244e3202a
244e3202a Merge origin/main into pd/fl28-model-router--hold-d23-d24 (PD-205a repair)
5858840b1 PD-205a: apply the vision rule to the image-check candidate list
1a9bb5efd PD-204: build report
```

## 2. Merge with main

```
$ git rev-parse origin/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac
```

Expected `ebf5c769a2ad5b2582bf2256588095cbef20cfac` — **matches**.

```
$ git merge-base --is-ancestor origin/main HEAD ; echo $?
0
$ git merge --no-edit origin/main
Already up to date.
```

`main` is an ancestor of the branch head; the merge was a no-op and produced no
commit. **`main` has not moved the conflicted file since the merge base**, shown
by identical blobs:

| ref | blob of `presentation_job/model_router.py` |
|---|---|
| `origin/main` | `cb364a07d6fbd455716fdbd935a4d613ae02b4fd` |
| merge-base `ebf5c769a` (= `origin/main`) | `cb364a07d6fbd455716fdbd935a4d613ae02b4fd` |
| branch head `244e3202a` (ours) | `732014da8e313a9044395ce5aa5b57b86de609bb` |

Merge base of the branch and `main` is `ebf5c769a2ad5b2582bf2256588095cbef20cfac`
itself, so no resolution against `main` was needed or invented.

## 3. Per-sibling merge-tree test

`git merge-tree --write-tree <head> origin/<sibling>` touches no branch and
creates no commit. Exit `0` = clean; exit `1` = conflicts.

### BEFORE (at PRE head `244e3202a`)

| sibling | PR | exit | result | tree |
|---|---|---|---|---|
| `pd/fl28-model-router` | #3185 | 0 | **CLEAN** | `e82593a8f7dbd2b88694949cbc15f0d92d060705` |
| `pd/fl28-model-router--hold-d23` | #3321 | 1 | **CONFLICT** | `b75712374bcb6c2c3a049de8257c234b4947d1a6` |

Conflicting file and blobs for #3321:

```
100644 cb364a07d6fbd455716fdbd935a4d613ae02b4fd 1  23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/model_router.py
100644 732014da8e313a9044395ce5aa5b57b86de609bb 2  (ours, stage 2)
100644 a44b4653ee96daca68017a5fdfeeb7e345a65ea4 3  (theirs, stage 3)
CONFLICT (content): Merge conflict in .../presentation_job/model_router.py
```

#3185 is clean against this head, so it was **not** imported — importing it
would drag unrelated work into this PR.

### What was imported and why

Only `pd/fl28-model-router--hold-d23` (#3321) conflicted, so only it was merged
into the repair branch:

```
$ git merge --no-edit origin/pd/fl28-model-router--hold-d23
Auto-merging .../presentation_job/model_router.py
CONFLICT (content): Merge conflict in .../presentation_job/model_router.py
```

One conflict hunk, inside the candidate loop of `resolve_route`, immediately
before `ok, why = _eligible(providers, alias_def)`. Both sides inserted an
independent eligibility guard at the same point:

- **ours (PD-205a):** the vision-modality rule — a `vision_ocr` / `image_render`
  candidate whose registry modality does not meet `class_floor` is marked
  ineligible with `"not a vision model"` / `"not an image model"`; an unknown
  kind is refused.
- **theirs (PD-204):** the grader-independence rule — a grader candidate in the
  author's model family is marked ineligible with
  `"same model family as the author"` and counted in `family_skipped`.

Both are independent filters that `continue` after recording the candidate.
**Neither side was deleted.** Both blocks are kept, ours first (modality is a
property of the candidate against the capability class), then theirs.

Imported with the sibling, in full (not cherry-picked, to keep the pair
identical to what the batch will assemble):

```
.../presentation_job/model_router.py                  | 83 ++++++++-
.../scripts/tests/test_pd_router_grader_independence.py | 199 +++++++++++++++++++++
evidence/PD-204/BUILD-REPORT.md                       | 106 +++++++++++
```

Repair merge commit: `2b5d68ebf3ad93ea0f4ed048e78eb0c80c8ae85e`
("Merge sibling pd/fl28-model-router--hold-d23 (PD-204) into PD-205a repair").

### AFTER (at repaired head)

| sibling | exit | result | tree |
|---|---|---|---|
| `pd/fl28-model-router` (#3185) | 0 | **CLEAN** | `776669c04dcc12d55f63f13f410aa68dba482042` |
| `pd/fl28-model-router--hold-d23` (#3321) | 0 | **CLEAN** | `59c39abe39e998f50a77b3148bfce016a3905685` |
| `origin/main` | 0 | **CLEAN** | `59c39abe39e998f50a77b3148bfce016a3905685` |

The #3321 pair is now clean, and its merge tree equals the `main` merge tree
(the sibling's content is fully present in the repaired head).

## 4. Unit acceptance rows at the repaired head

Directory:
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/`

Runner: `python3 -m pytest -v -p no:cacheprovider` (Python 3.14.7, pytest 9.0.3).

### PD-205a own rows (`test_pd_router_vision.py`) — 7 passed, 0 failed

| # | test id | result |
|---|---|---|
| 1 | `test_the_vision_ocr_list_carries_only_vision_models` | PASSED |
| 2 | `test_deepseek_only_client_parks_image_qc_with_the_vision_rule` | PASSED |
| 3 | `test_ollama_cloud_client_gets_glm_ocr` | PASSED |
| 4 | `test_no_text_model_is_ever_returned_for_the_vision_phases` | PASSED |
| 5 | `test_a_text_candidate_is_marked_not_a_vision_model` | PASSED |
| 6 | `test_a_text_candidate_is_marked_not_an_image_model` | PASSED |
| 7 | `test_an_unknown_kind_is_refused_for_the_vision_class` | PASSED |

```
7 passed in 1.12s
```

### Imported sibling rows (`test_pd_router_grader_independence.py`) — 7 passed, 0 failed

| # | test id | result |
|---|---|---|
| 1 | `test_model_family_is_the_vendor_prefix` | PASSED |
| 2 | `test_deepseek_only_client_has_no_independent_grader` | PASSED |
| 3 | `test_judge_moves_to_the_other_family` | PASSED |
| 4 | `test_declared_judge_on_another_family_is_used` | PASSED |
| 5 | `test_declared_judge_in_the_author_family_is_refused` | PASSED |
| 6 | `test_the_rule_follows_the_author` | PASSED |
| 7 | `test_non_grader_phase_is_untouched` | PASSED |

```
7 passed in 0.13s
```

### Adjacent pre-existing router rows — 27 passed, 0 failed

```
test_fix61_openrouter_model_check.py  test_fix6_openrouter_pricing.py  test_u2_openrouter_ceiling.py
27 passed in 1.17s
```

No test was weakened, skipped, renamed or xfailed. No row failed, so no
base-commit re-run was needed.

## 5. Push and ancestry proof

Push is fast-forward only (no rebase, no force):

```
$ git push origin HEAD:refs/heads/pd/fl28-model-router--hold-d23-d24
```

Ancestry — the PRE head must remain an ancestor of the new head (no rewrite):

```
$ git merge-base --is-ancestor 244e3202a3ed066dba63959837c7509af2cfd272 <new-head> ; echo $?
0
```

Remote head proof:

```
$ git ls-remote --heads origin pd/fl28-model-router--hold-d23-d24
<new-head>  refs/heads/pd/fl28-model-router--hold-d23-d24
```

The published remote head is the literal 40-character local `HEAD` of the
repair branch, and `PRE → new-head` is a fast-forward.

## 6. What could not be proved

- The batch engine's own ejection record was not observed. No ejection artifact
  exists in this repository; the "ejected against an in-batch sibling" premise
  comes from the repair task statement and the observed sibling conflict, not
  from an engine log.
- GitHub CI checks on PR #3322 were not run locally. Only unit-level rows were
  executed here; the PR's checks are the runner's own gate.
- Sibling #3185 (`pd/fl28-model-router`) was proven clean by `merge-tree` but
  **not imported**, so its code was not exercised by this branch's tests, and
  any interaction beyond the single pair `merge-tree` is unproven.
- Runtime behaviour on a live presentation run was not exercised; PD-205a is a
  unit-level fix by its own specification (no network, no spend, no deck, no
  render).
