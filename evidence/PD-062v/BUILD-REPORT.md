# PD-062v — build report

- **Unit:** PD-062v (Critical, fixes finding PD-062) — the engine finds the deck where the render writes it
- **Lane:** FL17 · branch `pd/fl17-phase-checks` · repo trevorotts1/openclaw-onboarding
- **Builder:** deepseek-chain
- **Base head on entry:** `76703417c` (PD-915 build report). Branch also carries PD-206a `471fdae82`, PD-061 `f63ef6b0c`, PD-064 `200fa8630`, PD-910 `08a6cdcd7`/`021f74e24`, PD-915 `2d85e9d1b`/`76703417c`. None disturbed; `tests/test_slice3_gates.py` re-run unchanged (15 passed).

## Change

`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/phase_verifiers.py`

1. `artifact_path` — a key that carries a folder (`working/deliverables/*-FINAL.pptx`) now resolves AS WRITTEN relative to the run folder (literal, glob and trailing-`/*` forms). Keys with no folder keep the existing run-top then `working/upsell/` lookups. Additive: the old lookups still run when the literal path is absent, so no legacy upsell key changes behaviour.
2. `_verify_assemble` (P8-ASSEMBLE) — the deck is now resolved through `_assemble_deck_candidates` over exactly two accepted patterns: `working/deliverables/*-FINAL.pptx` (where the render writes it) and the run-top `*-FINAL.pptx` (the manifest's current `produces_artifact`, so this unit is safe before or after PD-062). Requires exactly one deck, and `_is_real_deck` requires a ZIP container holding `ppt/presentation.xml`. A stray `.pptx` elsewhere no longer stands in for the deck; a miss names the expected path. `build_deck.check_deck_harmony` is still required (and the F03 production/degraded rule is unchanged).
3. New test file `scripts/tests/test_pd062v_deck_assembly_path.py`.

Engine side unchanged: `presentation_job/phases.py:1845` already delegates to `phase_verifiers.artifact_path`, so the resolver fix reaches the engine without a second copy.

## Acceptance rows

| Row | Test | Result |
|---|---|---|
| A1 deck only at `working/deliverables/out-FINAL.pptx` is found | `test_a1_deck_under_working_deliverables_is_found` | PASS |
| A2 control: deck only at the run top is found | `test_a2_run_top_deck_is_found` | PASS |
| A3 stray `.pptx` elsewhere, no `-FINAL` deck → fail, names expected path | `test_a3_stray_pptx_is_not_the_deck_and_expected_path_is_named` | PASS |
| A4 text file named `x-FINAL.pptx` → "not a deck" | `test_a4_text_file_named_final_pptx_fails_as_not_a_deck` | PASS |

```
python3 -m pytest tests/test_pd062v_deck_assembly_path.py -q   -> 4 passed
python3 phase_verifiers.py --selftest                           -> PASS
```

Regression: `test_pd_phase_checks_audio.py`, `test_fix36_registry_parity_cand17.py`, `test_fix20_workingset.py`, `test_persona_governance.py`, `test_pd156_prompt_phase_declares_slides_index.py`, `test_deliverables_single_source.py`, `test_slice3_gates.py` — all pass.

Two pre-existing failures, proven on the base head with the change stashed (same failures, same names, not caused by this unit):

- `test_fix17_verifier_import_failclosed.py` — 5 failures, identical with `phase_verifiers.py` stashed.
- `tests/test_negative_fixtures.py::TestSameModelJudge::test_independent_judge_full_set_passes` — 1 failure, identical with the change stashed.

No `/tmp`, no client box, no live system, no paid model. Temp files under `$LOOP_ROOT/tmp`.
