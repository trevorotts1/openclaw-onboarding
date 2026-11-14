# PD-313 — Say "ready" on the normal close — BUILD REPORT

- **Unit:** PD-313
- **Lane:** FL05
- **Repository:** trevorotts1/openclaw-onboarding
- **Branch:** `pd/fl05-engine-reporting`
- **Prerequisite PD-042:** ACCEPTED at `f0da9bcf1deb17dfefd5d5d898519abb46db25ab` (also PD-031) — this is the branch head I built on.
- **Change commit (code + tests):** `edc4334137d4d8482cfb2c3823924d98b640cfe0`
- **Report commit:** this file is committed as a documentation-only commit on top of the change commit; the branch head after it is what `git ls-remote` returns and is recorded in the "Commit and remote proof" section and in my handoff.
- **Builder:** deepseek-chain
- **Acceptance row:** A1
- **Severity:** Moderate

## Spec text implemented (quoted)

From `$LOOP_ROOT/../fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`, section `### PD-313`:

> | Findings | PD-313 |
> | Severity | Moderate |
> | Builder | deepseek-chain — difficulty mechanical: one call, fully specified |
> | Lane and repository | FL05 · trevorotts1/openclaw-onboarding |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-042 |
> | Acceptance rows the checker must run | A1 |

> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> Call `_compose_done_message` from PD-042 instead of repeating the old sentence "All quality checks passed". When it returns nothing (no verified destination), send nothing and log `report.done_withheld`. The waived-checks sentence is appended as the text below gives it.

> **Carried-over unit text (from `PASS6-LAST.md`, section PD-313; ids, decisions and lanes already converted to final):**
>
> - **Change:** before line 5729 add the same `self.report.to_requester("done", …)` call used at lines 5654–5655. When any gate was waived, the text is "Your presentation is ready. {n} check(s) were waived at your request." (coordinate with PD-018's wording unit).
> - **Acceptance:** a stub run that passes every gate first time records one `report.done` event.

The finding it repairs, from `00-FINDINGS-RANKED.md` line 724:

> ### PD-313 — A run that passes every gate first time sends the client no "ready" message
> - **Repository:** ONB · **Status:** verified · **First reported in:** `PASS6-LAST.md`
> - **Evidence:** `phases.py` 5654-5655, 5726-5730; `__main__.py` 1382. The shell door, supervisor and board path were not checked.

The carried-over line numbers are from `PASS6-LAST.md`, not the current file. In the branch head they map to `close()`'s two DONE branches: the re-gated branch already called `self._send_done_message()` (PD-042, formerly the literal `to_requester("done", "Your presentation is ready. All quality checks passed.")`), and the normal branch — the one every first-time-pass run takes — reached DONE and printed `DONE -- all gates passed.` with no client message at all. That silent branch is where PD-313 adds the call.

## What changed

### `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/phases.py`

1. `_send_done_message` (PD-042's compose caller) gained `waived_count: int = 0`. After the composed message is proven non-empty, `" {n} check(s) were waived at your request."` is appended when `waived_count > 0`. When `_compose_done_message` returns `""`, the function still sends nothing and logs `report.done_withheld` — unchanged.
2. `close()` computes `waived_n` = how many gate keys ended the evaluation loop with `state == "waived"` (i.e. a genuinely applied client waiver), and passes it to both DONE branches.
3. The normal close (every gate passed first time) now calls `self._send_done_message(waived_count=waived_n)` after `terminal=DONE` is saved and before the console `DONE` line — the same call shape as the re-gated branch.

### `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_presentation_job.py`

New class `TestDoneMessageOnNormalClose` — 137 added lines, 0 deleted (purely additive; no existing test touched):

- `test_a_run_that_passes_every_gate_first_time_records_one_report_done` — row A1. Seeds every gate passing first time plus one verified delivery destination, calls the real `Engine.close()`, asserts EXIT_OK/DONE, exactly one `report.done` event, and that the message names the verified destination.
- `test_a_waived_check_is_named_in_the_ready_message` — a client-quoted `qc` waiver reaches DONE with `gates["qc"]["state"] == "waived"` and the message carries `1 check(s) were waived at your request.`
- `test_no_verified_destination_withholds_the_ready_message` — negative control: same fixture, no verified destination → no `report.done`, exactly one `report.done_withheld`, nothing sent.

## Row A1 proven — BEFORE and AFTER on the artefact

The proof runs the real `Engine.close()` and counts the real `report.done` event in `state["events"]`, which `Reporter.to_requester` records regardless of transport outcome. No returned value is trusted; the event list on disk in state is the artefact.

**AFTER (change commit, fix present):**

```
$ cd .../presentations/scripts
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
    tests/test_presentation_job.py::TestDoneMessageOnNormalClose -q
...                                                                      [100%]
3 passed in 2.49s
```

**BEFORE (mutation: `git checkout -- presentation_job/phases.py`, tests kept):**

```
$ git checkout -- presentation_job/phases.py
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
    "tests/test_presentation_job.py::TestDoneMessageOnNormalClose::test_a_run_that_passes_every_gate_first_time_records_one_report_done" -q
...
        assert rc == EXIT_OK, f"expected EXIT_OK, got {rc}; stderr={captured.err}"
        assert engine.state["terminal"] == "DONE"
>       assert len(done) == 1, done
E       AssertionError: []
E       assert 0 == 1
tests/test_presentation_job.py:1175: AssertionError
FAILED ...::test_a_run_that_passes_every_gate_first_time_records_one_report_done
```

The full class reverted together gives `3 failed` — the A1 row and both companions fail on the pre-fix artefact because zero `report.done` events exist on the normal close. The fix was then restored from `$TMPDIR/phases.fixed.py` and the class re-ran `3 passed`. The tests are discriminating, not vacuous.

## Test runs by test id (base and head)

Head = `edc4334137d4d8482cfb2c3823924d98b640cfe0` (this unit), built on base `f0da9bcf1deb17dfefd5d5d898519abb46db25ab`.

| Test id | Base (phases.py reverted) | Head (fix) |
|---|---|---|
| `tests/test_presentation_job.py::TestDoneMessageOnNormalClose::test_a_run_that_passes_every_gate_first_time_records_one_report_done` | FAIL (`AssertionError: []`, `assert 0 == 1`) | PASS |
| `...::test_a_waived_check_is_named_in_the_ready_message` | FAIL | PASS |
| `...::test_no_verified_destination_withholds_the_ready_message` | FAIL | PASS |

Head also passes the untouched PD-042/PD-031 neighbours:

```
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
    tests/test_presentation_job.py::TestDoneMessageOnNormalClose \
    tests/test_pd_engine_client_messages.py -q
..........                                                               [100%]
10 passed in 2.82s
```

Full `tests/test_presentation_job.py` + `tests/test_pd_engine_client_messages.py` on head: `40 passed, 1 failed`. The one failure is **pre-existing and not mine** — `TestQCAggregatePhaseEndToEnd::test_flawless_six_reports_reach_done` fails identically on the pristine lane clone at base (`f0da9bcf1`) with `final["pass"] is True` → `False` (AF-EXEC-STAMP on `copy_qc_report.json`). I did not weaken it.

The nine PD-042/PD-031-related files (`test_engine_client_report.py`, `test_fix29_style_pick_human_stage.py`, `test_pd_engine_client_copy.py`, `test_pd_engine_client_messages.py`, `test_pd_engine_eta.py`, `test_pd_engine_operator_review.py`, `test_pd_engine_process_certificate.py`, `test_pd_report_sanitize.py`, `test_pd_report_throttle.py`) give `13 failed, 72 passed` on head. I captured the `FAILED` set on base and on head and diffed them: **IDENTICAL failure sets** (13 names, same order after `sort`). They are pre-existing on this branch, not caused by PD-313.

## Hunk attribution — merge-base to HEAD

Merge-base with `origin/main`: `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`.

Branch commits `merge-base..HEAD` before my change (`f0da9bcf1`):

| Commit | Unit | Touches |
|---|---|---|
| `efa65b1ec` | PD-019 | `report.py`, `test_pd_report_throttle.py` |
| `18877e13e` | PD-019 | `__main__.py` |
| `62bfc699c` | PD-076 | `phases.py` (+68), `test_pd_engine_process_certificate.py` |
| `935c31e12` | PD-206b | `phases.py` (+97), `report.py`, `test_pd_engine_operator_review.py` |
| `c15aca513` | PD-906 | `state.py` |
| `c40b6744d` | PD-906 | `phases.py` (+15) |
| `414c715ab`, `aa506ba7e`, `f8cfbef10` | PD-018b | `phases.py`, `report.py`, `heal.py`, client-copy tests, evidence |
| **`afd4a7571`** | **PD-042** | **`phases.py` (+288), `test_fix29_style_pick_human_stage.py`, `test_pd_engine_client_messages.py`, `evidence/PD-042/`** |
| **`06bffcf21`** | **PD-031** | **`phases.py` (+85), `test_pd_engine_eta.py`** |
| `4556ab565`, `f0da9bcf1` | PD-031 | `evidence/PD-031/BUILD-REPORT.md` only |

**PD-042 hunks in `phases.py`** (`git show afd4a7571 -- phases.py | grep '^@@'`):
`@@ -744,6 +744,205 @@` — added `_read_run_json`, `_verified_destination_lines`, `_teleprompter_publish`, `_compose_done_message`, `_style_pick_samples_were_sent`, `_style_pick_messages`, and the constants `STYLE_PICK_TIMEOUT_SENTENCE`, `DONE_WITHHELD_EVENT`, `TELEPROMPTER_NO_LINK_SENTENCE`, `DELIVERY_PLAN_REL`, `MEDIA_LIBRARY_REL`, `SAMPLES_MANIFEST_REL`, `STYLE_SPEC_REL`.
`@@ -4150,14 +4349,30 @@`, `@@ -4165,17 +4380,19 @@`, `@@ -4235,7 +4452,7 @@`, `@@ -4305,13 +4522,20 @@`, `@@ -4336,10 +4560,13 @@` — the style-pick request/`_block` paths.
`@@ -5790,6 +6017,27 @@` — **`_send_done_message`**, the function I extended.
`@@ -5923,8 +6171,10 @@` — the re-gated DONE branch: replaced the literal `"Your presentation is ready. All quality checks passed."` with `self._send_done_message()`.

**PD-031 hunks in `phases.py`** (`git show 06bffcf21 -- phases.py | grep '^@@'`):
`@@ -8,6 +8,7 @@` — `import re`.
`@@ -774,6 +775,11 @@` — `_ETA_HISTORY_SIBLING_LIMIT = 20`.
`@@ -1858,8 +1864,87 @@` — `Engine._stage_timing_medians` and `Engine._client_eta_sentence`.

**My PD-313 hunk** (new commit `edc433413`, `phases.py` +17 −2): inside PD-042's `_send_done_message` (the `waived_count` parameter + appending the waived-checks sentence), a new `waived_n` computation just after `close()`'s gate loop, the `waived_count=waived_n` argument added to PD-042's re-gated call, and the new normal-close call before `print("DONE -- all gates passed.", flush=True)`. The only pre-existing line I removed is the old `def _send_done_message(self) -> None:` signature line (replaced by the same line with a parameter) — no PD-042/PD-031 behaviour is removed.

## Commit and remote proof

Change commit `edc433413` pushed to `origin/pd/fl05-engine-reporting`:

```
$ git push origin HEAD:refs/heads/pd/fl05-engine-reporting
   f0da9bcf1..edc433413  HEAD -> pd/fl05-engine-reporting
$ git ls-remote --heads origin refs/heads/pd/fl05-engine-reporting
edc4334137d4d8482cfb2c3823924d98b640cfe0	refs/heads/pd/fl05-engine-reporting
$ git rev-parse HEAD
edc4334137d4d8482cfb2c3823924d98b640cfe0
```

Local head = remote branch head = `edc4334137d4d8482cfb2c3823924d98b640cfe0`, 40 characters compared literally. The report commit is then pushed on top; its full sha and the fresh `git ls-remote` proof are in my handoff text, and the branch head after it is the report commit (the only difference from the change commit is this file).

Branch head after this report was first pushed, proven the same way:

```
$ git rev-parse HEAD
ccfa41fb4b5a21afd1ec5e805579a4db38e7ed89
$ git ls-remote --heads origin refs/heads/pd/fl05-engine-reporting
ccfa41fb4b5a21afd1ec5e805579a4db38e7ed89	refs/heads/pd/fl05-engine-reporting
```

The difference between `edc433413` and `ccfa41fb4` is this report file only. The true branch head at handoff is the final documentation commit; its full sha and `git ls-remote` output are in the handoff text.

## What I could not prove / notes

- **The line numbers in the carried-over text (`5654-5655`, `5729`) do not exist in the current file.** They are `PASS6-LAST.md` coordinates; the branch's PD-018b/PD-042/PD-031 work moved the file. I implemented the text's intent at the equivalent normal-close DONE branch and proved it there.
- **"coordinate with PD-018's wording unit"**: the exact sentence the spec gives is used — `{n} check(s) were waived at your request.` No PD-018 unit was found on this branch that owns this sentence, so there was nothing to reconcile; I did not invent alternative wording.
- **The waived-checks sentence is appended to `_compose_done_message`'s output**, per the binding amendment ("Call `_compose_done_message` … The waived-checks sentence is appended"). The full message begins `Your presentation is ready. Here is where to find it:` followed by the verified destinations and then the waived sentence; the carried-over sentence's leading `Your presentation is ready.` is therefore not duplicated.
- **`__main__.py` line 1382** (the finding's shell-door evidence) was not changed: the fix lives in `Engine.close()`, which every door reaches. I did not verify a non-engine door independently; that matches "the shell door, supervisor and board path were not checked" in the finding and is out of this unit's file scope.
- **Docstring/evidence only**: the change is 17 insertions / 2 deletions in `phases.py` and 137 insertions / 0 deletions in the test file. No manifest, SOP, install script, or shared file was touched (`update-skills.sh`, `universal-sops/_content-manifest.json`, `install.sh` untouched).
- **Scratch discipline**: `TMPDIR="$LOOP_ROOT/tmp/PD-313"`. The scratch worktree is `$TMPDIR/work` (created by `git worktree add --detach`, which must create the directory itself), the fixed-file backup is `$TMPDIR/phases.fixed.py`, and the two failure-set captures are `$TMPDIR/base-13.txt` and `$TMPDIR/head-13.txt`. These three files were written directly inside `$TMPDIR` with `cp`/shell redirection rather than through `mktemp -p "$TMPDIR"` — the worktree directory itself cannot be pre-created by `mktemp` because `git worktree add` creates it. No system temporary-directory path outside `$TMPDIR` appears in any command or output from this unit. The lane clone at `$LOOP_ROOT/worktrees/onboarding/FL05` was left clean (`git status` shows no changes there).
