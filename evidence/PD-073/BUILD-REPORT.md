# PD-073 — BUILD REPORT (deepseek-chain, build worker; no verdict)

Unit PD-073 · repo `trevorotts1/openclaw-onboarding` · branch `pd/fl15-renderer`
Lane clone (read-only, left clean): `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL15`
Build worktree (throw-away): `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-073/pd073.9pQq8m/wt`
Base comparison worktree: `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-073/pd073.9pQq8m/base`
Everything is under `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-073` created by this worker; every scratch dir came from `mktemp -p "$TMPDIR" -d`.

Branch confirmed live before any work:

```
$ git ls-remote --heads origin refs/heads/pd/fl15-renderer
fde9282bb6c33c73363ec0baeea63b75a968b7f2	refs/heads/pd/fl15-renderer
```

---

## 1. Spec quoted (binding text implemented)

From `.../fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`, section `### PD-073`:

> **PD-073 — Remove the pass-by-not-running branches in the renderer**
>
> Findings PD-073 · Severity Moderate · Builder deepseek-chain · Lane and repository FL15 · trevorotts1/openclaw-onboarding · Wave 3 · Depends on (must be ACCEPTED) PD-070 · Critical first no · Live-action flag none: files and stubbed tests only · **Acceptance rows the checker must run: A1**
>
> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> The same class of branch in `dispatcher._verify_single_prompt` (lines 3424-3432) is fixed inside PD-065 (lane FL18). `_gov_acquire` (lines 1742-1745) proceeding unthrottled on a poll-side error is left as it is; list it in the report as a known by-design proceed.
>
> **Carried-over unit text:**
>
> - **Change:** `_canonical_prompt_dir_problems` and `_verify_aspect_and_readback`: when `prompt_gate` cannot be imported, fail with a named reason unless `_degraded_allowed`-style test markers are present (reuse the rule in `phase_verifiers._degraded_allowed`; do not weaken it).
> - **Acceptance:** with the import forced to fail and no test marker → failure naming the missing module; with the marker → the current behavior.

What I implemented, clause by clause:

| Spec clause | Implementation |
|---|---|
| "when `prompt_gate` cannot be imported, fail with a named reason" (`_canonical_prompt_dir_problems`) | `pg is None` now returns one problem string: `prompt_gate: module unavailable — cannot judge <dir> for duplicate or non-canonical prompt names (the directory detector never ran; PD-073)` |
| same, `_verify_aspect_and_readback` | `pg is None` now `raise RuntimeError("slide N: prompt_gate module unavailable — cannot verify the 16:9/2K aspect pin or the OCR text readback ... A check that never ran is not a pass (PD-073).")` |
| "unless `_degraded_allowed`-style test markers are present" | new `build_deck._degraded_allowed(run_dir)` that **delegates to `phase_verifiers._degraded_allowed`** (single rule, not a copy); if that rule itself cannot be loaded it returns `False` — fail closed |
| "do not weaken it" | no new env var, no new marker, no extra escape hatch; the only accepted markers are the three `phase_verifiers` already honours (`PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1`, `CI`/`OPENCLAW_TEST`, run-dir `working/checkpoints/.test-context`) |
| "the current behavior" with the marker | marker present → `_canonical_prompt_dir_problems` returns `[]`, `_verify_aspect_and_readback` returns `None` — byte-for-byte the pre-change behaviour |
| `_gov_acquire` (1742-1745) left alone, listed as by-design | untouched; see §9 |
| `dispatcher._verify_single_prompt` (3424-3432) is PD-065/FL18 | untouched; verified still present and unchanged at `presentation_job/dispatcher.py:3424-3432` |

One extra branch inside the unit's own file, same class, also removed (declared, not smuggled): `_collect_prompt_problems` guarded the directory detector with `if _import_prompt_gate() is not None:` — with no `prompt_gate` the detector silently skipped and the rich-prompt gate passed on a check it never ran. Deleting the guard is what makes the new named failure reach the real gate; without it the fix would be dead code on that route. Guard removed, call made unconditional; the `-1` sentinel path already map to `AF-P1:` in `_chk_rich_prompts`.

---

## 2. Files changed

```
$ git diff --cached --stat
 .../presentations/scripts/build_deck.py            |  56 ++++-
 .../scripts/tests/test_pd073_missing_instrument.py | 122 ++++++++++
 evidence/PD-073/BUILD-REPORT.md                    | 248 +++++++++++++++++++++
 3 files changed, 414 insertions(+), 12 deletions(-)

$ git diff --cached --numstat -- .../build_deck.py
44	12	23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py
```

Four hunks, all in `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`:

1. `_canonical_prompt_dir_problems` — named problem on missing module + marker escape.
2. new `_degraded_allowed` helper (delegating, fail-closed).
3. `_verify_aspect_and_readback` — named raise on missing module + marker escape.
4. `_collect_prompt_problems` — removed the `_pg22 is not None` pass-by-not-running guard.

`python3 -m py_compile build_deck.py` → `compile OK`.

---

## 3. Acceptance rows, each proven with real output

Acceptance row **A1** has two clauses; split into A1.1 / A1.2 so each can fail on its own.

Trigger used: `build_deck._import_prompt_gate` monkeypatched to `lambda: None` — the function's own documented seam for "the shared module is not importable". The env markers are cleared in every negative case (`monkeypatch.delenv` on `PRESENTATION_ALLOW_DEGRADED_VERIFIERS`, `CI`, `OPENCLAW_TEST`) so the negative cannot silently degrade.

### A1.1 — import forced to fail, no test marker → failure naming the missing module

```
$ python3 -m pytest tests/test_pd073_missing_instrument.py -q -k "names_missing or raises_when or fails_closed"
......                                                                   [100%]
3 passed
```

Observable artefacts asserted (not a returned constant):

- `bd._canonical_prompt_dir_problems(rd)` → non-empty list, and one string contains both `prompt_gate` and `unavailable`.
- `bd._verify_aspect_and_readback(rd/"renders"/"slide-01.png", {"copy": ["x"]}, 1)` → raises `RuntimeError` whose text contains `prompt_gate` and `slide 1`.
- `bd._chk_rich_prompts(rd)` (the gate the renderer actually reads) → returns a string starting `AF-P1:` containing `prompt_gate`.

### A1.2 — marker present → the current behaviour

```
$ python3 -m pytest tests/test_pd073_missing_instrument.py -q -k "marker or control"
...                                                                      [100%]
3 passed
```

- marker `working/checkpoints/.test-context` present, import still forced to fail → `_canonical_prompt_dir_problems` returns `[]` (unchanged).
- same → `_verify_aspect_and_readback` returns `None` (unchanged no-op).
- CONTROL on the instrument: real `prompt_gate` importable, clean prompt dir → `[]`. This is the guard against "make the detector always fail", which would otherwise pass A1.1 for the wrong reason.

---

## 4. Failure proof — the BEFORE/AFTER pair

Same six tests, same command, run against the **unfixed base** (`fde9282bb`, clean worktree) and against **HEAD with the fix**:

BEFORE (base `fde9282bb`, test file copied in, no product change):

```
$ python3 -m pytest tests/test_pd073_missing_instrument.py -q
FAILED tests/test_pd073_missing_instrument.py::test_canonical_prompt_dir_problems_names_missing_prompt_gate
FAILED tests/test_pd073_missing_instrument.py::test_verify_aspect_and_readback_raises_when_prompt_gate_missing
FAILED tests/test_pd073_missing_instrument.py::test_rich_prompt_gate_fails_closed_when_prompt_gate_missing
3 failed, 3 passed in 0.12s
```

The three base failures are exactly the three defects, in the base's own words:

```
E       AssertionError: an unimportable prompt_gate must not read as 'no problems'
E       assert []
E       Failed: DID NOT RAISE <class 'RuntimeError'>
E       assert 'prompt_gate' in "AF-P1: rich-prompt-required gate FAILED for 1 of 1 slide-checks. ... Offenders: | slide 01: NO rich prompt file in working/prompts/"
```

- `assert []` — the base returns "no problems" for a detector that never ran.
- `DID NOT RAISE` — the base no-ops the aspect/readback verification.
- the third line is the pass-by-not-running branch itself: the base gate reports a *different* failure (`NO rich prompt file`) because the directory detector was silently skipped — `prompt_gate` is never named.

AFTER (HEAD with the fix):

```
$ python3 -m pytest tests/test_pd073_missing_instrument.py -q
......                                                                   [100%]
6 passed in 0.24s
```

The 3 tests that pass on base are the marker/control rows — recorded honestly: those rows are a **VERIFIED NO-OP** (the spec asks for current behaviour to survive; they pass before and after, which is the requirement).

---

## 5. Tests by id, base vs head

Census of every suite that reads the changed functions, by exact id count:

| Suite | base `fde9282bb` | head |
|---|---|---|
| `tests/test_gates.py` | `31 passed in 2.19s` | `31` (in `111 passed`) |
| `test_preflight.py` | `80 passed, 65 warnings in 14.94s` | `80` (in `111 passed`) |
| `tests/test_batch_render.py` + `tests/test_pd_render_batch_retry.py` | `9 passed in 100.14s` | `9 passed in 100.16s` |
| `tests/test_pd073_missing_instrument.py` (new) | `3 failed, 3 passed in 0.12s` | `6 passed in 0.24s` |

Head commands and outputs:

```
$ python3 -m pytest tests/test_gates.py test_preflight.py -q
111 passed, 65 warnings in 21.04s

$ python3 -m pytest tests/test_batch_render.py tests/test_pd_render_batch_retry.py -q
9 passed in 100.16s (0:01:40)

$ python3 -m pytest tests/test_pd073_missing_instrument.py -q
6 passed in 0.24s
```

No test was weakened, deleted, renamed, skipped or xfailed. `tests/test_gates.py::TestCanonicalPromptDirProblemsThreeValued` (the B4-1 three-valued gate tests) and `test_preflight.py`'s `AF-PROMPT-NAME` / `AF-PROMPT-DUP-FILE` proof both still pass unchanged.

New file's six ids:

```
tests/test_pd073_missing_instrument.py::test_canonical_prompt_dir_problems_names_missing_prompt_gate
tests/test_pd073_missing_instrument.py::test_canonical_prompt_dir_problems_marker_keeps_current_behaviour
tests/test_pd073_missing_instrument.py::test_control_prompt_gate_present_clean_dir_is_empty
tests/test_pd073_missing_instrument.py::test_verify_aspect_and_readback_raises_when_prompt_gate_missing
tests/test_pd073_missing_instrument.py::test_verify_aspect_and_readback_marker_keeps_current_noop
tests/test_pd073_missing_instrument.py::test_rich_prompt_gate_fails_closed_when_prompt_gate_missing
```

### Pre-existing failures, identical on base and head (NOT caused by this unit)

`tests/test_fanout_prompt_phase.py` (4) and `tests/test_fix112_missing_producers.py` (1) fail on **both** trees with the same 5 ids:

```
FAILED tests/test_fanout_prompt_phase.py::test_workers_1_and_workers_n_produce_identical_file_sets
FAILED tests/test_fanout_prompt_phase.py::test_three_failures_leave_rest_verified_and_name_the_failures
FAILED tests/test_fanout_prompt_phase.py::test_resume_after_failure_only_recalls_stub_for_failed_ordinals
FAILED tests/test_fanout_prompt_phase.py::test_never_exceeds_manifest_workers_concurrent_calls
FAILED tests/test_fix112_missing_producers.py::test_infographic_checklist_phase_exists_with_role_file_and_verifier
```

base: `5 failed, 5 passed in 257.50s` · head: `5 failed, 12 passed in 270.76s` (head run had 3 extra files in the same invocation). Failure shape is `assert 'exhausted' == 'ok'` inside `dispatcher._dispatch_prompt_phase` — a wall-clock exhaustion in this environment, present before my change.

---

## 6. Hunk attribution — merge-base to HEAD

```
$ git merge-base origin/main HEAD
1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc
```

Commits on `1a476d2..HEAD` and their `build_deck.py` hunks (base line numbers), i.e. hunks that are **not mine**:

| Commit | Unit | `build_deck.py` hunks |
|---|---|---|
| `1372454c0` | PD-046 — a recorded style pick passes the render check | `10965-10965`, `10988-11011` (`_chk_style_preview`) |
| `471fdae82` + merge `29108bfac` | PD-206a — the two human verdicts read from their own files | `phase_verifiers.py` only (+ `tests/test_pd_phase_checks_human_review.py`) |
| `35c649df7` | PD-902 — closeout wrappers read the human-review verdict files | `11493-11497`, `11509-11514`, `11526-11533`, `13791-13822` |
| `0ac43ab3a` | PD-060 — the bundle check comes out of the render | `124-206` (USAGE/EXIT CODES docstring), `14275-14956` (`main()`) |
| `f4cadfb38` | PD-200 — the render's speech checks read the folder the speech is written to | `2889-2890` (`discover_speech_chunks`), `5076-5157` (`check_speech_qc_teeth`), `6500-6513`, `6559-6580` |
| `fde9282bb` | PD-070 — a failed slide is retried inside the batch | `2480-2742` (`render_slides_batch`) |

My four hunks land at (`HEAD` line numbers) `1381-1397`, `1914-1929`, `1970-1985`, `6389-6405`. **No overlap with any sibling hunk.** The nearest sibling hunk is PD-200's at `6500-6513` (`_chk_kie_baked` / `_chk_speech_length`), ~95 lines below my `_collect_prompt_problems` hunk and in different functions.

Note: the lane's other accepted units named in the task — PD-200, PD-046, PD-206a, PD-902, PD-060 — are all in the table above; PD-070 is the branch head and is the unit PD-073 depends on.

---

## 7. Remote-head proof

Pre-push, the branch was `fde9282bb6c33c73363ec0baeea63b75a968b7f2` (confirmed at the top of this report and again immediately before the push). This report, the test file and the fix ship in the commit that this report is inside, so the 40-character head after the push **cannot be embedded in the commit it names** — it is returned verbatim with this report and is re-verifiable with:

```
$ git ls-remote --heads origin refs/heads/pd/fl15-renderer
<40 hex characters>	refs/heads/pd/fl15-renderer

$ git rev-parse HEAD
<the same 40 characters>
```

The literal comparison performed after the push (both values are the full 40 characters, compared literally) is pasted in the orchestrator return; nothing here is abbreviated.

---

## 8. Anything unproved / limitations

1. **No live render was run.** The unit is "files and stubbed tests only" (live-action flag `none`), and `_verify_aspect_and_readback` needs KIE + PIL + an OCR engine. Proven at the function and gate boundary with stubbed instruments; a doctrine-active scratch render is not part of A1 and was not attempted.
2. **`_verify_aspect_and_readback` derives the run dir as `out_path.parent.parent`.** That is the existing contract in the same function (`renders/.. == run dir`, already used for `_owner_skip_approved`). If a caller passes a non-canonical `renders_dir` (`build_deck.py:14619` allows `positional[2]`), the marker file will not be found and the branch **fails closed**. Not tested here; it errs on the safe side.
3. **`_degraded_allowed` is not exercised with the `PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1` and `CI`/`OPENCLAW_TEST` env shapes** — only the `.test-context` file shape. Delegation to `phase_verifiers._degraded_allowed` is asserted by that test, and `phase_verifiers`' own rule is unchanged and covered by its own tests.
4. **Non-numeric claim I cannot prove:** that no other lane imports `build_deck._degraded_allowed` under that bare name. Checked with `grep -n "_degraded_allowed" build_deck.py` (7 hits, all mine) and the name did not exist in `build_deck.py` at base (`grep` over base returned nothing). `phase_verifiers._degraded_allowed` remains the definition; mine only delegates.

---

## 9. Known by-design proceed (as the spec requires listing)

- **`_gov_acquire` (base lines 1741-1745).** `if _governor is None: return None` — a governor-absent / poll-side error lets the KIE submit proceed unthrottled. The consolidation amendment says leave it as it is. It is untouched by this diff.

## 10. Not this unit (named so they are not re-found here)

- **`dispatcher._verify_single_prompt`, `presentation_job/dispatcher.py:3424-3432`** — the same class of branch. Fixed inside **PD-065 (lane FL18)** per the consolidation amendment. Verified unchanged here.
- `_chk_citation_validated`, `check_speech_qc_teeth` hook-module branch, `check_image_qc_present` unreadable-date branch — **PD-218a** (depends on this unit). Not touched.
- `kie_balance_preflight` and `check_brand_consistency` — PD-218a's known by-design defers, not mine.
