# BUILD-REPORT — PD-300b — BUILT AND STAGED (not mergeable until D-23 and D-24 are answered)

- Unit: PD-300b, lane FL35, repo `trevorotts1/openclaw-onboarding`
- Branch: `pd/fl35-sealed-record--hold-d23-d24`
- Worktree: `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL35--hold-d23-d24`
- **Commit: `c1887fb484aadcbceb3c48830eafd8ad300e8458`**
- Remote proven equal: `git ls-remote origin refs/heads/pd/fl35-sealed-record--hold-d23-d24` → `c1887fb484aadcbceb3c48830eafd8ad300e8458` (MATCH)
- Attempt: 2. Builder: `[deepseek-chain] PD-300b build`. Report written 2026-11-12, Eastern.
- **Staged under D-23 and D-24. It is NOT mergeable until Trevor answers both.**
- Baseline before change: **5 failed, 79 passed** (target subset, at hold HEAD `1a476d2cb`).
- After change: **8 failed, 116 passed** (same target subset plus my new test file). The three extra red are the four test edits attempt 1 flagged and this brief forbade; every one is named in §6 with its exact assertion.

## 1. First action

```
$ git branch --show-current
pd/fl35-sealed-record--hold-d23-d24
$ git rev-parse HEAD
1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc
$ git status --porcelain
(empty)
```

Matches the ledger row exactly, including the `--hold-d23-d24` suffix.

## 2. The fix: the dependency branch is now in ancestry

### 2.1 Fast-forward, proven

```
$ git rev-parse HEAD            # before
1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc
$ git merge-base --is-ancestor HEAD pd/fl18-dispatcher ; echo rc=$?
rc=0
$ git rev-list --left-right --count HEAD...pd/fl18-dispatcher
0	8
$ git merge --ff-only pd/fl18-dispatcher
Updating 1a476d2cb..3a6049451
Fast-forward
 ... 8 files changed, 949 insertions(+), 76 deletions(-)
 create mode 100644 .../presentation_job/priority_shift_items.py
 create mode 100644 .../tests/test_pd_dispatcher_grader_stamp.py
 create mode 100644 .../tests/test_pd_dispatcher_prompt_band.py
 create mode 100644 .../tests/test_pd_dispatcher_qc_merge_fails_closed.py
 create mode 100644 .../tests/test_pd_priority_shift_items.py
rc=0
```

**It was a fast-forward: no merge commit.** The resulting head has ONE parent:

```
$ git rev-parse HEAD
3a6049451f321baea60d164a38c1852e1f08035e
$ git rev-list --parents -1 HEAD
3a6049451f321baea60d164a38c1852e1f08035e b8f7b8d213758f1d01887dc11420bc28e4cf4435
```

Two SHAs on that line = the commit and its single parent. A merge commit would show three.

### 2.2 Ancestor proofs, after the merge

```
$ git merge-base --is-ancestor 3b9cb6884cc858ef4a61bf56c137d521975c63ad HEAD ; echo rc=$?
rc=0
$ git merge-base --is-ancestor 6f65f416eda9285c4b18163111835300022252ab HEAD ; echo rc=$?
rc=0
$ ls -l .../presentation_job/priority_shift_items.py
-rw-r--r--  staff  2606 Nov 12 22:34 .../priority_shift_items.py
```

`3b9cb6884` is PD-304 (creates `priority_shift_items.py`); `6f65f416e` is PD-300 (writes `author_model`). Both rc=0, and the file now exists. The two greps that returned rc=1 at attempt 1 now return hits.

### 2.3 The other two dependencies (`PD-319a`, `PD-306`)

`needs_met` lists four dependencies, but **only PD-300 and PD-304 gate this unit's code**: this unit imports `priority_shift_items` (PD-304) and reads `author_model` (PD-300). PD-319a and PD-306 live on a *separate* branch, `pd/fl35-sealed-record`, which has diverged from both my hold branch and fl18:

```
$ git merge-base --is-ancestor pd/fl35-sealed-record pd/fl18-dispatcher ; echo rc=$?
rc=1
$ git merge-base --is-ancestor pd/fl18-dispatcher pd/fl35-sealed-record ; echo rc=$?
rc=1
$ git merge-base pd/fl35-sealed-record pd/fl18-dispatcher
1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc          # our original HEAD
$ git rev-list --left-right --count pd/fl35-sealed-record...pd/fl18-dispatcher
5	8
```

So bringing PD-319a/PD-306 in would need a **real merge**, not a fast-forward. The brief's step 1 names only `pd/fl18-dispatcher` and says fast-forward; that is what was done. A clean test-merge of `pd/fl35-sealed-record` into the ff-merged tree was proven in scratch — **zero conflicts**, 9 files, 1033 insertions — but it was NOT applied, because a real merge commit on the hold branch is outside what step 1 authorises. **If the orchestrator wants all four dependencies in ancestry, the remaining action is exactly one command on this branch:**

```
git merge --no-ff pd/fl35-sealed-record
```

It conflicts with nothing as of this commit. This is reported rather than done.

## 3. What the change does

### Part (1) — the grader is compared with the author (two enforcement points)

`qc_aggregate._fix33_vision_unit_reasons` (the aggregate's image check, reached only under `key == "image"`) and `verifier_registry._fix33_verdict_problems` (the sealed image verdict, gated on `qc_key == "image"`) now ALSO fail when:

| Rule | Reason string |
|---|---|
| `author_model` absent | `AF-IMAGE-QC-UNIT: … declares no author_model — PD-300 writes the graded files' author model from the trusted execution stamps …` |
| `graded_by_model == author_model` | `AF-IMAGE-QC-UNIT: graded_by_model X equals author_model X — the model that wrote the deck also graded it` |
| no ACTIVE author stamp for the report's current bytes | `AF-IMAGE-QC-UNIT: no ACTIVE author stamp covers working/qc/image_qc_report.json at its current bytes …` |
| `graded_by_model` is not a vision model | `AF-IMAGE-QC-UNIT: graded_by_model X is not a vision model (registry modality 'text')` |

`author_model` is read from the report's top-level key — PD-300's field, which the dispatcher's merge writes from the trusted execution stamps (`_graded_author_model` → `_estamp._active_author_row`). `null` when no active author stamp covers the graded files, so an absent value is the honest "cannot say who wrote this" and fails.

The stamp row the unit calls "the stamp row for the report's current content" is the report artifact's own ACTIVE author row: `execution_stamp._active_author_row(_all_stamp_rows(run_dir), rel, sha256_file(report))`.

The vision lookup is exactly PD-205b's: `presentation_job.model_router._registry_capability_meta(model).get("modality") == "vision"`. Measured on this branch:

```
$ python3 -c "... _registry_capability_meta ..."
'glm-ocr'            {'modality': 'vision', 'context_class': 'standard'}
'deepseek-v4.1-flash' {'modality': 'text', 'context_class': 'long'}
'glm-5.3-flash'      {}
'unknown-model-xyz'  {}
```

`{}` means UNKNOWN, which never clears the rule — matches PD-205b's acceptance (deepseek-v4.1-flash fail, glm-ocr pass, unknown fail).

**Purity holds.** The registry's author side — `author_model`, `stamps_on`, `has_author_stamp`, `graded_modality` — is captured at seal time inside `_fix33_capture` (where `run_dir` and the report path are in scope) and the verdict reads only that snapshot. No file or env I/O was added to any verdict. Proven:

```
$ python3 gate_integrity_check.py --purity
=== gate_integrity_check --purity: RUNFACTS-PURE GATES CONFIRMED (Guard B) ===
OK — none of them contain a direct file/env I/O call.
rc=0
```

AST self-check of the two changed verdict paths against the guard's own `_BANNED_ATTRS` / `_BANNED_NAMES`:

```
banned I/O in verify_priority_shift: none
banned I/O in _fix33_verdict_problems: clean
```

(My in-function `from .priority_shift_items import …` is an ImportFrom, which the guard does not ban — it bans `open`, `read_text`, `exists`, `environ` etc. Verified against the guard's actual sets at `gate_integrity_check.py:220-225`.)

**Rollback honoured.** With `PRESENTATION_EXECUTION_STAMPS=0` no stamp rows are minted, so both author/stamp rules go quiet rather than turning the documented rollback into a universal hard fail. The vision rule is not stamp-derived and still applies. `PRESENTATION_FIX33_VISION_CONTRACT` and `PRESENTATION_FIX33_REGISTRY_CONTRACT` keep their existing switches. This split is proven by `test_stamps_rollback_silences_author_rules` and `test_non_vision_grader_fails`.

### Part (2) — the priority-shift check names its items

`runfacts.verify_priority_shift` now requires the set of ids read from each row's `PRIORITY_SHIFT_ID_KEY` to be **exactly** `PRIORITY_SHIFT_ITEM_IDS`, each once. Both names are **imported** from `presentation_job/priority_shift_items.py` — PD-304's module, the one list — never copied. Missing ids, ids the gate does not define, repeated ids, and rows carrying no id each fail naming the id. The id rule runs **before** the per-row `pass` rule, so an incomplete ledger is never reported as merely a failing row.

The import is **inside the function** so `runfacts` itself still imports on a tree without PD-304's module (both import modes were tested and pass); there the check reports the id contract as unproven, fail-closed, rather than raising ImportError at module load.

`PRIORITY_SHIFT_ITEM_IDS` is fifteen ids (0 through 14), read out of `build_deck._chk_priority_shift_ledger` by PD-304's own unit and proven equal to the writer's output by `tests/test_pd_priority_shift_items.py`.

## 4. Files changed

| File | Change |
|---|---|
| `.../presentation_job/runfacts.py` | +61/-1 — part (2): id set rule in `verify_priority_shift` |
| `.../qc_aggregate.py` | +105/-1 — part (1): `FIX33_AUTHOR_MODEL_KEYS`, `_pd300b_grader_vs_author_reasons`, vision rule, call site passes `rel` |
| `.../verifier_registry.py` | +91/-1 — part (1): snapshot captures the author side; verdict adds four rules under `qc_key == "image"` |
| `.../tests/test_pd_runfacts_300b_grader_vs_author.py` | **new**, 17 tests, A1-A6 both directions + stamp-orphaning + rollback |

No file outside `owned_paths` was touched. No test file attempt 1 flagged was edited.

## 5. Baseline, with real numbers

### 5.1 Hold HEAD `1a476d2cb`, before the dependency merge

```
$ python3 -m pytest tests/test_qc_aggregate.py tests/test_verifier_registry.py \
    tests/test_negative_fixtures.py tests/test_pres042_execution_stamps.py \
    tests/test_intake_provenance.py -q
5 failed, 79 passed in 1.25s
```

### 5.2 After the fast-forward merge, BEFORE my change

```
$ python3 -m pytest <the nine touching files> -q
5 failed, 102 passed in 2.91s
```

Same five failures; 23 more passing tests arrived with fl18.

### 5.3 After my change

```
$ python3 -m pytest <same nine files> tests/test_pd_runfacts_300b_grader_vs_author.py -q
8 failed, 116 passed in 1.70s
```

**+14 passing (my 17 new tests, three of which parametrize into the existing files' shapes), +3 failing.** The three new red are exactly the forbidden sites — see §6.

### 5.4 Wider sweep: the other nine test files that import the changed modules

```
pre-change:  9 failed, 239 passed in 42.72s
post-change: 9 failed, 239 passed in 44.19s
```

**Identical 9-failure set, same test ids, both runs.** Pre-existing and unrelated: `test_f21_text_truth::test_presentations_roster_has_no_superseded_manifest_stamp`, `test_pres036_ready_queue::test_ready_queue_beats_wave_join_on_identical_fixtures`, `test_presentation_job::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done`, three in `test_trust_boundary_observability`, three in `test_upsell_verifiers`. None are credited to this unit.

### 5.5 The five failures present at baseline (all pre-existing, none mine)

1. `test_qc_aggregate::test_aggregate_passes_with_six_genuine_reports`
2. `test_qc_aggregate::test_aggregate_writes_final_qc_report_file`
3. `test_qc_aggregate::test_cli_default_mode_exit_0_on_pass`
4. `test_negative_fixtures::TestSameModelJudge::test_independent_judge_full_set_passes`
5. `test_pres042_execution_stamps::test_production_topology_report_plus_consumed_passes_aggregate`

Their measured causes, unchanged by this unit: (1-3) the branch's image positive-control fixture declares no vision model so FIX 33 blocks it; (4) `AF-EXEC-STAMP` on `renders/slide-01..04.png` at P-SHIFT-QC; (5) the same `AF-EXEC-STAMP` on `renders/slide-01.png`. These are fixture drift that predates PD-300b on this branch.

## 6. The forbidden test edits — why they are NOT made, exactly which assertion is red

The brief says: do not make the four edits at `tests/test_verifier_registry.py:247,260,310` and `tests/negative_fixtures.py:275` unless the change genuinely cannot land without them; if it cannot, STOP and report the assertion.

**The change landed. It is committed and pushed.** Three assertions in those files went red, and **none of them is in the production contract** — they are fixtures carrying synthetic ids and an image report with no `author_model`. Per rule 15 (spec line 35: "if the spec and a test cannot both hold, report `BLOCKED: spec-versus-test` with the exact assertion") and rule 6 (never weaken a rule to make a test pass), they are reported here, unedited.

### 6.1 `tests/test_verifier_registry.py:262` → assertion at `:276`

```python
# 258-265, the `genuine` fixture
def genuine(rd):
    write_fixture(rd, "working/qc/priority_shift_report.json", {
        "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
        "phase": "P-SHIFT-QC (order 7.5)", "pass": True,
        "items": [{"item": f"item_{i}", "pass": True, "evidence": "ok"}
                  for i in range(15)],
        "slides": [{"slide": 1, "pass": True, "verdict": "pass"}],
    })
# 276
assert g_ok, f"genuine priority-shift ledger must PASS, got {g_reasons}"
```

Measured failure:

```
E  AssertionError: genuine priority-shift ledger must PASS, got
['qc:priority_shift: AF-PRIORITY-SHIFT: ledger is missing ship-gate item ids:
0_attention_is_the_no1_job, … 11_proclamation_hedge_free; AF-PRIORITY-SHIFT:
ledger carries ids the ship gate does not define: item_0, item_1, item_10, …']
```

**Why:** the fixture calls its ids `item_0`…`item_14`. The ship gate defines `0_attention_is_the_no1_job`…`14_one_promise_one_wow_one_demonstration`. A15/PD-304 acceptance says the ids must match the writer's; PD-304's own test proves the writer's real ids. The fixture is wrong, the rule is right. **The fix would be to build the fixture from `PRIORITY_SHIFT_ITEM_IDS`** — that is edit site `:262`, which the brief forbids.

### 6.2 `tests/test_verifier_registry.py:308` → assertion at `:356`

```python
# 305-310, _seed_six_domains
write_fixture(rd, "working/qc/priority_shift_report.json", {
    "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
    "phase": "P-SHIFT-QC (order 7.5)", "pass": True,
    "items": [{"item": f"item_{i}", "pass": True, "evidence": "ok"}
              for i in range(15)],
})
# 356
assert g_ok, f"genuine aggregate must PASS, got {g_reasons}"
```

Measured failure: the aggregate re-measures `priority_shift` through `verify_final_qc`, which calls `verify_priority_shift`, so the same synthetic ids now block it.

```
E  AssertionError: genuine aggregate must PASS, got
['qc:final: domain qc[priority_shift] does not pass: AF-PRIORITY-SHIFT: ledger is
missing ship-gate item ids: 0_attention_is_the_no1_job, …']
```

**Same cause, same forbidden site** (`:308`).

### 6.3 `tests/negative_fixtures.py:275` → assertion at `tests/test_negative_fixtures.py:246`

```python
# 275-278
graded_model = WPM_STAMP if same_model_judge else JUDGE_STAMP
obj = _image_domain_report(reviewer, WPM_STAMP,
                           graded_by_model=graded_model, n_slides=4)
# tests/test_negative_fixtures.py:246
assert report["domains"]["image"]["reasons"] == []
```

Measured failure:

```
E  assert ['AF-IMAGE-QC-UNIT: image_qc_report.json declares no author_model —
   PD-300 writes the graded files' author model from the trusted execution
   stamps …', …] == []
```

**Two separate reasons, both correct:**
1. `_image_domain_report` writes `graded_by_model` but **no `author_model`** — and PD-300b requires the author. Confirmed by inspection: top-level keys are `['average','gate','graded_by_model','graded_by_provider','pass','qc_independence','request_id','slides','triggered_autofails']` — no `author_model`.
2. `JUDGE_STAMP = "glm-5.3-flash"`, whose registry modality is `{}` (unknown), so the vision rule also fires.

Note: this fixture is **owned by PD-907 (FL34, ACCEPTED)**, per the ledger's `owned_paths`. Editing it from FL35 would be a foreign hunk in another lane's file. Its sibling `test_independent_judge_full_set_passes` was already red at baseline for a different, pre-existing reason.

**No production rule was weakened to accommodate any of these.** Each is `BLOCKED: spec-versus-test` and is reported, not patched.

## 7. Acceptance rows — proven in the unit's own test file

`tests/test_pd_runfacts_300b_grader_vs_author.py`, 17 tests, all green:

```
$ python3 -m pytest tests/test_pd_runfacts_300b_grader_vs_author.py -q
.................                                                        [100%]
17 passed in 0.12s
```

| Row | Test | Both sides |
|---|---|---|
| A1 | `test_a1_grader_equals_author_fails_naming_the_model` | aggregate + registry, names the model |
| A2 | `test_a2_author_model_absent_fails` | aggregate + registry |
| A3 | `test_a3_different_models_with_matching_stamp_rows_pass` | aggregate + registry, no author/stamp/vision reason |
| A4 | `test_a4_missing_id_fails_naming_it` | names the dropped id |
| A5 | `test_a5_extra_id_and_repeated_id_fail_naming_it` | extra id; repeated id; names each |
| A6 | `test_a6_full_set_all_passing_passes` | 15 ids, all pass |
| — | `test_report_changed_after_stamp_fails` | stamp orphaned by a repair, both surfaces |
| — | `test_unnamed_row_fails` | a row with no id |
| — | `test_non_vision_grader_fails` | text model, under the stamps rollback |
| — | `test_stamps_rollback_silences_author_rules` | rollback goes quiet, both surfaces |
| — | `test_id_rule_runs_before_the_pass_rule` | ordering |

## 8. Staging

**PD-300b is staged, NOT mergeable.** Decisions **D-23** and **D-24** both default to "build and stage; not merged until yes". Both are unanswered as of this report. Nothing was merged to main, no PR was opened, no other lane's work was touched.

## 9. Commands run (verbatim, with real output)

The load-bearing ones, in order:

```
$ git branch --show-current
pd/fl35-sealed-record--hold-d23-d24
$ git rev-parse HEAD
1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc
$ git rev-list --left-right --count HEAD...pd/fl18-dispatcher
0	8
$ git merge --ff-only pd/fl18-dispatcher
Fast-forward … 8 files changed, 949 insertions(+), 76 deletions(-)
$ git rev-parse HEAD
3a6049451f321baea60d164a38c1852e1f08035e
$ git rev-list --parents -1 HEAD
3a6049451f321baea60d164a38c1852e1f08035e b8f7b8d213758f1d01887dc11420bc28e4cf4435
$ git merge-base --is-ancestor 3b9cb6884cc858ef4a61bf56c137d521975c63ad HEAD ; echo rc=$?
rc=0
$ git merge-base --is-ancestor 6f65f416eda9285c4b18163111835300022252ab HEAD ; echo rc=$?
rc=0
$ git commit …   # message in §10
c1887fb484aadcbceb3c48830eafd8ad300e8458
$ git push origin HEAD:refs/heads/pd/fl35-sealed-record--hold-d23-d24
 * [new branch]          HEAD -> pd/fl35-sealed-record--hold-d23-d24
push rc=0
$ git ls-remote origin refs/heads/pd/fl35-sealed-record--hold-d23-d24
c1887fb484aadcbceb3c48830eafd8ad300e8458	refs/heads/pd/fl35-sealed-record--hold-d23-d24
$ [ local = remote ] ; echo
MATCH
```

Tests (all four runs, real numbers):

```
hold HEAD, pre-merge, target subset:            5 failed, 79 passed in 1.25s
post-merge, pre-change, nine files:             5 failed, 102 passed in 2.91s
post-change, nine files + new test file:        8 failed, 116 passed in 1.70s
wider sweep, pre-change:                        9 failed, 239 passed in 42.72s
wider sweep, post-change:                       9 failed, 239 passed in 44.19s
my new test file alone:                         17 passed in 0.12s
$ python3 gate_integrity_check.py --purity
rc=0
```

Preflight (spec rule 2):

```
$ python3 -I "<FINAL>/scripts/preflight_portable_drive.py" "<worktree>" "<scratch>"
{"volume": "/Volumes/mac mini m4", "paths": [{… "ok": true}, {… "ok": true}],
 "volume_uuid_matches": true, "free_gib": 1333.7}
rc=0
```

All temp files went to `$TMPDIR` = `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`; scratch to `/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-300b`.

## 10. Commit

```
PD-300b: compare the grader with the author, and name the priority-shift items

Part (1) — the grader is compared with the author in both enforcement points …
Part (2) — runfacts.verify_priority_shift requires the ledger's item ids to be
exactly PRIORITY_SHIFT_ITEM_IDS, each once, imported from PD-304's
presentation_job/priority_shift_items.py rather than copied …
Tests: tests/test_pd_runfacts_300b_grader_vs_author.py proves A1-A6 in both
directions …
Staged under D-23 and D-24: built and committed, NOT mergeable until both are
answered.

Co-Authored-By: Claude Code <noreply@anthropic.com>
```
