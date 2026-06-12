# CATEGORY RULES — PowerPoint Designs (PPT-)
**Read before any PPT- analysis or generation. Deck analysis follows _system/PPT-ANALYSIS-SOP.md — this file holds the generation-side constraints.**

## Formats & aspect ratios
- **ALWAYS 16:9.** This is the standard. The single exception: the operator explicitly states the client uses a legacy 4:3 deck.

## Resolution decision (per deck, client's choice governs)
Record the resolution in the Slide Manifest. If unspecified, producer asks the client; default 2K.
| Need | Resolution | Endpoints |
|---|---|---|
| Drafts / contact sheets | 1K | GPT-Image 2, Nano Banana 2, Wan 2.7 |
| Standard screen deck (DEFAULT) | 2K | All (Seedream `basic`) |
| Projection / print / premium | 4K | GPT-Image 2, Nano Banana 2, Seedream `high` — NOT Wan 2.7 |

## Hard rules
- **Multi-slide generation MUST run the Style Rotation Engine** (PPT-ANALYSIS-SOP §3B): build the Slide Manifest first, assign families per Usage Rules, honor rhythm constraints, rotate flex variables so same-family slides differ. Never generate a deck slide-by-slide ad hoc.
- Placing the client IN a slide → combine the family prompt with the Identity Lock Block (PHOTO-SHOOT-SOP Mode E).
- Every generation names its family explicitly: "use PPT-002 Family C" — never "use PPT-002" alone for a single slide. If the operator doesn't specify, ask or infer from the slide's purpose via the deck's Usage Rules.
- Text strategy decision per generation: (a) AI renders the text in-image (use exact-text quoting, GPT-Image 2 / Nano Banana 2), or (b) generate the background/imagery only and text is added in PowerPoint later (PREFERRED for editable client decks — the producer can revise text without regenerating). Record the chosen strategy.
- Strategy (b) prompts must state: "leave the {ZONE} area clear and visually quiet for text overlay" — clear zones per the family's grid.
- Cross-slide cohesion beats single-slide beauty: every slide prompt includes the deck's Foundation Block (see PPT-ANALYSIS-SOP §2 Step 6).
- Respect the deck's rhythm rules when generating multiple slides.
- Client document standards recorded in the workspace's brand notes apply — confirm the audience and brand guidelines before choosing a deck style.

## Model routing
- Slide backgrounds/imagery (strategy b): Nano Banana 2 or GPT-Image 2.
- Full slides with rendered text (strategy a): GPT-Image 2 LONG.
- Variant exploration for one slide: Wan 2.7 n=4.
