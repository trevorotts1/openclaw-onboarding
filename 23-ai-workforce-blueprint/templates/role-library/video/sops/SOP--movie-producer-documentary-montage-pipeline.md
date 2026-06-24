# SOP -- Movie Producer (Automated Video Production) — Documentary-Montage Pipeline

**Source:** video/automated-video-production-specialist-openmontage.md (registered slug UNCHANGED).
**Authority:** Pipeline-type SOP for the FREE, zero-key real-footage documentary-montage pipeline. Defers all budget/approval control to `SOP--movie-producer-rule-zero-budget.md`. This pipeline is the recommended default for cost-zero productions.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 47-movie-producer (clones the upstream OpenMontage engine on the client box at runtime — AGPLv3 source NEVER vendored)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> **Cost profile:** ZERO paid API calls. Footage comes from the free public-domain corpus (Archive.org, NASA, Wikimedia, Library of Congress, National Archives, NOAA, European Space Agency, JAXA, Pond5 public domain); narration is Piper free offline TTS; composition is FFmpeg. `documentary-montage.yaml` ships `budget_default_usd: 1.00`. Because no paid call is made, the Rule-Zero announce/approve gate (`SOP--movie-producer-rule-zero-budget.md` RZ-3/RZ-4) is SKIPPED — but `budget.mode: cap` must still be set (RZ-1) so no accidental paid tool can fire.

---

## DMAIC Coverage Map

- **Define** — confirm the brief fits the free corpus and pick keywords (SOP DM-1).
- **Measure** — verify clip availability and dependency readiness before assembling (SOP DM-2).
- **Analyze** — confirm the no-paid-call routing (every asset is free corpus / Piper) (SOP DM-3).
- **Improve** — retrieve, assemble, FFmpeg-render, and ffprobe-validate (SOP DM-4).
- **Control** — QC the montage, archive, and route handoff (SOP DM-5).

---

## Define

*DMAIC phase: Define. Confirm the topic is coverable from the free corpus and lock the retrieval keywords.*

### SOP DM-1 -- [VID-MP-DM-1] Topic Fit and Keyword Lock

**DMAIC phase:** Define
**When to run:** When a documentary, explainer, or educational brief is routed to the free path.
**Frequency:** Per documentary-montage job.
**Inputs:** Brief (topic, narrative arc, target duration, aspect ratio, tone).

**Steps:**

1. Confirm the brief is a fit for real-footage documentary content (public topic, no brand-new generated visuals required). If brand-original generated imagery is required, this is NOT a documentary-montage job — route to the short-form or VSL pipeline SOP instead.
2. Lock a CLIP-retrieval keyword list (5-12 terms) covering the narrative arc's beats. Include synonyms and adjacent terms to widen corpus coverage.
3. Draft the section narrative outline (3-7 sections) that the retrieved clips will illustrate.
4. Confirm `budget.mode: cap` is set per `SOP--movie-producer-rule-zero-budget.md` RZ-1 (even though spend is $0.00, the cap prevents an accidental paid tool invocation).

**Outputs:** Keyword list, section outline, confirmation the job is free-path-eligible.
**Hand to:** SOP DM-2 (availability + dependency check).
**Failure mode:** Forcing a brand-original-visual brief through the free path. The corpus is real archival footage; it cannot produce a specific branded scene that does not exist as public-domain footage.

---

## Measure

*DMAIC phase: Measure. Verify enough usable clips exist and the runtime deps are healthy before assembling.*

### SOP DM-2 -- [VID-MP-DM-2] Clip Availability and Dependency Preflight

**DMAIC phase:** Measure
**When to run:** After SOP DM-1 locks keywords.
**Frequency:** Per documentary-montage job.
**Inputs:** Keyword list, the Skill 47 `verify-deps.sh` preflight, the free stock corpus sources.

**Steps:**

1. Run the Skill 47 runtime-dependency preflight (`bash [OPENCLAW_SKILLS]/47-movie-producer/verify-deps.sh`): FFmpeg present, Node ≥18, `npx hyperframes --version` resolves, Python deps import. NEVER proceed on a failing preflight — return the precise error and the client's install command.
2. Run a CLIP-retrieval availability pass against the free corpus for the locked keywords. Count usable clips per source.
3. If fewer than 5 usable clips return for the topic: widen keywords and try all 9 corpus sources explicitly. If still insufficient, escalate per the role file's Edge Case 17.2 (reduce duration, reframe topic, or switch to a paid pipeline with budget approval).

**Outputs:** Confirmed clip inventory (count + source per keyword), passing dependency preflight.
**Hand to:** SOP DM-3 (no-paid-call routing confirmation).
**Failure mode:** Skipping the dependency preflight and discovering mid-assembly that FFmpeg or Node is missing. The preflight is fail-loud for exactly this reason.

---

## Analyze

*DMAIC phase: Analyze. Prove the run will make zero paid calls before it starts.*

### SOP DM-3 -- [VID-MP-DM-3] Zero-Paid-Call Routing Confirmation

**DMAIC phase:** Analyze
**When to run:** Immediately before assembly begins.
**Frequency:** Per documentary-montage job.
**Inputs:** The provider availability audit, the pipeline manifest.

**Steps:**

1. Run the OpenMontage registry audit. Confirm the documentary-montage pipeline uses only the free stock sources and Piper TTS — no `image_generation` or `video_generation` tool is invoked.
2. Confirm `kie` is the only AVAILABLE generative provider (so even if a stage tried to generate, it could only route to Kie — but this pipeline must not invoke generation at all). Native paid providers must show UNAVAILABLE.
3. Record `estimated_cost_usd: 0.00` in the manifest. Because the estimate is zero, the Rule-Zero announce/approve gate is correctly skipped.

**Outputs:** Provider-audit confirmation, `estimated_cost_usd: 0.00` in the manifest.
**Hand to:** SOP DM-4 (retrieve, assemble, render).
**Failure mode:** Assuming the run is free without auditing. A misconfigured manifest could invoke a paid generation stage; the audit catches it before any spend.

---

## Improve

*DMAIC phase: Improve. Retrieve the footage, assemble via FFmpeg, and prove the render with ffprobe.*

### SOP DM-4 -- [VID-MP-DM-4] Retrieve, Assemble, FFmpeg Render, ffprobe Validate

**DMAIC phase:** Improve
**When to run:** After SOP DM-3 confirms zero-paid routing.
**Frequency:** Per documentary-montage job.
**Inputs:** Clip inventory, section outline, the OpenMontage clone at `~/.openclaw/skills/47-movie-producer/OpenMontage/`.

**Steps:**

1. `cd` to the OpenMontage clone. Drive `documentary-montage.yaml` per the OpenMontage staged-pipeline model (the AI coding assistant IS the orchestrator). Retrieve clips from the free corpus via CLIP-retrieval.
2. Generate section narration with Piper (offline, no API key). Mix audio to a consistent loudness target.
3. Compose and stitch the final timeline with FFmpeg — the EXCLUSIVE render path for the documentary-montage pipeline. Do NOT invoke Remotion or HyperFrames for this path. Apply the client's output spec (codec, resolution, frame rate, aspect ratio from the brief).
4. Run ffprobe on the rendered MP4: `ffprobe -v error -show_entries format=duration,format_name -show_entries stream=codec_type,codec_name,width,height -of json [output].mp4`. PASS requires: `format.duration` > 0; `format_name` contains `mp4`/`mov`; at least one `codec_type: video` stream; width/height match the requested resolution. On fail, retry the render once; if the second render also fails ffprobe, halt and escalate with the full ffprobe JSON.
5. Write `render-receipt.json` (output path, `kie_task_id: null`, `kie_result_url: null`, ffprobe fields, rendered_at).

**Outputs:** ffprobe-validated MP4, `render-receipt.json` with `null` Kie fields (free path).
**Hand to:** SOP DM-5 (QC + handoff).
**Failure mode:** Marking the render complete because an MP4 file exists. A file existing is not a render succeeding — ffprobe is the non-negotiable proof.

---

## Control

*DMAIC phase: Control. QC the montage against the brief, archive, and route the handoff.*

### SOP DM-5 -- [VID-MP-DM-5] Montage QC, Archive, and Handoff Routing

**DMAIC phase:** Control
**When to run:** After SOP DM-4 produces a validated MP4.
**Frequency:** End of every documentary-montage job.
**Inputs:** `render-receipt.json`, the brief, the rendered MP4.

**Steps:**

1. Content QC: correct duration (±5%), correct aspect ratio (per ffprobe), narration intelligible and on-script, no black frames or silent gaps > 2s, no hardcoded client names or personal data in any on-screen text (fleet-template rule).
2. Confirm rights-clarity: every clip came from a public-domain corpus source. Record the per-clip source attribution in the delivery note.
3. Archive job assets to `_local/archive/[job_id]/`. Retain `render-receipt.json` and `job-manifest.json` permanently.
4. Route handoff per `SOP--movie-producer-cross-role-handoff.md` (captions → Skill 26; editorial → Skill 27; delivery → Head of Video Production).

**Outputs:** QC-passed montage, source-attribution note, archived assets, handoff routed.
**Hand to:** `SOP--movie-producer-cross-role-handoff.md`.
**Failure mode:** Delivering without per-clip source attribution. Rights-clarity is the value of the free corpus; the attribution is the proof.

---

*SOPs owned: [VID-MP-DM-1], [VID-MP-DM-2], [VID-MP-DM-3], [VID-MP-DM-4], [VID-MP-DM-5]. sop_count: 5.*
*Token inventory: `{{COMPANY_NAME}}`, `{{GENERATION_DATE}}`. All other tokens live in the parent role file.*
