# PD-068 — BUILD REPORT (deepseek-chain, D-13 HOLD branch)

Unit: PD-068 · repo `trevorotts1/openclaw-onboarding` · branch `pd/fl18-dispatcher--hold-d13`
Lane clone: `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL18--hold-d13`
Build worktree (mine, detached): `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-068/wt-n2tQQI`
Base worktree (pristine comparison): `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-068/base-1kUEZo`

This is a BUILD report. It states what was built and what the commands returned. It issues
no verdict — the opus-chain reviewer does that.

## Branch and live head, confirmed first

`git ls-remote --heads origin refs/heads/pd/fl18-dispatcher--hold-d13` **returned nothing at
start** (rc=0, empty stdout): the hold branch did not exist on the remote. The lane clone was
on the branch name locally at `1a476d2c` with `ahead=0 behind=14` of `origin/main` — i.e. it
carried **no** lane work and **not PD-079**, which this unit depends on.

Live heads at start (`git ls-remote --heads origin 'refs/heads/pd/fl18*'`):

```
be56b5a19da62ab55873937a406097a170d0b1d2	refs/heads/pd/fl18-dispatcher
e9393913975be56882b20b14544037ded470c314	refs/heads/pd/fl18-dispatcher--hold-d39
```

`pd/fl18-dispatcher` (be56b5a1) is where PD-079 is accepted, and PD-079 is this unit's
hard dependency ("must be ACCEPTED, that is QC-passed, first"). So the unit was built on
**be56b5a19**, not on the stale lane-clone tip and not on `origin/main` (which lacks PD-079).
The lane clone was left untouched and clean (`git status --porcelain` → empty, both before
and after).

Base inventory of that head, quoted so the dependency is checkable:

```
$ git log --oneline e939391..be56b5a1
be56b5a19 PD-079: correct the dispatcher's stale text and home-folder guess
3a6049451 PD-078: remove the slot-reserve claim
b8f7b8d21 PD-067: the per-slide quality merge fails closed
9da9718ae PD-065 QC: an advisory gate note no longer flips the worker's pass to a fail
ed11309e7 PD-065: state the real prompt band from the shared gate
6f65f416e PD-300: stamp the grading provider and model into every merged quality report
3b9cb6884 PD-304: qc fix restore GENERIC_CONTRACT anchor to 1569 ...
6566a6f2c PD-304: compose the P-SHIFT-QC contract at the module tail
7b0b6d91b PD-304: give the priority-shift step a contract that matches its check
```

## Spec quoted (the text implemented)

`.../fable-reviews-2026-11-11/03-presentation-department/FINAL/01-BUILD-SPEC.md`, section
`### PD-068`:

> **Change:** (1) rewrite the three report contracts (lines 1240–1292) to describe the fields
> and say "report what you found; a failing report is a correct output". (2) In `dispatch_one`,
> for a quality step whose report parsed and says `pass: false`, do not retry: return a new
> status `qc_failed` with the report's own reasons, and add it to `_FAILING_STATUSES`.
> (3) Before a quality step's model call, compare the routed model family with the author stamp
> of the consumed files (`execution_stamp`); when equal and no other eligible route exists,
> return `error` with "no independent model is available to grade this step".
>
> **Acceptance:** stubbed model returns `pass: false` → one call, status `qc_failed`, no second
> call; author and grader on the same family with one route → zero calls and the plain reason;
> two families → one call on the other family.

Consolidation amendment (binding), also quoted:

> PD-204 (lane FL28) puts the same rule in the router; this unit keeps the dispatcher-side
> refusal as the second check behind it. Use one helper for the model family; if PD-204's
> `_model_family` is on the base when this unit is built, import it instead of writing a second one.

PD-204 is **not** on this base (`grep -n "_model_family" model_router.py` → no definition), so
the rule was written once, in `dispatcher.py`, and it delegates to `model_router._model_family`
the moment PD-204 lands — one helper, not two.

## Files changed (commit `efeb1dd7b`)

```
222  26  .../presentation_job/dispatcher.py
248   0  .../tests/test_pd_dispatcher_grader_independence.py
2 files changed, 470 insertions(+), 26 deletions(-)
```

No shared file touched: `update-skills.sh`, `universal-sops/_content-manifest.json` and
`install.sh` are absent from `git show --name-only HEAD`.

### 1. The three report contracts (dispatcher.py, `ARTIFACT_CONTRACTS`)

`P1Q-COPY-QC`, `P-PROMPT-QC`, `P-TYPO-QC` — the three QC report contracts that sat at old
lines 1240–1292 — now open with "Report what you found; a failing report is a correct output."
and describe each field honestly:

* `criteria` — ≥6 named criteria, scored from the real content;
* `average` — the arithmetic mean actually measured; it must not exceed that mean by >1.0
  (inflation is still refused); the 8.5 floor is now stated as the gate's decision, not the
  reporter's;
* `triggered_autofails` — `[]` only when there is genuinely nothing, otherwise the real AF-* ids;
* `pass` — `true` when the work meets the bar, `false` when it does not; never true over a real
  AF-* entry or a sub-8.5 mean;
* `qc_independence` — unchanged, still refuses a self/builder grader.

Removed on purpose: the `pass:true` instruction and the "must be >= 8.5" demand on the value
the model reports. The verifier still enforces both; the contract no longer tells the model to
fake them.

### 2. `qc_failed` (dispatcher.py, `dispatch_one`)

After publication and **before** the verifier, `_qc_report_failure()` parses the quality step's
own report. If it parses as a JSON object with `pass is False`, the attempt returns
`DispatchResult(status="qc_failed", reasons=<the report's own reasons>)` — one call, no retry,
report left on disk. Reasons are taken from the report itself, in order: `reasons` / `findings`
/ `failures` lists, `triggered_autofails` / `autofails_triggered` ids, then any criterion scored
below 8.5, then a single `<phase> report says pass: false` fallback.

`qc_failed` was added to `_FAILING_STATUSES`. That frozenset has exactly two behavioural
readers (`dispatcher.py:10360` repeat ceiling, `dispatcher.py:10382` outcome cap), so the new
status parks/blocks exactly like `error`/`exhausted` with no other edit.

### 3. The family gate (dispatcher.py, `dispatch_one` + three helpers)

Inserted before the attempt loop, for `_is_qc_phase` phases only:

* `_graded_author_model()` (PRES-042/PD-300, already on the base) supplies the AUTHOR model of
  the consumed files — the execution stamp reader is reused, never duplicated;
* `_model_family()` — PD-204's rule: text after the last `/`, lower-cased, up to the first
  non-letter; delegates to `model_router._model_family` when present;
* `_grader_route_decision()` — `resolve_route(phase_id, mode=…)` read once, before the call, so
  the candidate list can be inspected;
* `_independent_grader_decision()` — refusal or pin:

  - same family, no eligible candidate on another family → `("no independent model is available
    to grade this step", None)`; `dispatch_one` records the sidecar and returns
    `DispatchResult("error", 0, [reason])` — **zero model calls**;
  - same family, an eligible candidate on another family exists → that `{provider, model}` is
    returned as `route_override` and rides into every attempt (it wins over a heal rung's pin,
    so a heal can never re-point a quality step onto the author's family);
  - different family → no pin, normal dispatch;
  - every unknown is permissive, never a fabricated refusal: non-QC phase, unstamped/revised
    author (`""` = UNKNOWN), unknown family, router disabled/broken, or no route at all
    (`dispatch_complete` owns that park).

## Row A1 — proven with real output

Command (head, my worktree):

```
$ python3 -m pytest tests/test_pd_dispatcher_grader_independence.py -q
9 passed in 0.76s
```

Row-by-row, quoting the assertion each test makes:

1. **stubbed model returns `pass: false` → one call, status `qc_failed`, no second call.**
   `test_a_failing_report_is_one_call_and_qc_failed` asserts `calls["n"] == 1`,
   `result.status == "qc_failed"`, `result.reasons == ["P1Q-COPY-QC report says pass: false"]`,
   and that the published report is still on disk with `pass is False`. It also asserts
   `D.DISPATCH_RETRY_CAP > 1` first, so "no second call" cannot be satisfied by a cap of one.
   `test_qc_failed_is_a_failing_status` asserts the status is in `_FAILING_STATUSES`.
   Control: `test_a_passing_report_still_reaches_the_verifier` runs the identical harness with
   `pass: true` and gets `status == "ok"` after exactly one call and a verifier pass.
2. **author and grader on the same family with one route → zero calls and the plain reason.**
   `test_same_family_with_one_route_makes_zero_calls` (author `deepseek/deepseek-chat`, one
   eligible candidate `deepseek-chat`): the stub raises if called, and the test asserts
   `calls["n"] == 0`, `status == "error"`,
   `reasons == ["no independent model is available to grade this step"]`, and that no report
   was written.
3. **two families → one call on the other family.**
   `test_two_families_pin_the_other_family_and_call_once`: candidates `deepseek-chat` and
   `ollama-cloud z-ai/glm-4.6`; the captured `route_override` is
   `{"provider": "ollama-cloud", "model": "z-ai/glm-4.6"}` and `calls["n"] == 1`.
   `test_model_family_follows_the_pd204_rule` pins the helper to PD-204's definition.

## Failure proof (the mutation that turns it RED, then reverted)

Both production checks were neutralised in place (`if qc_failure is not None:` →
`if False and qc_failure is not None:`, `if grader_refusal:` → `if False and grader_refusal:`)
and the same test file re-run:

```
2 failed, 7 passed in 0.52s
FAILED tests/test_pd_dispatcher_grader_independence.py::test_a_failing_report_is_one_call_and_qc_failed
FAILED tests/test_pd_dispatcher_grader_independence.py::test_same_family_with_one_route_makes_zero_calls
```

(with the second failing on `AssertionError: no model call may happen without an independent
grader` from inside the stub — proof the gate really is what stops the call).

Restored from a byte snapshot; `shasum -a 256` of the restored file equals the snapshot
(`f1161bbe752edab143d111bec136e13199ff88fbe9c2c49a2dc0acb995077f67`), `grep -c "if False and"` → `0`,
and the suite is green again (`9 passed in 0.76s`).

## BEFORE / AFTER by test id

| test | base `be56b5a1` | head `efeb1dd7b` |
|---|---|---|
| `test_the_three_report_contracts_allow_an_honest_failure` | FAIL | PASS |
| `test_a_failing_report_is_one_call_and_qc_failed` | FAIL | PASS |
| `test_qc_failed_is_a_failing_status` | FAIL | PASS |
| `test_a_passing_report_still_reaches_the_verifier` | PASS | PASS (control leg — correct on both) |
| `test_same_family_with_one_route_makes_zero_calls` | FAIL | PASS |
| `test_two_families_pin_the_other_family_and_call_once` | FAIL | PASS |
| `test_an_unknown_author_never_invents_a_refusal` | FAIL | PASS |
| `test_a_non_qc_phase_is_never_gated` | FAIL | PASS |
| `test_model_family_follows_the_pd204_rule` | FAIL | PASS |

Base run, quoted: `8 failed, 1 passed in 0.65s` (the new test file copied into a pristine
`be56b5a1` worktree; the one pass is the `pass: true` control, which is the honest result —
that leg exercises nothing this unit adds).

## Whole-directory runs (regression)

Same command, same machine, two worktrees — head first, then the pristine base:

```
$ python3 -m pytest tests -q          # head, efeb1dd7b
221 failed, 3688 passed, 12 skipped, 4 warnings in 1152.97s (0:19:12)

$ python3 -m pytest tests -q          # base, be56b5a1 (my test file NOT present)
222 failed, 3678 passed, 12 skipped, 4 warnings in 904.45s (0:15:04)
```

Failure-set difference by test id (222 base ids vs 221 head ids):

```
NEW_FAILURES_ON_HEAD: 0
GONE_ON_HEAD: 1
  - tests/test_pres026_media_resume.py::test_two_workers_same_run_single_operation
```

Zero new failures. The one id that changed is a flaky concurrency test outside every path this
unit touches, and it went the other way (red on base, green on head). The +10 passing tests are
this unit's 9 plus that one. The tree is broadly red on both sides (222/221 ids) — that is the
state of this lane's base commit, not a product of this change.

**Clean, like-for-like check on the surface this unit actually touches** (same 10 files, no
other agent's pytest competing for the CPU):

```
head (efeb1dd7b): 3 failed, 130 passed in 75.21s
base (be56b5a1) : 3 failed, 121 passed in 75.02s
```

The three failures are identical on both sides and are **pre-existing**:
`tests/test_qc_aggregate.py::test_aggregate_passes_with_six_genuine_reports`,
`::test_aggregate_writes_final_qc_report_file`,
`::test_cli_default_mode_exit_0_on_pass` — they need `graded_by_model` in their seeded reports
(FIX 33) and fail on the pristine base with the same message. Not an owned path, not fixed here.

## Hunk attribution (merge-base of the pushed branch to my HEAD)

The pushed branch `pd/fl18-dispatcher--hold-d13` is cut at `be56b5a1`. Its merge-base with
`origin/main` is `1a476d2cbc`; everything between `1a476d2c` and `be56b5a1` is **sibling lane
work, not this unit**:

```
 .../scripts/presentation_job/dispatcher.py         | 386 ++++++++++++++++-----
 .../presentation_job/parallel_prompt_worker.py     |  58 +++-      (PD-065)
 .../presentation_job/priority_shift_items.py       |  55 +++      (PD-304)
 .../tests/test_pd_dispatcher_grader_stamp.py       | 131 ++++     (PD-300)
 .../tests/test_pd_dispatcher_prompt_band.py        | 167 ++++++    (PD-065)
 .../tests/test_pd_dispatcher_qc_merge_fails_closed.py | 94 ++++   (PD-067)
 .../tests/test_pd_dispatcher_stale_text.py         |  69 +++      (PD-079)
 .../tests/test_pd_priority_shift_items.py          | 161 +++++     (PD-304)
 .../tests/test_pres001_unit_contracts.py           |   5 +-       (PD-067)
```

My commit adds exactly two files, and my `dispatcher.py` hunks are:

```
@@ -859 +859,8 @@            _FAILING_STATUSES
@@ -1243,2 +1250,2 @@        ARTIFACT_CONTRACTS
@@ -1253,8 +1260,11 @@
@@ -1275,8 +1285,10 @@
@@ -1288,3 +1300,5 @@
@@ -1292 +1306,2 @@
@@ -3335,0 +3351,141 @@      new helpers after _graded_author_model
@@ -5629,0 +5786,17 @@       dispatch_one: gate before the loop
@@ -5652,3 +5825,6 @@        dispatch_one: grader pin wins over the heal pin
@@ -5747,0 +5924,20 @@       dispatch_one: qc_failed return
```

**Overlap with PD-079 (the dependency) — named, not duplicated.** PD-079's dispatcher hunks are
old lines 5568–5571 (a ROOT-CAUSE comment), 8454–8457 and 8462–8464
(`_json_load_manifest_fallback`) and 11125 (`build_parser` help). None intersects any hunk
above. PD-079 already made the fallback resolve the manifest through `_qc_manifest_for_run()`,
which is the resolver `_graded_author_model` uses — so this unit gets the correct manifest for
free and does not repeat the fix.

**Overlap with PD-079 on the non-hold branch of the same name.** PD-079 is accepted at the head
of `pd/fl18-dispatcher`; this hold branch is cut from that head, so it *contains* PD-079 rather
than re-implementing any of it.

## Remote-head proof

Push 1 — the code commit:

```
$ git rev-parse HEAD
efeb1dd7b5728b1ed8188479429843df2962c085
$ git ls-remote --heads origin refs/heads/pd/fl18-dispatcher--hold-d13
efeb1dd7b5728b1ed8188479429843df2962c085	refs/heads/pd/fl18-dispatcher--hold-d13
```

Push 2 — this report (fast-forward off push 1):

```
$ git rev-parse HEAD
6b2760afe1a3872662c8e5763895643314b2f9d2
$ git ls-remote --heads origin refs/heads/pd/fl18-dispatcher--hold-d13
6b2760afe1a3872662c8e5763895643314b2f9d2	refs/heads/pd/fl18-dispatcher--hold-d13
```

40 characters, compared literally, both times. Branch line: `be56b5a19` (base, PD-079) →
`efeb1dd7b` (PD-068 code) → the evidence commits on top of it (this file describes pushes 1 and
2; later evidence-only commits follow, and the live head is whatever `git ls-remote` prints). No
commit after `efeb1dd7b` touches a production file. Nothing was merged (D-13 HOLD) and no PR was
opened.

## Anything unproved / honest limits

1. **The fan-out branch is not gated.** `dispatch_one` returns into
   `_dispatch_phase_fanout_units()` before the new gate, so a QC phase declared with a manifest
   `fanout` field (the image QC family) does not go through the family comparison. The spec's
   text names `dispatch_one`'s model call; the acceptance rows name the single-target path. This
   is a real gap for fan-out QC phases and should be its own unit if D-13 is answered yes.
2. **The gate is only as good as the stamp.** An unstamped or post-hoc-edited consumed file
   yields no author model, and the gate allows the call (permissive). Fail-closed was rejected
   here on purpose: the spec's rule fires on *equal families*, and absence of a stamp is not
   evidence of an equal family.
3. **Whole-directory failures are not all attributable by this report.** The numbers above are
   set differences between two runs of the same command in the same environment; they show what
   *changed*, not the cause of every pre-existing red test.
4. **`test_qc_aggregate.py` was already red on the base** (3 tests, `graded_by_model` seeds).
   Reported, not fixed — not an owned path and not this unit.
5. **No test asserts the old contract wording**, so the rewrite could not be caught by an
   existing test; it is proven only by the new contract assertions.
6. **A hold branch is not a merge.** No PR was opened and no merge was attempted.
