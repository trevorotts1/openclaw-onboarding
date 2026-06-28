# SOP-HARMONY-01: DECK COHESION (the orchestration layer above the engines)

**Cluster:** Intelligence Engines (the orchestration layer)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md; SOP-ENGINE-00 (the engine framework)
**Owning role at write time:** Director of Presentations (owns the recurring-character / palette / world-continuity / archetype-rhythm decisions across the deck)
**Contributing roles:** Slide Copywriter (narrative arc cohesion), Typography Architect (visual-system continuity), Slide Image Creator (per-slide composition), Brand Steward (palette), Offer Price Strategist (pitch arc)
**Enforced at the gate by:** QC Specialist - Presentations + QC Specialist - Image; the deterministic gate `build_deck.check_harmony` (deck-level), `check_narrative_harmony` (copy), and the per-slide harmony dimension inside `check_prompt_qc_deterministic`
**Registered:** SOP-SLIDE-00 §5 + §5.5; auto-fail `AF-HARMONY`
**Status:** Doctrine procedure, v15.0.0. This SOP defines the gate that proves the engines are *orchestrated in harmony* — not merely that each one passed in isolation.

---

## 1. WHY HARMONY IS A SEPARATE GATE

Ten engines can each pass on their own slide and still produce a deck that reads incoherent: a different stock person on every slide, a palette that drifts from teal to maroon to grey, a 15-year-old's bedroom on one slide and a luxury penthouse three slides later, and an archetype order with no rhythm. Per-slide compliance is **necessary but not sufficient**. Harmony is the orchestration layer ABOVE the per-engine checks — it asks one question the per-slide gates cannot:

> **Do the engines COHERE across the whole deck — one story, one world, one cast, one visual system, one deliberate rhythm — so the deck reads as ONE amazing thing, not fifty compliant fragments?**

This is the runtime form of Trevor's intent: the engines must be *"orchestrated in HARMONY to produce something AMAZING, not merely compliant."* `AF-HARMONY` is distinct from `AF-CREATIVITY` (which only rejects template SAMENESS — too much repetition); harmony rejects the OPPOSITE failure — incoherent variety with no through-line.

---

## 2. THE FOUR COHESION DIMENSIONS

### 2.1 Recurring-character continuity (Story engine, across slides)
A named character carried across the deck is the SAME recognizable person at every appearance, aged or changed only per the arc beat — never a different stock face. Where slides are tagged `STORY_CHARACTER:<id>`, the identity is held via image-to-image with a locked character reference. **Fails** when a slide tagged for continuity shows a different person, or the intended recurring cast fragments into unrelated faces.

### 2.2 Palette / brand coherence (cross-checked with `check_brand_consistency`)
The deck holds ONE brand palette. Dominant sampled colors per slide stay within the declared `intake.json brand.palette` token set (the `AF-BRAND-CONSISTENCY` tolerance). A break slide may invert for contrast, but the deck never drifts off-brand slide to slide. **Fails** on uncontrolled palette drift across the deck even when each slide individually renders.

### 2.3 World / scene continuity (World engine, across slides)
The world is believable AND consistent: the same character's environment, props, era, and station hold across their slides. A teen's room is trophies-not-a-condo on slide 8 and STILL a believable teen's room on slide 22. **Fails** on world discontinuity (a character's station/era/setting jumps incoherently between their slides).

### 2.4 Archetype rhythm (a deliberate cadence, NOT just anti-sameness)
The five proven archetypes (A1–A5) are sequenced with a deliberate rhythm — type-dominant beats and people beats alternate to a cadence that paces the deck, hook/section slides land on purpose, and the offer ladder rides its own visual build. This is distinct from `AF-CREATIVITY`'s dominance ceiling (which only fails > 60% one archetype). Harmony asks whether the ORDER is intentional, not merely varied. **Fails** when archetypes are scattered with no cadence (e.g. three section dividers back to back, or every offer rung rendered identically).

---

## 3. THE THREE PHASE PLACEMENTS (shift-left — one concept, three gates)

The single harmony concept is enforced at the **earliest phase where each kind of incoherence is detectable**, so the deck is proven coherent before it is assembled — never assembled then found incoherent.

| Placement | Phase | What it proves | Gate symbol | Routes back to |
|---|---|---|---|---|
| **Narrative harmony** | COPY-QC (Phase 1Q), **before any prompt is authored** | the arc coheres in the COPY — villain→hero ordering holds, the promise/stakes/proof/CTA beats sequence into one story, the pitch cadence is unbroken | `check_narrative_harmony` (in the copy-QC path) | Slide Copywriter / Offer-Price Strategist |
| **Per-slide harmony** | PROMPT-QC, **before any render is paid for** | within each slide the engines cohere — the facial/lighting/world/typography tokens describe ONE consistent scene, the recurring-character reference is carried, the slide's palette matches the deck | per-slide harmony dimension of `check_prompt_qc_deterministic` | Prompt Author |
| **Deck-level visual harmony** | PRE-ASSEMBLY, **after render, before assembly/delivery** | across ALL rendered PNGs the four dimensions hold — recurring character, palette, world, archetype rhythm | `build_deck.check_harmony` (deck-level), alongside `check_brand_consistency` + `check_visual_variety` | Director of Presentations (re-render ONLY the inconsistent slides) |

A failure at any placement **routes back to the right owner and re-runs that phase's loop** (SOP-SLIDE-00 §5.5, the SEND-BACK-THROUGH rule) — it does not pass downstream. The deck-level gate fires **before** `assemble_pptx`, so an incoherent deck is caught before it is bundled, not after delivery.

---

## 4. HOW TO VERIFY IT LANDED

1. **Read the deck end to end as a story.** The copy alone tells one continuous arc (villain → stakes → promise → proof → offer → recap); no beat contradicts the one before it.
2. **Trace the named character** across every slide tagged for continuity — same person, aged only per the beat.
3. **Scan the palette** across all renders — one brand family; break slides are deliberate, not drift.
4. **Walk the world** — each character's environment, props, era, and station hold across their slides.
5. **Map the archetype order** — the A1–A5 sequence has a deliberate cadence, not scatter.

If all five hold, `AF-HARMONY` passes. If any fails, the offending slides route back to the Director (deck-level), the Copywriter (narrative), or the Prompt Author (per-slide), with the specific dimension named.

---

## 5. FAILURE MESSAGE & ESCALATION

`AF-HARMONY` failure message names the dimension and the offending slides, e.g.:
`AF-HARMONY: DECK FAIL -- recurring-character discontinuity (slides 8, 22, 31 show three different people where STORY_CHARACTER:hero continuity was reserved). Re-render with the locked character reference (SOP-HARMONY-01 §2.1).`

**Escalation.** Harmony failures route to the **Director of Presentations**, who owns the recurring-character / palette / world-continuity / archetype-rhythm decisions and re-renders ONLY the inconsistent slides. If a harmony loop exhausts its cap (`PROMPT_QC_MAX_ATTEMPTS`), the Director escalates to the human owner per QC SOP 9.4. A deck never ships while a harmony dimension is below standard.

---

## 6. INTEGRATION NOTE

Harmony is the orchestration layer; the engines are the instruments. Cross-reference: SOP-ENGINE-00 (the ten engines + the per-engine phase table), SOP-STORY-01 (recurring character + villain→hero), SOP-PITCH-06 (the pitch cadence the narrative-harmony gate proves unbroken), SOP-DESIGN-01 (the visual system continuity), brand-steward-sops.md (palette), director-of-presentations.md (the harmony owner), and SOP-SLIDE-00 §5 (`AF-HARMONY` registration) + §5.5 (the SEND-BACK-THROUGH loop harmony failures route through). The deterministic gates `check_narrative_harmony` (copy), the per-slide harmony dimension of `check_prompt_qc_deterministic` (prompt), and `check_harmony` (deck-level) are built in `build_deck.py` and wired into `PREFLIGHT_REQUIRED` — harmony fires un-bypassably, not by an agent choosing to run a script.
