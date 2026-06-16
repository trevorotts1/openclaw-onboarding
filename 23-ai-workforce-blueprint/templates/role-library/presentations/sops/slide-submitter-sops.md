# SOPs Mirror -- Slide Submitter

**Source:** presentations/slide-submitter.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Model Manifest and Variant Selection

**When to run:** At the very start of Phase 4, before the first API call.

**Inputs:**
- MODEL MANIFEST from master SOP (Section 9.0 of the master SOP)
- working/copy/intake.json (LOGO_ON_SLIDES, LOGO_URL fields)
- working/copy/media_library.json (LOGO_URL, FOUNDER_PORTRAIT_URL)

**Steps:**
1. Read the MODEL MANIFEST from the master SOP. It specifies exactly two models:
   - `gpt-image-2-image-to-image` (i2i): the DEFAULT whenever LOGO_ON_SLIDES = true in intake.json. Every call passes input_urls beginning with LOGO_URL (from media_library.json). Slides assigned archetype A5 (founder portrait) append FOUNDER_PORTRAIT_URL. Maximum 16 URLs; all public https. This is also used any time reference images are available.
   - `gpt-image-2-text-to-image` (t2i): used ONLY when there are no reference images at all (LOGO_ON_SLIDES = false AND no founder portrait URL and no other reference images).
2. Read `LOGO_ON_SLIDES` from intake.json.
3. Set `model_variant`:
   - If LOGO_ON_SLIDES = true (or any reference images exist): `gpt-image-2-image-to-image`.
   - If LOGO_ON_SLIDES = false AND no reference images of any kind: `gpt-image-2-text-to-image`.
4. Write the model_variant selection to working/checkpoints/phase4_checkpoint.json: `{ "model_variant": "...", "selected_at": "...", "manifest_version": "..." }`.
5. If the MODEL MANIFEST specifies a different model than these two defaults, use the manifest's specification. The manifest takes precedence. Never use a model not in the manifest.
6. Announce the model selection to the Director: "Phase 4 starting with model: [model_variant]. Manifest version: [version]. Logo on slides: [true/false]. Smoke test will run next."
7. **(Density-floor overhaul) Run the SOP-IMG-01 submit-time preflight (checks 1-8) on every slide body before submitting** (universal-sops/presentation-image-library/SOP-IMG-01 section 7): (1) mode matches assets, a logo/portrait/style-frame slide is I2I with non-empty input_urls, never T2I; (2) every input_urls reference is NAMED in order in the prompt; (3) the logo reference carries "place, do not redraw, recolor, or restyle it"; (4) a style-reference frame carries the verbatim style-reference-only directive; (5) that directive is NOT applied to the logo or a face; (6) every reference URL is a reachable public https <=30 MB (a 404/auth/local-path logo HALTS the wave, never fall back to T2I to "get unblocked", that reintroduces logo mutation); (7) no analysis/"image-to-text" job is POSTed to Kie (there is no such endpoint); (8) download reads `JSON.parse(data.resultJson).resultUrls[0]`, never `.url`. A slide failing any preflight check is not submitted until fixed.

**Outputs:**
- phase4_checkpoint.json updated with model_variant

**Hand to:** SOP 9.5 (smoke test), then SOP 9.2 (wave submission)

**Failure mode:** If MODEL MANIFEST is missing or the model_variant field is ambiguous, halt immediately. Notify the Director: "Cannot proceed without a clear MODEL MANIFEST. Awaiting clarification." Never guess the model.

---

### SOP 9.2 -- KIE Submit and Rate Cap (20 requests / 10 seconds)

**When to run:** After smoke test passes (SOP 9.5). This is the main submission loop.

**Rate cap source.** The cap below (20 new generation requests per 10 seconds, per account, 100+ concurrent tasks allowed, HTTP 429 on excess) is sourced from the live Kie.ai documentation: https://docs.kie.ai/ Section 8 "Rate Limits & Concurrency", verified 2026-06-14. It is not estimated. Re-confirm against the live docs on each MODEL MANIFEST version bump.

**Inputs:**
- working/prompts/slide-NN-prompt.txt (all prompt files)
- working/checkpoints/phase4_checkpoint.json (skip completed slides)
- Client's KIE_API_KEY (from client's env store)
- LOGO_URL and FOUNDER_PORTRAIT_URL (from working/copy/media_library.json)

**Steps:**
1. Build the submission queue: list all slide-NN-prompt.txt files in order. Remove any slides already in phase4_checkpoint.json with status "submitted" or "success". This is the PENDING list.
2. Check the generation budget BEFORE starting: SLIDE_COUNT x 2 x $0.03 = budget ceiling. If the Kie.ai account balance is < budget ceiling, notify the Director BEFORE submitting the first slide.
3. Submit slides in WAVES of 20:
   a. Take the first 20 slides from the PENDING list.
   b. Submit each as a separate API call to Kie.ai with the appropriate model_variant.

      **Request body for image-to-image (the default when LOGO_ON_SLIDES = true):**
      ```json
      {
        "model": "gpt-image-2-image-to-image",
        "input": {
          "prompt": "<the slide's full QC-passed prompt>",
          "input_urls": ["<LOGO_URL>", "<FOUNDER_PORTRAIT_URL if A5>"],
          "aspect_ratio": "16:9",
          "resolution": "2K"
        }
      }
      ```

      **Request body for text-to-image (only when no reference images at all):**
      ```json
      {
        "model": "gpt-image-2-text-to-image",
        "input": {
          "prompt": "<the slide's full QC-passed prompt>",
          "aspect_ratio": "16:9",
          "resolution": "2K"
        }
      }
      ```

   c. Record each submission: `{ "slide_number": N, "task_id": "...", "submitted_at": "...", "status": "submitted" }` in phase4_checkpoint.json.
   d. After submitting all 20 in the wave: sleep for 10 seconds (the documented window) before starting the next wave. Any retries issued during the wave count against the cap, so let the full 10-second window elapse before the next wave.
4. Repeat step 3 until all slides are submitted.
5. Pacing: each wave is 20 submissions followed by a 10-second window, so the submission rate stays at or below the documented 20 requests / 10 seconds (source: https://docs.kie.ai/ Section 8, verified 2026-06-14). Do not collapse the sleep below the window; do not submit more than 20 in a wave.
6. Update the generation budget tracker in phase4_checkpoint.json: `{ "slides_submitted": N, "estimated_cost_so_far": N * 0.03 }`. If estimated_cost_so_far > 1.5 x budget ceiling: warn the Director. If estimated_cost_so_far > 2 x SLIDE_COUNT x $0.03: stop and escalate. Never exceed 2x the slide count in API calls without explicit operator authorization.

**Prompt-must-state-references rule:** Every i2i prompt must state what each reference is. Specifically: "the first reference image is the brand logo, place it per the LOGO element; and on A5, the second reference is the founder, whose likeness drives the portrait." This description must appear in the prompt body so the model understands the role of each URL. If a prompt is missing this statement and the slide uses i2i, add it at the end of the prompt before submitting (log the addition in phase4_checkpoint.json).

**Outputs:**
- phase4_checkpoint.json (all submissions recorded with task_ids)

**Hand to:** SOP 9.3 (polling loop)

**Failure mode:** If any API call returns a rate limit error (HTTP 429): increase the sleep between waves from 10 seconds to 30 seconds and retry. Log the rate limit event in phase4_checkpoint.json. If 3 consecutive rate limit errors occur on the same slide, halt and notify the Director.

---

### SOP 9.3 -- Loop-Guarded Poll and Parallel Download

**When to run:** After all slides are submitted (SOP 9.2 complete). Polls Kie.ai for task completions.

**Inputs:**
- phase4_checkpoint.json (all task_ids with status "submitted")

**Steps:**
1. Wait 5 minutes (300 seconds) after the last submission before the first poll. Kie.ai generation typically takes 2-4 minutes per image -- polling immediately wastes API calls.
2. Begin the poll loop. In each poll iteration:
   a. For each task_id with status "submitted": call the Kie.ai status endpoint: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` with `Authorization: Bearer <CLIENT_KIE_API_KEY>`. Read `data.state` from the response.
   b. For any task with state `success`: parse `data.resultJson` as a JSON string; extract the `resultUrls` array; download `resultUrls[0]` to `working/renders/slide-NN.png` immediately. Update phase4_checkpoint.json: `{ "status": "success", "downloaded_at": "...", "local_path": "working/renders/slide-NN.png" }`.
   c. For any task with state `fail` (or `failed`/`error`/`cancelled`): record `failCode` and `failMsg` from `data.failCode` and `data.failMsg` into phase4_checkpoint.json and flag to the Director.
   d. For tasks still in state `waiting`: skip until next poll.
3. After each poll iteration: check if any "submitted" tasks remain. If none remain: exit the poll loop.
4. Sleep 60 seconds between poll iterations.
5. HARD CAP: 100 poll iterations maximum. If 100 iterations complete and tasks still have "submitted" status: stop the poll loop. Write `poll_cap_reached: true` to phase4_checkpoint.json. Escalate to the Director immediately: "Poll cap of 100 reached. [N] tasks still pending. Kie.ai may be stuck. Director must investigate."
6. After each successful download: verify the file is a valid PNG (check file size > 0 bytes and PNG magic bytes). If the file is empty or corrupted: mark `download_corrupt: true` in the checkpoint and retry the download once.

**State reference (use exactly these state values, never the old incorrect ones):**

| API state value | Meaning | Action |
|---|---|---|
| `waiting` | Task is queued or in progress | Skip; poll again next iteration |
| `success` | Task complete | Parse resultJson -> resultUrls -> download resultUrls[0] |
| `fail` (or `failed`/`error`/`cancelled`) | Terminal failure | Log failCode + failMsg; flag to Director; do NOT poll again for this task |

**Outputs:**
- working/renders/slide-NN.png (all completed images)
- phase4_checkpoint.json (updated with completion status and local paths)

**Hand to:** QC Specialist -- Presentations (Phase 5 image QC)

**Failure mode:** If the poll cap is reached (100 iterations): escalate immediately. Write a clear status to phase4_checkpoint.json showing which slides are complete and which are pending. The Director can re-dispatch this role to resume polling after investigating the Kie.ai issue.

---

### SOP 9.3a -- API CONTRACT (authoritative)

The following table is copied verbatim from Appendix A of the master SOP (universal-sops/CLIENT-WEBINAR-DECK-SOP.md). It is the authoritative API reference for Phase 4. If this section ever conflicts with Section 9.3 above, Appendix A wins and Section 9.3 must be corrected.

> **Source of every hard constant below:** the live Kie.ai documentation at https://docs.kie.ai/ (endpoints + GPT Image 2 reference + Section 8 "Rate Limits & Concurrency"). Verified 2026-06-14. Every external constant here (model ids, character ceiling, reference-image count, rate cap, task states) is sourced, not estimated.

| Item | Value |
|---|---|
| Platform | Kie.ai (the pinned image platform for this SOP) |
| Text-to-image model string | `gpt-image-2-text-to-image` |
| Image-to-image model string | `gpt-image-2-image-to-image` |
| Create task | `POST https://api.kie.ai/api/v1/jobs/createTask` |
| Check task | `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` |
| Auth | `Authorization: Bearer <CLIENT_KIE_API_KEY>` + `Content-Type: application/json` |
| Prompt ceiling | 20,000 characters in `input.prompt` (SOP authoring max: 15,000) |
| Reference images | `input.input_urls`, public https URLs, max 16 |
| Aspect ratios | auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, **16:9**, 9:16, 2:1, 1:2, 3:1, 1:3, 21:9, 9:21 (this SOP pins 16:9) |
| Resolutions | 1K, 2K, 4K (this SOP pins 2K unless intake says otherwise) |
| Create response | `{ "code": 200, "data": { "taskId": "..." } }` |
| Task states | `waiting`, `success`, `fail` (treat fail/failed/error/cancelled as terminal) |
| Success payload | `data.resultJson` is a JSON STRING containing `{"resultUrls": ["https://..."]}`; download `resultUrls[0]` |
| Failure fields | `data.failCode`, `data.failMsg` (log both) |
| Optional | `callBackUrl` webhook on createTask (this SOP polls instead) |
| Cost benchmark | ~3 cents per image at 2K |

Rate cap, wave scheduling, polling cadence, and the 100-poll guard live in Section 9. Every hard external constant here is sourced from the live docs (https://docs.kie.ai/, verified 2026-06-14). On the NEXT MODEL MANIFEST version bump, re-fetch the live docs, re-confirm each constant, and update the verification date; if a constant changed, update the MODEL MANIFEST and this appendix with operator sign-off, refresh the citation, and log the change. Do NOT leave a bare "verify later" note on an un-cited number; that pattern is an AF-SRC auto-fail.

---

### SOP 9.4 -- Truncation and Generation-Budget Discipline

**When to run:** Continuously during Phase 4, checked at the start of each wave (SOP 9.2) and during polling (SOP 9.3).

**Inputs:**
- phase4_checkpoint.json (current cost tracker)
- working/copy/capacity_plan.json (budget estimate from Capacity & Reliability Engineer)

**Steps:**
1. After every 10 successful downloads: calculate actual cost. Formula: submissions_sent x $0.03 = estimated actual cost.
2. Compare actual cost to budget_ceiling from capacity_plan.json.
3. Budget warnings and stops:
   - At 1.0x budget_ceiling: log "Budget at 100% -- proceeding within budget."
   - At 1.5x budget_ceiling: WARN. Send message to Director: "Generation cost at 1.5x budget ceiling ([N] slides generated, estimated $X spent). Continuing but flagging for review."
   - At 2.0x budget_ceiling: STOP. Send message to Director: "Generation cost has reached 2x budget ceiling ($X spent for [SLIDE_COUNT] slides). Halting submission. Awaiting operator authorization to continue."
4. Record all budget events in phase4_checkpoint.json: `{ "budget_checks": [{"at_slide": N, "estimated_cost": X, "ceiling": Y, "action": "continue|warn|stop"}] }`.
5. Truncation check: if the prompt file for a slide exceeds 15,000 characters (this should have been caught by Phase 3 QC, but check again before submission), truncate the prompt at the 15,000-character boundary by removing content from the end of the AVOID block. Log the truncation: `{ "slide_number": N, "original_chars": N, "truncated_to": 15000, "truncation_applied": true }`. Notify the Slide Image Creator.

**Outputs:**
- phase4_checkpoint.json (budget events and truncation log)

**Hand to:** Director (budget warnings and stops), Slide Image Creator (truncation notifications)

**Failure mode:** If the budget ceiling calculation is impossible (capacity_plan.json missing or has no budget_ceiling field), use the default formula: SLIDE_COUNT x 2 x $0.03. Never skip the budget check.

---

### SOP 9.5 -- API Smoke Test

**When to run:** Before wave 1 of any run, immediately after model variant is confirmed (SOP 9.1). This test runs once per Phase 4 invocation, never skipped.

**Purpose:** Verify the client's KIE_API_KEY is live, the createTask endpoint is reachable, and resultUrls parsing works end-to-end. A failed smoke test costs ~3 cents and stops Phase 4 before 75 real slides burn.

**Inputs:**
- Client's KIE_API_KEY (from client's env store)
- working/checkpoints/phase4_checkpoint.json (record smoke test outcome here)

**Steps:**
1. Submit ONE cheap test task using the client's key:
   - Model: `gpt-image-2-text-to-image` (use t2i for the smoke test regardless of run variant -- it is cheaper and tests the key and endpoint equally well).
   - Prompt: `"test slide, white background, the word TEST centered"`
   - Resolution: `1K` (cheapest; ~3 cents).
   - Aspect ratio: `16:9`.
   - POST to `https://api.kie.ai/api/v1/jobs/createTask` with `Authorization: Bearer <CLIENT_KIE_API_KEY>`.

2. Confirm the response contains `{ "code": 200, "data": { "taskId": "..." } }`. If not, HALT Phase 4 immediately and notify the Director with the response body.

3. Poll the smoke task to terminal state (same poll logic: 5-minute initial wait, then every 60 seconds, maximum 20 polls for the smoke test).

4. On state `success`:
   - Parse `data.resultJson` as a JSON string.
   - Extract the `resultUrls` array.
   - Confirm `resultUrls[0]` is a non-empty https URL.
   - Attempt to download it (HEAD or GET the URL; confirm HTTP 200 and non-zero content).
   - Record in phase4_checkpoint.json: `{ "smoke_test": "passed", "smoke_task_id": "...", "smoke_at": "..." }`.
   - Announce to Director: "Smoke test passed. KIE key live, resultUrls parsing confirmed. Proceeding to wave 1."

5. On state `fail` (or `failed`/`error`/`cancelled`):
   - Record `failCode` and `failMsg` from the response.
   - Write to phase4_checkpoint.json: `{ "smoke_test": "failed", "failCode": "...", "failMsg": "...", "smoke_at": "..." }`.
   - HALT Phase 4. Notify Director: "Smoke test FAILED. failCode: [X], failMsg: [Y]. Phase 4 is blocked. Investigate KIE key and account balance before retrying."
   - Do NOT submit any real slides until the smoke test passes on a retry.

6. On poll cap (20 polls with no terminal state):
   - Record `{ "smoke_test": "timeout", "smoke_task_id": "...", "smoke_at": "..." }`.
   - HALT Phase 4. Notify Director: "Smoke test timed out after 20 polls. Kie.ai may be degraded. Investigate before starting the run."

**Outputs:**
- phase4_checkpoint.json (smoke_test field: "passed" | "failed" | "timeout")

**Hand to:** SOP 9.2 (wave submission) on pass only. Director on fail or timeout.

**Failure mode:** A smoke test that cannot complete (network error, auth error, timeout) always halts the run. There is no bypass. The ~3 cent cost is mandatory insurance against burning 75 slides on a broken key or a degraded platform.

---

