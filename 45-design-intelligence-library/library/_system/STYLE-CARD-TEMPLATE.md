# STYLE CARD TEMPLATE
**Version:** 1.0 | **Last Updated:** 2026-06-12
**Audience:** AI agents. Copy this entire template for every new style card. Fill EVERY section. The rigid structure is what allows any AI session to execute "use style FB-003" cold — never reorder, rename, or omit sections. Write "N/A — [reason]" only when a section truly does not apply.

---

```markdown
# {ID} — {Style Name}

## CARD HEADER
- **ID:** {e.g., FB-003}
- **Style Name:** {short evocative name, e.g., "Bold Cinematic Gold"}
- **Category:** {e.g., Facebook ad designs}
- **Status:** draft | tested | production
- **Version:** v1.0
- **Created:** {YYYY-MM-DD}
- **Source:** {one-line description of the analyzed image(s) — describe, never embed}
- **One-line style summary:** {≤25 words — this exact line also goes in INDEX.md}
- **Default aspect ratio:** {from category rules}
- **Recommended model + tier:** {e.g., GPT-Image 2, LONG} (per MODEL-SPECS.md routing)

## STYLE DNA (the 12 dimensions)

### 1. Render Style
{primary type, realism 1–10, hybrid notes}

### 2. Composition & Grid
{9-zone map of element placement, compositional system, eye-flow path}
| Zone | Contents |
|---|---|
| upper-left | |
| upper-center | |
| upper-right | |
| middle-left | |
| middle-center | |
| middle-right | |
| lower-left | |
| lower-center | |
| lower-right | |

### 3. Subject Treatment
{size %, crop, angle, lens feel, depth of field, subject-background relationship}

### 4. Color Palette
| Role | Hex (reference) | Descriptive name (use in prompts) |
|---|---|---|
| Dominant | | |
| Secondary | | |
| Accent | | |
| Background | | |
| Text | | |

### 5. Color Grading & Saturation
{saturation level/%, contrast, temperature, shadow/highlight tints, named grade, skin tone handling}

### 6. Lighting
{direction, quality, drama, practical effects, light color}

### 7. Typography Treatment
{hierarchy + ratios, weight/style, case, placement zones, effects, text-to-image ratio, face-clearance strategy}

### 8. Layering & Depth
{back-to-front stack, layer-breaking elements, inter-layer shadows/glows}

### 9. Texture & Finish
{grain, surface, edge quality, print vs screen feel}

### 10. Negative Space & Density
{density 1–10, breathing-room zones, active vs passive space}

### 11. Mood & Energy Keywords
{exactly 5–8 adjectives}

### 12. Hard Rules (ALWAYS / NEVER)
- ALWAYS: ...
- ALWAYS: ...
- ALWAYS: ...
- NEVER: text overlapping any face
- NEVER: ...
{minimum 5 rules; the face rule is mandatory for any style involving people}

## PROMPT TEMPLATES
Variables available: {SUBJECT} {HEADLINE_TEXT} {SUBHEAD_TEXT} {CTA_TEXT} {BRAND_COLOR_1} {BRAND_COLOR_2} {ASPECT_RATIO} {LOGO_NOTE}

### SHORT (≤500 chars — all models) — actual count: {N} chars
```
{one dense paragraph per MASTER-SOP §5.1}
```

### MEDIUM (≤2,800 chars — all models) — actual count: {N} chars
```
{structured paragraphs per MASTER-SOP §5.1}
```

### LONG (≤18,000 chars — GPT-Image 2 / Nano Banana 2 only) — actual count: {N} chars
```
{full spec per MASTER-SOP §5.1, ending with restatement of the 3 most critical instructions}
```

## AVOID-LIST
{single list; rendered as negative_prompt on Ideogram V3, inline "Do not..." sentences elsewhere}
```
text overlapping any face, distorted hands, misspelled text, watermark, ashy or greyed skin tones, blown-out highlights on skin, {style-specific additions}
```

## MODEL NOTES
{Only quirks specific to THIS style. e.g., "Seedream tends to under-saturate the gold — add 'rich saturated metallic gold' twice." General model behavior lives in MODEL-SPECS.md, not here.}

## TEST LOG
| Date | Model | Tier | Test subject | Score /5 | Notes / failure modes / fixes |
|---|---|---|---|---|---|
| | | | | | |

## CHANGELOG
| Date | Version | Change | Why |
|---|---|---|---|
| {YYYY-MM-DD} | v1.0 | Initial analysis | — |
```

---

## FILLING INSTRUCTIONS (for the analyzing AI)

1. Run the full 12-Dimension Protocol from MASTER-SOP.md §4 BEFORE opening this template. Analysis first, transcription second.
2. The Golden Rule applies to every line: HOW, never WHAT. If a content noun from the source image appears anywhere outside the "Source" line, you have failed the separation test.
3. Character counts on prompts must be ACTUAL counts (count them), not estimates. A MEDIUM prompt at 2,950 chars will silently fail on Seedream.
4. The SHORT prompt is not a summary of the MEDIUM prompt — it is the 8–10 highest-leverage style signals only. Choose the details that, if lost, would make the output unrecognizable as this style.
5. The LONG prompt should be 3,000–8,000 chars for most styles. Only text-dense layouts (magazine covers, infographic-style ads) justify going beyond 10,000.
6. Status lifecycle: `draft` (just created) → `tested` (passed TEST-PROTOCOL once) → `production` (passed with score ≥4.0 and registered in INDEX.md).
