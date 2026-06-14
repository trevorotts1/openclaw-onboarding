# SOP-IMG-02 - Design-Intelligence-Library Integration + Seeding (skill 45 <-> Presentations)

**Cluster:** Image-Gen Mechanics + Design-Library (skill 45) Integration
**Status:** Reference SOP - POPULATE + WIRE the existing skill 45; do not rebuild it. The DIU boundary (SOP-DIU-611), the cross-department request block (SOP-DIU-612), and the analysis engine (PPT-ANALYSIS-SOP) already exist; the design-intelligence-library INDEX.md is still the empty seed on every box, so the seeding step and the auto-handoff trigger this SOP defines remain the genuine forward work (a pointer for the Brand Steward + DIU build, not yet wired into those roles).
**Owner roles:** Brand Steward (Presentations side), Deck Systems Specialist + Chief Design Officer (DIU side)
**Master authority extended:** `45-design-intelligence-library/library/_system/PPT-ANALYSIS-SOP.md`; `SOP-DIU-611` (boundary contract); `SOP-DIU-612` (cross-dept request block); `presentations/00-START-HERE.md` boundary mirror (T7b)
**Library-version pin:** PPT-ANALYSIS-SOP v1.1; SOP-DIU-611 v1.0; SOP-DIU-612 v1.0; INDEX.md v2.0

---

## 0. WHY THIS SOP EXISTS (the ground-truth state)

The design-library investigation (design-library-findings.md) found skill 45 - the **Design Intelligence Library / Design Intelligence Unit (DIU)** - is REAL, COMPLETE, and EXECUTABLE, but is **unused**: the library `INDEX.md` is an empty seed (`*(empty - awaiting first analysis)*`) on every box. The PPTX style analysis works deterministically (rasterize -> cluster into 3-8 named families -> Deck Style System file with a Shared Foundation block + per-family SHORT/MEDIUM/LONG prompt templates), and the named-style recall (SOP-DIU-607) is fully specified. The capability exists; nobody has run it.

This SOP does NOT re-author the analysis engine. It does three things:
1. Defines the **seeding step** that fills the empty library by running a reference deck (the gold-standard v2 reference deck, and any client reference deck) through the analyzer. (Closes GAP a.)
2. Defines the **auto-handoff contract** between Presentations and the DIU so the style flows without manual CDO archaeology. (Closes GAP d.)
3. Explains, enforceably, **how the Presentations dept consumes** a style family: PPTX style analysis -> 3-8 named style families -> per-family scaffolding prompts -> Slide Image Creator.

Two sibling SOPs in this cluster close the other gaps: SOP-IMG-03 (the "do you have a style or should I creatively develop one?" conversation branch + GAP b/e the NAMED-STYLES seed) and SOP-IMG-04 (signature-style recall + GAP c the DIU logo-as-I2I mechanics). The Kie call mechanics live in SOP-IMG-01.

This is build doctrine. None of it is ever printed on a slide.

---

## 1. PURPOSE

Wire skill 45 into the Presentations pipeline as the imagery STYLE-INTELLIGENCE layer, and guarantee the library is never empty when a client wants "a deck that looks like THIS." Make "the library is empty" and "no handoff happened" detectable, gateable conditions.

---

## 2. THE BOUNDARY (do not duplicate - read at runtime)

Per SOP-DIU-611 and the 00-START-HERE T7b mirror, the two pipelines stay separate and there are exactly TWO legal crossings:

- **Presentations** owns CLIENT-WEBINAR-DECK-SOP: webinar/funnel decks, the five archetypes (A1-A5), white-base doctrine, the GPT-Image-2-only model manifest, narrative + price-ladder + PPTX assembly.
- **DIU (in Graphics)** owns PPT-ANALYSIS-SOP: visual style analysis, the 3-8-family Deck Style System, the Rotation Engine, the 7-endpoint roster.
- **Crossing A:** the Brand Steward consumes a PPT-category style card's **Foundation Prompt Block** as the STYLE BLOCK input for a webinar deck, requested via SOP-DIU-612. This is the ONLY way DIU style content enters a Presentations deck.
- **Crossing B:** for DIU strategy-(b) decks, the DIU delivers text-clear background imagery to Presentations for editable overlay. (Not the webinar-deck path; out of scope here.)

**Hard rule (unchanged):** Webinar/funnel decks NEVER enter the DIU Rotation Engine, and the DIU's 7-endpoint routing NEVER overrides the GPT-Image-2-only manifest. The DIU supplies STYLE, not generation, for webinar decks. This SOP only adds WHEN and HOW the crossing fires; it changes none of the boundary.

---

## 3. WHEN THE PRESENTATIONS DEPT USES THE DIU (the trigger contract - closes GAP d)

Today the crossing requires manual CDO coordination, so it never happens. This SOP makes it an **automatic, conditioned trigger** the Brand Steward fires at a fixed point in the pipeline.

**The trigger (fires inside Brand Steward SOP 9.1, before the STYLE BLOCK is finalized):**

> IF intake declares a style reference - any of: `STYLE_REFERENCES` (a reference deck / past designs to match), `ANALYZE_REQUEST = true`, `STYLE_ID` (a named saved style), or the client answered the SOP-IMG-03 conversation with "match my existing deck" - THEN the Brand Steward MUST open Crossing A via SOP-DIU-612 to source a PPT-category style and fold its Foundation Prompt Block into the STYLE BLOCK, BEFORE delivering the STYLE BLOCK to the Slide Image Creator.
>
> IF intake declares NO style reference (`NEW_STYLE = true` or no style fields) -> no crossing; the Brand Steward builds the STYLE BLOCK from intake brand fields as today, and (per SOP-IMG-03) offers the "creatively develop one" path.

**The handoff contract (the artifact that makes it automatic):**

1. Brand Steward writes a `style_request.json` to `working/brand/` with the SOP-DIU-612 STYLE block fields: `STYLE_ID@version` OR mood keywords + `ANALYZE_REQUEST` + reference deck path; `tier` (MEDIUM default); `destination_format: webinar-deck-slide`; `likeness_present` (true if a founder portrait will appear); all required Workflow-B variables.
2. Brand Steward submits `style_request.json` to the **Chief Design Officer** (the sole DIU intake per SOP-DIU-612) - NOT to the Generation Operator or Slide Image Creator directly.
3. CDO resolves/analyzes (see §4) and returns the **Foundation Prompt Block + family roster + usage rules** (the card ID@version) to the Brand Steward.
4. Brand Steward folds the Foundation Prompt Block into `style_block.md` (Crossing A) and records `style_card_id@version` in `brand_registry.json`.
5. Slide Image Creator now writes Phase 2 prompts with the analyzed style baked into the STYLE BLOCK. The card governs; the Slide Image Creator never writes style from memory or silently overrides the contracted foundation (SOP-DIU-611 hard rule 3).

This is the auto-handoff: a single conditioned trigger + one request artifact + one return artifact, at a fixed pipeline point. No manual archaeology.

---

## 4. SEEDING THE EMPTY LIBRARY (closes GAP a)

The library must not be empty when the trigger fires. Two seeding paths:

### 4.1 Bootstrap seed - run the gold-standard v2 reference deck through the analyzer (one-time, fleet baseline)

Run ONCE per box during onboarding so every client starts with at least one production-status reference style.

**Source (the verified gold standard, NOT the abstract PNG deck):** the gold-standard reference prompt set (the 75-slide prompt set). (A 29-slide abstract PNG deck is a text-free abstract tech deck and is NOT the gold standard - do not seed from it.)

**Steps (PPT-ANALYSIS-SOP §2, applied; the Deck Systems Specialist runs this):**
1. Rasterize the source to slide images. If a rendered `.pptx`/PDF of the gold-standard deck exists, use `libreoffice --headless --convert-to pdf` then `pdftoppm -png -r 100`. If only the prompt set exists (no rendered deck), the analyzer reads the prompt set's per-slide ONE-BIG-IDEA + archetype + layout descriptions as the evidence (the v2 file IS a structured per-slide spec).
2. Batch-survey in groups of ~10; tag each slide: layout archetype, dominant colors, text density, imagery type.
3. Cluster into 3-8 NAMED families (the gold-standard deck maps cleanly to the documented 5-archetype system: A=Full-bleed photo+headline, B=Photo one side/text opposite, C=Photo-top/data-bottom, D=Type-dominant punch, E=Portrait/selfie). Record which slide numbers belong to each family.
4. Extract the Shared Foundation: Montserrat weight ladder; brand hexes (off-white #FBF7F4, raspberry #C8104E, gold #C9A24B, charcoal #231F20); the gold-gradient/glow/strikethrough price system; logo bottom-right ~9% via I2I; the AVOID list (no black backgrounds).
5. Write the Deck Style System file `PPT-001_gold-standard.md` with the Foundation Prompt Block (800-1,200 chars) + one family card per family (SHORT/MEDIUM/LONG templates).
6. **Register in INDEX.md:** one PPT row + one row per family (PPT-001-A ... PPT-001-E), `Status: production`, version v1.0. The INDEX must no longer read `*(empty)*` for PowerPoint designs.
7. Test per TEST-PROTOCOL: generate one test slide per family with new content; score family fidelity AND cross-family cohesion.

### 4.2 Per-client seed - run the client's OWN reference deck

When a client supplies a reference deck (concern: "analyze a PowerPoint, detect how many distinct image STYLES it uses"), the SOP-DIU-612 request carries `ANALYZE_REQUEST = true` and the deck path. The CDO routes to the Deck Systems Specialist, who runs PPT-ANALYSIS-SOP §2 (identical to 4.1 steps 1-7) on the client's deck, producing `PPT-NNN_{client-style}.md` and registering it. The Foundation Prompt Block of the chosen family is returned to the Brand Steward via Crossing A.

**The "how many styles" output is explicit and evidence-backed:** the analyzer returns "this deck has N families (3-8)," names each, and lists which slide numbers belong to each - never a vague "6-7 styles" estimate. If it detects more than 8, it has over-split and merges families differing only in content.

---

## 5. ENFORCEMENT CHECKS (auto-fail conditions)

| # | Check (trigger) | PASS | AUTO-FAIL |
|---|---|---|---|
| 1 | **Library not empty when style-match is requested.** If the trigger (§3) fired (intake has a style reference), INDEX.md has >=1 production-status PPT card before the STYLE BLOCK is delivered. | A registered card exists | INDEX.md PowerPoint section still reads `*(empty)*` while a style-match deck proceeds |
| 2 | **Crossing A used, not bypassed.** A style-match deck's STYLE BLOCK contains a Foundation Prompt Block sourced from a registered card (recorded `style_card_id@version` in brand_registry.json). | Foundation block sourced via SOP-DIU-612 | Slide Image Creator wrote style from memory / invented a look on a deck that requested a style match (violates SOP-DIU-611 hard rule 3) |
| 3 | **Single intake point.** The style request went to the CDO via SOP-DIU-612, not to the Generation Operator or Slide Image Creator directly. | CDO intake | A direct DIU call bypassing the CDO |
| 4 | **Family count is named + evidenced.** The analysis output names 3-8 families and lists member slide numbers per family. | 3-8 named families with slide map | A vague style estimate, >8 families (over-split), or 0 families |
| 5 | **Webinar deck stayed in the Presentations pipeline.** The deck was NOT routed into the DIU Rotation Engine, and generation used the GPT-Image-2-only manifest. | Presentations pipeline + GPT-Image-2 | Webinar deck routed through the Rotation Engine or a non-manifest model |
| 6 | **Bootstrap seed present (per box).** After onboarding, INDEX.md contains the `PPT-001_gold-standard` production rows. | Seed registered | No seed; library still empty after onboarding |
| 7 | **No-reference path is clean.** If intake declares NO style reference, no crossing fired and the STYLE BLOCK was built from intake brand fields + the SOP-IMG-03 creative-develop path. | No spurious crossing | A crossing fired with no style reference (wasted DIU spend) |

---

## 6. ESCALATION / REPAIR PATH

| Condition | First action | If unresolved |
|---|---|---|
| Trigger fired but INDEX.md empty (check 1) | CDO schedules a New-Client Calibration Run (SOP-DIU-613) to analyze the client's reference deck, OR seeds from the gold-standard bootstrap (§4.1) if the client has no reference. Do NOT proceed to prompts with an invented style on a style-match deck. | Director of Presentations + CDO |
| Client supplied a reference deck the analyzer calls "inconsistent junk / no coherent system" | Per PPT-ANALYSIS-SOP §5: analyze only the strongest 10-15 slides and build the system from those; tell the operator. | CDO |
| `style_request.json` missing required Workflow-B variables | CDO returns it to the Brand Steward with an itemized list (SOP-DIU-612 §A). Brand Steward fills, never guesses. | Director |
| Slide Image Creator overrode the contracted foundation (check 2) | QC fails the prompt; re-author with the Foundation Prompt Block. | Director; CDO if disputed |
| Webinar deck got routed to the Rotation Engine (check 5) | Halt generation immediately (SOP-DIU-611 hard rule 1); re-route to the Presentations pipeline. | CDO is final arbiter |

---

## 7. PASS vs FAIL EXAMPLES

**FAIL (the current default state):** A client says "build my webinar deck to look like the deck my designer made last year" and attaches it. The deck was built anyway with an invented look because INDEX.md was empty and no one ran the analyzer. Fails checks 1 and 2.

**PASS:** Same request. Brand Steward detects `STYLE_REFERENCES` + `ANALYZE_REQUEST`, writes `style_request.json`, submits to CDO. Deck Systems Specialist runs PPT-ANALYSIS-SOP on the client's deck -> "4 families: A Title/Hero [1], B Section [2,9,17], C Content [3-8,10-16], D Quote [18]" -> writes `PPT-002_client-style.md`, registers it production. CDO returns the Foundation Prompt Block; Brand Steward folds it into the STYLE BLOCK. Slide Image Creator writes Phase 2 prompts with the real analyzed style. Passes checks 1-5.

**PASS (no reference):** A client has no reference deck and answers "creatively develop one for me" (SOP-IMG-03). No crossing fires; the STYLE BLOCK is built from intake brand fields and the creative-develop branch. Passes check 7.

**FAIL:** Onboarding completed but no one ran the bootstrap seed, so the first style-match client hit an empty library. Fails check 6.

---

*End of SOP-IMG-02. This SOP populates and wires the existing skill 45; it re-authors none of the analysis engine. The boundary contract (SOP-DIU-611) is unchanged - this SOP only fixes WHEN the legal crossing fires and ensures the library is seeded.*
