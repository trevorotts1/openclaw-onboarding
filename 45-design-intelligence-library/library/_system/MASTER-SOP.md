# MASTER SOP — Design Style Analysis & Prompt Generation System
**Version:** 1.1 | **Last Updated:** 2026-06-12 | **Owner:** {{COMPANY_NAME}}
**Audience:** AI agents (Claude, OpenClaw, or any LLM operator). This document is the brain of the Design Library. Read it fully before performing any style analysis or style-based generation.

---

## 1. PURPOSE

This system teaches an AI agent to:
1. **Analyze** any image (or batch of images / slide deck) across 12 style dimensions.
2. **Extract the STYLE** — the transferable aesthetic DNA — while discarding the CONTENT.
3. **Write a Style Card** — a permanent, reusable file that any future AI session can read cold and execute.
4. **Generate prompts** in three tiers (Short / Medium / Long) calibrated to real API character limits.
5. **Maintain the library** — register every style in INDEX.md, version every change, log every test.

The end state: a human can say *"Make me a Facebook ad using style FB-003 with [new subject and headline]"* and the AI produces an on-style image with zero re-analysis.

---

## 2. LIBRARY MAP

```
/master-files/
└── design-library/
    ├── INDEX.md                      ← Master lookup table. ALWAYS check here first.
    ├── _system/
    │   ├── MASTER-SOP.md             ← This file. The analysis brain.
    │   ├── MODEL-SPECS.md            ← API limits, model routing, ready-to-send JSON templates.
    │   ├── STYLE-CARD-TEMPLATE.md    ← The rigid schema every style card must follow.
    │   ├── PPT-ANALYSIS-SOP.md       ← Batch / deck analysis + Style Rotation Engine for deck generation.
    │   ├── NEGATIVE-PROMPTING-SOP.md ← The avoid-list system: 3 layers, per-model delivery.
    │   ├── PHOTO-SHOOT-SOP.md        ← Personal Photo Shoot Mode: identity-locked client imagery.
    │   └── TEST-PROTOCOL.md          ← Fidelity testing & card-patching protocol.
    ├── single image designs/         ← ID prefix: SI-
    ├── facebook ad designs/          ← ID prefix: FB-
    ├── book cover designs/           ← ID prefix: BC-
    ├── magazine cover designs/       ← ID prefix: MAG-
    ├── social media designs/         ← ID prefix: SM-
    ├── banner designs/               ← ID prefix: BN-
    ├── advertisement designs/        ← ID prefix: AD-
    ├── powerpoint designs/           ← ID prefix: PPT- (deck) + letter suffix (family, e.g. PPT-001-A)
    └── personal photo shoot/         ← ID prefix: PS- (shoot cards) + per-client identity folders
```

Every category folder contains:
- `_RULES.md` — non-negotiable constraints for that category (aspect ratios, safe zones, model routing).
- Style card files named: `{ID}_{kebab-case-style-name}.md` → e.g. `FB-001_bold-cinematic-gold.md`

---

## 3. THE GOLDEN RULE — STYLE ≠ CONTENT

**A style card describes HOW an image looks, never WHAT it depicts.**

The purpose of analysis is to capture an aesthetic that transfers to brand-new subjects. If the source image shows a woman in a red blazer holding a book, the style card must work equally well for a man at a podium, a product bottle, or a city skyline.

### 3.1 The separation test
For every line you write in a style card, ask: *"Would this line still make sense if the subject were completely different?"*
- ✅ KEEP: "Subject occupies the right third, cropped at mid-torso, shot from slightly below eye level"
- ❌ STRIP: "A woman in a red blazer holding a book" → becomes `{SUBJECT}` + treatment notes
- ✅ KEEP: "Headline in heavy condensed sans-serif, all caps, locked to upper-left zone"
- ❌ STRIP: "The headline says SPEAK WITH POWER" → becomes `{HEADLINE_TEXT}`

### 3.2 The variable system
All content slots use these standard variables. Every prompt template in every style card MUST use these exact tokens:

| Variable | Meaning |
|---|---|
| `{SUBJECT}` | The main subject — person, product, object, scene. Includes a one-line description supplied at generation time. |
| `{HEADLINE_TEXT}` | Primary text, verbatim, in quotes. |
| `{SUBHEAD_TEXT}` | Secondary text, verbatim. |
| `{CTA_TEXT}` | Button / call-to-action text, verbatim. |
| `{BRAND_COLOR_1}` / `{BRAND_COLOR_2}` | Override colors when adapting a style to a specific brand. If not supplied, use the card's native palette. |
| `{ASPECT_RATIO}` | Supplied at generation time; must be one supported by the target model (see MODEL-SPECS.md). |
| `{LOGO_NOTE}` | Optional logo placement instruction. |

At generation time, the operator (human or AI) fills the variables. Anything not filled gets the card's default.

---

## 4. THE 12-DIMENSION ANALYSIS PROTOCOL

Analyze EVERY image across all 12 dimensions, in this exact order. Order matters: Dimension 1 sets the vocabulary for everything after it.

### Dimension 1 — Render Style
What kind of image is this? Choose primary + modifiers:
`photograph` | `cinematic photograph` | `3D render` | `flat illustration` | `editorial illustration` | `collage / mixed media` | `painterly` | `vector / graphic design` | `photo-composite (photo + graphic elements)`
Record: primary type, realism level (1–10), any hybrid characteristics ("photo subject on graphic background").

### Dimension 2 — Composition & Grid (the 9-zone map)
Divide the frame into a 3×3 grid. Zones are named:
```
upper-left    | upper-center  | upper-right
middle-left   | middle-center | middle-right
lower-left    | lower-center  | lower-right
```
Record:
- Which zone(s) hold the focal point
- Which zones hold text, which hold the subject, which are breathing room
- Compositional system in use: rule of thirds / center-dominant / golden ratio / diagonal / symmetrical / Z-pattern / F-pattern
- Eye-flow path: where does the eye enter, travel, and land? (e.g., "enters at face upper-right → travels down diagonal to headline lower-left → exits at CTA")
- Horizon/baseline position if applicable

### Dimension 3 — Subject Treatment
- Size: what % of frame height/width does the subject occupy?
- Crop: full body / three-quarter / mid-torso / bust / face only / product full / product detail
- Camera angle: eye level / low angle (heroic) / high angle / dutch tilt / overhead
- Lens feel: wide (environmental) / standard / telephoto compression / macro
- Depth of field: razor-thin / shallow / moderate / deep (everything sharp)
- Subject-to-background relationship: cut-out / integrated / silhouetted / overlapping graphic elements

### Dimension 4 — Color Palette
Extract 5–7 dominant colors. Record BOTH formats (per system rule: hex for reference, descriptive for prompts):

| Role | Hex | Descriptive name (use THIS in prompts) |
|---|---|---|
| Dominant | #0E1B2C | deep midnight navy |
| Secondary | #D4A437 | rich metallic gold |
| Accent | #E8453C | vivid coral red |
| Background | ... | ... |
| Text | ... | ... |

Why both: hex codes are precise for human reference and HTML/design work, but image models respond more reliably to vivid descriptive color language. Prompts use the descriptive column; the hex column is the source of truth for verification.

### Dimension 5 — Color Grading & Saturation
- Overall saturation: muted (-) / natural (0) / pushed (+) / hyper-saturated (++) — estimate as a % shift from natural
- Contrast: low / medium / high / crushed blacks
- Temperature: cool / neutral / warm / split (e.g., "teal shadows, amber highlights")
- Shadow tint and highlight tint (the grade): e.g., "teal-orange cinematic grade", "matte faded blacks", "high-key clean commercial"
- Skin tone handling (critical): how are deep skin tones lit and graded? Record luminosity, warmth, highlight behavior. Deep skin tones must remain rich and dimensional — never ashy, never blown out.

### Dimension 6 — Lighting
- Direction: front / side (which side) / back / rim / under / top
- Quality: hard (crisp shadows) / soft (wrapped) / mixed
- Drama level: flat commercial / moderate / dramatic chiaroscuro
- Practical effects: lens flare, glow, light leaks, neon spill, god rays
- Light color: matches grade or contrasts it?

### Dimension 7 — Typography Treatment (skip if no text)
- Hierarchy: how many text levels? Relative size ratios (e.g., headline 5× subhead)
- Weight & style: heavy condensed sans / elegant serif / script accent / mixed
- Case: all caps / title case / sentence case / mixed
- Placement zones (use the 9-zone names from Dimension 2)
- Effects: drop shadow, outline, gradient fill, knockout, behind-subject layering, highlight bars
- Text-to-image ratio: what % of the frame is typography?
- **HARD RULE CHECK: text must NEVER overlap faces.** Record how this image keeps text clear of the subject's face.

### Dimension 8 — Layering & Depth
Describe the stack from back to front:
- Background layer (what is it: gradient / texture / environment / solid)
- Mid layer(s): subject, secondary objects
- Foreground/overlay layer: graphic shapes, gradients, vignettes, particles, light effects, texture overlays
- Does any element break layers (e.g., subject's shoulder overlapping a text block = depth illusion)?
- Drop shadows / glows between layers?

### Dimension 9 — Texture & Finish
- Grain: clean digital / subtle film grain / heavy grain
- Surface: glossy / matte / paper texture / fabric / metallic
- Edge quality: sharp vectors / soft photographic / rough collage edges
- Print feel vs. screen feel

### Dimension 10 — Negative Space & Density
- Density rating 1–10 (1 = minimal/airy, 10 = maximalist/packed)
- Where is the breathing room (zone names)?
- Is negative space active (shaped, colored) or passive (plain)?

### Dimension 11 — Mood & Energy Keywords
Exactly 5–8 adjectives that capture the emotional register. These words go directly into prompts.
Examples: "authoritative, aspirational, cinematic, bold, premium" or "warm, feminine, inviting, soft, encouraging."

### Dimension 12 — Extracted Hard Rules
The ALWAYS / NEVER list this style obeys. Minimum 5 rules. Examples:
- ALWAYS: gold accent appears in exactly one zone, never more
- ALWAYS: subject lit from camera-left with warm key
- NEVER: text over the subject's face
- NEVER: more than 3 colors in the typography
- NEVER: pure white background (always graded off-white minimum)

---

## 5. PROMPT TIER CONSTRUCTION

Every style card carries three prompt templates. Tiers are calibrated to verified Kie.ai API limits (full specs in MODEL-SPECS.md).

| Tier | Character budget | Compatible models | Use case |
|---|---|---|---|
| **SHORT** | ≤ 500 chars | ALL models | Fast drafts, volume runs, quick iterations |
| **MEDIUM** | ≤ 2,800 chars | ALL models (fits Seedream 4.5's 3,000 ceiling with headroom; safe for Ideogram/Wan 5,000) | **Default production tier** |
| **LONG** | ≤ 19,000 chars | GPT-Image 2 + Nano Banana 2 ONLY (20,000 ceilings) | Full style spec: complex layouts, text-heavy designs, maximum fidelity |

### 5.1 Required structure for each tier

**SHORT** — one dense paragraph:
`[render style] of {SUBJECT}, [composition in one phrase], [3 palette colors descriptive], [grade in one phrase], [lighting in one phrase], "{HEADLINE_TEXT}" in [type treatment, placement zone], [2-3 mood keywords]`

**MEDIUM** — structured paragraphs in this order:
1. Render style + subject treatment (crop, angle, size, zone placement)
2. Composition: zone-by-zone layout of all elements
3. Color: full descriptive palette + grading + saturation
4. Lighting
5. Typography: every text element, verbatim in quotes, with placement, weight, effects
6. Layering & depth + texture
7. Mood keywords + the style's top 3 hard rules written as instructions
8. Avoid-list (see 5.2)

**LONG** — everything in MEDIUM, expanded with:
- Explicit 9-zone map: one line per zone stating exactly what occupies it
- Eye-flow narrative
- Per-element specifications (each text block, each graphic shape, each overlay described individually)
- Skin tone / subject finish directives
- Full hard-rules block
- Extended avoid-list
- Redundant restatement of the 3 most critical instructions at the END of the prompt (models weight prompt endings heavily; repetition enforces compliance)

### 5.2 The Avoid-List (negative prompting)
Negative prompting is a full subsystem — see **NEGATIVE-PROMPTING-SOP.md** for the complete protocol. Summary: three layers (universal baseline + category baseline + style-specific) merge at generation time; Ideogram V3 receives the merged list in its true `negative_prompt` field; every other endpoint gets the 10 strongest items converted to "Do not..." sentences in the final paragraph, with critical negatives paired to positive twins stated earlier in the prompt.

### 5.3 Writing quality bar
- Use vivid, specific, descriptive color names — never hex codes inside prompts.
- Quote ALL verbatim text in double quotes and state: "render this text exactly, correctly spelled."
- State placements using the 9-zone vocabulary.
- Never write "high quality, 4K, masterpiece" filler — resolution is an API parameter, not a prompt word. Spend characters on style information instead.

---

## 6. WORKFLOW A — ANALYZE A NEW IMAGE → CREATE A STYLE CARD

1. **Identify category** → determines folder + ID prefix. Read that category's `_RULES.md` first.
2. **Run the 12-Dimension Protocol** (Section 4) on the image. Be exhaustive — over-describe rather than under-describe.
3. **Apply the Golden Rule** — strip all content, install variables.
4. **Open `STYLE-CARD-TEMPLATE.md`** and fill EVERY section. No section may be left empty; write "N/A — [reason]" if truly inapplicable.
5. **Write the three prompt tiers** per Section 5. Verify character counts with an actual count, not an estimate.
6. **Assign the ID**: next available number in that category (check INDEX.md). Name the file `{ID}_{kebab-style-name}.md`.
7. **Register in INDEX.md**: add the row (ID, name, category, one-line description, source description, date, version, file path).
8. **Run TEST-PROTOCOL.md** before marking the card `status: production`. Until tested, card status is `draft`.

## 7. WORKFLOW B — GENERATE FROM AN EXISTING STYLE

When instructed e.g. *"Create an image using style FB-003 with subject X and headline Y"*:
1. **Look up FB-003 in INDEX.md** → open the card file.
2. **Read the card fully**, including hard rules and the test log (the test log contains known failure modes and fixes).
3. **Read the category `_RULES.md`** for aspect ratio and platform constraints.
4. **Choose the tier**: default MEDIUM unless the operator specifies, the design is text-heavy (→ LONG on GPT-Image 2 / Nano Banana 2), or it's a draft run (→ SHORT).
5. **Choose the model** using the routing table in MODEL-SPECS.md (category rules may override).
6. **Fill the variables** into the template. Do not improvise style changes — the card is law. If the operator requests a deviation, apply it and note it in your response, but do NOT edit the card unless told to.
7. **Assemble the API request** using the JSON templates in MODEL-SPECS.md.
8. **After generation**: if output is off-style, consult the card's test log, patch the prompt per TEST-PROTOCOL.md guidance, and log the finding.

## 8. VERSIONING RULES

- Cards use semantic-ish versioning: `v1.0` initial → `v1.1` prompt patch → `v2.0` re-analysis.
- NEVER delete failure notes from a test log; they prevent repeat failures.
- Every edit to a card appends a line to that card's Changelog section: date, version, what changed, why.
- If a model is deprecated or a new model is added, update MODEL-SPECS.md ONLY — style cards stay model-agnostic and never need rewriting. This is the future-proofing layer.

## 9. BRAND DEFAULT ({{COMPANY_NAME}})

Unless the source image dictates otherwise or the operator overrides, library-wide aesthetic defaults are guided by your brand. Resolve brand defaults from:
- The box's `company-config.json` brand block (colors, style voice, visual energy)
- Branding interview answers (visual identity, target perception, market positioning)

**Hard rule (universal, not brand-specific):** deep skin tones rendered rich, warm, and dimensional - this is non-negotiable in every card involving people. This is a RENDER-QUALITY rule for whoever is cast, not a casting rule.

**REPRESENTATION_MIX OVERRIDE (mandatory, highest priority):** Per-client representation governs and OVERRIDES the universal skin-tone default when they conflict. If a client's captured REPRESENTATION_MIX specifies a particular audience composition, casting must reflect that composition. The skin-tone quality rule applies to whoever is cast per that mix; it does not impose or override the client's specified audience. Deep-skin quality = how you render the person; REPRESENTATION_MIX = who is cast. Never conflate the two. A card that ignores a client's REPRESENTATION_MIX in favor of the universal skin-tone default fails the representation gate.

These defaults inform analysis emphasis but NEVER override what the source image actually shows. Analyze what IS, not what should be.

---

## 10. SPECIAL MODES (pointers)

- **Deck generation with style rotation** — generating multiple slides from a PPT style is governed by the Style Rotation Engine: PPT-ANALYSIS-SOP.md §3B. Slide Manifest first, always 16:9, resolution per the client's choice.
- **Personal Photo Shoot Mode** — any request involving a real client's likeness (new scenes, wardrobe changes, poses, slide placement, stylized/cartoon versions, retouching) is governed by PHOTO-SHOOT-SOP.md. The Identity Lock Block is mandatory; skin-tone preservation is a hard rule; Seedream 4.5 Edit is the surgical-editing tool.
- **Negative prompting** — NEGATIVE-PROMPTING-SOP.md governs all avoid-list assembly and delivery.
