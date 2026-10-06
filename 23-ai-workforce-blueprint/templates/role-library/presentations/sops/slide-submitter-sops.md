# SOPs Mirror -- Slide Submitter

**Source:** presentations/slide-submitter.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Model Pin, Mode Rule, and Submit-Time Preflight

**When to run:** At the very start of Phase 4, before the render command.

**Inputs:**
- `presentation_job/model_catalog.json` (aliases `image.t2i`, `image.i2i`)
- `working/checkpoints/model_manifest.json` (the operator-confirmed echo from the Director)
- `working/copy/intake.json` (LOGO_ON_SLIDES, `brand.logo_image_path`) and `working/copy/media_library.json`

**Steps:**
1. Read the two image aliases from `presentation_job/model_catalog.json`. They must equal the models named in the operator-confirmed `model_manifest.json`. A mismatch is not yours to resolve: halt and tell the Director "model_manifest.json and model_catalog.json disagree." Never guess the model.
2. Mode rule (what the canonical command does): the canonical entry has NO `--logo` option (passing one exits with "unknown argument"). The logo reaches the renderer only through `working/copy/intake.json` `brand.logo_image_path`, which must be a LOCAL PNG file (absolute, or relative to the run directory). With a local logo the render stays text-to-image (alias `image.t2i`) and the renderer places that exact file on every slide at assembly (SOP-IMG-05 Rule A mechanism 2). With no logo configured, every slide is rendered text-to-image and no logo is placed. The URL image-to-image mechanism (SOP-IMG-05 Rule A mechanism 1) is not reachable through the canonical command today; it needs `--logo` to be forwarded by the entry and runner (lane D). The batch renderer sends no reference image. A reference image (a founder portrait on an A5 slide, a style frame) is not supported by the batch path: flag it to the Director, do not hand-submit.
3. If LOGO_ON_SLIDES = true, `brand.logo_image_path` must name an existing local PNG before the render starts (a missing file or a URL there makes the renderer exit 2). If the client's logo exists only as a hosted LOGO_URL, it is downloaded once to a local PNG in the run directory (for example `working/copy/logo.png`) and `brand.logo_image_path` is pointed at it by the intake owner; you do not edit `intake.json` yourself. If that cannot be done, escalate to the Director before the render. Rendering a logo deck with no logo configured ships slides with no logo.
4. Run the SOP-IMG-01 section 7 preflight on the deck: (1) mode matches assets; (2) the prompts name no reference image on the canonical command (a local logo is placed at assembly), and keep the top-right logo zone free of type and imagery; (3) a style-reference frame, if any, carries the verbatim style-reference-only directive and the logo does not; (4) the logo file at `brand.logo_image_path` exists and is a PNG, which are the two things the renderer checks (a missing, non-PNG, or URL-valued path HALTS the render; a local path is valid here because the renderer places the file at assembly, and it is invalid only as an image-to-image `input_urls` value, which this command never sends); (5) no analysis or "image-to-text" job is ever sent to KIE (there is no such endpoint). A deck failing a check is not rendered until fixed.
5. Record the pin and mode in `working/checkpoints/phase4_checkpoint.json`: `{ "model_t2i": "...", "model_i2i": "...", "logo_mode": "t2i", "logo_file": "<path>|none", "selected_at": "..." }`, and tell the Director: "Phase 4 starting with models: [t2i/i2i]. Logo: [local file placed at assembly / none]."

**Outputs:**
- `phase4_checkpoint.json` updated with the pin and mode

**Hand to:** SOP 9.2 (dispatch)

**Failure mode:** If the catalog or the manifest is missing or ambiguous, halt immediately and notify the Director: "Cannot proceed without a clear model pin." Never guess the model.

---

### SOP 9.2 -- Dispatch the One Render Command

**When to run:** After SOP 9.1 passes.

**Inputs:** the run directory, `slides.json`, the output path, and the client's own KIE key in the client's env stores.

**Steps:**
1. Run exactly one command:
   ```bash
   bash <SCRIPTS_DIR>/presentation-canonical-entry.sh \
       --run-dir <RUN_DIR> --slides slides.json --out <ARTIFACT_DIR>/presentation.pptx
   ```
   There is no `--logo` option; the logo comes from `intake.json` `brand.logo_image_path` (SOP 9.1 step 3). The entry runs the deps, bypass-scan and version-pin gates; the runner runs its Phase-0 preflight (OCR engine present, key authenticates, live credit balance via `GET /api/v1/chat/credit` against the script's estimated floor, abort `AF-KIE-AUTH` or `AF-KIE-BALANCE`, exit 4); then `build_deck.py` renders.
2. You do not sleep, wave, throttle, or retry on your own. The script submits every slide once 0.6 seconds apart, the governor paces the `kie` provider, a submit that gets HTTP 429 sleeps 20 seconds and retries (at most 15 times in a row, then that slide fails), and the poll cadence is the script's.
3. Never run `build_deck.py` or `run_signature_deck.py` directly to route around the entry gates, never run a per-deck `working/*.py` driver, and never start a smoke-test createTask by hand: a createTask outside the canonical path is `AF-CANONICAL-RENDER-BYPASS`. The built-in auth proof and credit check are the smoke test.
4. Credit and price questions are answered by Skill 74, read-only and from the Skill 74 folder: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (rule 7). Never copy the adapter into the run directory.

**Outputs:** the run's console output and JSON summary, plus the receipts of SOP 9.3.

**Hand to:** SOP 9.3 (read the result)

**Failure mode:** If the command reports a missing key, a placeholder key, or a 401 or 403, stop. Do not retry (a 401 or 403 is permanent). Notify the Director to check the client's own KIE key in the client's env stores; never use the operator's key.

---

### SOP 9.3 -- Read the Receipts and Route the Exit Code

**When to run:** When the render command returns.

**What the renderer did (so you can read it):** After the last submit it polls every pending task, one pass every 10 seconds, and downloads each slide the moment its own task succeeds. A task still unfinished 900 seconds after polling began (`BUILD_DECK_POLL_MAX_SECONDS`, `BATCH_MAX_POLL_SECONDS`) is a terminal failure for that slide, never re-submitted blindly and never a silent hang. Each download is an authenticated GET (the client's key as the Bearer header plus a browser User-Agent), then verified as a real PNG, 16:9 at 2K, with an OCR readback of the baked text against the approved copy.

**Receipts to read:**
- `working/checkpoints/pending_tasks.json`: per slide, the KIE task id written before polling, replaced by the verified PNG's sha256 and `completed: true` once downloaded. A re-run reuses only slides recorded complete here, so a crash never re-bills a finished slide; a slide whose task was still in flight is submitted again.
- `working/renders/slide-NN.ocr.json`: the OCR readback record per slide.
- `working/checkpoints/process_manifest.json`: the render record (model used, task ids).
- The JSON summary: `{ "slidesRendered": N, "kieTaskIds": [...], "outputPath": "...", "failures": [] }`.

**Exit codes:**

| Exit | Meaning | Action |
|---|---|---|
| 0 | Every slide rendered and the `.pptx` was written | Confirm `slidesRendered` equals the slide count and every slide has a task id; notify the Director |
| 1 | One or more slides failed (NO `.pptx`), or assembly failed | Read `failures` (terminal KIE state with `failCode` and `failMsg`, poll cap, bad PNG, OCR mismatch). Fix the Layer-A input if it was a content problem and re-run the SAME command; otherwise report. Never substitute an image. Hand failCode events to the Healer |
| 2 | Fatal config error (no or placeholder key, bad `slides.json`, `python-pptx` missing) | Fix the config; notify the Director |
| 3 | Process preflight failed: a required upstream artifact is missing or thin | Re-run `run_signature_deck.py --next` to see what is owed |
| 4 | Phase-0 abort: OCR engine missing, key did not authenticate, or credit balance below the floor | Report to the Director; top up credits or fix the key; do NOT render anyway |
| 5 | Guard or postflight block (hand-rolled renderer in the run directory, or the deliverable bundle incomplete) | Remove the offender or finish the bundle; never self-approve a skip |

**State reference (use exactly these KIE state values):** `waiting` (and `queuing`, `generating`) = still in flight; `success` = done, parse `data.resultJson` (a JSON STRING) then `resultUrls[0]`; `fail` (also `failed`, `error`, `cancelled`) = terminal failure, log `failCode` and `failMsg`.

**Outputs:** the verified `working/renders/slide-NN.png` set and the receipts above.

**Hand to:** QC Specialist -- Presentations (Phase 5 image QC, `P-IMAGE-QC`)

**Failure mode:** If the run exits 1 for the same slide on a second run, escalate to the Director with the `failCode`, the `failMsg`, and the task id from `pending_tasks.json`.

---

### SOP 9.3a -- API CONTRACT (authoritative)

This table is the API reference for Phase 4 in this role. It follows AGENTS.md N43 and `07-kie-setup/references/kie-common-rules.md`, which win over it. If this section ever conflicts with Section 9.3 above, this table wins and Section 9.3 must be corrected.

> **Source of every hard constant below:** `07-kie-setup/references/kie-common-rules.md` (live-verified 2026-10-05 against https://docs.kie.ai/ and live endpoint probes), and the shipped code (`build_deck.py`, `providers.yaml`, `model_catalog.json`).

| Item | Value |
|---|---|
| Platform | Kie.ai (the pinned image platform for this SOP) |
| Models | The `image.t2i` and `image.i2i` aliases in `presentation_job/model_catalog.json` (today `gpt-image-2-5-sunburst-text-to-image` and `gpt-image-2-5-sunburst-image-to-image`); the catalog wins over any id quoted in a document |
| Create task | `POST https://api.kie.ai/api/v1/jobs/createTask` |
| Check task | `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` |
| Balance | `GET https://api.kie.ai/api/v1/chat/credit` |
| Auth | `Authorization: Bearer <CLIENT_KIE_API_KEY>` + `Content-Type: application/json` (a header named `apikey` returns 401); always read the body `code`, HTTP 200 can still carry 401, 402, 404, 422, 429, 433 or 455 |
| Prompt length | The model's prompt maximum (20,000 characters for the current pin); authoring size follows rule 12 (read with `prompt-budget`), and the renderer gate today is 9,000 to 18,000 |
| Reference images | `input.input_urls`, public https URLs. `build_deck.py` sends none on the canonical command (a local logo is placed at assembly); it sends exactly one, the logo URL, only when run directly with `--logo <https URL>` (SOP-IMG-05 mechanism 1, not reachable through the canonical command today) |
| Aspect ratio and resolution | The renderer pins `16:9` and `2K` |
| Rate limits | createTask 20 per 10 seconds per account; recordInfo 10 per second per taskId (rule 3) |
| Create response | `{ "code": 200, "data": { "taskId": "..." } }` |
| Task states | `waiting`, `success`, `fail` (treat fail, failed, error, cancelled as terminal) |
| Success payload | `data.resultJson` is a JSON STRING containing `{"resultUrls": ["https://..."]}`; download `resultUrls[0]` |
| Failure fields | `data.failCode`, `data.failMsg` (log both) |
| Retention | Download immediately; result URLs may expire within 24 hours (rule 8) |
| Price | `kie_live_adapter.py price` is the authority (rule 7); the catalog `unit_costs` is a dated snapshot |

---

### SOP 9.4 -- Generation-Budget Discipline

**When to run:** Before the render and after every run.

**Inputs:**
- `working/copy/capacity_plan.json` (budget estimate from the Capacity & Reliability Engineer)
- `working/checkpoints/pending_tasks.json` (task ids actually created)

**Steps:**
1. Before the render: budget ceiling = SLIDE_COUNT x price per image (from `kie_live_adapter.py price`). If the live balance is below ceiling x 1.30 (the credit preflight of rule 6), tell the Director before dispatching; the script's own Phase-0 balance check still applies and aborts with exit 4.
2. After each run: count the task ids in `pending_tasks.json`. Each id is a billed submission. If the total created exceeds 2 x SLIDE_COUNT, stop and escalate to the Director for operator authorization before any further re-run.
3. Length check: the Slide Image Creator and Prompt QC own prompt sizing (rule 12). Never truncate a prompt to fit; return it with the measured length and the model maximum.

**Outputs:** budget notes in `phase4_checkpoint.json`.

**Hand to:** Director (budget warnings and stops), Slide Image Creator (length returns)

**Failure mode:** If `capacity_plan.json` is missing or has no budget ceiling, compute SLIDE_COUNT x price per image from `kie_live_adapter.py price` and continue. Never skip the budget check.

---
