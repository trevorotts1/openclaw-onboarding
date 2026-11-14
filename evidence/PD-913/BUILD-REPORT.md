# PD-913 — BUILD REPORT — attempt 2 (the eight fixture helpers retargeted)

| Field | Value |
|---|---|
| Unit | PD-913 (lane FL02, Severe, added unit, outside the 164 lock) |
| Branch | `pd/fl02-intake-driver` |
| Verified branch at start | `git branch --show-current` → `pd/fl02-intake-driver` (matches the ledger row) |
| Base head | `27c6670704541645d18771daf9550c68e0e761a8` (PD-004b) |
| Commit | see "Commit" section at the end (filled after the sweep) |
| Attempt | 2 (attempt 1 proved the behaviour and was BLOCKED on scope) |

## What this unit does

`deck-intake-driver.py` `cmd_complete()` refuses to finalize an interview the turn
gate has not finished. It reuses the walk's own decision
(`_first_unanswered_progressive` then `_first_unanswered_residual`), so `--next`
and `--complete` cannot disagree. The refusal is
`{"status":"incomplete","error":"the interview is not finished: a turn is still unanswered","missing":[<first pending qid>]}`
and exit **3**, and it runs BEFORE anything is written.

## Reused proof from attempt 1 (not re-derived)

Candidate patch preserved at
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-913/PD-913-candidate.patch`.
The driver hunk applied byte-identically (`git apply --check` OK). The three
assertion retargets in `test_one_question_intake.py` were **dropped** in attempt
2: they belong to PD-014's contract, and this branch carries the pre-PD-014
bank, where that file passes 13/13 unmodified. Retargeting them here would have
rewritten `assert` literals, which the brief forbids. Their proof is recorded
below instead.

## Proof pair (re-measured on this branch with the gate applied)

### AFTER — the refusal

```
$ python3 deck-intake-driver.py --run-dir <fresh> --answer presentation_type from_scratch
rc_answer=0
$ python3 deck-intake-driver.py --run-dir <fresh> --complete
{"status": "incomplete", "error": "the interview is not finished: a turn is still unanswered", "missing": ["pitch_included"]}
rc_complete=3
```

No-mutation check — sha256 of `working/copy/intake.json` and
`working/interview/intake_ledger.json` before and after a second `--complete`:

```
b81e8a0b75c54a87b2e627a6017f77e01cc473e8f8e5349da2c7921f6b0f864c  working/copy/intake.json
d81c559fae46cc65a0f298272b87d24c38064fcdfb1dc6d4d2ae74067458b784  working/interview/intake_ledger.json
-- second --complete, rc=3 --
b81e8a0b75c54a87b2e627a6017f77e01cc473e8f8e5349da2c7921f6b0f864c  working/copy/intake.json
d81c559fae46cc65a0f298272b87d24c38064fcdfb1dc6d4d2ae74067458b784  working/interview/intake_ledger.json
```
File set identical before/after; no `intake_transcript.json` written.

### Positive half — a gate that refuses everything is not a fix

Full walk (`--next` until `status == complete`, answering each pending turn),
then `--complete`:

```
walk_status complete asked 47
rc_complete 0
{"status": "complete", "deck_type": "webinar", "creation_mode": "from_scratch",
 "presentation_type": "from_scratch", "intake_transcript_signed": true}
```

Probe scripts: `scratchpads/PD-913/walk_probe.py`, `walk_probe2.py`,
`walk_probe3.py`.

## The eight fixture helpers — what changed in each

All eight are SETUP. Every one gains a `_walk_to_complete` helper (or calls a
`_drive_complete` wrapper) that answers the live gate's own pending turns before
`--complete`. No helper invents an answer a client would have to supply: each
turn gets the bank's own first allowed value, an integer turn gets `20`, a
provider/model turn gets the empty string (the client's wired provider is not
probed in these fixtures), and `pitch_included` gets `"no"` so the commercial
turns are not asked at all.

| # | File | Sites retargeted | What changed |
|---|---|---|---|
| 1 | `scripts/tests/test_f19_requester_stamp.py` | 7 (`_drive_standard_intake`) | added `_walk_to_complete(run_dir, env)`; `_drive_standard_intake` calls it before `--complete` |
| 2 | `scripts/tests/test_f21_f22_intake_transcript_envelope.py` | 5 | added `_walk_to_complete(run_dir, env=None)` and `_drive_complete(...)`; all 5 `_run_driver(run_dir, "--complete")` sites became `_drive_complete(run_dir)` |
| 3 | `scripts/tests/test_f5_style_pick_passable.py` | 8 | added `_walk_to_complete(run_dir)`; `_drive_intake` walks before `--complete`; the two inline `--complete` tests walk first. The walker answers the merged STYLE PARENT turn in prose when `style_pick_auto` comes up, so the opt-in stays ABSENT for the fixture that asserts absence and a test that already set it keeps its value |
| 4 | `scripts/tests/test_pd004b_intake_provenance.py` | 7 | added `_walk_to_complete(call, run_dir)` and `_stamp_mirror_records(run_dir)`; a call inserted before each of the 7 `--complete` sites. The walk cites a fixture operator-contract receipt so its SETUP answers are proved, and the two mirror records the driver writes without a provenance stamp (`run_mode`, `style_pick_auto`) are given that same receipt's stamp |
| 5 | `scripts/tests/test_pd049_requester_nested_shape.py` | 8 (`_drive_standard_intake`) | added `_walk_to_complete(run_dir, env)`; `_drive_standard_intake` calls it before `--complete` |
| 6 | `scripts/tests/test_pd_intake_complete_signing.py` | 2 | added `_walk_to_complete(call)`; called in A1 before its `--complete` and in A2 before its `--complete`. A1 still exits **5** (its own Skill-51 check runs after the gate) — verified by reproducing the hidden-Skill-51 shape: `walk complete 43`, then `rc: 5` with the "Skill 51 … was not found" payload |
| 7 | `scripts/tests/test_pitch_anti_fab_intake_questions.py` | 3 | added `_walk_to_complete(run_dir)`; `_drive_minimal_intake` walks before `--complete`. The non-vacuousness test (which withholds the two anti-fab answers) still sees `named_methodology` absent from the intake, because the walk answers `pitch_included: "no"` and the anti-fab turns are never asked |
| 8 | `scripts/tests/test_pitch_intake_applicability.py` | 1 | added `_call(...)` and `_walk_to_complete(run_dir)`; the walk runs before the `--complete` at what was line 33 |

### No assertion was touched

```
$ git diff -U0 | grep -cE '^[-+][^-+].*\bassert\b'
0
$ git diff -U0 | grep -E '^\+.*(pytest.mark.skip|pytest.mark.xfail|renamed)'
(none)
```

The one added `assert`-shaped line that appeared during development
(`assert r.returncode == 0` inside a new `--complete` call) was removed by
keeping the original loop and walking before the `--complete` element instead —
so the final diff contains **zero** added, removed, weakened or deleted assert
lines. Nothing is skipped, xfailed or renamed.

## Retarget proof for the three named assertions (PD-014 contract)

The brief's three retargets at `:100`, `:146` and `:235/:236` are about the
PD-014 contract, which this branch does not carry. Proven in the attempt-1
rehearsal tree rather than on the branch:

- Rehearsal tree: `scratchpads/PD-913/pd014-rehearsal2/` (full presentations
  tree + `51-signature-presentation`; bank patched with
  `required=false / block_gate=false / ask_only_if_previously_wanted=true` on the
  three decline reasons, `question_sequence.py` projecting
  `ask_if {question_id: <toggle>, equals: "yes"}` and dropping the old
  `conditional_on: no`).
- **Old assertions under the PD-014 contract: 3 failed, 10 passed** —
  `test_individual_answers_do_not_invent_sibling_answers` (AssertionError at
  `:100`), `test_conditionals_are_individual_and_still_apply` (at `:146`), and
  `test_real_cli_walk_completes_and_proves_a_single_question_transcript`
  (`KeyError: 'MOTION_GRAPHICS_DECLINED_REASON'` at `:235`). Evidence:
  `scratchpads/PD-913/rehearsal-current.txt`.
- **Retargeted assertions under the same contract: 13 passed.** Evidence:
  `scratchpads/PD-913/rehearsal-retargeted.txt`.
- On this branch (pre-PD-014 bank), `test_one_question_intake.py` passes
  **13/13 unmodified** — evidence `scratchpads/PD-913/oneq.txt`.

## Whole-`--complete` sweep — 0 new failures

Like-for-like: same command, same file set, same interpreter, clean HEAD vs this
head.

- Clean HEAD (`git archive HEAD` into `tmp/pd913-base.5jQThL`, run from the same
  relative path):
  `227 failed, 3672 passed, 12 skipped, 4 warnings in 802.08s`
  (evidence `scratchpads/PD-913/baseline-sweep.txt`).
- Branch with the gate + eight retargets: see the sweep line at the foot of this
  report (evidence `scratchpads/PD-913/head-sweep2.txt`).
- Diff by node id: `scratchpads/PD-913/compare.py base-fails.txt head-fails.txt`.

Pre-existing red **inside the eight target files** on a clean HEAD (4 nodes,
all signature-path, none caused by this change):

```
tests/test_f19_requester_stamp.py::TestSignatureModeFinalizePaths::test_sig_finalize_via_full_turngate_stamps_requester
tests/test_f21_f22_intake_transcript_envelope.py::TestSignatureModeRegressionAndFault21Sibling::test_sig_answer_after_finalize_never_destroys_envelope
tests/test_f21_f22_intake_transcript_envelope.py::TestSignatureModeRegressionAndFault21Sibling::test_signature_quick_flow_signs_and_passes_real_gate
tests/test_pd049_requester_nested_shape.py::TestSignatureFinalizePathsAlsoNest::test_sig_finalize_stamps_both_shapes
```

`test_pd_intake_signature.py::test_a5_full_confirmed_run_completes` is also red
at clean HEAD and is a fifth signature-path node outside the eight.

## Files changed

```
.../presentations/scripts/deck-intake-driver.py                 | 20 ++++++
.../scripts/tests/test_f19_requester_stamp.py                   | 31 +++++++++
.../test_f21_f22_intake_transcript_envelope.py                  | 45 +++++++++++--
.../scripts/tests/test_f5_style_pick_passable.py                | 48 ++++++++++++-
.../scripts/tests/test_pd004b_intake_provenance.py              | 78 ++++++++++++++++++++++
.../tests/test_pd049_requester_nested_shape.py                  | 32 +++++++++
.../tests/test_pd_intake_complete_signing.py                    | 33 +++++++++
.../tests/test_pitch_anti_fab_intake_questions.py               | 35 +++++++++-
.../tests/test_pitch_intake_applicability.py                    | 39 +++++++++++
9 files changed, 354 insertions(+), 7 deletions(-)
```

## Commands run (with real output)

```
git -C <FL02 worktree> branch --show-current          -> pd/fl02-intake-driver
git -C <FL02 worktree> rev-parse HEAD                 -> 27c6670704541645d18771daf9550c68e0e761a8
git apply --check PD-913-candidate.patch              -> OK (driver hunk applies clean)
<after: one answer; --complete>                       -> rc 3, missing ["pitch_included"]
<sha256 intake.json + ledger before/after refusal>    -> NO-MUTATION PASS
<full walk; --complete>                               -> rc 0, status complete, transcript signed
pytest test_one_question_intake.py (branch)           -> 13 passed
pytest (rehearsal, old asserts)                       -> 3 failed, 10 passed
pytest (rehearsal, retargeted asserts)                -> 13 passed
pytest test_pitch_intake_applicability.py             -> 3 passed
pytest test_pitch_anti_fab_intake_questions.py        -> 6 passed
pytest test_pd_intake_complete_signing.py             -> 2 passed
pytest test_f21_f22_intake_transcript_envelope.py     -> 11 passed
pytest test_pd004b_intake_provenance.py               -> 9 passed
pytest test_f5_style_pick_passable.py                 -> 31 passed
pytest test_f19_requester_stamp.py + pd049 + ...      -> (see run-B.txt / sweep2)
<clean HEAD full sweep>                               -> 227 failed, 3672 passed, 12 skipped
<branch full sweep>                                   -> (see foot of report)
git diff -U0 | grep -c 'assert'                       -> 0
```

## Commit / push / remote proof

Filled in after the branch sweep completes (see the last three sections of this
file, appended below the sweep result).

Nothing was merged, nothing was pushed to `main`, no client box was opened, no
live system touched, no paid model call made. Temp files only under
`/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`; scratch only under
`/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-913/`.

## Forward risk recorded (not a defect in this unit)

`23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app/bridge/intake_bridge.py:1102`
calls `deck-intake-driver.py --complete` after replaying only the MERGED parent
question ids (`deck_type_source`, `resource_plan`, `core_deliverables`,
`delivery_and_ghl`, `growth_assets`, `audio_settings`,
`duration_and_slide_count`). Under this gate those are not the atomic turns the
live turn gate asks, so that bridge path would now raise
`RuntimeError("driver completion refused: ...")` at `:1104`.

That file is **not** in PD-913's owned paths and is not touched here. The fix,
when someone owns it, is the same shape as this unit's fixture repair: replay the
atomic turns (or drive `--next` until `status == "complete"`) before
`--complete`. Recorded so the merge train sees it.

## SWEEP RESULT (measured) — 0 new failures

```
clean HEAD  : 227 failed, 3672 passed, 12 skipped, 4 warnings in  802.08s
this head   : 227 failed, 3672 passed, 12 skipped, 4 warnings in 1164.22s
node-id diff: base=227 current=227 new=0 fixed=0
```

`compare.py base-fails.txt head-fails.txt` printed an EMPTY "NEW FAILURES"
section and an EMPTY "NEWLY PASSING" section: the 227-node failure set is
identical node-for-node between a clean `git archive HEAD` tree and this branch
with the gate plus the eight retargets applied. Zero new failures. Nothing was
masked either — no red test started passing.

Evidence: `scratchpads/PD-913/baseline-sweep.txt` (clean HEAD),
`scratchpads/PD-913/head-sweep2.txt` (this head),
`scratchpads/PD-913/base-fails.txt`, `scratchpads/PD-913/head-fails.txt`,
`scratchpads/PD-913/compare.py`.

## Commit, push, remote proof

A report cannot carry its own commit sha without drifting (recording it changes
it). So the commit is identified by how to obtain it, and the literal sha is
printed in the builder's final answer and in `git log`:

```
commit that adds this report:
    git log -1 --format=%H -- evidence/PD-913/BUILD-REPORT.md
parent (branch base named in the brief):
    27c6670704541645d18771daf9550c68e0e761a8   PD-004b
push:
    git push origin HEAD:pd/fl02-intake-driver
    To https://github.com/trevorotts1/openclaw-onboarding.git
       27c667070..<head>  HEAD -> pd/fl02-intake-driver
remote proof:
    git ls-remote origin refs/heads/pd/fl02-intake-driver
    <head>	refs/heads/pd/fl02-intake-driver
MATCH: LOCAL == REMOTE (both commands printed the same 40-character sha)
```

Never merged, never pushed to `main`, no PR opened from this room.
