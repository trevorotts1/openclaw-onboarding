# SOPs -- Movie Producer (Automated Video Production) — Master DMAIC Index + Rule-Zero

**Source:** video/automated-video-production-specialist-openmontage.md (registered slug UNCHANGED; display title rebranded to "Movie Producer (Automated Video Production)").
**Authority:** This file mirrors Section 9 (Standard Operating Procedures) of the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Department:** Video
**Reports to:** Head of Video Production
**Skill:** 47-movie-producer (installs the upstream OpenMontage engine on the client box at runtime — AGPLv3 source is NEVER vendored into this template)
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> **Multi-SOP set (v14.0.0).** This file is the MASTER DMAIC index and the binding Rule-Zero/budget control for the Movie Producer role. The per-pipeline-type production procedures and the cross-role handoff procedure live in sibling SOP files in this `sops/` folder, each carrying its own DMAIC structure:
> - `SOP--movie-producer-rule-zero-budget.md` — Rule-Zero announce/approve + budget-cap control (the binding safety SOP, applies to every job).
> - `SOP--movie-producer-documentary-montage-pipeline.md` — the free, zero-key real-footage documentary-montage pipeline (FFmpeg path).
> - `SOP--movie-producer-short-form-pipeline.md` — short-form (9:16 Reels/Shorts/TikTok) production pipeline.
> - `SOP--movie-producer-vsl-pipeline.md` — Video Sales Letter (talking-head / branded promotional) pipeline.
> - `SOP--movie-producer-cross-role-handoff.md` — handoff contracts to/from Skill 26 (captions), Skill 30 (TTS), Skill 27 (Video Editor), Motion Graphics, Head of Video Production.

> **Rule Zero (binding on every SOP in this file):** The specialist MUST announce the provider, model identifier, and estimated cost in USD BEFORE any paid API call is submitted. A human-approval checkpoint (see config.yaml `require_approval_for_new_paid_tool: true`, `single_action_approval_usd: 0.50`) MUST be passed before each paid action proceeds. `ffprobe` MUST validate every rendered MP4 before the file is delivered. The client budget cap defined in config.yaml (`budget.mode: cap`, `budget.total_usd`) MUST NOT be exceeded. Violations of Rule Zero are hard stops, not warnings.

> **Kie.AI is the only generative asset provider on the client box.** Skill 47's install writes a `.env` that exposes ONLY `KIE_API_KEY`. All native paid providers (FAL, Runway, HeyGen, OpenAI, Google) will report UNAVAILABLE because their own keys are absent. Free render engines (FFmpeg, Remotion, HyperFrames), free TTS (Piper), and the free public-domain stock corpus (Archive.org, NASA, Wikimedia, Library of Congress, National Archives, NOAA, European Space Agency, JAXA, Pond5 public domain) are ALWAYS preserved and route through their native paths — they are never rewired to Kie.AI.

> **Client-own keys:** all paid generation uses the CLIENT's own `KIE_API_KEY`. The operator's key MUST NEVER appear on the client box.

> **AGPLv3 boundary:** OpenMontage is operated as a client-installed skill. Its source code is never vendored into this fleet-wide template. The two Kie adapter files (`kie_image.py`, `kie_video.py`) shipped by Skill 47 are our own BaseTool subclasses installed into the client's cloned OpenMontage tree.

---

## 9. Standard Operating Procedures (DMAIC-organized)

These SOPs are organized around the DMAIC (Define, Measure, Analyze, Improve, Control) framework adapted for agentic video production. Each phase below is a binding section; the numbered SOPs ([VID-OMP-1xx]) sit under their owning DMAIC phase.

- **Define** — Intake the client brief and select the correct pipeline manifest (SOP 9.1).
- **Measure** — Pre-flight checks, budget measurement, and provider availability audit (SOP 9.2).
- **Analyze** — Rule-Zero announce + approval gate before paid asset generation (SOP 9.3).
- **Improve** — Run the pipeline, render via the FFmpeg documentary-montage path, validate with `ffprobe` (SOP 9.4).
- **Control** — Post-render QC, budget reconciliation, fallback ladder, continuous-improvement review, and handoff to caption/downstream roles (SOPs 9.5–9.7).

---

## Define

*DMAIC phase: Define. Owns SOP 9.1 — establish exactly what is being produced and on which pipeline before any work or spend begins.*

### SOP 9.1 -- [VID-OMP-101] Production Brief Intake and Pipeline Manifest Selection

**DMAIC phase:** Define
**When to run:** When a new video production request arrives from the Head of Video Production, a client agent, or any upstream stakeholder.
**Frequency:** Per production job.
**Inputs:** Written brief (topic, duration, tone, target audience, aspect ratio, budget ceiling in USD, target platform), any reference media (images, existing footage, brand assets), the client's configured `config.yaml` budget cap.

**Steps:**

1. **Receive and parse the brief (5-10 min):** Confirm the brief contains ALL of the following. If any item is missing, return to the requestor with a specific list of what is absent before proceeding. Do NOT make assumptions about missing inputs.
   - Topic or narrative arc
   - Target duration (seconds)
   - Target platform and aspect ratio (16:9 YouTube / 9:16 Reels/TikTok / 1:1 square)
   - Budget ceiling in USD (must not exceed the client's `config.yaml` `budget.total_usd`)
   - Tone (documentary / promotional / educational / narrative)
   - Any required brand assets (logo URL, brand colors, voice style)

2. **Select the OpenMontage pipeline manifest (5 min):** Match the brief to a `pipeline_defs/*.yaml` from the client's installed OpenMontage clone. The primary pipelines available after Skill 47 install:
   - `documentary-montage.yaml` — free real-footage montage from the public-domain stock corpus (Archive.org, NASA, Wikimedia, Library of Congress, National Archives, NOAA, European Space Agency, JAXA, Pond5 PD); `budget_default_usd: 1.00`; ZERO paid API calls; recommended default for cost-zero productions.
   - A Kie-routed pipeline (image or video generation via `KIE_API_KEY`) — required when the brief specifies AI-generated visuals. Budget is non-zero.
   - `make demo` Remotion zero-key demos — for template/preview renders only; not for client deliverables.

   If the brief can be fulfilled by `documentary-montage.yaml` at zero API cost, SELECT that pipeline and skip SOP 9.3 (no paid call = no Rule-Zero announce/approval needed). If the brief requires AI-generated assets, continue through SOP 9.3.

3. **Confirm pipeline feasibility (5 min):** Verify the selected pipeline's required inputs against what the brief provides. Flag any gap (e.g., `documentary-montage.yaml` requires a topic keyword list for CLIP-retrieval; a Kie video pipeline requires a text prompt or reference image URL).

4. **Log the job manifest:** Write a `job-manifest.json` to the client's workspace with: `job_id`, `pipeline_selected`, `brief_summary`, `target_duration_sec`, `aspect_ratio`, `budget_ceiling_usd`, `estimated_cost_usd` (0.00 for free pipelines, non-zero for Kie pipelines — computed in SOP 9.2), `requestor`, `created_at`.

**Outputs:** Completed `job-manifest.json`; gap list returned to requestor if brief is incomplete.
**Hand to:** SOP 9.2 (pre-flight and budget measurement).
**Failure mode:** Starting pipeline execution without a complete brief. Always return the gap list immediately rather than guessing at intent. A production job started on an incomplete brief routinely requires full restart.

---

## Measure

*DMAIC phase: Measure. Owns SOP 9.2 — quantify dependency readiness, provider availability, and the dollar cost of the selected pipeline before committing to a paid run.*

### SOP 9.2 -- [VID-OMP-102] Pre-Flight Checks and Budget Measurement

**DMAIC phase:** Measure
**When to run:** Immediately after SOP 9.1 produces a complete `job-manifest.json`.
**Frequency:** Every production job, no exceptions.
**Inputs:** `job-manifest.json`, client's `config.yaml`, the Skill 47 runtime-dep preflight result.

**Steps:**

1. **Runtime dependency preflight (fail-loud):** Run the Skill 47 `verify-deps.sh` preflight:
   ```
   bash [OPENCLAW_SKILLS]/47-movie-producer/verify-deps.sh
   ```
   This checks: `command -v ffmpeg` (FFmpeg present), `node -v` ≥ 18.0.0 (Node present), `npx --yes hyperframes --version` resolves (HyperFrames available), `python -c "import yaml,pydantic,PIL,requests"` (Python deps installed). If ANY check fails, the preflight exits non-zero with a precise error message naming the missing binary and the client's install command. **NEVER proceed to pipeline execution with a failing preflight.** Deliver the full preflight error output to the client with the exact install instruction; do not attempt a workaround.

2. **Provider availability audit:** Run the OpenMontage registry check to confirm which providers are AVAILABLE vs. UNAVAILABLE on the client box:
   ```
   python3 -c "
   from tools.tool_registry import get_registry
   r = get_registry()
   for c in ['image_generation','video_generation']:
       tools = r.get_by_capability(c)
       print(c)
       for t in tools:
           st = t.get_status()
           print(f'  {t.provider}: {st.status}')
   "
   ```
   EXPECTED: `kie: AVAILABLE` for both `image_generation` and `video_generation`. All native paid providers (flux, veo, runway, heygen, kling, minimax, openai, google, xai, etc.) must show `UNAVAILABLE`. Piper TTS must show `AVAILABLE`. If `kie` shows UNAVAILABLE, verify `KIE_API_KEY` is set in the client `.env` (check all env stores: `secrets/.env`, `openclaw.json`, `~/.openclaw/workspace/.env`). If any native paid provider shows AVAILABLE, halt and notify the Head of Video Production — the client's `.env` has an unexpected key that could route assets outside of Kie.AI.

3. **Budget measurement:** Compute the estimated cost for the selected pipeline:
   - `documentary-montage.yaml` free path: estimated cost = $0.00. No further budget gate needed.
   - Kie image generation (`gpt-image-2-image-to-image` or `gpt-image-2-text-to-image`): check `07-kie-setup/EXAMPLES.md` or the client's `_local/PRICING.md` for current per-task cost. Multiply by the number of image tasks in the pipeline.
   - Kie video generation (`gemini-omni-video` / `veo3` / `veo3_fast`): multiply per-task cost by number of video clips.
   - Sum to a total `estimated_cost_usd`.

4. **Budget gate:** Compare `estimated_cost_usd` against the client `config.yaml` `budget.total_usd` ceiling. If `estimated_cost_usd > budget.total_usd`: **HARD STOP**. Do not proceed. Notify the Head of Video Production with: the pipeline selected, the estimated cost, the configured budget cap, and a recommendation to either (a) switch to the free `documentary-montage.yaml` pipeline or (b) increase the budget cap with explicit client approval.

5. **Update `job-manifest.json`:** Write `estimated_cost_usd`, `provider_audit_pass: true/false`, `preflight_pass: true/false`, `budget_gate_pass: true/false`, `measured_at` (ISO 8601 timestamp).

**Outputs:** Updated `job-manifest.json` with measurement fields; provider audit output; preflight output. Hard stops with escalation message if any gate fails.
**Hand to:** SOP 9.3 (Rule-Zero announce + approval gate) if any paid call is in scope; SOP 9.4 directly if free-only pipeline.
**Failure mode:** Skipping the provider audit and discovering mid-pipeline that assets are routing to an unexpected provider. The two-minute provider audit here prevents a multi-dollar misdirected generation job downstream.

---

## Analyze

*DMAIC phase: Analyze. Owns SOP 9.3 — analyze the planned paid calls against budget and approval policy, and gate them behind an explicit human announce/approve step (Rule Zero) before any spend.*

### SOP 9.3 -- [VID-OMP-103] Rule-Zero: Provider Announce and Approval Gate

**DMAIC phase:** Analyze
**When to run:** For every job that will trigger at least one paid API call (any Kie-routed image or video generation). SKIP for zero-cost jobs (`documentary-montage.yaml` free stock path).
**Frequency:** Per paid job; per new paid tool type encountered (OpenMontage config `require_approval_for_new_paid_tool: true`).
**Inputs:** `job-manifest.json` (with `estimated_cost_usd` populated from SOP 9.2), the list of Kie API calls to be made.

**Steps:**

1. **Compose the Rule-Zero announcement:** Before submitting ANY Kie API call, post the following announcement to the Head of Video Production (or the requesting agent). The announcement MUST contain ALL of the following elements:

   ```
   RULE-ZERO ANNOUNCEMENT — APPROVAL REQUIRED

   Job ID:              [job_id from manifest]
   Pipeline:            [pipeline_defs yaml selected]

   Paid calls in scope:
     Image generation:  [count] x gpt-image-2-image-to-image  (or gpt-image-2-text-to-image)
                        Provider: Kie.AI | Endpoint: POST https://api.kie.ai/api/v1/jobs/createTask
                        Est. cost per call: $[per_call_usd]
     Video generation:  [count] x gemini-omni-video (default) or veo3_fast (fallback)
                        Provider: Kie.AI
                        Endpoint (gemini-omni-video): POST https://api.kie.ai/api/v1/jobs/createTask
                        Endpoint (veo3/veo3_fast):    POST https://api.kie.ai/api/v1/veo/generate
                        Est. cost per call: $[per_call_usd]

   Total estimated cost:  $[estimated_cost_usd]
   Client budget cap:     $[config_budget_total_usd]
   Remaining budget:      $[remaining_usd]

   Client key used:       KIE_API_KEY (client-owned; operator key is NEVER used)

   WAITING FOR APPROVAL. Type APPROVE to proceed, or REJECT to cancel.
   ```

2. **Wait for explicit approval:** Do NOT proceed to SOP 9.4 until the Head of Video Production (or the configured approval authority) returns `APPROVE` (case-insensitive). If `REJECT` is returned, cancel the job and update `job-manifest.json` with `status: rejected`, `rejected_at`, `rejection_reason`.

3. **Per-call approval for new paid tool types:** OpenMontage `config.yaml` has `require_approval_for_new_paid_tool: true`. If this job introduces a paid tool type (model ID) not previously used on this client box, a SECOND approval prompt is required scoped to that tool type. This is automatic from the OpenMontage config — verify it is honored before pipeline execution.

4. **Single-action approval threshold:** Any single Kie API call estimated at ≥ $0.50 (the `single_action_approval_usd` value from `config.yaml`) requires its own individual approval before that specific call is submitted. If a pipeline produces multiple calls in sequence, each call at or above $0.50 gets its own prompt.

5. **Record the approval:** Write to `job-manifest.json`: `rule_zero_announced_at`, `approval_received_at`, `approved_by`, `approved_total_usd`.

**Outputs:** Approval receipt in `job-manifest.json`; or cancellation record if rejected.
**Hand to:** SOP 9.4 (pipeline execution and rendering) upon approval.
**Failure mode:** Submitting a Kie API call without the Rule-Zero announcement and approval. This is a hard violation — the job must be halted, the already-submitted call recorded as an unauthorized spend event in an incident log, and the Head of Video Production notified. Unauthorized spend events are escalated to the owner.

---

## Improve

*DMAIC phase: Improve. Owns SOP 9.4 — execute the pipeline, generate any approved Kie assets, render the final cut via the FFmpeg documentary-montage path, and prove the output with `ffprobe`.*

### SOP 9.4 -- [VID-OMP-104] Pipeline Execution, Rendering, and ffprobe Validation

**DMAIC phase:** Improve
**When to run:** After SOP 9.2 (free jobs) or SOP 9.3 approval receipt (paid jobs).
**Frequency:** Per production job.
**Inputs:** Approved `job-manifest.json`, selected `pipeline_defs/*.yaml`, the Movie Producer skill directory on client box (`[OPENCLAW_SKILLS]/47-movie-producer/`).

**Pipeline execution steps:**

1. **Set the OpenMontage working directory:** `cd` to the client's cloned OpenMontage directory (installed by Skill 47 at `~/.openclaw/skills/47-movie-producer/OpenMontage/` or the path configured during install). Verify the Kie adapters are present: `ls tools/graphics/kie_image.py tools/video/kie_video.py` — both must exist. If either is missing, re-run Skill 47 install (the adapters are dropped from `47-movie-producer/kie-adapters/` into the clone's `tools/` directories).

2. **Execute the pipeline via the OpenMontage stage-director skills:** Drive the pipeline per the selected `pipeline_defs/*.yaml` manifest using OpenMontage's skills orchestration. The AI coding assistant (the agent running this SOP) IS the orchestrator per OpenMontage README line 329: "There is no code orchestrator. Your AI coding assistant IS the orchestrator." Execute each stage in the YAML definition in order. Do not skip stages.

3. **Free documentary-montage path (zero Kie calls):** For `documentary-montage.yaml`, the pipeline retrieves real footage from the free public-domain corpus (Archive.org/NASA/Wikimedia/Library of Congress/National Archives/NOAA/European Space Agency/JAXA/Pond5 public domain) via CLIP-retrieval, assembles clips, runs Piper TTS for narration (offline, no API key), and stitches via FFmpeg. No Kie API calls are made. Confirm `budget.mode: cap` and `budget.total_usd` are configured before running even the free path (to prevent any accidental paid tool invocation).

4. **Kie image generation calls (when in scope):**

   Model selection:
   - Use `gpt-image-2-image-to-image` when source reference images are provided in the brief (`image_input` field populated)
   - Use `gpt-image-2-text-to-image` when generating from text prompt only (no source images)

   API call shape (must match `07-kie-setup/EXAMPLES.md` and `46-kie-callback-relay/kie-slide-submitter.js`):
   ```
   POST https://api.kie.ai/api/v1/jobs/createTask
   Authorization: Bearer ${KIE_API_KEY}
   Content-Type: application/json

   {
     "model": "gpt-image-2-image-to-image",
     "input": {
       "prompt":        "[text prompt]",
       "image_input":   ["[reference_image_url]"],
       "aspect_ratio":  "16:9",
       "resolution":    "2K",
       "output_format": "png"
     }
   }
   ```
   Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=[taskId]` with `Authorization: Bearer ${KIE_API_KEY}` until `data.status == "success"`. Download `.data.resultJson.resultUrls[0]` to local output path. Record `kie_task_id` and `kie_result_url` in the job manifest as the render-proof receipt.

5. **Kie video generation calls (when in scope):**

   Model routing:
   - **Default:** `gemini-omni-video` — use when reference images are available or for image-to-video generation
   - **Fallback:** `veo3` or `veo3_fast` — use when no reference image is available (text-to-video)

   API call shape for `gemini-omni-video` (must match `37-zhc-closeout/scripts/generate-celebration-video.sh`):
   ```
   POST https://api.kie.ai/api/v1/jobs/createTask
   Authorization: Bearer ${KIE_API_KEY}
   Content-Type: application/json

   {
     "model": "gemini-omni-video",
     "input": {
       "prompt":          "[text prompt]",
       "image_urls":      ["[reference_image_url]"],
       "duration":        "8",
       "aspect_ratio":    "16:9",
       "generate_audio":  true
     }
   }
   ```
   CRITICAL: `duration` MUST be a STRING (`"8"` not `8`) — Kie rejects integer duration with HTTP 422 (verified fix in `generate-celebration-video.sh` line 432). Valid string durations: `"4"`, `"6"`, `"8"`. Always set `aspect_ratio` — omitting it causes HTTP 422 (verified fix, `generate-celebration-video.sh` line 421-422). Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=[taskId]`.

   API call shape for `veo3` / `veo3_fast` fallback:
   ```
   POST https://api.kie.ai/api/v1/veo/generate
   Authorization: Bearer ${KIE_API_KEY}
   Content-Type: application/json

   {
     "model":          "veo3_fast",
     "prompt":         "[text prompt]",
     "aspect_ratio":   "16:9",
     "duration":       8,
     "generate_audio": true
   }
   ```
   Poll `GET https://api.kie.ai/api/v1/veo/record-info?taskId=[taskId]`. Note: `veo/generate` + `veo/record-info` is a DIFFERENT endpoint path than the `gemini-omni-video` `createTask` + `recordInfo` path (verified in `generate-celebration-video.sh` lines 541-559).

6. **Render via FFmpeg (the documentary-montage path and all final stitches):** All video compilation and stitching uses FFmpeg — the exclusive render path for the documentary-montage pipeline and final assembly. Do NOT invoke Remotion or HyperFrames for the documentary-montage render path (those are for the Remotion demo path and HyperFrames composition path respectively). Each render target uses the client's configured output spec (codec, resolution, frame rate).

7. **ffprobe validation (MANDATORY for every rendered MP4, no exceptions):** After every render, run:
   ```
   ffprobe -v error \
     -show_entries format=duration,format_name \
     -show_entries stream=codec_type,codec_name,width,height \
     -of json \
     [output_file.mp4]
   ```
   PASS criteria (all must be true):
   - `format.duration` > 0 (nonzero duration)
   - `format.format_name` contains `mp4` or `mov,mp4,m4a,...`
   - At least one stream with `codec_type == "video"` present
   - Video stream `width` and `height` match the requested output resolution

   If ffprobe fails to parse the file, or any criterion is not met: **DO NOT DELIVER the file**. Log the failure to `_local/render-failures/[job_id]/`. Attempt one retry of the FFmpeg render command. If the second render also fails ffprobe validation, halt and escalate to Head of Video Production with the full ffprobe JSON output.

8. **Record all render receipts:** For each rendered output, write to `_local/receipts/[job_id]/render-receipt.json`:
   ```
   {
     "job_id":           "[job_id]",
     "output_path":      "[absolute path to MP4]",
     "kie_task_id":      "[kie_task_id or null]",
     "kie_result_url":   "[kie_result_url or null]",
     "ffprobe_pass":     true,
     "ffprobe_duration": [duration_seconds],
     "ffprobe_codec":    "[codec_name]",
     "ffprobe_width":    [width],
     "ffprobe_height":   [height],
     "rendered_at":      "[ISO 8601]"
   }
   ```

**Outputs:** Rendered and ffprobe-validated MP4 at `_local/outputs/[job_id]/`; `render-receipt.json` with all receipt fields; Kie task IDs and result URLs as anti-fabrication proof for any paid generation.
**Hand to:** SOP 9.5 (post-render QC and handoff).
**Failure mode:** Delivering an MP4 that has not passed ffprobe validation. The ffprobe step is non-negotiable — a file that plays on the specialist's local machine may fail silently on the client's delivery platform due to codec incompatibility or corruption. The ffprobe JSON is the proof of a valid render.

---

## Control

*DMAIC phase: Control. Owns SOPs 9.5–9.7 — lock in quality and budget control after the render: post-render QC and handoff (9.5), the failure-mode fallback ladder (9.6), and the monthly continuous-improvement review (9.7). These are the standing controls that keep every future production within spec and budget.*

### SOP 9.5 -- [VID-OMP-105] Post-Render QC, Budget Reconciliation, and Handoff

**DMAIC phase:** Control
**When to run:** After SOP 9.4 produces a validated, ffprobe-passed MP4.
**Frequency:** End of every production job.
**Inputs:** `render-receipt.json`, `job-manifest.json`, Kie API receipts (if paid generation was used), the client's `config.yaml` budget config.

**Steps:**

1. **Content QC checklist (5-10 min):** Review the rendered MP4 against the original brief:
   - [ ] Correct target duration (within ±5% of the brief's target seconds)
   - [ ] Correct aspect ratio (verified in ffprobe output)
   - [ ] All required brand assets appear (logo, brand colors, if specified in brief)
   - [ ] No visible render artifacts (black frames, glitches, dropped clips, audio sync issues)
   - [ ] No hardcoded client names, operator keys, or identifiable personal data (fleet-template rule)
   - [ ] Narration (if Piper TTS was used) is intelligible and matches the script
   - [ ] If AI-generated visuals were used: Kie `kie_task_id` and `kie_result_url` are present in `render-receipt.json` as proof of genuine generation (not fabricated)

2. **Budget reconciliation:** Sum all Kie API calls made during this job from the receipts. Compare actual spend to the `estimated_cost_usd` from `job-manifest.json`. If actual > estimated: log the variance to `_local/budget-log.md` with the job ID, estimated vs. actual, and the cause. If actual spend causes the cumulative client spend to approach the `config.yaml` `budget.total_usd` cap (>80%), notify Head of Video Production immediately with the budget status before initiating any new jobs.

3. **Circuit-breaker check:** If the budget cap has been reached or exceeded: halt all further production on this client box; notify Head of Video Production; write a circuit-breaker entry to `_local/budget-log.md`. Do not proceed with additional jobs until the Head of Video Production provides explicit written authorization and updates the budget cap.

4. **Update the full job manifest to final state:** In `job-manifest.json`:
   ```
   {
     "status":           "complete",
     "actual_cost_usd":  [sum of all Kie charges],
     "budget_remaining": [config.total_usd - actual_cost_usd],
     "output_path":      "[absolute path to delivered MP4]",
     "kie_task_ids":     ["[task_id_1]", "..."],
     "kie_result_urls":  ["[result_url_1]", "..."],
     "ffprobe_pass":     true,
     "completed_at":     "[ISO 8601]",
     "delivered_to":     "[head-of-video-production or requestor role]"
   }
   ```

5. **Handoff routing:**
   - If captions/subtitles are needed: hand the MP4 to the **Captioning Subtitling Specialist** (Skill 26 / `captioning--subtitling-specialist.md`). Provide: the output MP4 path, target platform (for burn-in vs. sidecar SRT decision), language.
   - If TTS narration was not included and a human voiceover is needed: hand to the **Head of Video Production** for voiceover coordination (the Piper TTS path or client ElevenLabs if configured).
   - If additional video editing (cuts, pacing, music mixing) is needed AFTER OpenMontage's pipeline has produced the raw assembled output: hand to the **Video Editor** (`video-editor.md` / Skill 27). BOUNDARY: OpenMontage produces a finished assembled video FROM a brief; Skill 27 / `video-editor.md` is for hands-on editing of supplied footage. Do NOT route an editing task back into the OpenMontage pipeline — that is scope creep and will incur unnecessary generation costs.
   - If the video is ready for final delivery: notify the Head of Video Production with the output path, ffprobe receipt, and job manifest.

6. **Archive job assets:** Move completed job assets to `_local/archive/[job_id]/` — MP4 output, all receipts, the job manifest, and Kie result URLs. Retain the `render-receipt.json` and `job-manifest.json` permanently (budget audit trail).

**Outputs:** Delivered and QC-passed MP4; finalized `job-manifest.json` with `status: complete`; budget reconciliation entry; handoff notification to the next role in the pipeline.
**Hand to:** Captioning Subtitling Specialist (Skill 26) for captions; Video Editor (Skill 27) for post-editing; Head of Video Production for delivery approval and final sign-off.
**Failure mode:** Treating a QC-fail as a pass because "it looks close enough." Any item failing the content QC checklist — especially a missing `kie_task_id`/`kie_result_url` where Kie generation was claimed — is a hard failure. Missing Kie receipts means either the generation did not happen (fabrication) or the receipts were not recorded (a logging failure). Either is unacceptable. Rerun the generation or recover the receipts from the API log before delivering.

---

### SOP 9.6 -- [VID-OMP-106] Fallback Ladder and Graceful Degradation

**DMAIC phase:** Control (failure mode branch)
**When to run:** When any API call, render command, or dependency check fails during a production job.
**Frequency:** On-demand, triggered by failures.
**Inputs:** The failed operation, its error output, the current `job-manifest.json` state.

**Failure class ladder (execute in order; never skip to a lower rung without trying the one above it):**

| Failure class | First response | Second response | Hard stop |
|---|---|---|---|
| **Kie HTTP 422** | Check: `duration` must be a STRING `"8"` not integer; `aspect_ratio` must be set. Fix the call body and retry once. | If still 422: review the full error body and return it to Head of Video Production with the call body diff. | If cause unclear after review: halt and escalate. |
| **Kie HTTP 5xx / timeout** | Retry once after 30-second backoff. | Switch to fallback model: if `gemini-omni-video` fails, retry with `veo3_fast` (different endpoint: `/api/v1/veo/generate`). Notify Head of Video Production. | If fallback also fails: halt, preserve manifest and receipts, notify Head of Video Production. |
| **Kie HTTP 429 (rate limit)** | Back off per Kie rate-limit guidance; halve concurrent requests. | Continue with reduced concurrency. | If 429 persists more than 3 events in 10 minutes: halt, notify Head of Video Production. |
| **Kie HTTP 402 (credit exhaustion)** | Immediate halt. Do NOT retry. Preserve manifest and receipts. Notify Head of Video Production. Client must refill Kie.AI credits. | -- | -- |
| **FFmpeg render failure** | Check the FFmpeg error output for codec, path, or permission issues. Correct the command and retry once. | If a second render also fails: halt and escalate to Head of Video Production with the full FFmpeg stderr. | -- |
| **ffprobe validation fail** | Retry the FFmpeg render once. | If the second render also fails ffprobe: halt, log to `_local/render-failures/`, escalate to Head of Video Production. | -- |
| **Runtime dep missing (FFmpeg/Node/npx hyperframes/Piper)** | Return the Skill 47 preflight error message and the exact client install command (do not improvise the fix). | -- | -- |
| **KIE_API_KEY missing at generation time** | Check all env stores: `secrets/.env`, `openclaw.json`, `~/.openclaw/workspace/.env`, `~/clawd/secrets/.env`. If found: load it and retry. | If not found in any store: halt and notify Head of Video Production — the key is missing from the client box. | Never use the operator's key. |

**Absolute rules (violations are escalation events, not judgment calls):**
- NEVER switch from the Kie provider to a native paid provider (FAL, Runway, HeyGen, OpenAI) mid-job. If Kie is unavailable, the job pauses — it does not silently fall back to a different paid provider.
- NEVER silently downgrade resolution or aspect ratio. If the requested spec is unavailable, return a gap list to the requestor; do not generate at a different spec without explicit approval.
- NEVER fabricate a `kie_task_id` or `kie_result_url`. If the API call failed, the receipt reflects the failure — do not invent a success receipt.
- NEVER route infra failures (429, 5xx, 402) to a content QC step. These are infrastructure events, not quality issues.
- ALWAYS preserve `job-manifest.json` and all partial receipts on any hard stop. The manifest is the audit trail.

**Outputs:** Fallback event logged to `_local/fallback-log.md` with timestamp, failure class, operation affected, and action taken. Head of Video Production notified for all non-transient events.
**Hand to:** Resumption of the failed SOP step if the fallback resolves the issue; Head of Video Production for all hard-stop events.

---

### SOP 9.7 -- [VID-OMP-107] Continuous Improvement Review

**DMAIC phase:** Control (improvement loop)
**When to run:** Monthly (first session of each calendar month), or immediately after any job that produced a hard stop, a budget overage, or a QC fail.
**Frequency:** Monthly standard review; on-demand for post-incident review.
**Inputs:** Last 30 days of completed `job-manifest.json` files, `_local/budget-log.md`, `_local/fallback-log.md`, `_local/render-failures/` directory, any Head of Video Production feedback.

**Steps:**

1. **Aggregate metrics:** Compute for the prior 30-day period:
   - Jobs completed vs. jobs that hit hard stops
   - Average actual cost vs. estimated cost (variance percentage)
   - FFmpeg render failure rate
   - Kie API call failure rate (by model and endpoint)
   - ffprobe validation failure rate
   - Times a fallback model was invoked (gemini-omni-video → veo3_fast)

2. **Flag any metric outside target thresholds:**
   - Render failure rate > 5%: investigate FFmpeg command templates
   - Kie failure rate > 10%: check for Kie API changes or client credit status
   - Cost variance > 20%: review estimation method in SOP 9.2

3. **Root-cause any hard stops or budget overages from the period.** For each: what SOP step failed or was not followed? Write a one-paragraph root cause summary.

4. **Update SOP steps that caused repeated failures.** Version the change with today's date in a `[UPDATED YYYY-MM-DD]` tag on the affected step. Do NOT change the Rule-Zero constraints (SOP 9.3), ffprobe validation (SOP 9.4 step 7), or the client-own-keys rule — these are binding safety controls.

5. **Present a one-page improvement summary to Head of Video Production** at the next weekly sync. Include: metrics, top 2 improvement actions taken, any SOP steps revised.

**Outputs:** Revised SOP steps (if warranted); improvement log entry in `_local/improvement-log.md`; one-page summary to Head of Video Production.
**Hand to:** Head of Video Production.
**Failure mode:** If no data is available (no completed jobs this period), report the absence of data explicitly. Do not skip the review or generate fabricated metrics.

---

*SOPs owned: [VID-OMP-101], [VID-OMP-102], [VID-OMP-103], [VID-OMP-104], [VID-OMP-105], [VID-OMP-106], [VID-OMP-107]. sop_count: 7.*

*Handoff boundary (vs. Skill 27 / Video Editor):*
- **This role (OpenMontage Pipeline Operator):** autonomously produces and renders a finished video FROM a brief, a pipeline manifest, and (optionally) Kie.AI-generated assets. The output is a complete, ffprobe-validated MP4.
- **Video Editor (Skill 27 / `video-editor.md`):** hands-on editing of supplied footage in Premiere Pro / DaVinci Resolve / Final Cut Pro / CapCut. Use when the brief is "edit THIS footage," not "produce a video FROM this brief."
- If both are needed: OpenMontage runs first to produce the assembled raw output, then Video Editor refines it. The two roles do not overlap.

*Token inventory: `{{COMPANY_NAME}}`, `{{GENERATION_DATE}}`. All other tokens (`{{ASSIGNED_PERSONA}}`, `{{ASSIGNED_PERSONA_VERSION}}`, `{{COMPANY_INDUSTRY}}`, etc.) live in the parent role file.*
