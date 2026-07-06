# CATEGORY RULES — Funnel / Landing / Website Page Designs (FN-)
**The web-page category: imagery that lives inside a rendered funnel, landing page, or website page — hero sections, section illustrations, proof/benefit portraits, letter portraits, and typography-as-art canvases. These cards govern the *look* of the images the Skill 6 GHL delivery rail generates and the Skill 49 (Signature Funnel) / Skill 56 (Sales Page Assets) engines request.**

## What consumes an FN- card
- **Skill 6 GHL rail** — an optional `style_card_id` on a `page_spec`. When set, `ghl_image_stage._derive_copy_specs` resolves the card via DIU Workflow B and embeds its LONG tier as the Brand-Style block (block 8) of every derived section prompt. Unset = brand-color-only Signature look (unchanged default).
- **Skill 49 / Skill 56** — an optional `style_card_id` on the intake; the engine's image-prompt template (PROMPT 7 / the baked image prompt) carries the resolved LONG tier into block 8. Purely additive — an intake without a `style_card_id` behaves exactly as before.

## Formats & aspect ratios
- Web pages mix ratios by section. The default per-page hero and body sections are **16:9 / 2K**; letter-portrait / regal sections are **3:4**; typography-as-art canvases follow the page's section recipe. The card records its native ratio; the **per-entry `aspect_ratio` on the prompt/prompts.json** is authoritative at generation time (FIX-IMG-03) — never bake the ratio into prompt text.
- When re-ratioing a section (e.g. a 16:9 hero card reused for a 3:4 letter portrait), re-map the 9-zone layout explicitly in the prompt: state where subject and negative space move; do not let the model guess.

## Hard rules
- NEVER text over faces (when text is present). Reserve clean negative space for overlaid web copy — a web hero must leave room for the headline/subhead/CTA that render as page copy, not in the image.
- Non-text sections must state "No text, no letters, no words anywhere in the image." Only typography-as-art sections carry spelling-locked words (in quotes, letter-for-letter).
- Skin-tone hard rule applies to all people imagery: rich, warm, dimensional deep skin tones — never ashy, grey, or flattened. Honor the page's declared representation EXACTLY; never assume a default.
- The LONG tier is the tier of record for FN- cards (web heroes are detail-dense and text-heavy) — author it to the STYLE-CARD-TEMPLATE `### LONG` section so `ghl_image_stage._diu_extract_long_tier` can lift it. A card with no LONG tier is rejected fail-loud when referenced.

## Model routing
- Follow MODEL-SPECS routing by task. The LONG tier targets **GPT-Image 2 / Nano Banana 2** (20,000-char ceilings), matching the Skill 6 rail's `gpt-image-2` generator. No category override beyond the ratio rules above.
