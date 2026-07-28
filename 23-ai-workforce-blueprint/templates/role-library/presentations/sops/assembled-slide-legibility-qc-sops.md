# SOPs Mirror -- Assembled-Slide Legibility and Visual-Artifact QC Owner ("The Inspector")

**Source:** departments/Presentations/roles/assembled-slide-legibility-qc.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Source classification:** custom (Trevor BlackCEO; the render-the-assembled-deck-and-QC-the-rendered-pages blocking gate, the em-dash auto-fail, and the facial-expression-match review are BlackCEO standards the floor presentations library does not carry).
**Department:** Presentations -- BlackCEO
**Version:** 1.0
**Last updated:** 2026-06-14

---

## 9. Standard Operating Procedures (Numbered)

---

### SOP 9.1 -- Assembled-Deck Render and Coded Assert Battery

**SOP ID:** SOP-PRES-CUSTOM-13 (BlackCEO)
**Library pointer:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` Section 11.3 (render the assembled deck to PDF to PNG, then QC the rendered pages)
**When to run:** After the PPTX Assembly Specialist delivers the assembled deck and before delivery.
**Frequency:** Per deck, once, plus once per rework loop.
**Inputs:** The assembled PPTX, the slide manifest, the upstream gate artifacts (approval record, prompt QC pass, image QC pass, representation tally, grounding pass).

**Steps:**
1. Confirm the upstream gate artifacts all exist. If any is missing, halt: a deck reaching final QC without an approval record, prompt QC pass, image QC pass, representation tally, or grounding pass is a gate-skip. Route it back and notify the Director and the Healer.
2. Render the assembled PPTX to PDF (`soffice --convert-to pdf`), then to PNG pages (`pdftoppm -png`). Confirm the render succeeded and every slide produced a page; a missing or blank page is a render failure, not a pass.
3. Run the coded assert battery on each rendered page: text-versus-image COLLISION (text bounding box overlaps an image element it should not); TEXT-OVER-FACE (rendered text intersects a detected face); OVERLAY OVERLAP (two text boxes overlap); CONTRAST and LEGIBILITY (text-to-background contrast below the legibility threshold); CROP (an element clipped at the slide edge); STRETCH (an image distorted from its native aspect ratio); MISALIGNMENT (an element off its layout grid).
4. For every failing assert, record the slide number, the assert that failed, and the coded specifics (the overlapping boxes, the low-contrast pair, the clipped element).
5. Confirm slide count matches the manifest and slide order matches the narrative architecture; a count or order mismatch is a fail.
6. Do not write a pass for any deck with an open assert failure; route fails back (SOP 9.4) and re-render after the fix.

**Outputs:** A coded assert report per deck: all-pass, or a flagged set of slides with the specific assert and coded specifics that failed.
**Hand to:** PPTX Assembly Specialist or Slide Image Creator (fix collisions, overlaps, crops); Director of Presentations (the report feeds the gate).
**Failure mode:** If the render toolchain fails, do not pass the deck on the raw images as a substitute. Halt, repair the render path, and re-render; the gate must open the assembled artifact.

---

### SOP 9.2 -- Rendered-Page Spelling and Em-Dash Sweep

**SOP ID:** SOP-PRES-CUSTOM-14 (BlackCEO)
**Library pointer:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` auto-fail battery (spelling auto-fail); governing intelligence GP-18 (M-dash hard ban)
**When to run:** On the rendered PNG pages, during final QC, after the render succeeds.
**Frequency:** Per deck, once, plus once per rework loop.
**Inputs:** The rendered PNG pages, the approved slide copy (for cross-reference).

**Steps:**
1. Read every rendered word on every page (the words the renderer actually painted, which may differ from the prompt copy).
2. Spell-check every rendered word against the approved copy and a dictionary. Any misspelling is an AUTO-FAIL, checked first, before any average score; the deck cannot pass with a single misspelled rendered word.
3. Sweep every rendered page for em dashes. Any em dash is an AUTO-FAIL; it is the AI dead-giveaway Trevor bans. Flag the slide for a re-render that strips it.
4. Confirm the rendered text matches the approved copy (the renderer did not garble or drop a word); a garbled or dropped word is a fail.
5. Record any misspelling, em dash, or garble with the slide number and the exact rendered string.

**Outputs:** A spelling and em-dash sweep record: clean, or a flagged set of slides with the exact offending rendered strings.
**Hand to:** Slide Image Creator (re-render flagged slides); QC Specialist (the auto-fail record feeds the gate).
**Failure mode:** If a misspelling or em dash is rendered into the image and cannot be removed by re-render, escalate to use the native PPTX text fallback for that element (the two-failed-renders fallback); never ship a misspelling or an em dash.

---

### SOP 9.3 -- Facial-Expression-Match Review

**SOP ID:** SOP-PRES-CUSTOM-15 (BlackCEO)
**Library pointer:** Governing intelligence GP-18 (facial-expression engine); `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` image QC expression-match criterion
**When to run:** On the rendered pages of people-bearing slides, during final QC.
**Frequency:** Per deck, for every people-bearing slide.
**Inputs:** The rendered people-bearing pages, the narrative architecture (the emotional job of each slide), the SEE-journey map.

**Steps:**
1. Identify the people-bearing slides and the emotional job each carries (the message the slide makes the viewer feel).
2. For each face, confirm the expression MATCHES the slide's message: a pain slide carries pain or concern, a promise slide carries hope or joy, an authority slide carries confidence.
3. Flag any slide where the face contradicts the message (a smiling face on a loss slide, a blank face on an emotional beat).
4. Confirm no slide has a deformed face or a hand artifact (extra fingers, deformed hands) visible on the rendered page.
5. Record any expression mismatch or face or hand artifact with the slide number and the corrective instruction.

**Outputs:** A facial-expression-match record: pass, or a flagged set of slides with the mismatch or artifact and the corrective instruction.
**Hand to:** Slide Image Creator (re-render flagged faces); Image-Grounding Steward (confirm the corrected expression still serves the SEE journey).
**Failure mode:** If a face artifact repeatedly renders (a hand that will not resolve), apply the known tactic of keeping hands soft or out of frame on the re-render; never ship a deformed face or hand on a premium deck.

---

### SOP 9.4 -- Final-Deck QC Pass-Artifact (The Blocking Gate)

**SOP ID:** SOP-PRES-CUSTOM-16 (BlackCEO)
**Library pointer:** `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` Section 6.2 and Section 12 (gates are blocking; the artifact is the gate token)
**When to run:** After all assembled-slide asserts, the spelling and em-dash sweep, and the expression review pass.
**Frequency:** Per deck, once, before delivery.
**Inputs:** The all-pass coded assert report, the clean spelling and em-dash record, the pass expression record, the upstream representation tally and grounding pass.

**Steps:**
1. Confirm every assembled-slide assert passed (SOP 9.1), the spelling and em-dash sweep is clean (SOP 9.2), and the expression review passed (SOP 9.3).
2. Confirm the representation final tally (`representation_final_tally.json`) and the grounding final pass (`grounding_final_pass.json`) both read pass; these ride alongside your gate at final QC.
3. Confirm font embedding on the rendered deck (no font substitution that changes how the audience sees the slide).
4. Only when every check passes, write the blocking pass-artifact `final_deck_qc.json` with: the deck id, the assert results, the spelling and em-dash result, the expression result, the linked representation and grounding pass artifacts, and a timestamp.
5. If any check fails, do NOT write the pass-artifact. Route the specific fails back (SOP 9.1 to 9.3) and re-run after the fix.

**Outputs:** A blocking `final_deck_qc.json` pass-artifact (only on a fully clean deck), or a routed-back set of fails with coded specifics.
**Hand to:** Delivery Concierge (delivery cannot proceed without the pass-artifact); Director of Presentations (the gate record). Failing slides go to the responsible role.
**Failure mode:** Never write the pass-artifact to clear a deadline with an open fail. A done message without verified clean artifacts is a lie; the pass-artifact only exists when the assembled deck is genuinely clean.

---

*End of SOPs mirror for the Assembled-Slide Legibility and Visual-Artifact QC Owner. Custom Presentations SOPs SOP-PRES-CUSTOM-13 through 16 for BlackCEO. This file is regenerated from the role file and is never edited directly.*
