# SOPs Mirror -- QC Specialist (Presentations)

**Source:** presentations/qc-specialist-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

> Signature Presentations (Skill 51) cross-reference: for a deck with `deck_type: signature_presentation`, the AF-SP-* battery (AF-SP-8Q-MISSING / AF-SP-8Q-SPLIT / AF-SP-FRAME-UNSET / AF-SP-TYPE-MISMATCH / AF-SP-OFFER-UNDECLARED / AF-SP-SLIDE-FLOOR / AF-SP-PHASE-RANGE / AF-SP-PHASE-ORDER / AF-SP-PHASE-LABEL / AF-SP-IMG-SUGGESTION / AF-SP-CASESTUDY-CAP / AF-SP-TEACH-STEPS / AF-SP-HOOK / AF-SP-QUADRANT / AF-SP-P3-PITCH) is enforced fail-closed by the manifest phases P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE (`build_deck._chk_sp_intake` / `_chk_sp_structure` / `_chk_sp_no_pitch`, which DEFER for every non-signature deck). The semantic layer is owned by `qc-specialist-signature-presentations.md`. Treat any AF-SP-* code as a first-class auto-fail; non-signature decks are unaffected.

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### AUTO-FAIL RULE: an auto-fail condition forces FAIL for that item regardless of any average. Auto-fails are checked FIRST, before scoring.

#### Copy QC Auto-Fails (SOP 9.1)

The following conditions each independently force an immediate FAIL verdict on the affected slide. Check these before assigning any scores. Document every triggered auto-fail by criterion code in the QC report.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-C1 | Any em dash in any field of any slide. The em dash is the dead giveaway of unedited AI output. |
| AF-C2 | **(REPLACED 2026-06-14, density-floor overhaul.)** The OLD AF-C2 ("hook count below 7 = auto-fail") was the RETIRED historical FLOOR rule that PRODUCED the 40-slide footer-stamping. It is DELETED. The hook is now governed by the AF-HOOK ceiling battery below: the verbatim hook stands on 3-4 DEDICATED pure-typography A4 slides, total appearances ~4-5 max, NEVER 2 consecutive, never a footer on every slide (hook on MORE than 4 slides = fail; footer-stamped hook = fail; zero dedicated hook slides = fail). Over-stamping is the #1 defect; STRIP excess rather than pad. Do not re-introduce a hook floor. See universal-sops/presentation-slide-craft/SOP-SLIDE-03-HOOK-DOCTRINE.md. |
| AF-C3 | Any fabricated proof or statistic not traceable to intake.json or proof_audit.txt. A number not present in the intake or research brief = auto-fail on that slide. |
| AF-C4 | Any cross-slide numeric mismatch (e.g., stack total stated as $[STACK_TOTAL] on one slide and a different $[STACK_TOTAL] on another). Defer the Offer Strategist mechanics to SOP 9.3, but a FAIL there blocks this gate. The QC agent compiles all repeated numbers and diffs them; any mismatch auto-fails all slides carrying the inconsistent value. |
| AF-C5 | Headline over 9 words (mechanical word count; count is exact). |
| AF-C6 | Multi-idea slide. The operator's rule is "one big idea per slide; a multi-idea slide FAILS." A slide that makes more than one point is an automatic FAIL, not a deduction. Signal: more than 3 text blocks, or copy that needs a second point to make sense. Split it and re-QC. |
| AF-C7 | GRADUAL-drop choreography violation (the STACKED FAILURE). The price drops are NOT spread across the deck. This auto-fail has four INDIVIDUALLY CHECKABLE sub-conditions, mirroring the Offer and Price Strategist Gate 10; ANY ONE failing triggers AF-C7 on the offer/ladder slides, and each must be recorded by its sub-code in the report: (a) SPREAD -- fail if 2 or more drops fall within 2 slides of each other, OR all drops fall in the final 10% of the deck, OR the ANCHOR is treated as a drop instead of a value plant (drops must be spread at roughly ~47% / ~68% / ~87% of the deck); (b) EARNED + BUILT-UP -- fail if any drop has no earned reason, OR any drop has no emotional BUILDUP slide immediately before it; (c) ADDS value -- fail if any drop strips value to justify the lower price, OR neither the drop slide nor its immediate successor names new $-valued component added to the table (the red rule: the lower the price, the greater the value -- zero stripping). This sub-condition (c) now carries two ADDITIONAL checkable clauses, each independently failing and each recorded as it triggers: (c) ESCALATION -- the value added at each drop must be BIGGER and BETTER than the prior rung, not a token add. Fail if any `value_additions_by_drop` entry is a vague "and more" / an unnamed item, OR restates value already added at a prior rung (re-worded or re-added), OR carries only a trivial added_value so the cumulative `running_value_total` does not strictly increase by a non-trivial amount at that rung. The promises get bigger as the price falls; a drop that adds only a trivial, restated, or unnamed item fails (c) even though it technically "added" something. (For a non-monetary offer, escalation is judged on the substance and distinctness of the named bonus under the priceless frame, never a fabricated dollar figure; the running total is an internal pitch figure built from the client-stated stack, not an external-service constant, so the AF-SRC un-cited-external-number gate is not invoked and is not satisfied by inventing a number here.) (c) RISING-VALUE CURVE -- the cumulative running value total must be SHOWN climbing against the falling price so the inverse is seen, not merely implied. Fail if the running value total is not recorded at every rung in offer_stack.json (strictly increasing: tally_total < DROP1 total < DROP2 total < DROP3 total), OR if the drop slide (or its immediate successor) renders the struck/falling price with NO climbing value total beside it (the design-system price-typography SOP renders both; a struck price with no rising value total paired against it leaves the curve invisible). The running totals must reconcile to the dollar with the stack so no AF-C4 cross-slide numeric mismatch is introduced. (d) FINAL below the ladder -- fail if the FINAL real price does not sit strictly below every rung of the entire ladder. Quantify the value gap (total value vs FINAL price) on the slide immediately before the FINAL reveal; absence of the value-gap statement before FINAL is an AF-C7(a) buildup/spread failure. (Cross-checked against price_ladder.json, offer_stack.json, and the Offer and Price Strategist Gate 6 + Gate 10.) The RAVENOUS objective: a falling price beside a visibly climbing, escalating value is what makes the audience ravenous by the final price; a flat value beside a falling price is a mere discount and fails sub-condition (c). |
| AF-C8 | Over-stuffed slide (the TOTAL-WORDS ceiling, FIX-2). A slide can pass the 3-text-block test (AF-C6) while being mechanically over-stuffed. Count the TOTAL words across ALL on-slide text fields (kicker + headline + sub + every body beat + any tertiary line + any hook overlay). If the total exceeds 30 words on any single slide (the master copy ceiling: headline <= 9, sub <= 18, plus a small kicker), the slide auto-fails for density even if no single field individually overruns and even if the 3-block count is met. The hook-refrain overlay and the italic tertiary line are NOT default stack elements and, when present, count toward this total. |
| AF-C9 | Audience-facing forbidden content baked as ON-SLIDE text (FIX-3 battery; same severity tier as AF-C1 the em-dash ban -- auto-fail on sight). Any of the following appearing as visible slide copy in ANY field is an immediate FAIL on that slide: (1) PRESENTER NARRATION / what-to-say lines (the spoken script leaking onto the slide, e.g. "today I'm gonna show you why ..."); (2) the AI's OWN META-COMMENTARY or reasoning (any model self-talk, instruction-to-self, or build note rendered as copy); (3) IMAGE / SCENE DESCRIPTIONS used as visible headline or sub (e.g. "Same parent, same child. Two completely different rooms to grow up in." or "The senior engineer who hit every goal and still feels lost." -- a description of the picture is NOT slide copy); (4) TELEGRAPHING / STAGE-DIRECTION kickers ("one last proof before you decide", "before you decide", "this is not just a webinar", "hold on, the value is still climbing", "today I'm gonna show you why", or the mechanic leaking to the slide such as "the lower the price, the greater the value"); (5) the literal word "WEBINAR" on ANY audience-facing slide. Each is auto-fail on sight; record which of (1)-(5) triggered. |
| AF-C10 | Authored-narrative absent or ghostwritten. Every narrative slide MUST read in the owner's authentic first-person voice with at least one owner-specific detail (a named experience, decision, client, location, or before/after moment sourced from the intake interview). A narrative slide whose copy could be swapped into any business's deck with zero edits auto-fails. |
| AF-C11 | Voice-consistency break. After the first narrative slide establishes the owner's voice register, any subsequent slide that drops to generic corporate language or switches register without a documented reason auto-fails. |

#### Slide-Craft Auto-Fails (density-floor overhaul; source: universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md)

These are checked at Phase 1Q (copy stage, on slides_copy.md + arc_allocation.json + hook_package.json + audience_say_tags.json) and RE-VERIFIED on the rendered face at Phase 5/6. They were added because the existing 77 auto-fails did NOT catch the reference failure case: the hook stamped on 40 slides, speaker lines and pitch doctrine and image narration on the face, the word "webinar", bracket placeholders, a misspelled/mutated hook, and multi-idea slides ALL passed the old gate. Each row below is a BINARY trigger checked BEFORE scoring. A slide-level trigger fails that slide; a DECK-level trigger fails the whole gate. No averaging.

**AF-HOOK -- Hook ceiling, anti-footer, and integrity (the sacred refrain):**

| Code | Level | Auto-Fail Condition | Detection |
|------|-------|---------------------|-----------|
| AF-HOOK-1 | DECK | The verbatim hook (or any near-variant, fuzzy match >= 0.85) appears on MORE than 4 slides. Wallpaper. | Count slides where the canonical HOOK string from mission_prd.json appears in copy or rendered text; count > 4 fails the deck. |
| AF-HOOK-2 | slide | The hook appears in a footer / bottom-band / recurring-strip position on ANY slide. The hook is NEVER a footer. | Slide entry TEXT_ANCHOR carries the hook on a non-dedicated slide, OR the rendered image shows the hook in a bottom strip/band. |
| AF-HOOK-3 | DECK | Zero dedicated typography hook slides exist. The hook must have a home. | Count of slides whose one big idea IS the hook = 0. |
| AF-HOOK-4 | slide | The hook printed 2+ times on one slide (bold copy plus ghosted italic repeat, or headline plus footer). | Per-slide hook occurrence count >= 2. |
| AF-HOOK-5 | slide | The hook mutated, extended, reworded, or abbreviated (reference failure case s28 added "...and the results are significantly different."). | Character-exact compare of every occurrence against the canonical HOOK string in mission_prd.json; any difference fails. |
| AF-HOOK-6 | slide | The hook misspelled or garbled in a rendered image (reference failure case s23 "hclarity"). Render stage; also caught by AF-I1, double-flagged because the hook is sacred. | Spell/glyph check on the rendered hook line. |
| AF-HOOK-7 | slide | The dedicated signature-quote slide also carries the main control-vs-clarity hook (reference failure case s18). | The main hook present on the signature-quote slide. |

**AF-AUD -- Audience-facing only (six banned categories on the slide face):**

| Code | Level | Auto-Fail Condition | Detection |
|------|-------|---------------------|-----------|
| AF-AUD-1 | slide | A speaker SAY line on the face ("When you come into our program...", "Remember this number", "Stay right here", "Hold on", "This is the door"). | Line phrased as presenter speech (first-person guide-talk, narrates the moment) in slide copy or rendered text. Route to the Presenter's Speech. |
| AF-AUD-2 | slide | Internal pitch-doctrine printed as a caption ("The lower the price, the greater the value", "In the next breath, the real number", "Now let us talk about what you actually pay"). | Line restates a master Section 4.3 principle. Section 4.3 is build-logic, never slide copy. |
| AF-AUD-3 | slide | Image-narration caption (reference failure case s10 "Same parent, same child. Two completely different rooms..."; s5 "Step 1 . Step 2 . Step 3"). | Caption describes what the slide's own image brief already depicts. |
| AF-AUD-4 | slide | Meta-telegraphing, the word "webinar", or a technique self-label ("This Is Not Just A Webinar", "ONE LAST PROOF BEFORE YOU DECIDE", "An intrigue gap, on purpose", "Hold onto this line"). | Case-insensitive literal match on "webinar"; plus matches on "this is not just", "one last proof", "an intrigue gap", "hold onto this line", and other format/technique announcements. |
| AF-AUD-5 | slide | A credential / justification dump on the face ([Co-Founder Name]-licensed-counselor, [Founder Name]-years-in-recruitment paragraphs). | Resume/credential paragraph ("licensed", "clinical", "years in", "certified") as body copy. Quote slides carry the NAME ONLY (master rule 1). |
| AF-AUD-6 / AF-PLACEHOLDER | slide (blocks FINAL) | Any bracket/build token on a RENDERED slide (reference failure case s28/30/35/38/40/42 "[INSERT REAL RESULT - owner to confirm]", "[CLIENT WIN - owner to confirm]"). | Render stage only. Regex `\[[^\]]*\]` plus case-insensitive substrings "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", "pending". At COPY stage a `[CLIENT TO SUPPLY]` placeholder is permitted; it must be resolved or the slide pulled before render. ANY match on a rendered image fails that slide and BLOCKS FINAL STATUS. |

**AF-OBI -- One big idea (slide-level; the rule above all rules):**

| Code | Level | Auto-Fail Condition | Detection |
|------|-------|---------------------|-----------|
| AF-OBI-1 | slide | More than 3 text blocks on a slide. | Count HEADLINE + SUB-COPY + SUPPORTING plus any rendered text block not among those three; > 3 fails. |
| AF-OBI-2 | slide | Headline over 9 words (two ideas). | Exact word count of HEADLINE. (Overlaps AF-C5; kept for completeness of the OBI battery.) |
| AF-OBI-3 | slide | Two or more core ideas on one slide (diagnosis+method, gap+reframe, two assertions). Reference failure case s8 = gap + reframe. | QC agent identifies distinct claim count; >= 2 fails. |
| AF-OBI-4 | slide | A full value trio on one slide (reference failure case s26 = all three Cs on one slide). | Three parallel named values co-present. Build 4 slides (one per value + a formula slide). |
| AF-OBI-5 | slide | A bulleted list of 2+ pains. | Multiple distinct pain statements as list items. Each pain is its own slide with its own image (master rule 9). |
| AF-OBI-6 | slide (render) | A comparison table with more than 2 contrast rows (reference failure case s28 = 8-row control-vs-clarity table). | Rendered contrast-row count > 2. Reduce to the single sharpest contrast or move the table to the Presenter's Guide. |

#### Density / Pacing Auto-Fails (density-floor overhaul; DECK-level; source: universal-sops/presentation-slide-craft/SOP-SLIDE-04-DECK-DENSITY-AND-PACING.md)

These are DECK-level and evaluated against arc_allocation.json and slide order at Phase 1Q and re-verified against the final slide order at Phase 6. They are auto-fails, not scored, because the crammed offer (price beats 2 and 3 slides apart, no stack, no promises, no re-pitch) was the root of the reference failure case 2/10 pitch. Gold-standard numbers from the proven 75-slide reference run: ladder at s24/35/51/65/73, gaps 11/16/14/8, Wall of Wins 5 slides before offer, re-pitch s74-75.

| Code | Level | Auto-Fail Condition | Detection |
|------|-------|---------------------|-----------|
| AF-DEN-1 | DECK | Any two adjacent price beats fewer than 8 slides apart. | Read LADDER tags (ANCHOR/DROP1/DROP2/DROP3/FINAL) in slide order; any adjacent gap < 8 fails. Computed against the FULL deck, never the offer window only. |
| AF-DEN-2 | DECK | Anchor outside the 25-to-45% depth band (reference failure case anchor was at 71%). | Anchor slide position / total slides outside 0.25-0.45 fails. |
| AF-DEN-3 | DECK | A DROP with no BUILDUP slide immediately before it. | For each DROP, the immediately preceding slide must be tagged BUILDUP. |
| AF-DEN-4 | DECK | No itemized value-stack slide before Drop 1. | A slide tagged as the value stack (itemized components, each with its value, summed to a total) must exist before the first DROP. |
| AF-DEN-5 | DECK | No promises beat before the anchor. | A promises slide must exist before the ANCHOR (people buy promises, not products). |
| AF-DEN-6 | DECK | Wall of Wins not 4-6 slides before the offer (reference failure case was 2-3; the gold-standard reference deck is 5). | Wall-of-Wins slide position vs final-offer slide position outside 4-6 fails. |
| AF-DEN-7 | DECK | No 4-to-7-slide re-pitch block after the FINAL price (reference failure case closed on a plain thank-you). | After FINAL, 4 to 7 slides recapping stack + promises + urgency must exist before the send-off. |
| AF-DEN-8 | DECK | A section below its minimum slide count. | Per-SECTION slide count vs the SOP-SLIDE-04 floors (hook >=5, authority >=4, teaching >=18, proof >=4, offer >=14, re-pitch+close >=5). |

#### Anti-Compression / Source-Coverage Auto-Fail (DECK-level)

This is a binary DECK-level auto-fail. It vetoes the whole gate; no averaging.

| Code | Level | Auto-Fail Condition | Detection |
|------|-------|---------------------|-----------|
| AF-COVERAGE-1 | DECK | `final_slide_count < source_slide_count`. The system must NEVER output fewer slides than the client's source deck (Mode B is ADD-only; never delete a client slide to hit a duration cap). Mode A (`source_slide_count == 0`) always passes. | Stage 1Q: compare arc_allocation.json total against `mission_prd.source_slide_count`. Phase 6: compare the assembled deck page count against `mission_prd.source_slide_count`. Either stage failing fails the deck. |

Message on trigger: `AF-COVERAGE-1: output deck has {final} slides; client source deck had {source}. The system must NEVER output fewer slides than the source (Mode B is ADD-only). Add {source-final} slides; never delete a client slide to hit a duration cap.`

#### Prompt QC Auto-Fails (SOP 9.2)

Check these before scoring. Each independently forces FAIL on the affected prompt.

**Density-floor-overhaul additions (design-system + image-library clusters):**

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-P9 | LOGO_ON_SLIDES = true but the prompt does NOT pass LOGO_URL via `input.input_urls` (the logo is being drawn text-to-image). The image-to-image path is mandatory for the logo. Source: SOP-IMG-01 check 1, presentation-design-system/05-SOP-logo-consistency.md. |
| AF-P10 | A reference URL is present in `input_urls` but not NAMED in order in the prompt ("the first reference is the logo, the second is the founder"). Source: SOP-IMG-01 check 2. |
| AF-P11 | The logo reference sentence is missing the "place, do not redraw, recolor, or restyle it" anti-mutation instruction. Source: SOP-IMG-01 check 3. |
| AF-P12 | A STYLE-reference frame is in `input_urls` but the verbatim style-reference-only directive is missing, OR that directive is wrongly applied to the logo or a face. Source: SOP-IMG-01 checks 4-5. |
| AF-P13 | A slide's prompt does not declare its assigned archetype (A1-A5) on line 1, OR does not state its word-block position in thirds language. Source: presentation-design-system/04-SOP-variable-layout-anti-template.md. |
| AF-P14 | A slide's prompt names no weight-ladder role for its text (just "bold text"), OR a price-ladder slide's prompt omits the gold-gradient/glow/strike price-typography treatment, OR an A4/A3 hero slide does not set its hero element in BLACK weight at hero scale. Source: presentation-design-system/02-SOP-creative-typography-guide.md, the Typography Architect treatment table. |
| AF-P15 | A dedicated hook-anchor slide's prompt renders the hook as a footer band, carries a competing photographic subject at normal opacity, or is not pure-typography (hook line large over a low-opacity image). Source: presentation-design-system/03-SOP-pure-typography-hook-slides.md. |

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-P1 | Character count under the hard floor of 9000 (Check 0: count mechanically and RECORD the exact number in the report). A prompt under 9000 chars is starved of the per-line spelling-lock, the full paired negative block, the image-to-image logo language, and the complete anatomy direction; it fails unless it carries a documented reason for a near-empty transition slide. |
| AF-P2 | Character count over 18000. The LONG-tier budget is 18000 (a 2000-char safety margin below the GPT-Image 2 ceiling of 20000 on both endpoints, MODEL-SPECS). Over 18000 = auto-fail. (Raised from 15000 in v12.7.1: the old short cap starved prompts of the specificity that prevents the forensic defects.) |
| AF-P3 | Headline not verbatim to slides_copy.md HEADLINE field (any paraphrase, any changed word = auto-fail). |
| AF-P4 | Missing 16:9 or 2K (either absent = auto-fail). |
| AF-P5 | Dark background language present without DARK_OK = true. |
| AF-P6 | Missing thirds/zone language (explicit thirds placement for headline, people, and objects is required; "centered" alone is not thirds language). |
| AF-P7 | People are present in the slide spec but the prompt is missing any of: hair description, clothing description, or facial expression description. All three are required when people appear. |
| AF-P8 | Missing the closing negative block (element 15). Every prompt must end with the mandatory paired NEGATIVE-PROMPT BLOCK per slide-image-creator SOP 9.8. A prompt with no closing negative block, or one carrying only the old thin one-line AVOID phrase instead of the full eight-class paired block, = auto-fail. (The depth of the block is then checked by AF-P13.) |
| AF-P9 | Image-grounding failure (P6, BLOCKING): the prompt for a people-slide or scene-slide does NOT depict a concrete moment from THIS client's method, book, message, or offer (the GROUNDED_CONTENT variable carried in the brief). A prompt describing a generic, interchangeable scene that could belong to any business, when the brief named a specific grounded moment, = auto-fail. ("A confident woman at a desk" is generic; "the founder reviewing the {{CLIENT_METHOD}} 5-step intake dashboard at the kitchen table at 6am" is grounded.) |
| AF-P10 | Basic / default / undesigned TYPOGRAPHY (the TYPOGRAPHY LAW, brand-steward SOP 9.4 + slide-image-creator SOP 9.6 Part A). Any of the following on a prompt is an auto-fail: it names a basic or platform-default typeface (Calibri, Arial, Times, "a clean sans-serif," or any system default); OR it names a font with NO per-line weight and large pt size (e.g. "Montserrat Bold" with no size); OR it does not honor the one-family weight map (headlines and giant numbers in the heaviest weight, e.g. Montserrat Black; subs and body beats in ExtraBold; gold all-caps kicker labels in Bold); OR it lacks the size scale (giant numbers 110-150pt, hero headline 62-86pt, kicker ~13pt); OR it has no designed hierarchy (no dominating charcoal Black 2-line headline, no size contrast). Designed typography is mandatory; basic or default fonts are the documented failure mode. |
| AF-P11 | Standalone-art failure (the core design principle, slide-image-creator SOP 9.6 Part B). The prompt produces "just a background with text": a generic background image with copy dropped on top, with no intentional art direction, no clear hero subject, no composition, and the typography pasted on rather than composed INTO the image. A prompt whose result would only read as part of a sequence (it does not stand alone as a deliberate, gallery-grade art piece with its own felt emotional beat) = auto-fail. Each slide must be a finished standalone piece of art. |
| AF-P12 | Hook-overlay over-stamping (the prompt-side hook ceiling, FIX-1). A prompt carries a hook-refrain overlay / hook-footer / "3b. HOOK REFRAIN" device on a slide whose corresponding `hook_variants.json` entry has `hook: false` (i.e. the slide is NOT a scheduled hook beat). The hook refrain is a CONDITIONAL device fired ONLY on the scheduled hook beats sourced from `hook_variants.json`; a prompt that stamps the hook as a fixed device on a non-scheduled slide = auto-fail. The literal templating phrase "present on every slide" or "sung the whole way through" appearing in any prompt as a render instruction is itself an AF-P12 auto-fail (that wording is the documented root cause of the hook-on-every-slide defect). |
| AF-P13 | NEGATIVE BLOCK PRESENT AND PAIRED (FIX-13, the pre-generation negative-prompt gate; slide-image-creator SOP 9.8). The dedicated final-paragraph negative block must exist and cover ALL EIGHT defect classes, each as an imperative "Do not ..." sentence, and EACH critical negative must have a positive twin stated earlier in the prompt. The eight classes are: (1) garbled / misspelled text, (2) logo mutation / invented mark, (3) placeholder / bracket tokens, (4) image narration / presenter / meta / the word "webinar", (5) anatomical artifacts (extra fingers, warped faces), (6) background competing with text, (7) demographic / skin-tone fidelity (no off-mix demographic, no lightened / ashy deep skin, no mono-cast), (8) the carried-forward universal baseline (watermark, em dash, dark background, clipart / emoji, text within 5% of edge, text over face, basic / default font). Missing the block, missing ANY of the eight classes, any negative with no positive twin earlier in the prompt, or a negative that contradicts a positive instruction (no-contradiction audit, NEGATIVE-PROMPTING-SOP Section 4) = auto-fail. This supersedes the bare element-15 AVOID check; because GPT-Image 2 has no negative-prompt field (MODEL-SPECS), the block is INLINE imperative text and the skill-45 "10 strongest only" cap is LIFTED for this long-budget path (all eight classes are mandatory). |
| AF-P14 | SPELLING-LOCK PRESENT (FIX-13; slide-image-creator element 3). EVERY verbatim text string in the prompt (headline, sub-headline, supporting line, kicker label, price, struck price, and any other quoted on-slide string) must carry the letter-for-letter spelling-lock instruction ("Render this exact string, letter-for-letter, correctly spelled ... Do not alter, misspell, duplicate ... any character"). A verbatim string present in the prompt with no spelling-lock sentence = auto-fail. This is the pre-generation guard against the garbled-text defect ("hclarity", "GRABLED BRANDCO"); the render-side re-verify is AF-I1 + AF-F9. |
| AF-P15 | LOGO IMAGE-TO-IMAGE DECLARED (FIX-13; SOP-IMG-01 check 1/3 + SOP-DESIGN-04, enforced at prompt time). On any slide where LOGO_ON_SLIDES = true, the prompt must declare image-to-image mode (`gpt-image-2-image-to-image`) with the locked LOGO_URL as the FIRST reference in `input_urls`, AND carry the verbatim "place, do not redraw" logo sentence, AND carry the negative twin "do not invent / redesign any mark." A prompt that describes the logo in words only (no reference image), or that declares text-to-image (Mode A) on a logo slide, = auto-fail. This is the write-time guard that pairs with the render-time logo-identity-drift auto-fail AF-F7; both are required (a deck can pass AF-P15 and still fail AF-F7 if the render drifts). |
| AF-P16 | NO PLACEHOLDER / BRACKET TOKEN IN THE PROMPT (FIX-13; the pre-generation placeholder gate). Scan the prompt body for any text intended as RENDERED on-slide copy that matches a bracketed token `[...]`, or a case-insensitive substring of "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", or "pending". Any such token presented as copy to render = auto-fail at the prompt stage, so it can never reach the render (this pre-empts the render-side blanket ban AF-F10). A spelling-lock or negative-block sentence that NAMES a banned token only to forbid it (e.g. the block's own "Do not render any bracketed token ...") is permitted; the ban is on a token presented as text to render. A copy-stage `[CLIENT WIN - owner to confirm]` placeholder must have been resolved with the client's real interview-sourced content (or the slide pulled) BEFORE the prompt is written; if a prompt still carries one, fail it and flag the Director that the copy gate let an unresolved placeholder reach Phase 2. |

#### Image QC Auto-Fails (SOP 9.3)

Check these before scoring. Each independently forces FAIL on the affected image.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-I1 | ANY misspelling, duplicated word, or garbled glyph in ANY rendered text anywhere on the slide. This applies to every word on the slide, not just the headline -- inspect EVERY text element (headline, sub, supporting line, kicker, price, struck price, any logo wordmark). This is the render-side re-verify of the prompt-side spelling-lock (AF-P14) and the negative-block class 1; the OCR-readback diff AF-F9 confirms it pixel-by-pixel against the intended copy. A string that garbles is fixed by the re-prompt/re-seed loop then human escalation (Decision 5C); the native-text overlay path is ELIMINATED (its presence is AF-OVERLAY-DELIVERED). The only image-composite exception is the real-logo IMAGE composited via the PIL path (SOP-IMG-05), which is not native text. |
| AF-I2 | Any anatomical deformity: malformed or fused hands, extra or missing fingers, distorted or warped faces, mismatched eyes, distorted teeth, plastic over-smoothed skin, warped or severed limbs, unnatural proportions. This is the render-side re-verify of negative-block class 5 (anatomical artifacts). |
| AF-I3 | Wrong aspect ratio (must be 16:9; anything else = auto-fail). |
| AF-I4 | Missing or mangled logo when LOGO_ON_SLIDES = true (logo absent, illegible, distorted, recolored, clipped, incorrectly placed, **OR a DIFFERENT mark than the locked LOGO_URL asset** = auto-fail). (Extended for the density-floor overhaul: "differs from the locked asset" is now part of AF-I4.) |
| AF-I5 | Dark background without DARK_OK = true. |
| AF-I6 | Emoji or clipart glyphs rendered anywhere in the image. Premium decks use photography and typography only. |
| AF-I7 | An em dash rendered in slide text. |
| AF-I8 | Image-grounding failure (P6, BLOCKING): a people-slide or scene-slide image that does NOT depict a concrete moment from THIS client's method, book, message, or offer (the GROUNDED_CONTENT variable). A generic stock-style scene that could belong to any business when the brief named a specific grounded moment = auto-fail. Grounding is scored at prompt QC (AF-P9) and re-verified here against the rendered image. |
| AF-I9 | Basic / default / undesigned TYPOGRAPHY rendered in the image (the TYPOGRAPHY LAW). The rendered text reads as a basic or default font (Calibri/Arial/Times/system-default look) rather than the designed weight-mapped system; OR there is no type hierarchy (no dominating heavy-weight charcoal headline, no giant number at 1.5x-3x surrounding text where the brief calls for one, no gold caps kicker); OR a headline renders in pure black on the base instead of charcoal. The image must show DESIGNED typography composed into the picture. This is the prompt-side AF-P10 re-verified against the rendered image. |
| AF-I10 | Standalone-art failure rendered in the image (the core design principle). The rendered slide is "just a background with text": a generic background with copy dropped on top, no intentional art direction, no clear hero subject, the typography pasted on rather than composed into the image, and no felt emotional beat. Pull the slide out alone: if it does not read as a deliberate, gallery-grade piece of visual art on its own, it auto-fails. This is the prompt-side AF-P11 re-verified against the rendered image. |
| AF-I11 | Real-image-present failure. Every non-pure-typography slide MUST include a real generated raster image at 2K resolution minimum (1920 x 1080 px or larger) as its primary visual element. A slide that reaches image QC with only text overlaid on a flat color background, a placeholder graphic, or no image file on disk fails AF-I11. The generated raster must exist at `working/renders/slide-NN.png` at the correct resolution; a missing file or a file under 1920px in either dimension is AF-I11 regardless of cause. |
| AF-I12 | Typography overuse violation (layout monotony). Any font family appearing as the display/headline typeface on MORE THAN 60% of all slides in the deck fails AF-I12. The deck-wide headline typeface must rotate through the designed weight hierarchy defined in type_layout_system.md. Count is mechanical; threshold is 60% of slide_count_final. |
| AF-I13 | Body-text point-size violation. Any body/sub-headline text element rendered below 18pt in the composed slide auto-fails AF-I13. The 18pt minimum is the absolute floor defined in type_layout_system.md (`min_body_pt: 18`). |

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
| AF-F6 | Image-position SAMENESS (the layout-variety assert, FIX-9). Record each slide's image zone (left / right / top / bottom / full-bleed / none) from the composed slide. MORE THAN 2 CONSECUTIVE slides sharing the same image position = auto-fail (a deck that is photo-right / type-left on every slide is the cookie-cutter failure this assert exists to stop). This mirrors the TEXT_ANCHOR variation rule (copy QC c16) on the image axis. Hook slides must be type-driven (no image, or a <=15% opacity background image with large designed type over it); a hook slide carrying a full-strength image fails. |
| AF-F7 | Logo IDENTITY drift (FIX-10; authorities sops/SOP-IMG-01-KIE-CALL-MECHANICS.md check 9 and sops/SOP-DESIGN-04-LOGO-CONSISTENCY.md). Where LOGO_ON_SLIDES = true, the logo must be visually IDENTICAL across all slides -- same asset, same crop, same color, same scale, same chip, same corner -- and identical to the locked LOGO_URL reference asset. Sample N slides, isolate the logo region on each, and diff each against the locked LOGO_URL and against each other; ANY drift (a different lockup, a re-rendered or re-designed mark, a different monogram / leaf / sprout / tree / mountain / roundel variant on one slide, a different scale/crop/color) = auto-fail the deck (the forensic reference deck four-plus-marks defect). This read-time identity guard pairs with the write-time AF-P15 (the prompt declared image-to-image with LOGO_URL as first reference + "place, do not redraw"); BOTH are required, a deck can pass AF-P15 and still fail AF-F7 if the render drifts. After two failed image-to-image attempts the REAL logo IMAGE is composited onto the slide PNG via the PIL image-composite path (SOP-IMG-05), baked into the image before assembly — an IMAGE composite of the real mark, NOT a native PPTX text/element overlay (native overlays are eliminated, Decision 5C; a pptx_text_overlays.json or any native on-slide text run is AF-OVERLAY-DELIVERED). |
| AF-F8 | Offer-slide price mismatch (FIX-10). The price shown on the offer / CTA slide must EQUAL FINAL_PRICE from price_ladder.json / intake.json. Any other number on the offer slide (the $544-where-it-should-be-$97 class of error) = auto-fail. This is the explicit offer-slide==FINAL_PRICE assert layered on top of the cross-slide numeric-consistency gate (criterion 14 + AF-C4). |
| AF-F9 | OCR-readback mismatch (FIX-11). Read the rendered text back from each composed-slide PNG (OCR) and diff it against the INTENDED copy string from the prompt / slides_copy.md for that slide. OCR readback runs on EVERY rendered text element on the slide -- headline, sub-headline, every supporting line, kicker label, price, struck price, and any logo wordmark -- NOT just the headline; each element is diffed independently against its intended string. Any mismatch -- a baked typo (e.g. a garbled word where "clarity" renders as "hclarity" or a brand name as "GRABLED BRANDCO"), a garble, a missing connector (e.g. "A real [OFFER NAME] outcome  your turn next"), or a leaked scene/stage-direction description that does not match the intended copy -- = auto-fail; the slide is re-rendered. The current QC trusts the prompt, not the pixels; this gate trusts the pixels. This is the render-side closing of the loop opened by the prompt-side spelling-lock (AF-P14) and confirmed alongside AF-I1. |
| AF-F10 | Build-token / placeholder rendered on the slide face (FIX-12, the slide-craft Audience-Facing battery RULE 3 / AF-PLACEHOLDER, reconciled). On the OCR text from each composed-slide PNG, run a blanket scan: any bracketed token matching the pattern `[...]` (an open bracket, any text, a close bracket), OR a case-insensitive substring match on "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", or "pending", rendered ON the slide face = auto-fail, and it BLOCKS FINAL STATUS on its own. This is an UNCONDITIONAL ban distinct from AF-F9 (which fires only as a copy-vs-pixel diff): even if the prompt itself carried the bracket token, compositing it is the single most embarrassing tell (the forensic reference deck shipped raw "[CLIENT WIN - owner to confirm]" and "[INSERT REAL RESULT - owner to confirm]" on rendered slides). A `[CLIENT TO SUPPLY]` / `[CLIENT WIN - owner to confirm]` placeholder is permitted at COPY stage only; it must be resolved with the client's real interview-sourced content, or the slide pulled, before render. A bracket token must never reach a rendered image. See sops/SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md and sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md. |
| AF-F11 | Portable-document export missing or mismatched at delivery (the system-wide deck-PDF rule). The PPTX Assembly Specialist must emit a portable-document-format (`.pdf`) export ALONGSIDE the `.pptx` for EVERY deck, so a recipient without PowerPoint can open it. Auto-fail when, at Phase 6, ANY holds: the `.pdf` delivery file is absent or empty next to the assembled `.pptx`; render_log.json does not record `pdf_is_delivery_output: true`; or the `.pdf` page count does not equal the `.pptx` slide count and slide_count_final. The QC already renders the `.pptx` to PDF for inspection; this assert additionally confirms the export was produced AND retained as a delivery output by assembly. BLOCKS FINAL STATUS; routes a revision to the PPTX Assembly Specialist (its SOP 9.2 + Gate 6). |
| AF-F12 | Body/sub-headline text below the 18pt minimum floor. On the COMPOSED slide, any text element classified as body copy or sub-headline that renders below 18pt equivalent auto-fails. This is the final-deck enforcement of the Typography Architect's `min_body_pt: 18` machine-readable token, paired with AF-I13 at image QC. |
| AF-F13 | Type-scale step count out of range. `working/typography/type_layout_system.md` MUST declare exactly 4 or 5 distinct type-scale steps via the `type_scale_steps` machine-readable token. A missing file, missing token, or count outside {4, 5} auto-fails and blocks FINAL STATUS. Route to Typography Architect. |
| AF-F14 | Section-divider visual identity collision. Section-divider slides must use a distinct visual identity from adjacent content slides. Any section-divider whose rendered PNG background region scores above 0.85 SSIM against the immediately adjacent content slide's background = AF-F14. Route to Typography Architect. |

#### Design-Craft Auto-Fails (checked at Phase 3 Prompt QC and Phase 5 Image QC)

These conditions each independently force an immediate FAIL verdict on the affected slide. They enforce the PROFESSIONAL DESIGN-CRAFT standard required of a PROFESSIONALLY TRAINED ADOBE GRAPHIC ARTIST AND ART DIRECTOR WITH 30 YEARS OF EXPERIENCE. Check these at Phase 3 (against the prompt) and re-verify at Phase 5 (against the rendered image).

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-DC1 | Text over a face: any text element (headline, sub, kicker, body beat, hook overlay) lands directly over a human face in the image. Text over a face is the most common amateur composition error. Every prompt must specify face position in a named thirds zone that does not intersect the text zone. |
| AF-DC2 | Flat single layer: the image has no foreground / midground / background separation -- a single flat plane with subject and environment merging together. Checked at Phase 5 against the rendered image. Every prompt must specify all three depth layers (IMAGE LAYERING AND DEPTH rule, slide-image-creator SOP 9.2). |
| AF-DC3 | Ignored thirds: the prompt does not declare which third holds the headline, which holds the primary subject, and which holds supporting elements. "Centered" alone without a thirds declaration is also AF-DC3. Required by the THIRDS SYSTEM rule (slide-image-creator SOP 9.2). |
| AF-DC4 | Clashing or uncontrasted colors: any headline-on-background combination in the rendered image that fails WCAG AA (below 4.5:1 for normal text, below 3:1 for large text at 18pt+ regular or 14pt+ bold). Also flagged if visually clashing complementary colors are placed adjacent without sufficient separation or hierarchy (e.g., full-saturation raspberry directly adjacent to full-saturation gold with no neutral buffer). |
| AF-DC5 | Ungraded inconsistent deck: across the deck as a whole, some images are visibly warm-toned and others are visibly cool-toned, with no unified color-grading profile. Each image must feel as if it was shot in the same light. An inconsistently graded deck fails the color-grading dimension regardless of individual slide scores. |
| AF-DC6 | Font in unsafe zone: text placed within 5% of any slide edge (the bleed/margin zone), or any text element overlapping a human face. Both are composition defects independent of content quality. |
| AF-DC7 | Prompt missing all three design-craft element groups (Phase 3 only): the prompt omits all of the following groups: (a) a thirds-zone assignment for headline, subject, and supporting elements; (b) depth-layer specification (foreground / midground / background); (c) a COLOR GRADING block comment. A prompt missing all three groups has not been art-directed to the required standard and is a Phase 3 auto-fail. Missing one or two groups triggers a scored deduction (p-DC dimension), not an outright auto-fail, unless the missing group is also covered by a more specific auto-fail above. |

#### Vision-Gate and Pixel-Level Enforcement Auto-Fails (SOP 9.7 -- the v11 gate overhaul)

These auto-fails implement the gate-overhaul doctrine (SOP fix plan Section 0 and 1-13): every rule lands in BOTH a producing SOP AND a hard auto-fail. The codes below are the hard auto-fail half of each rule. They extend (never duplicate) the existing AF-C, AF-P, AF-I, AF-F, AF-R, and AF-DC namespaces. Run ALL of these checks before the scored layer.

**AF-GATE-0 (meta auto-fail -- the entire QC run fails if images are not opened and logged):** The gate input for Phase 5 and Phase 6 is the RENDERED PNG SET plus the final deliverable bundle, NOT the brief text and NOT the assembly script. If `QC-FINAL.md` does not record, per slide, (a) the PNG file path opened, (b) the OCR text extracted, and (c) the vision-model verdict, the ENTIRE QC run auto-fails and the deck cannot be marked done. No image opened = no PASS. A text-only "PASS" without evidence of image inspection is itself an AF-GATE-0 auto-fail. The "assembly-only (no generation)" run path is eliminated; Phase 5 is always a VISION gate.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-LOGO | Logo identity drift or mutation on any slide. After the mandatory PIL composite (SOP-IMG-05-PIL-LOGO-COMPOSITE.md), run an OCR + SSIM comparison of the logo chip region of every rendered slide against the locked `LOGO_URL` reference asset. ANY of the following triggers AF-LOGO on the affected slide, which fails the deck: (a) wordmark mismatch -- OCR reads a different string (e.g., "Hlowth", "Gfowth", "Now/Flow/How", or any garbled variant) instead of the exact client wordmark; (b) invented roundel, glyph, or mark not present in LOGO_URL; (c) color, scale, or crop drift below SSIM >= 0.97 on the chip region against LOGO_URL; (d) logo absent from a slide where LOGO_ON_SLIDES = true; (e) PIL composite not logged for the slide in `logo_composite_log.json`. One failed slide fails the deck. This code closes the loop opened by AF-P15 (prompt-side) and AF-F7 (composed-slide identity). |
| AF-CAST | Deck-wide casting / audience-composition violation. Run after Phase 5 image QC completes for the deck. (a) Face-detect and classify every people-slide by demographic group. (b) Compute the deck-wide distribution and compare against `audience_composition.groups` in intake.json. (c) If the distribution of ANY captured group is outside +/- 10 percentage points of its intake percentage, auto-fail the deck (re-cast the deficient or over-represented slides). (d) ALL-ONE-RACE auto-fail: if the deck-wide cast is 90% or more a single demographic when the intake mix specifies two or more groups at significant percentages (>= 10%), trigger AF-CAST immediately regardless of the +/- 10 point threshold -- the all-one-race failure is always a hard fail. (e) INVERTED DEFAULT auto-fail: if the intake says the dominant group is X+Y but the rendered deck is dominated by Z, trigger AF-CAST. (f) If `audience_composition.captured` is false or the field is absent but people appear in the deck, trigger AF-CAST (and AF-R3). The QC tally is BIDIRECTIONAL (fails both under-representation and mono-casting) and is run twice: once on generated images (Phase 5) and once on the final assembled deck (Phase 6). |
| AF-FACE-MOOD | Expression mismatch on a positive beat. On every people-slide where the slide's `MOOD` field or arc section is positive (vision, future-pace, celebration, transformation, close), the rendered face must express warmth, brightness, or hopefulness. A dour, flat, blank, or pained expression on a positive-beat slide auto-fails the slide. Verified against the rendered PNG via the face-classifier. Pairs with QC criterion i11 (expression matches arc section, already wired) and AF-I (image QC). |
| AF-GRAD | Gradient or glow on any type region. Run the gradient / glow detector on all type regions of every rendered slide. ANY of the following triggers AF-GRAD on the slide: (a) a gradient FILL on a typographic element (a gold-to-gold gradient, a metallic gradient, a color-to-transparent gradient applied to text glyphs); (b) a radial glow, bloom, or soft luminance emanating from a text element; (c) the phrase "liquid-gold gradient", "metallic warm gold", or "soft warm radial glow" in the prompt AND a corresponding visual effect detected in the image. Flat solid-color type passes. A scrim gradient behind the type (on the image layer, not the text layer) passes. AF-GRAD is the read-time enforcement of the gradient ban in SOP-IMG-05-PIL-LOGO-COMPOSITE.md and in slide-image-creator-sops.md SOP 9.6 Part A (gradient strip). |
| AF-TYPE | Weak, small, generic, or low-effort typography. On every slide, the rendered hero type must clear ALL of the following. Any single failure triggers AF-TYPE: (a) the hero headline is NOT below the SOP pt-size floor (62pt minimum for a hero headline at 2K resolution -- check by measuring the rendered text height in pixels against slide height); (b) the hero type does NOT occupy less than the SOP zone minimum (the headline must dominate its assigned zone -- a headline that floats small in a large zone fails); (c) the rendered font is NOT a basic, default, or system font (no Calibri, Arial, Times, or any font with no designed hierarchy); (d) there is a visible weight hierarchy (the headline is rendered in a heavier weight than the subhead, the kicker is rendered in a smaller weight than the headline). Criteria (a)-(d) are verified on the rendered PNG via OCR and visual inspection. |
| AF-TELEGRAPH | Presenter-voice or telegraphing content on the slide face. OCR the face copy of every slide and run a banned-pattern matcher. Any of the following present as VISIBLE SLIDE COPY (not in presenter notes) auto-fails the slide: (a) first-person presenter verbs directed at the audience ("I am going to", "I want to", "I'm gonna", "let me show you", or any variant where the speaker is the subject acting on the audience from the slide face); (b) ledger or build-process language baked as audience-facing copy ("Added:", "DROP 2", "Total Value So Far:", "BECAUSE YOU BELIEVED", "YOU STAYED"); (c) telegraph eyebrows or stage-direction kickers ("THE PROMISE", "THE DECISION", "TODAY'S PROMISES", "WHO AGREES", "one last proof before you decide", or any slide that signals the mechanic to the audience instead of delivering the message); (d) "who agrees" framing or consensus-seeking copy on the slide face. Verbatim match to the brief is NOT a defense (killing the AF-P3-as-sufficient loophole): a string that matches the brief but is presenter-voice or first-person telegraphing still auto-fails. See SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md. Pairs with the existing AF-C9 copy auto-fail (which catches these at Phase 1Q) and AF-F9/AF-F10 (which catch them at Phase 6). |
| AF-PRICE-FACE | Unauthorized price(s) or per-item dollar values on the slide face. OCR the face of every slide. More than ONE distinct price or dollar figure on the slide face auto-fails unless: (a) the slide is a price-ladder DROP slide (where the struck-old price and new price are both declared by price_ladder.json), or (b) the slide is the re-pitch value-stack where price is the running total. Any of the following are always an auto-fail regardless of slide type: (a) a per-component dollar value ("Value: $997", "Value: $1,497") on the offer face when the brief calls for promise framing; (b) a "Total Value So Far: $X" tally on the audience face of a non-tally slide; (c) any dollar value on the face not declared in price_ladder.json or the value-stack table in the brief. The SINGLE sanctioned price is the big callout on the offer slide (the $97 or equivalent final price). Everything else is AF-PRICE-FACE. |
| AF-VALIDATOR | Missing or self-referential validator slide. OCR and inspect the slide(s) designated as the "who says so" / validator beat. (a) The validator slide must carry at least 3 distinct EXTERNAL third-party references: named publications (Forbes, Harvard Business Review, named peer-reviewed journals), named institutions, or named peer-reviewed studies. Self-referential copy ("Who Agrees With Us?", "families who lived it", "our graduates say") does NOT count as an external reference. (b) If the validator slide carries zero external references, trigger AF-VALIDATOR immediately. (c) If the validator slide carries only self-referential framing with no named external source, trigger AF-VALIDATOR. The target is approximately 4 distinct external references. Pairs with QC copy criterion c18 (who says so / external proof present, already wired). |
| AF-WALL | Empty tile, placeholder, or fabricated entry in the Wall of Wins. Open the rendered Wall-of-Wins PNG and OCR every tile. Any of the following triggers AF-WALL on the slide: (a) an empty tile (a blank grid cell with no content); (b) a bracket / placeholder string rendered on the slide face (e.g., "[CLIENT WIN - owner to confirm]", "[INSERT REAL RESULT]") -- bracket tokens on the face are already AF-F10 but AF-WALL adds the semantic check that the Wall specifically is real; (c) a "Watch What Changes" or future-pace framing that targets the BUYER's own outcome instead of presenting real past-client wins. The Wall must present real served-client wins with real names, real cities, and real result figures. Pairs with QC c19 (already wired). The existing AF-F10 catches the bracket token; AF-WALL catches the future-pace framing and the empty tile even when no bracket is visible. |
| AF-OPACITY | Missing atmospheric background on a slide that would otherwise be flat. Inspect slides identified in the brief or archetype as "would be otherwise flat" (pure type slides, data-only slides, transition slides). If a slide is pure flat brand-color with no photographic or atmospheric layer where the SOP requires one (the opacity rule in slide-image-creator-sops.md SOP 9.6 Part C), trigger AF-OPACITY and flag for a faded-image background fix. A controlled low-opacity atmospheric layer (approximately 10-15% opacity photographic background behind the type, on-brand and on-temperature) is required where the SOP mandates it. This is a flag-for-fix (the slide is regenerated with the atmospheric layer added) not a deck-wide fail. |
| AF-CALLOUT | Missing, small, or garbled price callout on the offer slide. On the slide designated as the main offer / CTA (the final price reveal slide, per price_ladder.json), verify: (a) the single sanctioned price callout (e.g., "$97") is present, rendered large (hero typography, not a body beat), and legible (OCR reads the exact correct figure); (b) the time/access callout (e.g., "15 Minutes") is present and legible if the brief specifies it; (c) no additional unauthorized prices appear beside it (AF-PRICE-FACE catches those; AF-CALLOUT specifically checks PRESENCE and LEGIBILITY of the sanctioned callout). Missing, small (below the SOP size floor), or garbled callout text triggers AF-CALLOUT. Pairs with AF-F8 (offer-slide price == FINAL_PRICE, already wired). |
| AF-REPITCH | Missing or incomplete re-pitch block. Verify the deck contains a 4-to-5 slide re-pitch block after the FINAL price reveal and before the hook-reprise close. The re-pitch block must carry BOTH: (a) an emotional beat (the transformation, the family outcome, the identity the offer delivers -- NOT just a feature list), AND (b) a logical justification beat (the rational no-brainer math of the final price, the value-gap framing, or the priceless-pitch comparison). A deck whose final price is revealed and then goes directly to the close (no re-pitch) auto-fails. A re-pitch block that carries ONLY emotion or ONLY logic auto-fails. Pairs with QC copy criterion c23 (re-pitch present, already wired). |
| AF-MODEL | Image-model or color-grade inconsistency across the deck. Where all slides in the deck are generated from the same image model and grade family, any detectable model or grade break (a slide that is visibly from a different model aesthetic, or a slide that is warm-toned when the deck is cool-toned and no DARK_OK exception applies) triggers AF-MODEL on that slide. The check is a deck-wide visual consistency audit run during Phase 5 image QC. One detected break flags the slide for re-generation from the correct model. Pairs with AF-DC5 (ungraded inconsistent deck, already wired). |
| AF-SAME | Identical-layout run or variety floor violation. Compute a layout / archetype hash per slide. (a) RUN CHECK: if 2 or more CONSECUTIVE slides share the same archetype hash (same image zone AND same text layout zone), auto-fail those slides. Three consecutive A2 slides with photo-right / type-left (as shipped in the V10 deck on slides 53-55) is an AF-SAME auto-fail. (b) VARIETY FLOOR: if the deck-wide distribution of archetypes shows fewer than 3 distinct archetypes among the majority of slides (the "swap the person, keep the frame" pattern), trigger AF-SAME on the deck-level report. The existing AF-F6 (image-position sameness, already wired) catches consecutive image-zone runs; AF-SAME additionally checks the archetype run and the deck-wide variety floor. |
| AF-DELIVER | Deliverable bundle incomplete at closeout (the closeout hard gate). Fires at closeout when ANY of the following is true: (a) `working/checkpoints/deliverable_bundle.json` is absent or its `all_present` field is not `true`; (b) the presenter guide PDF does not exist on disk or is empty; (c) the word-for-word script PDF does not exist on disk or is empty; (d) the audio file (`PRESENTER-AUDIO.mp3` or equivalent) does not exist on disk, is under 100KB (for any full webinar script), or is the stub silence file. Missing audio (the V10 gap that closed out without an audio deliverable) is the primary trigger. AF-DELIVER is checked independently of AF-F5 (the deck QC pass-artifact gate). BOTH must pass before any delivery action may proceed. A "done" flag or a partial delivery without the full three-artifact bundle is not closeout. See SOP-PITCH-05-DELIVERABLE-BUNDLE.md. |
| AF-DH1 | Deliverable Hygiene violation. The client package directory `delivery/[DECK_SLUG]-FINAL/` must contain ONLY the five allowed files: `[Deck-Title]-FINAL.pptx`, `[Deck-Title]-FINAL.pdf`, `PRESENTER-GUIDE.pdf`, `PRESENTERS-SPEECH.pdf`, `PRESENTER-AUDIO.mp3`. Any extra file or wrongly-named file (no `-FINAL` suffix on PPTX/PDF) = AF-DH1. Enumerate the delivery directory and compare every file name against the whitelist; one mismatch blocks delivery. Owned by Delivery Concierge SOP 9.0; final check confirmed here before the owner's download link is produced. |
| AF-RESEARCH-GATE | Research Phase gate block. At Phase 1Q, BEFORE any per-slide copy QC begins, verify `working/research/brief-[DECK_SLUG].md` exists, contains `research_complete: true`, and includes sections for categories A, C, D, AND F. Any condition unmet = AF-RESEARCH-GATE and BLOCKS Phase 1Q entirely. Failure message: "BLOCKED: Research Phase (-0.5) incomplete. Director must re-dispatch ROLE-04." Applies to ALL deck types (personal brand and general offer). |

**Tooling the vision gate (required tools -- fail-closed if missing):** The following tools are required by the above AF codes. If any tool is absent or returns an error, the corresponding AF code HARD-FAILS CLOSED (treat as fail, never silent-pass): (1) OCR engine (for logo chip, hero strings, offer price, validator refs, Wall tiles, callout text); (2) SSIM / perceptual-hash logo comparator (for AF-LOGO); (3) face-detection + skin-tone classifier (for AF-CAST, AF-FACE-MOOD); (4) gradient / glow detector on type regions (for AF-GRAD); (5) pt-size estimator from rendered PNG (for AF-TYPE); (6) archetype / layout-hash generator (for AF-SAME); (7) disk-file existence + size check (for AF-DELIVER). A tool that is down is treated as if the check failed, not as if it passed.

**AF-P3 demotion:** AF-P3 ("rendered string matches brief verbatim") is necessary but NOT sufficient as a PASS condition. A string that matches the brief verbatim but contains first-person presenter voice (AF-TELEGRAPH), per-item pricing (AF-PRICE-FACE), or any other AF code violation still auto-fails. Verbatim match to the brief is NOT a defense.

#### SOP-Doctrine Auto-Fails (checked when auditing or revising THIS SOP and any SOP it depends on)

This family does not score a slide. It guards the SOP TEXT ITSELF against the defect that produced the invented Kie.ai rate cap (the "2 RPS / waves of 20 / 15-second sleep" framing that was never verified against the live docs and was wrong). It is checked whenever this document, the master CLIENT WEBINAR DECK SOP, the slide-submitter SOPs, the MODEL MANIFEST, MODEL-SPECS, or any SOP this gate references is authored, revised, or re-audited. Quality Control's procedure auditor enforces the same rule fleet-wide (`quality-control/procedure-auditor.md`, the seventh mechanical auto-flag).

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-SRC | Un-sourced hard EXTERNAL-API constant baked into an SOP as doctrine. A "hard external constant" is any concrete value about a third-party service the SOP states as fact and an agent then acts on: a rate limit or throttle, a token or character cap, a price or cost, an endpoint URL, a model id, a quota, or a payload-size limit. Every such constant MUST carry EITHER (a) an inline citation `(source: <doc URL>, verified <YYYY-MM-DD>)`, OR (b) an explicit `UNVERIFIED-AGAINST-DOCS` tag naming who stated it, when, and the URL to confirm it at. Neither = auto-fail. Independently: a self-hedging line of the form "if this conflicts with / ever conflicts with live documentation, verify later / with operator sign-off" ATTACHED TO AN UN-CITED HARD NUMBER is ITSELF an automatic fail (it is the fingerprint of an invented constant). An internal library-defined value (a budget multiple, a poll-count guard, a word ceiling) is out of scope. PASS: `20 new generation requests per 10 seconds (source: https://docs.kie.ai/ Section 8, verified 2026-06-14)`. PASS (honest unverified): `operator-stated 20 images / 10 seconds. UNVERIFIED-AGAINST-DOCS, operator-stated 2026-06-14, confirm at https://docs.kie.ai/`. FAIL (the exact defect this gate stops): `2 RPS = 20 requests per wave with a 15-second sleep ... if this appendix ever conflicts with live Kie.ai documentation, verify against the live docs.` |

**Density-floor-overhaul render auto-fails (design-craft + slide-craft at render stage). Checked on every rendered image at Phase 5 and re-checked across all pages at Phase 6:**

| Code | Level | Auto-Fail Condition | Source SOP |
|------|-------|---------------------|------------|
| AF-I8 | slide | The hook refrain is rendered in a footer band on ANY slide (footer-stamped hook). Also AF-HOOK-2 at render. | presentation-design-system/03 + presentation-slide-craft/SOP-SLIDE-03 |
| AF-I9 | slide | A dedicated hook slide carries a competing photographic subject at normal opacity (>~15% opacity), or is not pure-typography. | presentation-design-system/03 |
| AF-I10 | slide | The hook line appears twice on the same slide, or is reworded/extended/abbreviated from the canonical refrain. Also AF-HOOK-4/5 at render. | presentation-design-system/03 + presentation-slide-craft/SOP-SLIDE-03 |
| AF-I11 | slide / DECK | The rendered logo is a DIFFERENT mark than the locked LOGO_URL asset, OR the mark DRIFTS between slides (two slides show two different marks = deck-level). Cross-slide comparison at Phase 6. | presentation-design-system/05 + presentation-image-library/SOP-IMG-01 check 9 |
| AF-I12 / AF-PLACEHOLDER | slide (blocks FINAL) | Any bracket / "owner to confirm" / placeholder token rendered into the image face. Same as AF-AUD-6 at render. | presentation-slide-craft/SOP-SLIDE-02 + MASTER-QC-AUTOFAIL-RULESET RULE 3 |
| AF-I13 | slide | Image-narration caption rendered on the face (describes what the photo already shows). Same as AF-AUD-3 at render. | presentation-slide-craft/SOP-SLIDE-02 |
| AF-I14 | slide | A speaker SAY line, internal pitch doctrine, credential dump, or the word "webinar"/meta-telegraph rendered on the face. Same as AF-AUD-1/2/4/5 at render. | presentation-slide-craft/SOP-SLIDE-02 |
| AF-I15 | slide | A rendered text block beyond the three approved copy blocks (an invented step list, credential paragraph, "Step 1/2/3" cue, or any body text not in slides_copy.md). Same as AF-OBI-1 at render (reference failure case s5 image cards). | presentation-slide-craft/SOP-SLIDE-01 |
| AF-I16 | slide | A rendered comparison table with more than 2 contrast rows. Same as AF-OBI-6 at render. | presentation-slide-craft/SOP-SLIDE-01 |

**Density-floor-overhaul deck-level design-craft auto-fails (run at Phase 6 final-deck QC over all rendered pages):**

| Code | Level | Auto-Fail Condition | Source SOP |
|------|-------|---------------------|------------|
| AF-D1 | DECK | The deck uses fewer than 3 distinct archetypes, OR one archetype exceeds 60% of slides, OR the same five-part word-block stack (kicker + headline + subhead + footer + caption) appears on more than 60% of slides (the reference failure case rigid chassis). | presentation-design-system/04-SOP-variable-layout-anti-template.md |
| AF-D2 | DECK | The deck has zero dedicated pure-typography hook slides. Also AF-HOOK-3. | presentation-design-system/03 + presentation-slide-craft/SOP-SLIDE-03 |
| AF-D3 | DECK | No locked weight ladder (only one headline weight deck-wide), OR the single black-headline-plus-one-accent-word device appears on more than 70% of slides (the reference failure case single-device cookie-cutter typography). | presentation-design-system/02-SOP-creative-typography-guide.md |

---

### SOP 9.1 -- Copy QC Gate (Phase 1Q)

**When to run:** Phase 1Q -- immediately after the Slide Copywriter delivers slides_copy.md and proof_audit.txt. Runs before the owner approval gate (Phase 1A).

**Inputs:**
- working/copy/slides_copy.md
- working/copy/proof_audit.txt
- working/copy/hook_variants.json
- working/copy/hook_package.json (Hook Strategist placement map + hook-absent list + canonical_hook; required for AF-HOOK)
- working/copy/audience_say_tags.json (Slide Copywriter AUDIENCE/SAY tagging pass output; required for AF-AUD; its absence fails the deck)
- working/copy/arc_allocation.json (section order + LADDER positions; required for AF-DEN)
- working/copy/intake.json / mission_prd.json (canonical HOOK string, prices, proof claims)

**Steps:**
1. For every slide, check ALL Copy-stage auto-fails BEFORE scoring, in this order, and record each triggered code in the report. A slide with any slide-level auto-fail is marked FAIL immediately; any DECK-level trigger fails the whole gate.
   a. The five base Copy QC Auto-Fails (AF-C1, AF-C3, AF-C4, AF-C5; AF-C2 is retired, see the AF-HOOK battery).
   b. The Slide-Craft auto-fails: **AF-HOOK** (1a/1c deck-level count and dedicated-slide check, 2 footer, 4 doubled, 5 mutated, 7 conflated signature quote -- using hook_package.json and mission_prd.json canonical_hook), **AF-AUD** (1 speaker SAY, 2 internal doctrine, 4 meta/"webinar", 5 credential dump -- AF-AUD-3 image-narration and AF-AUD-6 placeholder are render-stage; verify audience_say_tags.json exists or fail the deck for a missing required artifact), **AF-OBI** (1 block count, 2 headline words, 3 two ideas, 4 value trio, 5 pain list -- AF-OBI-6 table is render-stage).
   c. The Density auto-fails **AF-DEN-1 through AF-DEN-8** against arc_allocation.json and slide order (DECK-level).
   d. **AF-COVERAGE-1** (DECK-level anti-compression): compare the arc_allocation.json total slide count against `mission_prd.source_slide_count`. If `final_slide_count < source_slide_count` the gate FAILS (Mode A, where `source_slide_count == 0`, always passes). Mode B is ADD-only; never delete a client slide to hit a duration cap.
   e. **The PITCH-ENGINE auto-fails** (DECK/slide-level; SOP-PITCH-06). Run `python3 scripts/pitch_engines_check.py --run-dir <run_dir> --phase 1Q --json`; exit 4 = one or more triggered, record each `code` from the `fails[]` array. This covers **AF-CADENCE** (per-rung VALUE_ADD->PROMISE->REPITCH_MINI->COST_OF_INACTION ordering), **AF-NO-COST-OF-INACTION**, **AF-GUARANTEE-GENERIC** (mechanical anti-generic half; the felt-vs-generic VERDICT is a logged scored note in this report), **AF-NO-BRANDED-METHOD** / **AF-METHOD-FABRICATED** (de-inverted: propose-for-owner-approval; silent fabrication still banned), and **AF-NO-TIME-TO-RESULT**. A `defer` (input artifact absent) is not a fail. Any triggered code fails the gate. (The Emotional/Story copy-beat engines **AF-NO-FELT-STAKES** / **AF-NO-VILLAIN** are run by `scripts/intelligence_engines_check.py --phase copy` per SOP-SLIDE-00 Section 9.)
2. Dispatch 3-5 QC agents (qwen3-vl:235b-cloud — independent from the producer; no self-grading) each independently scoring slides_copy.md on all 17 criteria. Each agent returns a score per criterion per slide.
3. Average the agent scores for each criterion across all slides. Compute the overall average.
4. Apply double-weight to criteria 2, 5, 7, 12, 13, and 15 (these are the most critical -- see criteria list below). NOTE: the hook (old criterion 1) and the placeholder/audience-facing categories are no longer scored criteria at all -- they are now AUTO-FAILS (AF-HOOK, AF-AUD) that veto before scoring, so they cannot average away. One-big-idea (criterion 5) and slide-vs-script (criterion 13) remain as double-weighted scored criteria AND are backstopped by the AF-OBI and AF-AUD auto-fails.
5. Write the copy_qc_report.json. One entry per slide, plus a summary. Structure:
   ```json
   {
     "gate": "Phase 1Q",
     "overall_average": 0.0,
     "weighted_average": 0.0,
     "average": 0.0,
     "auto_fails_triggered": [],
     "pass": true,
     "qc_independence": {
       "graded_by": "qc-specialist-presentations",
       "independent": true,
       "builder": "slide-copywriter",
       "self_graded": false,
       "graded_at": "2026-06-18T00:00:00Z"
     },
     "per_slide_scores": [
       {"slide": N, "auto_fails": [], "scores": {"c1": 0, "c2": 0, ...}, "average": 0.0, "pass": true, "notes": ""}
     ],
     "failing_slides": [],
     "revision_instructions": []
   }
   ```

   **PROVENANCE — the `qc_independence` block is MANDATORY (AF-QC-INDEPENDENCE).**
   The build_deck.py preflight (`_chk_copy_qc`) HARD-FAILS the deck (exit 3) on a
   self-graded / builder-graded report. A report that passes every numeric check
   but was written by the role that authored the copy proves nothing — it is the
   rubber-stamp the gate exists to refuse. The block MUST satisfy ALL of:
   - `graded_by` (or `reviewer` / `reviewed_by` / `reviewer_identity`) names the
     INDEPENDENT QC specialist persona running THIS gate. It must be a non-empty
     string and must NOT be any of `build_deck.py`, `build_deck`, `self`,
     `builder`, `author`, nor the deck-copy author role `slide-copywriter`.
   - `independent` is `true` (an explicit `independent: false` fails the gate).
   - `self_graded` is `false` (top-level `self_graded: true` fails the gate).
   - if a `builder` / `built_by` identity is recorded, it must NOT equal the
     reviewer identity (the builder may not grade its own work).
   A report that OMITS this block entirely FAILS — independence is proven
   affirmatively, never assumed. The independent QC specialist (a persona distinct
   from the Slide Copywriter that authored the copy) stamps this block when it
   writes the report.
6. For every slide with an auto-fail or scoring < 8.5: write specific revision_instructions. Each instruction must name the criterion or auto-fail code, the specific failure, and the required fix. Example: "Slide 12, AF-C5 (headline word count): headline is 11 words (max 9). Trim to: 'Your clients come to you every week.'"
7. If overall weighted_average >= 8.5 AND no individual slide scores below 7.0 AND no auto-fails: pass. Write `pass: true`.
8. If any slide scores below 7.0 OR overall weighted_average < 8.5 OR any auto-fail triggered: fail. Write `pass: false`. Send revision_instructions to the Slide Copywriter.
9. Increment `loop_count` in the report. If loop_count reaches 4 without a pass: escalate to the Director with the specific persistent failures.

**The 17 Copy QC Criteria (c1-c17):**
1. **(NOT SCORED -- now an auto-fail battery.)** The hook is no longer scored by count. It is governed entirely by the AF-HOOK auto-fails (ceiling of 4 dedicated slides, anti-footer, anti-duplicate, anti-mutation, dedicated-slide-must-exist). Do NOT score a hook-frequency criterion; checking AF-HOOK is mandatory and vetoes before scoring. (Replaces the old "hook appears >= 7 times" criterion that produced the 40-slide stamping.)
2. (double-weight) Every headline is 9 words or fewer. Count is exact.
3. Every subhead is 18 words or fewer.
4. Body copy is 3 bullets max or 30 words max per slide.
5. (double-weight) Slides are one big idea each. No slide tries to do two things. Backstopped by the AF-OBI auto-fail battery (block count, two-ideas, value trio, pain list).
6. Presentation arc is complete: hook / problem / solution / proof / offer / price / close.
7. (double-weight) No em dashes anywhere in any field.
8. (double-weight) PRESENTER NOTE is present and substantive (not a duplicate of the slide copy) for every slide. The SLIDE IS NOT THE SCRIPT (master rule 15): the spoken words live in the PRESENTER NOTE and route to the Presenter's Speech / Guide, never on the face. Backstopped by the AF-AUD auto-fail battery (speaker SAY lines, internal doctrine captions, image narration, meta/"webinar", credential dumps, placeholder tokens are all auto-fails that veto before scoring).
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
17. Ladder integrity (all sub-items must pass; the SPACING half is now backstopped by the AF-DEN deck-level auto-fails):
    - ANCHOR slide carries the explicit memory hook ("Remember this number. Keep watching." or equivalent).
    - A BUILDUP slide immediately precedes every DROP slide (no DROP without a BUILDUP). (AF-DEN-3.)
    - At least one callback is present in the offer section explicitly referencing the ANCHOR.
    - FINAL price sits below all ladder rungs (strictly less than DROP3 in drop mode).
    - Every adjacent price beat is at least 8 slides apart, the anchor sits near the one-third mark, a promises beat precedes the anchor, an itemized value-stack slide precedes Drop 1, the Wall of Wins sits 4-6 slides before the offer, and a 4-7 slide re-pitch block follows FINAL. (These are the AF-DEN-1/2/4/5/6/7 deck-level auto-fails; a failure there fails this gate.)

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
1. For every prompt, check ALL Prompt QC Auto-Fails BEFORE scoring: the eight base codes (AF-P1 through AF-P8) AND the density-floor-overhaul design-craft codes (AF-P9 logo-as-T2I, AF-P10 references-not-named, AF-P11 missing "place do not redraw", AF-P12 style-frame directive, AF-P13 archetype/position not declared, AF-P14 weight-ladder role / price-type / hero-weight missing, AF-P15 hook-anchor prompt not pure-type). Check 0 (character count) is always first: count mechanically and record the exact integer in the report. A prompt with any auto-fail is marked FAIL immediately; record the code(s). The prompt must be written TO the Typography Architect's treatment_table.md (the archetype, weight roles, emphasis word, price treatment) and must use Mode B image-to-image with LOGO_URL in input_urls per SOP-IMG-01.
2. Dispatch 5-10 QC agents (qwen3-vl:235b-cloud — independent from the producer; no self-grading) in parallel. Each agent independently scores each prompt on all 15 criteria.
3. For each prompt, calculate the per-agent score, then average across all agents.
4. Apply double-weight to criteria 2, 3, 4, 13, 16, 17, 18, and 19 (the most commonly failing and highest impact; criterion 16 image-grounding is double-weighted because ungrounded imagery is the F3 defect this gate exists to stop; criterion 17 designed-typography and criterion 18 standalone-art are double-weighted because basic fonts and "background with text" are the documented gold-standard failures these gates exist to stop; criterion 19 negative-block defect mapping is double-weighted because the missing negative block is the root cause of the garbled-text, logo-mutation, placeholder, and image-narration defects this overhaul exists to stop).
5. Write prompt_qc_report.json. One entry per prompt (one per slide), including the recorded character count and any auto-fail codes.
6. For any prompt with an auto-fail or scoring < 8.5: write specific revision_instructions. Instructions must specify the failing auto-fail code or criterion and the exact change required.
7. Identify fail classification for each failing prompt: render-noise (image quality issues likely in generation), prompt-defect (structural problem with the prompt itself), or text-fail (headline text will not render correctly -- mark as text-fail-x2 if two text elements fail).
8. Pass: overall weighted average >= 8.5, no individual prompt below 7.0, no auto-fails. Fail: otherwise.
9. Increment loop_count. At loop_count = 4, escalate.

**The 22 Prompt QC Criteria (p1-p22):**
1. All 15 elements present in order (format / background / headline verbatim / typography / font placement / thirds / object placement / overlays / brand palette / logo / people / bullets / mood / professionalism / closing constraints -- where element 15 is the SOP 9.8 paired negative block).
2. (double-weight) Headline text is verbatim match to slides_copy.md HEADLINE field (not paraphrased).
3. (double-weight) Character count is within the working range (hard floor 9,000, hard maximum 18,000). Band 9,000-18,000. Beyond the AF-P1/AF-P2 floor, this criterion rewards genuine budget use: a prompt at or above 9,000 characters that spends the budget on defect-preventing specificity (per-line spelling-lock, the full eight-class paired negative block, exhaustive image-to-image logo language, complete people-anatomy direction, deep scene and grade detail) scores high; a prompt that scrapes the 9,000 floor with boilerplate, OR that pads to the count with repeated adjectives or repeated adjectives, scores low. The long budget is for specificity, never filler.
4. (double-weight) White base rule: element 2 specifies white background (unless DARK_OK=true).
5. People element (11) specifies at least one of the 3 engines with representation group and gender.
6. Thirds-grid assignment in element 6 is specific (named regions -- not "somewhere on the right").
7. No em dashes in the prompt body.
8. Brand palette (element 9): all 3 hex codes from STYLE BLOCK listed with roles.
9. Logo placement (element 10): matches STYLE BLOCK logo_placement_rule.
10. Overlays (element 8): present for hook slides per hook_variants.json; absent for non-hook slides.
11. Mood (element 13): specific and appropriate for the arc section.
12. Negative block (element 15, SOP 9.8) is the full eight-class paired block, not the old thin one-line AVOID phrase. Beyond the AF-P13 floor, this criterion scores how complete and well-paired the block is: all eight defect classes present as imperative "Do not ..." sentences, each critical negative paired with a positive twin earlier in the prompt, no contradiction with the positive prompt.
13. (double-weight) Representation ratio: spot-check 10 prompts -- people specifications are consistent with STYLE BLOCK representation_ratio.
14. Price-drop slides: struck price and new price match price_ladder.json exactly (verify for any slide in the Price Ladder arc section).
15. Prompt front-loads critical content: composition, people, and headline appear in the first 500 characters.
16. (double-weight) Image grounding (P6): the prompt depicts a CONCRETE moment from THIS client's method, book, message, or offer (the GROUNDED_CONTENT variable in the brief), not a generic interchangeable scene. The scored question is "does this image depict a concrete moment from THIS client's method?" Beyond the binary AF-P9 floor, this criterion scores HOW grounded the moment is: a prompt that names the specific method step, the specific setting where that step happens, and the specific outcome it produces scores high; a prompt that gestures at the industry generically scores low. This criterion is also evaluated against the rendered image at final-deck QC (SOP 9.5).
17. (double-weight) Designed typography (the TYPOGRAPHY LAW): beyond the binary AF-P10 floor, this criterion scores HOW well the prompt carries the designed type system. A prompt that names the exact weight AND a large pt size on EVERY text line, honors the one-family weight map (Black for headlines and giant numbers, ExtraBold for subs and body beats, Bold for gold caps labels, Medium italic for tertiary), applies the full size scale (giant numbers 110-150pt, hero headline 62-86pt, kicker ~13pt), lays out the canonical hierarchy stack, and specifies the creative devices (giant numbers, paired gold rules, drawn strikes, single-word color swaps, text baked into the image) scores high; a prompt that names a font with only a partial size hint or a thin hierarchy scores low; a basic or default font is the AF-P10 floor.
18. (double-weight) Standalone art (the core design principle): beyond the binary AF-P11 floor, this criterion scores HOW well the prompt directs a finished, gallery-grade standalone composition. A prompt with intentional art direction (focal hierarchy, negative space, depth), a clear hero subject, premium lifestyle-documentary photography, the typography composed INTO the image, and its own felt emotional beat (readable in 2 seconds) scores high; a prompt that gestures at a scene with copy on top scores low; "just a background with text" is the AF-P11 floor. The scored question is "would this single slide, pulled out alone, read as a deliberate piece of visual art?" Re-evaluated against the rendered image at Phase 5 and final-deck QC.
19. (double-weight) Negative-block defect mapping (the pre-generation negative-prompt gate; beyond the AF-P13 floor): scores HOW well the eight-class block maps onto the forensic defects. A prompt whose block states each of the eight classes as a specific, defect-named imperative ("Do not misspell or garble any letter" beats "no bad text"), pairs every critical negative with a concrete positive twin earlier in the prompt, and reads cleanly against the positive prompt with no contradiction, scores high; a block that gestures vaguely, omits a class, or leaves negatives unpaired scores low; a missing block is the AF-P13 / AF-P8 floor. Re-verified against the rendered image at Phase 5/6 (AF-I1, AF-I2, AF-F7, AF-F9, AF-F10, AF-DC1, AF-R1).
20. Spelling-lock coverage (beyond the AF-P14 floor): every verbatim string carries an explicit letter-for-letter spelling-lock written immediately after the string. Full coverage scores high; a prompt that locks only the headline and leaves the sub, kicker, or price unlocked scores low; any unlocked string is the AF-P14 floor. This is the prompt-side guard against the garbled-text defect.
21. Logo image-to-image directive (beyond the AF-P15 floor): on every LOGO_ON_SLIDES = true slide the prompt declares image-to-image mode with LOGO_URL as the first reference, carries the verbatim "place, do not redraw" sentence, and carries the "do not invent any mark" negative twin. Complete directive scores high; a directive missing the mode declaration, the reference order, or the "do not redraw" sentence scores low; a logo-in-words-only or text-to-image logo prompt is the AF-P15 floor. Pairs with the render-time AF-F7 logo-identity-drift gate.
22. No placeholder token (beyond the AF-P16 floor): the prompt body carries no bracket token or build-note substring as rendered copy. Clean scores high; any such token is the AF-P16 floor and pre-empts the render-side AF-F10.

**Design-Craft Scoring Dimensions (Phase 3 Prompt QC -- scored p-DC1 through p-DC7; Phase 5 Image QC -- re-scored i-DC1 through i-DC7):**

After the standard 18 criteria, score the following seven Design-Craft dimensions. Each dimension is scored 1-10, same scale as the standard criteria. The Design-Craft average is included in the overall prompt QC score for that slide. A slide that scores <= 3 on ANY SINGLE Design-Craft dimension triggers a forced revision loop regardless of the overall average (the "forced loop" rule -- amateur composition on even one dimension blocks the deck).

| Dim | Code | What is scored | AUTO-FAIL code |
|-----|------|---------------|----------------|
| 1 | p-DC1 / i-DC1 | Composition / Thirds: prompt declares thirds-zone for headline, subject, and supporting elements; rendered image honors the declared zones; focal point at or near a thirds-grid intersection | AF-DC3 if missing entirely |
| 2 | p-DC2 / i-DC2 | Layering / Depth: prompt specifies foreground / midground / background; subject is separated from background by depth of field, rim light, or scrim gradient in the rendered image | AF-DC2 if completely flat |
| 3 | p-DC3 / i-DC3 | Card / Object Use: when the slide spec calls for a panel, inset, callout chip, vignette, hang-tag, price-tag motif, or gold-rule divider, the prompt specifies the device with correct placement (named thirds zone, not just "corner") | -- |
| 4 | p-DC4 / i-DC4 | Font Placement / Alignment: headline and copy stack within the named thirds zone; text is within safe margins (no element within 5% of any edge); no text over a human face in the rendered image | AF-DC6 if in unsafe zone; AF-DC1 if over face |
| 5 | p-DC5 / i-DC5 | Color Harmony (DOUBLE-WEIGHT): prompt declares a contrast ratio for headline-on-background (WCAG AA minimum); complementary accent is reserved for maximum-impact moments; color relationships match the STYLE BLOCK COLOR THEORY section; rendered image passes the contrast check | AF-DC4 if WCAG fails |
| 6 | p-DC6 / i-DC6 | Color Grading (DOUBLE-WEIGHT): prompt includes the TEMPERATURE LOCK and COLOR GRADING block comment; rendered image matches the deck-level grade profile (WARM / COOL / NEUTRAL); deck-wide grade consistency is checked at SOP 9.5 | AF-DC5 if inconsistent across deck |
| 7 | p-DC7 / i-DC7 | Art-Direction Quality: overall prompt demonstrates professional art direction -- clear visual idea, intentional composition, gallery-standard ambition; rendered image reads as magazine-grade, not amateur stock-photo aesthetic | AF-DC1 (text over face), AF-DC2 (flat), AF-P11 (standalone) if worst-case |

**Design-Craft pass rules:**
- 8.5 average threshold and 7.0 per-dimension floor apply to the Design-Craft block exactly as they apply to the standard criteria.
- Dimensions 5 (color harmony) and 6 (color grading) are DOUBLE-WEIGHT: the score on each of those dimensions counts twice in the Design-Craft average.
- A score of <= 3 on any single Design-Craft dimension triggers a FORCED REVISION LOOP regardless of the average. "3 or below" = amateur composition that must be rebuilt before the deck advances.

**Outputs:**
- working/qc/prompt_qc_report.json (with per-prompt character counts, auto-fail codes, scores including p-DC1 through p-DC7, fail classifications, revision instructions)

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
1. For every image, check ALL Image QC Auto-Fails BEFORE scoring: the seven base codes (AF-I1 through AF-I7, where AF-I4 now also fails a logo that DIFFERS from the locked LOGO_URL asset) AND the density-floor-overhaul render codes (AF-I8 footer-stamped hook, AF-I9 hook slide not pure-type, AF-I10 hook doubled/mutated on render, AF-I11 logo a different mark than the locked asset, AF-I12/AF-PLACEHOLDER any bracket/"owner to confirm" token rendered into the face, AF-I13 image-narration caption, AF-I14 speaker/doctrine/"webinar"/credential text on the face, AF-I15 a rendered text block beyond the three approved copy blocks, AF-I16 a rendered comparison table over 2 rows). A triggered auto-fail immediately marks the image FAIL; record the code(s) in the report. Auto-fail inspection includes: reading every word of rendered text on the slide for misspellings/duplicates/garbled glyphs AND for any banned audience-facing category (the word "webinar", speaker SAY phrasing, internal pitch-doctrine captions, image-narration captions, credential paragraphs) AND for any bracket/placeholder token (regex `\[[^\]]*\]` plus "owner to confirm" etc -- this BLOCKS FINAL STATUS); inspecting hands/faces/limbs for deformities; verifying aspect ratio; verifying the logo is present, integral, AND the SAME mark as the locked LOGO_URL asset; checking that dedicated hook slides are pure-typography (hook line over a low-opacity image, no footer band, printed once, verbatim); checking background darkness; scanning for emoji/clipart; checking rendered text for em dashes.
2. Dispatch up to 5 QC agents (qwen3-vl:235b-cloud) per batch of images. Each agent scores a non-overlapping batch (e.g., agent 1 handles slides 1-15, agent 2 handles slides 16-30, etc.).
3. Each agent scores each image on all 17 criteria.
4. Apply double-weight to criteria 3, 5, 6, 7, 15, 16, and 17 (most critical for the assembled deck; criterion 15 image-grounding, criterion 16 designed-typography, and criterion 17 standalone-art are all double-weighted, because ungrounded imagery, basic fonts, and "background with text" are the documented gold-standard failures).
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

**The 17 Image QC Criteria (i1-i17):**

AUTO-FAIL LAYER (checked first; see AF-I1 through AF-I10 above plus the deck-wide AF-R1/AF-R3 tally -- these override scoring):
- i-AF: Any of AF-I1 through AF-I10 triggers a hard FAIL on the image before the scored layer runs; the deck-wide AF-R1/AF-R3 representation tally (step 5a) hard-FAILS the deck regardless of individual image scores.

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
16. (double-weight) Designed typography (the TYPOGRAPHY LAW): the rendered type reads as the DESIGNED weight-mapped system, not a basic or default font. The scored question is "is this gallery-grade designed typography composed into the image?" An image with a dominating heavy-weight (Black) charcoal headline, real size hierarchy, giant numbers at 1.5x-3x surrounding text where the brief calls for them, gold all-caps letter-spaced kicker labels, and charcoal headlines (never pure black) scores high; an image whose type looks like a basic or default font, or is flat with no hierarchy, scores low. (The binary floor is AF-I9; this criterion scores the degree of designed typography above that floor.)
17. (double-weight) Standalone art (the core design principle): the rendered slide reads as a finished, gallery-grade piece of visual art that stands on its own. The scored question is "pulled out alone, would this single slide read as a deliberate piece of art?" An image with intentional art direction, a clear hero subject, premium lifestyle-documentary photography, typography composed into the picture, and its own felt emotional beat scores high; an image that is "just a background with text," or that only makes sense as part of the sequence, scores low. (The binary floor is AF-I10; this criterion scores the degree of standalone art above that floor.)

**Design-Craft Image QC Dimensions (i-DC1 through i-DC7) -- scored after criteria i1-i17:**

Re-score the seven Design-Craft dimensions from Phase 3 Prompt QC against the RENDERED IMAGE. The same 1-10 scale, same 8.5 threshold, same 7.0 floor, same double-weight for color-harmony and color-grading, same forced-loop rule (score <= 3 on any dimension triggers a forced revision loop regardless of average).

| Dim | i-Code | What is scored in the rendered image |
|-----|--------|--------------------------------------|
| 1 | i-DC1 | Composition / Thirds: does the rendered image place headline, subject, and supporting elements in the declared thirds zones? Does the focal point land at or near a thirds-grid intersection? |
| 2 | i-DC2 | Layering / Depth: is there visible foreground / midground / background separation in the image? Is the subject separated from the background by depth of field, rim light, or scrim gradient? |
| 3 | i-DC3 | Card / Object Use: if the slide called for a design device (panel, inset, callout chip, vignette, hang-tag, price-tag motif, gold-rule divider), is it present, correctly placed, and well-executed? |
| 4 | i-DC4 | Font Placement / Alignment AND LAYOUT VARIETY (FIX-9 recut): is text within safe margins (not within 5% of any edge)? Is any text landing over a human face? CRUCIALLY -- this dimension now REWARDS LAYOUT VARIETY and FAILS SAMENESS, rather than rewarding a single canonical hierarchy stack honored identically across all slides (the old cookie-cutter virtue). A deck that places the same hierarchy stack and the same image position (e.g. photo-right / type-left) on every slide scores LOW; a deck that rotates the layout per slide-type per the Typography Architect's type_layout_system.md scores HIGH. The hook slides must be type-driven (no image or <=15% opacity bg image with large designed type over it). See the image-position-variety assert in SOP 9.5 step 1e. |
| 5 | i-DC5 (DOUBLE-WEIGHT) | Color Harmony: do the rendered colors honor WCAG AA contrast on all text? Are complementary accents used only for maximum-impact moments? Does the palette feel intentionally composed? |
| 6 | i-DC6 (DOUBLE-WEIGHT) | Color Grading: does this image match the deck's grade profile (WARM / COOL / NEUTRAL)? Does it feel shot in the same light as the other slides? Is temperature and saturation consistent? |
| 7 | i-DC7 | Art-Direction Quality: does the rendered slide look magazine-grade, gallery-worthy, art-directed? Or does it look like a generic stock photo with text on top? |

**Outputs:**
- working/qc/image_qc_report.json (per-image auto-fail codes, scores including i-DC1 through i-DC7, classifications, and the deck-wide `representation_tally` table + verdict)
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

**Render step (always first):** an agent cannot eyeball a PPTX directly. Render it to inspectable pages exactly per MASTER-QC-AUTOFAIL-RULESET.md (SOP-SLIDE-00) + qc-specialist-presentations SOP 9.x (PRESENTATION-MASTER-DOCTRINE.md §4):
```
soffice --headless --convert-to pdf <Deck>.pptx && pdftoppm -png -r 100 <Deck>.pdf working/qc/finalrender/page
```
(The Capacity & Reliability Engineer's soffice/python-pptx/poppler preflight must have passed before this gate runs; if the render toolchain is unavailable, escalate, do not skip the gate.)

**Inputs:**
- The assembled PPTX file (the deliverable)
- The PDF-rendered pages (PNG files at 100 DPI in working/qc/finalrender/)
- The PPTX shape geometry (every text box and overlay element's x / y / w / h, read from the PPTX XML via python-pptx)
- (Decision 5C) NO pptx_text_overlays.json — native overlays are eliminated. The QC confirms the delivered PPTX carries NO native (non-notes) on-slide text run on any slide (every slide is a single composed gpt-image-2 image; AF-OVERLAY-DELIVERED). A present pptx_text_overlays.json is itself AF-OVERLAY-DELIVERED.
- working/copy/slides_copy.md (for copy verification in the assembled deck)
- working/copy/presenter_notes.json (for speaker notes verification)
- working/brand/style_block.md + the captured REPRESENTATION_MIX (for the tally re-run)
- working/brief GROUNDED_CONTENT variable (for the grounding re-verification)
- working/copy/price_ladder.json + working/copy/intake.json (for the offer-slide price == FINAL_PRICE assert, AF-F8)
- working/typography/type_layout_system.md (the Typography Architect's per-slide-type layout system, for the image-position-variety assert AF-F6 and the hook-slide type-driven check)
- one canonical LOGO_URL / logo reference asset (for the logo-identity diff, AF-F7)

**Steps:**

1. **CODED ASSEMBLED-SLIDE ASSERTS (P3) -- run on EVERY composed slide, mechanically, before any score.** These are the auto-fails AF-F1 through AF-F4 plus AF-F6 through AF-F9 (above). For each slide:
   a. **Collision assert (AF-F1):** read the bounding box (x, y, w, h) of every text box and every overlay element from the PPTX geometry; additionally detect focal faces in the rendered PNG. Compute pairwise intersection of all text/overlay boxes with each other, with the logo chip, and with detected faces. ANY intersection = AF-F1 collision auto-fail on that slide. A non-overlapping layout has zero intersecting boxes.
   b. **No-native-overlay assert (Decision 5C, AF-OVERLAY-DELIVERED):** read every shape on the slide via python-pptx; the slide must carry ONLY picture shapes (the composed gpt-image-2 image, plus the PIL-composited logo image baked into the PNG) and the off-slide notes pane. ANY native (non-notes) on-slide text run, or the presence of a pptx_text_overlays.json in the run, fails AF-OVERLAY-DELIVERED. There are no overlay text boxes to collision-check (the legacy per-overlay AF-F4 no longer applies).
   c. **Contrast assert (AF-F2):** for every text element, sample the rendered PNG pixels in the text element's bounding region and behind it; compute the WCAG-AA contrast ratio (text luminance vs background luminance). Below 4.5:1 for normal text (or below 3:1 for large text >= 24px equivalent) = AF-F2 contrast auto-fail.
   d. **Legibility assert (AF-F3):** verify every text element renders at or above the minimum legible size (as a fraction of slide height) and is not clipped, truncated, or running off the slide edge = AF-F3 if it fails.
   e. **Image-position-variety assert (AF-F6, FIX-9):** record each slide's image zone (left / right / top / bottom / full-bleed / none). Walk the full slide sequence and flag any run of MORE THAN 2 CONSECUTIVE slides with the same image position = AF-F6. Additionally verify hook slides are type-driven (no image, or a <=15% opacity background image with large designed type over it); a hook slide with a full-strength image fails AF-F6.
   f. **Logo-identity assert (AF-F7, FIX-10):** where LOGO_ON_SLIDES = true, sample N logo-bearing slides, isolate the logo region on each, and diff them against one canonical reference logo lockup. Any drift in asset / crop / color / scale / chip / corner (e.g. a re-rendered mark or a different monogram variant on one slide) = AF-F7. Confirm logo-bearing slides were generated image-to-image (input_urls included LOGO_URL with the "reproduce pixel-for-pixel, do not redesign" instruction); an optional belt-and-suspenders is to composite one canonical logo PNG identically post-render.
   g. **Offer-slide price assert (AF-F8, FIX-10):** read the price rendered on the offer / CTA slide and assert it EQUALS FINAL_PRICE from price_ladder.json / intake.json. Any other number = AF-F8 (the $544-where-it-should-be-$97 class).
   h. **OCR-readback assert (AF-F9, FIX-11):** OCR the rendered text from each composed-slide PNG and diff it against the INTENDED copy string from slides_copy.md / the prompt for that slide. Any mismatch -- baked typo, garble, missing connector, or a leaked scene/stage-direction string -- = AF-F9 and the slide is re-rendered.
   i. **Build-token / placeholder assert (AF-F10, FIX-12):** on the same OCR text from each composed-slide PNG, run the blanket placeholder scan -- regex for any bracketed token `[...]`, plus a case-insensitive substring match on "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", "pending". Any match rendered on the slide face = AF-F10 and BLOCKS FINAL STATUS. This is unconditional (it does not require a copy-vs-pixel diff like AF-F9): a bracket token must never be composited. A copy-stage `[CLIENT TO SUPPLY]` placeholder is resolved with real interview-sourced content or the slide is pulled BEFORE render; if one reaches a rendered image, the slide is failed and routed back through the Slide Image Creator, plus a Director flag that the copy gate let an unresolved placeholder through to Phase 2.
   Record each slide's assert results (collision / contrast / legibility / image-position-zone / logo-identity / offer-price / ocr-readback, pass or the failing element) in the report.

2. **Visual re-verification of the per-slide gates on the composed output.** For each rendered page (slide), verify:
   a. All 17 image QC criteria (including the AF-I1 through AF-I10 auto-fail layer) are still satisfied in the rendered output. Images from Phase 5 that passed should still pass here; if they do not, it indicates an assembly error.
   b. All 17 copy QC criteria are satisfied in the text overlays and any PPTX-native text elements.
   c. **Image-grounding re-verification (P6, BLOCKING):** AF-I8 / criterion i15 re-checked on the composed slide -- does each people-slide or scene-slide image still depict a concrete moment from THIS client's method? An ungrounded image that slipped through fails here.
   d. **Designed-typography re-verification (BLOCKING):** AF-I9 / criterion i16 re-checked on the composed slide -- does the rendered type read as the designed weight-mapped system (dominating heavy-weight charcoal headline, real hierarchy, giant numbers at scale, gold caps kickers) and not a basic or default font? A basic-font or flat-hierarchy slide fails here.
   e. **Standalone-art re-verification (BLOCKING):** AF-I10 / criterion i17 re-checked on the composed slide -- pulled out alone, does the slide read as a finished, gallery-grade piece of art with its own felt beat, not "just a background with text"? A slide that fails the standalone test fails here.

3. **Deck-wide representation tally re-run (P5, AF-R2).** Re-run the step-5a tally on the FINAL assembled deck, because dropped, substituted, or re-cast slides can shift the distribution since Phase 5. If any captured REPRESENTATION_MIX group is outside +/- 10 percentage points = AF-R2 auto-fail on the deck. If people appear with no captured mix = AF-R3. Bidirectional (fails under-representation AND mono-casting); representation overrides skin-tone-quality.

4. **Structural-completeness checks (the governing intelligence: master Section 4.3 + Section 4.4 ten required components + the signature-presentation framework).** Verify, deck-wide, that the pitch and journey machinery AND every one of the operator's ten named required presentation components is present in the assembled deck (each missing item routes a revision instruction to the responsible author):
   a. **Cost-versus-value beat present (GP-9):** the deck contains an explicit cost-of-inaction AND value-of-action beat.
   b. **Dual emotion + logic track (GP-4):** for each key offer beat ask "does this beat serve BOTH the emotional buyer and the logical justifier?" An offer section that is all-emotion or all-math fails.
   c. **Light pitch distributed, not back-loaded (GP-11):** the program is named and referenced inside the teaching sections from the first verse, not only in the offer section.
   d. **Care-first open (SP-CARE):** "does the open care about the audience before it talks about the presenter?" A deck that opens on credentials before caring about the audience fails the open check.
   e. **PSD teaching pattern (SP-PSD):** "is each teaching slide a Point / Story / Demo structure?"
   f. **Journey / SEE (SP-JOURNEY / SP-SEE):** the deck is a JOURNEY, not a fact list; and per slide ask "does this slide create a felt moment (a Significant Emotional Experience), or just inform?"
   g. **Old-to-new bridge (SP-OLDNEW):** each new idea is anchored to something the audience already knows.
   h. **Teach-themselves (SP-TEACH):** the deck invites the audience to reach the conclusion themselves ("you already know..."), conversational rather than lecturing.
   i. **Not over-taught (GP-10):** "appetizer, not dinner" -- the teaching proves value and creates desire without handing over the complete HOW (which lives in the offer).
   j. **The Promise leads (master rule 2, component 1):** the deck identifies and leads with the core promise; teach/offer slides pitch the promise, not the product.
   k. **The Hook sings (master rule 1, component 2):** the verbatim hook stands on EXACTLY 3 to 4 DEDICATED pure-typography slides, NOWHERE ELSE, and never as a footer in the assembled deck (re-confirm the AF-HOOK ceiling survived assembly; over-stamping is the defect, not under-count).
   l. **Who says so / external proof present (master rule 12, component 3):** at least one third-party proof beat (case study / study / white paper) is woven between the drops. ZERO external proof in the assembled deck = fail; surface to the operator.
   m. **Wall of Wins present (master rule 20, component 4):** a wall-of-wins / wall-of-results slide concentrating multiple named wins exists near the close.
   n. **The Guarantee present (master rule 21, component 6):** an explicit guarantee / risk-reversal beat exists.
   o. **The Scarcity Factor present (master rule 21, component 7):** a real scarcity / last-calls / doors-closing beat exists in the close (real only; fake scarcity is a Devil's-Advocate blocking flag).
   p. **The Story Arc present (master rule 19, component 8):** an explicit short-term-fix-vs-long-term-identity contrast beat driving self-recognition exists.
   q. **Re-pitch present (FIX-7, copy QC c23):** a 4-7 slide recap + value-gap + promise + guarantee + objection-kill + reset-urgency block exists AFTER the FINAL price reveal and before the hook-reprise close. A deck whose price is revealed and then simply ends FAILS; route a revision instruction to the Slide Copywriter / Offer Price Strategist.
   r. **Close density / Wall-of-Wins spacing (FIX-8, copy QC c24):** the post-Wall close is never thinner than ~8 slides on a 45+ slide deck and the Wall of Wins does NOT sit within 2 slides of the final CTA; auto-flag a too-thin close.
   s. **Wall-of-Wins framing (FIX-6, copy QC c19):** the wall presents REAL named client results (>= 4 named clients with city + result number + aggregate band + a "these are your peers" line), NOT a future-paced "Watch What Changes" about the buyer's own outcome; the future-paced anti-pattern fails and rebuilds.
   (Note: items a, c, e, g, h, i, j, k, l, m, n, o, p, q, r, s are also enforced upstream at copy QC c15 / c1 / c11 / c18-c24; this is the deck-level confirmation that they survived into the assembled deck. One-big-idea-per-slide is enforced as copy-QC auto-fail AF-C6 upstream and re-confirmed per composed slide here. The gradual price ladder (component 9) is confirmed via the ladder-integrity re-check and the Offer Price Strategist gates. The checklist-is-a-list-of-promises (component 10) is the Director echo gate plus the existence of this PASS artifact, which IS the walked checklist. SP-LING / SP-LOCAL and the Michael-J figure are operator-supplied placeholders; they are checked as "placeholder present, not fabricated," never invented.)

5. **Additional final-deck-specific checks:**
   a. Slide order matches arc_allocation.json exactly.
   b. Speaker notes are present in the PPTX for every slide per presenter_notes.json.
   c. No slides are missing (total count matches slide_count_final in mission_prd.json).
   d. No images are stretched, cropped, or misaligned in the PPTX layout.
   e. Font embedding: if PPTX-native text is used, fonts are embedded (verify by opening in a clean environment without the brand fonts installed -- text should still display correctly).
3. **Density-floor-overhaul deck-level finishing gates (these BLOCK FINAL STATUS; run across ALL rendered pages):**
   a. **AF-PLACEHOLDER (re-scan):** scan every rendered page for any bracket/"owner to confirm"/placeholder token (regex `\[[^\]]*\]` + the token substrings). A single token on ANY page blocks final status. A placeholder must never reach a final deck.
   b. **AF-HOOK (deck re-verify):** the hook appears on at most 4 dedicated slides, is never footer-stamped, is verbatim and correctly spelled on every occurrence, and at least one dedicated typography hook slide exists. (AF-HOOK-1/2/3/5/6 across the assembled order.)
   c. **AF-I11 cross-slide logo-drift:** pull the logo region from every page and compare to the locked LOGO_URL asset. If any page's mark differs from the asset, OR two pages differ from each other, it is a deck-level logo-drift auto-fail. (This is the cross-slide check; the per-slide check ran at Phase 5.)
   d. **AF-D1 layout variety:** at least 3 distinct archetypes; no archetype over 60%; the five-part word-block stack on no more than 60% of slides.
   e. **AF-D2:** at least one dedicated pure-typography hook slide exists.
   f. **AF-D3 typography variety:** a locked weight ladder is evident (more than one headline weight); the single black-headline-plus-one-accent-word device on no more than 70% of slides; the gold/glow/strike price-type system is applied across the WHOLE ladder, not one beat.
   g. **AF-DEN (density re-verify against the final slide order):** all eight AF-DEN deck-level triggers (8-slide minimum gaps, anchor near one-third, BUILDUP before every DROP, value-stack before Drop 1, promises before anchor, Wall of Wins 4-6 before offer, 4-7 slide re-pitch after FINAL, section floors) hold in the assembled deck.
   h. **AF-AUD (deck re-verify):** no banned audience-facing category (speaker SAY line, internal doctrine caption, image narration, "webinar"/meta, credential dump) on any rendered page.
   i. **AF-COVERAGE-1 (assembled-deck re-verify):** count the assembled deck pages and compare to `mission_prd.source_slide_count`. If the final page count is below `source_slide_count` it is a deck-level anti-compression auto-fail (Mode A with `source_slide_count == 0` always passes). The system must NEVER output fewer slides than the client's source deck; Mode B is ADD-only.
4. Write final_deck_qc_report.json (include every triggered AF-PLACEHOLDER, AF-HOOK, AF-I11, AF-D1/D2/D3, AF-DEN, AF-AUD code by page).
5. If pass (all base criteria AND all density-floor-overhaul deck-level finishing gates clear): notify the Director that Phase 6 is complete and the deck is ready for delivery.
6. If fail: send specific revision instructions to the PPTX Assembly Specialist (and to the Slide Image Creator / Typography Architect / Offer Price Strategist / Slide Copywriter for the AF-I11 / AF-D / AF-DEN / AF-PLACEHOLDER classes respectively). A deck with any AF-PLACEHOLDER, AF-HOOK, AF-I11, AF-D, AF-DEN, or AF-AUD trigger is NOT final and does not reach the owner.

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
