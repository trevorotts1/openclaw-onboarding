# MASTER QC AUTO-FAIL RULESET (SLIDE-CRAFT)

**Cluster:** Slide-Craft Rules (the single most important deliverable)
**Purpose:** the precise, machine-checkable list the integrator wires into qc-specialist-presentations.md so a deck CANNOT pass if it repeats the forensic failures.
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md
**How to use:** every rule below is an AUTO-FAIL. Auto-fails are checked FIRST, before any 1-to-10 scoring, exactly like the existing AF-C / AF-P / AF-I tables in the QC role. A triggered auto-fail forces FAIL on the affected slide (or the whole DECK where marked) regardless of any average. The QC report records the triggered code, the slide, and the failure message verbatim.
**Status:** Reference ruleset, RECONCILED with the live gate. This document is the authored slide-craft auto-fail doctrine; the named codes below (AF-HOOK, AF-AUD, AF-OBI, AF-DEN, AF-PLACEHOLDER) are the doctrine's own taxonomy. In the live qc-specialist-presentations.md these protections are ALREADY WIRED under the repo's existing code namespace (the FIX-1 through FIX-8 overhaul). Use the reconciliation map below to find each rule's live equivalent. Do NOT re-add a parallel AF-HOOK/AF-AUD/AF-OBI/AF-DEN namespace to the QC role; that work is done.

---

## RECONCILIATION MAP (this ruleset's codes to the LIVE qc-specialist codes)

The protections this ruleset specifies are already enforced in qc-specialist-presentations.md under these live codes and criteria:

| This ruleset (doctrine code) | LIVE enforcement already in qc-specialist-presentations.md |
|---|---|
| RULE 1 hook ceiling + anti-footer (AF-HOOK-1/2/3) | AF-C2 (banded hook cadence, fails BOTH ways: over-stamping on >~5 slides / 2+ consecutive / footer-on-every, AND under the 3-4 dedicated beats) + AF-P12 (prompt-side hook-overlay over-stamping; the literal phrase "present on every slide" is itself AF-P12) + copy QC c1 |
| RULE 2 audience-facing only (AF-AUD-1..5; "webinar") | AF-C9 (audience-facing forbidden-content battery: presenter narration, AI meta-commentary, image/scene description, telegraphing/stage-direction kickers, the literal word "webinar") + AF-F9 (OCR re-verify on the composed slide) |
| RULE 3 no bracket/placeholder token on a rendered slide (AF-PLACEHOLDER) | AF-F9 catches a leaked bracket as a copy-vs-pixel diff; the NET-NEW blanket bracket-token ban is added by this overhaul as AF-F10 (see qc-specialist-presentations.md Image/Final auto-fail table) |
| RULE 4 hook integrity: mutated/misspelled/duplicated/conflated (AF-HOOK-4/5/6/7) | AF-P3 (headline not verbatim to slides_copy.md = auto-fail) + AF-I1 (any misspelling/garbled glyph in rendered text) + AF-F9 (OCR diff) + AF-C2 (banded cadence) |
| RULE 5 one big idea (AF-OBI-1..6) | AF-C6 (multi-idea slide = auto-fail, "one big idea per slide; a slide that makes more than one point auto-fails") + AF-C8 (30-word total-density ceiling) + copy QC c5 |
| Section 2 density/pacing (AF-DEN-1..8) | AF-C7 (gradual-drop choreography, 4 sub-conditions: SPREAD / EARNED+BUILT-UP / ADDS-value / FINAL-below-ladder) + copy QC c17 (ladder integrity) + c19 (Wall of Wins framing) + c23 (re-pitch) + c24 (close density and Wall spacing) + the Offer Price Strategist SOP 9.1/9.2/9.9 gates |

The ONE genuinely net-new auto-fail this overhaul adds to the QC role is the blanket bracket-token-on-render ban (AF-F10), because the live AF-F9 caught a bracket only as a copy-vs-pixel diff, not as an unconditional ban that blocks FINAL on any `[...]` token. Everything else in this ruleset is already live; this document is the reference doctrine behind it.

Note on the spacing floor: this ruleset's AF-DEN-1 proposes an absolute "8-slide minimum gap"; the LIVE AF-C7 enforces "no 2 drops within 2 slides" plus the Offer Price Strategist percentage placement (~47/68/87% depth). The 8-slide figure is the gold-standard DOCTRINAL TARGET (gaps 11/16/14/8); the 2-slide minimum is the hard auto-fail floor. See SOP-PITCH-01 Section 2 rule 2 for the reconciliation. Do not introduce a contradictory hard 8-slide auto-fail without the Director adjusting AF-C7.

---

## 0. WHY DESCRIPTION ALONE FAILED (read before wiring)

PR #212 added 77 auto-fails and the FINAL deck STILL shipped the hook on 40 slides, the word "webinar", and raw "[owner to confirm]" placeholders. The lesson: a rule that is SCORED (averages away) or phrased as soft guidance ("the hook should recur as a refrain, not wallpaper") does not stop the defect. Every rule here is a BINARY TRIGGER with an exact detection method and a deck/slide-level veto. If a checker cannot mechanically evaluate it, it is not in this ruleset. The five things that must be impossible to ship are:

1. The hook on more than its dedicated slides (or footer-stamped).
2. Any banned audience-facing category on the face.
3. Any bracket/placeholder token on a rendered slide.
4. A misspelled or mutated hook.
5. More than one idea crammed on a slide.

Each maps to a numbered rule below.

---

## 1. THE FIVE LOAD-BEARING AUTO-FAILS (the ship-blockers)

These five are the spine. A deck that trips any of them is NOT final, full stop.

### RULE 1 -- HOOK CEILING + ANTI-FOOTER (deck-level veto)
- **Trigger 1a (AF-HOOK-1):** the verbatim hook (or any near-variant) appears on MORE than 4 slides. Detection: count slides where the canonical HOOK string from mission_prd.json (fuzzy match >= 0.85 to catch near-variants) appears in copy or rendered text. Count > 4 fails the DECK.
  - Failure message: `AF-HOOK-1: hook appears on {N} slides (max 4). Wallpaper detected. Remove from all but the 3-4 named anchor slides.`
- **Trigger 1b (AF-HOOK-2):** the hook appears in a footer / bottom-band / recurring-strip position on ANY slide. Detection: slide entry has TEXT_ANCHOR carrying the hook on a non-dedicated slide, OR the rendered image shows the hook in a bottom strip/band. Any occurrence fails that slide.
  - Failure message: `AF-HOOK-2: slide {N} footer-stamps the hook. The hook is never a footer. Delete the footer band.`
- **Trigger 1c (AF-HOOK-3):** zero dedicated typography hook slides exist. Detection: count of slides whose one big idea IS the hook = 0. Fails the DECK.
  - Failure message: `AF-HOOK-3: zero dedicated hook slides. Build 3-4 pure-typography hook slides at the named anchors.`

### RULE 2 -- AUDIENCE-FACING ONLY (slide-level veto, six categories)
- **Trigger 2a (AF-AUD-1):** a speaker SAY line on the face. Detection: line phrased as presenter speech (narrates the moment, "remember this", "stay right here", "hold on", first-person guide-talk) appears in slide copy or rendered text.
  - Failure message: `AF-AUD-1: slide {N} carries a speaker SAY line: "{line}". Route to the Presenter's Speech.`
- **Trigger 2b (AF-AUD-2):** internal pitch-doctrine printed as a caption. Detection: line restates a master Section 4.3 principle (price-vs-value mechanics, "the lower the price the greater the value", "in the next breath the real number").
  - Failure message: `AF-AUD-2: slide {N} prints internal build doctrine: "{line}". Section 4.3 is build-logic, never slide copy. Delete.`
- **Trigger 2c (AF-AUD-3):** image-narration caption. Detection: caption describes what the slide's own image brief already depicts.
  - Failure message: `AF-AUD-3: slide {N} narrates the image: "{line}". The audience can see it. Delete the caption.`
- **Trigger 2d (AF-AUD-4):** meta-telegraphing or the word "webinar" or a technique self-label. Detection: case-insensitive literal match on "webinar"; plus matches on "this is not just", "one last proof", "an intrigue gap", "hold onto this line", and other format/technique announcements.
  - Failure message: `AF-AUD-4: slide {N} telegraphs structure / uses a banned meta line: "{line}". Replace with a neutral label or delete.`
- **Trigger 2e (AF-AUD-5):** credential / justification dump on the face. Detection: resume/credential paragraph ("licensed", "clinical", "years in", "certified") as body copy.
  - Failure message: `AF-AUD-5: slide {N} dumps credentials: "{line}". Move to the Presenter's Speech (name-only on quote slides).`
- **Trigger 2f (AF-AUD-6):** see RULE 3 (placeholder on render); cross-listed here because it is also an audience-facing violation.

### RULE 3 -- NO BRACKET / PLACEHOLDER TOKEN ON A RENDERED SLIDE (slide-level veto, render stage)
- **Trigger 3 (AF-AUD-6 / AF-PLACEHOLDER):** any build token on a rendered image. Detection: regex on rendered text for `\[[^\]]*\]` (any bracketed token), plus case-insensitive substring match on "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", "pending". Any match on a RENDERED image fails that slide and BLOCKS FINAL STATUS.
  - Note: at COPY stage a `[CLIENT TO SUPPLY]` placeholder is permitted (it must be resolved or the slide pulled before render). This rule fires only on RENDERED images (Phase 5/6).
  - Failure message: `AF-PLACEHOLDER: slide {N} rendered with a build token: "{token}". Fill with the client's real interview-sourced content or pull the slide. A bracket token must never be composited.`

### RULE 4 -- HOOK INTEGRITY (slide-level veto, the sacred refrain)
- **Trigger 4a (AF-HOOK-4):** the hook printed 2+ times on one slide (bold copy plus ghosted italic repeat, or headline plus footer). Detection: per-slide count of hook occurrences >= 2.
  - Failure message: `AF-HOOK-4: slide {N} prints the hook {N} times. Print it once. Remove duplicates.`
- **Trigger 4b (AF-HOOK-5):** the hook mutated, extended, reworded, or abbreviated. Detection: character-exact compare of every occurrence against the canonical HOOK string in mission_prd.json; any difference fails.
  - Failure message: `AF-HOOK-5: slide {N} renders a mutated hook: "{rendered}" vs canonical "{canonical}". Restore the exact string.`
- **Trigger 4c (AF-HOOK-6):** the hook misspelled or garbled in a rendered image (e.g. "hclarity"). Detection: spell/glyph check on the rendered hook line (also caught by AF-I1; double-flagged because the hook is sacred).
  - Failure message: `AF-HOOK-6: slide {N} renders the hook misspelled: "{rendered}". Re-render; composite as native text if it garbles twice.`
- **Trigger 4d (AF-HOOK-7):** the signature quote slide also carries the main hook. Detection: the dedicated signature-quote slide contains the control-vs-clarity-style main hook.
  - Failure message: `AF-HOOK-7: slide {N} conflates the signature quote with the main hook. Keep them as separate beats.`

### RULE 5 -- ONE BIG IDEA (slide-level veto)
- **Trigger 5a (AF-OBI-1):** more than 3 text blocks on a slide. Detection: count HEADLINE + SUB-COPY + SUPPORTING plus any rendered text block not among those three; > 3 fails.
  - Failure message: `AF-OBI-1: slide {N} has {count} text blocks (max 3): {list}. Split or move the extra to the Presenter's Guide.`
- **Trigger 5b (AF-OBI-2):** headline over 9 words. Detection: exact word count of HEADLINE.
  - Failure message: `AF-OBI-2: slide {N} headline is {N} words (max 9). Two ideas. Split.`
- **Trigger 5c (AF-OBI-3):** two or more core ideas on one slide (diagnosis+method, gap+reframe, two assertions). Detection: QC agent identifies distinct claim count; >= 2 fails.
  - Failure message: `AF-OBI-3: slide {N} contains {N} core ideas: {A}; {B}. Split as: {proposed split}.`
- **Trigger 5d (AF-OBI-4):** a full value trio on one slide. Detection: three parallel named values co-present.
  - Failure message: `AF-OBI-4: slide {N} lists a full value trio ({values}) on one slide. Build 4 slides (one per value + a formula slide).`
- **Trigger 5e (AF-OBI-5):** a bulleted list of 2+ pains. Detection: multiple distinct pain statements as list items.
  - Failure message: `AF-OBI-5: slide {N} lists {N} pains as bullets. Each pain is its own slide with its own image. Build {N} slides.`
- **Trigger 5f (AF-OBI-6):** a comparison table with more than 2 contrast rows. Detection: rendered contrast-row count > 2.
  - Failure message: `AF-OBI-6: slide {N} renders a {N}-row table. Reduce to the single sharpest contrast or move the table to the Presenter's Guide.`

---

## 2. DENSITY / PACING AUTO-FAILS (deck-level veto; from SOP-SLIDE-04)

These are deck-level and are evaluated against arc_allocation.json and slide order. They are auto-fails, not scored, because a crammed offer was the root of the forensic-deck 2/10 pitch.

- **AF-DEN-1:** any two adjacent price beats < 8 slides apart. `AF-DEN-1: {beatA}@{X} and {beatB}@{Y} are {gap} slides apart (min 8).`
- **AF-DEN-2:** anchor outside 25-45% depth. `AF-DEN-2: anchor at {pct}% (target ~one-third).`
- **AF-DEN-3:** a DROP with no BUILDUP immediately before it. `AF-DEN-3: {drop}@{X} has no BUILDUP before it.`
- **AF-DEN-4:** no itemized value-stack slide before Drop 1. `AF-DEN-4: no value-stack slide before Drop 1.`
- **AF-DEN-5:** no promises beat before the anchor. `AF-DEN-5: no promises slide before the anchor.`
- **AF-DEN-6:** Wall of Wins not 4-6 slides before the offer. `AF-DEN-6: Wall of Wins {gap} slides before offer (target ~5).`
- **AF-DEN-7:** no 4-7 slide re-pitch block after FINAL. `AF-DEN-7: {N} post-FINAL slides, no re-pitch block (need 4-7).`
- **AF-DEN-8:** any section below its minimum slide count. `AF-DEN-8: {section} has {N} slides (floor {M}).`

---

## 3. THE CHECK ORDER (how QC runs this ruleset)

1. **Phase 1Q (copy stage, on slides_copy.md + arc_allocation.json + hook_package.json + audience_say_tags.json):** run RULE 1 (1a, 1c), RULE 2 (2a-2e), RULE 4 (4a, 4b, 4d), RULE 5 (5a-5e), and all of Section 2 (density). These are checkable from copy and arc. Trigger 1b footer is checkable from copy (TEXT_ANCHOR carrying the hook on a non-dedicated slide).
2. **Phase 5 (render stage, on each rendered image):** run RULE 1b (rendered footer), RULE 3 (placeholder on render), RULE 4 (4c misspelled hook, plus re-verify 4a/4b on the rendered face), RULE 5 (5a/5f for rendered text blocks and tables), and RULE 2 (2c image-narration, 2f placeholder) against the rendered face.
3. **Phase 6 (final deck, on the assembled PDF pages):** re-run RULE 3 and RULE 4c across all pages (a placeholder or a misspelled hook on ANY page blocks final status), confirm RULE 1 deck-level counts hold in the assembled order, and confirm Section 2 density against the final slide order.
4. **Veto semantics:** a slide-level trigger fails that slide and loops it; a DECK-level trigger (RULE 1a/1c, all of Section 2) fails the entire gate. No averaging. No "almost passed". The auto-fail is checked before scoring and the failing item receives no score.

---

## 4. REQUIRED WIRING (what the integrator changes in qc-specialist-presentations.md)

1. **Add a Slide-Craft auto-fail table** (RULES 1, 2, 4, 5 above) to the Copy QC Auto-Fails section (alongside AF-C1..C5), checked at Phase 1Q before scoring.
2. **Add a Render auto-fail table** (RULE 1b rendered, RULE 3 placeholder, RULE 4c, RULE 2c/2f, RULE 5a/5f rendered) to the Image QC Auto-Fails section (alongside AF-I1..I7), checked at Phase 5/6 before scoring.
3. **Add the Density auto-fail table** (Section 2) as a new deck-level gate run at Phase 1Q and re-verified at Phase 6.
4. **Replace AF-C2** (the current "hook count BELOW 7 = auto-fail" floor) with RULE 1 (the ceiling). This is the single most important change: the old floor PRODUCED the 40-slide stamping.
5. **Promote one-big-idea (criterion 1) and audience-facing (criterion 13) from scored criteria to double-weighted auto-fails** via RULE 5 and RULE 2; they no longer average away.
6. **Add the placeholder-on-render ban as a hard finishing failure that blocks FINAL status** (RULE 3), and extend the native-text fallback from price-only to the hook line (so RULE 4c cannot recur).
7. **Update the QC role KPI** "Auto-fail detections caught before owner sees work = 100%" to explicitly include the new codes, and add to the weekly QC Trend Report a per-code count for AF-HOOK, AF-AUD, AF-PLACEHOLDER, AF-OBI, and AF-DEN.

---

## 5. THE MACHINE-CHECKABLE SUMMARY TABLE (one row per auto-fail, the wireable list)

| Code | Stage | Level | Trigger (one line) | Detection |
|---|---|---|---|---|
| AF-HOOK-1 | 1Q/5/6 | DECK | hook on > 4 slides | count fuzzy-matched hook occurrences across deck |
| AF-HOOK-2 | 1Q/5/6 | slide | hook in a footer/band position | TEXT_ANCHOR or rendered bottom strip carrying the hook on a non-dedicated slide |
| AF-HOOK-3 | 1Q | DECK | zero dedicated hook slides | count of slides whose one idea IS the hook = 0 |
| AF-HOOK-4 | 1Q/5 | slide | hook printed 2+ times on one slide | per-slide hook occurrence count >= 2 |
| AF-HOOK-5 | 1Q/5/6 | slide | hook mutated/extended/reworded | char-exact compare to canonical HOOK string |
| AF-HOOK-6 | 5/6 | slide | hook misspelled/garbled on render | spell/glyph check on rendered hook line |
| AF-HOOK-7 | 1Q/5 | slide | signature quote conflated with main hook | main hook present on the signature-quote slide |
| AF-AUD-1 | 1Q/5 | slide | speaker SAY line on the face | presenter-speech phrasing in slide/rendered text |
| AF-AUD-2 | 1Q/5 | slide | internal pitch doctrine as caption | restates a Section 4.3 principle |
| AF-AUD-3 | 1Q/5 | slide | image-narration caption | caption describes what the image already shows |
| AF-AUD-4 | 1Q/5 | slide | meta-telegraph / "webinar" / technique label | literal "webinar" + format/technique-announcement match |
| AF-AUD-5 | 1Q/5 | slide | credential/justification dump | resume/credential paragraph as body copy |
| AF-PLACEHOLDER (AF-AUD-6) | 5/6 | slide (blocks FINAL) | bracket/placeholder token on a rendered slide | regex `\[[^\]]*\]` + token substrings on rendered text |
| AF-OBI-1 | 1Q/5 | slide | > 3 text blocks | count of text blocks > 3 |
| AF-OBI-2 | 1Q | slide | headline > 9 words | exact word count |
| AF-OBI-3 | 1Q | slide | 2+ core ideas | distinct-claim count >= 2 |
| AF-OBI-4 | 1Q | slide | full value trio on one slide | three parallel named values co-present |
| AF-OBI-5 | 1Q | slide | bulleted pain list | 2+ distinct pains as list items |
| AF-OBI-6 | 5 | slide | comparison table > 2 rows | rendered contrast-row count > 2 |
| AF-DEN-1 | 1Q/6 | DECK | price beats < 8 slides apart | gap between adjacent LADDER tags |
| AF-DEN-2 | 1Q/6 | DECK | anchor outside 25-45% depth | anchor position / total |
| AF-DEN-3 | 1Q/6 | DECK | DROP with no BUILDUP before it | slide before each DROP not tagged BUILDUP |
| AF-DEN-4 | 1Q/6 | DECK | no value-stack slide before Drop 1 | no itemized-stack slide before first DROP |
| AF-DEN-5 | 1Q/6 | DECK | no promises beat before anchor | no promises slide before ANCHOR |
| AF-DEN-6 | 1Q/6 | DECK | Wall of Wins not 4-6 before offer | WoW position vs offer position |
| AF-DEN-7 | 1Q/6 | DECK | no 4-7 slide re-pitch after FINAL | post-FINAL slide count / content |
| AF-DEN-8 | 1Q/6 | DECK | section below its slide floor | per-section slide count vs floor |
| AF-SPEECH-SHORT | 9 | DECK | presenter speech words < target_talk_minutes x 120 wpm (too short for the requested duration) | `word_count(speech.md) < round(intake.target_talk_minutes * 120)`; enforced by build_deck `_chk_speech_length` (conditional: fires once the speech exists) |


| AF-RENDERER | Phase 4/6 | DECK | Deck shipped its own renderer instead of calling the canonical render module | render_manifest.json missing OR render script is not the canonical 23-ai-workforce-blueprint/templates/presentation-render/render_deck.py |
| AF-MODEL-SOVEREIGNTY | Phase 4/6 | DECK | Submitted model does not match client's pinned model with no logged fallback event | render_manifest.json model_used != intake.json model_pin AND no fallback_events entry for that slide |
| AF-BAKED | Phase 5/6 | slide (blocks FINAL) | Slide text was drawn by Pillow/PPTX/ImageDraw rather than baked by the image model, OR slide is a flat placeholder fill with no Kie render | Vision QC agent confirms: text is overlaid, not rendered; OR image dimensions/size match known placeholder signatures |
| AF-PROMPT-FLOOR | Phase 3 | slide | Image prompt outside 5000-18000 chars OR missing required structural blocks | len(prompt) < 5000 OR len(prompt) > 18000 OR prompt missing [ARCHETYPE, NEGATIVE BLOCK, "Do not " imperatives] (reconciled v12.7.1 from 1500/15000 to match the live AF-P1/AF-P2 floor/ceiling so the canonical render module never hard-blocks a prompt the QC gate would pass; 18000 = 2000-char safety margin below the 20000 GPT-Image 2 API ceiling, MODEL-SPECS) |
| AF-NO-VISION-QC | Phase 6 | DECK | Deck submitted without an executed vision-QC log (path.exists() is not vision QC) | working/qc/vision_qc_log.json missing OR empty OR contains only path-existence checks with no vision API call records |
| AF-CONVERTER-PARITY | Phase 1Q | DECK (converter-origin only) | Converter-origin deck (intake.json source_brief_origin: "role-22") failed the runtime parity gate | Any of: render_manifest.json absent or not canonical; model pin mismatch; vision_qc_log.json missing/empty/path-only; research brief absent or Category E/F missing; persuasion variables (GOAL/CTA_ACTION/TRANSFORMATION_PROMISE/PRIMARY_OBJECTION/TARGET_FEELING/TONE) absent from intake.json without being listed in fields_absent_in_source |

Every row is a binary trigger with an exact detection method and a verbatim failure message (Section 1 and 2). Wire them as auto-fails, checked before scoring. A deck that trips any DECK-level row, or any slide that trips a slide-level row, cannot be marked final.

---

## 7. NEW AUTO-FAIL CODES -- 2026-06-15 PRESENTATION-DEPT-V2 ENFORCEMENT OVERHAUL

These ten codes close the remaining gaps found in the Presentation Department V2 forensic analysis. Each code is authored as doctrine here and wired as a mechanical check in `qc-specialist-presentations.md` (and its SOP mirror). Every rule is in BOTH the producing role AND the auto-fail gate.

### Code Index

| Code | Workstream | Gate phase | Scope | What it blocks |
|------|-----------|-----------|-------|----------------|
| `AF-I11` | Deck-quality / real-image | Phase 5 image QC | slide | image slide ships with no real generated raster (>=1920px) / icon-glyph / clipart / emoji as content art |
| `AF-I12` | Deck-quality / invisible-asset | Phase 5/6 | slide | invisible / vanishing asset (e.g. white-on-white glyph) -- asset-vs-background contrast near zero |
| `AF-I13` | Deck-quality / duplicate-glyph | Phase 5/6 | DECK | same md5-identical decorative asset reused as content more than 2x across the deck |
| `AF-F12` | Deck-quality / font-floor | Phase 6 final deck | slide | rendered body/run text below 18pt-equivalent absolute floor |
| `AF-F13` | Deck-quality / type-scale | Phase 6 | DECK | more than 4-5 type-scale steps OR platform-default font family (Calibri / Arial / system look) on render |
| `AF-F14` | Deck-quality / template-uniformity | Phase 6 | DECK | more than 2 structurally identical section-divider slides OR dividers+recap slides exceed ~20% of slide count |
| `AF-C10` | Deck-quality / no-transcript | Phase 1Q copy QC | slide | verbatim / near-verbatim spoken-transcript line used as slide copy |
| `AF-C11` | Deck-quality / persuasion-arc | Phase 1Q | DECK | missing one or more required arc beats (hook / stakes / promise / proof) OR no explicit CTA |
| `AF-DH1` | Deliverable hygiene | Closeout / pre-delivery | package (DECK) | dev artifacts in the client package / file not in the allowed five-file set / presenter guide or speech as .md instead of .pdf |
| `AF-RESEARCH-GATE` | Research mandate | Phase 1Q | DECK | Research Brief absent / `research_complete: false` / missing required categories A, C, D, F, G, H, I, K, or L (J condensed-OK) / fact-validation ledger absent when slide-bound figures exist |

---

### AF-I11 -- Real-Image-Present (slide-level, Phase 5)

**Doctrine:** A slide whose archetype or layout template calls for visual content ships with no real generated raster (>=1920px on the long edge), OR ships with a decorative icon-font glyph, a single-color clip-art PNG <=256px, or an emoji standing in for slide art. This is the image-present companion to AF-I6 (which bans clipart/emoji on ANY slide); AF-I11 specifically targets slides where a real raster is REQUIRED by the archetype and was never generated.

**Detection:** Inspect embedded media dimensions. If the nominal "image" element is an icon-font glyph (vector or tiny raster), a single-color PNG under 256px on the long edge, or an emoji character, it is not a real raster. Any image slide whose media element fails the >=1920px test auto-fails.

**Producing-role requirement (Slide Image Creator):** Every non-pure-typography slide must specify a real generated raster (Kie / GPT-Image-2) at >=1920px on the long edge, full-bleed or designed-zone, sourced from the Category E grounded anchor. Decorative icon-font glyphs, single-color clip-art PNGs <=256px, and emoji-as-iconography are forbidden as slide content art.

**Failure message:** `AF-I11: slide {N} carries no real generated raster (>=1920px). The archetype requires an image; a decorative icon/glyph/emoji is not a slide image. Generate a real raster via the canonical render pipeline.`

---

### AF-I12 -- Invisible / Vanishing Asset (slide-level, Phase 5/6)

**Doctrine:** Any embedded image asset whose mean luminance against the pixels directly behind it falls below a visibility delta (the asset effectively disappears into the slide background -- e.g. an all-white glyph on an off-white or white background) auto-fails that slide. This is the asset-side companion to AF-F2 (which covers TEXT contrast only); AF-I12 covers decorative or structural image assets that vanish into the background.

**Detection:** Composite the asset over its slide region at the slide's background color. Compute the asset-vs-background contrast ratio or edge-energy. A near-zero delta (asset is effectively invisible) triggers the fail. A white-on-white asset, a light-grey-on-white asset, or any asset whose edge-energy falls below a perceptible threshold triggers AF-I12.

**Failure message:** `AF-I12: slide {N} contains an invisible / vanishing asset (asset disappears into the background -- near-zero contrast). Remove or replace with a visible, contrast-passing asset. See AF-F2 for the text-contrast companion.`

---

### AF-I13 -- Duplicate-Glyph Filler (deck-level, Phase 5/6)

**Doctrine:** The same md5-identical decorative asset reused as slide content more than 2 times across the deck is the signature of decorative filler rather than genuine content (e.g. the same checkmark or abstract glyph used 12 times across different slides, or used 7 times on a single recap slide). This is a deck-level auto-fail.

**Detection:** Compute the md5 hash of every embedded image asset across all slides. Count occurrences of each unique hash across the deck. Any hash that appears as content on more than 2 slides triggers the deck-level fail.

**Producing-role requirement (Slide Image Creator):** Generate unique, content-appropriate raster art per slide. Decorative filler assets may not stand in for real visual content.

**Failure message:** `AF-I13: DECK FAIL -- md5 asset {hash} appears on {N} slides as slide content (max 2). This is the duplicate-glyph-filler signature. Generate unique raster art for each slide.`

---

### AF-F12 -- Minimum-Font Floor (slide-level, Phase 6)

**Doctrine:** Any rendered body or run text below 18pt-equivalent at the deck's canvas size is a presentation-distance failure. A deck that is effectively a document (with 10-12pt body text) cannot be read from a presentation screen. This is the absolute-pt companion to AF-F3 (fraction-of-height check).

**Detection:** At Phase 6, for each slide in the assembled deck, measure the rendered pt size of every text run. Any run below 18pt-equivalent (computed as the fraction of the slide's total height that corresponds to 18pt in a 1920px-wide render) triggers the fail on that slide.

**Producing-role requirement (Typography Architect):** The type-layout system must declare an absolute minimum body size of 18pt. The system file `working/typography/type_layout_system.md` must record this as a machine-readable token so QC can assert it.

**Failure message:** `AF-F12: slide {N} renders text at {pt}pt-equivalent (minimum 18pt). Revise the type-layout system to enforce the 18pt absolute floor for all body runs.`

---

### AF-F13 -- Type-Scale / Default-Font Discipline (deck-level, Phase 6)

**Doctrine:** A deck that uses more than the declared 4-5 type-scale steps (the "16 random point sizes" defect) OR that renders in a platform-default family (Calibri, Calibri Light, Arial, or any system default look) is a deck-level auto-fail. This is the scale-discipline companion to AF-P10/AF-I9 (which assert designed typography); AF-F13 adds the step-count assert and the assembled-deck default-font scan.

**Detection:** At Phase 6, enumerate all font families and pt sizes in the assembled deck. If the unique-family set includes a platform-default family, or if the count of distinct pt sizes exceeds the declared 4-5 scale steps from `type_layout_system.md`, fail the deck.

**Producing-role requirement (Typography Architect):** Declare exactly 4-5 type-scale steps and a non-default brand font pairing. Record both as machine-readable tokens in `working/typography/type_layout_system.md`.

**Failure message:** `AF-F13: DECK FAIL -- {N} distinct type sizes detected (declared 4-5 scale) OR platform-default font family found ({family}). The Typography Architect must enforce the declared type scale and a designed font pairing.`

---

### AF-F14 -- Template-Uniformity / Empty-Divider Padding (deck-level, Phase 6)

**Doctrine:** More than 2 section-divider slides that are structurally identical (same layout template, only the label text changes) OR a deck where divider plus recap slides exceed approximately 20% of total slide count auto-fails as a deck that pads thin content behind structural repetition.

**Detection:** Compute a structural hash of each divider slide (layout, zone counts, image zone, ignoring text content). If more than 2 divider slides share the same structural hash, fail. Compute the ratio of divider + recap slides to total deck slide count; if it exceeds ~20%, fail.

**Producing-role requirement (Typography Architect + Slide Image Creator):** Section dividers may not be byte-identical with one label swapped. Each archetype template must declare a focal point, whitespace strategy, and a varied composition. The design-brief Category F input from the Deep Research Specialist must be consulted before authoring divider templates.

**Failure message:** `AF-F14: DECK FAIL -- {N} structurally identical section dividers detected (max 2) OR divider+recap slides = {pct}% of deck (max ~20%). Each divider must have a distinct composition. Revise the type-layout system and divider archetype templates.`

---

### AF-C10 -- Verbatim-Transcript Leak (slide-level, Phase 1Q)

**Doctrine:** Slide copy that is a verbatim or near-verbatim spoken-transcript line -- informal spoken cadence, dictation artifacts, conversational asides, coaching dialog -- rather than authored slide copy fails that slide. The transcript is source material, not output. This is distinct from AF-C9 (which bans presenter narration and meta-commentary); AF-C10 bans raw transcript bullets that read as informal "content."

**Detection:** At Phase 1Q, scan each slide's copy for spoken-cadence markers: sentence fragments ending in trailing particles, "you know," "right," "basically," filler words carried from transcription, informal dictation phrasing, or copy that reads as an interrupted spoken sentence rather than a crafted headline/sub.

**Producing-role requirement (Slide Copywriter):** Slide copy must be AUTHORED from the source material. The transcript is input only. Spoken-quote artifacts from a raw coaching/transcript session are forbidden on the slide face.

**Failure message:** `AF-C10: slide {N} carries a verbatim/near-verbatim transcript line as slide copy: "{line}". Author the copy from the source; the transcript is input, not output.`

---

### AF-C11 -- Missing Persuasion Arc / No CTA (deck-level, Phase 1Q)

**Doctrine:** A deck that lacks one or more of the five required arc beats {hook, stakes, promise, proof, explicit CTA} across the deck as a whole fails as structurally incomplete. A deck that is "all telling, no showing" with no CTA is not a complete persuasion vehicle.

**Detection:** At Phase 1Q, assert that each arc beat is tagged or present in `slides_copy.md`. Check for: (1) a dedicated hook slide or opening hook beat, (2) a stakes / problem slide identifying what is at risk, (3) a promise slide or offer-promise beat, (4) a proof slide carrying external corroboration, (5) an explicit CTA slide or closing CTA beat. Any missing beat fails the deck.

**Note:** AF-C11 complements AF-C2 (hook cadence). AF-C2 checks the hook's stamping pattern; AF-C11 checks the structural completeness of all five arc beats as a whole.

**Producing-role requirement (Slide Copywriter):** The deck must carry a complete persuasive architecture: hook -> stakes -> promise -> proof -> CTA. All five beats are required.

**Failure message:** `AF-C11: DECK FAIL -- missing arc beat(s): {missing_beats}. A deck must carry hook + stakes + promise + proof + CTA. Add the missing beat(s) before Phase 1Q can pass.`

---

### AF-DH1 -- Deliverable Hygiene (package-level, pre-delivery closeout)

**Doctrine:** The client-deliverable package must contain EXACTLY the five allowed files and NOTHING ELSE. Any dev artifact, script, log, manifest, QC report, or markdown-format presenter guide reaching the client package is a hygiene failure. AF-DH1 is a file-system enumeration executed mechanically by the Delivery Concierge at SOP 9.0 (Package Assembly and Hygiene Sweep) before any upload. This gate is complementary to AF-DELIVER (which checks the three required artifacts EXIST and are non-empty); AF-DH1 checks the package contains ONLY the allowed set and NO dev artifacts.

**THE FIVE ALLOWED FILES:**
```
[DECK_SLUG]-FINAL/
  [Deck-Title]-FINAL.pptx          # assembled deck
  [Deck-Title]-FINAL.pdf           # portable-document export
  PRESENTER-GUIDE.pdf              # rendered from working/deliverables/PRESENTER-GUIDE.md
  PRESENTER-SPEECH.pdf             # rendered from working/deliverables/PRESENTER-SPEECH.md
  PRESENTER-AUDIO.mp3              # Fish Audio S2 render
```

**Blocklist (any match = auto-fail):**
- File extensions: `*.py`, `*.log`, `*.txt` (prompt files)
- File name patterns: `*_manifest.json`, `*_qc_log.json`, `*_run.log`, `fix_*.py`, `run_*.py`, `write_*.py`, `validate_*.py`, `assemble_*.py`, `post_render*.py`, `*QC-FINAL.md`, `vision_qc_log.json`, `render_manifest.json`
- Directories present in the package: `working/`, `prompts/`, `images/`, `renders/`, `qc/`, `scripts/`, `checkpoints/`
- Any presenter guide or speech as `.md` (must be `.pdf`)

**Whitelist (primary check):** Every file in the package must match one of the five allowed names. The whitelist is the primary gate; the blocklist is belt-and-suspenders.

**Producing-role requirement (Delivery Concierge):** SOP 9.0 (Package Assembly and Hygiene Sweep) creates a clean `delivery/[DECK_SLUG]-FINAL/` directory, copies only the five allowed files into it, runs AF-DH1, and only then proceeds to SOP 9.1.

**Producing-role requirement (PPTX Assembly Specialist):** The assembly script writes the PPTX to `output/[DECK_SLUG].pptx` and ALL intermediates under `working/`. The assembly script at `working/scripts/assemble_pptx.py` must NEVER hard-code the client delivery folder (such as `BUNDLE_DIR = ~/Downloads/<DECK>`) as the working directory or the output path. Dev artifacts do not appear in `output/` or `delivery/` under any circumstance.

**Failure message:** `AF-DH1: DELIVERY BLOCKED -- package hygiene fail. {details: specific file or directory that triggered the fail}. The client package must contain exactly the five allowed files. Remove all dev artifacts before delivery.`

---

### AF-RESEARCH-GATE -- Research Brief Required (deck-level, Phase 1Q)

**Doctrine:** A deck that reaches Phase 1Q without a complete Research Brief from the Deep Research Specialist (ROLE-04) is blocked. The Research Phase (-0.5) is mandatory on EVERY deck run -- personal or general, webinar or content-to-presentation. The gate fires at Phase 1Q so the block is caught before copy is approved and resources are committed to prompt and image generation.

**Detection (all conditions must be satisfied for PASS; any failure triggers the gate):**
1. `working/research/brief-[DECK_SLUG].md` exists on disk at Phase 1Q.
2. The file's header records `research_complete: true`.
3. The file contains the four ALWAYS-REQUIRED category sections: Category A (Niche Deck Structures), Category C (Supporting Statistics / Studies / White Papers), Category D (External Corroboration), and Category F (Design + Hook + Pacing Best-Practices).
4. The file contains the VALIDATION + PERSUASION category sections added by the 2026-06-16 ROLE-04 mandate overhaul: Category G (Credible Attributable Quotes), Category H (Fact-Validation -- Slide-Claim Verification Ledger), Category I (Objection Research), Category K (Persuasion-Framework Validation), and Category L (Compliance Flags). Category J (Social-Proof Patterns) is required-but-may-be-condensed and is not a hard gate condition. Category B (Pricing & Value Benchmarking) and Category E (Grounded Image Context) are checked by their own role gates (Offer Price Strategist and Gate 5 respectively) and the AF-CONVERTER-PARITY gate for converter runs.
5. When Category H records any slide-bound figure, the ledger `working/research/fact-validation-[DECK_SLUG].md|json` must exist and carry `verified_count` / `flagged_count` / `kill_count` (the upstream partner to AF-C3 / AF-C4 / AF-PRICE-FACE -- no invented figure reaches a slide).

**Failure response:** QC notifies the Director: "AF-RESEARCH-GATE: Phase 1Q blocked. Research Brief absent or incomplete. ROLE-04 must complete Phase -0.5 before copy QC can proceed." Record `af_research_gate_triggered: true` in `copy_qc_report.json`. The Director cannot advance to owner approval (Phase 1A) until the brief is on disk and complete.

**Producing-role requirement (Director of Presentations):** Step 5a (post-brief-lock, pre-Phase-B+): dispatch ROLE-04 as Phase -0.5. Block Phase B+ (Hook Strategist) until `working/research/brief-[DECK_SLUG].md` exists and records `research_complete: true`.

**Producing-role requirement (Content-to-Presentation Architect):** The Director MUST dispatch ROLE-04 as Phase -0.5 unconditionally on ALL content-to-presentation builds, regardless of `proof_flags`.

**Failure message:** `AF-RESEARCH-GATE: DECK FAIL at Phase 1Q -- Research Brief missing or incomplete. Brief path: working/research/brief-{DECK_SLUG}.md. Required: exists + research_complete: true + sections A, C, D, F, G, H, I, K, L present (J condensed-OK); and the fact-validation ledger present when any slide-bound figure exists. Dispatch ROLE-04 Phase -0.5 and complete the brief before re-running Phase 1Q.`

---

### AF-CONVERTER-PARITY -- Converter-Origin Runtime Parity Gate (deck-level, Phase 1Q)

**Doctrine:** A deck whose `intake.json` carries a `source_brief_origin: "role-22"` field (set by the Director SOP 9.1 step 4a when a `source_brief.json` from the Content-to-Presentation Architect accompanies the brief) MUST have used the IDENTICAL pipeline as a regular deck. No converter-specific image path, renderer, model choice, text-baking path, or QC log is permitted. Per "enforcement, not description -- a rule not auto-failed at the QC gate does not exist," every converter-parity invariant is a binary auto-fail checked at Phase 1Q by the SAME single QC Specialist that scores regular decks.

**Condition (all five must be satisfied for PASS; any failure triggers AF-CONVERTER-PARITY for the DECK):**

1. **Canonical renderer used:** `render_manifest.json` exists AND its `module_version` key proves it was written by the canonical `23-ai-workforce-blueprint/templates/presentation-render/render_deck.py` (re-uses AF-RENDERER logic). No throwaway renderer was used.

2. **Model pin held on a converter run:** `render_manifest.json model_used` per slide == `intake.json model_pin` with no undocumented fallback (re-uses AF-MODEL-SOVEREIGNTY logic). The gpt-image-2 pin applies to converter runs exactly as it applies to regular runs.

3. **Real vision QC executed:** `working/qc/vision_qc_log.json` exists, is non-empty, and carries at minimum one entry per slide with a non-null `vision_api_response` field (re-uses AF-NO-VISION-QC logic). A log that records only path-existence checks with no vision API call records is NOT real vision QC.

4. **Phase -0.5 Research Brief present and complete:** `working/research/brief-[DECK_SLUG].md` exists on disk with `research_complete: true` in its header AND the files `working/research/grounded-content-[DECK_SLUG].json` and `working/research/design-brief-[DECK_SLUG].md` exist (Category E and Category F delivered to the image stage). This proves the Slide Image Creator received grounded scene context specific to this source, not generic stock direction.

5. **Persuasion intelligence propagated into intake:** `intake.json` carries the persuasion variables (GOAL, CTA_ACTION, TRANSFORMATION_PROMISE, PRIMARY_OBJECTION, TARGET_FEELING, TONE) as non-null values (or, for each field, documented as listed in `source_brief.json.persuasion_intelligence.fields_absent_in_source`). When the source contained an offer, OFFER_NAME, PRICE_MODE, and FINAL_PRICE must also be non-null. This proves SOP 9.4B actually ran and Fix-A's persuasion intelligence propagated -- so the deck is persuasive, not a teaching dump.

**Producing-role requirements:**
- **Content-to-Presentation Architect (ROLE-22):** SOP 9.4B must run and write the `persuasion_intelligence` block to `source_brief.json` before handoff. The brief MUST carry `persuasion_intelligence_complete: true`. No image path, renderer, or model is owned here; all image work routes through the shared pipeline.
- **Director of Presentations:** SOP 9.1 step 4a must propagate the `persuasion_intelligence` block into `intake.json` AND set `source_brief_origin: "role-22"` so the QC gate can identify converter-origin decks. Must satisfy the mandatory-variable check from `persuasion_intelligence` FIRST before routing gaps to the Brainstorming Buddy.
- **Deep Research Specialist (ROLE-04):** must run unconditionally as Phase -0.5 on all converter runs and produce `working/research/brief-[DECK_SLUG].md` (`research_complete: true`), `grounded-content-[DECK_SLUG].json`, and `design-brief-[DECK_SLUG].md` before Phase B+ begins.

**QC Specialist run-list addition:** After completing all other Phase 1Q auto-fail checks, the QC Specialist checks `intake.json` for `source_brief_origin: "role-22"`. If present, AF-CONVERTER-PARITY is checked. If the source brief origin key is absent, AF-CONVERTER-PARITY is skipped (it is a converter-specific gate, not a universal gate). Record the outcome in `copy_qc_report.json` as `af_converter_parity_triggered: true|false`.

**Failure message:** `AF-CONVERTER-PARITY: DECK FAIL -- converter-origin deck (source_brief_origin: role-22) failed the runtime parity gate. Failed conditions: {list}. A converter deck must use the identical pipeline as a regular build: canonical renderer + gpt-image-2 model pin + real vision QC + Phase -0.5 Research Brief (Category E + F) + propagated persuasion variables. Correct the failing conditions and re-run QC.`

---

## 6. NEW AUTO-FAIL CODES -- 2026-06-14 ENFORCEMENT OVERHAUL

These five codes were added after the forensic four-deck failure analysis. Each one maps to a specific failure pattern from that analysis:

### AF-RENDERER (Fix 1)
**What failed:** Each of four test decks wrote its own throwaway renderer (render.py, build_deck.py, gen_and_build.py). No shared standard enforced model, prompt length, text strategy, or QC.
**Detection:** Phase 4 at dispatch: confirm the producing agent is calling `23-ai-workforce-blueprint/templates/presentation-render/render_deck.py`. At Phase 6: confirm `render_manifest.json` is present and was written by the canonical module (it includes a `module_version` key). If absent: DECK FAIL.

### AF-MODEL-SOVEREIGNTY (Fix 2)
**What failed:** Two of four decks submitted to `nano-banana-pro` instead of `gpt-image-2-text-to-image`. The wrong model was copy-pasted from example payloads without reading the client's config.
**Detection:** Compare `render_manifest.json` -> `model_used` per slide against `intake.json` -> `model_pin`. If any slide used a different model AND there is no corresponding entry in `render_manifest.json` -> `fallback_events` with a documented hard API failure: DECK FAIL.

### AF-BAKED (Fix 4)
**What failed:** Two of four decks used Pillow ImageDraw plus a black RGBA scrim to composite Helvetica text over Kie images, producing "flat dark slabs." Four to twenty-three slides in the other two decks were rendered entirely in Pillow (no Kie image at all).
**Detection:** Vision QC (the client's own vision model: `qwen3-vl:235b-cloud` via Ollama Cloud, fallback `qwen/qwen3-vl-235b-a22b-instruct` via OpenRouter) checks each slide. If the vision agent scores text as "overlaid / composited" rather than "rendered as part of image composition," or if the image matches a flat-fill placeholder signature (solid color, tiny file under 50KB), the slide triggers AF-BAKED.

### AF-PROMPT-FLOOR (Fix 5)
**What failed:** 100% of 98 image prompts (across all four decks) were below the 1500-char floor. Median was 277 chars -- 5.4x under floor. Zero prompts had proper archetype declarations or negative blocks. (This forensic record describes the incident at the time the floor was 1500; the floor/ceiling have since been raised to 5000/18000 — see the AF-PROMPT-FLOOR row in the table above and the live AF-P1/AF-P2 gate. The CURRENT gate is 5000-18000, target band 9000-14000.)
**Detection:** Phase 3 (Prompt QC gate). Count characters in each prompt file. Check for `[ARCHETYPE` on line 1, a dedicated NEGATIVE BLOCK paragraph, and at least three "Do not ..." imperative sentences in the final paragraph. Any miss: slide FAIL, loops back to Slide Image Creator.

### AF-NO-VISION-QC (Fix 6)
**What failed:** All four decks used only `path.exists()` for "verification." No vision API was called on any image. Part1-GENERAL shipped 40 placeholder PNGs because they passed the file-presence check.
**Detection:** Phase 6 final gate: confirm `working/qc/vision_qc_log.json` exists, is non-empty, and contains at minimum one entry per slide with a non-null `vision_api_response` field. A log that records only `{"slide": N, "exists": true}` entries is NOT a vision QC log and triggers AF-NO-VISION-QC for the DECK.

