# SOP-IMG-01 - KIE.AI Call Mechanics (the three call modes, made exact)

**Cluster:** Image-Gen Mechanics + Design-Library (skill 45) Integration
**Status:** DRAFT for overhaul - extends the Presentations pipeline; does not replace it
**Owner role (Presentations):** Slide Submitter (primary), Slide Image Creator (secondary, for which-mode declaration)
**Master authority extended:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` §9 (Phase 4) and Appendix A; `45-design-intelligence-library/library/_system/MODEL-SPECS.md` (the Design Intelligence Library reference for endpoint behavior; it is NOT the authority for the model ids a Presentations deck uses)
**Model authority:** the model ids a Presentations deck uses are named in exactly one file, `presentation_job/model_catalog.json` (aliases `image.t2i` and `image.i2i`, beside `build_deck.py`). Limits and rates shared by every KIE skill are in `07-kie-setup/references/kie-common-rules.md`.
**Library-version pin:** `presentation_job/model_catalog.json` (model ids); MODEL-SPECS v1.2

---

## 0. WHY THIS SOP EXISTS (the defect it kills)

Concern 20 (verbatim): "Kie.ai text-to-image vs image-to-image vs image-to-text/JSON use DIFFERENT curl / JSON / HTTP-POST structures. Logo-on-every-slide = image-to-image. The SOP must teach the correct call per mode."

The reference-case forensic (Dimension F) proved the consequence of guessing the mode: the logomark mutated into at least four different marks across the deck (ringed leaf, bare leaf, monogram, mountain peak) because the slides were generated text-to-image per slide instead of composited image-to-image with one locked logo asset passed as a reference. An agent that does not know the exact call structure for each mode WILL default to text-to-image and WILL reinvent the logo.

This SOP is a precise reference an agent follows without guessing. It does not introduce a new model. The model catalog (`presentation_job/model_catalog.json`, aliases `image.i2i` and `image.t2i`) currently names `gpt-image-2-5-sunburst-image-to-image` / `gpt-image-2-5-sunburst-text-to-image`; the ids written in this SOP are illustrations of those current values, and if they ever differ the catalog wins. This SOP makes the choice between the two modes, and the body for each, mechanical. The model ids are a department pin: the pin outranks Skill 74 and the fleet `latest-family` default (rule 1 and rule 13 of `07-kie-setup/references/kie-common-rules.md`). When `kie_live_adapter.py latest-family --family gpt-image` reports a newer GPT Image generation, the operator bumps the catalog; the deck never switches model silently.

This is a build-mechanics reference. NONE of its content is ever printed on a slide. (Cross-ref the Audience-Facing battery in the slide-craft cluster.)

---

## 1. PURPOSE

Give every agent the EXACT call structure (HTTP verb, endpoint, headers, JSON body, polling, result parsing) for each of the three Kie.ai interaction modes a Presentations deck uses, plus a single decision rule for picking the mode per slide. Make the wrong mode a detectable, auto-failable condition rather than a silent default.

---

## 1A. THE DETERMINISTIC RENDER PATH IS MANDATORY (no self-generate, no native image tool)

Every Kie.ai call described in this SOP is made by a SHIPPED SCRIPT, never by an agent typing an HTTP call from memory. There are exactly two renderers, both in `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/` (installed into the client's Presentations scripts directory on a materialized box):

- **`build_deck.py`** - the single-command deterministic path. The builder writes `slides.json`, and the Slide Image Creator authors one RICH prompt file per slide (`working/prompts/slide-NN.txt` or `slide-NN-prompt.txt`, sized per rule 12 of `07-kie-setup/references/kie-common-rules.md`). The script does NOT compose prompts. It loads each authored prompt VERBATIM, gates it (character band, quality floor, no hard-coded demographic default), appends the mandatory English/Latin-only pin only when the authored prompt does not already carry it, and submits it with the text-to-image model, or with the image-to-image model and the logo URL in `input_urls` when a logo URL is supplied (both models resolve from the catalog aliases `image.t2i` and `image.i2i`). It then polls, downloads + verifies each PNG, and assembles the `.pptx`. A slide with no authored prompt file fails loudly; the script never falls back to a thin composed prompt. No model decides wording at runtime.
- **`kie_generate.py`** - the image-to-image / text-to-image submit+poll+download helper for slides that must pass references (Mode B below). It submits the `prompt` it is given and never composes one. A second, older copy of this helper lives at `23-ai-workforce-blueprint/templates/presentation-render/kie_generate.py`; only Skill 06 (GHL media) runs it, and it is not a Presentations renderer (its header says how it differs).

**The mandated flow is:** the builder writes `slides.json` → runs `build_deck.py` → KIE.ai (createTask → recordInfo → `resultUrls[0]`) is the ONLY render call → register the `.pptx` the script produced. **FORBIDDEN, each an auto-fail (AF-I14 / AF-RENDERER / AF-CANONICAL-RENDER-BYPASS / AF-LOCAL-CANVAS):** generating any image with a native/built-in tool (`image_generate`, `openai`, etc.); writing an inline hand-typed KIE.ai HTTP call instead of the script; the dead endpoint `/api/v1/image/gpt-image`; hand-editing PNGs or substituting stock/placeholder images; **fabricating any slide canvas locally with Pillow/PIL `Image.new` / `ImageDraw` (a flat cream or color typography card) or a PowerPoint-rendered card**; running any per-deck/hand-rolled renderer or assembler in `working/*.py` instead of the canonical `build_deck.py` / `run_signature_deck.py` path. A non-zero exit means the deck is NOT built - never fake a deliverable.

**Skill 74 is never part of a deck run.** `74-kie-live-adapter` is mechanics for the other KIE skills; none of its files (`kie_live_adapter.py`, `kie-model-registry.json`, its shell scripts, its receipts) is ever copied into, imported from, or run inside a deck run directory. The canonical render guard blocks any `*.py` in the run directory that mentions `createTask`, `recordInfo` or `api.kie.ai`, and a copy of the adapter does (`AF-CANONICAL-RENDER-BYPASS`). Use the adapter only from the Skill 74 folder, and only for read-only checks such as `prompt-budget`, `price` and `latest-family`.

**Pure-typography hook slides are NOT an exception to any of the above.** A PURE_TYPE_HOOK slide (a hook line set large over a cream surface or low-opacity wash, per SOP-DESIGN-02) is rendered by kie.ai GPT Image 2.5 Sunburst like every other slide - Mode A (text-to-image) when no logo is composited, Mode B (image-to-image) when the locked logo is composited. kie.ai bakes the cream/wash AND the verbatim hook type into ONE composed image. "Pure typography" describes the visual (type carries the slide), never the render path. Rendering a hook slide locally because it "has no photo" is the exact `AF-LOCAL-CANVAS` defect; every hook slide carries a real kie.ai `taskId` and a PNG above the 51,200-byte kie-bake floor. The only Pillow/PIL step permitted anywhere in the pipeline is the LOCKED LOGO image composite (SOP-IMG-05) - never a slide canvas, never any text.

**MANDATORY ENGLISH / LATIN-ONLY PIN - every image prompt carries this verbatim (every slide, every mode):**

> All text rendered in the image MUST be in English, Latin alphabet ONLY. NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled correctly, letter-for-letter. No garbled, misspelled, or invented text.

`build_deck.py` appends this pin to any prompt that does not already carry it. Any prompt authored by hand for a Mode A or Mode B call below (or at the Phase 2/3 prompt-writing stage) MUST include this pin verbatim. A prompt missing the pin, or a render carrying CJK / non-Latin glyphs or garbled/misspelled text, is an auto-fail (see check 10 in Section 7).

---

## 2. THE THREE MODES (what each is FOR)

| Mode | Kie.ai endpoint family | What it does | When the Presentations pipeline uses it |
|---|---|---|---|
| **A. Text-to-Image (T2I)** | model `gpt-image-2-5-sunburst-text-to-image` | Generates a slide image from words ONLY. No reference images. The model invents every pixel, including any logo or face described in words. | ONLY when the deck has NO logo asset AND no founder portrait for this slide (`LOGO_ON_SLIDES = false` AND archetype is not A5). Rare. |
| **B. Image-to-Image (I2I)** | model `gpt-image-2-5-sunburst-image-to-image` | Generates a slide image from words PLUS up to 16 reference image URLs passed in `input_urls`. The references anchor real assets (the locked logo, the founder's real face, an optional style-reference frame) so they are composited rather than reinvented. | THE DEFAULT for every slide that carries the logo (i.e. almost every slide), and for every A5 founder-portrait slide. |
| **C. Image-to-Text / JSON (analysis)** | NOT a Kie.ai generation endpoint | "Read this image and return structured findings" (e.g. analyze a reference deck into named style families; QC-read a rendered slide for defects). | Done by the multimodal LLM agent READING the image directly. There is no Kie.ai HTTP call for this. See §6. |

**The hard mode-selection rule (this is the gate):**

> **Scope of the logo rules in this SOP:** they describe URL image-to-image mode (the standalone `kie_generate.py` flow and a direct `build_deck.py --logo <https URL>` run). On the canonical command (`presentation-canonical-entry.sh`, no `--logo`) the logo is a local PNG from `intake.json` `brand.logo_image_path` placed by `assemble_pptx`; the render is text-to-image (Mode A), the prompt draws no logo and keeps the top-right corner clear (SOP-IMG-05 Rule A, AF-P15), and Mode A on that deck is correct, not a defect.
>
> If a URL logo asset is in use (`LOGO_ON_SLIDES = true`, a `LOGO_URL` is on file and passed as a reference) OR the slide is archetype A5 (founder portrait) OR any reference frame is being passed for style → the call MUST be Mode B (I2I) with the reference URL(s) in `input_urls`. A T2I call (Mode A) on any such slide is an AUTO-FAIL.

There is no "image-to-text/JSON" Kie.ai endpoint to call. An agent that tries to POST an "extract JSON" job to Kie.ai is wrong; analysis is the agent's own multimodal read (§6).

---

## 2A. MODEL AND ASPECT-RATIO ROUTING (RULING 6 — TWO-MODEL SYSTEM, operator ruling 2026-09-09)

As of 2026-09-09 this is a TWO-MODEL system, not a straight swap from GPT-Image-2 to GPT Image 2.5 Sunburst. Every Presentations Kie call routes to exactly ONE of the two models below, selected by the requested aspect ratio. Get the routing wrong and either the render fails validation or the wrong prompt-char-cap gets applied.

**DEFAULT — GPT Image 2.5 Sunburst (`gpt-image-2-5-sunburst-*`):** use for every ratio EXCEPT the three legacy ratios below.
- Mode A: `gpt-image-2-5-sunburst-text-to-image`
- Mode B: `gpt-image-2-5-sunburst-image-to-image`

**2.5 supported aspect ratios — EXACTLY these 13, nothing else:**
`auto, 1:1, 3:2, 2:3, 16:9, 9:16, 4:3, 3:4, 21:9, 27:16, 16:27, 9:8, 8:9`
- **1K-ONLY (2K and 4K REJECTED for these four):** `27:16`, `16:27`, `9:8`, `8:9`.
- 2K and 4K are available for every other ratio in the list.

**2.5 prompt cap: 20,000 chars** (`prompt_max_chars: 20000`, DOCS marker 2026-09-09). This cap applies to the 2.5 model ONLY — see the legacy-route cap below, which is a different number.

**APPROVED SUBSTITUTIONS — these four route to 2.5 under a substitute ratio (operator-blessed):**

| Requested | Renders on 2.5 as |
|---|---|
| `5:4` | `4:3` |
| `4:5` | `3:4` |
| `2:1` | `16:9` |
| `1:2` | `9:16` |

**LEGACY ROUTE — MANDATORY for these three ratios, no exceptions:**

| Ratio | Model (Mode A / Mode B) |
|---|---|
| `3:1` | `gpt-image-2-text-to-image` / `gpt-image-2-image-to-image` |
| `1:3` | `gpt-image-2-text-to-image` / `gpt-image-2-image-to-image` |
| `9:21` | `gpt-image-2-text-to-image` / `gpt-image-2-image-to-image` |

The operator rated 2.5's rendering of these three too weak to substitute (candidates 21:9, 9:16, and 16:27 were each considered and rejected). Do NOT send `3:1`, `1:3`, or `9:21` to the 2.5 model. Do NOT silently pick a different ratio for these three — each keeps its own requested ratio and routes to the legacy model as-is, via the SAME canonical call lifecycle (§3) and the SAME canonical renderer.

**Legacy-route prompt cap: 25,000 chars — OWNER_CONFIRMED 2026-08-27.** That confirmation was made against `gpt-image-2` and stays in force for the legacy route only. Never apply the 20,000 figure to a legacy-route call, and never apply 25,000 to a 2.5 call.

**A ratio in NEITHER list above** (not one of the 13 allowed-on-2.5 ratios, not one of the three legacy ratios) is still a HARD-FAIL — reject outright, no warn-only, no silent substitution.

**UNCHANGED on BOTH routes (2.5 and legacy):** the endpoints (`POST /api/v1/jobs/createTask`, `GET /api/v1/jobs/recordInfo`), the `Authorization: Bearer $KIE_API_KEY` header, the response envelope (`code`/`msg`/`data.taskId`; state `waiting`|`success`|`fail`; `resultJson.resultUrls[]`), `callBackUrl` semantics, and the I2I reference field `input_urls` (≤30 MB/file, `image/jpeg|png|webp|jpg`) — never `image_input` (that field belongs to Nano Banana 2; see §5 rule 2).

The curl and JSON examples in §4 and §5 below show the DEFAULT (2.5) route. A legacy-route call has the identical shape — same endpoints, same headers, same envelope, same `input_urls` mechanics — with only the `model` string swapped to the legacy id above and the 25,000-char cap applied instead of 20,000.

---

## 3. SHARED CALL LIFECYCLE (identical for Mode A and Mode B)

Every generation call, regardless of mode, follows this lifecycle. The shipped scripts perform it (`build_deck.py` and `kie_generate.py`, in the Presentations department's `scripts` directory); an agent never types these calls by hand. This section describes what the scripts do today, so the document and the code agree. The limits and rates shared by every KIE skill (createTask rate, recordInfo rate, prompt caps, credit endpoint) are kept in one place, `07-kie-setup/references/kie-common-rules.md`; this SOP does not restate them as rules.

1. **Submit (async):** `POST https://api.kie.ai/api/v1/jobs/createTask`
   - Headers: `Authorization: Bearer $KIE_API_KEY` (the CLIENT's own key - never a shared key), `Content-Type: application/json`
   - Body: see §4 (Mode A) or §5 (Mode B).
2. **Capture the task id:** on `{ "code": 200, "data": { "taskId": "..." } }` the renderer records the id immediately, before it polls. `build_deck.py` writes it to `working/checkpoints/pending_tasks.json` in the run directory (and replaces the entry with the verified PNG's sha256 once the slide is downloaded). `kie_generate.py` writes it, through `kie_tasks.py`, to `<renders_dir>/.kie-tasks/kie_tasks.json`. After a restart, `kie_generate.py` (through `kie_tasks.py`) re-polls a known id instead of paying for a second createTask. `build_deck.py` batch reuses only slides already downloaded, verified and recorded complete in `pending_tasks.json`; a slide whose task was still in flight is submitted again.
3. **Submit pacing (the createTask rate limit is in kie-common-rules.md):**
   - `build_deck.py` (the batch path every deck uses) submits every slide once, 0.6 seconds apart, so at most 17 createTask calls land in any 10 second window. Each createTask also takes a slot from the governor (`presentation_job/governor.py`, per-provider plan in `presentation_job/providers.yaml`, `kie` row: 1.33 per second, at most 13 per rolling 10 seconds, 100 tasks in flight). Whichever is slower sets the pace, and both stay inside the KIE limit. On HTTP 429 it sleeps 20 seconds and retries the same slide, at most 15 times in a row, then that slide fails.
   - `kie_generate.py` submits through `kie_tasks.py`, which allows at most 20 createTask calls per rolling 10 seconds (and also takes governor slots when the governor module is importable). Polling does not count toward the createTask rate.
4. **Poll:** `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` (same Bearer). Read `data.state`: `success` is done; `fail` (also `failed`, `error`, `cancelled`) is a terminal failure, and the renderer logs `data.failCode` + `data.failMsg`; any other state (`waiting`, `queuing`, `generating`, and so on) means still in flight. Cadence by script:
   - `build_deck.py` batch path: there is NO initial wait. After the last submit it polls every pending task, one pass every 10 seconds, and downloads each slide the moment its own task succeeds, so a fast slide never waits for a slow one. A 429 on a poll just retries that task on the next pass.
   - `build_deck.py` single-task path (`poll_task`, used for sample renders): sleeps 10 seconds between polls for the first 120 seconds, 20 seconds for the next 180 seconds, then 40 seconds.
   - `kie_generate.py`: NO initial wait. `kie_tasks.py` polls every pending task round-robin every 60 seconds (environment variable `KIE_ROUND_POLL_S`) and downloads and verifies each task the moment it succeeds.
   - The older Skill 06 copy of `kie_generate.py` (`templates/presentation-render/`) still waits 5 minutes after the last submit, then polls one task at a time every 60 seconds for up to 100 passes. That wait-then-poll pattern belongs to that copy only; it is not how a Presentations deck renders.
5. **Download:** on `success`, `data.resultJson` is a JSON STRING; parse it -> `resultUrls` (an ARRAY) -> download `resultUrls[0]` to the renders directory as `slide-NN.png`. It is `resultUrls`, NOT `.url` - the old runbook had this wrong. Each renderer performs the download itself, authenticated with the client's own key as the Bearer header plus a browser User-Agent (an unauthenticated GET of the KIE result URL returns 403), and checks it is a real PNG.
6. **Poll cap (a time limit, not a pass count):** `build_deck.py` gives up on a task that is still not finished 900 seconds (15 minutes) after polling began (`BUILD_DECK_POLL_MAX_SECONDS`, `BATCH_MAX_POLL_SECONDS`). `kie_generate.py` gives up at 6,000 seconds (`KIE_DEADLINE_S`, which is 100 polls of 60 seconds). At the cap the renderer records a terminal timeout for the stuck task, does NOT re-submit it, and the run reports the stuck task ids for escalation. Never loop forever.

The ONLY thing that differs between Mode A and Mode B is the `model` string and the presence/absence of `input_urls`. Everything else above is identical.

---

## 4. MODE A - TEXT-TO-IMAGE (no references)

**Use only when:** `LOGO_ON_SLIDES = false` AND the slide is not A5 AND no style-reference frame is passed. (Rare for a branded deck.)

**curl:**
```bash
curl -s -X POST 'https://api.kie.ai/api/v1/jobs/createTask' \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-image-2-5-sunburst-text-to-image",
    "input": {
      "prompt": "<the slide-NN QC-passed prompt, up to 20000 chars>",
      "aspect_ratio": "16:9",
      "resolution": "2K"
    }
  }'
```

**JSON body (the shape):**
```json
{
  "model": "gpt-image-2-5-sunburst-text-to-image",
  "input": {
    "prompt": "<full QC-passed prompt>",
    "aspect_ratio": "16:9",
    "resolution": "2K"
  }
}
```

**Rules for Mode A:**
- There is NO `input_urls` field. Adding one to a T2I body is malformed - the reference would be ignored, and the agent would falsely believe the logo was composited. If `input_urls` is needed, the call is Mode B, not Mode A.
- Prompt length: the API ceiling for the GPT Image 2.5 Sunburst family is 20,000 characters (`07-kie-setup/references/kie-common-rules.md`). How much of that ceiling a descriptive prompt should use (target, floor, ceiling) is set by rule 12 of that file. This SOP does not restate it. Measure it with `python3 74-kie-live-adapter/scripts/kie_live_adapter.py prompt-budget --model <the image.t2i id> --check --prompt-file <slide-NN.txt>` (run from the Skill 74 folder, never from a deck run directory). `build_deck.py` and `prompt_gate.py` currently enforce a 9,000 to 18,000 character band, so until that gate is migrated to rule 12 write 16,000 to 18,000 characters for the current 20,000-character pin: that window passes both the rule 12 floor (16,000) and the renderer ceiling (18,000).
- Everything the model must draw is in `prompt`. A logo described in words here WILL be reinvented (the reference-case logo-mutation defect). That is exactly why a deck with a logo never uses Mode A.
- The `prompt` MUST carry the mandatory English/Latin-only pin verbatim (Section 1A): *"All text rendered in the image MUST be in English, Latin alphabet ONLY. NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled correctly, letter-for-letter. No garbled, misspelled, or invented text."* (When the deterministic `build_deck.py` path is used, the script appends this for you if the authored prompt lacks it.)

---

## 5. MODE B - IMAGE-TO-IMAGE (the default; logo + portrait + optional style frame)

**Use when (the default for nearly every slide):** a `LOGO_URL` exists, OR the slide is A5 (founder portrait), OR a style-reference frame is being passed. This is how "logo on every slide" is achieved.

**curl (logo on a content slide):**
```bash
curl -s -X POST 'https://api.kie.ai/api/v1/jobs/createTask' \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-image-2-5-sunburst-image-to-image",
    "input": {
      "prompt": "<the slide-NN QC-passed prompt>. The first reference image is the company logo: place it exactly as specified, do not redraw, recolor, or restyle it.",
      "input_urls": ["<LOGO_URL>"],
      "aspect_ratio": "16:9",
      "resolution": "2K"
    }
  }'
```

**curl (A5 founder portrait - logo + face):**
```bash
curl -s -X POST 'https://api.kie.ai/api/v1/jobs/createTask' \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-image-2-5-sunburst-image-to-image",
    "input": {
      "prompt": "<the slide-NN QC-passed prompt>. The first reference image is the company logo (place as specified, do not redraw). The second reference image is the founder; her likeness drives the portrait.",
      "input_urls": ["<LOGO_URL>", "<FOUNDER_PORTRAIT_URL>"],
      "aspect_ratio": "16:9",
      "resolution": "2K"
    }
  }'
```

**JSON body (the shape):**
```json
{
  "model": "gpt-image-2-5-sunburst-image-to-image",
  "input": {
    "prompt": "<full QC-passed prompt + the reference-naming sentence(s)>",
    "input_urls": ["<LOGO_URL>", "<FOUNDER_PORTRAIT_URL if A5>", "<STYLE_FRAME_URL if used>"],
    "aspect_ratio": "16:9",
    "resolution": "2K"
  }
}
```

**Rules for Mode B (all enforceable):**
1. **`input_urls` order is load-bearing and stated in the prompt.** The prompt MUST name what each reference is, in order: "the first reference is the logo, the second is the founder." A reference passed but not named in the prompt is a defect - the model may copy the wrong thing.
2. **Up to 16 public https URLs.** Each must be a reachable public https URL (Kie cannot read a local path or a private/expiring link). Max 30 MB each (jpeg/png/webp/jpg). A `LOGO_URL` that 404s or requires auth = HARD STOP (see §7).
3. **Logo reference = "place, do not redraw."** The logo reference sentence always instructs the model to PLACE the supplied mark, never to redraw/recolor/restyle it. This is the anti-mutation instruction.
4. **Style-reference frame requires the style-reference-only directive.** If a reference is passed for STYLE (not the logo, not the face) - e.g. a frame from an analyzed reference deck - the prompt MUST include, verbatim (MODEL-SPECS §4): *"Use the attached style-reference image only as style reference for color grading, lighting, and composition - do not copy its subjects, faces, or text."* Without this sentence the model copies the reference's subjects verbatim. Omitting it when a style frame is attached = auto-fail.
5. **The logo reference is NOT a style-reference.** Never apply the style-reference-only directive to the logo URL (that would tell the model to ignore the logo's shape - the opposite of what we want). The two reference types get opposite instructions; keep them distinct and named.
6. **English/Latin-only pin is mandatory.** The `prompt` MUST carry the pin verbatim (Section 1A): *"All text rendered in the image MUST be in English, Latin alphabet ONLY. NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled correctly, letter-for-letter. No garbled, misspelled, or invented text."* Omitting it is an auto-fail (check 10).

---

## 6. MODE C - IMAGE-TO-TEXT / JSON (analysis: there is NO Kie.ai call for this)

"Image-to-text/JSON" in concern 20 means "read an image and produce structured output" - two real Presentations needs:

- **Analyzing a reference deck into named style families** (seeding the Design Intelligence Library - see SOP-IMG-02). The agent rasterizes the deck (LibreOffice + pdftoppm), then READS the slide PNGs with its own multimodal vision and writes the Deck Style System file. No Kie.ai job is submitted.
- **QC-reading a rendered slide** for defects (hook on every slide, the word "webinar," bracket placeholders, logo mutation). The QC agent READS `working/renders/slide-NN.png` directly and scores it. No Kie.ai job is submitted.

**Hard rule:** There is no `gpt-image-2-image-to-text` or "JSON extraction" generation endpoint in the roster (MODEL-SPECS §1 has 7 endpoints, none of them image-to-text). An agent that POSTs an analysis/extraction job to `createTask` is making a malformed call. Image analysis is always the agent's own read. If an agent reports "I called Kie image-to-text to analyze the deck," that report is wrong and is an auto-fail of this SOP.

---

## 7. ENFORCEMENT CHECKS (what auto-fails the slide / the run)

The Slide Submitter (at submit time) and the QC Specialist (at image QC) enforce these. Each is a concrete PASS/FAIL trigger, not guidance.

| # | Check (trigger) | PASS | AUTO-FAIL |
|---|---|---|---|
| 1 | **Mode matches assets.** If a URL logo is in use (URL image-to-image mode) OR slide is A5 OR a style frame is passed, the submitted body's `model` is `gpt-image-2-5-sunburst-image-to-image` and `input_urls` is non-empty. | I2I used, refs present | T2I used on a slide that has a logo/portrait/style frame, OR I2I with an empty `input_urls` |
| 2 | **Reference naming.** Every URL in `input_urls` is named, in order, in the prompt ("first reference is the logo...", "second is the founder..."). | All refs named in order | A ref URL present with no naming sentence |
| 3 | **Logo "place, do not redraw."** The logo reference sentence forbids redrawing/recoloring/restyling the logo. | Sentence present | Logo described only in words with no "do not redraw" instruction (the mutation path) |
| 4 | **Style-frame directive.** If a STYLE reference frame is in `input_urls`, the style-reference-only directive sentence is present verbatim. | Directive present | Style frame attached, directive missing |
| 5 | **No style-only directive on the logo/face.** The style-reference-only directive is NOT applied to the logo URL or the founder URL. | Directive scoped to style frame only | Directive applied to the logo or face (which would erase them) |
| 6 | **Reachable refs.** Every `input_urls` entry is a public https URL that returns 200 and ≤30 MB. | All reachable | Any 404 / auth-required / >30 MB / non-https / local-path ref |
| 7 | **No analysis-as-Kie-call.** No `createTask` body whose intent is "read/extract/analyze." | Analysis done by agent read | An "image-to-text"/"extract JSON" job POSTed to Kie |
| 8 | **resultUrls parse.** Download reads `JSON.parse(data.resultJson).resultUrls[0]`, not `data.url`. | Correct field | Reads `.url` (the old-runbook bug) |
| 9 | **Logo identity (image QC).** The rendered logo on the slide is the SAME mark as the locked `LOGO_URL` asset (shape, color, lockup), on every slide. | Identical mark | A different mark than the locked asset on any slide (the reference-case logo-mutation defect) - see SOP-IMG-04 lock |
| 10 | **English/Latin-only pin + render (write + read).** WRITE-time: every submitted `prompt` carries the mandatory pin verbatim (Section 1A). READ-time (image QC): the rendered slide shows only English Latin-alphabet text, spelled correctly letter-for-letter. | Pin present in prompt AND render is clean English | Pin missing from any prompt, OR any rendered slide carries CJK / non-Latin glyphs or garbled/misspelled text |

Check 10 is the close of the garbled-text loop: the pin in the prompt (WRITE-time) is the guard; the clean-English render (READ-time) is the verification. `build_deck.py` appends the pin automatically, so a deterministic deck satisfies the WRITE-time half by construction.

Check 9 is the closing of the reference-case logo-mutation loop: passing the logo via I2I (checks 1–3) is the WRITE-time guard; the rendered-logo-matches-locked-asset comparison is the READ-time guard. Both are required. A deck that passes checks 1–8 but renders a mutated logo still fails check 9.

---

## 8. ESCALATION / REPAIR PATH

| Condition | First action | If unresolved |
|---|---|---|
| `LOGO_URL` 404s / needs auth / not https (check 6) | Slide Submitter halts the wave. Notify Brand Steward: re-host the logo to a public https URL (client GHL media library or Drive) and update `LOGO_URL`. Do NOT fall back to T2I to "get unblocked" - that reintroduces logo mutation. | Director; then operator |
| A slide was submitted T2I when it should have been I2I (check 1) | Image QC fails the slide; Slide Submitter re-submits that slide as I2I with the logo reference. Counts against the per-slide 3-attempt cap. | After 3 loops: Director |
| Rendered logo differs from locked asset on ≥1 slide (check 9) | Re-submit the affected slides via I2I with the locked `LOGO_URL` and the "place, do not redraw" sentence. If the logo still garbles after 2 attempts, escalate to the Director, who may switch the deck to a local logo file placed at assembly (SOP-IMG-05 Rule A mechanism 2); never edit a PNG and never write `pptx_text_overlays.json` (AF-OVERLAY-DELIVERED, Decision 5C). | Director |
| Agent claims it used a Kie "image-to-text" endpoint (check 7) | Reject the report. The analysis must be redone as an agent multimodal read. | Director |
| Kie outage (no model available) | Per the master SOP: PAUSE and escalate. Never substitute a different model mid-run. | Operator updates the model catalog (`presentation_job/model_catalog.json`) in writing |

---

## 9. PASS vs FAIL EXAMPLES (drawn from the actual reference-case defects)

**FAIL (the real reference-case defect):** A content slide with a logo on file was submitted with body `{"model":"gpt-image-2-5-sunburst-text-to-image","input":{"prompt":"...with the [CLIENT_LOGO_NAME] ringed-leaf logo in the lower right..."}}`. No `input_urls`. Result: the model invented a logo, and across the deck it drew a ringed leaf on one slide, a bare leaf on another, a monogram on a third, a mountain peak on a fourth. Fails check 1 (T2I on a logo slide) and check 9 (logo not identical to a locked asset).

**PASS:** The same slide submitted as `{"model":"gpt-image-2-5-sunburst-image-to-image","input":{"prompt":"... The first reference image is the company logo: place it on a white chip in the lower-right corner at ~9% slide width, do not redraw, recolor, or restyle it. ...","input_urls":["https://media.../client-logo.png"],"aspect_ratio":"16:9","resolution":"2K"}}`. One locked logo asset, named as the first reference, with the "do not redraw" instruction. Passes checks 1–3; the rendered logo is the same mark on every slide (check 9).

**FAIL:** An A5 founder slide submitted I2I with `input_urls:["<LOGO_URL>","<FOUNDER_URL>"]` but the prompt never said which reference was which. The model painted the logo's colors onto the founder's blazer. Fails check 2 (references not named in order).

**FAIL:** A slide passed a frame from a previously-analyzed reference deck as a style anchor but omitted the style-reference-only directive; the render copied a person from that reference slide verbatim. Fails check 4.

**FAIL:** An agent reported "I ran the reference deck through Kie image-to-text to get the style families." There is no such endpoint; the analysis was never actually performed. Fails check 7.

---

*End of SOP-IMG-01. This SOP teaches the call per mode; it changes no model. Model ids are decided in one place only, `presentation_job/model_catalog.json`; the ids quoted in this SOP are illustrations of its current values, and the catalog wins if they ever differ.*
