# SOP -- Movie Producer (Automated Video Production) — VSL (Video Sales Letter) Pipeline

**Source:** video/automated-video-production-specialist-openmontage.md (registered slug UNCHANGED).
**Authority:** Pipeline-type SOP for Video Sales Letter / branded talking-head / promotional production. Defers all budget/approval control to `SOP--movie-producer-rule-zero-budget.md`. The VSL script is authored upstream (VSL Specialist); this SOP produces and renders from that script.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 47-movie-producer (clones the upstream OpenMontage engine on the client box at runtime — AGPLv3 source NEVER vendored)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> **Cost profile:** Typically PAID — VSL production usually requires brand-original generated imagery and/or talking-head video via Kie (the `latest-family` image model for stills, a Skill 67 video model for clips). `SOP--movie-producer-rule-zero-budget.md` (RZ-1 through RZ-5) governs every paid call. A VSL is a conversion asset: the offer logic and proof sequence are authoritative inputs from the VSL Specialist, not invented here.

---

## DMAIC Coverage Map

- **Define** — confirm the finished VSL script + offer structure + brand assets (SOP VSL-1).
- **Measure** — count Kie stills/clips, estimate cost, preflight deps (SOP VSL-2).
- **Analyze** — Rule-Zero announce/approve for the full generation set (SOP VSL-3).
- **Improve** — generate assets, assemble to the script's beat map, FFmpeg-render, ffprobe-validate (SOP VSL-4).
- **Control** — conversion-asset QC, spend reconciliation, archive, handoff (SOP VSL-5).

---

## Define

*DMAIC phase: Define. A VSL is built on an authored script; never produce one from a vague brief.*

### SOP VSL-1 -- [VID-MP-VSL-1] Script, Offer, and Brand-Asset Confirmation

**DMAIC phase:** Define
**When to run:** When a VSL or branded promotional brief is routed to this pipeline.
**Frequency:** Per VSL job.
**Inputs:** The finished VSL script + offer structure from the VSL Specialist, brand assets (logo URL, brand colors, voice style), target duration, aspect ratio, target platform.

**Steps:**

1. Confirm a FINISHED VSL script is attached (hook → problem → mechanism → proof → offer → call-to-action). If only a topic is provided, return a gap to the VSL Specialist — this pipeline renders a script; it does not write copy.
2. Confirm brand assets: logo URL (for image-to-image generation), brand color palette, any required talking-head reference image.
3. Map the script to a beat list: which beats are talking-head video, which are generated b-roll stills, which are text/overlay. This beat map drives the generation count in SOP VSL-2.
4. Confirm `budget.mode: cap` per `SOP--movie-producer-rule-zero-budget.md` RZ-1 and record the approval authority.

**Outputs:** Confirmed script, brand-asset set, beat map, budget envelope.
**Hand to:** SOP VSL-2 (measurement).
**Failure mode:** Producing a VSL from a topic instead of a finished script. A VSL's persuasion logic must be authored deliberately; the pipeline renders it, it does not author it.

---

## Measure

*DMAIC phase: Measure. Count the generated assets and estimate the cost precisely.*

### SOP VSL-2 -- [VID-MP-VSL-2] Generation Count, Cost Estimate, and Dependency Preflight

**DMAIC phase:** Measure
**When to run:** After SOP VSL-1.
**Frequency:** Per VSL job.
**Inputs:** Beat map, Kie price source, the Skill 47 preflight.

**Steps:**

1. Run the Skill 47 `verify-deps.sh` preflight. Fail-loud.
2. From the beat map, count: Kie image stills (the `latest-family` image-to-image model when a brand reference is supplied, its text-to-image sibling otherwise) and Kie video clips (the Skill 67 video model for the brief).
3. Hand the full call list to `SOP--movie-producer-rule-zero-budget.md` RZ-2 for cost estimation and remaining-budget computation.
4. Provider audit: `kie` AVAILABLE; all native paid providers UNAVAILABLE; Piper AVAILABLE (VSL narration may use Piper or hand to Skill 30 for premium TTS per the handoff SOP).

**Outputs:** Full Kie call list, cost estimate from RZ-2, preflight + audit pass.
**Hand to:** SOP VSL-3 (Rule-Zero gate).
**Failure mode:** Under-counting generated clips. A VSL beat map can require many assets; an inaccurate count under-estimates the cost and breaks the budget gate downstream.

---

## Analyze

*DMAIC phase: Analyze. Gate the whole generation set behind Rule-Zero before any spend.*

### SOP VSL-3 -- [VID-MP-VSL-3] Rule-Zero Announce/Approve for the Generation Set

**DMAIC phase:** Analyze
**When to run:** Before any Kie call for the VSL.
**Frequency:** Per VSL job.
**Inputs:** The RZ-2 cost estimate and call list.

**Steps:**

1. Invoke `SOP--movie-producer-rule-zero-budget.md` RZ-3: announce job ID, pipeline `vsl`, image-call count + model, video-call count + model, endpoints, per-call + total estimate, cap, remaining, client-key statement. Wait for `APPROVE`.
2. If the VSL introduces a new paid tool type not previously approved on this box, obtain the scoped second approval (RZ-3 step 3).
3. Apply the per-call threshold (RZ-4) for each individual call ≥ `single_action_approval_usd`.
4. Record the approval receipt.

**Outputs:** Approval receipt (or cancellation).
**Hand to:** SOP VSL-4 (generate + assemble + render).
**Failure mode:** Batch-approving then submitting an over-threshold single video call without its own approval. Each ≥$0.50 call is individually gated.

---

## Improve

*DMAIC phase: Improve. Generate the approved assets, assemble to the script beat map, render with FFmpeg, prove with ffprobe.*

### SOP VSL-4 -- [VID-MP-VSL-4] Asset Generation, Beat-Map Assembly, FFmpeg Render, ffprobe Validate

**DMAIC phase:** Improve
**When to run:** After SOP VSL-3 approval.
**Frequency:** Per VSL job.
**Inputs:** Approved manifest, beat map, brand assets, the OpenMontage clone.

**Steps:**

1. Generate stills through Skill 74 (`validate`, then `prompt-budget --check`, then `price` and `preflight`, then `submit --mode active`, then `wait` and `save`) with the `latest-family` image-to-image model, the brand reference as the image input, `aspect_ratio` from the brief, `resolution: 2K`. The live schema is the authority for field names (rule 5); `validate` rejects a wrong field before any spend, and a Skill 47 helper that sends a field `validate` rejects is below the fix and must be updated, not worked around here. Record `kie_task_id` and the saved local file path.
2. Generate clips through the same Skill 74 sequence with the Skill 67 video model. Pass `duration` as a STRING (`"8"`) and set `aspect_ratio` (omitting either causes HTTP 422; `validate` catches both). Skill 74 selects the correct endpoint family and `recordInfo` route; do not hand-pick one. Record every `kie_task_id` and saved file path.
3. Narration: Piper offline TTS for the script, OR hand to Skill 30 (Fish Audio) per the handoff SOP when premium voice is required. Do NOT reimplement cloud TTS in the pipeline.
4. Assemble to the beat map with FFmpeg: stills + clips + narration + brand color title/end cards, in the script's persuasion order. The strongest proof and the call-to-action land last.
5. ffprobe-validate the rendered MP4 (duration > 0, mp4/mov, video stream, width/height match). On fail, retry once; if the second render also fails, halt and escalate with the ffprobe JSON.
6. Write `render-receipt.json` with all Kie receipts + ffprobe fields.

**Outputs:** ffprobe-validated VSL MP4, `render-receipt.json` with the full Kie receipt set.
**Hand to:** SOP VSL-5 (QC + handoff).
**Failure mode:** Passing `duration` as an integer to a Kie video model (HTTP 422), or omitting `aspect_ratio`. Both are live-schema requirements that `validate` enforces before spend.

---

## Control

*DMAIC phase: Control. QC the conversion asset, reconcile spend, archive, route handoff.*

### SOP VSL-5 -- [VID-MP-VSL-5] Conversion-Asset QC, Reconciliation, Archive, Handoff

**DMAIC phase:** Control
**When to run:** After SOP VSL-4 produces a validated MP4.
**Frequency:** End of every VSL job.
**Inputs:** `render-receipt.json`, the VSL script, Kie receipts, the budget config.

**Steps:**

1. Conversion-asset QC: the rendered VSL follows the script's persuasion order; the offer and call-to-action are present and correct; brand assets (logo, colors) appear as specified; narration matches the script; no hardcoded client names or personal data; every claimed Kie asset has a real `kie_task_id` and a saved file.
2. Invoke `SOP--movie-producer-rule-zero-budget.md` RZ-5: reconcile actual vs. estimated spend, run the circuit-breaker check, write the audit-trail fields.
3. Archive to `_local/archive/[job_id]/`; retain receipts and manifest permanently.
4. Route handoff per `SOP--movie-producer-cross-role-handoff.md` — VSLs typically need captions (Skill 26) and may need editorial polish (Skill 27) or motion-graphics lower-thirds before final delivery.

**Outputs:** QC-passed VSL, reconciliation entry, archived assets, handoff routed.
**Hand to:** `SOP--movie-producer-cross-role-handoff.md`.
**Failure mode:** Approving a VSL that drops or reorders the offer/proof sequence. The script's order is the conversion logic; an out-of-order render is a defective deliverable even if it plays cleanly.

---

*SOPs owned: [VID-MP-VSL-1], [VID-MP-VSL-2], [VID-MP-VSL-3], [VID-MP-VSL-4], [VID-MP-VSL-5]. sop_count: 5.*
*Token inventory: `{{COMPANY_NAME}}`, `{{GENERATION_DATE}}`. All other tokens live in the parent role file.*
