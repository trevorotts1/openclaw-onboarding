# SOP-ENGINE-00: THE INTELLIGENCE ENGINES (FRAMEWORK INDEX)

**Cluster:** Intelligence Engines (the named capability set behind every deck)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 7 the image engines, Section 4 the pitch choreography)
**Owning role at write time:** Director of Presentations (assigns which engines a slide runs); Slide Image Creator (Facial / Lighting / Story / World / Product); Typography Architect (Typography); Offer Price Strategist (Pricing / Recap); Hook Strategist (Hook)
**Enforced at the gate by:** QC Specialist - Presentations (the per-engine auto-fail codes registered in SOP-SLIDE-00 Section 8, below)
**Status:** Doctrine procedure - Intelligence Engines cluster, RECONCILED with the live gate. This SOP does NOT introduce a parallel pipeline. Three of these engines already run inside the image pipeline under these exact names - the FACIAL EXPRESSION ENGINE, the AUDIENCE ENGINE, and the WORLD ENGINE (slide-image-creator-sops.md element 11, "the THREE ENGINES") - and two of them (Hook, Recap) already run under their mechanic names (Hook Doctrine / Re-Pitch). This document promotes the full set of NINE engines to first-class, named, verifiable capabilities and POINTS AT the enforcement that already exists, adding new enforcement only where a real gap was found (Lighting skin-tone, Typography 8th-row + salesy-font, Story character-continuity, Product placement). Each engine below carries the same three parts: (a) a DEFINITION, (b) HOW TO VERIFY IT LANDED, and (c) FAILURE MODES that are auto-failed at QC.

---

## 1. PURPOSE

This department does not "make slides." It runs NINE INTELLIGENCE ENGINES against every deck. An engine is a named capability with (1) a definition, (2) a "how you know it landed" verification check, and (3) named failure modes that are auto-failed at QC. The phrase "intelligence engine" used to live nowhere in the library even though the pipeline already spoke three of them by name; this SOP is the single artifact that proves the department actually runs this taxonomy, end to end, and wires each engine to its gate.

**The binding principle across ALL engines (the spine) — ATTENTION, then coherence:**

> **THE SPINE IS ATTENTION.** Every engine exists to do ONE job: **hold the audience's
> attention for the whole duration so the owner's offer or idea re-ranks to the top of the
> audience's priority stack** (the priority shift). The engines are not a coherence checklist —
> they are the machinery that wins and keeps attention, and the creativity of the imagery is the
> engine that holds it (salience / von Restorff). A deck on which the engines technically "pass"
> but the attention is lost and nothing re-ranks has failed the spine. Parent doctrine: **the
> North Star — `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` §0 / `SOP-NORTHSTAR-00` (when
> present).**
>
> **The coherence law (in service of the spine, not above it):** THE IMAGE MUST REFLECT WHAT
> THE WORDS SAY, AND THE WORDS MUST MATCH WHAT THE IMAGE REFLECTS. Any slide where the picture
> and the copy tell different stories is a defect (AF-WORD-IMAGE-MISMATCH). Coherence is
> necessary because incoherence breaks attention — it is the floor, never the goal.

**Each engine is a psychology lever that holds or shifts attention.** Naming the lever is *why*
the engine is enforced — it lets the role adapt rather than copy. (Lever numbers are the Part-3
psychology levers of the *Powerful Presentation Framework*.)

| # | Engine | Attention/priority lever | Framework lever |
|---|---|---|---|
| 1 | Facial | identity & purpose — a guide's face transfers the felt identity the audience prioritizes | **P50** identity/purpose |
| 2 | Lighting | salience — correct, dimensional light makes the hero subject the most vivid thing in frame | **P48** salience / von Restorff |
| 3 | Typography | salience — the 8th-row-readable, intent-signaling headline is the distinct thing the eye fixes on | **P48** salience / von Restorff |
| 4 | Story (villain→hero) | identity & purpose — character continuity + the villain→hero arc tie the offer to who they are | **P50** identity/purpose |
| 5 | World | salience — a believably grounded world is vivid and credible; a generic backdrop is forgettable | **P48** salience / von Restorff |
| 6 | Pricing (promise-before-price) | anchoring & contrast — the high true-value anchor set before the number ranks the thing high | **P47** anchoring/contrast |
| 7 | Hook | salience — the verbatim refrain is the single most repeatable, distinct phrase in the room | **P48** salience / von Restorff |
| 8 | Recap / Re-Pitch | peak-end rule — the post-price recap engineers a deliberate ending the audience judges by | **P49** peak-end |
| 9 | Product [roadmap] | salience — the real product placed in-world is a vivid, memorable brand cue | **P48** salience / von Restorff |
| 10 | Emotional (felt-stakes) | loss aversion — the felt-stakes quantifier lands the present-tense cost of inaction | **P44** loss aversion |
| + | Representation / Hair | identity & purpose — authentic representation lets the audience see themselves in the vision | **P50** identity/purpose |

**The engines:** 1 Facial - 2 Lighting - 3 Typography - 4 Story (incl. villain->hero ordering) - 5 World - 6 Pricing - 7 Hook - 8 Recap - 9 Product (roadmap) - 10 Emotional (felt-stakes, NEW 2026-06-20). The Representation HAIR engine is enforced via the Brand Steward (SOP 9.2b) and registered as AF-HAIR-INAUTHENTIC.

---

## 1.5 ENFORCEMENT PHASE PER ENGINE (v15.0.0 — both halves honored)

Every engine is honored in the PHASE where its work actually lives — the **writing** (copy/script/offer), the **image** (the prompt + the rendered pixels), or **both** — and fires at the EARLIEST detectable phase (shift-left). The perceptual engines' mechanical halves are render-wired (shipped v14.28.x); the narrative + pitch engines are wired into the render preflight in v15.0.0 so a deck cannot reach kie.ai with a missing engine even if an agent skipped copy-QC.

| # | Engine | Phase enforced | Where the gate fires (v15.0.0) | Auto-fail code(s) |
|---|---|---|---|---|
| 1 | Facial | **image** (prompt token) + vision verdict | PROMPT-QC (`check_intelligence_engines_prompt`) + IMAGE-QC | AF-FACE-PROMPT-MISSING / AF-FACE-MOOD |
| 2 | Lighting | **image** (prompt token) + vision | PROMPT-QC + IMAGE-QC | AF-LIGHT-PROMPT-MISSING / AF-LIGHT-SKINTONE |
| 3 | Typography | **both** (copy law + image perceptual) | COPY-QC (one-big-idea, font floor) + IMAGE-QC (8th-row, salesy-font) | AF-TYPE-8THROW / AF-TYPE-SALESY-FONT / AF-FONT-FLOOR |
| 4 | Story (character + villain→hero) | **writing** (copy) | COPY-QC (`check_intelligence_engines_copy` / `pitch_engines_check`) + render-preflight backstop | AF-NO-VILLAIN / AF-STORY-CHARACTER-DRIFT |
| 5 | World | **image** (prompt token) | PROMPT-QC | AF-WORLD-SCALE |
| 6 | Pricing (promise-before-price + cadence) | **writing** (offer) + **image** (price-reveal slide) | COPY-QC (`check_pitch_engines --phase 1Q`) + render-preflight backstop | AF-CADENCE / AF-NO-COST-OF-INACTION / AF-GUARANTEE-GENERIC / AF-NO-BRANDED-METHOD / AF-NO-TIME-TO-RESULT |
| 7 | Hook (suppressor) | **both** (copy refrain + image no-footer/verbatim baked) | COPY-QC (3–4 band) + PROMPT-QC (`check_hook_image`) | AF-HOOK-1..7 (copy) + AF-HOOK-IMG (image) |
| 8 | Recap / Re-Pitch | **writing** | COPY-QC | AF-DEN-7 / c23 / c24 |
| 9 | Product [ROADMAP] | **image** | PROMPT/IMAGE-QC (gated on PRODUCT_ASSET_URL) | AF-PRODUCT-INVENTED / AF-PRODUCT-MISSING |
| 10 | Emotional (felt-stakes) | **writing** (copy) | COPY-QC (`check_intelligence_engines_copy` / `chk_felt_stakes`) + render-preflight backstop | AF-NO-FELT-STAKES |
| + | Representation / Hair | **image** (prompt token) | PROMPT-QC | AF-HAIR-INAUTHENTIC / AF-R* / AF-CAST |
| — | **Harmony** (orchestration layer) | **all three** | COPY-QC (narrative) + PROMPT-QC (per-slide) + PRE-ASSEMBLY (deck-level) | AF-HARMONY (SOP-HARMONY-01) |

The mechanical-half doctrine (§2 below) is now render-wired for the perceptual engines (Facial / Lighting / World / Hair) and wired into the render preflight for the narrative + pitch engines (Story / Emotional / Pricing) in v15.0.0 via `build_deck.check_intelligence_engines_copy` and `build_deck.check_pitch_engines`.

## 1.6 THE EXCELLENCE PRINCIPLE (amazing, not merely compliant)

Clearing the LENGTH floor (9,000 chars; max 18,000) is **necessary but never sufficient.** The named engines being present is the QUALITY floor — and the two are **separate gates**: length never buys a pass, engines never buy a pass, BOTH are required (the TWO FLOORS, §1.1a of the build spec). EXCELLENCE is the dimension that proves the character budget was spent on **defect-preventing specificity** — per-line spelling-lock coverage, the full eight-class negative block, complete people-anatomy + world-grounding, grade detail — **not on boilerplate padding.** A floor-grazing, boilerplate-padded prompt scores LOW on EXCELLENCE and is **routed back even though it clears 9,000 chars** (`AF-EXCELLENCE`). The standard is *amazing, orchestrated in harmony* — the budget is for richness, never bulk.

---

## 2. THE NINE ENGINES

### Engine 1 - FACIAL INTELLIGENCE

**Definition.** The face on every people-slide is engineered to match the message. The expression carries the slide's emotion (passion, purpose, sensitivity) and is inferred automatically from the slide copy - never defaulted to "smiling," never "too salesy." A guide's face, not a closer's face.

**How to verify it landed.** Read the slide copy with the image covered, predict the emotion, uncover the image - the face matches. On a serious or sober beat the subject reads DISTANT, NOT ANGRY (facial intelligence on a heavy beat is distance, not aggression). Cross-check the rendered expression against the Expression Vocabulary Table.

**Failure modes (auto-failed at QC).** Smiling on a pain slide; a blank or dour face on a positive beat; an over-eager "salesperson" face on a trust beat; any expression that contradicts the copy.

[CROSS-REF] Already enforced: slide-image-creator-sops.md element 11 (FACIAL EXPRESSION ENGINE), the Expression Vocabulary Table (SOP 9.2 strengthening), Part E "Facial-intelligence rule," auto-fail AF-FACE-MOOD. ADDED by this update: the "distant, not angry" tell and the explicit "never a salesy face on a trust beat" line (slide-image-creator-sops.md Part E).

---

### Engine 2 - LIGHTING INTELLIGENCE

**Definition.** The subject is lit correctly FOR THEIR SKIN TONE. Deep skin is lit rich, warm, and dimensional - never crushed into the too-dark "murderer" look. Lighter skin is never blown out into the flat, ghostly "Casper" look. Every people-prompt states a key / fill / rim direction appropriate to the cast member's skin tone, and names a rim or hair light ("lighting on top of the hair") as the tell that the subject is correctly separated from the background. Lighting is a SKIN-TONE property, not a single deck-wide recipe.

**How to verify it landed.** Deep-skin subjects show visible tonal range on the face (catchlights, modeled cheeks, a lit hair edge), not a silhouette; lighter-skin subjects retain texture and shadow, not a washed-out ghost; a rim or hair light is present on the hero subject.

**Failure modes (auto-failed at QC).** Deep skin rendered as a dark silhouette (the "murderer" failure); a lighter-skinned subject over-lit flat-white (the "Casper" failure); no rim or hair light on the hero subject; a single deck-wide lighting recipe applied regardless of skin tone.

[CROSS-REF] Before this update only scene / time-of-day presets existed (slide-image-creator-sops.md SOP 9.3 "Lighting + World Library") plus a COLOR-preservation negative (do not ashen / grey / desaturate deep skin tones). ADDED by this update: a skin-tone LIGHTING sub-section to SOP 9.3 and a new negative-prompt class. New auto-fail: AF-LIGHT-SKINTONE.

---

### Engine 3 - TYPOGRAPHY INTELLIGENCE

**Definition.** Type is engineered for the room and the goal. Headlines are big enough to read FROM THE 8TH ROW. One big idea per slide. Typeface choice signals intent: certain fonts telegraph "salesy / cheap / $9.97-big-price-tag" and are BANNED when the goal is trust. "Typography and funnel are the same thing" - the type does the persuading, so the type is chosen like a funnel step, not like decoration.

**How to verify it landed.** Stand back (or shrink the slide to about 25%) - the headline still reads = passes the 8th-row test. No banned salesy display faces on a trust deck. Exactly one idea per slide.

**Failure modes (auto-failed at QC).** Headline unreadable when shrunk (fails the 8th-row test); a loud "big price tag" carnival font on a credibility deck; two ideas competing on one slide.

[CROSS-REF] The weight ladder and hierarchy are already in SOP-DESIGN-01 (the 4-weight ladder, pt sizes relative to 1440px); one-big-idea in SOP-SLIDE-01. ADDED by this update to SOP-DESIGN-01: (a) the 8th-row readability test, (b) a "fonts to avoid for trust" taxonomy, (c) the "typography = funnel" framing. New auto-fails: AF-TYPE-8THROW (headline fails the shrink test) and AF-TYPE-SALESY-FONT.

---

### Engine 4 - STORY INTELLIGENCE (S-T-O-R-Y)

**Definition.** The imagery accurately tells the deck's story, and a recurring CHARACTER is carried across slides at different life stages (the same kid younger and older) to build narrative continuity. The picture advances the arc; it does not just decorate it.

**How to verify it landed.** Trace the named character across the deck - the same person, recognizably aged or changed per the arc; the image sequence, read alone, tells the story the copy tells.

**Failure modes (auto-failed at QC).** A different stock person on every slide where continuity was intended; an image that contradicts the narrative beat; "decorative" imagery with no story job.

**Story narrative ordering -- VILLAIN before HERO (the 2026-06-20 addition).** Story Intelligence is not only VISUAL character continuity; it is the NARRATIVE arc itself: problem -> promise, and specifically VILLAIN -> HERO. "No one cares about the hero until they meet the villain." The arc must carry an explicit VILLAIN/antagonist beat (the broken system, the old way, the lie they've been told, the thing actually stopping them) that PRECEDES the HERO/solution/promise beat. The Slide Copywriter writes and tags these beats (`VILLAIN`, `HERO` -- slide-copywriter-sops.md SOP 9.7 step 23); the Director reserves the ordering in `arc_allocation.json`. Detection is mechanical: scan `slides_copy.md` arc tags in slide order; a missing villain, or a villain that appears after the hero, fails. New auto-fail: AF-NO-VILLAIN (deck-level; SOP-STORY-01; SOP-SLIDE-00 §8b; checker `scripts/intelligence_engines_check.py --phase copy`). ORTHOGONAL to AF-STORY-CHARACTER-DRIFT (the two never both fire on one finding).

[CROSS-REF] NEW capability. It conflicted with the prior line in slide-image-creator-sops.md Part D ("Consistency is a color and light property, not a composition property"), which silently blocked same-character continuity. That line was AMENDED by this update to carve out a STORY_CHARACTER exception: when a slide is tagged `STORY_CHARACTER:<id>`, the same person identity is held across its slides (image-to-image with a locked character reference), aged per the beat. New auto-fails: AF-STORY-CHARACTER-DRIFT (visual continuity) and AF-NO-VILLAIN (villain->hero narrative ordering).

---

### Engine 5 - WORLD INTELLIGENCE (world-building)

**Definition.** The render KNOWS what the real world looks like. The environment is believable for THIS character: a roughly 15-year-old's room is a sports poster and a few trophies in a normal house - NOT a million-dollar condo. GPT-Image-2 is the mandated model specifically because of its strong real-world grounding.

**How to verify it landed.** Ask "would this exact person actually be in this exact room, with these exact props, at this moment?" - yes = pass. Props and scale match the character's real life and station.

**Failure modes (auto-failed at QC).** Aspirational over-scaling (a teen in a luxury penthouse); a generic studio backdrop where a real scene belongs; props that contradict the character's station.

[CROSS-REF] Already enforced: slide-image-creator-sops.md element 11 (WORLD ENGINE), SOP 9.3 "Lighting + World Library," QC grounding criterion. ADDED by this update: the believability / scale calibration rule (the "trophies, not a condo" example) in slide-image-creator-sops.md SOP 9.3, and the GPT-Image-2-for-grounding rationale STATED in SOP-IMG-01 (the model was pinned without the "why").

---

### Engine 6 - PRICING INTELLIGENCE

**Definition.** A named engine that owns how price is PRESENTED. Its first law: PROMISE PRECEDES PRICE - the promise is always stated before the number, because price-first decreases perceived value. "It's not the product they buy, it's the promise of what it does." It then runs the slow-drop, anchor, and value-stack mechanics.

**How to verify it landed.** On every price beat a promise was already on screen before the first number; the price arrives as a relief, not a shock; value is stacked above the anchor before the cheapest price.

**Failure modes (auto-failed at QC).** A number shown before any promise is planted; price stated cold; value not stacked above the anchor before the cheapest price.

[CROSS-REF] Mechanics already enforced: offer-price-strategist-sops.md SOP 9.1-9.5, SOP-PITCH-01 (slow drop), SOP-PITCH-02 (value stack and promises), AF-C7 / AF-DEN density gates. "Promise precedes price" already lives in SOP-PITCH-02; this update re-homes it as the FIRST LAW of Pricing Intelligence and cross-references it. Mostly a NAMING + framing change; no new gate.

---

### Engine 7 - HOOK INTELLIGENCE

**Definition.** Builds ONE canonical hook and reuses it verbatim at natural beats across the deck (the sacred refrain), never reworded, never stamped as a footer band.

**How to verify it landed.** The exact hook string appears on 3 to 4 dedicated slides and nowhere else; it is identical every time.

**Failure modes (auto-failed at QC).** Hook reworded or mutated; hook stamped as a footer on every slide; hook duplicated on one slide; more than 4 appearances; zero dedicated hook slides.

[CROSS-REF] Fully enforced: SOP-SLIDE-03 (HOOK DOCTRINE), hook-strategist-sops.md, the AF-HOOK / AF-C2 / AF-P12 battery. Pure NAMING / cross-reference change (alias "Hook Doctrine" -> "Hook Intelligence"); no new gate.

---

### Engine 8 - RECAP INTELLIGENCE

**Definition.** Near the close, recaps the value received AND the price - so the buyer re-feels the full stack against the number before deciding. (Already built and shipping under the name "Re-Pitch.")

**How to verify it landed.** A 4-to-7-slide recap block exists after the final price and before the send-off; it restates value + price and introduces nothing new.

**Failure modes (auto-failed at QC).** No post-price recap; recap introduces a new claim or offer; value recapped without re-stating price (or vice-versa).

[CROSS-REF] Fully enforced: SOP-PITCH-03 (RE-PITCH), offer-price-strategist-sops.md SOP 9.9, QC copy criteria c23 / c24, AF-DEN-7. Pure NAMING change (alias "Re-Pitch" -> "Recap Intelligence"); no new gate.

---

### Engine 9 - PRODUCT INTELLIGENCE  [ROADMAP / NEW]

**Status:** Documented capability, gated. The intake field and slide tag are now defined; treat as enforceable on any deck that carries a PRODUCT_ASSET_URL.

**Definition.** Subtle, in-world product placement - the brand's actual product (for example a book, a bottle, a box) sitting naturally in-scene, the way a sponsor's product sits on a TV-show desk. Distinct from the formal logo chip. Little brands can do it too. The real product is composited image-to-image from a supplied PRODUCT_ASSET_URL, never reinvented as a garbled or made-up cover.

**How to verify it landed.** On designated PRODUCT_PLACEMENT slides, the client's real product appears as a believable scene object (on a desk, in hand, on a shelf), correctly branded, not a floating logo and not competing with the headline.

**Failure modes (auto-failed at QC, on a PRODUCT_PLACEMENT slide).** The product is absent on a slide tagged for placement (AF-PRODUCT-MISSING); the product is rendered as a garbled or invented cover instead of image-to-image from the real asset (AF-PRODUCT-INVENTED); placement breaks World Intelligence believability or covers copy.

[CROSS-REF] NEW. The intake field `PRODUCT_ASSET_URL` and the slide tag `PRODUCT_PLACEMENT:yes` are defined here. Enforcement: slide-image-creator-sops.md adds a 16th people / scene element, "PRODUCT PLACEMENT (image-to-image, from PRODUCT_ASSET_URL)," mirroring the logo image-to-image mechanic (element 10) so the real product is composited, never reinvented. New auto-fails: AF-PRODUCT-INVENTED, AF-PRODUCT-MISSING. Pairs with the Subtle Brand Cue doctrine in brand-steward-sops.md.

---

### Engine 10 - EMOTIONAL INTELLIGENCE  [NEW 2026-06-20]

**Definition.** The deck makes the audience FEEL the cost of inaction in concrete HUMAN terms, not abstract ones. Its signature device is the felt-stakes quantifier -- "3,285 mornings left" -- a real NUMBER fused to a personal-loss frame, landed BEFORE the offer so the audience feels what's at stake before they see a price. This is the emotional twin of Pricing Intelligence's "promise precedes price": felt-stakes precede the close.

**How to verify it landed.** At least one FELT_STAKES slide exists before the first ladder beat (ANCHOR/BUILDUP/DROP/FINAL), pairing a concrete number with a personal-loss frame ("mornings left", "days you'll never get back", "every day you wait costs you"). Read the deck in order: the audience feels the cost before the offer arrives.

**Failure modes (auto-failed at QC).** No felt-stakes slide anywhere (stakes stated only abstractly); a felt-stakes slide placed AFTER the offer ladder (too late to do its job); a fabricated number (the figure must come from the Deep Research brief or intake, never invented).

[CROSS-REF] NEW. Owned by the Slide Copywriter (copy + `FELT_STAKES` beat tag -- slide-copywriter-sops.md SOP 9.7 step 22) and the Deep Research Specialist (the real number). It survived before only as element 13 MOOD + copy-QC `SP-SEE`/`SP-JOURNEY` with no required beat; this promotes it to a first-class engine with a deck-level gate. New auto-fail: AF-NO-FELT-STAKES (deck-level; SOP-SLIDE-00 §8b; checker `scripts/intelligence_engines_check.py --phase copy`).

---

### THE PERCEPTUAL-ENGINE MECHANICAL-HALF DOCTRINE (Facial / World / Lighting / Hair) [NEW 2026-06-20]

Four engines above (Facial=1, Lighting=2, World=5) plus the Representation HAIR engine are irreducibly perceptual at the VERDICT layer -- "does the face read the slide's emotion", "would this person be in this room", "is this subject lit for their skin tone", "is the hair authentic". Per the binding doctrine *a rule that cannot be mechanically checked is not a rule*, each is split into two halves:
- a MECHANICAL half (the GATEABLE half) -- a required token string MUST be present in the people/scene prompt, asserted deterministically at Prompt QC by `scripts/intelligence_engines_check.py --phase prompt`. This is the hard auto-fail trigger. Codes: AF-FACE-PROMPT-MISSING (expression token), AF-WORLD-SCALE (setting + believability justification), AF-LIGHT-PROMPT-MISSING (key/fill/rim direction + rim/hair light), AF-HAIR-INAUTHENTIC (age-banded hairstyle-catalog token).
- a VISION VERDICT half -- the perceptual call, graded at Image-QC and LOGGED to `working/qc/vision_qc_log.json` (already required non-empty by AF-NO-VISION-QC). Codes: AF-FACE-MOOD, AF-WORD-IMAGE-MISMATCH/world-grounding, AF-LIGHT-SKINTONE, the plastic-hair read.

This is how the Slide-00 binary-auto-fail principle is kept literally true for perceptual engines. Producing-role doctrine: slide-image-creator-sops.md SOP 9.3b (prompt-token mandate) and brand-steward-sops.md SOP 9.2b (hairstyle catalog). Registration: SOP-SLIDE-00 §8b + §9 code index. Typography (Engine 3) is already fully mechanical and needs no such split.

---

## 3. NOTE - IMAGE EDITING IS A LEGO SET

People, races, poses, and scenes are modular: mix and match via image-to-image to build the exact cast a slide needs (this ties to the Personal Photo Shoot skill). The Facial Intelligence engine infers the right expression automatically from the slide copy; the operator does not hand-pose every face. This is the mental model behind the engines, not a separate gate.

---

## 4. THE REQUIRED SLIDE-TYPE DOCTRINES (which engines produce which beats)

The engines above are CAPABILITIES; the deck-density SOP (SOP-SLIDE-04) and the pitch cluster turn several of them into REQUIRED BEATS. These are listed here so the framework is the single map; the enforcement lives in the named SOP.

- **Formula slide** (this + this + this = this; e.g. M+M+M=M) - required beat, SOP-SLIDE-04, gated AF-NO-FORMULA.
- **Measurable Results slide** ("decide on emotion, justify with logic"), distinct from the Wall of Wins - required beat, SOP-SLIDE-04, gated AF-NO-MEASURABLE-RESULTS.
- **Fork-in-the-Road decision tree** (two paths; a visible CHECK-MARK on the chosen path; the other path carries the cost of inaction) - required beat, SOP-SLIDE-04, gated AF-NO-FORK.
- **Before & After** (at least 1, 2 to 3 ideal) - required beat, SOP-SLIDE-04, gated AF-NO-BEFORE-AFTER.
- **External Proof** - Expert Quote boxes AND a "the science agrees" studies slide, distinct from the Wall of Wins - required beats, SOP-PITCH-04, gated AF-NO-EXPERT-PROOF.
- **Subtle Brand Cue** (a hidden in-world reminder of the brand's core value) - brand-steward-sops.md; pairs with Product Intelligence.
- **Hybrid delivery** (live -> record -> live; at least 3 live runs before the recording is cut) - presenter-coach-sops.md + delivery-concierge-sops.md.
- **Per-slide speaker notes in the .pptx notes pane** - pptx-assembly-specialist-sops.md, gated AF-EMPTY-NOTES-PANE.

---

## 5. ESCALATION / REPAIR PATH

1. Any engine auto-fail at QC routes the slide (or deck, where the code is deck-level) back to the owning role named in the engine's CROSS-REF, with the exact failing code and message.
2. For the NAMING-only engines (Pricing, Hook, Recap) there is no new gate; their existing gates (AF-C7 / AF-DEN, AF-HOOK / AF-C2, c23 / c24 / AF-DEN-7) are the enforcement and this SOP only renames and cross-references them.
3. For the NEW gates (AF-LIGHT-SKINTONE, AF-TYPE-8THROW, AF-TYPE-SALESY-FONT, AF-STORY-CHARACTER-DRIFT, AF-PRODUCT-INVENTED, AF-PRODUCT-MISSING) and the required-beat gates (AF-NO-FORMULA, AF-NO-MEASURABLE-RESULTS, AF-NO-FORK, AF-NO-BEFORE-AFTER, AF-NO-EXPERT-PROOF, AF-EMPTY-NOTES-PANE, AF-WORD-IMAGE-MISMATCH), see SOP-SLIDE-00 Section 8 for the wired detection method and message.
4. Loop up to 3 times. On the 4th failure escalate to the Director and ROLE-16 Healer per QC SOP 9.4.

---

## 5.2 REDUNDANT / ALIASED ENGINES (the single authoritative merge map — do NOT add a parallel code)

Several engines named in the June-19 breakdown are REAL devices but are already fully enforced by an existing auto-fail under a different name. They are MERGED here, not given a parallel namespace. Adding a duplicate `AF-NO-SHIFT` / `AF-NO-COMPARISON` / `AF-NO-CHOICE` code would create a second gate for the same beat and is forbidden (it would also create lockstep drift in `sync_check.py`). The mapping below is the authority:

| Breakdown engine / device | MERGED INTO (the live enforcing code) | Why it is the same beat |
|---|---|---|
| **Shift** (was / now) | `AF-NO-BEFORE-AFTER` (SOP-SLIDE-04 rule 13) | "was → now" IS the Before & After transformation beat. A separate shift gate would fire on the identical slide. |
| **Comparison & Contrast** (what it was / what it is) | `AF-NO-BEFORE-AFTER` (SOP-SLIDE-04 rule 13) | The same was/is device. One required before/after pair satisfies both. |
| **Choice** (DIY-alone vs with-us; two paths) | `AF-NO-FORK` (SOP-SLIDE-04 rule 12) | The Fork-in-the-Road already presents EXACTLY two paths (act / stand still), a check-mark on the chosen path, and the cost of inaction on the unchosen path. "DIY-alone vs with-us" IS that fork; the copy doctrine in SOP-SLIDE-04 rule 12 frames the two branches as act-with-us vs stand-still-alone. No new code. |
| **Pricing** (Engine 6) | `AF-C7` / `AF-DEN` battery (offer-price-strategist SOP 9.1-9.5, SOP-PITCH-01/02) | NAMING alias only (§5 rule 2); "promise precedes price" is re-homed here, the gates are the slow-drop/value-stack codes. |
| **Hook** (Engine 7) | `AF-HOOK` / `AF-C2` / `AF-P12` battery (SOP-SLIDE-03) | NAMING alias only; the verbatim-refrain + banded-cadence gates ARE the enforcement. |
| **Recap** (Engine 8) | `AF-DEN-7` + copy `c23`/`c24` (SOP-PITCH-03 RE-PITCH) | NAMING alias only; the post-FINAL 4-7-slide re-pitch block IS the recap. |

The Pricing / Hook / Recap rows restate §5 rule 2 (the three NAMING-only engines); the Shift / Comparison / Choice rows are the NET-NEW merges added by the 2026-06-20 structure consolidation so the breakdown's full device list maps cleanly onto the existing gates with zero duplicate codes.

---

## 6. INTEGRATION NOTE

This SOP is the index; the enforcement is distributed. Cross-reference: slide-image-creator-sops.md (Facial, Lighting, Story, World, Product), SOP-DESIGN-01 (Typography), SOP-IMG-01 (the GPT-Image-2 grounding rationale), SOP-PITCH-02 (Pricing first law), SOP-PITCH-03 (Recap), SOP-SLIDE-03 / hook-strategist-sops.md (Hook), SOP-PITCH-04 (External Proof), SOP-SLIDE-04 (the required slide-type beats), brand-steward-sops.md (Subtle Brand Cue), presenter-coach-sops.md + delivery-concierge-sops.md (Hybrid delivery), pptx-assembly-specialist-sops.md (notes pane), and SOP-SLIDE-00 Section 8 (the registered auto-fail codes). The promotion of the three existing un-named engines (Facial, Audience, World) into the named nine is the highest-leverage change: it makes the department sound and behave as deliberate as it already is.
