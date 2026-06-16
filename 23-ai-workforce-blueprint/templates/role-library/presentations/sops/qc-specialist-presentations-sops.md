# SOPs Mirror -- QC Specialist (Presentations)

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
| AF-C2 | **(REPLACED 2026-06-14, density-floor overhaul.)** The OLD AF-C2 ("hook count below 7 = auto-fail") was the RETIRED historical FLOOR rule that PRODUCED the 40-slide footer-stamping. It is DELETED. The hook is now governed by the AF-HOOK ceiling battery below: the verbatim hook stands on 3-4 DEDICATED pure-typography A4 slides, total appearances ~4-5 max, NEVER 2 consecutive, never a footer on every slide (hook on MORE than 4 slides = fail; footer-stamped hook = fail; zero dedicated hook slides = fail). Over-stamping is the #1 defect; STRIP excess rather than pad. Do not re-introduce a hook floor. See universal-sops/presentation-slide-craft/SOP-SLIDE-03-HOOK-DOCTRINE.md. |
| AF-C3 | Any fabricated proof or statistic not traceable to intake.json or proof_audit.txt. A number not present in the intake or research brief = auto-fail on that slide. |
| AF-C4 | Any cross-slide numeric mismatch (e.g., stack total stated as $[STACK_TOTAL] on one slide and a different $[STACK_TOTAL] on another). Defer the Offer Strategist mechanics to SOP 9.3, but a FAIL there blocks this gate. The QC agent compiles all repeated numbers and diffs them; any mismatch auto-fails all slides carrying the inconsistent value. |
| AF-C5 | Headline over 9 words (mechanical word count; count is exact). |

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
| AF-P1 | Character count under 1500 (Check 0: count mechanically and RECORD the exact number in the report). |
| AF-P2 | Character count over 15000. |
| AF-P3 | Headline not verbatim to slides_copy.md HEADLINE field (any paraphrase, any changed word = auto-fail). |
| AF-P4 | Missing 16:9 or 2K (either absent = auto-fail). |
| AF-P5 | Dark background language present without DARK_OK = true. |
| AF-P6 | Missing thirds/zone language (explicit thirds placement for headline, people, and objects is required; "centered" alone is not thirds language). |
| AF-P7 | People are present in the slide spec but the prompt is missing any of: hair description, clothing description, or facial expression description. All three are required when people appear. |
| AF-P8 | Missing AVOID block (the closing constraints block listing negatives is mandatory in every prompt). |

#### Image QC Auto-Fails (SOP 9.3)

Check these before scoring. Each independently forces FAIL on the affected image.

| Code | Auto-Fail Condition |
|------|---------------------|
| AF-I1 | ANY misspelling, duplicated word, or garbled glyph in ANY rendered text anywhere on the slide. This applies to every word on the slide, not just the headline. Inspect all text elements. |
| AF-I2 | Any deformity: malformed hands, extra or missing fingers, distorted faces, warped or severed limbs. |
| AF-I3 | Wrong aspect ratio (must be 16:9; anything else = auto-fail). |
| AF-I4 | Missing or mangled logo when LOGO_ON_SLIDES = true (logo absent, illegible, distorted, recolored, clipped, incorrectly placed, **OR a DIFFERENT mark than the locked LOGO_URL asset** = auto-fail). (Extended for the density-floor overhaul: "differs from the locked asset" is now part of AF-I4.) |
| AF-I5 | Dark background without DARK_OK = true. |
| AF-I6 | Emoji or clipart glyphs rendered anywhere in the image. Premium decks use photography and typography only. |
| AF-I7 | An em dash rendered in slide text. |

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
2. Dispatch 3-5 QC agents (minimax-m3:cloud) each independently scoring slides_copy.md on all 17 criteria. Each agent returns a score per criterion per slide.
3. Average the agent scores for each criterion across all slides. Compute the overall average.
4. Apply double-weight to criteria 2, 5, 7, 12, 13, and 15 (these are the most critical -- see criteria list below). NOTE: the hook (old criterion 1) and the placeholder/audience-facing categories are no longer scored criteria at all -- they are now AUTO-FAILS (AF-HOOK, AF-AUD) that veto before scoring, so they cannot average away. One-big-idea (criterion 5) and slide-vs-script (criterion 13) remain as double-weighted scored criteria AND are backstopped by the AF-OBI and AF-AUD auto-fails.
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
2. Dispatch 5-10 QC agents (minimax-m3:cloud) in parallel. Each agent independently scores each prompt on all 15 criteria.
3. For each prompt, calculate the per-agent score, then average across all agents.
4. Apply double-weight to criteria 2, 3, 4, and 13 (the most commonly failing and highest impact).
5. Write prompt_qc_report.json. One entry per prompt (one per slide), including the recorded character count and any auto-fail codes.
6. For any prompt with an auto-fail or scoring < 8.5: write specific revision_instructions. Instructions must specify the failing auto-fail code or criterion and the exact change required.
7. Identify fail classification for each failing prompt: render-noise (image quality issues likely in generation), prompt-defect (structural problem with the prompt itself), or text-fail (headline text will not render correctly -- mark as text-fail-x2 if two text elements fail).
8. Pass: overall weighted average >= 8.5, no individual prompt below 7.0, no auto-fails. Fail: otherwise.
9. Increment loop_count. At loop_count = 4, escalate.

**The 15 Prompt QC Criteria (p1-p15):**
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
1. For every image, check ALL Image QC Auto-Fails BEFORE scoring: the seven base codes (AF-I1 through AF-I7, where AF-I4 now also fails a logo that DIFFERS from the locked LOGO_URL asset) AND the density-floor-overhaul render codes (AF-I8 footer-stamped hook, AF-I9 hook slide not pure-type, AF-I10 hook doubled/mutated on render, AF-I11 logo a different mark than the locked asset, AF-I12/AF-PLACEHOLDER any bracket/"owner to confirm" token rendered into the face, AF-I13 image-narration caption, AF-I14 speaker/doctrine/"webinar"/credential text on the face, AF-I15 a rendered text block beyond the three approved copy blocks, AF-I16 a rendered comparison table over 2 rows). A triggered auto-fail immediately marks the image FAIL; record the code(s) in the report. Auto-fail inspection includes: reading every word of rendered text on the slide for misspellings/duplicates/garbled glyphs AND for any banned audience-facing category (the word "webinar", speaker SAY phrasing, internal pitch-doctrine captions, image-narration captions, credential paragraphs) AND for any bracket/placeholder token (regex `\[[^\]]*\]` plus "owner to confirm" etc -- this BLOCKS FINAL STATUS); inspecting hands/faces/limbs for deformities; verifying aspect ratio; verifying the logo is present, integral, AND the SAME mark as the locked LOGO_URL asset; checking that dedicated hook slides are pure-typography (hook line over a low-opacity image, no footer band, printed once, verbatim); checking background darkness; scanning for emoji/clipart; checking rendered text for em dashes.
2. Dispatch up to 5 QC agents (minimax-m3:cloud) per batch of images. Each agent scores a non-overlapping batch (e.g., agent 1 handles slides 1-15, agent 2 handles slides 16-30, etc.).
3. Each agent scores each image on all 14 criteria.
4. Apply double-weight to criteria 3, 5, 6, and 7 (most critical for the assembled deck).
5. Write image_qc_report.json with per-image auto-fail codes and scores.
6. For each failing image (auto-fail or score < 8.5): classify the failure type:
   - `render-noise`: generation artifact, blurriness, corrupted output -- re-generate with the same prompt.
   - `prompt-defect`: the prompt produced the wrong composition or wrong mood -- send prompt back to Slide Image Creator for revision, then re-generate.
   - `text-fail`: the headline text is garbled, missing, or wrong -- if one text element is wrong, mark `text-fail-x1`; if two or more, mark `text-fail-x2`. Send back to Slide Image Creator with specific text correction instructions.
7. For render-noise failures: re-generate immediately (up to 3 attempts) without touching the prompt.
8. For prompt-defect or text-fail: send revision instructions to Slide Image Creator, then re-generate.
9. Maximum 3 total attempts per image. At attempt 4: escalate to the Director.
10. Passed images are moved to working/media-library/ immediately (do not wait for full deck pass).

**The 14 Image QC Criteria (i1-i14):**

AUTO-FAIL LAYER (checked first; see AF-I1 through AF-I7 above -- these override scoring):
- i-AF: Any of AF-I1 through AF-I7 triggers a hard FAIL before the scored layer runs.

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

**Outputs:**
- working/qc/image_qc_report.json (per-image auto-fail codes, scores, and classifications)
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

### SOP 9.5 -- Final Deck QC (Rendered Pages)

**When to run:** Phase 6 -- after the PPTX Assembly Specialist has assembled the deck and rendered it to PDF (via soffice --headless --convert-to pdf, then pdftoppm -png -r 100).

**Inputs:**
- The assembled PPTX file
- The PDF-rendered pages (PNG files at 100 DPI)
- working/copy/slides_copy.md (for copy verification in assembled deck)
- working/copy/presenter_notes.json (for speaker notes verification)

**Steps:**
1. Review the PDF-rendered pages visually. For each page (slide), verify:
   a. All 14 image QC criteria (including the auto-fail layer) are still satisfied in the rendered output (images from Phase 5 that passed should still pass here -- if they don't, it indicates an assembly error).
   b. All 17 copy QC criteria are satisfied in the text overlays and any PPTX-native text elements.
2. Additionally check 5 final-deck-specific criteria:
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
- working/qc/final_deck_qc_report.json

**Hand to:** Director (who initiates delivery)

**Failure mode:** If the PPTX file cannot be opened or rendered: escalate to the Director and PPTX Assembly Specialist immediately. Record the technical error in run_ledger.json.

---
