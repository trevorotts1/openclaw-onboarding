# PD-097 — The priority-shift ledger stops inventing per-slide verdicts and never overwrites the step's own report

- Repo: `trevorotts1/openclaw-onboarding` · Branch `pd/fl15-renderer` (lane FL15) · Wave 2
- Builder: deepseek-chain
- Depends on: PD-218a (ACCEPTED on this branch at `5dc81e96e`) and PD-304
  (head `3b9cb6884cc858ef4a61bf56c137d521975c63ad` on `pd/fl18-dispatcher`, phase **IN_BATCH**,
  not yet on `main` — so it is a cross-lane dependency, merged only in the throwaway
  integration tree, never pushed by this unit)
- Acceptance row run: **A1** (plus the binding amendment (d))

## 0. Row taken from the gate, and branch state proved before editing

```
$ python3 -I .../FINAL/scripts/step_gate.py ready --control /Volumes/mac mini m4/swarm-contract/loop-control/pd-fix
{"ready": [], "waiting": {..., "PD-111": ["waits for PD-097 (BUILDING)", "branch pd/fl15-renderer is busy"], ...}, "count": 0}
```

`ready` was empty because PD-097 is already `BUILDING` (dispatched to this builder, note in
`ledger.json`: "build dispatched deepseek-chain in wf_c908f1d6-dbb at 2026-11-13 10:47:12 EST").
The ledger row names the unit, not a guess:

```
id PD-097 | lane FL15 | branch pd/fl15-renderer
owned_paths: .../scripts/build_deck.py, .../scripts/presentation_job/motion.py,
             .../scripts/tests/test_pd046_style_lock.py, .../scripts/tests/test_pd_render_*.py,
             .../scripts/tests/test_pd089_value_stack_band.py
acceptance_rows: ["A1"] | phase BUILDING
```

Branch proved with `git ls-remote --heads`, and the refs/heads/main control was run too:

```
$ git ls-remote --heads origin pd/fl15-renderer
5dc81e96e054a373c1558fea1c015f573c5581e6	refs/heads/pd/fl15-renderer
$ git ls-remote --heads origin refs/heads/main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
```

**Discrepancy, stated in full:** the lane worktree
(`/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL15`) was checked out at
`fde9282bb6c33c73363ec0baeea63b75a968b7f2` ("PD-070: a failed slide is retried inside the batch"),
which is **not** an ancestor of the remote head (`git merge-base --is-ancestor 5dc81e9 HEAD` → NO).
After `git fetch origin --prune` the branch is present at `5dc81e96e`. I did **not** edit, commit,
checkout, reset or clean the lane clone; every write of this unit happened in a fresh detached
worktree cut from `origin/pd/fl15-renderer` = `5dc81e96e`.

```
$ S=$(mktemp -d -p "$TMPDIR" work.XXXXXX)   # $TMPDIR = .../loop-control/pd-fix/tmp/PD-097
$ git worktree add --detach "$S/wt" origin/pd/fl15-renderer
HEAD is now at 5dc81e96e PD-218a: report records the repo-wide sweep as abandoned, not clean
```

## 1. Spec quoted (binding text implemented)

> ### PD-097 — The priority-shift ledger stops inventing per-slide verdicts and never overwrites the step's own report
>
> | Quality control (finds and fixes) | suggested opus-chain at thinking level high (data-loss risk) |
> | Lane and repository | FL15 · trevorotts1/openclaw-onboarding |
> | Wave | 2 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-218a, PD-304 |
> | Live-action flag | none: files and stubbed tests only |
> | Acceptance rows the checker must run | A1 |
>
> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> This unit was PD-213; it is the code repair finding PD-097 asked for. (a) Two writers, one file:
> on a retry or resume this function writes `working/qc/priority_shift_report.json`, the same file
> the engine dispatches the P-SHIFT-QC agent to write (PD-304 gives that agent its contract). After
> this unit the function never overwrites a report that already carries
> `schema: "priority_shift_report/v1"`: it validates that report against the one shape in section
> 1.3 of this specification and returns the failure text when it is invalid. It writes the file
> itself only when none exists, and what it writes is that same shape. (b) Row count and ids:
> replace the function's literal item ids with an import of `PRIORITY_SHIFT_ITEM_IDS` and
> `PRIORITY_SHIFT_ID_KEY` from `presentation_job/priority_shift_items.py` (created by PD-304 with
> the ids this function writes today, so no id changes). The function writes 15 item rows at the
> reviewed commit; the doctrine names 14, and two doctrine items ("Vision sold", "Value established
> and seen before price") are absent from the code. Keep the code's ids, list the difference in the
> report, and change no doctrine text (decision D-41). (c) Four rows pass when a marker word appears
> anywhere in the copy file; list those four in the report with their lines. Do not change them in
> this unit. (d) Extra acceptance row: the file this function writes on a fixture run passes
> `runfacts.verify_priority_shift` when every item passes, and fails it when one item fails (paste
> both).
>
> **Carried-over unit text (from `PASS5-GATES.md`, section PD-213; ids, decisions and lanes already converted to final):**
>
> - **Change:** first, on a scratch run, establish which code writes `working/qc/priority_shift_report.json` on an engine run and paste the result in the report. Then: (1) in `_chk_priority_shift_ledger` remove the per-slide rows (lines 11076–11086) and write `"per_slide": "not applicable — 14-item deck-level checklist"`. (2) Read `_qc_slide_floor` (lines 4478–4515) and make the per-slide verdict floor not apply to a report whose `gate` is `AF-PRIORITY-SHIFT`; change nothing else in that function. (3) Correct the docstring to say where the function is and is not called.
> - **Acceptance:** a doctrine-active scratch run with renders → the written report has 15 item rows and no slide rows, and the report-substance check does not reject it for too few per-slide verdicts.

The one shape, quoted from `01-BUILD-SPEC.md` section 1.3 (the shape the check accepts):

> ```json
> {
>   "schema": "priority_shift_report/v1",
>   "pass": true,
>   "items": [
>     { "<PRIORITY_SHIFT_ID_KEY>": "<an id from PRIORITY_SHIFT_ITEM_IDS>", "pass": true, "evidence": "<quoted text from the deck>" }
>   ]
> }
> ```
>
> `items` holds exactly one row per id in `PRIORITY_SHIFT_ITEM_IDS`: none missing, none extra, none
> twice. ... Other keys the writer adds today (for example `gate`, or PD-097's `per_slide` note) are
> allowed and ignored.
>
> - **One writer at a time.** The P-SHIFT-QC agent writes the file. `_chk_priority_shift_ledger`
>   writes it only when no file exists, and otherwise validates the existing one against this shape
>   (PD-097). It never overwrites a report that carries the schema.

## 2. Files changed

| File | Change | Commit |
|---|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py` | `_qc_slide_floor` waiver; new `_priority_shift_report_shape_problems`; `_chk_priority_shift_ledger` docstring, id import, 15 deck-level rows, `per_slide` note, no-overwrite + validate | `3b57687be` |
| `.../scripts/tests/test_pd_render_priority_shift_ledger.py` | new test file, 5 tests for A1 (+ amendment (d)) | `3b57687be` |
| `evidence/PD-097/BUILD-REPORT.md` | this report | this commit |

No file outside the unit's owned paths was touched. `tests/test_pd046_style_lock.py`,
`tests/test_pd089_value_stack_band.py` and `presentation_job/motion.py` are lane-owned but not
needed here and were left alone. `tests/test_slice1_gates.py` was briefly edited during the build
and **reverted** (`git checkout --`) once it was proved to assert the *other* writer's shape — see
section 8.

## 3. Engine-run writer, established (amendment "first, on a scratch run")

Probe (`probe_writer.py`, run from the scripts dir against a fixture run dir):
doctrine spec `{}`, `intake.json {"pitch_included": true}`, `slides_copy.md`, `arc_allocation.json`,
three `renders/slide-0N.png`; then `s1.run_gate("slice1:priority_shift_ledger", rd)`; then delete the
file and call `bd._chk_priority_shift_ledger(rd)` directly.

```
engine gate slice1:priority_shift_ledger -> False ['AF-PRIORITY-SHIFT: the 14-item priority-shift ship gate failed on 0_attention..., 14_one_promise...']
after ENGINE RUN   : keys = ['gate', 'generated_at', 'items', 'pass', 'phase', 'schema', 'slides'] | slides rows = 3 | per_slide key = False
legacy build_deck  : returned 'AF-PRIORITY-SHIFT: the 14-item priority-shift ship gate fail'
after DIRECT CALL  : keys = ['gate', 'generated_at', 'items', 'pass', 'per_slide', 'phase', 'schema'] | slides rows = 0 | per_slide key = True
```

**Answer: on the engine gate path the file is written by `slice1_gate_verifiers.v_priority_shift_ledger`**
(the new verifier runs during the seal and writes; `build_deck._chk_priority_shift_ledger` is the
legacy/shadow side and, after this unit, sees a schema-carrying report and leaves it alone).
`run_preflight()` calls `_chk_priority_shift_ledger` before any render, so on that path it returns
`""` and writes nothing. The P-SHIFT-QC step check (`runfacts.verify_priority_shift`) only reads the
file. That third writer is **not** an owned path of this unit — see section 8, overlap 1.

## 4. Each acceptance row proven (real output, by test id)

Commands (integration tree `$S/integ` = `origin/pd/fl15-renderer` + merge of `origin/pd/fl18-dispatcher`
(PD-304); never pushed). Python is `python3 -I`; all writes go to the scratch TMPDIR; no network.

```
$ cd "$S/integ/23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
$ python3 -I -m pytest tests/test_pd_render_priority_shift_ledger.py -v
tests/test_pd_render_priority_shift_ledger.py::test_a1_report_is_15_deck_level_rows_and_clears_the_substance_floor PASSED
tests/test_pd_render_priority_shift_ledger.py::test_a1_written_file_passes_verify_priority_shift PASSED
tests/test_pd_render_priority_shift_ledger.py::test_a1_one_failing_item_fails_verify_priority_shift PASSED
tests/test_pd_render_priority_shift_ledger.py::test_a1_existing_agent_report_is_never_overwritten PASSED
tests/test_pd_render_priority_shift_ledger.py::test_a1_invalid_existing_report_is_named_not_overwritten PASSED
5 passed
```

| # | Acceptance clause | Test id | Head |
|---|---|---|---|
| A1.1 | doctrine-active run with renders → 15 item rows, ids = `PRIORITY_SHIFT_ITEM_IDS` in order | `::test_a1_report_is_15_deck_level_rows_and_clears_the_substance_floor` | PASS |
| A1.2 | no slide rows; `per_slide` note present | same test (`"slides" not in obj`, note equality) | PASS |
| A1.3 | report-substance check does not reject for too few per-slide verdicts (34-slide deck → old floor 20) | same test (`_qc_slide_floor == 0`, `check_qc_phase_report_real("P-SHIFT-QC") == ""`) | PASS |
| A1.4 | (d) written file passes `runfacts.verify_priority_shift` with every item passing | `::test_a1_written_file_passes_verify_priority_shift` (`Verdict.PASS`, detail "…15 item rows passing") | PASS |
| A1.5 | (d) fails `runfacts.verify_priority_shift` when one item fails, naming it | `::test_a1_one_failing_item_fails_verify_priority_shift` (`Verdict.FAIL`, `5_higher_priority_lever` in detail) | PASS |
| A1.6 | two writers: an existing schema report is never overwritten | `::test_a1_existing_agent_report_is_never_overwritten` (report bytes identical) | PASS |
| A1.7 | an existing report that does not match the shape is named, not clobbered | `::test_a1_invalid_existing_report_is_named_not_overwritten` (`missing ids`, `14_one_promise…` named, bytes identical) | PASS |

### At the base commit (same fixture, same integration base, before this unit)

```
$ cd "$S/base/..."   # origin/pd/fl15-renderer + origin/pd/fl18-dispatcher, no PD-097 change
$ python3 -I -m pytest tests/test_pd_render_priority_shift_ledger.py -q
FAILED ::test_a1_report_is_15_deck_level_rows_and_clears_the_substance_floor
FAILED ::test_a1_existing_agent_report_is_never_overwritten
FAILED ::test_a1_invalid_existing_report_is_named_not_overwritten
3 failed, 2 passed
```

A1.4 and A1.5 pass at base as well — they assert a property the old writer already had
(its report is gradeable by `runfacts`); they are kept because amendment (d) requires the pair to be
pasted, not because this unit introduces them. The three failing rows at base are the change.

## 5. Mutation proof (neutralise → RED → restore → GREEN)

**M1 — remove the no-overwrite guard** (one line: `if isinstance(existing, …)` → `if False:`):

```
$ python3 -I -m pytest tests/test_pd_render_priority_shift_ledger.py -q
FAILED ::test_a1_existing_agent_report_is_never_overwritten
FAILED ::test_a1_invalid_existing_report_is_named_not_overwritten
2 failed, 3 passed
```

**M2 — put the per-slide rows back** (one line: `"per_slide": "not applicable — …"` →
`"slides": [{"slide": s, "pass": True} for s in range(1, 4)]`):

```
FAILED ::test_a1_report_is_15_deck_level_rows_and_clears_the_substance_floor
1 failed, 4 passed
```

**Restore** (copy the committed file back, `grep -c MUTATION build_deck.py` → 0):

```
$ python3 -I -m pytest tests/test_pd_render_priority_shift_ledger.py -q
5 passed
```

## 6. Wider affected suite, base vs head (both counts)

Same file set, same integration base, run once against the base tree and once against head+this unit:

| Tree | Command | Result |
|---|---|---|
| base (lane head + PD-304) | `pytest tests/test_slice1_gates.py tests/test_fix103_deck_size_floors.py tests/test_pd151_render_dependent_gates.py tests/test_qc_aggregate.py tests/test_pres042_execution_stamps.py tests/test_verifier_registry.py tests/test_presentation_job.py test_fix2_qc_unskippable.py test_runfacts.py test_preflight.py -q` | **8 failed, 260 passed** |
| head (+ `3b57687be`) | same, plus `tests/test_pd_render_priority_shift_ledger.py` | **8 failed, 265 passed** |

The 8 failures are the same 8 in both runs, so they are pre-existing and proved at base:

```
tests/test_fix103_deck_size_floors.py::test_prompt_floor_untouched
tests/test_qc_aggregate.py::test_aggregate_passes_with_six_genuine_reports
tests/test_qc_aggregate.py::test_aggregate_writes_final_qc_report_file
tests/test_qc_aggregate.py::test_cli_default_mode_exit_0_on_pass
tests/test_pres042_execution_stamps.py::test_production_topology_report_plus_consumed_passes_aggregate
tests/test_presentation_job.py::TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done
test_fix2_qc_unskippable.py::test_qc_phase_skip_record_refused_in_load_skip_approvals
test_fix2_qc_unskippable.py::test_real_report_attests_for_all_four_qc_phases
```

Head − base = +5 passed = exactly the new file. No test that passed at base fails at head.

## 7. Hunk attribution (`git show 3b57687be -- build_deck.py`, 129 insertions / 64 deletions)

| Hunk | Line (head) | Belongs to |
|---|---|---|
| `_qc_slide_floor`: `if report_obj.get("gate") == "AF-PRIORITY-SHIFT": return 0` + docstring | 4600–4620 | PD-097 carried-over (2) |
| new `_priority_shift_report_shape_problems` | 11235–11267 | PD-097 amendment (a) |
| `_chk_priority_shift_ledger` docstring rewrite (where called / not called, two writers) | 11270–11301 | PD-097 carried-over (3) |
| lazy import of `PRIORITY_SHIFT_ID_KEY` / `PRIORITY_SHIFT_ITEM_IDS` + 15-id guard | 11307–11323 | PD-097 amendment (b) |
| the 15 `add(ITEM[n], …)` rows | 11325–11356 | PD-097 amendment (b) — ids only, no check changed |
| `per_slide` note, removal of the per-slide loop + `slides` key | 11358–11374 | PD-097 carried-over (1) |
| validate-or-write block (never overwrite a schema report) | 11375–11395 | PD-097 amendment (a) |

The test file is 184 added lines, new, no existing test key removed.

Four rows that pass on a marker word anywhere in the copy file (amendment (c), **not changed**):

| Row id | Line (head) | Rule |
|---|---|---|
| `4_present_cost_exposed` | `build_deck.py:11335` | `_first_marker_offset(text, COST_OF_INACTION_MARKERS)` |
| `6_value_anchored_high` | `build_deck.py:11341` | `_first_marker_offset(text, ("anchor", "value-stack", "value_stack", "value add"))` |
| `7_urgency_scarcity` | `build_deck.py:11344` | `_first_marker_offset(text, URGENCY_SCARCITY_MARKERS)` (skipped for a pitchless deck) |
| `8_ability_unblocked` | `build_deck.py:11347` | `_first_marker_offset(text, ABILITY_UNBLOCK_MARKERS)` (skipped for a pitchless deck) |

Id-count difference kept, per decision D-41: the code writes **15** ids (item 0,
`0_attention_is_the_no1_job`, through `14_one_promise_one_wow_one_demonstration`); the doctrine names
**14**. Two doctrine items are absent from the code: **"Vision sold"** and **"Value established and
seen before price"**. No doctrine text was changed by this unit.

## 8. Remote head proof

```
$ git ls-remote --heads origin pd/fl15-renderer      # before the push
5dc81e96e054a373c1558fea1c015f573c5581e6	refs/heads/pd/fl15-renderer
$ git push origin HEAD:refs/heads/pd/fl15-renderer
   5dc81e96e..3b57687be  HEAD -> pd/fl15-renderer
```

After the report commit the head is re-proved at the end of this file (section 10).

## 9. Honest unproved / overlap

1. **Overlap — second writer left untouched, by design.** `slice1_gate_verifiers.py`
   `v_priority_shift_ledger` (lines ~806–905) is a **third** writer: it keeps its own literal copy of
   the 15 ids and its own `slides` per-slide rows, and on the engine gate path it writes the file
   *first* (inside the seal) so `build_deck` correctly refuses to overwrite it. The file therefore
   still carries per-slide rows when produced by that path. `slice1_gate_verifiers.py` is **not** an
   owned path of PD-097, so it was not edited; this is a named dependency for the FL15/FL18 owner
   (and for PD-300b, which owns the exact-ids rule on the step check). The A1 clause "the written
   report has 15 item rows and no slide rows" is proved for the writer this unit owns
   (`_chk_priority_shift_ledger`), and the probe in section 3 is the evidence for the other one.
2. **Cross-lane dependency.** `presentation_job/priority_shift_items.py` exists only on PD-304's
   branch (`pd/fl18-dispatcher`, phase IN_BATCH), not on `main` and not on this lane branch. On the
   branch **alone** the new test file cannot even collect
   (`ModuleNotFoundError: No module named 'presentation_job.priority_shift_items'`) and
   `tests/test_slice1_gates.py::test_slice1_priority_shift_ledger_both_directions` fails 1 of 30
   because the genuine direction receives the named fail-closed message. With PD-304 merged (the
   prescribed cross-lane method, `01-BUILD-SPEC` section 1.2) that file is 30/30 and the new file is
   5/5. PD-304 must land in the same batch as this unit.
3. **Verdict source when a valid report already exists.** The function validates the existing report
   and never writes, but it returns **its own** fresh measurement, not the existing report's `pass`
   flag. That keeps the existing `both_directions` contract (fabricate writes a failing report, the
   genuine pass must then return `""`) intact. A hand-crafted run dir could therefore hold a valid
   but stale failing report while the step returns `""`; the step check reads the file and would fail
   such a run. Not observed on any real path (both writers measure the same inputs); recorded here
   rather than hidden.
4. **Report-substance floor waiver is by gate name.** `_qc_slide_floor` returns 0 whenever the report
   object it is handed has `"gate": "AF-PRIORITY-SHIFT"` — a report could claim that gate name to
   skip the per-slide floor. That is the same trust level the rest of the report floor has (it reads
   the report it is judging) and the priority-shift rows are independently graded by
   `runfacts.verify_priority_shift`; named, not fixed here (out of this unit's scope).
5. **Not run:** no live engine run, no paid service, no network. Everything above is fixture-driven
   pytest and one probe script, as the unit's live-action flag allows.
## 10. Final head proof

```
$ git ls-remote --heads origin pd/fl15-renderer
e04e7de8fc62acec9a442cc1f78971dc254bc8f9	refs/heads/pd/fl15-renderer
$ git rev-parse HEAD
e04e7de8fc62acec9a442cc1f78971dc254bc8f9
```

Unit commit `3b57687be` (code + tests), report commit `e04e7de8f`. Fast-forward only: the push
was `5dc81e96e..3b57687be` then `3b57687be..e04e7de8f`; no rebase, no force-push, `main` never
written.
