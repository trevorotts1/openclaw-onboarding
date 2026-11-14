# PD-111 — A QC report is not rejected for words in a reviewer's note

- Repo: `trevorotts1/openclaw-onboarding` · Branch `pd/fl15-renderer` (lane FL15) · Wave 3
- Builder: deepseek-chain
- Depends on: PD-097, ACCEPTED on this branch (base commit below)
- Acceptance rows run: **A1, A2, A3**
- Build base: `70bc3121624bc957f0f0b87b3ca45ce21a7d1a79`
- Build head: `165a8b0f0eeca69c206294aa2067e60800120dd1`

## 0. Row from the gate, and branch proved before editing

```
$ python3 -I .../FINAL/scripts/step_gate.py ready --control .../loop-control/pd-fix
{ "ready": [
    {"id": "PD-081", ...},
    {"id": "PD-111", "kind": "build", "lane": "FL15",
     "branch": "pd/fl15-renderer", "builder": "deepseek-chain",
     "qc": "opus-chain", "qc_thinking": "high",
     "severity": "Moderate"}, ... ],
  "waiting": { "PD-210": ["waits for PD-111 (READY)"], ... },
  "count": 4 }
```

Branch proved, with the `refs/heads/main` control run in the same call pair:

```
$ git ls-remote --heads origin 'refs/heads/pd/fl15-renderer'
70bc3121624bc957f0f0b87b3ca45ce21a7d1a79	refs/heads/pd/fl15-renderer
$ git ls-remote --heads origin 'refs/heads/main'
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
```

Ledger row (read from `ledger.json`, not from memory) names the unit:

```
id PD-111 | lane FL15 | branch pd/fl15-renderer | phase READY | wave 3
owned_paths: scripts/build_deck.py, scripts/presentation_job/motion.py,
             scripts/tests/test_pd046_style_lock.py, scripts/tests/test_pd_render_*.py,
             scripts/tests/test_pd089_value_stack_band.py
acceptance_rows: ["A1", "A2", "A3"]
```

## 1. Spec quoted (binding text implemented)

> **Change (`build_deck.py`, `QC_FOREIGN_SIGNATURES` at lines 4376-4382 and the function
> that applies it):** match the signatures only against the report's key names (at any
> depth) and against the string value of a top-level `generator` field. Never match them
> against free-text values such as notes, reasons, findings or fixes.
>
> **Acceptance:** (A1) a report whose reviewer note says "do not overlay the headline;
> re-prompt" is not rejected for that text. (A2) a report that has a key named
> `overlay_readiness` is still rejected. (A3) a report with
> `"generator": "post-production overlay tool"` is still rejected.

## 2. Discrepancies, stated in full

1. **Line numbers drifted.** The spec cites `QC_FOREIGN_SIGNATURES` at lines 4376-4382.
   At the build base it is at **4498-4504**; the applying function
   `_qc_report_substance_problems` is at **4507**. No other definition exists in the file
   (`grep -n QC_FOREIGN_SIGNATURES` → 603 comment, 4498 definition, 4523 use, 6342 and
   11914 comments).
2. **The lane clone was stale, not dirty.** `pd-fix/clones/onboarding` has
   `pd/fl15-renderer` checked out at `fde9282bb6c33c73363ec0baeea63b75a968b7f2`
   ("PD-070: a failed slide is retried inside the batch"), which is **9 commits behind**
   origin and is its **ancestor**
   (`git merge-base --is-ancestor 70bc312 fde9282` → NO; `git merge-base` → `fde9282`;
   `git rev-list --left-right --count 70bc312...fde9282` → `9  0`). Origin tip carries
   the PD-097 work this unit depends on. The lane clone was **not** edited, fetched into
   its worktree, checked out, reset or cleaned — `git status --porcelain` on it was empty
   before and after. Every write of this unit happened in its own clone cut from GitHub
   at `pd/fl15-renderer`.
3. **Pre-existing breakage on the branch head, unrelated to this unit.**
   `presentation_job/priority_shift_items.py` is **absent** at `70bc312`
   (`git ls-tree -r --name-only 70bc312 | grep priority_shift_items` → no lines) while
   `tests/test_pd_render_priority_shift_ledger.py:30` imports it → collection ERROR on
   base and head alike. Not fixed here: it belongs to PD-097's own files.
4. **Pre-existing failures, identical both sides.** `tests/test_qc_aggregate.py` fails 3
   tests (362 `AssertionError`) at base and at head with the same three names.

## 3. Implementation

`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`

Before — the whole report was serialised and each signature matched against that blob:

```python
    problems = []
    try:
        blob = json.dumps(obj, default=str).lower()
    except Exception:  # noqa: BLE001
        blob = ""
    for sig in QC_FOREIGN_SIGNATURES:
        if sig in blob:
```

After — a new helper returns the only text a signature may match (every key name at any
depth, plus a top-level `generator` string), and the loop reads it:

```python
def _qc_foreign_signature_text(obj) -> str:
    """The only text a foreign-generator signature may match: every KEY NAME at any
    depth, plus the string value of a top-level `generator` field. Free-text values
    (notes, reasons, findings, fixes) are deliberately excluded — a reviewer writing
    "do not overlay the headline; re-prompt" is describing the report, not signing it.
    Lowercased; depth-capped so a pathological/cyclic report cannot recurse forever."""
    parts = []

    def walk(node, depth):
        if depth > 32:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                parts.append(str(k))
                walk(v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v, depth + 1)

    walk(obj, 0)
    if isinstance(obj, dict):
        gen = obj.get("generator")
        if isinstance(gen, str):
            parts.append(gen)
    return "\n".join(parts).lower()
```

```python
    problems = []
    sig_text = _qc_foreign_signature_text(obj)
    for sig in QC_FOREIGN_SIGNATURES:
        if sig in sig_text:
```

The module comment above `QC_FOREIGN_SIGNATURES` and the
`_qc_report_substance_problems` docstring both said "matched against the whole report
JSON blob"; both now state the key-name / `generator` rule.

Single implementation, no second copy: `presentation_job/runfacts.py:637` calls
`_bd._qc_report_substance_problems`, and `presentation_job/dispatcher.py:1239` only
mentions it in a prompt comment. `grep -rn QC_FOREIGN_SIGNATURES` finds no other matcher.

Score-consistency teeth, the caller gates and every other branch of
`_qc_report_substance_problems` are untouched.

## 4. Rows — real output

Probe run against the branch code, same script before and after the change.

**Before (base behaviour):**

```
A1_note_prose: REJECT ["report bears a corrupt/foreign QC-generator signature
  ('overlay the headline') — ..."]
A2_key_overlay_readiness: REJECT [('... overlay_readiness ...')]
A3_generator_overlay: REJECT [('... post-production overlay ...')]
```

**After:**

```
A1_note_prose: ACCEPT []
A2_key_overlay_readiness: REJECT ["report bears a corrupt/foreign QC-generator
  signature ('overlay_readiness') — ..."]
A3_generator_overlay: REJECT ["report bears a corrupt/foreign QC-generator
  signature ('post-production overlay') — ..."]
```

The committed test runs the real gate (`_qc_report_gate`) as well as the helper:

```
$ python3 -m pytest tests/test_pd_render_qc_foreign_signature.py -q -p no:cacheprovider
......                                                                   [100%]
6 passed in 0.06s
```

| Row | Test | Result |
|---|---|---|
| A1 | `test_a1_reviewer_note_prose_is_not_a_foreign_signature` (asserts the phrase IS in the blob, then that the gate returns `""`) | PASS |
| A1 | `test_a1_free_text_at_depth_is_also_ignored` | PASS |
| A2 | `test_a2_key_named_overlay_readiness_is_still_rejected` (gate names the signature) | PASS |
| A2 | `test_a2b_nested_key_name_is_still_rejected` | PASS |
| A3 | `test_a3_generator_field_is_still_rejected` (gate names the signature) | PASS |
| A3 | `test_a3b_generator_is_matched_case_insensitively` | PASS |

Test file: `tests/test_pd_render_qc_foreign_signature.py` — kept inside the lane's
`test_pd_render_*.py` owned glob (commit `165a8b0f0`, a rename-only follow-up).

## 5. Mutation — RED then GREEN

Mutation applied to the shipped code: `sig_text = json.dumps(obj, default=str).lower()`
(the old whole-blob match), everything else unchanged.

```
$ python3 -m pytest tests/test_pd_render_qc_foreign_signature.py -q
2 failed, 4 passed in 0.12s
FAILED ...::test_a1_reviewer_note_prose_is_not_a_foreign_signature
FAILED ...::test_a1_free_text_at_depth_is_also_ignored
```

Exactly the two A1 rows go red; A2/A3 stay green because key-name and `generator`
matching is common to both implementations — that is the discriminator working.

Restored from the pre-mutation snapshot (sha256
`50a936e660b14ac023d52fa23a99a56550ced98fbe989f6f7612ead6ae324233`):

```
$ python3 -m pytest tests/test_pd_render_qc_foreign_signature.py -q
6 passed in 0.15s
$ grep -c MUTATION build_deck.py
0
```

## 6. Wider suite — base and head, counts

Same interpreter, same flags, same file lists on both sides.

**QC-gate files** (`test_qc_gate_teeth.py`, `test_fix36_registry_parity_cand17.py`,
`test_qc_aggregate.py`; head adds this unit's test):

```
base: 3 failed, 35 passed in 1.91s
head: 3 failed, 41 passed in 1.18s     (+6 = this unit's rows)
```

**Lane subset** (all `tests/*qc*.py`, all `tests/test_pd_render_*.py`):

```
base: 3 failed, 83 passed, 1 error in 21.34s
head: 3 failed, 89 passed, 1 error in 22.65s
```

Identical failure and error names on both sides:
`test_qc_aggregate.py::test_aggregate_passes_with_six_genuine_reports`,
`::test_aggregate_writes_final_qc_report_file`, `::test_cli_default_mode_exit_0_on_pass`,
and `ERROR tests/test_pd_render_priority_shift_ledger.py` (discrepancy 3).

**Whole `tests/` directory** (272 files, `--continue-on-collection-errors`):

```
base 70bc312: 194 failed, 3729 passed, 12 skipped, 4 warnings, 1 error in 817.44s
head 165a8b0 : see §6a
```

## 6a. Whole-directory head run

Run against `165a8b0f0` with the same command as the base run. The box was carrying a
sibling lane's own full suite (PD-105) at load average 33-44 during this window, so the
head run was started under that contention and its wall-clock is not comparable to the
base run's.

```
HEAD_FULL_SUITE_PENDING
```

## 7. Push proof

```
$ git push origin HEAD:refs/heads/pd/fl15-renderer
   70bc31216..a6a72d0ee  HEAD -> pd/fl15-renderer
   a6a72d0ee..165a8b0f0  HEAD -> pd/fl15-renderer

$ git rev-parse HEAD
165a8b0f0eeca69c206294aa2067e60800120dd1
$ git ls-remote --heads origin 'refs/heads/pd/fl15-renderer'
165a8b0f0eeca69c206294aa2067e60800120dd1	refs/heads/pd/fl15-renderer
```

Fast-forward only. No rebase, no force-push, no `--force-with-lease`.

## 8. Overlap with sibling units

- **None.** `build_deck.py` had exactly one other writer window in this lane, and
  PD-210 — the only FL15 unit that names this file next — **depends on PD-111** and was
  `waiting` in the gate output above. It was not started.
- The other three READY units (PD-081 FL21, PD-105 FL17, PD-316b FL33) are on other
  branches and other files.
- **Adjacent finding, not touched (outside this unit's named change):**
  `qc_generator_guard.py` carries `_CORRUPT_REPORT_PATTERNS`, a plain text scan of an
  emitted `*_qc_report.json` ("text scan — JSON or not"). It still flags a report whose
  free text quotes e.g. `typography_overlay_readiness`. That is the same class of bug as
  PD-111 but in a different module the unit text does not name; the owning unit should
  decide.
- **Documentation drift, not touched:** `sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md`
  row `AF-COPY-QC` says the check "scans QC_FOREIGN_SIGNATURES ... in the report JSON".
  Still true of keys and `generator`, no longer true of free text. Out of the named
  change.

## 9. Files changed

```
23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py
23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_render_qc_foreign_signature.py  (new)
evidence/PD-111/BUILD-REPORT.md  (this file)
```
