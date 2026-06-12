# PPT ANALYSIS SOP — Slide Decks, PDFs & Image Batches
**Version:** 1.1 | **Last Updated:** 2026-06-12
**Audience:** AI agents. Use this protocol whenever the input is a PowerPoint (.pptx), a multi-page PDF, or any batch of 4+ related images. Single images use MASTER-SOP.md Workflow A directly.

---

## 1. CORE CONCEPT: A DECK IS A STYLE SYSTEM, NOT A STYLE

A 100-slide deck is never one style. It is a **family system**: typically 3–8 distinct slide styles (families) sharing one visual foundation. The output of deck analysis is therefore NOT one style card — it is one **Deck Style System file** containing:
1. A **Shared Foundation** (the DNA every family inherits)
2. One **Family Card** per detected style family
3. **Usage Rules** (which family is used for what, and in what rhythm)

ID scheme: deck = `PPT-002`, families = `PPT-002-A`, `PPT-002-B`, ... File name: `PPT-002_{deck-style-name}.md` — ONE file per deck, families live inside it.

---

## 2. STEP-BY-STEP PROTOCOL

### Step 1 — Rasterize
Convert every slide/page to an image before analysis.
- **.pptx** → convert to PDF first, then PDF pages to PNG:
  ```bash
  libreoffice --headless --convert-to pdf deck.pptx
  pdftoppm -png -r 100 deck.pdf slide   # produces slide-01.png, slide-02.png, ...
  ```
- **PDF** → `pdftoppm -png -r 100 deck.pdf slide`
- 100 DPI is sufficient for style analysis; use 150+ only if fine typography needs inspection.

### Step 2 — Batch survey (first pass: clustering, not analysis)
Review slides in batches of ~10. For each slide record ONLY:
`slide # | layout archetype | dominant colors | text density (low/med/high) | imagery type (photo/icon/chart/none)`

Common layout archetypes to tag:
`title/hero` | `section divider` | `content: text-only` | `content: text+image split` | `quote/callout` | `data/chart` | `photo-full-bleed` | `agenda/list` | `closing/CTA` | `team/headshot grid`

### Step 3 — Cluster into families
Group slides whose archetype + treatment match. Rules:
- Target **3–8 families**. If you detect more than 8, you are over-splitting — merge families that differ only in content, not style.
- A family needs ≥2 member slides, OR be a structurally critical singleton (e.g., the one title slide is always Family A).
- Name each family by function: A = Title/Hero, B = Section Divider, C = Standard Content, D = Quote, E = Data, etc.
- Record which slide numbers belong to each family (evidence trail).

### Step 4 — Extract the Shared Foundation
Analyze what ALL families have in common — this is the deck's unifying DNA:
- Master palette (hex + descriptive, per MASTER-SOP Dimension 4)
- Typography system: heading font character, body font character, the size hierarchy
- Grid & margins: consistent safe areas, alignment system
- Recurring motifs: shapes, lines, icon style, photo treatment, background system
- Grade: the consistent color treatment across all imagery
- Logo/footer/page-number conventions

### Step 5 — Run the 12-Dimension Protocol per family
For each family, run MASTER-SOP §4 on 2–3 representative slides. Record only what DIFFERS from or SPECIALIZES the Shared Foundation. Family cards are deltas, not full repeats — this keeps the file readable and prevents drift.

### Step 6 — Write the prompt templates
- The **Shared Foundation gets its own MEDIUM-length "foundation block"** (~800–1,200 chars) describing the universal style.
- Each **family gets a SHORT and MEDIUM template** that BEGINS by including the foundation block, then adds family-specific instructions.
- LONG templates: only for families that will be generated standalone as hero images (usually Family A).
- Slide generation variables (in addition to the standard set): `{SLIDE_TITLE}` `{SLIDE_BODY}` `{SLIDE_NUMBER}` `{CHART_DESCRIPTION}` `{IMAGE_SUBJECT}`

### Step 7 — Write the Usage Rules
The intelligence layer that makes a generated deck feel designed, not templated:
- Family-to-purpose mapping ("Family D for any quote or testimonial")
- Rhythm rules ("never more than 3 consecutive Family C slides; insert a B or D to break monotony")
- Proportions observed in the source ("source deck: ~60% C, 15% B, 10% D, 10% E, 5% A")
- Transition logic ("every section opens with B and the first C after a B uses the image-right variant")

### Step 8 — Register & test
- One INDEX.md row for the deck + one row per family (families indented/referenced to the parent).
- TEST-PROTOCOL: generate one test slide per family with new content; score family fidelity AND cross-family cohesion (do the test slides look like siblings?).

---

## 3. DECK STYLE SYSTEM FILE SCHEMA

```markdown
# PPT-{NNN} — {Deck Style Name}

## DECK HEADER
- ID / Status / Version / Created / Source description / One-line summary
- Slide count analyzed: {N} | Families detected: {N}
- Family roster: A = {name}, B = {name}, ...
- Slide-to-family map: A: [1] | B: [2,14,28] | C: [3-13,15-27] | ...

## SHARED FOUNDATION
{palette table, typography system, grid, motifs, grade — per Step 4}

### Foundation Prompt Block (include at the start of every family prompt)
```
{800–1,200 chars}
```

## FAMILY A — {name}
- Purpose: ...
- Delta from foundation (12-dimension highlights): ...
- Hard rules: ...
- SHORT template / MEDIUM template (each = foundation block + family delta)

## FAMILY B — {name}
{same schema}

{...remaining families...}

## USAGE RULES
{mapping, rhythm, proportions, transitions — per Step 7}

## AVOID-LIST (deck-wide)
## TEST LOG
## CHANGELOG
```

---

## 3B. THE STYLE ROTATION ENGINE (deck GENERATION side)

This is the intelligence that prevents a generated deck from looking stamped. When the operator says *"build a {N}-slide deck using PPT-008"* (or generates any multi-slide set), follow this algorithm EXACTLY:

### Step 1 — Build the Slide Manifest FIRST (no generation before the manifest exists)
A table assigning every slide before any image is generated:

| Slide # | Purpose | Assigned Family | Flex variation | Resolution |
|---|---|---|---|---|
| 1 | Title | PPT-008-A | — | 2K |
| 2 | Section open | PPT-008-B | accent: gold rule | 2K |
| 3 | Content | PPT-008-C | image side: RIGHT, bg hue: deep teal | 2K |
| 4 | Content | PPT-008-C | image side: LEFT, bg hue: navy | 2K |
| 5 | Quote | PPT-008-D | — | 2K |
| ... | | | | |

For decks over 10 slides, show the manifest to the operator/producer for approval BEFORE generating.

### Step 2 — Family assignment rules (in priority order)
1. **Purpose mapping** — assign each slide's family from the deck's Usage Rules ("Family D for quotes").
2. **Proportions** — keep the overall family mix near the source deck's observed proportions.
3. **Rhythm constraint** — never more than 3 consecutive slides from the same family (or the deck's own stated limit); when content forces a 4th, break it with the deck's designated "breaker" family (usually B or D) or switch to that family's alternate flex state.
4. **Bookends** — slide 1 is always Family A (title); final slide uses the closing/CTA family if one exists.

### Step 3 — Within-family flex rotation
Same-family slides must still differ. Every Family Card defines 2–3 **flex variables** (identified during analysis): typically image side (left/right), background hue (within the family's recorded range), and accent element. Rotate them deterministically: slide's position-within-family (1st, 2nd, 3rd C-slide...) cycles through the flex states in order. Deterministic rotation means the same deck request always yields the same manifest — reproducible, debuggable.

### Step 4 — Prompt assembly per slide
Each slide's prompt = Deck Foundation Block + Family delta + this slide's flex values stated explicitly + slide content variables ({SLIDE_TITLE} etc.) + Identity Lock Block if the client appears (see PHOTO-SHOOT-SOP Mode E) + merged avoid-list (NEGATIVE-PROMPTING-SOP).

### Step 5 — Cohesion check
After generating, view the set as a whole: same palette? same grade? same type system? Sibling test — would a stranger sort these into one deck? Fix outliers before delivery.

## 3C. FORMAT & RESOLUTION (deck generation)

- **Aspect ratio: ALWAYS 16:9** for PowerPoint generation. No exceptions unless the operator explicitly states a legacy 4:3 deck.
- **Resolution is a per-deck decision, recorded in the manifest, and the CLIENT'S CHOICE governs.** If unspecified, the producer asks the client; absent an answer, default 2K.

| Need | Resolution | Endpoints that can deliver it |
|---|---|---|
| Internal drafts / contact sheets | 1K | GPT-Image 2, Nano Banana 2, Wan 2.7 |
| Standard screen-share deck (default) | 2K | All (Seedream `basic` = 2K) |
| Projection, print handouts, zoom-heavy, premium client decks | 4K | GPT-Image 2, Nano Banana 2, Seedream `high` — **NOT Wan 2.7 (2K max)** |

If the chosen resolution isn't available on the routed endpoint, re-route per MODEL-SPECS rather than silently downgrading — and tell the operator.


---

## 4. BATCH ANALYSIS OF NON-DECK IMAGE SETS

For a batch of related standalone images (e.g., 20 Facebook ads from one campaign):
1. Run Steps 2–3 to check: one style or several?
2. **One consistent style** → produce ONE standard style card (MASTER-SOP Workflow A), noting "analyzed from {N} images" in Source. Multi-image evidence makes a STRONGER card — record the consistent rules and the observed variation range ("background hue varies teal→navy across the set; treat as flexible").
3. **Multiple styles** → produce one card per style, cross-referenced in each card's Model Notes ("sibling styles: FB-004, FB-005 — same campaign"). Assign each source image to exactly one card and record the assignment in each card's Source line ("images 1,4,7 of the batch"). If the styles share a visual foundation (same palette/type but different layouts), note the shared foundation in each card AND consider whether the set is really a style SYSTEM — if the operator will generate coordinated sets from it, build it as a Deck-style system file instead (one file, families, usage rules), even though it isn't a literal deck. The deck schema works for any coordinated multi-style system.
4. **When the batch resolves to multiple styles, report back**: how many styles found, the evidence (which images formed each cluster), and your recommendation (separate cards vs. one system file) — let the operator confirm before writing files.

## 5. PRACTICAL LIMITS

- Decks over ~40 slides: process in passes of 20; complete Step 2 tags for ALL slides before clustering (clustering on partial evidence produces bad families).
- If slides are visually inconsistent junk (no coherent system), say so. Recommend analyzing only the strongest 10–15 slides and building the system from those. Garbage in, garbage card.
- Animated/video slides: analyze the static visual only; note "motion present, not captured" in the header.
