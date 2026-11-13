# PD-031 — tell the client roughly how long is left — BUILD REPORT

- **Unit:** PD-031
- **Lane:** FL05
- **Repository:** trevorotts1/openclaw-onboarding
- **Branch:** `pd/fl05-engine-reporting`
- **Commit:** `06bffcf210ce220b2c8bc1a145e68c344c6e629c`
- **Base:** `afd4a7571` (PD-042)
- **Builder:** deepseek-chain

## Pre-existing work on this branch — NOT mine, not disturbed

| Unit | Commit | What it put on this branch |
|---|---|---|
| PD-018b | `f8cfbef10` (repair report), `aa506ba7e` + `414c715ab` (code) | client labels, empty-string hidden phases, rendered-N count, non-empty-label fallback |
| PD-042 | `afd4a7571` | `phases.py` +192: the DELIVER block, the `_block` signature change, `_send_done_message` and the `close()` DONE path, with PD-018b's behaviour preserved underneath |

`phases.py` is the file both of them touched. My work is purely additive
(85 insertions, 0 deletions in that file — see the proof below), and the
other units' lines are still present and were re-quoted.

## What the change is

When a visible step starts, the client's start message now ends with
`About <N> minutes to go.`

`N` = the sum of the **median** recorded `duration_s` of the phases still
ahead of the run, in whole minutes, rounded.

Source: the box's own stage-timing history — `working/telemetry/stage-timings.jsonl`,
`event == "phase_exit"` rows. That is the same source `eta` is filled from
today (`Engine._observed_stage_seconds`, `Engine._emit_stage_timing`, and the
PRES-036 ready-queue `eta_basis: "observed_critical_path"` payload). This run's
own file is read first, then the newest 20 sibling run dirs beside it under the
same runs root, so a fresh run still speaks from what the box measured before
it.

No history → the sentence is not appended. Phase already done / deferred /
obsolete → not counted as remaining. A phase with no recorded row contributes
nothing (it is simply absent from the sum) — never a guessed constant.

Only the START message gets the sentence; the done message never does.

### Files changed

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/phases.py` | +85 / −0: `import statistics`; `_ETA_HISTORY_SIBLING_LIMIT = 20`; the PD-031 branch in `_render_client_report_msg`; `Engine._stage_timing_medians()`; `Engine._client_eta_sentence()` |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_engine_eta.py` | new, +96: four tests proving acceptance row A1 and two guards |

No file outside the unit's owned paths was edited. No shared file
(`update-skills.sh`, `universal-sops/_content-manifest.json`, `install.sh`) was
touched.

## Which lines are mine vs. the other two units (same file)

My hunks, by post-change line number in `phases.py`:

| Lines | Mine |
|---|---|
| 11 | `import statistics` |
| 778–782 | `_ETA_HISTORY_SIBLING_LIMIT` constant block |
| 1867–1873 | the PD-031 start branch in `_render_client_report_msg` |
| 1876–1946 | `_stage_timing_medians()` and `_client_eta_sentence()` |

PD-018b's lines, still present (post-change line numbers):

```
1771:    def _client_rendered_phases(self, phases: List[Phase]) -> List[Phase]:
1776:        PD-018b item-4 ruling: N in "Step {k} of {N}" must be the number of
1808:    def _phase_client_meta(self, phase: Phase) -> Tuple[str, bool]:
1826:        PD-018b: returns "" (the caller sends nothing) when the phase is
```

PD-042's lines, still present (post-change line numbers):

```
748: #: PD-042. The one sentence a client receives when the style-pick wait expires
751: STYLE_PICK_TIMEOUT_SENTENCE = (
759: DONE_WITHHELD_EVENT = "report.done_withheld"
764: TELEPROMPTER_NO_LINK_SENTENCE = (
864: def _compose_done_message(run_dir: Path) -> str:
892: def _style_pick_messages(run_dir: Path) -> List[str]:
6105:    def _send_done_message(self) -> None:
```

`git show --stat 06bffcf21` — the commit is additive only:

```
 .../scripts/presentation_job/phases.py             | 85 +++++++++++++++++++
 .../scripts/tests/test_pd_engine_eta.py            | 96 ++++++++++++++++++++++
 2 files changed, 181 insertions(+)
```

## Acceptance row A1 — the pair, measured

A1: *fixture history with medians 4, 6, 10 minutes → at the first step the
message says "About 20 minutes to go."; empty history → no sentence.*

### BEFORE — `afd4a7571`, the new test file copied into a clean detached worktree at that base

```
$ cd /Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-031/base-afd4a7571/23-ai-workforce-blueprint/templates/role-library/presentations/scripts
$ grep -c _client_eta_sentence presentation_job/phases.py
0
$ python3 -m pytest tests/test_pd_engine_eta.py -q
E       AssertionError: Step 2 of 3 — P-B — starting
E       assert False
E        +  where False = <built-in method endswith of str object at 0x107b27830>('About 4 minutes to go.')
E        +    where <built-in method endswith of str object at 0x107b27830> = 'Step 2 of 3 — P-B — starting'.endswith
FAILED tests/test_pd_engine_eta.py::TestEtaFromRecordedDurations::test_first_step_says_about_twenty_minutes_to_go
FAILED tests/test_pd_engine_eta.py::TestEtaFromRecordedDurations::test_the_median_is_the_median_not_the_sum_of_rows
2 failed, 2 passed in 0.11s
```

(The two that "passed" on the baseline are the two NEGATIVE rows: empty history
says nothing, and the done message carries no eta. Both are true before the
change too, by absence — that is exactly the control.)

### AFTER — this commit, same test file

```
$ cd /Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL05/23-ai-workforce-blueprint/templates/role-library/presentations/scripts
$ python3 -m pytest tests/test_pd_engine_eta.py -q
....                                                                     [100%]
4 passed in 0.07s
```

The headline assertion in the passing run is exact equality, not a substring:

```python
msg = eng._render_client_report_msg(eng.manifest.phase("P-A"), "start")
assert msg == "Step 1 of 3 — P-A — starting About 20 minutes to go."
```

with fixture rows recorded as `P-A` 4 min, `P-B` 6 min, `P-C` 10 min — 4+6+10 = 20.

Second guard (`test_the_median_is_the_median_not_the_sum_of_rows`): three rows
for one phase of 1, 4 and 40 minutes → the sentence says 4, not 45 (a sum) and
not 15 (a mean).

## Regression — same tests, before and after

The lane's own PD-042/PD-018b surface, run before and after the change, both
green and unchanged:

```
$ python3 -m pytest tests/test_pd_engine_client_messages.py tests/test_pd_engine_operator_review.py \
    tests/test_pd_engine_process_certificate.py tests/test_pd_report_sanitize.py tests/test_pd_report_throttle.py -q
BEFORE: 30 passed in 1.25s
AFTER : 30 passed in 1.08s
```

## UNDETERMINED / not a claim I am making

Two test files on this branch are RED before my change and RED after it, with
identical counts — 14 failed, 27 passed on both runs of
`tests/test_pres036_ready_queue.py tests/test_engine_client_report.py tests/test_pd_engine_client_copy.py`.
Cause, measured: the only `PIPELINE-MANIFEST.json` in this worktree
(`universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`, v75) declares
`client_label` on **0** of its 56 phases, so PD-018b's renderer correctly
returns `""` and the label assertions fail. That is a manifest/base condition,
not my change: PD-018b's own report already records the PD-018a manifest
dependency. I did not touch either test file.

`tests/test_pres036_ready_queue.py::test_ready_queue_beats_wave_join_on_identical_fixtures`
fails on the detached `afd4a7571` baseline too (1 failed, 8 passed both before
and after) — a timing fixture, pre-existing.

A full `tests/` sweep of this worktree ran once after the change and finished
`252 failed, 3660 passed, 12 skipped` in 748.85s. I did **not** run the same
sweep on the baseline, so I am not claiming that number is unchanged — it is
reported as measured, and the before/after pair above is the evidence I stand
on.

## Commit and remote proof

```
$ git push origin pd/fl05-engine-reporting
   afd4a7571..06bffcf21  pd/fl05-engine-reporting -> pd/fl05-engine-reporting

$ git rev-parse HEAD
06bffcf210ce220b2c8bc1a145e68c344c6e629c
$ git rev-parse origin/pd/fl05-engine-reporting
06bffcf210ce220b2c8bc1a145e68c344c6e629c
$ git ls-remote origin refs/heads/pd/fl05-engine-reporting
06bffcf210ce220b2c8bc1a145e68c344c6e629c	refs/heads/pd/fl05-engine-reporting
```

Local head = remote branch head = `06bffcf210ce220b2c8bc1a145e68c344c6e629c`.

## Temp discipline

Every temp file in this unit was made with `mktemp -p "$TMPDIR"` where
`TMPDIR="/Volumes/mac mini m4/swarm-contract/pd-fix/tmp"`. No `/tmp`,
`/private/tmp` or `/var/folders` path was named or written by this unit's own
commands. Scratch lives at
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-031`.
