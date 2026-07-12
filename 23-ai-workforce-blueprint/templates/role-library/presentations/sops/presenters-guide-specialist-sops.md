# SOPs Mirror -- Presenter's Guide Specialist

**Source:** presentations/presenters-guide-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Build the Speaker Outline

**Purpose:** Turn the sparse deck into a speaker-facing map: per section and per slide, what to cover and the one point to drive home. This is the OUTLINE, distinct from the word-for-word Speech.

**The hard rule:** Every section gets a section header with its job in one line; every slide gets an entry with (a) the slide's one big idea restated, (b) 2 to 4 talking-point bullets of WHAT to cover, and (c) one bolded POINT TO DRIVE HOME sentence. The entry tells the owner what to say ABOUT, not the exact words to say.

**Inputs:** slides_copy.md (PRESENTER NOTE, PURPOSE, SECTION, LADDER, HOOK_REFRAIN), arc_allocation.json, intake.json.

**Steps:**
1. Write a one-paragraph OPENING for the Guide: deck title, DURATION_MIN, total slides, the HOOK line verbatim, the GOAL (the action at the end), and a one-line reminder that this Guide is for the SPEAKER and the words to say verbatim live in the Presenter's Speech.
2. For each SECTION (from arc_allocation.json), write a section header: the section name, the slide range, and its job in one sentence (for example "AUTHORITY: earn the right to teach; slides 6 to 11").
3. For each slide, write an outline entry:
   ```
   SLIDE NN  [HEADLINE]  (SECTION, LADDER tag if any)
   On screen: [the one big idea, restated in a few words]
   Cover: [2 to 4 bullets of what to talk about here, derived from the PRESENTER NOTE and the slide PURPOSE]
   POINT TO DRIVE HOME: [one bold sentence: the belief shift or feeling this slide must land]
   ```
4. On HOOK_REFRAIN slides, add a line: "SING THE HOOK here: '[HOOK verbatim]'" so the owner re-anchors on cue.
5. On LADDER slides, add a line stating the rung, the earned reason, and the pause cue (for example "DROP1: $2,500 because they showed up live. Land the number, then go quiet for 3 seconds.").
6. Carry any [CLIENT TO SUPPLY] placeholder forward verbatim as "[OWNER: fill in your real [result/win/number] before going live]". Never fabricate.
7. Write the outline to working/presenter-guide/outline.md.

**Enforcement check (what auto-fails the Guide):**
- Any slide or section missing from the outline = FAIL.
- Any slide entry missing the POINT TO DRIVE HOME sentence = FAIL.
- The outline reproduces the word-for-word Speech instead of talking points = FAIL (wrong deliverable; that is ROLE-20).
- A fabricated client win/number in place of a [CLIENT TO SUPPLY] flag = FAIL.

**PASS example (illustrative -- substitute your DISCOVERY VARIABLES):** "SLIDE 09 Control vs Clarity (THE CONTRAST, hook is born here). On screen: control vs clarity. Cover: name the two modes; give the contrast; this is where the hook is born. POINT TO DRIVE HOME: most high-achieving people are controlling out of love and do not realize clarity is the better lever. SING THE HOOK: 'There is a difference between parenting by control and parenting through clarity.'"

**FAIL example:** an entry that just repeats the slide headline with no talking points and no point to drive home; or an entry that prints the full spoken paragraph (that belongs in the Speech).

**Outputs:** working/presenter-guide/outline.md.

**Hand to:** SOP 9.2 (render the PDF).

**Failure mode:** If a PRESENTER NOTE is blank or under 10 words, flag the slide as [INCOMPLETE PRESENTER NOTE: needs Slide Copywriter revision], log it, and notify the Director. Do not invent talking points for an empty note.

---

### SOP 9.2 -- Render the Beautiful PDF (font never below 12)

**Purpose:** Produce a genuinely beautiful, on-brand, readable PDF the owner can hold or put on a second screen. Beautiful and readable are both requirements; the font floor exists because a tired presenter cannot read 9pt under stage lights.

**The hard rule:** No text in the PDF renders below 12pt. Body text 12 to 14pt minimum; section headers larger; the POINT TO DRIVE HOME lines visually distinct (bold and/or accent color). The PDF uses the deck's brand colors and headline font (from the design system) so it feels like part of the same product.

**Inputs:** outline.md, design_system.json (optional, for brand match), intake.json (deck title, TONE).

**Steps:**
1. Convert outline.md to a styled document: cover page (deck title, owner name, date, "Presenter's Guide -- Speaker-Facing"), a one-page contents/section map, then the per-slide entries grouped under section headers.
2. Apply brand: headline font and Primary/Secondary accent colors from the design system; the POINT TO DRIVE HOME line in the accent color and bold.
3. Set the type scale with a hard 12pt floor. Verify the floor programmatically after render (extract text run sizes if the toolchain allows, or render to image and confirm legibility); if any run is below 12pt, fix the stylesheet and re-render.
4. Render to working/presenter-guide/Presenters_Guide_<DeckTitle>.pdf using the box's confirmed PDF toolchain.
5. Confirm the file exists and opens (ground truth, not a self-report).

**Enforcement check (what auto-fails):**
- Any text below 12pt in the rendered PDF = FAIL.
- The PDF does not open or is zero bytes = FAIL.
- No POINT TO DRIVE HOME visual distinction = FAIL.

**Outputs:** working/presenter-guide/Presenters_Guide_<DeckTitle>.pdf.

**Hand to:** SOP 9.3 (Notion) and SOP 9.4 (delivery).

**Failure mode:** If no PDF toolchain is installed on the box, escalate to the Capacity and Reliability Engineer (ROLE-03) to confirm or install one; do not deliver only a Markdown file and call it a beautiful PDF.

---

### SOP 9.3 -- Publish the Notion Doc

**Purpose:** Mirror the Guide into Notion so the owner can read it on any device and the team can reference it.

**The hard rule:** The Notion doc carries the same content as the PDF, well-formatted (headings, toggles per section, the POINT TO DRIVE HOME lines as callouts), and the published URL is captured and verified.

**Inputs:** outline.md (source of truth), the box's Notion integration credentials (from the env stores per the credential-check rule, never assume missing).

**Steps:**
1. Create or locate the client's Presentations Notion space.
2. Create a page titled "Presenter's Guide -- <DeckTitle>".
3. Render the outline as Notion blocks: section headers as H2, slide entries as H3 + bulleted talking points, POINT TO DRIVE HOME lines as callout blocks in the accent color, hook and ladder cues as quote/callout blocks.
4. Capture the public or workspace URL; write it to working/presenter-guide/notion_url.json with a verification fetch confirming the page resolves.

**Enforcement check (what auto-fails):**
- notion_url.json missing or the URL does not resolve = FAIL.
- The Notion content diverges from the PDF content = FAIL.

**Outputs:** working/presenter-guide/notion_url.json.

**Hand to:** SOP 9.4.

**Failure mode:** If the Notion credential is genuinely absent after checking ALL env stores and the live process env (per the credential-check rule), flag to the Director and operator; deliver the PDF and note the Notion step as blocked, never silently skip it.

---

### SOP 9.4 -- Surface-Boundary Audit and Delivery

**Purpose:** Prove the Guide is a SPEAKER surface and nothing speaker-facing leaked the other way (no Guide content on the deck), then deliver both artifacts and verify.

**The hard rule:** The Guide content lives only in the PDF and Notion (speaker surfaces). No slide-copy file or image prompt may contain Guide text. Deliver to the owner with explicit labeling of which artifact is which surface.

**Inputs:** the PDF, the Notion URL, slides_copy.md (to confirm no leakage), intake.json (delivery destinations / environment).

**Steps:**
1. Surface-boundary check: grep the slide copy and prompt files to confirm none of the Guide's talking-point text or POINT TO DRIVE HOME lines were copied onto the audience deck. If any appear on the deck, flag to the Director (deck must be corrected) and do not deliver until resolved.
2. Deliver per SOP-PITCH-05-DELIVERABLE-BUNDLE + delivery-concierge SOP + CLIENT-WEBINAR-DECK-SOP.md Section 9a (PRESENTATION-MASTER-DOCTRINE.md §4): Mac clients get the PDF copied to their Downloads folder with a clear descriptive name (Presenters_Guide_<DeckTitle>.pdf); the Notion URL is included in the message. If the environment is unclear, ASK where to deliver.
3. Notify the owner via openclaw message send, stating plainly which artifact is which surface: "Two speaker-facing documents are ready. The Presenter's Guide (this PDF and Notion link) is your MAP: what to cover and the point to land on each slide. The Presenter's Speech, coming from [ROLE-20], is the exact words plus an audio demo. The slide deck is what the AUDIENCE sees; the Guide and Speech are only for you."
4. Verify file existence at every destination (ground truth) before reporting done.
5. Update working/checkpoints/run_ledger.json: `presenter_guide_phase: "complete"`, with the PDF path and Notion URL.

**Enforcement check (what auto-fails):**
- Any Guide content found on the audience deck = FAIL (block delivery, escalate).
- Delivery reported done without verified file existence = FAIL.
- Delivery message does not name which artifact is which surface = FAIL.

**Outputs:** delivered PDF, Notion URL, run_ledger.json updated.

**Hand to:** Director of Presentations (completion); Presenter's Speech Writer (ROLE-20) and Presenter Coach (ROLE-14) consume the same source notes.

**Failure mode:** If the owner is unreachable, deliver to the default location (Downloads for Mac), log the delivery, and send one follow-up; never hold a finished Guide hostage to a reply.

---
