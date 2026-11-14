# PD-018b — The client sees plain labels, and nothing internal

- **Unit:** PD-018b (lane FL05, Critical-first prerequisite of PD-048b)
- **Repository:** trevorotts1/openclaw-onboarding
- **Branch:** `pd/fl05-engine-reporting` (verified with `git branch --show-current` before editing; it already matched the ledger row, so no checkout or create was needed)
- **Base:** `c40b6744dae34ef7e560c71166294919a7cd27e5`
- **Built at:** 2026-11-12, 9:13 PM Eastern

## Files changed

| File | What changed |
|---|---|
| `…/scripts/presentation_job/phases.py` | `{client_label}` filled from the manifest for all 112 templates; `client_visible: false` and no-step phases render `""` (caller sends nothing); default/fallback copy carries no phase id and no role name; the pause message is rewritten to `Your presentation is paused. <plain need>. Everything you sent is saved.` with `<plain need>` from `auto_resume.classify_park`; the three internal lines (script retry, "Still waiting on", and — in `heal.py` — "artifact check failed … Regenerating") become `report.internal` events; the close-time failure messages (integrity, curation ×2, self-audit ×2) send one plain sentence and keep the technical text in the event log; start/done messages pass `phase_id` to the reporter. |
| `…/scripts/presentation_job/report.py` | `Reporter` takes the loaded manifest (optional) and builds the phase-id and client-label maps from it, never from a pattern; `to_requester` sanitizes any message carrying a manifest phase id or an `AF-` token into `Your presentation is moving ahead: <client_label>.` and records `report.sanitized`; `_is_milestone` now takes the `phase_id` argument, and `_throttle_decision` passes it through. |
| `…/scripts/presentation_job/heal.py` | `rung2_regenerate`'s requester message replaced by a `report.internal` event carrying the full text. |
| `…/scripts/tests/test_engine_client_report.py` | Four assertions updated for a true reason (see below). |
| `…/scripts/tests/test_pd_engine_client_copy.py` | New: all 112 templates carry their own label and no internal text; hidden phase silent; A4 script fail-once-then-pass sends nothing and logs the retry. |
| `…/scripts/tests/test_pd_report_sanitize.py` | New: phase-id and `AF-` sanitization, control message untouched, milestone throttle by phase id. |

`__main__.py` line 267 already reads `(deck-intake-driver.py, function derive_legacy_fields)` — PD-019 landed it; nothing to do.

## Proof — the real rendered step line, before and after

Rendered on the integration tree (this branch + PD-018a), `deck_type=webinar`, `creation_mode=from_scratch`, real `PIPELINE-MANIFEST.json`:

**Before PD-018b** (the recorded merge-order defect):

```
P0A-INTAKE     start -> 'Step 2 of 46 —  — starting'
P-0.5-RESEARCH start -> 'Step 1 of 46 —  — starting'
P4-COPY        start -> 'Step 9 of 46 —  — starting'
P4-RENDER      start -> 'Step 19 of 46 —  — starting'
P-CONVERTER    start -> 'P-CONVERTER — not part of the 46-step plan for this deck type (internal housekeeping phase, no client-visible step number) — starting'
P-STYLE-SPEC   start -> 'Step 16 of 46 —  — starting'
```

**After PD-018b:**

```
P0A-INTAKE     start -> 'Step 2 of 46 — Confirming your answers — starting'
P-0.5-RESEARCH start -> 'Step 1 of 46 — Researching your topic — starting'
P4-COPY        start -> 'Step 9 of 46 — Writing your slides — starting'
P4-RENDER      start -> 'Step 19 of 46 — Creating your slide images — starting'
P-CONVERTER    start -> ''
P-STYLE-SPEC   start -> ''
```

(`P-CONVERTER` has no step number on this deck and `P-STYLE-SPEC` is `client_visible: false` in the manifest — both send nothing rather than an internal sentence.)

## Tests changed, and why (rule 15)

`test_engine_client_report.py` (PD-018a's file, same directory as the tests this unit touches):
- `test_deferred_phase_gets_honest_wording_not_a_wrong_step_number` → `test_deferred_phase_gets_no_client_message`: the old assertion required the phase id in the sentence; PD-018b's acceptance requires the phase id never reach the client, so the true consequence is `""`.
- `test_sp_only_phase_deferred_on_standard_deck`: same reason, `""`.
- `test_malformed_template_falls_back_to_default_not_a_crash_or_leak` and `test_no_template_declared_uses_plain_default`: the old default `Starting <phase id> (<role>)` is itself the leaked internal text this unit removes; the assertions now pin a labelled step line with no id and no role, still proving no crash and no literal brace.

No test was deleted, skipped or weakened; every rewritten assertion still fails on the pre-fix behaviour.

## Observation for the checker (no runtime constant changed)

`{N}` still comes from `_client_visible_phases` (46 on a from-scratch webinar deck at this base), while the manifest now marks 18 of 56 phases `client_visible: true`. The spec for PD-018b says to skip `client_visible: false` phases and fills `{client_label}`; it says nothing about recomputing `N`, so `N` is untouched. A client therefore sees only the visible phases' lines, numbered within the 46-step total. Reported, not changed.

## Not done here (by rule)

No test suite and no acceptance row was run: tests are QC's job (rule 9). Only a `python3 -m py_compile` syntax gate was run on the changed files.
