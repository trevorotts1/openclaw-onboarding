# BUILD-REPORT — PD-925 — the three fixture retargets PD-300b reported

- Unit: **PD-925** (ADDED unit, counted outside the 164 lock), lane **FL35**
- Branch: `pd/fl35-sealed-record--hold-d23-d24`
- Worktree: `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL35--hold-d23-d24`
- Repository: `trevorotts1/openclaw-onboarding`
- **Commit: `167622602545de863f0a6d7838a7f3c98b8b4548`**
- Base at start: `f3933631bd0ac5b0c412c3debf30cf860b183989` (PD-300b attempt-3 report commit; tree clean)
- Builder: `[deepseek-chain] PD-925 build`. Report written 2026-11-13.
- Scratchpad: `/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-925`
- Temp: `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp` (no `/tmp`, `/private/tmp` or `/var/folders` path used anywhere)

## 1. First action

```
$ git branch --show-current
pd/fl35-sealed-record--hold-d23-d24
$ git rev-parse HEAD
f3933631bd0ac5b0c412c3debf30cf860b183989
$ git status --porcelain
(empty)
```

Matches the PD-925 ledger row: `branch: pd/fl35-sealed-record--hold-d23-d24`, `phase: BUILDING`, `lane: FL35`.

## 2. The rule applied

Change what the **fixture constructs**. Never delete, weaken, flip or silence an assertion. Proven by diff: zero assertion lines appear in the change.

```
$ git diff -U0 | grep -E '^[+-].*assert'
(no output)
```

Both files' test functions keep every original `assert`, at the same line, with the same message text. Three assertions went green because they now receive an honest artifact, not because they were relaxed.

## 3. Per-assertion: what changed

### 3.1 `tests/test_verifier_registry.py:262` fixture → assertion at `:276`

**What was wrong.** The `genuine` fixture wrote `items: [{"item": f"item_{i}"} for i in range(15)]` — synthetic ids `item_0`…`item_14`. PD-300b's id-set rule (spec §1.3 / PD-304) requires the ledger's ids to equal `PRIORITY_SHIFT_ITEM_IDS` exactly. The rule is right; the fixture was the thing that lied about the ship gate's shape.

**Change.** Import `PRIORITY_SHIFT_ITEM_IDS` from `presentation_job/priority_shift_items.py` (PD-304's one list — the same constant the check reads) and build both fixture directions from it:

```python
from presentation_job.priority_shift_items import (  # noqa: E402
    PRIORITY_SHIFT_ITEM_IDS,
)
...
    def fabricate(rd):
        # Headline says pass but the ledger contradicts it: every ship-gate id
        # is present and passing except the salience apex.
        write_fixture(rd, "working/qc/priority_shift_report.json", {
            "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
            "pass": True,
            "items": [{"item": item_id,
                       "pass": item_id != "13_most_vivid_by_the_end",
                       "evidence": ("AF-NO-SALIENCE-APEX"
                                    if item_id == "13_most_vivid_by_the_end"
                                    else "ok")}
                      for item_id in PRIORITY_SHIFT_ITEM_IDS],
        })
```

The `fabricate` direction was retargeted too, and this matters: `range(13)` + one apex row was 14 synthetic rows, which after the id rule would fail on the *ids* before it ever reached the pass rule the assertion is about. Building both directions from the real list keeps the fabricated direction failing **because the apex row says pass:false**, which is what the assertion `assert "13_most_vivid_by_the_end" in joined` measures. Docstring updated to say so.

**Status: PASS.**

### 3.2 `tests/test_verifier_registry.py:308` (`_seed_six_domains`) → assertion at `:356`

**What was wrong.** Same synthetic id list, reached through `verify_final_qc` → `_seed_six_domains` → the priority-shift domain.

**Change.** The same constant, one construction site:

```python
    write_fixture(rd, "working/qc/priority_shift_report.json", {
        "schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
        "phase": "P-SHIFT-QC (order 7.5)", "pass": True,
        "items": [{"item": item_id, "pass": True, "evidence": "ok"}
                  for item_id in PRIORITY_SHIFT_ITEM_IDS],
    })
```

**Status: PASS.**

### 3.3 `tests/negative_fixtures.py:275` (`_image_domain_report`) → assertion at `tests/test_negative_fixtures.py:246`

**What was wrong.** Two independent defects in one fixture, both real:

1. `_image_domain_report` wrote `graded_by_model` but **no `author_model`** — PD-300b fails closed on a report that cannot say who wrote the files it graded.
2. `JUDGE_STAMP = "glm-5.3-flash"`, whose router-registry modality is `{}` (unknown). PD-205b/PD-300b require the grading route to be a **vision** model; an unknown modality fails, correctly.

**Change (2 hunks, one fixture, no other fixture touched).**

```python
JUDGE_STAMP = "glm-ocr"             # GLM-OCR via Ollama Cloud (registry: vision)
...
        "author_model": built_by,
```

`author_model = built_by` is the honest value: `built_by` is `WPM_STAMP`, the deck-authoring model, which is exactly the fact PD-300's field carries. `glm-ocr` is a real alias in `DEFAULT_ALIAS_REGISTRY` with `modality: "vision"` (verified by calling `_registry_capability_meta`: `{'modality': 'vision', 'context_class': 'standard'}`), and it differs from both the author stamp and the QC-specialist identity, so the positive control still exercises what it was written to exercise: an independent, vision-capable grader is clean.

**Ownership note (explicit, per the brief).** `negative_fixtures.py` is named in **PD-907's** `owned_paths` in the ledger (PD-907: `ACCEPTED`, branch `pd/fl34-approvals`). This edit is confined to the **single fixture** the retarget needs — `_image_domain_report` plus the module-level `JUDGE_STAMP` constant that fixture reads. `JUDGE_STAMP` has exactly one consumer in the whole repo (`negative_fixtures.py:275`, inside `fixture_qc_reports`); `grep -rn JUDGE_STAMP` over the repository returns 3 hits, all inside this file. Nothing beyond the one fixture was needed, so nothing beyond it was changed.

**Status: PASS.**

## 4. Mutation proofs — each retargeted assertion can still FAIL

Scratch copy of the whole `scripts/` tree at `/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-925/scripts`, with `sops/PIPELINE-MANIFEST.json` and `sops/MASTER-QC-AUTOFAIL-RULESET.md` symlinked from the branch's `universal-sops/presentation-slide-craft/` so the tree imports (the scratch copy sits outside the repo root and cannot walk up to the cluster manifest). Scratch baseline reproduces the branch exactly: **1 failed, 42 passed**.

### 4.1 Mutation 1 — assertion 1 (`:276`) goes red again

Break the fixture back to synthetic ids (the exact pre-retarget construction):

```
$ python3 -m pytest tests/test_verifier_registry.py::test_slice2_priority_shift_both_directions -q
E  AssertionError: genuine priority-shift ledger must PASS, got ['qc:priority_shift: AF-PRIORITY-SHIFT:
   ledger is missing ship-gate item ids: 0_attention_is_the_no1_job, 1_creation_mode_identified,
   2_priority_stack_named, 3_priority_shift_engineered, 4_present_cost_exposed, 5_higher_priority_lever,
   6_value_anchored_high, 7_urgency_scarcity, 8_ability_unblocked, 9_rerank_demanded, 10_trigger_fired,
   11_proclamation_hedge_free; AF-PRIORITY-SHIFT: ledger carries ids the ship gate does not define:
   item_0, item_1, item_10, item_11, item_12, item_13, item_14, item_2, item_3, item_4, item_5, item_6']
E  assert False
1 failed in 0.07s
```

Fails, naming the missing ids and the offending synthetic ids. **Assertion is live.**

### 4.2 Mutation 2 — assertion 2 (`:356`) goes red again

Break `_seed_six_domains` back to synthetic ids:

```
$ python3 -m pytest tests/test_verifier_registry.py::test_slice2_final_qc_both_directions -q
E  AssertionError: genuine aggregate must PASS, got ['qc:final: domain qc[priority_shift] does not pass:
   AF-PRIORITY-SHIFT: ledger is missing ship-gate item ids: 0_attention_is_the_no1_job, …;
   AF-PRIORITY-SHIFT: ledger carries ids the ship gate does not define: item_0, …']
E  assert False
1 failed in 0.07s
```

Fails through `verify_final_qc`. **Assertion is live.**

### 4.3 Mutations 3a and 3b — assertion 3 (`test_negative_fixtures.py:246`) goes red again

Two independent mutations, one per defect the retarget fixed. Each must red the assertion on its own, or one of the two fixes would be decorative.

**3a — remove `author_model`:**

```
$ python3 -m pytest "tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_control_clean" -q
>       assert report["domains"]["image"]["reasons"] == []
E       assert ['AF-IMAGE-QC...ail-closed).'] == []
E         Left contains one more item: "AF-IMAGE-QC-UNIT: image_qc_report.json declares no author_model —
   PD-300 writes the graded files' author model from the trusted execution stamps, so a merged report
   without it cannot prove the grader was anyone other than the author (fail-closed)."
1 failed in 0.10s
```

**3b — `JUDGE_STAMP` back to `glm-5.3-flash` (unknown modality):**

```
$ python3 -m pytest "tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_control_clean" -q
E       assert ['AF-IMAGE-QC...e behind it.'] == []
E         Left contains one more item: "AF-IMAGE-QC-UNIT: graded_by_model 'glm-5.3-flash' is not a vision
   model (registry modality 'unknown') — FIX 33 requires the image range to be graded by a model that can
   read pixels; a text model's grade of a rendered deck is a claim with no route behind it."
1 failed in 0.08s
```

Both mutations red the same assertion by the exact rule the retarget satisfies. **Assertion is live, and both fixes are load-bearing.**

After each mutation the scratch file was restored and the scratch baseline re-run: **1 failed, 42 passed** — identical to the branch.

## 5. Before and after — the two named test files, branch tip vs working tree

Target subset = `tests/test_verifier_registry.py` + `tests/test_negative_fixtures.py`, run from `23-ai-workforce-blueprint/templates/role-library/presentations/scripts` with `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`.

### 5.1 BEFORE — at `f3933631b` (branch tip, unmodified working tree)

```
$ python3 -m pytest tests/test_verifier_registry.py tests/test_negative_fixtures.py -p no:cacheprovider -q
FAILED tests/test_verifier_registry.py::test_slice2_priority_shift_both_directions
FAILED tests/test_verifier_registry.py::test_slice2_final_qc_both_directions
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_control_clean
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes
4 failed, 39 passed in 0.47s
```

Full `E` lines, verbatim:

```
E  AssertionError: genuine priority-shift ledger must PASS, got ['qc:priority_shift: AF-PRIORITY-SHIFT:
   ledger is missing ship-gate item ids: 0_attention_is_the_no1_job, 1_creation_mode_identified,
   2_priority_stack_named, 3_priority_shift_engineered, 4_present_cost_exposed, 5_higher_priority_lever,
   6_value_anchored_high, 7_urgency_scarcity, 8_ability_unblocked, 9_rerank_demanded, 10_trigger_fired,
   11_proclamation_hedge_free; AF-PRIORITY-SHIFT: ledger carries ids the ship gate does not define:
   item_0, item_1, item_10, item_11, item_12, item_13, item_14, item_2, item_3, item_4, item_5, item_6']
E  assert False                                                    # test_verifier_registry.py:276

E  AssertionError: genuine aggregate must PASS, got ['qc:final: domain qc[priority_shift] does not pass:
   AF-PRIORITY-SHIFT: ledger is missing ship-gate item ids: 0_attention_is_the_no1_job, …']
E  assert False                                                    # test_verifier_registry.py:356

E  assert ['AF-IMAGE-QC...e behind it.'] == []
E  Left contains 2 more items, first extra item: "AF-IMAGE-QC-UNIT: image_qc_report.json declares no
   author_model — PD-300 writes the graded files' author model from t...xecution stamps, so a merged
   report without it cannot prove the grader was anyone other than the author (fail-closed)."
                                                                   # test_negative_fixtures.py:246

E  assert False is True                                            # test_negative_fixtures.py:253
```

### 5.2 AFTER — at `167622602` (this commit)

```
$ python3 -m pytest tests/test_verifier_registry.py tests/test_negative_fixtures.py -p no:cacheprovider -q
FAILED tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes
1 failed, 42 passed in 0.31s
```

```
E  assert False is True                                            # test_negative_fixtures.py:253
```

### 5.3 The one remaining failure — pre-existing, different cause, NOT one of PD-925's three

`tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes` (assertion at `:253`).

Its measured blocking reasons, after this change, on the fixture `fixture_qc_reports(same_model_judge=False, full_set=True)`:

```
Priority-Shift Ship Gate (P-SHIFT-QC): AF-EXEC-STAMP: no reviewer stamp from P-SHIFT-QC covers consumed
  input renders/slide-03.png at its current sha 2b83ce4a2c6b — the input changed after the review (or was
  never reviewed by this phase); re-run P-SHIFT-QC so a fresh independent review covers the current bytes
  (PRES-042 row 2).
  … renders/slide-02.png … renders/slide-01.png … renders/slide-04.png …
```

This is `AF-EXEC-STAMP` on the **consumed upstream** renders at P-SHIFT-QC. `fixture_qc_reports`'s `_CONSUMED_STAGING` staggers the `P-SHIFT-QC` consumed entries as `working/copy/priority_shift_spec.json` + `working/copy/slides_copy.md`, but the real manifest for that phase also consumes `renders/slide-*.png` (verified: `qc_aggregate._resolve_consumes('P-SHIFT-QC')` → `['working/copy/priority_shift_spec.json', 'working/copy/slides_copy.md', 'renders/slide-*.png']`). The fixture stamps the first two through `P-PRODUCER-FIXTURE`/`exec-fixture-reviewer` and never stamps the four renders for that phase, so PRES-042 row 2 fires on all four.

PD-300b's own BUILD-REPORT §5.5 already lists this test as red at baseline for this exact reason ("(4) `AF-EXEC-STAMP` on `renders/slide-01..04.png` at P-SHIFT-QC … fixture drift that predates PD-300b on this branch"). It was red before PD-925 existed and it is red now for the same cause. Fixing it means editing the `_CONSUMED_STAGING` table — a change to a different part of the fixture that the PD-925 retarget does not need. Per the brief ("If the retarget needs anything beyond that fixture, STOP and report it instead"), it is **reported, not patched**.

## 6. Pre-existing failures named by test id

Every failure observed anywhere in this build, with its status:

| Test id | File:line | Status |
|---|---|---|
| `test_verifier_registry.py::test_slice2_priority_shift_both_directions` | `:276` | **PD-925 retarget — now PASS** |
| `test_verifier_registry.py::test_slice2_final_qc_both_directions` | `:356` | **PD-925 retarget — now PASS** |
| `test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_control_clean` | `:246` | **PD-925 retarget — now PASS** |
| `test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes` | `:253` | Pre-existing, different cause (`AF-EXEC-STAMP` on `renders/slide-01..04.png` at P-SHIFT-QC) — reported, not in PD-925's scope |
| `test_qc_aggregate.py::test_aggregate_passes_with_six_genuine_reports` | — | Pre-existing (its own local fixture, not `negative_fixtures`) — unchanged by this unit |
| `test_qc_aggregate.py::test_aggregate_writes_final_qc_report_file` | — | Pre-existing — unchanged |
| `test_qc_aggregate.py::test_cli_default_mode_exit_0_on_pass` | — | Pre-existing — unchanged |
| `test_pres042_execution_stamps.py::test_production_topology_report_plus_consumed_passes_aggregate` | `:337` | Pre-existing — unchanged |

The last four were measured on the four neighbouring test files that import the changed surfaces (`test_pd_runfacts_300b_grader_vs_author.py`, `test_pd_priority_shift_items.py`, `test_qc_aggregate.py`, `test_pres042_execution_stamps.py`), **before and after** this change, in the scratch tree with the HEAD versions of the two retargeted files swapped in:

```
BEFORE (HEAD versions of both retargeted files):  4 failed, 53 passed in 1.12s
AFTER  (this commit):                              4 failed, 53 passed in 1.02s
```

Byte-identical failure-id set — the same four named above, both runs. Zero new red, zero new green from PD-925 on that sweep.

## 7. Diff

Two files, `+33 −13`, zero assertion lines touched, zero tests skipped, zero tests deleted, zero product code touched:

```
$ git show --stat 167622602
 .../scripts/tests/negative_fixtures.py             | 13 +++++++--
 .../scripts/tests/test_verifier_registry.py        | 33 ++++++++++++++--------
 2 files changed, 33 insertions(+), 13 deletions(-)
```

- `test_verifier_registry.py`: one import (`PRIORITY_SHIFT_ITEM_IDS`), three construction sites rewritten to use it (`fabricate`, `genuine`, `_seed_six_domains`), two docstrings updated to state why.
- `negative_fixtures.py`: `JUDGE_STAMP` value change with the reason in a comment above it, one new `author_model` key in `_image_domain_report`, one docstring bullet stating what `author_model` is.

## 8. Commit, push, remote proof

```
$ git commit
167622602545de863f0a6d7838a7f3c98b8b4548
PD-925: retarget the three fixtures PD-300b's rule broke

$ git push origin pd/fl35-sealed-record--hold-d23-d24
To https://github.com/trevorotts1/openclaw-onboarding.git
   f3933631b..167622602  pd/fl35-sealed-record--hold-d23-d24 -> pd/fl35-sealed-record--hold-d23-d24

$ git rev-parse HEAD
167622602545de863f0a6d7838a7f3c98b8b4548
$ git ls-remote origin refs/heads/pd/fl35-sealed-record--hold-d23-d24 | cut -f1
167622602545de863f0a6d7838a7f3c98b8b4548
MATCH
```

## 9. What was NOT done, and why

- **No assertion deleted, weakened, flipped or silenced.** Proven by `git diff -U0 | grep -E '^[+-].*assert'` returning empty.
- **No product code touched.** `qc_aggregate.py`, `verifier_registry.py`, `presentation_job/runfacts.py` and `runfacts.verify_priority_shift` are unchanged. PD-300b's rules stay exactly as PD-300b wrote them; the fixtures moved to meet them.
- **Nothing outside the room.** No other lane's branch, worktree, PR, ledger or folder was read, edited, merged or touched. `pd/fl35-sealed-record` (the parent), `pd/fl34-approvals` (PD-907's branch) and every other lane were not opened.
- **No merge to main, no push to main, no client box, no live system, no paid call.**
- **`test_independent_judge_full_set_passes` left red** with its cause named in §5.3. Its fix lives in `_CONSUMED_STAGING`, outside the single fixture PD-925 needed.
