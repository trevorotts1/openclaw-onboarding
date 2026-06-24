# SOP -- Movie Producer (Automated Video Production) — Short-Form Pipeline (Reels / Shorts / TikTok)

**Source:** video/automated-video-production-specialist-openmontage.md (registered slug UNCHANGED).
**Authority:** Pipeline-type SOP for vertical short-form production (9:16, ≤60s). Defers all budget/approval control to `SOP--movie-producer-rule-zero-budget.md`. Hands off polish/integration per `SOP--movie-producer-cross-role-handoff.md`.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 47-movie-producer (clones the upstream OpenMontage engine on the client box at runtime — AGPLv3 source NEVER vendored)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> **Cost profile:** May be zero-cost (free corpus + Piper, vertically reframed) OR Kie-paid (when brand-original generated b-roll is required). When ANY paid call is in scope, `SOP--movie-producer-rule-zero-budget.md` (RZ-2/RZ-3/RZ-4) governs the announce/approve/per-call gates. Short-form is hook-first: the first 1-3 seconds must earn the watch.

---

## DMAIC Coverage Map

- **Define** — lock the hook, the 9:16 aspect, and the ≤60s structure (SOP SF-1).
- **Measure** — measure paid-asset count + cost; preflight deps (SOP SF-2).
- **Analyze** — Rule-Zero gate for any paid b-roll generation (SOP SF-3).
- **Improve** — assemble the vertical cut, FFmpeg-render, ffprobe-validate (SOP SF-4).
- **Control** — QC for platform spec, archive, handoff to captions (SOP SF-5).

---

## Define

*DMAIC phase: Define. A short-form video lives or dies on the hook and the vertical frame; lock both before producing.*

### SOP SF-1 -- [VID-MP-SF-1] Hook, Aspect, and Structure Lock

**DMAIC phase:** Define
**When to run:** When a short-form (Reels/Shorts/TikTok) brief is routed to this pipeline.
**Frequency:** Per short-form job.
**Inputs:** Brief (message, target platform, hook idea, target duration ≤60s, brand assets if any).

**Steps:**

1. Confirm target aspect ratio is 9:16 (vertical). If the brief asks for 16:9 or 1:1 at short duration, confirm with the requestor before producing — platform spec mismatch is a common rework cause.
2. Lock the hook: the first 1-3 seconds. Write the exact opening line / visual. A short-form video with no hook in the first 3 seconds is a failed brief.
3. Lock the ≤60s structure: hook → payload → call-to-action. Keep one idea per video.
4. Decide the asset source: free corpus (vertically reframed) for zero-cost, or Kie-generated b-roll for brand-original visuals. If Kie is in scope, the job is a PAID job — `SOP--movie-producer-rule-zero-budget.md` applies.

**Outputs:** Locked hook, aspect, structure, and asset-source decision in the manifest.
**Hand to:** SOP SF-2 (measurement).
**Failure mode:** Producing a horizontal cut for a vertical platform. Always confirm 9:16 at the Define step.

---

## Measure

*DMAIC phase: Measure. Count the paid assets and preflight the deps.*

### SOP SF-2 -- [VID-MP-SF-2] Paid-Asset Count and Dependency Preflight

**DMAIC phase:** Measure
**When to run:** After SOP SF-1.
**Frequency:** Per short-form job.
**Inputs:** Asset-source decision, the Skill 47 preflight, Kie price source (for paid jobs).

**Steps:**

1. Run the Skill 47 `verify-deps.sh` preflight (FFmpeg / Node ≥18 / `npx hyperframes` / Piper). Fail-loud; never work around a failing preflight.
2. If Kie b-roll is in scope: enumerate the image/video calls (count + model). Hand the call list to `SOP--movie-producer-rule-zero-budget.md` RZ-2 for cost estimation.
3. If free-corpus only: estimate `$0.00` and skip the Rule-Zero announce gate.
4. Run the provider availability audit: confirm `kie` AVAILABLE (for paid jobs), all native paid providers UNAVAILABLE, Piper AVAILABLE.

**Outputs:** Paid-asset call list (if any), preflight pass, provider-audit pass.
**Hand to:** SOP SF-3 (Rule-Zero gate) for paid jobs; SOP SF-4 directly for free jobs.
**Failure mode:** Discovering mid-run that a native paid provider key is present. The audit here catches a key that would misroute b-roll outside Kie.

---

## Analyze

*DMAIC phase: Analyze. Gate any paid b-roll generation behind Rule-Zero.*

### SOP SF-3 -- [VID-MP-SF-3] Rule-Zero Gate for Generated B-Roll

**DMAIC phase:** Analyze
**When to run:** For short-form jobs that generate brand-original b-roll via Kie. SKIP for free-corpus jobs.
**Frequency:** Per paid short-form job.
**Inputs:** The estimated cost from RZ-2, the call list.

**Steps:**

1. Invoke `SOP--movie-producer-rule-zero-budget.md` RZ-3: post the Rule-Zero announcement (job ID, pipeline `short-form`, Kie image/video call counts + models, endpoints, per-call + total estimate, cap, remaining, client-key statement). Wait for `APPROVE`.
2. Honor the per-call threshold (RZ-4): any single Kie call ≥ `single_action_approval_usd` gets its own approval.
3. Record the approval receipt in the manifest.

**Outputs:** Approval receipt (or cancellation).
**Hand to:** SOP SF-4 (assemble + render).
**Failure mode:** Generating b-roll before approval. A short-form video is small spend per asset, but the announce gate is still mandatory — it is the client's money and the receipt is the paper trail.

---

## Improve

*DMAIC phase: Improve. Build the vertical cut, render with FFmpeg, prove with ffprobe.*

### SOP SF-4 -- [VID-MP-SF-4] Vertical Assembly, FFmpeg Render, ffprobe Validate

**DMAIC phase:** Improve
**When to run:** After SOP SF-2 (free) or SOP SF-3 approval (paid).
**Frequency:** Per short-form job.
**Inputs:** Approved manifest, assets (free corpus and/or Kie-generated), the OpenMontage clone.

**Steps:**

1. Retrieve free clips (vertically cropped to 9:16) and/or download approved Kie assets. For each Kie call, record `kie_task_id` + `kie_result_url` per RZ-4. Kie video uses string `duration` (`"8"`) and an explicit `aspect_ratio` to avoid HTTP 422.
2. Assemble the hook → payload → CTA structure. Burn the hook text only if the brief specifies on-screen text; otherwise leave captioning to the handoff (Skill 26).
3. Render with FFmpeg at 9:16, the client's resolution and frame rate. Do not exceed the locked duration.
4. ffprobe-validate: `format.duration` > 0 and ≤ the locked max; `format_name` mp4/mov; a `codec_type: video` stream; width:height in 9:16 ratio. On fail, retry once; if the second render also fails, halt and escalate with the ffprobe JSON.
5. Write `render-receipt.json` (output path, Kie receipts or null, ffprobe fields).

**Outputs:** ffprobe-validated 9:16 MP4, `render-receipt.json`.
**Hand to:** SOP SF-5 (QC + handoff).
**Failure mode:** Rendering past the platform duration cap (e.g. > 60s for Reels). ffprobe duration check enforces it.

---

## Control

*DMAIC phase: Control. QC against the platform spec, reconcile spend, archive, hand off captions.*

### SOP SF-5 -- [VID-MP-SF-5] Platform-Spec QC, Reconciliation, and Caption Handoff

**DMAIC phase:** Control
**When to run:** After SOP SF-4 produces a validated MP4.
**Frequency:** End of every short-form job.
**Inputs:** `render-receipt.json`, the brief, Kie receipts (if paid).

**Steps:**

1. Platform QC: 9:16 aspect confirmed; duration within platform limit; hook lands in first 3 seconds; CTA present; no hardcoded client names or personal data on-screen.
2. If paid: invoke `SOP--movie-producer-rule-zero-budget.md` RZ-5 for spend reconciliation and the circuit-breaker check. Confirm every claimed Kie asset has a real `kie_task_id` + `kie_result_url`.
3. Archive to `_local/archive/[job_id]/`; retain receipts and manifest permanently.
4. Route handoff per `SOP--movie-producer-cross-role-handoff.md` — short-form almost always needs burned-in captions (Skill 26).

**Outputs:** QC-passed short-form video, reconciliation (paid jobs), archived assets, caption handoff routed.
**Hand to:** `SOP--movie-producer-cross-role-handoff.md` (Skill 26 captions).
**Failure mode:** Shipping a short-form video without captions when the platform audience watches muted. Captioning is a handoff to Skill 26, not an in-pipeline reimplementation.

---

*SOPs owned: [VID-MP-SF-1], [VID-MP-SF-2], [VID-MP-SF-3], [VID-MP-SF-4], [VID-MP-SF-5]. sop_count: 5.*
*Token inventory: `{{COMPANY_NAME}}`, `{{GENERATION_DATE}}`. All other tokens live in the parent role file.*
