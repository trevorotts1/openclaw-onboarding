# MASTER QC AUTO-FAIL RULESET (SLIDE-CRAFT)

> **SOP-LOCKED DEPARTMENT:** if you add/modify any SOP, role, or gate, you MUST update
> `PIPELINE-MANIFEST.json` + `build_deck.py` + a test. Run
> `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/sync_check.py` — it
> fails the gate if the Python and the SOP stack drift. Every AF code in the Section-5 table
> below is reconciled against `PIPELINE-MANIFEST.json` by `sync_check.py` (any Section-5 code
> missing from the manifest is `DRIFT A4`). Procedure: `SOP-SLIDE-06-EXTENSION-AND-SYNC.md`.

**Cluster:** Slide-Craft Rules (the single most important deliverable)
**Purpose:** the precise, machine-checkable list the integrator wires into qc-specialist-presentations.md so a deck CANNOT pass if it repeats the reference failure case's failures.
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md
**How to use:** every rule below is an AUTO-FAIL. Auto-fails are checked FIRST, before any 1-to-10 scoring, exactly like the existing AF-C / AF-P / AF-I tables in the QC role. A triggered auto-fail forces FAIL on the affected slide (or the whole DECK where marked) regardless of any average. The QC report records the triggered code, the slide, and the failure message verbatim.
**Status:** DRAFT for integration. These codes are NEW and do not collide with the existing AF-C1..C5, AF-P1..P8, AF-I1..I7. They are added as a fourth and fifth auto-fail layer: the SLIDE-CRAFT auto-fails (copy stage, Phase 1Q) and the RENDER auto-fails (Phase 5/6).

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

These are deck-level and are evaluated against arc_allocation.json and slide order. They are auto-fails, not scored, because a crammed offer was the root of the reference failure case's 2/10 pitch.

- **AF-DEN-1:** any two adjacent price beats < 8 slides apart. `AF-DEN-1: {beatA}@{X} and {beatB}@{Y} are {gap} slides apart (min 8).`
- **AF-DEN-2:** anchor outside 25-45% depth. `AF-DEN-2: anchor at {pct}% (target ~one-third).`
- **AF-DEN-3:** a DROP with no BUILDUP immediately before it. `AF-DEN-3: {drop}@{X} has no BUILDUP before it.`
- **AF-DEN-4:** no itemized value-stack slide before Drop 1. `AF-DEN-4: no value-stack slide before Drop 1.`
- **AF-DEN-5:** no promises beat before the anchor. `AF-DEN-5: no promises slide before the anchor.`
- **AF-DEN-6:** Wall of Wins not 4-6 slides before the offer. `AF-DEN-6: Wall of Wins {gap} slides before offer (target ~5).`
- **AF-DEN-7:** no 4-7 slide re-pitch block after FINAL. `AF-DEN-7: {N} post-FINAL slides, no re-pitch block (need 4-7).`
- **AF-DEN-8:** any section below its minimum slide count. `AF-DEN-8: {section} has {N} slides (floor {M}).`

---

## 2.5 ANTI-COMPRESSION COVERAGE AUTO-FAIL (deck-level veto; Mode B never compresses the source)

A client who hands over an existing deck (Mode B) must NEVER receive back a deck with fewer slides. Mode B is ADD-ONLY: improve and expand, never reduce below the source slide count. Compressing a client's deck to hit a duration cap is a coverage failure, not an optimization.

- **AF-COVERAGE-1 (deck-level veto; no averaging):**
  - **Stage:** 1Q (arc_allocation.json vs `mission_prd.source_slide_count`) AND Phase 6 (assembled deck page count).
  - **Level:** DECK (vetoes the whole gate).
  - **Check:** `final_slide_count < source_slide_count` -> FAIL. (Mode A, `source_slide_count == 0`, always passes.)
  - **Message:** `AF-COVERAGE-1: output deck has {final} slides; client source deck had {source}. The system must NEVER output fewer slides than the source (Mode B is ADD-only). Add {source-final} slides; never delete a client slide to hit a duration cap.`
  - **Source of truth:** `source_slide_count` is captured as a TOP-LEVEL integer field in BOTH `mission_prd.json` and `enhancement_gap.json` at Mode B intake (Mode A -> 0). `SLIDE_COUNT_FINAL = max(duration_target, source_slide_count)`; this floor OVERRIDES the HARD MAX and the 90 absolute ceiling. See CLIENT-WEBINAR-DECK-SOP Section 3.4 (Mode B) and Section 4 (slide math).

---

## 2.6 RENDERER + PROCESS-MANIFEST AUTO-FAILS (deck-level veto; the canonical renderer is scripts/build_deck.py)

The single canonical renderer is `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`. It is the DETERMINISTIC, no-AI Phase-4 renderer + Phase-8 assembler with a built-in process preflight. It is NOT a banned throwaway renderer; it IS the renderer. There is no `render_deck.py`, no `render_manifest.json`, and no `vision_qc_log.json` in this system; any gate that asserts against those non-existent paths is re-keyed below to assert against `working/checkpoints/process_manifest.json` (which `build_deck.py` writes; see SOP-SLIDE-05-PROCESS-MANIFEST).

- **AF-RENDERER (deck-level veto):** the assembled deck was produced by anything other than the canonical `scripts/build_deck.py`, OR `build_deck.py` ran with `--adhoc-no-process` (preflight skipped) on a real deliverable. Detection: `working/checkpoints/process_manifest.json` records the render phase with `role: build_deck` / `artifact_path` pointing at the canonical script and `ran: true`; absence (or an adhoc-skip flag) fails the DECK.
  - Message: `AF-RENDERER: deck not produced by the canonical scripts/build_deck.py with process preflight (process_manifest.json missing the render phase or marked adhoc). Re-render through build_deck.py.`
- **AF-MODEL-SOVEREIGNTY (deck-level veto):** generation used a model other than the GPT-Image-2-only manifest (CLIENT-WEBINAR-DECK-SOP §9.0). Detection: the generation phase entry in `process_manifest.json` records a non-manifest model id. Any deviation fails the DECK.
  - Message: `AF-MODEL-SOVEREIGNTY: generation used a non-manifest model. Only the pinned GPT-Image-2 family is permitted; a model outage means PAUSE and escalate, never substitute.`
- **AF-NO-VISION-QC (deck-level veto):** the image QC phase (Phase 5) did not run a multimodal vision read of every rendered slide. Detection: `process_manifest.json` lacks a Phase-5 image-QC entry with `ran: true` and `gate_codes_checked` including the AF-I / AF-PLACEHOLDER / AF-HOOK render codes. Missing = fail the DECK.
  - Message: `AF-NO-VISION-QC: no recorded multimodal image-QC pass over the rendered slides (process_manifest.json Phase-5 entry missing). Every rendered slide must be vision-read before assembly.`
- **AF-CONVERTER-PARITY (deck-level veto):** the assembled PPTX page count does not match the count of QC-passed rendered slides. Detection: compare the assembled deck page count (recorded by `build_deck.py` in `process_manifest.json` at the assembly phase) against the count of Phase-5-passed `working/renders/slide-NN.png` files. A mismatch fails the DECK.
  - Message: `AF-CONVERTER-PARITY: assembled deck has {pptx} pages but {passed} QC-passed renders exist. The converter dropped or duplicated slides; re-assemble through build_deck.py.`

Every renderer auto-fail above asserts against `working/checkpoints/process_manifest.json`, the single per-run attestation that the full SOP stack ran (SOP-SLIDE-05-PROCESS-MANIFEST). None reference a render_manifest.json / render_deck.py / vision_qc_log.json (those do not exist).

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
3a. **Add the anti-compression coverage gate** (Section 2.5, AF-COVERAGE-1) as a deck-level gate run at Phase 1Q (arc vs `mission_prd.source_slide_count`) and re-verified at Phase 6 (assembled page count). Mode B is add-only; never trim a client slide.
3b. **Add the renderer + process-manifest gates** (Section 2.6: AF-RENDERER, AF-MODEL-SOVEREIGNTY, AF-NO-VISION-QC, AF-CONVERTER-PARITY) as a deck-level gate run at Phase 6, all asserted against `working/checkpoints/process_manifest.json`. The canonical renderer is `scripts/build_deck.py`; do not reference render_deck.py / render_manifest.json / vision_qc_log.json (they do not exist), and do not list build_deck.py as a banned renderer. The per-run process manifest spec is SOP-SLIDE-05-PROCESS-MANIFEST.
4. **Replace AF-C2** (the RETIRED "hook count BELOW 7 = auto-fail" floor) with RULE 1 (the banded ceiling: the verbatim hook stands on 3-4 DEDICATED pure-typography slides, ~4-5 appearances max, never 2 consecutive, never a footer on every slide; over-stamping is the #1 defect, STRIP excess rather than pad). This is the single most important change: the retired floor PRODUCED the 40-slide stamping.
5. **Promote one-big-idea (criterion 1) and audience-facing (criterion 13) from scored criteria to double-weighted auto-fails** via RULE 5 and RULE 2; they no longer average away.
6. **Add the placeholder-on-render ban as a hard finishing failure that blocks FINAL status** (RULE 3), and extend the native-text fallback from price-only to the hook line (so RULE 4c cannot recur).
7. **Update the QC role KPI** "Auto-fail detections caught before owner sees work = 100%" to explicitly include the new codes, and add to the weekly QC Trend Report a per-code count for AF-HOOK, AF-AUD, AF-PLACEHOLDER, AF-OBI, AF-DEN, AF-COVERAGE, AF-RENDERER, AF-MODEL-SOVEREIGNTY, AF-NO-VISION-QC, and AF-CONVERTER-PARITY.

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
| AF-COVERAGE-1 | 1Q/6 | DECK | output deck has fewer slides than the client source deck (Mode B add-only) | `final_slide_count < mission_prd.source_slide_count` (Mode A == 0 always passes) |
| AF-SPEECH-SHORT | 9 | DECK | presenter speech words < target_talk_minutes x 120 wpm (too short for the requested duration) | `word_count(speech.md) < round(intake.target_talk_minutes * 120)`; enforced by build_deck `_chk_speech_length` (conditional: fires once the speech exists) |
| AF-RENDERER | 6 | DECK | deck not produced by canonical scripts/build_deck.py (or preflight skipped) | process_manifest.json render phase: role=build_deck, ran=true, not adhoc |
| AF-MODEL-SOVEREIGNTY | 4/6 | DECK | generation used a non-manifest model | process_manifest.json generation-phase model id vs the GPT-Image-2 manifest |
| AF-NO-VISION-QC | 5/6 | DECK | no multimodal image-QC pass over rendered slides | process_manifest.json Phase-5 image-QC entry ran=true with render gate_codes_checked |
| AF-CONVERTER-PARITY | 6 | DECK | assembled PPTX page count != QC-passed render count | process_manifest.json assembly page count vs count of Phase-5-passed slide-NN.png |

Every row is a binary trigger with an exact detection method and a verbatim failure message (Sections 1, 2, 2.5, and 2.6). Wire them as auto-fails, checked before scoring. A deck that trips any DECK-level row, or any slide that trips a slide-level row, cannot be marked final. The renderer rows (AF-RENDERER, AF-MODEL-SOVEREIGNTY, AF-NO-VISION-QC, AF-CONVERTER-PARITY) and AF-COVERAGE-1 are verified against `working/checkpoints/process_manifest.json`, the single per-run attestation that the full SOP stack ran (see SOP-SLIDE-05-PROCESS-MANIFEST).
