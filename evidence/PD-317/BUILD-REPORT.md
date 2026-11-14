# PD-317 — BUILD REPORT

**Unit:** PD-317 — Sealed-record checks fail when their instrument is missing
**Lane:** FL35 · **Branch:** `pd/fl35-sealed-record`
**Repo:** trevorotts1/openclaw-onboarding
**Base:** `fcb901515` (PD-306, ACCEPTED — built on top, not duplicated)
**Commit:** `c78796b86fdf3d6779bd56f273428d179897df25`
**Builder:** deepseek-chain · **Acceptance rows:** A1

---

## 1. What was built

Only the two `runfacts.py` branches named by the consolidation amendment
(`_notes_sync_fact`, `verify_workbook`). The guard branches (FL37), craft branches
(FL31) and the closing-gate change (PD-317b, FL26) are out of this unit and were
not touched or reported anywhere.

### 1.1 `_notes_sync_fact` — an unmeasured pane is a finding, not a blank

`presentation_job/runfacts.py`

| Condition | Before | After |
|---|---|---|
| `build_deck` unreachable (`_import_build_deck() is None` or `_chk_notes_pane is None`) | `notes_pane_result = ""` | `NOTES_PANE_UNMEASURED` |
| `_chk_notes_pane` raises | `notes_pane_result = ""` (crash swallowed) | `NOTES_PANE_UNMEASURED` |
| healthy scan, no empty panes | `""` | `""` (unchanged) |

```python
NOTES_PANE_UNMEASURED = "AF-EMPTY-NOTES-PANE: could not be measured"
```

An empty string already means "scanned, every pane has notes" to
`verify_notes_sync`, so a missing renderer silently cleared the very check it was
supposed to run. It now fails the verdict, and the reason names the measurement.

### 1.2 `verify_workbook` — pypdf absence fails, unless the PD-201 rule allows it

`WorkbookInfo` gained `degraded_allowed: bool = False` (appended, defaulted — no
existing construction site changes). `_workbook_fact` resolves it **at seal time**
by asking the PD-201 rule's single owner, so the verdict stays pure:

```python
def _degraded_allowed(run_dir: Path) -> bool:
    try:
        from phase_verifiers import _degraded_allowed as _rule
        return bool(_rule(run_dir))
    except Exception:
        return False   # fails CLOSED
```

`verify_workbook`:

| Context | Before | After |
|---|---|---|
| `pypdf` missing, production (no rule signal) | `PASS` + "NOTE: pypdf not importable … (pass)" | `FAIL` naming pypdf and the sealed detail |
| `pypdf` missing, PD-201 rule on | `PASS` + note | `PASS` + note that says "under the PD-201 test rule" |
| `pypdf` present, read raises | degraded detail, `PASS` via the same silent branch | `FAIL` naming the read failure, or `PASS` under the rule |

The rule is delegated, never re-implemented: when PD-201 (FL17) removes the
marker-file branch from `_degraded_allowed`, this module follows automatically.
Nothing in the keyed-stamp machinery of PD-306 was edited, weakened, or reused —
these two branches never read a stamp row, so no new stamp row shape was needed.

---

## 2. Files touched

| File | Owner |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/runfacts.py` | lane FL35 (owned) |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_runfacts_317_missing_instrument.py` | lane FL35 (`test_pd_runfacts_*.py` glob) |
| `evidence/PD-317/BUILD-REPORT.md` | this report |

Diff: `runfacts.py` +45 / −15; test file new (114 lines). No other file was read
for writing, no other lane's branch/worktree/folder was touched. No merge, no
rebase, no force-push, no push to `main`.

**Hunks not mine:** none. Every hunk in the diff is PD-317's. The parent state of
the branch (PD-306 `fcb901515`, and the batch merges below it — `1a476d2cb`,
`f87dff427`, `fc736c7ac`, `9e3bcf93a`, `adf0f33a0`, `11b02e4fb`, `f0abf8344`)
was read, never modified.

---

## 3. Proof

### 3.1 The unit's own tests — 5 passed

```
$ cd 23-ai-workforce-blueprint/templates/role-library/presentations/scripts
$ python3 -m pytest tests/test_pd_runfacts_317_missing_instrument.py -q
.....                                                                    [100%]
5 passed in 0.39s
```

### 3.2 The same tests on the parent commit — 4 failed, 1 passed

Baseline taken by stashing only `runfacts.py` and re-running the same file in the
same worktree (same transport, same interpreter):

```
$ git stash push -m pd317-baseline -- .../presentation_job/runfacts.py
$ python3 -m pytest tests/test_pd_runfacts_317_missing_instrument.py -q
FAILED ...::test_notes_pane_missing_renderer_fails_naming_it
FAILED ...::test_notes_pane_crashing_renderer_fails_naming_it
FAILED ...::test_pypdf_missing_fails_naming_pypdf
FAILED ...::test_pypdf_missing_passes_only_under_the_pd201_rule
1 passed  (test_notes_pane_healthy_renderer_still_passes — the control)
$ git stash pop
```

So each new-branch test fails for the branch it guards, and the control test
passes on both sides (the change does not fail a healthy renderer).

### 3.3 Point-by-point

| Acceptance claim | Test | Evidence |
|---|---|---|
| missing renderer → failure naming the measurement | `test_notes_pane_missing_renderer_fails_naming_it` | `notes_pane_result == "AF-EMPTY-NOTES-PANE: could not be measured"`, verdict `FAIL`, reason contains it |
| crashing renderer → failure naming the measurement | `test_notes_pane_crashing_renderer_fails_naming_it` | `_chk_notes_pane` raises; same sealed string, verdict `FAIL` |
| control: healthy scan still passes | `test_notes_pane_healthy_renderer_still_passes` | renderer returns `""` → verdict `PASS` |
| pypdf missing → FAIL naming pypdf | `test_pypdf_missing_fails_naming_pypdf` | `sys.modules["pypdf"] = None`; no env/marker signal; verdict `FAIL`, reason names `pypdf`, the old `"NOTE: pypdf not importable"` pass text is absent |
| pypdf missing passes only under the PD-201 rule | `test_pypdf_missing_passes_only_under_the_pd201_rule` | `PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1` → `degraded_allowed is True`, verdict `PASS`, note names PD-201 |

### 3.4 No regression — like-for-like baseline

Same seven pre-existing test files, same worktree, same command; baseline run with
`runfacts.py` stashed:

| Run | Result | Failing tests |
|---|---|---|
| with PD-317 | `3 failed, 122 passed` (117 pre-existing + 5 new) | the 3 below |
| baseline `fcb901515` | `3 failed, 117 passed` | the 3 below |

```
FAILED tests/test_trust_boundary_observability.py::TestEndToEndCapture::test_tampered_run_detected_recorded_and_still_proceeds
FAILED tests/test_trust_boundary_observability.py::TestEnforcingIsOrthogonalToRecording::test_enforcing_on_still_gets_recorded_with_enforcing_true
FAILED tests/test_trust_boundary_observability.py::TestPreflightFamily::test_clean_run_summary_line_is_parsed
```

Identical on both sides → pre-existing on `pd/fl35-sealed-record` (their
assertions expect `entries=62`; the branch emits `entries=63`), not caused by
PD-317. Test files in the run: `test_pd_runfacts_306_execution_stamp.py`,
`test_trust_boundary_observability.py`, `test_slice3_gates.py`,
`test_verifier_registry.py`, `test_slice1_gates.py`, `test_intake_provenance.py`,
`test_workbook_builder.py`.

---

## 4. Push proof

```
$ git push origin pd/fl35-sealed-record
   fcb901515..c78796b86  pd/fl35-sealed-record -> pd/fl35-sealed-record

$ git ls-remote origin refs/heads/pd/fl35-sealed-record
c78796b86fdf3d6779bd56f273428d179897df25	refs/heads/pd/fl35-sealed-record

$ git rev-parse HEAD
c78796b86fdf3d6779bd56f273428d179897df25
```

Remote sha equals the commit.
