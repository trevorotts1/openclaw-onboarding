# SOP-DIU-611 — Graphics↔Presentations Deck Boundary Contract

**ID:** SOP-DIU-611
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Deck Systems Specialist (primary); Director of Presentations (named arbiter)
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** PPT-ANALYSIS-SOP v1.0, MASTER-SOP v1.0, CLIENT-WEBINAR-DECK-SOP v1.0, powerpoint-designs/_RULES.md v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Deck Systems Specialist runs this SOP on every deck request before any other action — manifest assembly, style analysis, or generation. Its purpose is to resolve which pipeline owns a given deck and what the only legal crossings between the two pipelines are.

This seam is the highest-risk boundary the DIU creates. The Presentations department owns CLIENT-WEBINAR-DECK-SOP, which carries five contracted archetypes, white-base doctrine, and a GPT-Image-2-only model manifest. The DIU owns PPT-ANALYSIS-SOP, which routes across seven endpoints and produces dark, brand-matched foundations. Both pipelines can plausibly claim a client deck at intake. An incorrectly routed deck means wasted metered generation spend, contradictory client deliverables, and a department-level conflict at the company's most visible output type.

This SOP is never skipped for deck requests. It takes two minutes on clear cases. It saves regenerations, budget overruns, and client trust on ambiguous ones.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/PPT-ANALYSIS-SOP.md` | §§3B–3C (Slide Manifest as interface artifact; strategy-(b) background-only handoff; re-route, don't downgrade) | The DIU deck pipeline's Slide Manifest contract; strategy-(a) vs strategy-(b) text handling; fallback routing rules |
| `powerpoint-designs/_RULES.md` | Full file (format table, text strategy, Rotation Engine parameters, resolution tiers) | All PPT-category card constraints; the Rotation Engine's domain — runs only on DIU-routed decks |
| `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` | Full file (five archetypes, white-base doctrine, GPT-Image-2-only model manifest, editable text contract) | The Presentations pipeline's exclusive scope; the model manifest that the DIU routing table never overrides |
| `presentations/00-START-HERE.md` | Mirror paragraph T7b (boundary contract counterpart — the Presentations-side view of this seam) | Confirms the Presentations department's view of the legal crossings; must agree with this SOP |

All routing verdicts, archetype definitions, pipeline scope, and model-manifest rules are read from the library files above at runtime. Do not reproduce archetype lists, pipeline ownership rules, or model manifests in this SOP.

---

## Procedure (ordered)

### A. Deck type identification (run on every deck request, before any other step)

1. **Read the brief.** Identify: deck purpose, target audience, any existing style reference or style ID, client context, and whether the brief explicitly names a webinar, funnel, virtual event, or training context.

2. **Apply the decision table.** Match the deck to exactly one row. If no row fits cleanly, the deck is ambiguous — go to step A.3.

   | Deck type | Routing verdict | Owning party |
   |---|---|---|
   | Webinar, funnel, or virtual event deck matching any of the five CLIENT-WEBINAR-DECK-SOP archetypes | **Presentations dept — CLIENT-WEBINAR-DECK-SOP** | Director of Presentations |
   | Strategy, brand, campaign, or portfolio deck requiring a visually analyzed client/brand style system | **DIU — PPT-ANALYSIS-SOP + Rotation Engine** | Deck Systems Specialist |
   | Sales proposal, capability deck, investor pitch, or onboarding deck with no specific style ID | **Presentations dept (narrative + layout)** with optional DIU strategy-(b) background imagery on request via SOP-DIU-612 | Director of Presentations primary; CDO requests imagery cross-dept |
   | Training or onboarding deck | **Presentations dept** unless the brief explicitly specifies a brand style system | Director of Presentations (default); CDO confirms DIU involvement if a style ID is specified |
   | Ambiguous — does not fit any row above | **Escalate to Director of Presentations** for arbiter decision | Director of Presentations decides; CDO coordinates; decision logged |

3. **Ambiguous deck escalation.** Route the brief to CDO immediately. CDO forwards to the Director of Presentations for the arbiter decision. The Deck Systems Specialist does not contact the Presentations department directly. Decision is logged in the deck's project record with: the ambiguity description, the deciding party, and the date. Log feeds the quarterly boundary contract joint review (see Section 6 of the Deck Systems Specialist how-to.md).

### B. DIU-routed deck: set text strategy before manifest assembly

1. After a deck is confirmed as DIU-routed, determine text strategy per `powerpoint-designs/_RULES.md`:
   - **Strategy (a):** text is generated into the slide image by Kie.ai. Use only when the client's style system requires text as an integral visual element.
   - **Strategy (b):** background-only generation; text-clear zones reserved for editable overlay by Presentations. Default for any deck where narrative copy is variable, editable, or lengthy.

2. Record the text strategy decision in the brief and in every row of the Slide Manifest before the manifest is handed to the Generation Operator. The strategy choice is locked at this point — it does not change per-slide without CDO approval.

3. For strategy-(b) decks, confirm at manifest assembly time that a Presentations handoff plan is agreed before generation begins. The Deck Systems Specialist verifies this with CDO; CDO communicates to the Presentations department. Never start strategy-(b) generation without confirming who will apply the text overlay layer.

### C. Legal crossings (the only two permitted interactions between the two pipelines)

1. **Crossing A — Brand Steward consumes a PPT-category foundation block as STYLE BLOCK input.** Within the CLIENT-WEBINAR-DECK-SOP pipeline, the Brand Steward may consume a PPT-category style card's foundation block as the STYLE BLOCK value in the cross-dept request template (SOP-DIU-612). The card governs the visual output; the Brand Steward does not write style into the request. This is the only permitted flow of DIU style content into the Presentations pipeline.

2. **Crossing B — DIU strategy-(b) imagery handed to Presentations for editable text overlay.** For confirmed strategy-(b) decks, the Deck Systems Specialist delivers completed background-only slide imagery (text-clear zones per `powerpoint-designs/_RULES.md`) to Presentations for editable text overlay. The Slide Manifest is the interface artifact — one manifest, one owner per phase (Deck Systems Specialist during generation; Director of Presentations during text overlay and final assembly).

### D. Hard rules (override all other routing and pipeline logic)

The following rules have no exception path:

1. **ROUTING INTERLOCK (coded hard stop):** An audience deck, webinar deck, funnel deck, or virtual event deck CANNOT proceed on the DIU strategy-(b) pipeline. This is not a preference - it is a mechanical gate. Any deck matching a CLIENT-WEBINAR-DECK-SOP archetype routes to Presentations regardless of the client's personal brand style, any existing DIU style card, or CDO convenience. The Deck Systems Specialist must halt the DIU workflow the moment a deck is identified as audience/webinar and route to CDO for forwarding to the Presentations Director. Proceeding past this gate on the wrong pipeline is an architecture violation; the deck would be assembled primarily from bare backgrounds with overlay text boxes, which is an AUTO-FAIL at final QC.

2. **ARCHITECTURE LOCK:** Text-in-image is THE rule for webinar and audience decks. The DIU strategy-(b) background-only approach is a per-element fallback only for non-audience DIU-routed decks. For audience/webinar decks, the Presentations pipeline's GPT-Image-2 text-in-image approach is the only legal architecture. The DIU's seven-endpoint routing table never overrides the CLIENT-WEBINAR-DECK-SOP model manifest.

3. **Slide Image Creator prompts in the Presentations pipeline may not silently override a contracted PPT-category foundation block.** If Presentations requests imagery using an analyzed client style, the style card governs — Presentations sources the style via SOP-DIU-612, not by writing style directly into Slide Image Creator prompts.

4. **The Slide Manifest has exactly one owner per phase.** Concurrent edits to the manifest by both pipelines are forbidden. Ownership transfers explicitly: Deck Systems Specialist to Generation Operator (during generation); Generation Operator to Deck Systems Specialist (cohesion review); Deck Systems Specialist to Presentations (strategy-(b) text overlay). Any phase-overlap is escalated to CDO immediately.

### E. Routing decision logging

All non-trivial routing decisions — and all ambiguous-deck arbiter decisions — are logged in the deck's project record with: the decision, the deciding party, the date, and the decision table row applied. Trivial clear-row matches (no ambiguity) may be logged as a single-line note. Logs feed the quarterly boundary contract joint review.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Deck brief (purpose, audience, style reference or style ID, client context) | Yes | CDO — must be complete before this SOP runs |
| `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` (current version, pinned) | Yes | Read at runtime — confirms the five Presentations archetypes |
| `presentations/00-START-HERE.md` (boundary mirror paragraph) | Yes | Read at runtime — confirms Presentations-side view of legal crossings |
| `powerpoint-designs/_RULES.md` (text strategy table, Rotation Engine scope) | Yes | Read at runtime for strategy-(a) vs strategy-(b) decision |
| `_system/PPT-ANALYSIS-SOP.md` (§§3B–3C, strategy-(b) handoff protocol) | Conditional | Read at runtime when deck routes to DIU |
| Director of Presentations' arbiter decision (ambiguous decks) | Conditional | Via CDO — required before any work begins on an ambiguous deck |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Routing decision + text strategy (for DIU-routed decks) | Deck project record | Documented; manifest assembly may begin |
| Forwarded brief (for Presentations-routed decks) | CDO for forwarding to Presentations dept | Forwarded |
| Logged arbiter decision (ambiguous decks) | Deck project record | Logged with deciding party + date |
| Confirmed Presentations handoff plan (strategy-(b) decks) | Deck project record + Slide Manifest header | Confirmed before generation begins |
| Slide Manifest (strategy-(b) completed imagery for Presentations) | `_local/jobs/{job-id}/SLIDE-MANIFEST.md` + delivery folder | Handed off at strategy-(b) completion |

---

## Handoff Conditions

- **DIU-routed, strategy-(a):** Proceed to SOP-DIU-201 (Deck Style System Analysis) if no production-status style card exists, or directly to SOP-DIU-202 (Slide Manifest Assembly) if a production-status card is confirmed in INDEX.md. CDO notified of routing decision.
- **DIU-routed, strategy-(b):** Proceed to manifest assembly. Before generation begins, confirm the Presentations handoff plan with CDO. At generation completion, hand background-only imagery to Presentations via the Slide Manifest interface artifact.
- **Presentations-routed:** Hand the brief to CDO for forwarding to the Director of Presentations. Deck Systems Specialist has no further involvement unless CDO explicitly requests strategy-(b) imagery cross-dept via SOP-DIU-612.
- **Ambiguous — awaiting arbiter:** All work halted. No analysis, no manifest assembly, no generation until the Director of Presentations' decision is logged.
- **Crossing A confirmed (Brand Steward consuming foundation block):** CDO coordinates. The Deck Systems Specialist confirms the correct card ID@version is provided to the Brand Steward. The card governs; the Brand Steward writes nothing into the STYLE BLOCK from memory.
- **Crossing B confirmed (strategy-(b) handoff):** Deck Systems Specialist delivers completed imagery with text-clear zones intact. Director of Presentations takes manifest ownership for text overlay phase.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Deck brief is incomplete (missing purpose, audience, or style reference) | Return to CDO with the specific missing fields. Do not route an incomplete brief. |
| Deck type is ambiguous — does not fit a decision table row | Escalate to CDO immediately for routing to Director of Presentations as arbiter. Halt all work. |
| Director of Presentations disputes a DIU routing decision after manifest assembly has begun | Halt generation immediately. Escalate to CDO. Do not continue a disputed deck run — wasted spend on the wrong pipeline is worse than a delay. CDO is the final arbiter. |
| Presentations pipeline requests imagery from a DIU style card without using SOP-DIU-612 | Refuse the direct request. Route CDO to formalize the cross-dept request via SOP-DIU-612. The card governs; direct Slide Image Creator overrides are forbidden. |
| A strategy-(b) deck reaches generation without a confirmed Presentations handoff plan | Hard stop. Notify CDO. Do not generate background imagery if there is no confirmed receiver for the text overlay phase. |
| Slide Manifest is being edited by both pipelines concurrently | Escalate to CDO immediately. Concurrent manifest edits corrupt the single-owner contract. |
| CLIENT-WEBINAR-DECK-SOP ships a new archetype | Apply update trigger: review the decision table in step A.2 and confirm the new archetype is correctly assigned to the Presentations row. Log any decision table revision with CDO. |
| `presentations/00-START-HERE.md` boundary mirror paragraph disagrees with this SOP | Escalate to CDO. The two views of the seam must agree. Never proceed with conflicting contracts. |
| Version pin for any governing file in this SOP is stale (detected by SOP-DIU-615 Healer sweep) | Halt routing decisions that depend on the stale file. Re-verify all §-refs against the current file version. Update the pin. Notify CDO. |

---

*Library-version pin: PPT-ANALYSIS-SOP v1.0, MASTER-SOP v1.0, CLIENT-WEBINAR-DECK-SOP v1.0, powerpoint-designs/_RULES.md v1.0 (§-refs verified 2026-06-12).*
