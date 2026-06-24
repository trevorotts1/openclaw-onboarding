# MASTER VIDEO QC AUTO-FAIL RULESET — Movie Producer (Video Production)

**Department:** Video — Movie Producer (Skill 47 / `automated-video-production-specialist-openmontage`).
**Authority:** This ruleset is the binary, machine-checkable companion to `VIDEO-PIPELINE-MANIFEST.json`. Every `in_ruleset:true` autofail in the manifest has exactly one row in Section 5 below. `47-movie-producer/scripts/video_sync_check.py` reconciles this table against the manifest in BOTH directions and exits 4 on any drift.
**Mirrors:** the Presentations `MASTER-QC-AUTOFAIL-RULESET.md` Section-5 contract.

---

## 0. WHY DESCRIPTION ALONE FAILED (read before wiring)

The video department shipped its production doctrine as **prose** — Rule-Zero, "ffprobe MUST validate every MP4", budget caps, "do not skip stages." Prose is bypassable: a stage can be skipped, a receipt fabricated, a balance unchecked, and nothing on disk fails. Presentation PR #212 proved the cost of prose: 77 auto-fail rules shipped as text and the deck still shipped 40 bad slides.

**Doctrine: a rule not auto-failed at a gate does not exist.** Every binary trigger below is enforced by a Python symbol in `executive_producer.py` / `video_build_check.py` (the `py_symbol` column of the manifest), is checked BEFORE any 1-10 scoring (no averaging away), and is proven by a deliberately-failing negative test in `test_video_preflight.py` (Guard A: `video_gate_integrity_check.py`).

---

## 1. THE LOAD-BEARING AUTO-FAILS (the ship-blockers)

These five are the spine of the pipeline. Each is owned by a DMAIC phase and is a precondition for the next:

1. **AF-VID-BRIEF-INCOMPLETE** (V-DEFINE) — no complete brief, no job. A production job started on an incomplete brief routinely requires a full restart.
2. **AF-VID-BUDGET-CAP** (V-MEASURE) — estimated spend over the client's funded cap is a HARD STOP. V-ANALYZE refuses to run without `budget_gate_pass`.
3. **AF-VID-RULE-ZERO / AF-VID-APPROVAL-MISSING** (V-ANALYZE) — a paid Kie call requires a logged announce + an explicit human APPROVE. The free documentary-montage path skips this only via a logged owner-authorized skip.
4. **AF-VID-NO-FFPROBE / AF-VID-FABRICATED-RECEIPT** (V-IMPROVE) — every MP4 is ffprobe-validated; a Kie-generated asset carries a REAL, non-placeholder `kie_task_id`. A missing/placeholder task id means the generation did not happen (fabrication) or was not recorded — both fail.
5. **AF-VID-DELIVERY-INCOMPLETE** (V-CONTROL) — the delivered bundle is complete (job manifest + render receipt + a real MP4 above its size floor) and a downstream handoff is declared.

---

## 2. PROVIDER + NATIVE-KEY AUTO-FAILS (Kie-only sovereignty)

- **AF-VID-PROVIDER-AUDIT** (V-MEASURE) — `kie` must be AVAILABLE and EVERY native paid provider (FAL/Runway/HeyGen/OpenAI/Google/flux/veo-native/kling/minimax/xai/elevenlabs) must be UNAVAILABLE. An unexpected native key could misdirect generation outside Kie.
- **AF-VID-NATIVE-PROVIDER** (V-IMPROVE) — no native paid provider key may be present in the recorded generation environment, and `provider_used` may not name a native provider. Native at generation time is a hard violation even if Kie was nominally selected.

---

## 3. THE CHECK ORDER (how QC runs this ruleset)

1. **Phase-0 balance** — `AF-VID-KIE-BALANCE` HARD-ABORTS (exit 4) for a paid job before any dispatch.
2. **Per-phase preconditions** — `AF-VID-PHASE-SKIPPED` (exit 2): before phase N, every lower-order phase is attested (by its owning_role) with its produces_artifact on disk, or owner-skipped.
3. **Per-phase receipt validation** — the phase's `_chk_*` checker validates the present receipt; a present-but-invalid receipt is exit 3.
4. Only after all binary gates pass does any 1-10 content scoring happen. A triggered AF is never averaged away.

---

## 4. REQUIRED WIRING (what the integrator keeps in lockstep)

Any added/changed video SOP, role, or gate MUST, in one change:
- (i) update `VIDEO-PIPELINE-MANIFEST.json` (+ bump `manifest_version`);
- (ii) add/point the enforcing `py_symbol` in `executive_producer.py` / `video_build_check.py`;
- (iii) add the AF code row to Section 5 below;
- (iv) add a deliberately-failing negative test in `test_video_preflight.py`.

`video_sync_check.py` exits 4 if any of those four is skipped. `video_gate_integrity_check.py` (Guard A) exits 1 if a declared+enforced gate has no triggering negative test.

---

## 5. THE MACHINE-CHECKABLE SUMMARY TABLE (one row per auto-fail, the wireable list)

| Code | Stage | Level | Trigger (one line) | Detection |
|---|---|---|---|---|
| AF-VID-BRIEF-INCOMPLETE | V-DEFINE | JOB | brief absent or any required brief field missing | `_chk_brief_complete`: job-manifest.json brief_complete:true AND every REQUIRED_BRIEF_FIELDS field non-empty |
| AF-VID-PREFLIGHT | V-MEASURE | JOB | runtime-dependency preflight did not pass | `_chk_measure_receipt`: measure-receipt.json preflight_pass:true |
| AF-VID-PROVIDER-AUDIT | V-MEASURE | JOB | kie not AVAILABLE, or a native paid provider AVAILABLE | `_chk_provider_audit`: provider_audit_pass:true AND kie in providers_available AND no NATIVE_PAID_PROVIDERS member present |
| AF-VID-BUDGET-CAP | V-MEASURE | JOB | estimated spend over the funded budget cap | `_chk_budget_cap`: budget_gate_pass:true AND estimated_cost_usd <= budget_ceiling_usd |
| AF-VID-RULE-ZERO | V-ANALYZE | JOB | paid job reached generation with no logged Rule-Zero announce | `_chk_rule_zero_approval` (paid only): approval-receipt.json carries rule_zero_announced_at |
| AF-VID-APPROVAL-MISSING | V-ANALYZE | JOB | paid job reached generation with no explicit human approval | `_chk_rule_zero_approval` (paid only): approval-receipt.json carries approval_received_at + approved_by |
| AF-VID-NO-FFPROBE | V-IMPROVE | JOB | render receipt does not prove an ffprobe validation | `_chk_render_receipt`: ffprobe_pass:true AND ffprobe_duration>0 AND a video stream recorded |
| AF-VID-FABRICATED-RECEIPT | V-IMPROVE | JOB | Kie in scope but kie_task_id null/placeholder | `_chk_kie_receipt_real` (paid only): kie_task_id non-null, not a FABRICATED_TASK_ID_TOKENS member, kie_result_url present |
| AF-VID-NATIVE-PROVIDER | V-IMPROVE | JOB | native paid provider key present at generation time | `_chk_native_provider`: provider_used not native AND no NATIVE_PROVIDER_ENV_KEYS member in generation_env |
| AF-VID-DELIVERY-INCOMPLETE | V-CONTROL | JOB | delivered bundle incomplete or no handoff declared | `run_postflight_gate`: status:complete AND every DELIVERABLES_REQUIRED file present >= min_bytes AND a HANDOFF_TARGETS handoff declared |
| AF-VID-BUDGET-OVERRUN | V-CONTROL | JOB | actual spend over the funded budget cap with no circuit-breaker | `_chk_budget_overrun`: actual_cost_usd <= budget_ceiling_usd (or a logged circuit_breaker) |
| AF-VID-KIE-BALANCE | Phase-0 | JOB | paid job balance below floor or unverifiable | `kie_balance_preflight`: live Kie credit balance >= estimated_cost_usd x VID_CREDIT_PER_USD x VID_KIE_BALANCE_FLOOR_MULTIPLIER; unverifiable = HARD ABORT |
| AF-VID-PHASE-SKIPPED | Driver | JOB | a phase dispatched before a lower-order phase was attested (or wrong owning_role) | `executive_producer.check_phase_preconditions`: every lower-order phase attested by its owning_role with produces_artifact present, or a logged owner-authorized skip |
