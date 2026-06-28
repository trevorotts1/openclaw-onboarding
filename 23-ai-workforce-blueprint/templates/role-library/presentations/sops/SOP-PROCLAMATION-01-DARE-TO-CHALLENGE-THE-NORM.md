# SOP-PROCLAMATION-01: PROCLAMATION -- DARE TO CHALLENGE THE NORM (the provocative content ceiling)

**Cluster:** North Star / Fuel. Child of SOP-NORTHSTAR-00 (attention is the #1 job) and SOP-PRIORITY-01 (Proclamation is one of the three power P's -- the fuel). The COPY counterpart to the imagery-creativity mandate: image creativity already has a gallery-grade ceiling; this SOP raises the ceiling for the WORDS.
**Owning role at write time:** Attention Content Strategist (owns the proclamation set -- "content that dares to challenge the norm" -- authored at P0B-PRIORITY, order 0.2) -> Slide Copywriter (executes the declarations on-slide) -> presenters-speech-writer (delivers them aloud, including the objection-as-expectation reframe).
**Enforced at the gate by:** QC Specialist - Presentations, via **AF-PROCLAMATION-HEDGE** (SLIDE-level) at COPY-QC (order 4.2) -- a hedge-token scan that fails a slide whose key declarations are softened into generic suggestions. Reinforces the existing slide-copywriter specificity rule (AF-C9 / "strengthen your language").
**Detection script:** `scripts/intelligence_engines_check.py check_copy` (hedge-token scan: "maybe", "kind of", "sort of", "you might want to consider", "perhaps", "we think", "could possibly" on a tagged PROCLAMATION beat). REGISTRATION PENDING -- Agent W3 (H->I->J lockstep).
**Registered:** PENDING Agent W3 lockstep. Until then this is stated copy doctrine the strategist and copywriter apply to PROCLAMATION-tagged beats.
**Enforcement phase:** Authored at P0B-PRIORITY (0.2, the proclamation set); written at P4-COPY (4); gated at COPY-QC (4.2, `AF-PROCLAMATION-HEDGE`); delivery-checked at P-SPEECH-QC (8.6, no-hedge).
**Status:** **DOCTRINE.** Provocative, norm-challenging COPY has no doctrine home today (imagery creativity is mandated; provocative content was only an optional tone). This SOP makes it the stated **ceiling for the words**. Gate `AF-PROCLAMATION-HEDGE` registered in lockstep by Agent W3.

---

## 1. THE RULE -- A PROCLAMATION IS A DECLARATION, NOT A HEDGE (P107-P109)

**Definition.** A proclamation is a bold, clear, declarative statement of truth -- not a hedge, a suggestion, or a soft opinion. It is a confident declaration the presenter stands behind about the audience's situation, the stakes, the value, and what is required.

> "Where there is a proclamation of truth, there is a demonstration of power." -- Trevor Otts

Proclamation is the **fuel** in the seven-P vehicle (with Promise -- SOP-PRIORITY-01 §4). Fuel that is hedged does not burn. Tentative language transfers **doubt** and leaves the priority feeling **optional** -- which is fatal, because the whole job is to make the thing feel non-optional (the priority shift, SOP-NORTHSTAR-00). If the presentation declares nothing, it has no fuel.

**The dare.** This is the COPY ceiling. The Attention Content Strategist's mandate is to author content that **dares to challenge the norm** -- to say the thing the audience has been circling but no one in their world will say plainly. A proclamation names the real problem, the real cost, the real value, and what is required, without flinching. The provocation is not edginess for its own sake; it is the refusal to soften a true thing into a comfortable thing. (This is the verbal twin of the imagery mandate that refuses the corporate, the seen-it-before, the safe -- SOP-DESIGN-03 / the Attention Designer.)

## 2. HOW TO DIAGNOSE PROCLAMATION (the hedge tell)

Read the language of the key beats. Is it hedged and generic -- full of "maybe," "kind of," "you might want to consider" -- or does it state the key truths plainly and specifically? If the deck's central truths are softened, Proclamation is the broken P. The gate `AF-PROCLAMATION-HEDGE` scans PROCLAMATION-tagged beats for hedge tokens and fails the slide.

## 3. HOW TO REMEDIATE -- WRITE THE TRUTHS AS DECLARATIONS (P110)

Identify the handful of truths the audience most needs to hear stated without flinching, and rewrite each as a declaration:
- **Name the real problem plainly.**
- **Name the real cost of inaction plainly.** (Feeds move 2 of the build sequence + felt-stakes, SOP-ENGINE-00 Engine 10.)
- **Name the real value plainly.** (Value before price -- SOP-PITCH-02.)
- **Name what is required plainly.**

Then strengthen the language until it says **exactly** what is meant -- not a softened approximation. *"Your mind will move toward a generic version of what you are saying unless you give it specificity."* This reinforces, and shares enforcement with, the Slide Copywriter's existing specificity discipline (AF-C9, "strengthen your language") -- do not duplicate that machinery; this SOP supplies its doctrine and the PROCLAMATION beat tag.

**Canonical proclamation:** *"The problem is not the price. The problem is your expectation. You expect less of yourself, so you invest little in yourself."*

## 4. THE OBJECTION-AS-EXPECTATION REFRAME (P137-P139)

A proclamation is the device that reframes an objection as an **expectation**, not a cost. When the audience reaches for "it costs too much," the norm-challenging move is to refuse the price frame and declare the deeper truth:

> "This is not a question of, is this thing worth it? It's worth hundreds of thousands of dollars. The price is just what you invested. Because where there is no investment, there is no appreciation." -- Trevor Otts

> "The problem is not the price; the problem is your expectation. You expect less out of yourself, and because you do, you invest little in yourself. You have to invest in yourself at the level at which you expect results." -- Trevor Otts

The closing pivot is a set of **identity questions** delivered as proclamations: do I have something worth telling, have I been capitalizing on what I know, have I turned my experience into a return? Underneath sits the same law: **price only matters in the absence of value** -- so when the objection is about cost, the move is to return them to the **vision** (SOP-VISION-01), not to the price. (The full price-is-a-value-problem doctrine lives in SOP-OBJECTION-01; this SOP owns the *declarative form* of the reframe -- the words that dare.)

## 5. THE BOUNDARY -- DARE, BUT NEVER FABRICATE

The proclamation ceiling raises **boldness and specificity**, never invention. A proclamation states a **true** thing plainly; it does not state a false thing confidently. The no-fabrication floor is absolute and already enforced (AF-C3, no fabricated proof/numbers/testimonials; honest scarcity and urgency only). Provocative does not mean exaggerated, and "challenge the norm" never means misrepresent the client's market. Where the truth is uncomfortable, declare it; where the claim is unproven, ask the presenter -- do not manufacture it.

## 6. FOR AGENT W3 -- ENFORCEMENT CODES THIS SOP DECLARES

- **AF-PROCLAMATION-HEDGE** (qc_check, SLIDE-level, COPY-QC 4.2) -- checker: hedge-token scan over PROCLAMATION-tagged beats in `slides_copy.md` ("maybe", "kind of", "sort of", "you might want to consider", "perhaps", "we think", "could possibly", "a little", "somewhat"). Register in lockstep (manifest v17->18 + ruleset Section 5 + SOP-SLIDE-00 mirror + qc-specialist wiring + test_preflight fixture). SLIDE-level (not deck-level): it fails the specific hedged slide, routing back through the copy-QC send-back loop. Reinforces existing AF-C9 specificity; the two are orthogonal (AF-C9 = vagueness/generic; AF-PROCLAMATION-HEDGE = tentative/hedged on a declaration beat).
