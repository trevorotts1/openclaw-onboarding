# SOP-MECHANICAL-ENFORCEMENT-REGISTRY -- Registration Ledger for Every Auto-Fail Code

**Cluster:** Infrastructure / Lockstep
**Status:** BINDING. This is the single authoritative registration ledger for every auto-fail code in the Presentations department.
**Parent SOP:** SOP-SLIDE-06-EXTENSION-AND-SYNC (the lockstep procedure)
**Created:** 2026-08-10 (WORK-ITEM-11, Decision D5 -- fix all stale SOPs)

---

## 1. PURPOSE

This document replaces the scattered "PENDING Agent W3" notes across 6+ SOPs with ONE authoritative tracking ledger. Every auto-fail code the department has declared lives here with one of three registration states. An agent that reads any SOP and wonders "is this gate actually wired?" consults this registry, not the SOP's own header.

---

## 2. REGISTRATION STATES

| State | Meaning |
|---|---|
| **REGISTERED** | The AF code has ALL four lockstep artifacts: (i) PIPELINE-MANIFEST.autofails entry, (ii) `_chk_*` callable or py_symbol in build_deck.py, (iii) MASTER-QC-AUTOFAIL-RULESET.md Section 5 row, (iv) test_preflight.py fixture. sync_check.py verifies all four. |
| **DOCTRINE-ONLY** | The AF code is declared in an SOP and documented here as doctrine, but has NO mechanical enforcement. No `_chk_*` callable exists. No PIPELINE-MANIFEST.autofails entry. The SOP's rules are enforced by role discipline and QC specialist manual review, not by sync_check-verifiable code. |
| **PENDING-REGISTRATION** | The AF code is declared, the SOP specifies its detection script and enforcement phase, but the lockstep steps have not been executed. When the Director or an Agent W3 successor registers it, the state changes to REGISTERED. |

---

## 3. THE REGISTRY

### 3.1 Core Pipeline Gates (all REGISTERED)

| AF Code | SOP | Registration | Notes |
|---|---|---|---|
| AF-SYNC | SOP-SLIDE-06 | REGISTERED | sync_check.py enforces lockstep at Phase 1Q |
| AF-C2 (banded hook gate) | SOP-SLIDE-03 | REGISTERED | build_deck.py `_chk_hook_band`; PIPELINE-MANIFEST v44 |
| AF-C7 (gradual-drop choreography) | SOP-SLIDE-04, SOP-PITCH-01 | REGISTERED | 4 sub-conditions: SPREAD / EARNED+BUILT-UP / ADDS-value / FINAL-below-ladder |
| AF-DENSITY (DEN-1..8) | SOP-SLIDE-04 | REGISTERED | Maps onto AF-C7 + c17 + c19 + c23 + c24 |
| AF-DELIVER | SOP-PITCH-05 | REGISTERED | Presenter artifacts exist |
| AF-DH1 | SOP-PITCH-05 | REGISTERED | Bundle hygiene |
| AF-DELIVERY-COMPLETE | SOP-PITCH-05 | REGISTERED | Consolidating Done-gate |
| AF-BUNDLE-COMPLETE | CLIENT-WEBINAR-DECK-SOP | REGISTERED | deliverables.json all-verified |
| AF-CANONICAL-RENDER-BYPASS | SOP-IMG-01 | REGISTERED | build_deck.py is the ONLY renderer |
| AF-LOCAL-CANVAS | SOP-IMG-01, SOP-DESIGN-02 | REGISTERED | No local image generation |
| AF-I14 | SOP-IMG-01 | REGISTERED | No native image_generate tool |
| AF-RENDERER | SOP-IMG-01 | REGISTERED | Only canonical renderer |
| AF-F7 (logo drift) | SOP-IMG-01, SOP-DESIGN-04 | REGISTERED | Logo identity check |
| AF-HARMONY | SOP-HARMONY-01 | REGISTERED | Deck cohesion gate |
| AF-CREATIVITY | SOP-ENGINE-00 | REGISTERED | Rejects template sameness |
| AF-NO-VILLAIN | SOP-STORY-01 | REGISTERED | Villain-hero arc |
| AF-PITCH-ENGINE | SOP-PITCH-06 | REGISTERED | Promise-before-price |
| AF-CADENCE | SOP-PITCH-02, SOP-PITCH-06 | REGISTERED | Price cadence |
| AF-NO-FORMULA | SOP-SLIDE-04 | REGISTERED | Formula slide requirement |
| AF-NO-MEASURABLE-RESULTS | SOP-SLIDE-04 | REGISTERED | Measurable results slide |
| AF-NO-FORK | SOP-SLIDE-04 | REGISTERED | Decision tree slide |
| AF-NO-BEFORE-AFTER | SOP-SLIDE-04 | REGISTERED | Before/after slide |
| AF-SP-* family (SIGPRES) | SOP-SIGPRES-00..06 | REGISTERED | All signature-presentation gates wired via prove_sp_*.py provers |

### 3.2 North-Star Cluster (REGISTERED as of FIX 82, 2026-09-02; formerly DOCTRINE-ONLY)

| AF Code | SOP | Registration | Notes |
|---|---|---|---|
| AF-PRIORITY-SHIFT | SOP-NORTHSTAR-00, SOP-INTEGRATION-00 | REGISTERED | 14-item ship gate. build_deck.py `_chk_priority_shift_ledger`; PIPELINE-MANIFEST.autofails entry with py_symbol (v54). |
| AF-PEAK-END | SOP-NORTHSTAR-00 | REGISTERED | Arc acceptance-test gate. build_deck.py `_chk_peak_end`; manifest entry with py_symbol. |
| AF-NO-SALIENCE-APEX | SOP-NORTHSTAR-00 | REGISTERED | Image-QC acceptance-test gate. build_deck.py `_chk_salience_apex`; manifest entry with py_symbol. |
| AF-MODE-UNSET | SOP-MODE-00 | REGISTERED | build_deck preflight, Phase 0.1. Intake field `creation_mode` exists; build_deck.py `_chk_mode` enforces it; manifest entry with py_symbol. |
| AF-NO-SHIFT | SOP-PRIORITY-01 | REGISTERED | COPY-QC gate. build_deck.py `_chk_priority_shift`; manifest entry with py_symbol. |
| AF-PROCLAMATION-HEDGE | SOP-PROCLAMATION-01 | REGISTERED | Hedge-token scan. build_deck.py `_chk_proclamation_hedge`; manifest entry with py_symbol. |

### 3.3 SOPs with NO gate registration required

| SOP | Reason |
|---|---|
| SOP-OBJECTION-01 | Explicitly states "No new auto-fail." Purely doctrine. |
| SOP-PERSON-00 | Diagnostic; gated at Rehearsal Gate, not at build time. |
| SOP-PHILOSOPHY-00 | Pure doctrine; no enforcement surface. |
| SOP-VISION-01 | References existing live gates; declares no new gate. |

### 3.4 Doctrine aliases (declared parent codes, machine-enforced via manifest successors)

Six codes below appear in this registry's older tables but have NO
PIPELINE-MANIFEST.autofails entry under that exact name. They are NOT
unregistered gates: each is a parent/alias name whose enforcement lives under
the named manifest successors, per MASTER-QC-AUTOFAIL-RULESET.md's own
reconciliation notes (its "how the OLD rules map to the LIVE gates" table,
lines 15-27). FIX 36(4) requires them DECLARED here rather than left silent —
a code that looks machine-enforced but is not is exactly the drift this
registry exists to kill.

| AF Code | Status | Manifest successor(s) | Authority |
|---|---|---|---|
| AF-C7 (gradual-drop choreography) | DOCTRINE ALIAS | AF-DEN-1..8 + copy QC c17 (ladder integrity) + c19 (Wall of Wins framing) + c23 (re-pitch) + c24 (close density and Wall spacing); the SPREAD/EARNED+BUILT-UP/ADDS-value/FINAL-below-ladder sub-conditions are enforced by the Offer Price Strategist SOP 9.1/9.2/9.9 gates | MASTER-QC-AUTOFAIL-RULESET.md Section 2 reconciliation row |
| AF-DENSITY (DEN-1..8) | DOCTRINE ALIAS | AF-DEN-1..8 (all 8 present in PIPELINE-MANIFEST.autofails, enforced_by qc_check) | MASTER-QC-AUTOFAIL-RULESET.md Section 2 reconciliation row ("Maps onto AF-C7 + c17 + c19 + c23 + c24") |
| AF-SYNC (lockstep broken) | DOCTRINE ALIAS | emitted directly by sync_check.py on any lockstep drift (the Phase 1Q gate itself); it is sync_check's own banner code, not a manifest autofail entry | sync_check.py drift banner |
| AF-F7 (logo identity drift) | DOCTRINE ALIAS | manifest successors: AF-BRAND-CONSISTENCY (palette-level drift, check_brand_consistency) and the locked-asset intake gates (AF-ASSET-QUESTION-MISSING, AF-MANIFEST-UNREFERENCED); the AF-P15 write-time guard and AF-I4 render-integrity clause remain QC-doctrine rows in qc-specialist-presentations.md, not manifest autofail entries | qc-specialist-presentations.md AF-P15/AF-I4 rows ("the cross-slide logo-IDENTITY-drift check is AF-F7") |
| AF-NO-FORMULA (formula slide requirement) | DOCTRINE ALIAS | AF-OBI-4 (value-trio-on-one-slide; its failure message mandates the formula slide) + AF-OBI-1..6 one-big-idea battery, in PIPELINE-MANIFEST.autofails | MASTER-QC-AUTOFAIL-RULESET.md AF-OBI-4 failure text |
| AF-SP-* family (SIGPRES) | FAMILY ROW | all 16 concrete AF-SP-<NAME> codes are in PIPELINE-MANIFEST.autofails and wired via prove_sp_*.py provers; this row is the family prefix, never itself an entry | SOP-SIGPRES-00..06 |

---

## 4. HOW TO REGISTER A DOCTRINE-ONLY GATE

Per SOP-SLIDE-06 Section 1, the four mandatory steps:

1. **(i) Declare it in PIPELINE-MANIFEST.json.** Add the `autofails[]` entry. Bump `manifest_version`.
2. **(ii) Add the build_deck gate.** Write a `_chk_<x>` callable and register it as `py_symbol`.
3. **(iii) Add the AF code to the ruleset.** Add a Section-5 row to MASTER-QC-AUTOFAIL-RULESET.md.
4. **(iv) Add a test.** Add a positive/negative fixture to test_preflight.py.

After all four steps, update this registry: change the state from DOCTRINE-ONLY to REGISTERED and reference the PIPELINE-MANIFEST version where it landed.

---

## 5. VERIFICATION

This registry IS machine-checked as of FIX 36(4) (2026-09-01):

1. **Parity test** — `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_fix36_registry_parity.py` fails on any manifest-enforced AF code absent from this document (including FIX 15/18's AF-SLIDE-CRAFT-LOADER / AF-CRAFT-JUDGEMENT-LOADER), on any appendix code the manifest no longer declares, and on any alias code not declared in section 3.4.
2. **Machine-checked appendix (section 6)** — generated from PIPELINE-MANIFEST.json by `23-ai-workforce-blueprint/scripts/gen_registry_parity.py`; the parity test re-derives it in --dry-run mode and requires a byte-for-byte match. If you change the manifest's autofails[], regenerate the appendix — the test fails otherwise.
3. **Lockstep (manifest ↔ build_deck ↔ ruleset §5 ↔ preflight)** — remains sync_check.py's A-series checks, unchanged.

Stale entries here are now MACHINE-detectable, not human-detectable.

---

## 6. MACHINE-CHECKED PARITY APPENDIX

Every PIPELINE-MANIFEST.autofails entry (enforced_by, py_symbol), generated —
never hand-edited. Regenerate:
`python3 23-ai-workforce-blueprint/scripts/gen_registry_parity.py`

<!-- BEGIN MACHINE-CHECKED PARITY TABLE -->
| AF code | enforced_by | py_symbol |
|---|---|---|
| `AF-AGENT-ENV-MISSING` | runner | - |
| `AF-AGENT-ENV-UNKNOWN` | runner | - |
| `AF-AGENT-ENV-UNMANAGED` | runner | - |
| `AF-ASSET-QUESTION-MISSING` | build_deck | _chk_asset_question |
| `AF-AUD-1` | qc_check | - |
| `AF-AUD-2` | qc_check | - |
| `AF-AUD-3` | qc_check | - |
| `AF-AUD-4` | qc_check | - |
| `AF-AUD-5` | qc_check | - |
| `AF-AUD-6` | qc_check | - |
| `AF-BAKED` | closeout_gate | - |
| `AF-BRAND-CONSISTENCY` | build_deck | check_brand_consistency |
| `AF-BUNDLE-COMPLETE` | build_deck | run_postflight_gate |
| `AF-BUNDLE-INCOMPLETE` | fix_bundle_complete | - |
| `AF-C2` | qc_check | - |
| `AF-CADENCE` | qc_check | - |
| `AF-CANONICAL-RENDER-BYPASS` | build_deck | check_canonical_render_path |
| `AF-CAPACITY-UNMEASURED` | launcher | - |
| `AF-CASTING` | closeout_gate | _chk_representation_casting_verdict |
| `AF-CASTING-MIX-PARITY` | closeout_gate | _chk_representation_casting_verdict |
| `AF-CASTING-PARK` | closeout_gate | _chk_representation_casting_verdict |
| `AF-CC-UNREGISTERED` | build_deck | _chk_cc_registered |
| `AF-CC-UNVERIFIED` | build_deck | _chk_cc_registered |
| `AF-CONVERTER-NO-INVENT` | build_deck | _chk_converter_no_invent |
| `AF-CONVERTER-PARITY` | closeout_gate | - |
| `AF-COPY` | build_deck | _engine_problem_to_def |
| `AF-COPY-BAND` | build_deck | _chk_copy_density |
| `AF-COPY-QC` | build_deck | _qc_report_substance_problems |
| `AF-COVERAGE-1` | build_deck | _chk_coverage |
| `AF-CRAFT-JUDGEMENT-LOADER` | build_deck | _chk_slide_craft |
| `AF-CREATIVITY` | build_deck | _chk_creativity |
| `AF-DARK-SLIDE` | build_deck | _chk_no_dark_slides |
| `AF-DECK-TYPE-UNSET` | build_deck | _chk_deck_type |
| `AF-DELIVER` | closeout_gate | - |
| `AF-DELIVERY-COMPLETE` | closeout_gate | - |
| `AF-DEN-1` | qc_check | - |
| `AF-DEN-2` | qc_check | - |
| `AF-DEN-3` | qc_check | - |
| `AF-DEN-4` | qc_check | - |
| `AF-DEN-5` | qc_check | - |
| `AF-DEN-6` | qc_check | - |
| `AF-DEN-7` | qc_check | - |
| `AF-DEN-8` | qc_check | - |
| `AF-DH1` | closeout_gate | - |
| `AF-EMPTY-NOTES-PANE` | build_deck | _chk_notes_pane |
| `AF-EXCELLENCE` | build_deck | check_prompt_excellence |
| `AF-FACE-PROMPT-MISSING` | qc_check | - |
| `AF-FONT-FLOOR` | build_deck | check_font_floor |
| `AF-FORGED-APPROVAL` | build_deck | check_phase_preconditions |
| `AF-GUARANTEE-GENERIC` | qc_check | - |
| `AF-HAIR-INAUTHENTIC` | qc_check | - |
| `AF-HARMONY` | build_deck | check_deck_harmony |
| `AF-HOOK` | build_deck | check_intelligence_engines_prompt |
| `AF-HOOK-1` | qc_check | - |
| `AF-HOOK-2` | qc_check | - |
| `AF-HOOK-3` | qc_check | - |
| `AF-HOOK-4` | qc_check | - |
| `AF-HOOK-5` | qc_check | - |
| `AF-HOOK-6` | agent | - |
| `AF-HOOK-7` | qc_check | - |
| `AF-HOOK-IMG-MISSING` | qc_check | - |
| `AF-HOOK-OVERSTAMP` | qc_check | - |
| `AF-I14` | build_deck | _chk_kie_baked |
| `AF-IMAGE-GROUNDING` | closeout_gate | _chk_image_grounding_verdict |
| `AF-IMAGE-GROUNDING-PARK` | closeout_gate | _chk_image_grounding_verdict |
| `AF-IMAGE-QC` | build_deck | _chk_image_qc |
| `AF-IMAGE-QC-RAN` | build_deck | check_image_qc_present |
| `AF-IMAGE-QC-VISION` | build_deck | check_image_qc_vision |
| `AF-INTAKE-BATCH` | build_deck | _chk_sp_intake_trace |
| `AF-INTELLIGENCE` | build_deck | _engine_name_for_code |
| `AF-INTELLIGENCE-COPY` | build_deck | check_intelligence_engines_copy |
| `AF-INTELLIGENCE-ENGINES` | build_deck | check_intelligence_engines_prompt |
| `AF-KIE-AUTH` | build_deck | _preflight_kie_auth |
| `AF-KIE-BALANCE` | build_deck | kie_balance_preflight |
| `AF-LIGHT-PROMPT-MISSING` | qc_check | - |
| `AF-LOCAL-CANVAS` | build_deck | check_canonical_render_path |
| `AF-MANIFEST-UNREFERENCED` | build_deck | _chk_assets_manifest |
| `AF-METHOD-FABRICATED` | qc_check | - |
| `AF-MODE-UNSET` | build_deck | _chk_mode |
| `AF-MODEL-SOVEREIGNTY` | closeout_gate | - |
| `AF-NARRATIVE-HARMONY` | qc_check | - |
| `AF-NO-BEFORE-AFTER` | build_deck | _chk_persuasion_beats |
| `AF-NO-BRANDED-METHOD` | qc_check | - |
| `AF-NO-CHOICE` | build_deck | _chk_persuasion_beats |
| `AF-NO-COMPARISON` | build_deck | _chk_persuasion_beats |
| `AF-NO-COST-OF-INACTION` | qc_check | - |
| `AF-NO-EXPERT-PROOF` | build_deck | _chk_persuasion_beats |
| `AF-NO-FELT-STAKES` | qc_check | - |
| `AF-NO-FORK` | build_deck | _chk_persuasion_beats |
| `AF-NO-HOOK-REFRAIN` | qc_check | - |
| `AF-NO-MEASURABLE-RESULTS` | build_deck | _chk_persuasion_beats |
| `AF-NO-PRIORITY-STACK` | build_deck | _chk_priority_stack |
| `AF-NO-PROBLEM` | build_deck | _chk_persuasion_beats |
| `AF-NO-RECAP` | qc_check | - |
| `AF-NO-RERANK` | build_deck | _chk_rerank |
| `AF-NO-RUN-DIR` | delivery_gate | - |
| `AF-NO-SALIENCE-APEX` | build_deck | _chk_salience_apex |
| `AF-NO-SHIFT` | build_deck | _chk_priority_shift |
| `AF-NO-TIME-TO-RESULT` | qc_check | - |
| `AF-NO-TRIGGER` | build_deck | _chk_trigger |
| `AF-NO-VILLAIN` | qc_check | - |
| `AF-NOT-KIE-RENDERED` | delivery_gate | - |
| `AF-OBI` | qc_check | - |
| `AF-OBI-1` | qc_check | - |
| `AF-OBI-2` | qc_check | - |
| `AF-OBI-3` | qc_check | - |
| `AF-OBI-4` | qc_check | - |
| `AF-OBI-5` | qc_check | - |
| `AF-OBI-6` | qc_check | - |
| `AF-OCR-ENGINE-MISSING` | build_deck | ocr_engine_preflight |
| `AF-OCR-READBACK` | build_deck | check_ocr_readback |
| `AF-OVERLAY-DELIVERED` | build_deck | _chk_no_overlay |
| `AF-P-DENSITY` | build_deck | _prompt_density_problems |
| `AF-P-STRUCT` | build_deck | REQUIRED_STRUCTURAL_BLOCKS |
| `AF-P-VERBATIM` | build_deck | _verbatim_copy_problems |
| `AF-P1` | build_deck | _chk_rich_prompts |
| `AF-P13` | build_deck | _negative_block_class_problems |
| `AF-P14` | build_deck | _spelling_lock_present |
| `AF-P2` | build_deck | PROMPT_CHAR_CEILING |
| `AF-PACKAGE-CLEAN` | build_deck | check_package_cleanliness |
| `AF-PEAK-END` | build_deck | _chk_peak_end |
| `AF-PHASE-REPORT-DONE` | runner | - |
| `AF-PHASE-REPORT-MISSING` | runner | - |
| `AF-PHASE-REPORT-START` | runner | - |
| `AF-PHASE-SKIPPED` | runner | - |
| `AF-PITCH-ENGINE` | build_deck | check_pitch_engines |
| `AF-PITCH-FLAG-UNSET` | build_deck | _chk_pitch_flag |
| `AF-PITCH-LEAK` | build_deck | _chk_pitch_leak |
| `AF-PITCH-MISSING` | build_deck | _chk_pitch |
| `AF-PLACEHOLDER` | qc_check | - |
| `AF-PRICE-BEFORE-PROMISE` | qc_check | - |
| `AF-PRIORITY-SHIFT` | build_deck | _chk_priority_shift_ledger |
| `AF-PROCESS-INTEGRITY` | runner | - |
| `AF-PROCLAMATION-HEDGE` | build_deck | _chk_proclamation_hedge |
| `AF-PROMPT-DUP-FILE` | build_deck | _canonical_prompt_dir_problems |
| `AF-PROMPT-FLOOR` | build_deck | PROMPT_CHAR_FLOOR |
| `AF-PROMPT-NAME` | build_deck | _canonical_prompt_dir_problems |
| `AF-PROMPT-QC` | build_deck | _chk_prompt_qc |
| `AF-QC-INDEPENDENCE` | build_deck | _chk_copy_qc |
| `AF-QC-PLACEHOLDER` | build_deck | check_qc_phase_report_real |
| `AF-QC-SKIP` | build_deck | UNSKIPPABLE_QC_PHASES |
| `AF-R3` | build_deck | FORBIDDEN_DEMOGRAPHIC_DEFAULTS |
| `AF-RENDER-COMPLETE` | build_deck | run_postflight_gate |
| `AF-RENDER-EMPTY` | build_deck | run_postflight_gate |
| `AF-RENDERER` | closeout_gate | - |
| `AF-RESEARCH-GATE` | build_deck | _chk_research_brief |
| `AF-RESEARCH-REACHES-RENDER` | build_deck | _chk_research_reaches_render |
| `AF-RESEARCH-UNCITED` | build_deck | _chk_research_cited |
| `AF-RESEARCH-WEAVE` | build_deck | _chk_research_map |
| `AF-SCRATCH-PARSE-SKIPPED` | build_deck | _chk_scratch_parse |
| `AF-SLIDE-COUNT-EXACT` | build_deck | _chk_slide_count_exact |
| `AF-SLIDE-COUNT-FLOOR` | build_deck | _chk_slide_count_floor |
| `AF-SLIDE-CRAFT-LOADER` | build_deck | _chk_slide_craft |
| `AF-SP-8Q-MISSING` | build_deck | _chk_sp_intake |
| `AF-SP-8Q-SPLIT` | build_deck | _chk_sp_intake |
| `AF-SP-CASESTUDY-CAP` | build_deck | _chk_sp_structure |
| `AF-SP-FRAME-UNSET` | build_deck | _chk_sp_intake |
| `AF-SP-HOOK` | build_deck | _chk_sp_structure |
| `AF-SP-IMG-SUGGESTION` | build_deck | _chk_sp_structure |
| `AF-SP-OFFER-UNDECLARED` | build_deck | _chk_sp_intake |
| `AF-SP-P3-PITCH` | build_deck | _chk_sp_no_pitch |
| `AF-SP-PHASE-LABEL` | build_deck | _chk_sp_structure |
| `AF-SP-PHASE-ORDER` | build_deck | _chk_sp_structure |
| `AF-SP-PHASE-RANGE` | build_deck | _chk_sp_structure |
| `AF-SP-QUADRANT` | build_deck | _chk_sp_structure |
| `AF-SP-SLIDE-FLOOR` | build_deck | _chk_sp_structure |
| `AF-SP-TEACH-STEPS` | build_deck | _chk_sp_structure |
| `AF-SP-TYPE-MISMATCH` | build_deck | _chk_sp_intake |
| `AF-SP-TYPE-UNDECLARED` | build_deck | _chk_sp_claim |
| `AF-SPEECH-HOOK-COUNT` | qc_check | - |
| `AF-SPEECH-PACING` | build_deck | _speech_pacing_deviation |
| `AF-SPEECH-QC` | build_deck | _chk_speech_qc |
| `AF-SPEECH-SHORT` | build_deck | _chk_speech_length |
| `AF-SPELLING` | build_deck | _chk_spelling |
| `AF-STYLE-DOUBLECHARGE` | build_deck | _chk_style_preview |
| `AF-STYLE-UNPICKED` | build_deck | _chk_style_preview |
| `AF-TELEPROMPTER-UNPUBLISHED` | postflight_bundle_gate | _check_teleprompter_published |
| `AF-TEXT-OVERFLOW` | build_deck | _chk_text_fits |
| `AF-TOOL-SCHEMA-LOOP` | runner | - |
| `AF-TYPE-SIZE-MEASURED` | build_deck | _chk_type_size |
| `AF-TYPOGRAPHY-QC` | build_deck | _chk_typography_qc |
| `AF-U-CHECKOUT-BUILD` | sales_checkout_builder | - |
| `AF-U-FORM-CHECKOUT` | sales_checkout_builder | - |
| `AF-U-SALES-BUILD` | sales_checkout_builder | - |
| `AF-U-VSL-BUILD` | vsl_builder | - |
| `AF-VISUAL-VARIETY` | build_deck | check_visual_variety |
| `AF-WEBINAR-INTRO` | synthesize_full_speech | - |
| `AF-WEBINAR-SIZE` | build_webinar_video | - |
| `AF-WORKBOOK-BOTH` | phase_verifiers | - |
| `AF-WORKBOOK-EMPTY` | workbook_builder | - |
| `AF-WORKBOOK-PROMPT-NO-CONTENT` | workbook_builder | - |
| `AF-WORLD-SCALE` | qc_check | - |
<!-- END MACHINE-CHECKED PARITY TABLE -->

---

**File written by WORK-ITEM-11 (2026-08-10) per operator Decision D5.**
