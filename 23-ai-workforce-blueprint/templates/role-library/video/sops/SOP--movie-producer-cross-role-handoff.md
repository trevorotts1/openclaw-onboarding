# SOP -- Movie Producer (Automated Video Production) — Cross-Role Handoff

**Source:** video/automated-video-production-specialist-openmontage.md (registered slug UNCHANGED).
**Authority:** Cross-role handoff contracts for the Movie Producer role. Every pipeline-type SOP (`documentary-montage`, `short-form`, `vsl`) ends by routing through this SOP. Defines the inbound work this role receives and the outbound handoffs it makes, with explicit boundaries that prevent scope creep and duplicate reimplementation.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 47-movie-producer (clones the upstream OpenMontage engine on the client box at runtime — AGPLv3 source NEVER vendored)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> **Boundary rule:** The Movie Producer autonomously produces and renders a finished, ffprobe-validated MP4 FROM a brief, manifest, and (optionally) Kie-generated assets. It NEVER reimplements captioning (Skill 26), premium TTS (Skill 30), hands-on footage editing (Skill 27 / `video-editor.md`), or motion-graphics overlays. Those are handoffs, not in-pipeline work.

---

## DMAIC Coverage Map

- **Define** — define the inbound handoff contract (what a complete inbound brief contains) (SOP CRH-1).
- **Measure** — measure handoff-package completeness before sending (SOP CRH-2).
- **Analyze** — analyze which downstream role each output needs, and confirm boundaries (SOP CRH-3).
- **Improve** — execute the outbound handoff with the receiving role's required inputs (SOP CRH-4).
- **Control** — track handoff acceptance and close the loop (SOP CRH-5).

---

## Define

*DMAIC phase: Define. Define exactly what a complete inbound brief contains so this role never starts on a partial input.*

### SOP CRH-1 -- [VID-MP-CRH-1] Inbound Handoff Contract

**DMAIC phase:** Define
**When to run:** When work is received from an upstream role.
**Frequency:** Per inbound handoff.
**Inputs:** The inbound brief or artifact.

**Steps:**

1. Identify the sender and the inbound contract:
   - **Head of Video Production** → approved production briefs, budget ceilings, quality standards.
   - **Long-Form Video Specialist / Deep Research Specialist (Video)** → researched topic outlines / narrative material to seed a documentary-montage run.
   - **VSL (Video Sales Letter) Specialist** → a FINISHED VSL script + offer structure + brand asset references for the VSL pipeline.
2. Validate the inbound artifact against the receiving pipeline's Define SOP (DM-1 / SF-1 / VSL-1). If anything required is missing, return a specific gap list to the sender — do NOT start on a partial input.
3. Record the inbound source and contract in the job manifest (`requestor`, inbound artifact reference).

**Outputs:** Validated inbound brief, gap list (if incomplete) returned to sender.
**Hand to:** The matching pipeline-type SOP's Define step.
**Failure mode:** Accepting a VSL "brief" that is only a topic. The VSL pipeline renders a script; an un-scripted inbound is incomplete.

---

## Measure

*DMAIC phase: Measure. Verify the outbound handoff package is complete before sending it downstream.*

### SOP CRH-2 -- [VID-MP-CRH-2] Outbound Package Completeness Check

**DMAIC phase:** Measure
**When to run:** After a pipeline-type SOP produces a validated MP4, before routing the handoff.
**Frequency:** Per outbound handoff.
**Inputs:** The validated MP4, `render-receipt.json`, `job-manifest.json`, Kie receipts (if paid).

**Steps:**

1. Confirm the package contains: the ffprobe-validated MP4 (absolute path), the `render-receipt.json` (ffprobe fields present), the `job-manifest.json` (final state), the Kie task receipt log (for paid jobs), and a delivery note (pipeline name, run date, total cost, duration, resolution).
2. Confirm the MP4 passed its pipeline's Control-phase QC (no hardcoded client names or personal data; on-brief; receipts real, not fabricated).
3. If any element is missing, return to the pipeline-type SOP's Control step to complete it before handoff.

**Outputs:** Verified-complete handoff package.
**Hand to:** SOP CRH-3 (routing decision).
**Failure mode:** Handing off an MP4 without the ffprobe receipt. The receipt is the proof the render is valid for the downstream platform.

---

## Analyze

*DMAIC phase: Analyze. Decide which downstream role each output needs and confirm the boundary is honored.*

### SOP CRH-3 -- [VID-MP-CRH-3] Routing Decision and Boundary Confirmation

**DMAIC phase:** Analyze
**When to run:** After SOP CRH-2 confirms a complete package.
**Frequency:** Per outbound handoff.
**Inputs:** The brief's downstream needs, the verified package.

**Steps:**

1. Determine the downstream needs and route:

   | Downstream need | Receiving role | Boundary (do NOT do this in-pipeline) |
   |---|---|---|
   | Captions / SRT subtitles | **Captioning Subtitling Specialist** (Skill 26 / `captioning--subtitling-specialist.md`) | Never run Whisper inside the OpenMontage pipeline. |
   | Premium voice narration (beyond Piper) | **Fish Audio TTS Reference** (Skill 30) | Never reimplement cloud TTS inside the pipeline. |
   | Hands-on editorial cuts / color grade / footage integration | **Video Editor** (Skill 27 / `video-editor.md`) | The Movie Producer renders FROM a brief; the Video Editor edits SUPPLIED footage. Do not route an editing task back into the pipeline. |
   | Animated overlays / lower-thirds / title sequences | **Motion Graphics Specialist** | Do not author kinetic typography in the pipeline. |
   | Final delivery / client approval | **Head of Video Production** | Owner approval gate for client-facing published video. |

2. Confirm the boundary for the chosen route — if the request is actually in-scope for a DIFFERENT pipeline-type SOP (e.g. "produce another version" rather than "edit this one"), route it back as a new production job, not as an edit.

**Outputs:** Routing decision with the receiving role named, boundary confirmed.
**Hand to:** SOP CRH-4 (execute the handoff).
**Failure mode:** Routing an editing request back into the OpenMontage pipeline (scope creep that incurs unnecessary generation cost). The Producer ↔ Editor boundary is binding.

---

## Improve

*DMAIC phase: Improve. Execute the handoff with exactly the inputs the receiving role requires.*

### SOP CRH-4 -- [VID-MP-CRH-4] Execute the Outbound Handoff

**DMAIC phase:** Improve
**When to run:** After SOP CRH-3 names the receiving role.
**Frequency:** Per outbound handoff.
**Inputs:** The verified package, the receiving role's required inputs.

**Steps:**

1. **To Skill 26 (captions):** provide the MP4 path, the target platform (burn-in vs. sidecar SRT decision), and the language. Example interface: `~/.openclaw/skills/caption-creator/Scripts/generate-captions.sh --input <output>.mp4 --output <captioned>.mp4 --style minimal --model medium`.
2. **To Skill 30 (premium TTS):** provide the narration script and the target voice style. Hand off the script only — do not pre-render narration the receiving role will replace.
3. **To Skill 27 (Video Editor):** provide the assembled MP4 as a sequence segment, the project context, and the editorial brief (what cuts/grade/integration is needed).
4. **To Motion Graphics:** provide the base render and a specific motion brief (lower-third copy, title-sequence spec).
5. **To Head of Video Production:** provide the full delivery package and the ffprobe receipt for final approval.
6. Notify the receiving role and update the production board with the handoff status.

**Outputs:** Handoff delivered with the receiving role's required inputs; production board updated.
**Hand to:** SOP CRH-5 (acceptance tracking).
**Failure mode:** Handing off without the inputs the receiving role needs (e.g. captions request with no language specified), forcing a round-trip.

---

## Control

*DMAIC phase: Control. Track acceptance and close the loop so no handoff stalls silently.*

### SOP CRH-5 -- [VID-MP-CRH-5] Acceptance Tracking and Loop Closure

**DMAIC phase:** Control
**When to run:** After SOP CRH-4 delivers a handoff.
**Frequency:** Per outbound handoff until accepted.
**Inputs:** The handoff record, the receiving role's acceptance status.

**Steps:**

1. Mark the handoff state on the production board (`handed-off`, awaiting acceptance).
2. Follow up if the receiving role has not accepted within the agreed window (default 24 hours). Log each follow-up.
3. On acceptance, mark the job's downstream stage complete in the manifest. On rejection (e.g. caption sync failed, editor flags a render defect), re-open the relevant pipeline-type SOP's Improve step, correct, and re-hand-off — do NOT re-deliver an un-corrected package.
4. If the receiving role is unavailable for 48+ hours, escalate one level up (Head of Video Production; for cross-department conflicts, the Master Orchestrator).

**Outputs:** Closed-loop handoff record; re-work routed (if rejected); escalation (if stalled).
**Hand to:** Head of Video Production for delivery sign-off; the originating pipeline-type SOP for any re-work.
**Failure mode:** Marking a job complete on handoff without confirming acceptance. A handoff is not done until the receiving role accepts it.

---

*SOPs owned: [VID-MP-CRH-1], [VID-MP-CRH-2], [VID-MP-CRH-3], [VID-MP-CRH-4], [VID-MP-CRH-5]. sop_count: 5.*
*Token inventory: `{{COMPANY_NAME}}`, `{{GENERATION_DATE}}`. All other tokens live in the parent role file.*
