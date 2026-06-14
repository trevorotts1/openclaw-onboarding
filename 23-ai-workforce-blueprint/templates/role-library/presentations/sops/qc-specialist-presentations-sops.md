# SOPs Mirror -- QC Specialist -- Presentations

**Source:** presentations/qc-specialist-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### AUTO-FAIL RULE: an auto-fail condition forces FAIL for that item regardless of any average. Auto-fails are checked FIRST, before scoring.

#### Copy QC Auto-Fails (SOP 9.1)

The following conditions each independently force an immediate FAIL verdict on the affected slide. Check these before assigning any scores. Document every triggered auto-fail by criterion code in the QC report.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-C1 | Any em dash in any field of any slide. The em dash is the dead giveaway of unedited AI output. |
| AF-C2 | Hook count below 7 across the deck (mechanical count; count every tagged HOOK_REFRAIN occurrence and the dedicated hook slide). Fewer than 7 = auto-fail. |
| AF-C3 | Any fabricated proof or statistic not traceable to intake.json or proof_audit.txt. A number not present in the intake or research brief = auto-fail on that slide. |
| AF-C4 | Any cross-slide numeric mismatch (e.g., stack total stated as $5,282 on one slide and $5,276 on another). Defer the Offer Strategist mechanics to SOP 9.3, but a FAIL there blocks this gate. The QC agent compiles all repeated numbers and diffs them; any mismatch auto-fails all slides carrying the inconsistent value. |
| AF-C5 | Headline over 9 words (mechanical word count; count is exact). |

#### Prompt QC Auto-Fails (SOP 9.2)

Check these before scoring. Each independently forces FAIL on the affected prompt.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-P1 | Character count under 1500 (Check 0: count mechanically and RECORD the exact number in the report). |
| AF-P2 | Character count over 15000. |
| AF-P3 | Headline not verbatim to slides_copy.md HEADLINE field (any paraphrase, any changed word = auto-fail). |
| AF-P4 | Missing 16:9 or 2K (either absent = auto-fail). |
| AF-P5 | Dark background language present without DARK_OK = true. |
| AF-P6 | Missing thirds/zone language (explicit thirds placement for headline, people, and objects is required; "centered" alone is not thirds language). |
| AF-P7 | People are present in the slide spec but the prompt is missing any of: hair description, clothing description, or facial expression description. All three are required when people appear. |
| AF-P8 | Missing AVOID block (the closing constraints block listing negatives is mandatory in every prompt). |
| AF-P9 | Image-grounding failure (P6, BLOCKING): the prompt for a people-slide or scene-slide does NOT depict a concrete moment from THIS client's method, book, message, or offer (the GROUNDED_CONTENT variable carried in the brief). A prompt describing a generic, interchangeable scene that could belong to any business, when the brief named a specific grounded moment, = auto-fail. ("A confident woman at a desk" is generic; "the founder reviewing the {{CLIENT_METHOD}} 5-step intake dashboard at the kitchen table at 6am" is grounded.) |

#### Image QC Auto-Fails (SOP 9.3)

Check these before scoring. Each independently forces FAIL on the affected image.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-I1 | ANY misspelling, duplicated word, or garbled glyph in ANY rendered text anywhere on the slide. This applies to every word on the slide, not just the headline. Inspect all text elements. |
| AF-I2 | Any deformity: malformed hands, extra or missing fingers, distorted faces, warped or severed limbs. |
| AF-I3 | Wrong aspect ratio (must be 16:9; anything else = auto-fail). |
| AF-I4 | Missing or mangled logo when LOGO_ON_SLIDES = true (logo absent, illegible, distorted, or incorrectly placed = auto-fail). |
| AF-I5 | Dark background without DARK_OK = true. |
| AF-I6 | Emoji or clipart glyphs rendered anywhere in the image. Premium decks use photography and typography only. |
| AF-I7 | An em dash rendered in slide text. |
| AF-I8 | Image-grounding failure (P6, BLOCKING): a people-slide or scene-slide image that does NOT depict a concrete moment from THIS client's method, book, message, or offer (the GROUNDED_CONTENT variable). A generic stock-style scene that could belong to any business when the brief named a specific grounded moment = auto-fail. Grounding is scored at prompt QC (AF-P9) and re-verified here against the rendered image. |

#### Deck-Wide Representation Auto-Fails (SOP 9.3 + SOP 9.5 -- the casting tally, P5)

The representation tally is a DECK-WIDE mechanical count, not a per-slide check. It is run twice: once across the full set of GENERATED images (after Phase 5 image QC completes for the deck) and again on the FINAL assembled deck (Phase 6). Both runs must pass. Tally every people-slide by REPRESENTATION_MIX group and compute each group's share of all people-slides; compare against the captured REPRESENTATION_MIX percentages.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-R1 | Deck-wide cast tally is outside +/- 10 percentage points of any captured REPRESENTATION_MIX group on the GENERATED images. Example: REPRESENTATION_MIX is 70% African American women / 20% African American men / 10% mixed, but the generated people-slides tally 45% / 35% / 20%; the women group is 25 points low = auto-fail the deck (not a single slide; the whole cast distribution fails and the under-represented group's slides are re-cast). |
| AF-R2 | Deck-wide cast tally is outside +/- 10 percentage points of any captured REPRESENTATION_MIX group on the FINAL assembled deck (re-run after assembly, because dropped or substituted slides can shift the distribution). |
| AF-R3 | People appear anywhere in the deck when REPRESENTATION_MIX was NOT captured. Uncaptured audience = NO PEOPLE; any person rendered against an uncaptured mix is an invented demographic and an auto-fail. No racial or gender default is ever inferred. (This is the deck-wide enforcement of the brand-steward NO-PEOPLE-or-flag rule.) |

The representation tally is BIDIRECTIONAL: it fails BOTH under-representation of a captured group AND mono-casting (a deck that renders one group far above its captured share against a multicultural REPRESENTATION_MIX). It is not a one-directional skin-lightening check. When a representation requirement and a skin-tone-quality preference conflict, REPRESENTATION OVERRIDES SKIN-TONE-QUALITY: the captured audience composition is the governing rule, and a beautifully rendered but mono-cast deck still fails AF-R1/AF-R2. This is the counterweight to the DIU deep-skin-tone quality rule (skill-45 MASTER-SOP), which is a rendering-quality rule, not a casting rule.

#### Final-Deck / Assembled-Slide Auto-Fails (SOP 9.5 -- the composed slide, P3)

These are checked on the COMPOSED slide (the rendered PPTX, not the raw PNG) after the deck is rendered PPTX -> PDF -> PNG. They are the gap that let the colliding 5-box text stack ship on a prior deck. Each independently forces FAIL on the affected slide.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-F1 | Text-box collision: any two text boxes, or a text box and the logo chip, or a text box and a focal subject (a face), overlap on the composed slide. The coded collision assert (SOP 9.5) computes the bounding box of every text element and every overlay element and flags any intersection. A native PPTX overlay element that lands on top of another element = auto-fail. |
| AF-F2 | Contrast failure: any text element on the composed slide fails the WCAG-AA contrast ratio against the pixels directly behind it (4.5:1 for normal text, 3:1 for large text >= 24px). White text over a light photo region, or charcoal text over a dark photo region, that drops below the ratio = auto-fail. |
| AF-F3 | Legibility failure: any text element on the composed slide renders below the minimum legible size at presentation distance (computed as a fraction of slide height) or is clipped, truncated, or runs off the slide edge. |
| AF-F4 | An overlay element exists on the composed slide but no collision assert was run on it. Every native PPTX overlay element MUST pass an individual collision assert; an un-checked overlay is itself an auto-fail (you cannot pass a slide whose overlay you never collision-checked). |
| AF-F5 | The delivery pass-artifact `working/qc/final_deck_qc.json` is absent or its `pass` field is not `true` at the moment delivery is attempted. (This is the delivery interlock; see SOP 9.6.) |

---

### SOP 9.1 -- Copy QC Gate (Phase 1Q)

**When to run:** Phase 1Q -- immediately after the Slide Copywriter delivers slides_copy.md and proof_audit.txt. Runs before the owner approval gate (Phase 1A).

**Inputs:**
- working/copy/slides_copy.md
- working/copy/proof_audit.txt
- working/copy/hook_variants.json
- working/copy/intake.json (for comparison on proof claims and prices)

**Steps:**
1. For every slide, check ALL five Copy QC Auto-Fails (AF-C1 through AF-C5) BEFORE scoring. Record each triggered auto-fail by code in the report. A slide with any auto-fail is marked FAIL immediately.
2. Dispatch 3-5 QC agents (minimax-m3:cloud) each independently scoring slides_copy.md on all 17 criteria. Each agent returns a score per criterion per slide.
3. Average the agent scores for each criterion across all slides. Compute the overall average.
4. Apply double-weight to criteria 1, 2, 7, 11, 12, and 15 (these are the most critical -- see criteria list below).
5. Write the copy_qc_report.json. One entry per slide, plus a summary. Structure:
   ```json
   {
     "gate": "Phase 1Q",
     "overall_average": 0.0,
     "weighted_average": 0.0,
     "auto_fails_triggered": [],
     "pass": true,
     "per_slide_scores": [
       {"slide": N, "auto_fails": [], "scores": {"c1": 0, "c2": 0, ...}, "average": 0.0, "pass": true, "notes": ""}
     ],
     "failing_slides": [],
     "revision_instructions": []
   }
   ```
6. For every slide with an auto-fail or scoring < 8.5: write specific revision_instructions. Each instruction must name the criterion or auto-fail code, the specific failure, and the required fix. Example: "Slide 12, AF-C5 (headline word count): headline is 11 words (max 9). Trim to: 'Your clients come to you every week.'"
7. If overall weighted_average >= 8.5 AND no individual slide scores below 7.0 AND no auto-fails: pass. Write `pass: true`.
8. If any slide scores below 7.0 OR overall weighted_average < 8.5 OR any auto-fail triggered: fail. Write `pass: false`. Send revision_instructions to the Slide Copywriter.
9. Increment `loop_count` in the report. If loop_count reaches 4 without a pass: escalate to the Director with the specific persistent failures.

**The 17 Copy QC Criteria (c1-c17):**
1. (double-weight) Hook appears >= 7 times across the deck, well-distributed (not clustered).
2. (double-weight) Every headline is 9 words or fewer. Count is exact.
3. Every subhead is 18 words or fewer.
4. Body copy is 3 bullets max or 30 words max per slide.
5. Slides are one big idea each. No slide tries to do two things.
6. Presentation arc is complete: hook / problem / solution / proof / offer / price / close.
7. (double-weight) No em dashes anywhere in any field.
8. PRESENTER NOTE is present and substantive (not a duplicate of the slide copy) for every slide.
9. Price Ladder slides reference prices from price_ladder.json exactly (Offer Price Strategist cross-check).
10. Proof slides contain only items from the proof inventory (proof_audit.txt shows VERIFIED or PENDING -- never fabricated).
11. (double-weight) No fabricated statistics (any number not in intake.json is flagged).
12. (double-weight) No literal client names ({{TOKENS}} used wherever a real name would appear).
13. Every slide has a SECTION label matching arc_allocation.json.
14. Mode B slides: augmented slides preserve original copy per SOP 9.4 of slide-copywriter.
15. (double-weight) Doctrine battery -- ALL of the following must pass (each sub-item that fails is a criterion-15 failure):
    - Promises pitched, not products (every teach and offer slide pitches a promise, not a product feature).
    - Every DROP adds named value (the drop slide or its immediate successor names additional value added to the table; no drop strips value).
    - Offer serves BOTH emotion AND logic (emotionally driven imagery and future-pacing present, AND explicit math or priceless-pitch reasoning present in the offer section).
    - Cost-versus-value explicitly answered: if the offer produces money, the math is on screen; if non-monetary, the priceless pitch frame is used. Dollar values are never fabricated for non-monetary outcomes.
    - Light pitches woven throughout (the program is named and referenced inside the teaching sections, not only in the offer section).
    - Appetizer not dinner (each Secret teaches the WHAT and WHY and one quick win; the complete HOW lives inside the offer -- a Secret that hands over the complete HOW = fail).
    - At least one intrigue slide per section (a slide that makes the audience ask a question).
    - Compare/contrast device present in every Secret (old-way vs new-way or equivalent two-sided belief-shift mechanism).
    - A paid pitch exists (unless the owner has signed off on free-only in writing).
16. TEXT_ANCHOR variation: no more than 2 consecutive slides share the same TEXT_ANCHOR value. The QC agent checks the sequence of TEXT_ANCHOR fields in slides_copy.md and flags any run of 3 or more identical anchors.
17. Ladder integrity (all sub-items must pass):
    - ANCHOR slide carries the explicit memory hook ("Remember this number. Keep watching." or equivalent).
    - A BUILDUP slide immediately precedes every DROP slide (no DROP without a BUILDUP).
    - At least one callback is present in the offer section explicitly referencing the ANCHOR.
    - FINAL price sits below all ladder rungs (strictly less than DROP3 in drop mode).

**Outputs:**
- working/qc/copy_qc_report.json

**Hand to:** Director (pass = proceed to Phase 1A owner approval; fail = back to Slide Copywriter)

**Failure mode:** If QC agents are unavailable (model down), use a single agent with 2 passes (the agent scores each criterion twice and averages). If still unavailable after 30 minutes, escalate to the Director.

---

### SOP 9.2 -- Prompt QC Gate (Phase 3, Dual-Scored)

**When to run:** Phase 3 -- immediately after the Slide Image Creator delivers all prompt files in working/prompts/.

**Inputs:**
- working/prompts/slide-NN-prompt.txt (all files)
- working/copy/slides_copy.md (for headline verbatim verification)
- working/brand/style_block.md (for brand palette and representation ratio)
- working/copy/price_ladder.json (for price-drop slide verification)

**Steps:**
1. For every prompt, check ALL nine Prompt QC Auto-Fails (AF-P1 through AF-P9) BEFORE scoring. Check 0 (character count) is always first: count mechanically and record the exact integer in the report. AF-P9 (image-grounding) is a BLOCKING check: a prompt that does not depict a concrete moment from THIS client's method fails before scoring. A prompt with any auto-fail is marked FAIL immediately; record the code(s).
2. Dispatch 5-10 QC agents (minimax-m3:cloud) in parallel. Each agent independently scores each prompt on all 16 criteria.
3. For each prompt, calculate the per-agent score, then average across all agents.
4. Apply double-weight to criteria 2, 3, 4, 13, and 16 (the most commonly failing and highest impact; criterion 16 image-grounding is double-weighted because ungrounded imagery is the F3 defect this gate exists to stop).
5. Write prompt_qc_report.json. One entry per prompt (one per slide), including the recorded character count and any auto-fail codes.
6. For any prompt with an auto-fail or scoring < 8.5: write specific revision_instructions. Instructions must specify the failing auto-fail code or criterion and the exact change required.
7. Identify fail classification for each failing prompt: render-noise (image quality issues likely in generation), prompt-defect (structural problem with the prompt itself), or text-fail (headline text will not render correctly -- mark as text-fail-x2 if two text elements fail).
8. Pass: overall weighted average >= 8.5, no individual prompt below 7.0, no auto-fails. Fail: otherwise.
9. Increment loop_count. At loop_count = 4, escalate.

**The 16 Prompt QC Criteria (p1-p16):**
1. All 15 elements present in order (format / background / headline verbatim / typography / font placement / thirds / object placement / overlays / brand palette / logo / people / bullets / mood / professionalism / closing constraints).
2. (double-weight) Headline text is verbatim match to slides_copy.md HEADLINE field (not paraphrased).
3. (double-weight) Character count is 1,500-15,000. Target 5,000-7,500.
4. (double-weight) White base rule: element 2 specifies white background (unless DARK_OK=true).
5. People element (11) specifies at least one of the 3 engines with representation group and gender.
6. Thirds-grid assignment in element 6 is specific (named regions -- not "somewhere on the right").
7. No em dashes in the prompt body.
8. Brand palette (element 9): all 3 hex codes from STYLE BLOCK listed with roles.
9. Logo placement (element 10): matches STYLE BLOCK logo_placement_rule.
10. Overlays (element 8): present for hook slides per hook_variants.json; absent for non-hook slides.
11. Mood (element 13): specific and appropriate for the arc section.
12. AVOID block (element 15) includes: dark backgrounds, watermarks, em dashes, any unspecified text.
13. (double-weight) Representation ratio: spot-check 10 prompts -- people specifications are consistent with STYLE BLOCK representation_ratio.
14. Price-drop slides: struck price and new price match price_ladder.json exactly (verify for any slide in the Price Ladder arc section).
15. Prompt front-loads critical content: composition, people, and headline appear in the first 500 characters.
16. (double-weight) Image grounding (P6): the prompt depicts a CONCRETE moment from THIS client's method, book, message, or offer (the GROUNDED_CONTENT variable in the brief), not a generic interchangeable scene. The scored question is "does this image depict a concrete moment from THIS client's method?" Beyond the binary AF-P9 floor, this criterion scores HOW grounded the moment is: a prompt that names the specific method step, the specific setting where that step happens, and the specific outcome it produces scores high; a prompt that gestures at the industry generically scores low. This criterion is also evaluated against the rendered image at final-deck QC (SOP 9.5).

**Outputs:**
- working/qc/prompt_qc_report.json (with per-prompt character counts, auto-fail codes, scores, fail classifications, revision instructions)

**Hand to:** Director (pass = proceed to Phase 4 generation; fail = back to Slide Image Creator)

**Failure mode:** Same as SOP 9.1 -- fall back to single-agent dual-pass if model is unavailable.

---

### SOP 9.3 -- Image QC Gate (Phase 5) and Fail Classification

**When to run:** Phase 5 -- as each image is downloaded from Kie.ai to working/renders/. Run QC on each image as it arrives; do not wait for all images before starting QC.

**Inputs:**
- working/renders/slide-NN.png (raw downloads)
- working/prompts/slide-NN-prompt.txt (the prompt that generated this image)
- working/copy/slides_copy.md (for visual text verification and slide MOOD/emotion)

**Steps:**
1. For every image, check ALL eight Image QC Auto-Fails (AF-I1 through AF-I8) BEFORE scoring. A triggered auto-fail immediately marks the image FAIL; record the code(s) in the report. Auto-fail inspection includes: reading every word of rendered text on the slide for misspellings, duplicated words, and garbled glyphs (not just the headline -- all text elements); inspecting hands, faces, and limbs for deformities; verifying aspect ratio; verifying logo presence and integrity when LOGO_ON_SLIDES = true; checking background darkness; scanning for emoji or clipart glyphs; checking rendered text for em dashes; and verifying the image depicts a concrete moment from THIS client's method (AF-I8 grounding, BLOCKING).
2. Dispatch up to 5 QC agents (minimax-m3:cloud) per batch of images. Each agent scores a non-overlapping batch (e.g., agent 1 handles slides 1-15, agent 2 handles slides 16-30, etc.).
3. Each agent scores each image on all 15 criteria.
4. Apply double-weight to criteria 3, 5, 6, 7, and 15 (most critical for the assembled deck; criterion 15 image-grounding is double-weighted).
5. Write image_qc_report.json with per-image auto-fail codes and scores.
5a. **Deck-wide representation tally (P5, AF-R1/AF-R3) -- run ONCE after the full deck's images have all passed per-slide image QC.** Tally every people-slide by its REPRESENTATION_MIX group; compute each group's share of all people-slides; compare to the captured REPRESENTATION_MIX percentages. If any group is outside +/- 10 percentage points, trigger AF-R1 and re-cast the deficient/over-represented slides (bidirectional: fails both under-representation AND mono-casting). If people appear when REPRESENTATION_MIX was never captured, trigger AF-R3 (invented demographic). Record the tally table and verdict in image_qc_report.json under `representation_tally`. The tally is a DECK property, not a slide property: the deck fails even if every individual image passed its own per-slide QC.
6. For each failing image (auto-fail or score < 8.5): classify the failure type:
   - `render-noise`: generation artifact, blurriness, corrupted output -- re-generate with the same prompt.
   - `prompt-defect`: the prompt produced the wrong composition or wrong mood -- send prompt back to Slide Image Creator for revision, then re-generate.
   - `text-fail`: the headline text is garbled, missing, or wrong -- if one text element is wrong, mark `text-fail-x1`; if two or more, mark `text-fail-x2`. Send back to Slide Image Creator with specific text correction instructions.
7. For render-noise failures: re-generate immediately (up to 3 attempts) without touching the prompt.
8. For prompt-defect or text-fail: send revision instructions to Slide Image Creator, then re-generate.
9. Maximum 3 total attempts per image. At attempt 4: escalate to the Director.
10. Passed images are moved to working/media-library/ immediately (do not wait for full deck pass).

**The 15 Image QC Criteria (i1-i15):**

AUTO-FAIL LAYER (checked first; see AF-I1 through AF-I8 above plus the deck-wide AF-R1/AF-R3 tally -- these override scoring):
- i-AF: Any of AF-I1 through AF-I8 triggers a hard FAIL on the image before the scored layer runs; the deck-wide AF-R1/AF-R3 representation tally (step 5a) hard-FAILS the deck regardless of individual image scores.

SCORED LAYER (1-10, applied only after auto-fail check passes):
1. 16:9 aspect ratio, 2K resolution confirmed.
2. White base background (or dark if DARK_OK=true).
3. (double-weight) Headline text is legible, matches slides_copy.md HEADLINE, no garbling. (Note: garbling is also an auto-fail via AF-I1; this criterion scores the degree of legibility and accuracy beyond the binary auto-fail threshold.)
4. Brand palette colors are visible and consistent with STYLE BLOCK.
5. (double-weight) No dark background (unless DARK_OK=true).
6. (double-weight) No watermarks, logos not belonging to the client, no text not in the prompt.
7. (double-weight) People subject(s) present and appropriate (when the prompt specifies people).
8. Logo is present and correctly placed per STYLE BLOCK.
9. Composition follows the thirds-grid assignment in the prompt.
10. No visual artifacts: no blur, no color banding, no corrupted regions.
11. Facial expression MATCHES the slide's emotion: pull the MOOD element from slides_copy.md for the slide being scored. A smiling, relaxed, or triumphant expression on a pain slide fails; a worried or overwhelmed expression on a vision slide fails. Expression must match the declared mood/section.
12. Real-world setting matches the World Engine spec in the prompt (the setting stated in the prompt must appear in the image; a generic studio backdrop where a specific real-world scene was specified = fail).
13. Text edges sharp at 2K (headline and all text elements rendered with crisp, high-resolution edges; soft or anti-aliased text = fail).
14. Mood and energy of the image match the arc section (aspirational for hero slides, urgent for price drops, etc.).
15. (double-weight) Image grounding (P6): the rendered image depicts a CONCRETE moment from THIS client's method, book, message, or offer, not a generic interchangeable scene. The scored question is "does this image depict a concrete moment from THIS client's method?" An image that renders the specific method moment named in the GROUNDED_CONTENT brief scores high; an image that resolved to a generic stock-style scene scores low. (The binary floor is AF-I8; this criterion scores the degree of grounding above that floor.)

**Outputs:**
- working/qc/image_qc_report.json (per-image auto-fail codes, scores, classifications, and the deck-wide `representation_tally` table + verdict)
- Passed images moved to working/media-library/ (the deliverable folder)

**Hand to:** Media Librarian / GHL Updater (passes images to GHL) and Director (for Phase 6 kick-off)

**Failure mode:** If an image fails 3 attempts and still does not pass: escalate to the Director with the image, the prompt, and all 3 QC reports. The Director decides whether to present a best-available image to the owner or wait for manual intervention.

---

### SOP 9.4 -- Revision-Loop Control and Escalation

**When to run:** Any time a QC gate loops back for revision. This SOP governs the loop mechanics.

**Inputs:**
- QC report (from any phase)
- loop_count field from the report

**Steps:**
1. Read the loop_count from the current phase's QC report.
2. If loop_count = 1 or 2: send revision_instructions to the responsible specialist and re-trigger the QC gate after revision.
3. If loop_count = 3: send revision_instructions AND flag to the Director: "Third loop on [phase]. If the next revision fails, I will escalate."
4. If loop_count = 4 (threshold reached): stop looping. Send this exact message to the Director via a checkpoint file: "QC ESCALATION: [phase] has failed [N] loops. Persistent failure on criteria: [list]. Most recent failing slide/prompt/image: [ID]. QC reports are at [path]. Director must intervene."
5. Do not continue the run past an escalated gate until the Director resolves the issue.
6. Record the escalation in working/checkpoints/run_ledger.json under `escalations`.

**Outputs:**
- Revision instructions to the relevant specialist
- Escalation record in run_ledger.json (if loop_count = 4)

**Hand to:** Director (for escalation resolution)

**Failure mode:** This SOP is itself the failure-mode handler for all other QC gates. There is no failure mode of a failure-mode handler -- if this SOP cannot be executed (e.g., QC models are all down), escalate to the Director immediately with the error.

---

### SOP 9.5 -- Final Deck QC (Composed-Slide Asserts on the Rendered Deck)

**When to run:** Phase 6 -- after the PPTX Assembly Specialist has assembled the deck. This gate grades the ACTUAL `.pptx` (the deliverable), not the raw Phase 5 PNGs. It is the gap that let a colliding 5-box text stack ship on a prior deck: nobody owned text-vs-image collision, text-over-face, overlay overlap, or finished-artifact contrast on the COMPOSED slide. ROLE-09 owns it now.

**Render step (always first):** an agent cannot eyeball a PPTX directly. Render it to inspectable pages exactly per the master SOP Section 11.3:
```
soffice --headless --convert-to pdf <Deck>.pptx && pdftoppm -png -r 100 <Deck>.pdf working/qc/finalrender/page
```
(The Capacity & Reliability Engineer's soffice/python-pptx/poppler preflight must have passed before this gate runs; if the render toolchain is unavailable, escalate, do not skip the gate.)

**Inputs:**
- The assembled PPTX file (the deliverable)
- The PDF-rendered pages (PNG files at 100 DPI in working/qc/finalrender/)
- The PPTX shape geometry (every text box and overlay element's x / y / w / h, read from the PPTX XML via python-pptx)
- working/checkpoints/pptx_text_overlays.json (every native PPTX text-overlay element added at assembly per master Section 7.4)
- working/copy/slides_copy.md (for copy verification in the assembled deck)
- working/copy/presenter_notes.json (for speaker notes verification)
- working/brand/style_block.md + the captured REPRESENTATION_MIX (for the tally re-run)
- working/brief GROUNDED_CONTENT variable (for the grounding re-verification)

**Steps:**

1. **CODED ASSEMBLED-SLIDE ASSERTS (P3) -- run on EVERY composed slide, mechanically, before any score.** These are the auto-fails AF-F1 through AF-F4 (above). For each slide:
   a. **Collision assert (AF-F1):** read the bounding box (x, y, w, h) of every text box and every overlay element from the PPTX geometry; additionally detect focal faces in the rendered PNG. Compute pairwise intersection of all text/overlay boxes with each other, with the logo chip, and with detected faces. ANY intersection = AF-F1 collision auto-fail on that slide. A non-overlapping layout has zero intersecting boxes.
   b. **Per-overlay collision assert (AF-F4):** every element listed in pptx_text_overlays.json for this slide MUST have been run through the collision assert in 1a. If a slide carries an overlay element that was not collision-checked, that is AF-F4. You cannot pass a slide whose overlay you never checked.
   c. **Contrast assert (AF-F2):** for every text element, sample the rendered PNG pixels in the text element's bounding region and behind it; compute the WCAG-AA contrast ratio (text luminance vs background luminance). Below 4.5:1 for normal text (or below 3:1 for large text >= 24px equivalent) = AF-F2 contrast auto-fail.
   d. **Legibility assert (AF-F3):** verify every text element renders at or above the minimum legible size (as a fraction of slide height) and is not clipped, truncated, or running off the slide edge = AF-F3 if it fails.
   Record each slide's assert results (collision / contrast / legibility, pass or the failing element) in the report.

2. **Visual re-verification of the per-slide gates on the composed output.** For each rendered page (slide), verify:
   a. All 15 image QC criteria (including the AF-I1 through AF-I8 auto-fail layer) are still satisfied in the rendered output. Images from Phase 5 that passed should still pass here; if they do not, it indicates an assembly error.
   b. All 17 copy QC criteria are satisfied in the text overlays and any PPTX-native text elements.
   c. **Image-grounding re-verification (P6, BLOCKING):** AF-I8 / criterion i15 re-checked on the composed slide -- does each people-slide or scene-slide image still depict a concrete moment from THIS client's method? An ungrounded image that slipped through fails here.

3. **Deck-wide representation tally re-run (P5, AF-R2).** Re-run the step-5a tally on the FINAL assembled deck, because dropped, substituted, or re-cast slides can shift the distribution since Phase 5. If any captured REPRESENTATION_MIX group is outside +/- 10 percentage points = AF-R2 auto-fail on the deck. If people appear with no captured mix = AF-R3. Bidirectional (fails under-representation AND mono-casting); representation overrides skin-tone-quality.

4. **Structural-completeness checks (the governing intelligence: master Section 4.3 + the signature-presentation framework).** Verify, deck-wide, that the pitch and journey machinery is present in the assembled deck (each missing item routes a revision instruction to the responsible author):
   a. **Cost-versus-value beat present (GP-9):** the deck contains an explicit cost-of-inaction AND value-of-action beat.
   b. **Dual emotion + logic track (GP-4):** for each key offer beat ask "does this beat serve BOTH the emotional buyer and the logical justifier?" An offer section that is all-emotion or all-math fails.
   c. **Light pitch distributed, not back-loaded (GP-11):** the program is named and referenced inside the teaching sections from the first verse, not only in the offer section.
   d. **Care-first open (SP-CARE):** "does the open care about the audience before it talks about the presenter?" A deck that opens on credentials before caring about the audience fails the open check.
   e. **PSD teaching pattern (SP-PSD):** "is each teaching slide a Point / Story / Demo structure?"
   f. **Journey / SEE (SP-JOURNEY / SP-SEE):** the deck is a JOURNEY, not a fact list; and per slide ask "does this slide create a felt moment (a Significant Emotional Experience), or just inform?"
   g. **Old-to-new bridge (SP-OLDNEW):** each new idea is anchored to something the audience already knows.
   h. **Teach-themselves (SP-TEACH):** the deck invites the audience to reach the conclusion themselves ("you already know..."), conversational rather than lecturing.
   i. **Not over-taught (GP-10):** "appetizer, not dinner" -- the teaching proves value and creates desire without handing over the complete HOW (which lives in the offer).
   (Note: items a, c, e, g, h, i are also enforced upstream at copy QC c15; this is the deck-level confirmation that they survived into the assembled deck. SP-LING / SP-LOCAL and the Michael-J figure are operator-supplied placeholders; they are checked as "placeholder present, not fabricated," never invented.)

5. **Additional final-deck-specific checks:**
   a. Slide order matches arc_allocation.json exactly.
   b. Speaker notes are present in the PPTX for every slide per presenter_notes.json.
   c. No slides are missing (total count matches slide_count_final in mission_prd.json).
   d. No images are stretched, cropped, or misaligned in the PPTX layout.
   e. Font embedding: if PPTX-native text is used, fonts are embedded (verify by opening in a clean environment without the brand fonts installed -- text should still display correctly).
   f. Logo present on every slide (Lyric standard) when LOGO_ON_SLIDES = true.

6. **Emit the delivery pass-artifact.** Write `working/qc/final_deck_qc.json` (this exact filename is the delivery interlock token; see SOP 9.6). Structure:
   ```json
   {
     "gate": "Phase 6 final deck QC",
     "deck_file": "<Deck_Title>_v<N>.pptx",
     "pass": true,
     "score": 0.0,
     "auto_fails_triggered": [],
     "per_slide_asserts": [
       {"slide": N, "collision": "pass", "contrast": "pass", "legibility": "pass", "overlay_checked": true, "grounding": "pass"}
     ],
     "representation_tally": {"captured_mix": [], "deck_tally": [], "within_10pct": true, "verdict": "pass"},
     "structural_completeness": {"cost_vs_value": true, "emotion_and_logic": true, "light_pitch_distributed": true, "care_first_open": true, "psd": true, "journey_see": true, "old_to_new": true, "teach_themselves": true, "not_over_taught": true},
     "logo_on_every_slide": true,
     "loop_count": 0,
     "revision_instructions": []
   }
   ```
   `pass` is `true` ONLY when: zero AF-F1 through AF-F4 asserts failed, zero AF-R2/AF-R3, zero AF-I8 grounding failures, every structural-completeness item is true, AND the visual score is >= 8.5 with no single item below the 7.0 floor.

7. If pass: notify the Director that Phase 6 is complete and the deck is ready for delivery. The presence of `final_deck_qc.json` with `pass: true` is what unlocks delivery (SOP 9.6).
8. If fail: write `pass: false`, route specific revision instructions to the PPTX Assembly Specialist (collision/contrast/legibility/order/overlay), the Slide Image Creator (grounding, representation re-cast), or the Slide Copywriter (structural-completeness gaps), and increment loop_count.

**Outputs:**
- working/qc/final_deck_qc.json (the delivery pass-artifact -- this exact filename gates delivery)

**Hand to:** Director and Delivery Concierge (delivery may begin ONLY on `final_deck_qc.json` with `pass: true`)

**Failure mode:** If the PPTX file cannot be opened or rendered: escalate to the Director and PPTX Assembly Specialist immediately. Record the technical error in run_ledger.json. NEVER emit `final_deck_qc.json` with `pass: true` on a deck you could not render and assert -- an un-rendered deck is an unverified deck, and a done message without verified artifacts is a lie.

---

### SOP 9.6 -- The Delivery Interlock (no final pass without final_deck_qc.json)

**When to run:** Whenever delivery is requested (the Director or Delivery Concierge attempts to ship the deck).

**Inputs:**
- working/qc/final_deck_qc.json (the pass-artifact from SOP 9.5)

**Steps:**
1. Before any delivery action (copy to Downloads, GHL upload, email, Drive), confirm `working/qc/final_deck_qc.json` EXISTS on disk and its `pass` field is exactly `true`.
2. If the file is absent or `pass` is not `true`: HARD-STOP delivery and trigger AF-F5. Return: "Delivery blocked: final_deck_qc.json is absent or not PASS. The deck has not cleared final QC." This is a coded precondition, not a courtesy check. A prior deck generated 34 images and would have shipped with NONE of the QC artifacts on disk; this interlock makes that impossible.
3. Only when the artifact exists and is PASS does delivery proceed. (Delivery itself is owned by ROLE-06 / ROLE-13; ROLE-09 owns only the gate token that authorizes it.)

**Outputs:**
- A PASS/HARD-STOP verdict consumed by the Director / Delivery Concierge.

**Hand to:** Delivery Concierge (ROLE-13) / Media Librarian (ROLE-06) on PASS; Director on HARD-STOP.

**Failure mode:** If `final_deck_qc.json` is malformed or unreadable, treat it as absent (HARD-STOP). Never infer PASS from a missing or broken artifact.

---
