# PD-218a — Renderer checks fail when their instrument is missing

- Repo: `trevorotts1/openclaw-onboarding` · Branch `pd/fl15-renderer` (lane FL15)
- Builder: deepseek-chain (fresh attempt; the previous lane for this unit went idle without a report)
- Wave 3 · depends on PD-073 (ACCEPTED on this branch) and RD-06 (read: `prompt_gate.py`,
  `presentation_job/citation_validator.py`, `presentation_job/motion.py`, `kie_generate.py`,
  `kie_tasks.py`, and the `build_deck.py` gaps named in PASS5-GATES section 5)
- Acceptance row run: **A1**

## 1. Spec quoted (binding text implemented)

> #### PD-218a — Renderer checks fail when their instrument is missing

> **Carried-over unit text (from `PASS5-GATES.md`, section PD-218a; ids, decisions and lanes already converted to final):**
>
> - **Change:** `_chk_citation_validated`: a missing module or a failed inventory read returns a named failure unless the test rule in PD-201 allows it; "no retrieval ledger" stays a defer only while no research brief exists, and becomes a failure once a brief exists. `check_speech_qc_teeth`: a missing or crashing hook module is a named problem. `check_image_qc_present`: an unreadable file date is a failure. Leave `kie_balance_preflight` and `check_brand_consistency` as they are and list them in the report as known by-design defers.
> - **Acceptance:** each changed branch has one test that forces the instrument away and sees a failure naming it.

Row from the unit table: `| Acceptance rows the checker must run | A1 |`.

## 2. Files changed

| File | Change | Commit |
|---|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py` | the three branches (`_chk_citation_validated`, `check_speech_qc_teeth`, `check_image_qc_present`) | `fbf8b9e60` (initial) + this commit (image-QC reason now names the exact file whose date failed) |
| `.../scripts/test_preflight.py` | fixture repair only: `make_workdir` now writes a FIX 19 retrieval ledger with the 8 brief sources already fetched, and map items no longer carry a `source_url` (their anchors are copy-weave ids, not fetched-page claims). Needed because the new citation rule correctly fails a brief-without-ledger run dir — proof below. No assertion removed, renamed, skipped or xfailed. | `fbf8b9e60` |
| `.../scripts/tests/test_pd_render_instrument_missing.py` | new test file, 12 tests (6 forced-instrument-away + 5 controls + 1 render-date attribution) | `fbf8b9e60` + this commit |
| `evidence/PD-218a/BUILD-REPORT.md` | this report | this commit |

No shared file touched (`update-skills.sh`, `universal-sops/_content-manifest.json`, `install.sh` untouched).

## 3. Each acceptance row proven

### Branch 1 — `_chk_citation_validated`: missing module

Code (`build_deck.py`, commit `fbf8b9e60`):

```python
if not _citation_validator:
    if _degraded_allowed(run_dir):
        return ""
    return ("AF-RESEARCH-UNCITED: citation validation could not run — the "
            "presentation_job.citation_validator module is MISSING, ...")
```

Test `tests/test_pd_render_instrument_missing.py::test_citation_validator_missing_fails_naming_it`
forces `bd._citation_validator = None` with every PD-201 marker stripped and asserts
`AF-RESEARCH-UNCITED:` + `citation_validator` + `MISSING`.
Control `::test_citation_validator_missing_defers_only_under_pd201_test_rule` proves the single
remaining defer path is the PD-201/`_degraded_allowed` marker rule (`.test-context` file).

### Branch 1b — `_chk_citation_validated`: failed inventory read

```python
except Exception as exc:
    if _degraded_allowed(run_dir):
        return ""
    return (f"AF-RESEARCH-UNCITED: citation inventory could not be read "
            f"({type(exc).__name__}: {exc}) — ...")
```

Tests `::test_citation_inventory_read_failure_fails_naming_it` (stub raises
`OSError("ledger unreadable")`; asserts the type and text are named) and control
`::test_citation_inventory_read_control_passes_when_readable` (same stub, readable → `""`).

### Branch 1c — `_chk_citation_validated`: brief exists, FIX 19 ledger absent

```python
if not ledger.is_file():
    briefs = sorted(run_dir.glob("working/research/brief-*.md"))
    if not briefs:
        return ""          # genuine pre-FIX-19 defer
    return (f"AF-RESEARCH-UNCITED: the research pack ({...}) declares "
            f"{len(citations)} URL-bearing citation(s) but the FIX 19 retrieval "
            f"ledger (working/research/{...LEDGER_NAME}) is MISSING, ...")
```

Tests `::test_brief_without_retrieval_ledger_fails_naming_ledger` (asserts `retrieval ledger`,
`brief-01.md`, `retrieval_ledger.jsonl`), plus two controls:
`::test_no_brief_no_ledger_still_defers` and `::test_brief_with_ledger_passes` (same fixture, ledger
present → `""`).

### Branch 2 — `check_speech_qc_teeth`: missing / crashing hook module

```python
pec = _import_pitch_engines_check()
if pec is None:
    problems.append("... the pitch_engines_check module is MISSING ... the hook "
                    "sing count was NOT verified")
else:
    try:
        hook_hits = pec.run(run_dir, phase="SPEECH-QC")
    except Exception as exc:
        problems.append(f"... CRASHED ({type(exc).__name__}: {exc}) — the hook sing "
                        f"count was NOT verified")
```

Tests `::test_speech_qc_missing_hook_module_is_a_named_problem` and
`::test_speech_qc_crashing_hook_module_is_a_named_problem` (assert `AF-SPEECH-QC:` prefix,
`pitch_engines_check` / `CRASHED`, and the exception type + message). Control
`::test_speech_qc_control_passes_with_real_hook_module` runs the real module and gets `""`.

### Branch 3 — `check_image_qc_present`: unreadable file date

`fbf8b9e60` turned the swallowed `except OSError: pass` into a named `AF-IMAGE-QC-RAN:` failure.
This attempt additionally makes the message name **the file whose date failed** — the original
text said "the image-QC report's file date could not be read" even when the unreadable date was a
render PNG's:

```python
def _date_of(path: Path) -> float:
    """A file date, or an OSError that NAMES the file it came from (PD-218a)."""
    try:
        return path.stat().st_mtime
    except OSError as exc:
        raise OSError(exc.errno, f"{path}: {exc.strerror}") from None
...
except OSError as exc:
    return (f"AF-IMAGE-QC-RAN: a file date could not be read "
            f"({type(exc).__name__}: {exc}) — ...")
```

Tests `::test_image_qc_unreadable_file_date_fails_naming_it` (report date unreadable → names
`image_qc_report.json`) and `::test_image_qc_unreadable_render_date_names_the_render` (render date
unreadable → names `slide-1.png`, and asserts the report is NOT blamed). Both fixtures assert the
clean pass first, so neither test can pass on a check that never runs.

### Known by-design defers, left exactly as they were (per spec)

- `kie_balance_preflight` (`build_deck.py:8006`) — defers only with no API key **and**
  adhoc/no-network context; a balance the endpoint cannot return is already a hard abort.
- `check_brand_consistency` (`build_deck.py:7329`) — defers when no palette is declared or no
  renders exist; absence of both is another gate's job.
Neither function is touched by any PD-218a hunk (verified in the commit diff below).

## 4. Failure proof (mutation, before/after)

Same test file, same interpreter, `build_deck.py` swapped for its pre-PD-218a content
(`341139e03` — the commit immediately before the unit):

```
$ git show 341139e03:.../build_deck.py > $S/build_deck.BASE.py   # swap in
$ python3 -m pytest tests/test_pd_render_instrument_missing.py -q
FAILED ...::test_citation_validator_missing_fails_naming_it
FAILED ...::test_citation_inventory_read_failure_fails_naming_it
FAILED ...::test_brief_without_retrieval_ledger_fails_naming_ledger
FAILED ...::test_speech_qc_missing_hook_module_is_a_named_problem
FAILED ...::test_speech_qc_crashing_hook_module_is_a_named_problem
FAILED ...::test_image_qc_unreadable_file_date_fails_naming_it
FAILED ...::test_image_qc_unreadable_render_date_names_the_render
7 failed, 5 passed in 0.50s
```

With the unit's code restored:

```
$ python3 -m pytest tests/test_pd_render_instrument_missing.py -q
12 passed in 0.43s
```

The 5 that stay green on the old code are the controls (defer paths and clean-pass fixtures), which
is the point: they prove the instrument-away tests fail for the right reason, not because the
fixture is broken. The image-QC control that could never fail is avoided — both image tests assert
`check_image_qc_present(rd) == ""` on the same fixture *before* the patch is applied.

The `test_preflight.py` fixture hunk is load-bearing, proven by reverting only that file:

```
$ git show 341139e03:.../test_preflight.py > .../test_preflight.py   # HEAD build_deck, base fixture
TEST FAILED:
  - PF-SPEECH-B: ...
  - STYLE-GATE-A: warn-stage should NOT exit, got sys.exit(3)
  - STYLE-GATE-C (warn): style-attested fixture should PASS, got sys.exit(3)
  - STYLE-GATE-C (enforce): style-attested fixture should PASS, got sys.exit(3)
  - STYLE-GATE-D: owner-authorized skip should PASS in enforce stage, got sys.exit(3)
  - CASE2 preflight wrongly refused
  - CASE2 expected 'PREFLIGHT PASSED' banner
```

With the fixture repair in place only the pre-existing `PF-SPEECH-B` remains (see §5).

## 5. Tests by id — base and head

New file `tests/test_pd_render_instrument_missing.py` (12 ids):

| # | test id | base `341139e03` | head |
|---|---|---|---|
| 1 | `::test_citation_validator_missing_fails_naming_it` | FAIL | PASS |
| 2 | `::test_citation_validator_missing_defers_only_under_pd201_test_rule` | PASS (control) | PASS |
| 3 | `::test_citation_inventory_read_failure_fails_naming_it` | FAIL | PASS |
| 4 | `::test_citation_inventory_read_control_passes_when_readable` | PASS (control) | PASS |
| 5 | `::test_brief_without_retrieval_ledger_fails_naming_ledger` | FAIL | PASS |
| 6 | `::test_no_brief_no_ledger_still_defers` | PASS (control) | PASS |
| 7 | `::test_brief_with_ledger_passes` | PASS (control) | PASS |
| 8 | `::test_speech_qc_missing_hook_module_is_a_named_problem` | FAIL | PASS |
| 9 | `::test_speech_qc_crashing_hook_module_is_a_named_problem` | FAIL | PASS |
| 10 | `::test_speech_qc_control_passes_with_real_hook_module` | PASS (control) | PASS |
| 11 | `::test_image_qc_unreadable_file_date_fails_naming_it` | FAIL | PASS |
| 12 | `::test_image_qc_unreadable_render_date_names_the_render` | FAIL | PASS |

Regression census on the files that reach the three changed functions
(`tests/test_qc_gate_teeth.py`, `tests/test_speech_pacing_fix97.py`,
`tests/test_pd_render_speech_candidate_folder.py`, `tests/test_pd073_missing_instrument.py`):

```
base 341139e03 : 10 failed, 32 passed
head           : 10 failed, 32 passed
diff of the FAILED sets -> IDENTICAL FAILURE SETS (10 lines)
```

The 10 are the pre-existing `tests/test_speech_pacing_fix97.py` failures. They fail identically at
the lane's **merge-base with `origin/main`** (`1a476d2cb`, `10 failed, 5 passed`), so they pre-date
every unit on this branch and are not PD-218a debt.

`python3 test_preflight.py` (the repo's own script harness, rc=1):

```
base 341139e03 : TEST FAILED: - PF-SPEECH-B: 3,600-word speech (30min target, at floor) should PASS, got sys.exit(5)
head           : TEST FAILED: - PF-SPEECH-B: 3,600-word speech (30min target, at floor) should PASS, got sys.exit(5)
```

Same single failure before and after — pre-existing, unrelated to this unit (it reproduces on the
parent commit with the parent's own `test_preflight.py`).

## 6. Hunk attribution — merge-base `1a476d2cb` to HEAD

| Commit | Unit | Hunks/artefacts |
|---|---|---|
| `1372454c0` | PD-046 | `build_deck.py` (recorded style pick), `tests/test_pd046_style_lock.py` |
| `471fdae82` | PD-206a | `phase_verifiers.py`, `tests/test_pd_phase_checks_human_review.py` |
| `35c649df7` | PD-902 | `build_deck.py` (closeout wrappers read verdict files), `tests/test_fix92_closeout_gates.py` |
| `0ac43ab3a` | PD-060 | `build_deck.py` (bundle check out of the render), `tests/test_pd_render_bundle_gate.py` |
| `f4cadfb38` | PD-200 | `build_deck.py` (speech checks read the delivery folder), `tests/test_pd_render_speech_candidate_folder.py` |
| `fde9282bb` | PD-070 | `build_deck.py` (per-slide retry), `tests/test_pd_render_batch_retry.py` |
| `49eb8a384` | PD-073 | `build_deck.py` (`_degraded_allowed` + prompt_gate fail-closed), `tests/test_pd073_missing_instrument.py`, `evidence/PD-073/BUILD-REPORT.md` |
| `341139e03` | PD-073 | `evidence/PD-073/BUILD-REPORT.md` only |
| `fbf8b9e60` | **PD-218a** | `build_deck.py` (three branches), `test_preflight.py` (fixture ledger), `tests/test_pd_render_instrument_missing.py` |
| this commit | **PD-218a** | `build_deck.py` (`_date_of` naming the unreadable file), `tests/test_pd_render_instrument_missing.py` (+1 test), `evidence/PD-218a/BUILD-REPORT.md` |

No PD-218a hunk touches `kie_balance_preflight`, `check_brand_consistency`, `phase_verifiers.py`
or any shared file. `build_deck._degraded_allowed` is PD-073's (commit `49eb8a384`); PD-218a only
calls it.

## 7. Remote-head proof

Before editing (dispatch-time check):

```
$ git ls-remote --heads origin refs/heads/pd/fl15-renderer
fbf8b9e602a8ce426f351bde9d8cb2d2b6650581	refs/heads/pd/fl15-renderer
```

The branch existed; the PD-218a commit `fbf8b9e60` was already on it (the previous lane committed
but never reported). This attempt verified that commit against the spec rather than assuming it,
fixed one truthfulness defect in its third branch, and added the evidence report.

Push of the code/test commit, then the same query read back in full (40 characters):

```
$ git push origin HEAD:refs/heads/pd/fl15-renderer
   fbf8b9e60..198c53f0b  HEAD -> pd/fl15-renderer
$ git ls-remote --heads origin refs/heads/pd/fl15-renderer
198c53f0b2b32c4f599a81feaa4a7983a07ef216	refs/heads/pd/fl15-renderer
```

The report commit that carries this file lands on top of `198c53f0b`; its own push is read back the
same way and quoted in the harness return.

## 8. Not proved / limits

- The repo-wide `pytest tests/` sweep was started and reached 73 % before it stalled (a test that
  blocks), so it is **not** a completed measurement and the run was abandoned there. It also
  produced `F` markers in the part it did run; those were **not attributed** to a test id and are
  not claimed as clean. The targeted census above (every file that references the three changed
  functions) is complete and compared base-to-head.
- The 10 pre-existing `test_speech_pacing_fix97.py` failures and the pre-existing `PF-SPEECH-B`
  are named, not fixed — they are outside this unit and fail identically at the merge-base.
- `test_image_qc_unreadable_file_date_fails_naming_it` relies on `Path.exists()` resolving through
  `os.path.exists` (true on CPython 3.14.7, this repo's interpreter). On a Python whose
  `Path.exists()` calls `Path.stat()` the monkeypatch would intercept the existence probe first and
  the test would be red — a test-environment limit, recorded rather than papered over.
