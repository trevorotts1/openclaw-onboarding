# SOP-IMG-01 - KIE.AI Call Mechanics (the three call modes, made exact)

**Cluster:** Image-Gen Mechanics + Design-Library (skill 45) Integration
**Status:** Reference SOP - extends the live Presentations pipeline; does not replace it. The logo-on-every-slide image-to-image path this SOP teaches is already mandated in the live slide-image-creator.md (the gpt-image-2-image-to-image path with LOGO_URL in input.input_urls) and the rendered-logo-identity check is the live AF-F7 (logo drift) auto-fail; this SOP is the authored mode-selection reference behind them.
**Owner role (Presentations):** Slide Submitter (primary), Slide Image Creator (secondary, for which-mode declaration)
**Master authority extended:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` §9 (Phase 4) and Appendix A; `45-design-intelligence-library/library/_system/MODEL-SPECS.md` (the single source of truth for model IDs and limits)
**Library-version pin:** CLIENT-WEBINAR-DECK-SOP §9.0 model manifest; MODEL-SPECS v1.2

---

## 0. WHY THIS SOP EXISTS (the defect it kills)

Concern 20 (verbatim): "Kie.ai text-to-image vs image-to-image vs image-to-text/JSON use DIFFERENT curl / JSON / HTTP-POST structures. Logo-on-every-slide = image-to-image. The SOP must teach the correct call per mode."

The forensic reference deck (Dimension F) proved the consequence of guessing the mode: the logomark mutated into at least four different marks across the deck (ringed leaf, bare leaf, a generic monogram, mountain peak) because the slides were generated text-to-image per slide instead of composited image-to-image with one locked logo asset passed as a reference. An agent that does not know the exact call structure for each mode WILL default to text-to-image and WILL reinvent the logo.

This SOP is a precise reference an agent follows without guessing. It does not introduce a new model. The model manifest (CLIENT-WEBINAR-DECK-SOP §9.0) still pins `gpt-image-2-image-to-image` / `gpt-image-2-text-to-image`. This SOP makes the choice between them, and the body for each, mechanical.

**Why GPT-Image-2 is the pinned model (the WORLD INTELLIGENCE rationale, SOP-ENGINE-00 Engine 5).** The pin is not arbitrary. GPT-Image-2 is mandated specifically because of its strong REAL-WORLD GROUNDING: it knows what an actual office, kitchen table, empty classroom at 6am, or a roughly 15-year-old's normal bedroom actually looks like, and it renders believable people, props, and scale for THIS character rather than a generic studio fantasy. That grounding is exactly what the WORLD ENGINE depends on (slide-image-creator-sops.md element 11 / SOP 9.3, the "would this exact person actually be in this exact room?" believability rule). A model with weaker real-world grounding would force the World Intelligence gate to fight the renderer; GPT-Image-2 makes grounded, believable scenes the default. This is the load-bearing reason the model is pinned, stated here so the pin is a defensible doctrine, not a bare config value.

This is a build-mechanics reference. NONE of its content is ever printed on a slide. (Cross-ref the Audience-Facing battery in the slide-craft cluster.)

---

## 1. PURPOSE

Give every agent the EXACT call structure (HTTP verb, endpoint, headers, JSON body, polling, result parsing) for each of the three Kie.ai interaction modes a Presentations deck uses, plus a single decision rule for picking the mode per slide. Make the wrong mode a detectable, auto-failable condition rather than a silent default.

---

## 1A. THE DETERMINISTIC RENDER PATH IS MANDATORY (no self-generate, no native image tool)

Every Kie.ai call described in this SOP is made by a SHIPPED SCRIPT, never by an agent typing an HTTP call from memory. There are exactly two renderers, both in `23-ai-workforce-blueprint/templates/presentation-render/` (installed into the client's Presentations scripts directory on a materialized box):

- **`build_deck.py`** — the single-command deterministic path. The builder writes `slides.json` (its only creative output) and runs the script; the script composes each prompt MECHANICALLY (scene + the agent's EXACT copy verbatim + optional logo wordmark + layout hint + the mandatory English/Latin-only pin), submits `gpt-image-2-text-to-image`, polls, downloads + verifies each PNG, and assembles the `.pptx`. No model decides wording at runtime.
- **`kie_generate.py`** — the image-to-image / text-to-image submit+poll+download helper for slides that must pass references (Mode B below).

**The mandated flow is:** the builder writes `slides.json` → runs `build_deck.py` → KIE.ai (createTask → recordInfo → `resultUrls[0]`) is the ONLY render call → register the `.pptx` the script produced. **FORBIDDEN, each an auto-fail (AF-I14 / AF-RENDERER):** generating any image with a native/built-in tool (`image_generate`, `openai`, etc.); writing an inline hand-typed KIE.ai HTTP call instead of the script; the dead endpoint `/api/v1/image/gpt-image`; hand-editing PNGs or substituting stock/placeholder images. A non-zero exit means the deck is NOT built — never fake a deliverable.

**MANDATORY ENGLISH / LATIN-ONLY PIN — every image prompt carries this verbatim (every slide, every mode):**

> All text rendered in the image MUST be in English, Latin alphabet ONLY. NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled correctly, letter-for-letter. No garbled, misspelled, or invented text.

`build_deck.py` appends this pin to every prompt automatically. Any prompt authored by hand for a Mode A or Mode B call below (or at the Phase 2/3 prompt-writing stage) MUST include this pin verbatim. A prompt missing the pin, or a render carrying CJK / non-Latin glyphs or garbled/misspelled text, is an auto-fail (see check 10 in Section 7).

---

## 2. THE THREE MODES (what each is FOR)

| Mode | Kie.ai endpoint family | What it does | When the Presentations pipeline uses it |
|---|---|---|---|
| **A. Text-to-Image (T2I)** | model `gpt-image-2-text-to-image` | Generates a slide image from words ONLY. No reference images. The model invents every pixel, including any logo or face described in words. | ONLY when the deck has NO logo asset AND no founder portrait for this slide (`LOGO_ON_SLIDES = false` AND archetype is not A5). Rare. |
| **B. Image-to-Image (I2I)** | model `gpt-image-2-image-to-image` | Generates a slide image from words PLUS up to 16 reference image URLs passed in `input_urls`. The references anchor real assets (the locked logo, the founder's real face, an optional style-reference frame) so they are composited rather than reinvented. | THE DEFAULT for every slide that carries the logo (i.e. almost every slide), and for every A5 founder-portrait slide. |
| **C. Image-to-Text / JSON (analysis)** | NOT a Kie.ai generation endpoint | "Read this image and return structured findings" (e.g. analyze a reference deck into named style families; QC-read a rendered slide for defects). | Done by the multimodal LLM agent READING the image directly. There is no Kie.ai HTTP call for this. See §6. |

**The hard mode-selection rule (this is the gate):**

> If a logo asset exists (`LOGO_ON_SLIDES = true`, a `LOGO_URL` is on file) OR the slide is archetype A5 (founder portrait) OR any reference frame is being passed for style -> the call MUST be Mode B (I2I) with the reference URL(s) in `input_urls`. A T2I call (Mode A) on any such slide is an AUTO-FAIL.

There is no "image-to-text/JSON" Kie.ai endpoint to call. An agent that tries to POST an "extract JSON" job to Kie.ai is wrong; analysis is the agent's own multimodal read (§6).

---

## 3. SHARED CALL LIFECYCLE (identical for Mode A and Mode B)

Every generation call, regardless of mode, follows this lifecycle. This is verbatim from CLIENT-WEBINAR-DECK-SOP §9.3-9.4 and MODEL-SPECS §5; reproduced here so the modes can be contrasted side by side.

1. **Submit (async):** `POST https://api.kie.ai/api/v1/jobs/createTask`
   - Headers: `Authorization: Bearer $KIE_API_KEY` (the CLIENT's own key - never a shared key), `Content-Type: application/json`
   - Body: see §4 (Mode A) or §5 (Mode B).
2. **Capture the task id:** on `{ "code": 200, "data": { "taskId": "..." } }`, append `{ "slide_NN": "<taskId>" }` to `working/checkpoints/kie_task_ids.json` immediately, before submitting the next slide.
3. **Rate cap:** never more than 20 new generation requests / 10 seconds, per account (source: https://docs.kie.ai/ Section 8 "Rate Limits & Concurrency", verified 2026-06-14). Submit in waves of 20, then sleep 10s (the documented window). Retries count against the cap.
4. **Poll:** after the LAST submit, wait 5 minutes, then `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` (same Bearer) every 60s. Parse `data.state`  in  {`waiting`,`success`,`fail`}. Treat `fail`/`failed`/`error`/`cancelled` as terminal failure; log `data.failCode` + `data.failMsg`.
5. **Download:** on `success`, `data.resultJson` is a JSON STRING; parse it -> `resultUrls` (an ARRAY) -> download `resultUrls[0]` to `working/renders/slide-NN.png`. It is `resultUrls`, NOT `.url` - the old runbook had this wrong.
6. **Poll cap:** 100 poll passes max. At 100 with tasks still `waiting`, STOP, checkpoint, escalate the stuck task ids. Never loop forever.

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
    "model": "gpt-image-2-text-to-image",
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
  "model": "gpt-image-2-text-to-image",
  "input": {
    "prompt": "<full QC-passed prompt>",
    "aspect_ratio": "16:9",
    "resolution": "2K"
  }
}
```

**Rules for Mode A:**
- There is NO `input_urls` field. Adding one to a T2I body is malformed - the reference would be ignored, and the agent would falsely believe the logo was composited. If `input_urls` is needed, the call is Mode B, not Mode A.
- Everything the model must draw is in `prompt`. A logo described in words here WILL be reinvented (the logo-mutation defect). That is exactly why a deck with a logo never uses Mode A.
- The `prompt` MUST carry the mandatory English/Latin-only pin verbatim (Section 1A): *"All text rendered in the image MUST be in English, Latin alphabet ONLY. NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled correctly, letter-for-letter. No garbled, misspelled, or invented text."* (When the deterministic `build_deck.py` path is used, the script appends this for you.)

---

## 5. MODE B - IMAGE-TO-IMAGE (the default; logo + portrait + optional style frame)

**Use when (the default for nearly every slide):** a `LOGO_URL` exists, OR the slide is A5 (founder portrait), OR a style-reference frame is being passed. This is how "logo on every slide" is achieved.

**curl (logo on a content slide):**
```bash
curl -s -X POST 'https://api.kie.ai/api/v1/jobs/createTask' \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-image-2-image-to-image",
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
    "model": "gpt-image-2-image-to-image",
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
  "model": "gpt-image-2-image-to-image",
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
| 1 | **Mode matches assets.** If `LOGO_URL` exists OR slide is A5 OR a style frame is passed, the submitted body's `model` is `gpt-image-2-image-to-image` and `input_urls` is non-empty. | I2I used, refs present | T2I used on a slide that has a logo/portrait/style frame, OR I2I with an empty `input_urls` |
| 2 | **Reference naming.** Every URL in `input_urls` is named, in order, in the prompt ("first reference is the logo...", "second is the founder..."). | All refs named in order | A ref URL present with no naming sentence |
| 3 | **Logo "place, do not redraw."** The logo reference sentence forbids redrawing/recoloring/restyling the logo. | Sentence present | Logo described only in words with no "do not redraw" instruction (the mutation path) |
| 4 | **Style-frame directive.** If a STYLE reference frame is in `input_urls`, the style-reference-only directive sentence is present verbatim. | Directive present | Style frame attached, directive missing |
| 5 | **No style-only directive on the logo/face.** The style-reference-only directive is NOT applied to the logo URL or the founder URL. | Directive scoped to style frame only | Directive applied to the logo or face (which would erase them) |
| 6 | **Reachable refs.** Every `input_urls` entry is a public https URL that returns 200 and <=30 MB. | All reachable | Any 404 / auth-required / >30 MB / non-https / local-path ref |
| 7 | **No analysis-as-Kie-call.** No `createTask` body whose intent is "read/extract/analyze." | Analysis done by agent read | An "image-to-text"/"extract JSON" job POSTed to Kie |
| 8 | **resultUrls parse.** Download reads `JSON.parse(data.resultJson).resultUrls[0]`, not `data.url`. | Correct field | Reads `.url` (the old-runbook bug) |
| 9 | **Logo identity (image QC).** The rendered logo on the slide is the SAME mark as the locked `LOGO_URL` asset (shape, color, lockup), on every slide. | Identical mark | A different mark than the locked asset on any slide (the logo-mutation defect) - see SOP-IMG-04 lock |
| 10 | **English/Latin-only pin + render (write + read).** WRITE-time: every submitted `prompt` carries the mandatory pin verbatim (Section 1A). READ-time (image QC): the rendered slide shows only English Latin-alphabet text, spelled correctly letter-for-letter. | Pin present in prompt AND render is clean English | Pin missing from any prompt, OR any rendered slide carries CJK / non-Latin glyphs or garbled/misspelled text |

Check 10 is the close of the garbled-text loop: the pin in the prompt (WRITE-time) is the guard; the clean-English render (READ-time) is the verification. `build_deck.py` appends the pin automatically, so a deterministic deck satisfies the WRITE-time half by construction.

Check 9 is the closing of the logo-mutation loop: passing the logo via I2I (checks 1-3) is the WRITE-time guard; the rendered-logo-matches-locked-asset comparison is the READ-time guard. Both are required. A deck that passes checks 1-8 but renders a mutated logo still fails check 9.

---

## 7A. CONSOLIDATED QC GATE TABLE (full prompt + image, ENFORCED auto-fail + reroute)

Section 7 above gates the CALL MECHANICS (which mode, which references, which fields). This section is the complete content QC gate the Slide Submitter runs at submit (prompt) and the QC Specialist runs at image QC (render), covering BOTH the prompt and the rendered image for every defect class. **Every row is a BINARY PASS / FAIL auto-fail with an exact detection, checked FIRST before any 1-to-10 scoring; a triggered row forces FAIL on the slide (or the DECK where marked) regardless of any average -- no averaging, no "almost passed".** This mirrors the live `qc-specialist-presentations.md` auto-fail tables and the master `CLIENT-WEBINAR-DECK-SOP.md` Section 10.5 gate table; the repo-canonical codes (AF-P1..AF-P16, AF-I1..AF-I10, AF-F7/F9/F10, AF-R1..AF-R3, AF-BAKED, AF-RENDERER) are authoritative. Nothing client-specific is hardcoded: `REPRESENTATION_MIX`, brand hexes, currency, `LOGO_URL`, and the verbatim copy are all read from the client's `intake.json` / approved `slides_copy.md`. The QC Specialist records the triggered code, the slide, the exact measured value (e.g. the integer char count), and the verbatim failure message, then executes the reroute.

### 7A.1 PROMPT GATES (write-time, at submit) -- every prompt, before createTask

| # | Gate | Live code | PASS | AUTO-FAIL (binary) | Reroute |
|---|---|---|---|---|---|
| P1 | English / Latin pin present | AF-P-ENGLISH (Section 1A pin) | Prompt carries the verbatim English/Latin-only pin | Pin absent | Append pin; re-QC prompt only |
| P2 | Exact copy, NO placeholder | AF-P3 + AF-P14 + AF-P16 | Every on-slide string verbatim to slides_copy.md, each spelling-locked, zero `[...]` / "owner to confirm" / "tbd" / "placeholder" tokens as copy | Paraphrase; unlocked string; placeholder/bracket token presented as render copy | Resolve placeholder with client's real content (or pull slide), re-lock, re-QC |
| P3 | Scene + layout present | AF-P9 + AF-P11 | Concrete scene/moment; archetype declared line 1; zone percentages + thirds placement for every element | "Just a background with text"; no archetype; no layout | Add scene + layout direction; re-QC |
| P4 | Logo text correct (image-to-image) | AF-P15 (= Section 7 checks 1-3) | `LOGO_ON_SLIDES = true` slide declares Mode B with locked `LOGO_URL` first in `input_urls`, carries "place, do not redraw" + "do not invent any mark" | Logo in words only; Mode A on a logo slide; missing "do not redraw" | Switch to Mode B, name the reference, add directive |
| P5 | 16:9 + 2K stated | AF-P (format line) | Both "16:9" and "2K" present | Either missing | Add the format line |
| P6 | Char count within [MIN, MAX] | AF-P1 / AF-P2 (Check 0, run first) | `5000 <= len(prompt) <= 18000`; record exact integer; target 9000-14000 | `len < 5000` (AF-P1) OR `len > 18000` (AF-P2) | Expand with defect-preventing specificity (under) or condense front-loaded + log (over) |
| P7 | Audience-matched representation | AF-P-REP | People match the slide's captured `REPRESENTATION_MIX` group; OR NO PEOPLE + operator flag when uncaptured | Person specified against no/uncaptured mix assignment | Re-cast to captured mix, or NO PEOPLE + flag |
| P8 | NO hardcoded demographic default | AF-P-REP / AF-R3 (the 60/30/10 landmine) | No invented racial/demographic percentage; uncaptured -> NO PEOPLE + flag | The "60% Black/Brown, 30% other POC, 10% white" default OR ANY invented split the client did not supply | Strip the default; NO PEOPLE + flag operator until client confirms |
| P9 | Currency correct | AF-P-CURRENCY | Every price/anchor/struck/stack value uses the client's currency symbol (default `$`), locked verbatim | Wrong symbol; missing symbol where required; localized/auto-translated currency | Correct the currency string, re-lock |

### 7A.2 IMAGE GATES (read-time, at image QC + final deck QC) -- every rendered slide

| # | Gate | Live code | PASS | AUTO-FAIL (binary) | Reroute |
|---|---|---|---|---|---|
| I1 | 100% English / zero CJK | AF-I-ENGLISH (= Section 7 check 10 read-half) | Every rendered glyph is English Latin-alphabet | ANY Chinese / CJK / non-Latin character anywhere | Regenerate as-is (render noise, Section 10.1 of master SOP) |
| I2 | No garbled / misspelled text | AF-I1 | Every word correct, no duplicated word, no garbled glyph | Any misspelling / duplicated word / garbled glyph in any text element | Re-prompt + RE-SEED (new prompt + new seed) and re-render the single composed image; persistent garble -> HUMAN ESCALATION. NEVER a native-text overlay (Decision 5C; AF-OVERLAY-DELIVERED). |
| I3 | Rendered text MATCHES intended copy | AF-F9 (OCR readback) | OCR of every text element diffs clean against the intended verbatim string | Any baked typo, garble, missing connector, or leaked stage-direction string vs intended copy | Re-prompt + RE-SEED and re-render; persistent -> HUMAN ESCALATION. NEVER a native-text overlay (AF-OVERLAY-DELIVERED). |
| I4 | Real KIE gpt-image-2 (NOT native) | AF-BAKED / AF-RENDERER (= Section 1A FORBIDDEN list) | Genuine Kie.ai `gpt-image-2` raster, typography baked in by the model, from the canonical render path | Native / built-in tool render; Pillow/PPTX/ImageDraw overlay; flat placeholder fill; stock/hand-edited substitute; per-deck renderer | HARD STOP deck: rebuild via canonical path; never fake the deliverable |
| I5 | Full-bleed 2560x1440 | AF-I-DIMS | Full-bleed 16:9 at 2K, nominal **2560x1440**, fills the canvas edge to edge, no letterbox / pillarbox / border / margin | Wrong aspect ratio; sub-2K; any non-full-bleed framing | Regenerate with 16:9 / 2K confirmed in the createTask body |
| I6 | Logo correct (cross-slide identity) | AF-I4 (slide) + AF-F7 (deck) (= Section 7 check 9) | `LOGO_ON_SLIDES = true`: SAME locked mark on every slide, identical to `LOGO_URL` (lockup, color, scale, crop, chip, corner) | Logo absent/illegible/distorted/recolored/clipped (AF-I4); a different lockup / monogram / variant on any slide (AF-F7) | Re-submit via Mode B with locked `LOGO_URL` + "place, do not redraw"; after 2 fails -> composite the REAL logo IMAGE onto the PNG via the PIL image-composite path (SOP-IMG-05), baked into the image before assembly. This is an IMAGE composite, NOT native text — never a `pptx_text_overlays.json` text box (AF-OVERLAY-DELIVERED). |
| I7 | Currency $ rendered correctly | AF-I-CURRENCY | Every rendered price shows the client's currency symbol (default `$`), matching intended copy | Wrong symbol; missing symbol where required; localized/auto-translated currency | Re-prompt + RE-SEED and re-render; persistent -> HUMAN ESCALATION. NEVER a native-text overlay for the price (AF-OVERLAY-DELIVERED). |
| I8 | On-brand palette | AF-I-PALETTE | Only the intake brand hexes in their assigned roles on the white base | Off-brand color cast; a palette the client did not supply; dark base without `DARK_OK` | Regenerate; if the prompt was the defect, revise COLOR VERIFICATION block and re-QC |
| I9 | Faces match the audience | AF-R1 / AF-R2 / AF-R3 (DECK-wide) | Every person matches the slide's assigned `REPRESENTATION_MIX` group; deck-wide cast tally within +/-10 pts of every captured group, bidirectional | Face off the assigned group; people when `REPRESENTATION_MIX` uncaptured (AF-R3); deck tally outside +/-10 pts under-representing a group OR mono-casting (AF-R1/AF-R2) | DECK-level fail: re-cast deficient / over-represented slides; tally once on generated images, again on final deck |

**Veto semantics (identical to the master SOP):** a slide-level trigger fails that slide and loops it (max 3 generation attempts per slide, then escalate to the Director per Section 8); a DECK-level trigger (I4 deck-wide native/renderer, I6 logo identity, I9 representation tally) fails the entire gate and blocks FINAL. The auto-fail is checked before scoring; the failing item receives no score. A non-zero exit from the canonical render path means the deck is NOT built -- fix the input or escalate; never mark a deck done on a faked or partial deliverable.

---

## 8. ESCALATION / REPAIR PATH

| Condition | First action | If unresolved |
|---|---|---|
| `LOGO_URL` 404s / needs auth / not https (check 6) | Slide Submitter halts the wave. Notify Brand Steward: re-host the logo to a public https URL (client GHL media library or Drive) and update `LOGO_URL`. Do NOT fall back to T2I to "get unblocked" - that reintroduces logo mutation. | Director; then operator |
| A slide was submitted T2I when it should have been I2I (check 1) | Image QC fails the slide; Slide Submitter re-submits that slide as I2I with the logo reference. Counts against the per-slide 3-attempt cap. | After 3 loops: Director |
| Rendered logo differs from locked asset on >=1 slide (check 9) | Re-submit the affected slides via I2I with the locked `LOGO_URL` and the "place, do not redraw" sentence. If the logo still garbles after 2 attempts, composite the REAL logo IMAGE onto the rendered PNG via the PIL image-composite path (SOP-IMG-05), baked into the image BEFORE assembly. This is an IMAGE composite of the real mark, NOT a native text run — NEVER write `pptx_text_overlays.json` (its presence at assembly is AF-OVERLAY-DELIVERED, Decision 5C). | Director |
| Agent claims it used a Kie "image-to-text" endpoint (check 7) | Reject the report. The analysis must be redone as an agent multimodal read. | Director |
| Kie outage (no model available) | Per the master SOP: PAUSE and escalate. Never substitute a different model mid-run. | Operator updates the manifest in writing |

---

## 9. PASS vs FAIL EXAMPLES (drawn from the actual forensic reference deck defects)

**FAIL (the forensic reference deck defect):** A content slide with a logo on file was submitted with body `{"model":"gpt-image-2-text-to-image","input":{"prompt":"...with a brand ringed-leaf logo described in words in the lower right..."}}`. No `input_urls`. Result: the model invented a logo, and across the deck it drew a ringed leaf on one slide, a bare leaf on another, a generic monogram on a third, a mountain peak on a fourth. Fails check 1 (T2I on a logo slide) and check 9 (logo not identical to a locked asset).

**PASS:** The same slide submitted as `{"model":"gpt-image-2-image-to-image","input":{"prompt":"... The first reference image is the company logo: place it on a white chip in the lower-right corner at ~9% slide width, do not redraw, recolor, or restyle it. ...","input_urls":["https://media.../brand-logo.png"],"aspect_ratio":"16:9","resolution":"2K"}}`. One locked logo asset, named as the first reference, with the "do not redraw" instruction. Passes checks 1-3; the rendered logo is the same mark on every slide (check 9).

**FAIL:** An A5 founder slide submitted I2I with `input_urls:["<LOGO_URL>","<FOUNDER_URL>"]` but the prompt never said which reference was which. The model painted the logo's colors onto the founder's blazer. Fails check 2 (references not named in order).

**FAIL:** A slide passed a frame from the gold-standard analyzed reference deck as a style anchor but omitted the style-reference-only directive; the render copied a person from the reference slide verbatim. Fails check 4.

**FAIL:** An agent reported "I ran the reference deck through Kie image-to-text to get the style families." There is no such endpoint; the analysis was never actually performed. Fails check 7.

---

*End of SOP-IMG-01. This SOP teaches the call per mode; it changes no model. The model manifest (CLIENT-WEBINAR-DECK-SOP §9.0) remains the only place a model is named.*
