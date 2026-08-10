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

### 3.2 North-Star Cluster (DOCTRINE-ONLY)

| AF Code | SOP | Registration | Notes |
|---|---|---|---|
| AF-PRIORITY-SHIFT | SOP-NORTHSTAR-00, SOP-INTEGRATION-00 | DOCTRINE-ONLY | 14-item ship gate. Detection script: `run_signature_deck.py check_priority_shift_ledger`. Composite gate declared but not mechanically wired. |
| AF-PEAK-END | SOP-NORTHSTAR-00 | DOCTRINE-ONLY | Arc acceptance-test gate |
| AF-NO-SALIENCE-APEX | SOP-NORTHSTAR-00 | DOCTRINE-ONLY | Image-QC acceptance-test gate |
| AF-MODE-UNSET | SOP-MODE-00 | DOCTRINE-ONLY | build_deck preflight, Phase 0.1. Intake field `creation_mode` exists; gate does not. |
| AF-NO-SHIFT | SOP-PRIORITY-01 | DOCTRINE-ONLY | COPY-QC gate. Detection script: `pitch_engines_check.py chk_priority_shift`. |
| AF-PROCLAMATION-HEDGE | SOP-PROCLAMATION-01 | DOCTRINE-ONLY | Hedge-token scan. Detection script: `intelligence_engines_check.py check_copy`. |

### 3.3 SOPs with NO gate registration required

| SOP | Reason |
|---|---|
| SOP-OBJECTION-01 | Explicitly states "No new auto-fail." Purely doctrine. |
| SOP-PERSON-00 | Diagnostic; gated at Rehearsal Gate, not at build time. |
| SOP-PHILOSOPHY-00 | Pure doctrine; no enforcement surface. |
| SOP-VISION-01 | References existing live gates; declares no new gate. |

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

This registry is NOT checked by sync_check.py (it is a documentation artifact, not a code artifact). It is the operator's and Director's reference for which gates are mechanically enforced vs doctrine-only. Stale entries here (a gate registered but this doc still says DOCTRINE-ONLY) are human-detectable, not machine-detectable.

---

**File written by WORK-ITEM-11 (2026-08-10) per operator Decision D5.**
