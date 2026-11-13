# PD-045 — decide "legitimately skipped" and "provider failure" from structured facts, not words — BUILD REPORT

- **Unit:** PD-045
- **Lane:** FL05
- **Repository:** trevorotts1/openclaw-onboarding
- **Branch:** `pd/fl05-engine-reporting`
- **Change commit:** `fd160d147a8a791d7133f336258135559d6ae303`
- **Report commit:** this file is a documentation-only commit on top; the branch
  head after it is the value `git ls-remote` returns and is recorded below.
- **Base:** `9504866a6933c3eeea1922cf0194d8986c5f746a` (branch head before this unit)
- **Builder:** deepseek-chain

## Spec quoted (what was implemented)

From `01-BUILD-SPEC.md`, section "### PD-045 — Decide "legitimately skipped" and
"provider failure" from structured facts, not words":

> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> (a) Also fix `heal.classify_failure` (`heal.py` lines 78-98): it chooses the recovery path by looking for words ("402", "429", "provider", "timeout", "waiver") in the failure text. Give it a `failure_kind` argument that the two call sites in `phases.py` fill from facts they already hold (a script's exit code, a caught exception's type, an HTTP status the transport returned); use the words only when `failure_kind` is absent, and log `heal.classified_by_text` each time that happens. New acceptance row: a check message that contains the word "provider" and has `failure_kind="check_failed"` is not routed as a provider outage. (b) If `phase_verifiers.py` must change, report `BLOCKED: needs phase_verifiers.py owned by FL17`. (c) Finding PD-111 is its own unit in lane FL15.
>
> **Carried-over unit text (from `01-BUILD-SPEC.md`, section PD-045; ids, decisions and lanes already converted to final):**
>
> - **Change:** `phases.py` `_phase_is_gate_declined` (lines 1857–1871) stops reading the joined notes for the words "defer", "waived", "gate", "declined". Read `phase_verifiers.py` fully first; give `verify()` results for the gate-decline cases a structured marker (for example a third return value or a note object `{"kind": "gate_declined", "gate": "<name>"}`) and have `_phase_is_gate_declined` return true only on that marker. FL05 owns the call site; if `phase_verifiers.py` must change, report `BLOCKED: needs phase_verifiers.py` so the orchestrator assigns it to this lane explicitly.
> - **Acceptance:** a passing verifier whose note text contains "the gate was declined by nobody; deferred maintenance" without the marker does **not** defer the phase; a real decline with the marker does.

## BLOCKED (partial) — the literal `verify()` marker

`phase_verifiers.py` is **not** in FL05's owned files (it is FL17's). It was not
edited. Therefore the literal carried-over contract — a third return value or a
`{"kind": "gate_declined", "gate": "<name>"}` note object emitted by
`verify()` — is **not built**.

**BLOCKED: needs phase_verifiers.py owned by FL17.**

Instead, the FL05-owned call site decides from the *same* structured facts the
verifier itself reads — the manifest's `defers_unless` gate against the run's
recorded intake answers (`presentation_job.defers.phase_is_deferred` /
`evaluate_defers_unless`). That is a structured marker held by the engine, not
words, and it proves the acceptance row below without another lane's file.

## What the change is

1. **`heal.classify_failure(reason, failure_kind=None)`** — a structured
   `failure_kind` now decides the class. Word lists run only when it is absent,
   and every word-based decision prints `heal.classified_by_text: <reason>` to
   stderr.
2. **The two `phases.py` call sites that choose a recovery path fill it from
   facts they already hold:**
   - `_run_script_phase` (class dispatch after rung-1 exhaustion):
     `subprocess.TimeoutExpired` → `failure_kind="timeout"`; `OSError` →
     `"exec_os_error"`; an exec exit code of 146 (HTTP 402 masked by the shell,
     402 & 255) → `"exit_code:146"`. Any other exit code is **not** decisive,
     so the captured stderr still supplies the evidence (and is logged as
     `heal.classified_by_text`).
   - `_heal_or_fail_agent_phase` (three wait outcomes): the substance
     verification failure → `failure_kind="check_failed"`; dispatcher retry
     ceiling → `"dispatcher_retry_ceiling"`; produced nothing →
     `"produced_nothing"`.
3. **`Engine._phase_is_gate_declined`** no longer joins the verifier's notes.
   It requires the phase to have a manifest `defers_unless` gate and to pass its
   substance verifier, then returns `phase_is_deferred(phase, intake)` — true
   only when the recorded intake answers do not satisfy the gate.
   `phase_verifiers.py` untouched.

## Files changed

```
44	2	presentation_job/heal.py
43	15	presentation_job/phases.py
```
plus `tests/test_pd_engine_pd045_structured_facts.py` (new, 12 tests).
(Paths under `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/`.)

No shared file (`update-skills.sh`, `universal-sops/_content-manifest.json`,
`install.sh`) was touched. No file outside the lane's owned paths was edited.

## Row proofs

### Acceptance (spec text): words without the structured fact do not defer; a real decline does

```
$ python3 -m pytest tests/test_pd_engine_pd045_structured_facts.py -v
... 12 passed in 0.21s
```

The four gate-decline cases, by id:

| id | what it asserts | result |
|---|---|---|
| `TestGateDeclineStructuredFacts::test_words_alone_do_not_defer` | verifier PASS whose note says `NOTE: the gate was declined by nobody; deferred maintenance`, phase has no `defers_unless` → `_phase_is_gate_declined` is **False**; the same assertion also evaluates the OLD word rule on that text and asserts it **True** (so the test kills the old behaviour) | PASSED |
| `TestGateDeclineStructuredFacts::test_real_structured_decline_defers` | `defers_unless = 'intake.want_vsl_page == "yes"'`, intake `{"want_vsl_page": "no"}` → **True** | PASSED |
| `TestGateDeclineStructuredFacts::test_satisfied_gate_is_not_a_decline` | gate satisfied, verifier notes still carry the decline words → **False** | PASSED |
| `TestGateDeclineStructuredFacts::test_intake_file_fallback` | no `state["intake"]`; `working/copy/intake.json` supplies the structured answers → **True** | PASSED |

### New acceptance row from amendment (a): a check message naming "provider" is not a provider outage

```
$ python3 -c "..."   # live classifier
heal.classified_by_text: upstream provider replied HTTP 429
class= provider_error                                  # no kind  -> words path (logged)
class= verifier_substance                              # failure_kind="check_failed"
```

By id:

| id | assertion | result |
|---|---|---|
| `TestFailureKind::test_check_message_with_provider_word_is_not_a_provider_outage` | `classify_failure(<check message containing "provider">, failure_kind="check_failed") == FAILURE_VERIFIER_SUBSTANCE`; the same text **without** a kind `== FAILURE_PROVIDER_ERROR` | PASSED |
| `TestFailureKind::test_timeout_fact_is_not_a_provider_outage` | `failure_kind="timeout"` beats the word `402` | PASSED |
| `TestFailureKind::test_exec_os_error_fact_is_transient` | `failure_kind="exec_os_error"` beats the word `provider` | PASSED |
| `TestFailureKind::test_masked_402_exit_code_is_a_provider_fact` | `"exit_code:146"` → provider; `"exit_code:1"` → transient | PASSED |
| `TestFailureKind::test_classified_by_text_is_logged_only_on_the_words_path` | `heal.classified_by_text` appears on stderr on the words path and is absent when a kind is given | PASSED |
| `TestAgentPhaseRouting::test_check_failed_takes_regenerate_not_failover` | engine routes the substance-failed agent phase to `rung2_regenerate`, never `rung2_provider_failover` | PASSED |
| `TestAgentPhaseRouting::test_without_the_kind_the_old_words_path_fails_over` | BEFORE control: same message, no kind → `rung2_provider_failover` fires | PASSED |

## Failure proof — mutation that turns the proof RED, then reverted

`git show HEAD~1:<file> > <file>` for `heal.py` and `phases.py` (old behaviour),
run the new file, then `git checkout --` (restored; `git status --porcelain`
clean afterwards).

```
MUTATION: PASSED=2 FAILED=10
  test_words_alone_do_not_defer                       FAILED
  test_real_structured_decline_defers                 FAILED
  test_satisfied_gate_is_not_a_decline                FAILED
  test_failing_verifier_is_not_a_decline              PASSED   <- intentional BEFORE control
  test_intake_file_fallback                           FAILED
  test_check_message_with_provider_word_is_not_a_provider_outage  FAILED
  test_timeout_fact_is_not_a_provider_outage          FAILED
  test_exec_os_error_fact_is_transient                FAILED
  test_masked_402_exit_code_is_a_provider_fact        FAILED
  test_classified_by_text_is_logged_only_on_the_words_path  FAILED
  test_check_failed_takes_regenerate_not_failover     FAILED
  test_without_the_kind_the_old_words_path_fails_over PASSED   <- intentional BEFORE control
========================= 10 failed, 2 passed =========================
```

Restored run: `12 passed in 0.21s`.

## Tests by id on base and head

Group A — engine surface (engine/report/heal/park/readmission tests; head adds
the new file):

| run | result |
|---|---|
| base `9504866a` | `3 failed, 150 passed in 33.35s` |
| head `fd160d147` | `3 failed, 162 passed in 33.93s` |

Identical failure ids both sides (pre-existing, untouched file):

```
tests/test_pd_engine_client_copy.py::TestEveryTemplateFillsItsOwnLabel::test_all_112_templates_render_with_the_manifest_label
tests/test_pd_engine_client_copy.py::TestEveryTemplateFillsItsOwnLabel::test_the_rendered_step_line_reads_as_a_step
tests/test_pd_engine_client_copy.py::TestEveryTemplateFillsItsOwnLabel::test_hidden_phase_is_silent_and_unnumbered
```

Δ = exactly +12 (the new test file). No test was weakened, deleted, renamed,
skipped or xfailed.

Group B — `tests/test_auto_resume.py` (exercises `classify_failure`):

| run | result |
|---|---|
| base | `2 failed, 62 passed in 3.27s` |
| head | `1 failed, 63 passed in 4.44s` |

Repeated three times each: head 2/1/1 failures, base 2/1/2 failures, always the
same two ids (`test_a_refused_dispatch_gives_the_attempt_back_end_to_end`,
`test_a_human_resume_has_no_attempt_to_refund`). These are flaky in this
environment at BOTH revisions — not caused by this unit, not touched.

## Hunk attribution (merge-base `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` → head)

**Mine** (`git diff -U0` new-file coordinates):

- `heal.py`: `+4` (import sys); `+79-101` (kinds + exit-code set + classify_failure
  signature/docstring); `+108-125` (kind branch); `+130-131` (classified_by_text log).
- `phases.py`: `+2254-2280` (`_phase_is_gate_declined`); `+3327` (per-attempt
  `failure_kind`); `+3373-3379` (146 fact); `+3392` / `+3395` (timeout /
  exec_os_error facts); `+3421-3422` (class dispatch); `+3803-3804`,
  `+3810-3811`, `+3815-3816` (three wait outcomes); `+4005-4006` (signature);
  `+4028-4033` (classify call + docstring).

**Sibling units on the same branch — named, not disturbed:**

| Unit | Commit | `phases.py` hunks (its commit's coordinates) |
|---|---|---|
| PD-042 (accepted) | `afd4a7571` | `+747-946` (module helpers: `_read_run_json`, `_verified_destination_lines`, `_teleprompter_publish`, `_compose_done_message`, `_style_pick_*`); `+4352-4570` (style-pick / done-message paths); `+6020-6040`; `+6174-6177` |
| PD-031 (accepted) | `06bffcf21` | `+778-782`; `+1867-1947` (`_stage_timing_medians`, `_client_eta_sentence`, ETA branch) |
| PD-313 (built) | `edc433413` | `6105-6357` region (normal close / ready message) |

No overlap with any of the above ranges. All three units' lines are still
present and their tests still pass in Group A.

## Remote-head proof

Before: `git ls-remote --heads origin refs/heads/pd/fl05-engine-reporting` =
`9504866a6933c3eeea1922cf0194d8986c5f746a`.

After push (recorded in the handoff line below; full 40 characters compared
literally):

```
<filled by the handoff message — see the push proof line>
```

## Not proved / honest gaps

- **BLOCKED (partial): literal `verify()` marker** — needs
  `phase_verifiers.py` owned by FL17 (see the BLOCKED section above). The
  acceptance row itself is proven at the FL05-owned call site.
- **`tests/test_pres002_ready_gate.py` NOT_RUN** — the module hangs in this
  environment at BASE `9504866a` with no changes applied: `timeout 150
  python3 -m pytest tests/test_pres002_ready_gate.py -q` exits `124` after two
  failures. Not caused by this unit; excluded from both sides of the pair.
- **Full `tests/` suite NOT_RUN** — the box is running several sibling build
  lanes concurrently; a full-suite run stalled at ~1% for >5 minutes (the same
  pres002 class of hang) and was stopped. The two affected groups above were
  run complete on both revisions.
- `failure_kind="exit_code:146"` is a new structured fact (HTTP 402 masked by
  the shell, documented in FIX 10's own comment). Codes other than 146
  deliberately fall through to the captured stderr + `heal.classified_by_text`
  so a provider status printed by the executor is still seen.
- `_fail_unit`'s owner-decision check (`classify_failure(reason)`) still uses
  the words path: at that call site no structured kind is available, and it is
  not one of the two recovery-path call sites the amendment names. Every such
  decision now logs `heal.classified_by_text`.
