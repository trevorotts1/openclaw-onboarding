# SOPs Mirror -- Slide Copywriter

**Source:** presentations/slide-copywriter.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Write the Slides (Words First, One Big Idea)

**When to run:** Phase 1 -- after arc_allocation.json is received and STYLE BLOCK is confirmed.

**Inputs:**
- working/copy/intake.json
- working/copy/mission_prd.json
- working/copy/arc_allocation.json
- STYLE BLOCK (brand voice, tone, color, type -- used to ensure copy tone matches brand voice)
- Proof inventory (extracted from intake.json)

**Steps:**
1. Open slides_copy.md. Write a file header: `# Slide Copy -- [DECK_SLUG] -- Draft 1`.
2. For each slide in arc_allocation order, write one slide block using this EXACT template (mirrors master SOP Section 5.2 -- every field is mandatory):
   ```
   ---
   SLIDE [N]
   SECTION: [arc section name]
   PURPOSE: [the one big idea, one sentence]
   ARCHETYPE: [A1-A5 from master Section 7.2]
   LADDER: [none | ANCHOR | BUILDUP | DROP1 | DROP2 | DROP3 | FINAL]
   HEADLINE: [max 9 words, active voice, no em dash]
   EMPHASIS: [which word(s) get accent color]
   SUBHEAD: [max 18 words, one line, optional -- only if the headline needs support]
   SUPPORTING: [third text block if any -- stat, label, or CTA chip -- or NONE]
   PROOF USED: [testimonial or stat name from proof inventory, or "none"]
   PEOPLE: [yes/no; if yes, which REPRESENTATION_MIX group this slide draws from]
   HOOK_REFRAIN: [yes/no; if yes, where the hook line sits on the slide]
   TEXT_ANCHOR: [bottom band | left block | right block | center punch]
   PRESENTER NOTE: [2-4 sentences the speaker says aloud that are NOT on the slide]
   HOOK VARIANT: [if this slide contains a hook appearance, write the exact hook variant used]
   ---
   ```
3. Apply the hard limits (master Section 5.1):
   - Headline: 9 words maximum. Count every word including articles and prepositions. Target 4 to 7.
   - Subhead (sub-copy): 18 words maximum. One line.
   - Maximum 3 text blocks per slide (headline + sub-copy + one supporting element such as a stat, label, or CTA chip). The supporting line stays short.
   - Bullet slides: maximum 5 bullets, 7 words per bullet. Bullets only when the idea is genuinely a list (stack components, "this is for you if", recap), never as a substitute for choosing the one big idea.
   - Value stack slides: maximum 6 line items, each `Name + $X value`, 7 words per name. Split across two slides if the stack runs longer.
   - No em dashes anywhere in any field. Use a comma or parenthesis instead.
   - No fabricated proof: if a slide calls for a testimonial and none is in the proof inventory, write `[TESTIMONIAL PENDING -- client must supply]` as a placeholder. Never invent a quote or a number.
4. For every slide in the Proof section (per arc_allocation.json), include PROOF USED field referencing a specific item from the proof inventory.
5. For every slide in the Offer Stack and Price Ladder sections, coordinate with the Offer Price Strategist's output in working/copy/price_ladder.json. Do not write price numbers yourself -- pull them from price_ladder.json.
6. Count hook appearances as you write. Track in a comment at the top of slides_copy.md: `# HOOK APPEARANCES: N`. Update after every hook-bearing slide.
7. After writing all slides, verify the hook appearance count is >= 7. If not, insert hook refrains in the Urgency/Close section until the count reaches 7.
8. Write the completed slides_copy.md to working/copy/slides_copy.md.

**Outputs:**
- working/copy/slides_copy.md (all slides, complete per-slide template for each)

**Hand to:** QC Specialist -- Presentations (Phase 1Q copy QC gate)

**Failure mode:** If intake.json is missing a required field (e.g., no FINAL_PRICE), do not invent a price. Write `[PRICE PENDING]` as a placeholder, flag the gap in a comment in slides_copy.md, and notify the Director immediately so the gap can be resolved before the QC gate.

---

### SOP 9.2 -- Hook Authoring and Refrain Placement

**When to run:** During Phase 1, after the hook is first established (typically on slide 1 or 2), and again during final hook-count verification.

**Inputs:**
- mission_prd.json (hook field)
- arc_allocation.json (slide positions for hook refrains)
- slides_copy.md (in progress)

**Steps:**
1. Read the hook from mission_prd.json. The hook is a single, memorable sentence that captures the deck's core promise. Example structure: "[Transformation] without [sacrifice/objection]."
2. Write 7 to 10 VARIANTS of the hook. Each variant says the same thing with different wording. Variants may be shorter, punchier, or reframed for the arc section they appear in. Record all variants in working/copy/hook_variants.json.
3. Assign each variant to a specific slide in arc_allocation.json. Distribute variants across the deck: first appearance on slide 1-3, then at the Problem close, Solution intro, Proof intro, Offer Stack intro, Price drop, and Urgency close.
4. Write a TEXT ANCHOR note for each hook-bearing slide in the HOOK VARIANT field of that slide's copy block. The anchor is the EXACT text that will appear on the slide or as an overlay. It must be 8 words or fewer.
5. Verify distribution: no more than 2 consecutive non-hook slides in the Price Ladder and Urgency sections. The hook must "sing" -- a listener with no context should hear it and want to stay.
6. Record the final hook placement map in hook_variants.json: `{ "hook_text": "...", "variants": [...], "placement_map": [{"slide": N, "variant_used": "..."},...] }`.

**Outputs:**
- working/copy/hook_variants.json
- slides_copy.md updated with HOOK VARIANT fields

**Hand to:** QC Specialist (for hook-count verification in Phase 1Q criteria 1)

**Failure mode:** If fewer than 7 natural hook placements exist in the arc, insert hook refrains as standalone "refrain slides" -- a single large headline with the hook text and no other body copy. These count toward the slide total.

---

### SOP 9.3 -- Proof Integrity and No-Fabrication Gate

**When to run:** Before submitting slides_copy.md to Phase 1Q. This is a self-check gate -- run it on your own output before handing off.

**Inputs:**
- working/copy/slides_copy.md (your draft)
- Proof inventory (extracted from intake.json)
- intake.json (source of truth for all client claims)

**Steps:**
1. List every PROOF USED value across all slide blocks in slides_copy.md. Write the list to working/copy/proof_audit.txt.
2. For each item in proof_audit.txt, verify: does this item appear verbatim (or as a direct paraphrase) in intake.json? If yes: mark VERIFIED. If no: mark UNVERIFIED.
3. For every UNVERIFIED item: replace the proof content on that slide with `[PROOF PENDING -- client must supply]` and add a comment in proof_audit.txt.
4. Scan every slide's HEADLINE, SUBHEAD, and BODY for fabricated statistics. A fabricated statistic is any number, percentage, or named study that does not appear in intake.json. Replace any found with `[STAT PENDING]`.
5. Scan every slide for em dashes. Replace every em dash with a comma or parenthesis.
6. Count total PROOF PENDING and STAT PENDING placeholders. If count > 5, flag to the Director: "High placeholder count ([N]) -- recommend resolving with the client before Phase 1Q."
7. Write proof_audit.txt to working/copy/proof_audit.txt.

**Outputs:**
- working/copy/proof_audit.txt
- slides_copy.md (updated -- em dashes removed, unverified proof replaced)

**Hand to:** QC Specialist -- Presentations (proof audit is attached to the Phase 1Q package)

**Failure mode:** If intake.json contains no proof at all (client provided no testimonials, case studies, or statistics), write a cover note to the Director: "No proof inventory items available. Proof slides contain placeholders. Recommend requesting proof from client before owner approval." Do NOT fabricate proof under any circumstances.

---

### SOP 9.4 -- Mode B Word-Preserving Augmentation

**When to run:** Mode B runs only (per SOP 9.3 of director-of-presentations -- Enhancement Gap Analysis).

**The absolute rule (master Section 3.4):** in Mode B you do not change their intent, you do not change their words, you do not change their methodology. Add on to, improve upon, NEVER change. The client's words ship verbatim. There is NO non-preserving rewrite path in Mode B -- not for headlines, not for subheads, not for body, not for any field. Any improvement you see is a PROPOSAL, never an edit.

**Inputs:**
- working/copy/enhancement_gap.json (from Director)
- Existing slide copy (the client's prior deck, in text form)
- intake.json and mission_prd.json

**Steps:**
1. Read enhancement_gap.json. Identify slides marked `enhancement_needed: "copy"` or `enhancement_needed: "both"`.
2. For slides marked `enhancement_needed: "none"`: copy the existing headline and body verbatim into slides_copy.md. Do not change a single word.
3. For ALL slides that carry the client's existing copy (regardless of the gap label), the client's words ship VERBATIM into every text field (HEADLINE, SUBHEAD, SUPPORTING, BODY). You may ADD net-new elements that did not exist before -- a PRESENTER NOTE, a HOOK_REFRAIN assignment, a TEXT_ANCHOR, a brand-new ADD slide (hook, pain, proof, ladder, roadmap, quote, cost-vs-value) -- but you never overwrite an existing client line. Record what you added in the slide block: `AUGMENTATION: presenter_note_added | hook_assigned | added_slide`.
4. **Improvements are PROPOSALS, not edits.** When you believe an existing client line is weak, do NOT rewrite it. Instead, write a proposal entry to `working/copy/mode_b_proposals.json`: `{ "slide": N, "field": "HEADLINE", "original": "<their exact words>", "proposed": "<your suggested line>", "reason": "<one sentence>" }`. The original stays in slides_copy.md untouched. At the owner approval gate (Phase 1A), every proposal is shown SIDE BY SIDE with the original, and the owner adopts proposals ONLY on a per-line basis. A proposal is adopted into the copy after the owner says yes to that specific line, never before.
5. **Typo fixes only, flagged.** The single exception to verbatim is a clear typographical error (misspelling, doubled word, broken punctuation). Fix it, and flag every such fix in a comment in slides_copy.md and in mode_b_proposals.json (`"type": "typo_fix"`) so the client can review. A typo fix is never a rewrite; if changing the typo would change meaning, treat it as a proposal instead.
6. After augmenting all gap slides, run SOP 9.3 (proof integrity gate) on the full slides_copy.md.
7. Flag any ORIGINAL copy that contained em dashes: do NOT silently rewrite the line. Replace only the em dash itself with a comma, parenthesis, or "--", and note the replacement in a comment and in mode_b_proposals.json so the client can review at the gate.

**Outputs:**
- working/copy/slides_copy.md (Mode B augmented version, client words verbatim)
- working/copy/mode_b_proposals.json (every proposed improvement + every flagged typo fix, shown beside the original at Phase 1A)
- working/copy/proof_audit.txt (updated)

**Hand to:** QC Specialist -- Presentations (Phase 1Q); the owner sees mode_b_proposals.json side by side with the originals at Phase 1A.

**Failure mode:** If the client's original copy contains fabricated statistics (numbers not verifiable from any provided source), do NOT rewrite the line. Flag each one individually in proof_audit.txt and as a proposal in mode_b_proposals.json, leaving the original in place for the owner to confirm or correct at the gate. Never silently pass a fabricated statistic into the QC gate, and never silently change the client's words.

---

### SOP 9.7 -- Doctrine Application (the writing-time checklist)

**When to run:** WHILE writing, on every slide as you draft it. This is not a post-write audit -- it is the doctrine you hold in your hands as you write each line. Source authority: master SOP Section 4.3 (the BlackCEO Pitch Doctrine). Copy QC scores against these same rules (Phase 1Q criterion 12), so building them in as you write is how you pass the gate the first time.

**Inputs:**
- master SOP Section 4.3 (the pitch doctrine)
- intake.json (TONE, OFFER_STACK, the client's named methodologies, PRICE_MODE)
- arc_allocation.json (section boundaries, so per-section rules can be checked)
- slides_copy.md (the slide you are writing right now)

**Steps (run each one AS you write the slide, not after):**
1. **Light pitches, woven (rule 7).** Weave soft program references through the teaching: "inside our program," "when you work with us," "when you attend this workshop." Never save the pitch for one block at the end. If you reach the offer section and the teaching slides carry no woven pitch, go back.
2. **Named methodologies are named SYSTEMS (rule 7).** Every piece of the client's methodology from intake (their identity development structure, their guided development system, their named frameworks) is treated as a named SYSTEM and softly sold every time it appears. A framework mentioned by name is a light sales point.
3. **One pain per slide with an emotional image note (rule 9).** Each distinct pain point is ONE slide, never a bulleted list of pains. Write a PRESENTER NOTE and a PURPOSE that make the viewer say "that is exactly how I feel," and note the emotion the image must carry.
4. **At least one intrigue slide per section (rule 10).** Each arc section contains at least one genuine curiosity-gap slide -- a line that makes the audience ask a question ("doing the right things, but in the wrong way?"). Track per-section coverage.
5. **Compare and contrast in every Secret (rule 11).** Every Secret section carries an old-way vs new-way device (control vs clarity, keep guessing vs build the system). Two-sided belief-shift slides are the workhorses; one lives in each Secret and again in the close.
6. **Cost vs value, answered before the close (rule 6).** Before the offer lands, the deck has explicitly answered both: the COST of inaction and the VALUE of action. If the offer produces money, the math is on screen. If the outcome is non-monetary, run the PRICELESS PITCH (the American Express frame) and elevate the outcome above money. Never fabricate dollar values for non-monetary outcomes.
7. **Appetizer depth, not dinner (rule 8).** Each Secret teaches the WHAT, the WHY, and ONE quick win. The complete HOW lives inside the offer. A Secret that hands over the full how-to has no dinner left to sell.
8. **Triple alliteration on value trios (rule 13).** When a value trio is part of the pitch, alliterate it where natural ("confident, consistent, clear") and consider giving each value word its own slide, because each is being sold.
9. **Quote slides carry the client NAME ONLY (rule 1, the T.D. Jakes rule).** Quote and signature-line slides attribute to the client's name with no credentials or resume.
10. **The slide is never the script (rule 15).** Slide text (HEADLINE / SUBHEAD / SUPPORTING) never duplicates the PRESENTER NOTE narration. If the headline says what the note says, rewrite one of them. That separation is why the audience listens instead of reading ahead.
11. **Pitch the PROMISE, not the product (rule 2, GP-3).** People do not buy the product, the product is a reflection of the promise they want. Every teach and offer slide pitches the PROMISE. Keep a running promise note in your head as you write: what is this slide promising? If a slide sells the product (features, deliverables, mechanics) without naming the promise underneath it, rewrite the headline to lead with the promise.
12. **Emotion buys, logic justifies, serve BOTH (rule 5, GP-4).** You are writing to a couple: one partner is emotionally ready, the other needs the logical case. Every offer-section slide carries something for each, emotionally driven future-pacing for the heart AND an explicit number (cost of inaction, payback, LTV) for the justifier. A slide that only inspires loses the justifier, a slide that only calculates loses the buyer. Do not split them across far-apart slides, weave both into the offer beats.
13. **Every drop ADDS value, never strips it (rule 3, GP-6).** When you write a DROP slide (pull the number from price_ladder.json, never invent it), the same slide or its immediate successor names a NEW value that just got added to the table. Write the added value as a concrete named item, not "plus more bonuses." If a drop only lowers the number and adds nothing, flag it to the Offer Price Strategist, do not ship a stripping drop.
14. **Old to new bridge (SP-OLDNEW).** Anchor every new idea to something the audience already understands, use their previous understanding to increase their current understanding. Before a new concept slide, the copy names the known thing it builds on ("you already know X, here is what changes"). This is distinct from the old-way vs new-way contrast in step 5, it is the teaching bridge, not the belief shift.
15. **Point, Story, Demo on teaching slides (SP-PSD).** Each teaching beat follows Point then Story then Demo: state the one point (HEADLINE), land it with a short story or example (PRESENTER NOTE), then show it working (a demo slide, a before/after, or a named quick win). When a Secret runs across more than one slide, sequence them P, then S, then D rather than three parallel points.
16. **Care before credentials, and let them teach themselves (SP-CARE, SP-TEACH).** The opening arc cares about the audience before it establishes the presenter, people do not care who you are until you show you care who they are, so the open names the audience's situation and feeling before any presenter bio or credential. Throughout, write conversationally so the audience arrives at the insight themselves ("you already know how this ends," "you have felt this"), inviting them to reach the conclusion rather than being told it. If the open leads with the presenter's resume, rewrite it to lead with the audience.

**Outputs:**
- slides_copy.md slides written doctrine-compliant on the first pass
- A short doctrine self-check note at the bottom of slides_copy.md confirming per-section intrigue coverage, per-Secret compare/contrast coverage, the care-first open, that both emotion and logic are served in the offer section, and that cost-vs-value was answered before the close

**Hand to:** QC Specialist -- Presentations (Phase 1Q criterion 12, Doctrine compliance)

**Failure mode:** If the intake does not name any client methodology to treat as a system (rule 2 has nothing to sell), do not invent one. Flag to the Director that the deck lacks a named system to weave, and ask whether the client has one to supply. Never fabricate a methodology name.

---
