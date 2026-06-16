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
- working/research/brief-[DECK_SLUG].md (Categories C and D from ROLE-04 Phase -0.5 -- proof statistics and external corroboration; load before writing any proof slide)

**Authored-narrative requirements (AF-C10 and AF-C11):** The transcript or source material is INPUT. You AUTHOR slide copy from it; you never paste transcript lines. Verbatim/near-verbatim transcript lines are forbidden (AF-C10). The deck must carry all five arc beats: hook + stakes + promise + proof + CTA (AF-C11). Tag each beat in slides_copy.md so QC can assert them mechanically.

**Steps:**
1. Open slides_copy.md. Write a file header: `# Slide Copy -- [DECK_SLUG] -- Draft 1`.
1a. Walk the canonical arc (master SOP Section 4.2A, THE BLACKCEO SIGNATURE WEBINAR ARC). arc_allocation.json carries each slot's arc-section label (A through J): A. Hook Open, B. Care / See-Yourself, C. The Promise, D. Story, E. Teaching, F. Proof (Who Says So + Wall of Wins), G. The Offer (gradual spread ladder), H. Guarantee, I. Scarcity / Close, J. Hook Callback. Write each slide to do its arc-section's beat (the Section 4.2A table names the components for each, including the ten required components of Section 4.4), and carry the connective tissue across slides: open ON the hook (A) and sing it from the first verse toward the ~10x cadence; care about the audience before any credentials (B); pitch the promise not the product and weave the light pitch from the front (C); demonstrate expertise not charisma and quote names without credentials (D); one big idea per slide, Point-Story-Demo, appetizer-not-dinner, with the hook refraining after every proof (E, F); on the offer, the ANCHOR is a value plant not a drop, every drop is earned and built up and ADDS value with proof between drops and the FINAL below the whole ladder (G); reverse the risk (H); close on real scarcity (I); reprise the hook on the final substantive slide (J). Vary the text anchor so eyes do not fade out, and never put the presenter's spoken words on the slide.
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
6. **(Density-floor overhaul) Place the hook ONLY on the 3 to 4 dedicated slides from hook_package.json** (SOP 9.2). Track in a comment at the top of slides_copy.md: `# HOOK-CARRYING SLIDES: [N, N, N]` (must be 3 to 4). Every other slide is `HOOK_REFRAIN: no`. Do NOT insert refrains to reach a count; there is no count floor anymore, there is a ceiling of 4.
7. **(Density-floor overhaul) Run the AUDIENCE / SAY tagging pass** (SOP 9.7a): tag every line of every slide AUDIENCE (stays on the slide) or SAY (routes to the Presenter's Speech and Guide). Delete meta-telegraphing, internal pitch-doctrine, and image-narration lines (they belong nowhere). The word "webinar" and any technique self-label are banned on the face. Write the result to working/copy/audience_say_tags.json so QC can verify the pass ran (its absence fails the deck). Confirm one big idea per slide before finalizing each slide (a diagnosis+method+outcome is three slides; a value trio is four; a gap+reframe is two; four pains are four slides).
8. Write the completed slides_copy.md to working/copy/slides_copy.md and audience_say_tags.json to working/copy/.

**Outputs:**
- working/copy/slides_copy.md (all slides, complete per-slide template for each)

**Hand to:** QC Specialist -- Presentations (Phase 1Q copy QC gate)

**Failure mode:** If intake.json is missing a required field (e.g., no FINAL_PRICE), do not invent a price. Write `[PRICE PENDING]` as a placeholder, flag the gap in a comment in slides_copy.md, and notify the Director immediately so the gap can be resolved before the QC gate.

---

### SOP 9.2 -- Hook Placement on Dedicated Slides (density-floor overhaul: ceiling, not floor)

**When to run:** During Phase 1, after the Hook Strategist delivers hook_package.json (the canonical hook + the ANCHOR MAP + the HOOK-ABSENT list), and again during final hook verification.

**The hard rule:** the hook is ONE canonical verbatim line placed on the 3 to 4 DEDICATED pure-typography slides named in hook_package.json, and NOWHERE ELSE. It is NEVER a footer band, NEVER body copy on a content/proof/offer slide, NEVER printed twice on a slide, NEVER reworded or extended. (This REPLACES the prior RETIRED "write 7 to 10 variants / distribute across the deck / insert refrains until the count reaches 7" floor engine, which produced the reference failure case 40-slide footer-stamping.)

**Inputs:**
- mission_prd.json (the canonical HOOK string, locked)
- working/copy/hook_package.json (the 3 to 4 anchor slides + the HOOK-ABSENT list, from the Hook Strategist)
- arc_allocation.json (the dedicated hook-slide slots the Director reserved)
- slides_copy.md (in progress)

**Steps:**
1. Read the CANONICAL hook string from mission_prd.json. It is rendered VERBATIM on every dedicated slide. You never reword it, shorten it, extend it, or write "variants."
2. Read the ANCHOR MAP from hook_package.json: the 3 to 4 dedicated hook-slide numbers at the named beats (born after the core contrast; after the proving story; at the payoff; late into the close). Write the canonical hook as the ONE BIG IDEA of each of those slides, tagged `HOOK_REFRAIN: yes` with no competing copy (it is a pure-typography slide; the Typography Architect marks it PURE_TYPE_HOOK in Phase 1.5).
3. On EVERY other slide (the HOOK-ABSENT list), the hook does NOT appear: not as a footer, not as body copy, not as a caption. Tag those slides `HOOK_REFRAIN: no`.
4. The signature quote (if any) is its OWN dedicated slide, name-only attribution, and does NOT carry the main hook (AF-HOOK-7).
5. Verify before handoff: the hook appears on at most 4 slides; footer occurrences = 0; at least one dedicated hook slide exists; the hook is never printed twice on a slide; every occurrence is character-exact to the canonical string.
6. Record the final placement in hook_package.json (alongside the Strategist's audit): `{ "canonical_hook": "...", "hook_carrying_slides": [N, N, N], "footer_occurrences": 0, "hook_absent": [all other slide numbers] }`.

**Outputs:**
- slides_copy.md updated with `HOOK_REFRAIN: yes` on the 3 to 4 dedicated slides only
- hook_package.json placement block confirmed (no separate variant ladder)

**Hand to:** QC Specialist (for the AF-HOOK ceiling/anti-footer battery in Phase 1Q)

**Failure mode:** If the arc has no dedicated hook-slide slots, do NOT manufacture footer refrains. Flag the Director to reserve 3 to 4 dedicated hook slots in arc_allocation.json at the named beats, then write them. A standalone refrain slide is the hook as the one big idea of a pure-typography slide (that is correct); stamping the hook at the bottom of content slides is the banned footer (AF-HOOK-2).

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
5. **Compare and contrast in every Secret (rule 11).** Every Secret section carries an old-way vs new-way device (e.g. struggling alone vs having the system, keep guessing vs build the process -- derived from THIS client's intake). Two-sided belief-shift slides are the workhorses; one lives in each Secret and again in the close.
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
17. **The Story Arc: short-term fix vs long-term identity (master rule 19, required component 8).** Write an explicit contrast beat that names the SHORT-TERM FIX the audience keeps chasing (the band-aid: control, behavior management, the quick patch) against the LONG-TERM IDENTITY the offer actually delivers (clarity, ownership, who they become), and walk them to SELF-RECOGNITION. The arc names the fix, shows why it never holds, then reframes the real outcome as a durable identity change, so the audience says "that is me" in both the before and the after. At least one short-term-fix-vs-long-term-identity contrast slide is required, and the deck-wide narrative reads as that journey, not a fact list. Copy QC criterion 22 checks for its presence.
18. **The Wall of Wins (master rule 20, required component 4).** Near the close, write a Wall of Wins / wall of results slide that concentrates MULTIPLE named, located client wins in one view (the proven deck: six named results). Pull the wins from intake `PROOF_ASSETS` and the Deep Research brief; mark any unsupplied win `[CLIENT TO SUPPLY]`, never fabricate. This is distinct from the single proof-within-two-slides testimonials; it is a deliberate stack of social proof that says "look how many this already worked for." A deck with no wall-of-wins slide is missing a required element (copy QC criterion 19).
19. **The Guarantee (master rule 21, required component 6).** Write an explicit guarantee / promise / risk-reversal slide using the type the Offer Price Strategist set (one of the four types; for a service business use the operator-preferred SERVICE GUARANTEE frame: "if you do not get the result, your next 30 days is on us," or "five more sessions until your breakthrough"). State the guarantee in one bold sentence with the conditional logic in the sub-copy. Positioned after the final price reveal. Required (copy QC criterion 20).
20. **The Scarcity Factor (master rule 21, required component 7).** Write a real scarcity / last-calls / doors-closing beat into the close (last calls, doors are closing, real cohort start, real spot cap, real expiry window). Use REAL constraints only, pulled from intake (`VIP_SPOTS`, real dates); never invent a cap or a countdown. A close with no scarcity beat is incomplete (copy QC criterion 21); fabricated scarcity is a Devil's-Advocate blocking flag, so write only what is true.
21. **Who says so, woven between the drops (master rule 12, required component 3).** Place at least one third-party proof beat (a case study, study, or white paper from the Deep Research brief or intake `PROOF_ASSETS`) woven BETWEEN the price drops, not clustered. A deck whose every proof point is the client's own assertion with zero external corroboration fails (copy QC criterion 18). If the Deep Research brief carries the GP-8 zero-proof alert, flag to the Director and do not paper over it with the client's own claims.

**Outputs:**
- slides_copy.md slides written doctrine-compliant on the first pass
- A short doctrine self-check note at the bottom of slides_copy.md confirming per-section intrigue coverage, per-Secret compare/contrast coverage, the care-first open, that both emotion and logic are served in the offer section, that cost-vs-value was answered before the close, AND that all ten required presentation components are present (master Section 4.4): the promise leads, the hook sings >= 7x, a who-says-so external-proof beat is woven between the drops, a Wall of Wins slide exists near the close, one big idea per slide, a guarantee beat, a real scarcity beat in the close, a short-term-fix-vs-long-term-identity Story Arc beat, the spread price ladder, and the copywriter's own checklist of these promises is walked before handoff

**Hand to:** QC Specialist -- Presentations (Phase 1Q criterion 12, Doctrine compliance)

**Failure mode:** If the intake does not name any client methodology to treat as a system (rule 2 has nothing to sell), do not invent one. Flag to the Director that the deck lacks a named system to weave, and ask whether the client has one to supply. Never fabricate a methodology name.

---

### SOP 9.7a -- AUDIENCE / SAY Tagging Pass (density-floor overhaul; the slide-is-not-the-script enforcement)

**When to run:** After all slides are drafted, before Phase 1Q handoff. Source authority: universal-sops/presentation-slide-craft/SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md.

**The hard rule:** every line on every slide is tagged AUDIENCE or SAY. Only AUDIENCE copy (the one big idea as headline + optional sub + optional one supporting element, plus the hook on its dedicated slides) stays on the slide face. SAY lines route to the Presenter's Speech and Guide. Meta / doctrine / image-narration lines are DELETED (they belong on neither surface).

**Steps:**
1. Walk every line of every slide. Tag each:
   - AUDIENCE: the one big idea, a stat chip, a label, a CTA chip, the hook on a dedicated slide. Stays.
   - SAY: the words the presenter speaks ("When you come into our program...", "Remember this number", "Stay right here"). Move to the Presenter's Speech/Guide.
   - DELETE: internal pitch-doctrine ("The lower the price, the greater the value"), image narration ("Same parent, same child, two rooms"), meta-telegraphing ("This is not just a webinar", "one last proof", "an intrigue gap", "hold onto this line"), credential dumps ("licensed counselor, years in recruitment"). These go nowhere.
2. The word "webinar" and any technique self-label are banned on the face, full stop.
3. Any unresolved proof stays as `[CLIENT TO SUPPLY]` at copy stage (it must be filled or the slide pulled before render; a bracket token must never reach a rendered image).
4. Write working/copy/audience_say_tags.json: `{ "slides": [ { "slide": N, "lines": [ {"text":"...","tag":"AUDIENCE|SAY|DELETE","route":"slide|speech|guide|deleted"} ] } ] }`.

**Enforcement check (what auto-fails):**
- audience_say_tags.json missing at Phase 1Q = the whole deck fails for a missing required artifact (the pass did not run).
- Any line tagged AUDIENCE that is actually a speaker SAY line, internal doctrine, image narration, meta, credential dump, or contains "webinar" = AF-AUD fail at QC.

**Outputs:** working/copy/audience_say_tags.json.

**Hand to:** QC Specialist (AF-AUD battery); Presenter's Speech Writer (ROLE-20) and Presenter's Guide Specialist (ROLE-19) consume the SAY-tagged lines.

**Failure mode:** If a line is genuinely ambiguous (audience copy or spoken line), default it to SAY (route to the speech) and keep the slide to the one big idea; never leave a maybe-spoken line on the face.

---
