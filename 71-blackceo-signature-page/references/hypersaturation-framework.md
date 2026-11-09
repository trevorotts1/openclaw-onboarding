# Hypersaturation framework: the page color system and the image grade

Owner order (Trevor Otts, 2026-10-19): "we use hyper saturation in our images - the blacks are
blacker, the reds are redder, the whites are whiter." GPT Image 2.5 through KIE rarely produces that
vibrancy unprompted, so it is prompted, on every mockup and every image, built in, and **always in
the client's own brand colors**. This file is the rules and their evidence. The wording that reaches
the model lives in one place, `scripts/hypersaturation.py`; the pixel check is
`scripts/validate_page_color.py`; its thresholds and their derivation are
`references/page-color-thresholds.json`.

## What the references teach

The two owner-supplied Go Full Page captures of the BlackCEO 6-Figure Launch Challenge registration
page (VA and VB, 14 PDF pages each, hosted as links in `assets/page-references/`) are hypersaturated at
**page level**, not only inside photos. Measured on the stitched pages (`validate_page_color.py`,
600 px wide working copy):

| Measure | VA | VB |
|---|---|---|
| Mean saturation | 0.409 | 0.361 |
| Saturated pixels (S > 0.5, V > 0.3) | 30.1% | 28.3% |
| Near-black (V < 0.20; the analysis' stricter V < 0.12 reads 18.9% / 13.0%) | 26.3% | 18.8% |
| Near-white (V > 0.93, S < 0.10) | 27.7% | 29.3% |
| Black point / white point (luma 1st / 99th percentile) | 0 / 255 | 0 / 255 |
| Hero-hue saturated share (red, within 15 degrees) | 24.9% | 18.4% |

Before this framework the skill taught hypersaturation only as an image-level grade (Image Guide v5
section 8F, Ruling 6 "selective saturation") and taught calm Cream and Navy grounds for pages; the
mockup tiers were the calm Set for Life look. A run that followed the canon correctly produced a calm
page (the run-003 outputs measure mean saturation 0.28 and 16% saturated pixels against 0.36 to 0.41
and 28 to 30%). The references were registered by name and size only. This framework closes that gap.

## Slots: every color is the client's

Nothing below names a hex. Every rule is a ratio over four **roles**, filled from the client's
resolved palette (`scripts/brand_colors.py`, never a default, never another client's palette):

| Role | Filled with | Chosen by `hypersaturation.roles()` |
|---|---|---|
| **Hero** | the client's single most chromatic color | the recorded `primary`, else highest chroma |
| **Dark** | the client's darkest color | lowest luminance |
| **Light** | the client's lightest color | highest luminance |
| **Accent** | a second chromatic color, reserved for the call to action | first distinct accent or secondary; **none** when the palette has no second chromatic color |

**No second chromatic color (the gold collision).** A one-chromatic palette (BlackCEO's own file:
gold, navy, cream) has hero and accent in the same hue. The framework does not invent a color: the
call-to-action slab is the hero color on the dark and light grounds and the dark color on the hero
ground, and the prompt says so. A hue-angle measure cannot separate hero from accent in that palette.

The examples' own colors (red, black and white, green and tan buttons) are structure only
(`references/reference-image-use.md`). They are recorded as colors to never reproduce, never as a
palette to use.

## Page rules R1 to R9

QC-corrected: the evidence below is the figure that survived four rounds of independent review, and
where a review corrected the analysis, the correction is what is written here.

**R1. One hero hue owns the page.** The hero color is a flat full-bleed ground on a large share of the
page and also runs through the second headline line, rules, frame lines and the light inside photos.
Measured, hero hue only: edge ground 22.5% (VA) and 20.0% (VB); flat ground 14.1% and 8.3%. (The earlier
"about 30%" was the share of saturated pixels in every hue; for the hero hue alone it is 25.6% and
18.3% with photos included.) Enforced as `hero_hue_saturated_share` in the pixel check, plus reviewer.

**R2. Three hard grounds, changing section to section.** Hero, dark and light carry the page; VB adds
at most two small accent panels (R9). No pastel, blush, peach, cream-tint or grey grounds; no soft fades
between grounds; sections meet at hard butt joins or a deliberate connector. Off-role light ground
(pastel, blush, peach, cream that is not the client's light color) is 2.5% of the page in VA and 0.4%
in VB. The ground changes, or at minimum the composition changes (R7), at every section: VA does have
runs of three white sections in a row (longest same-ground run 8.6% of page height) and two black
sections touching, VB's longest run is 12.2%, so "no two neighbours share a ground" is **not** a rule.
Default rotation: hero, light, dark, light (`hypersaturation.ground_for`), pinned per section by
`section["ground"]`.

**R3. The light is clean and the dark is deep.** The light ground is exactly the client's light color,
flat and bright; the dark ground exactly the client's dark color, flat and deep; never a tinted,
dimmed, yellowed or ivory-washed version. Measured: near-black 26.3% / 18.8%, near-white 27.7% / 29.3%,
black point 0, white point 255, almost no mid-tone fog. Enforced by four metrics in the pixel check.

**R4. Heavy two-tone headlines.** Heavy, large display type; the first line in a ground-contrast color,
the second line or keyword in the hero color (on a hero ground, in the dark color). VA uses condensed
all-caps; VB mixes serif, script and chips. Take the two-tone treatment and the weight, not VB's five
type faces. Fonts come from the brand file.

**R5. A typographic divider is a section, when the offer has chapters.** Full-width bands of oversized
repeated type ("DAY 1 DAY 1 DAY 1") open each chapter. This is conditional: Amendment 6 (C14) adapts
chapter markers only when the client's offering has curriculum structure, so it is never forced on a
page without one.

**R6. Photographs are tight, backlit and graded to the page.** The hero color appears as rim or
background light; photos bleed to a page edge or fill their slot; a hero-color device frames them
(offset bracket, edge bar, translucent wedge, arch or circle crop; a ring in the circle styles). The
hero hue that is not flat ground (photo light, type, rules, frames) is about 8 points of the page in both
references (VA 8.1, VB 7.9), an upper bound for photo light; the run-003 outputs show 2.9. The image
grade (below) is how this reaches the pixels.

**R7. No two consecutive sections share a composition.** Image left then right, full-bleed photo with
type on it, framed panel, giant repeated-word band. This is already a written brand rule; the
composition library and design styles (below) own the vocabulary.

**R8. The call to action is a solid slab, repeated.** One design every time, in the accent color (or the
hero or dark color when the palette has no accent), with ink chosen for contrast. A seat counter, a
countdown and a "seats left" line are part of the references; they are **client copy**, so the prompt
prints a scarcity line only when the verbatim copy carries one, and a copy guide must add the pattern
(Standard v6 and Long-Form v6 have none today) before a page shows it.

**R9. The accent is small and never the hero.** The accent fills every call-to-action button and may
appear in chips and badges. As a ground it is optional and rare: VA never uses its green as a ground
(0.7% of pixels, no band); VB uses its tan as ground panels twice (the "you'll discover" panel and the
"so you fire them" panel, about 2.8% to 3.3% and 2.76% of page height, about 5.5% to 6.1% together,
inset or edge-to-edge, which the edge-strip measure alone misses). Rule written for the prompt: at most
two small accent panels, together under 7 percent of the page height, never the hero hue. "The accent is
never a ground" would fail VB, one of the two sources.

## VA and VB: what to take from each

- **VA (clean and graphic).** The structure: flat white, hero and black bands, one headline treatment
  repeated, photos as clean rectangles with a hero-color device. Use VA for R1 to R4 and R6 to R8.
- **VB (layered and maximal).** The accent use (R9) and the shape vocabulary: arched and rounded crops,
  full-bleed photos with text on them, photos inside colored panels. Those shapes map to the circle
  and hybrid design styles (Style B Circle, Style C Hybrid: `references/design-styles.md`) and to the
  composition library's `mask-arch`, `mask-circle`, `mask-pill` and `caption-over-photo` treatments
  (`references/composition-patterns.md`). Do not take VB's many type faces, its patterned grounds or its
  thin light text on mid-value patterns.

## The image grade

Every image the skill generates carries this block, verbatim from `hypersaturation.grade_block()`, with
the client's hero (and accent, when it has one) in the slots:

> IMAGE COLOR GRADE - hyper-saturated cinematic color grade; deep true blacks, crushed shadows; vivid
> fully saturated [hero color] and [accent]; clean bright whites; high contrast, punchy midtones; strong
> directional key + rim light; luminous natural skin, true and rich, never tinted by the hero color.
> NEGATIVE - no muted, matte, faded, pastel, washed-out, flat or low-contrast grade, no grey haze, no
> warm ivory wash as the white.

It is additive to the signature grade block (`assets/brand/signature-grade-block.txt`, Ruling 6): the
same selective-saturation doctrine, stated as the explicit pixel qualities Trevor's order names. Skin,
neutrals and shadow detail stay protected; only the hero and accent are pushed. A prompt that already
carries the block is not given a second copy.

## Where it is wired

| Place | What it does |
|---|---|
| `scripts/stage_executor.py` `stage_prompt()` | `visual-mockup` and `final-mockups` prompts carry the PAGE COLOR SYSTEM block (the section's ground, the four slots, the rules) and the image grade block, ahead of the frame contract and negative block. Counted in `contract_chars` and reported as `hypersaturation_chars`. Wireframe stages are unchanged. |
| `scripts/stage_executor.py` `run_item()` | Every image-inventory item prompt gets the image grade block unless it carries one, and is refused (never silently trimmed) if prompt plus block passes the model maximum. |
| `--preflight` | prints `PREFLIGHT_HYPERSAT <stage> <file> ground=<ground> chars=<n>` per prompt. |
| `scripts/validate_page_color.py` | the page-level pixel check below. |
| `references/section-image-prompt.md`, `references/qc-contract.md` | the example set's colors and golden-hour look are now a structure benchmark only; the client's colors and this framework govern. |

The blocks are written to win over any other palette or "warm", "muted" or "ivory" wording in the same
prompt, because a request builder's design prose can still carry an old look; builders must not, and the
executor enforces it: a mockup or item prompt whose prose carries a `#hex` outside the client's palette, or
that has no resolved client palette at all, is refused before any provider call (never sent without the
blocks, never sent against them).
Budget: about 1,800 characters for the page block and 600 for the grade, inside the model band
(GPT Image 2.5: floor 16,000, target 19,000, maximum 20,000) like every other contract block.

## Quality check: `scripts/validate_page_color.py`

Pillow only, on a stitched page or full render. Six metrics (plus the hero-hue share when `--hero` is
given) against thresholds derived from VA and VB alone: floor = the weaker reference minus the larger of
the VA to VB spread and a noise tolerance (10 percent, or 8 levels of 255); ceiling for the black point
the same way mirrored. The numbers and the derivation are in `page-color-thresholds.json`; the command
`validate_page_color.py calibrate VA VB` reproduces them. No output of any run set a number.

```
python3 scripts/validate_page_color.py check STITCHED_PAGE.png --hero '#CLIENT_HERO'
```

Exit 0 PASS, 1 FAIL, 2 unreadable image, 3 UNDETERMINED. It is a page check (a single section slice is
mostly one ground) and a desktop calibration (no mobile reference exists). Ground order, divider bands,
off-role light grounds and accent panels remain reviewer-judged traits.

## Sibling lanes this consumes (not rebuilt here)

| Lane (branch) | What this framework uses from it | State at this commit |
|---|---|---|
| SPF019 `sigpage-brand-colors` (R69) | the resolved client palette: `scripts/brand_colors.py` `resolve(run_dir)`; `hypersaturation.roles_for_run()` calls it when present | not on main; until it lands, `roles_for_run` uses the stage gate's own brand lookup (`brand_path_for_checked`) and requires the file's `brand_id` to equal `intake.json` `brand_owner`, so prompt and gate read the same file |
| SPF022 `sigpage-reference-use` (R72) | the media-library upload method (`ghl-media-upload.sh`, reuse by SHA-256) and the structure-only reference contract (`references/reference-image-use.md`, `reference-library.json`) | upload method used; the contract file is not on main |
| SPF023 `sigpage-composition-library` (R73) | the composition vocabulary (`references/composition-patterns.md`: `mask-arch`, `mask-circle`, `mask-pill`, `caption-over-photo`) behind R7 | not on main |
| SPF025 `sigpage-design-style-choice` (R75) | Style B Circle, Style C Hybrid (`references/design-styles.md`): VB's arched and rounded crops map there | branch has no commits yet, so the file does not exist; the mapping is stated here, not linked |

These are named so the overlaps are visible; none of their files is edited by this change.

## Rulings and overlaps still open

1. **BlackCEO brand law.** `BlackCEO-Page-Brand-Law.md` page rule 1 says "alternate Navy and Cream
   grounds; Gold is the accent and CTA color". R1 and R2 put the hero color (gold, for BlackCEO's own
   pages) on about a quarter of the page as a ground. That needs Trevor's ruling in the brand file; this
   framework does not edit the brand law.
2. **Accent rule for one-chromatic palettes** (the gold collision above) needs the same ruling.
3. **VA and VB are red, black and white.** "Use the client's brand colors" and "match VA and VB
   literally" cannot both hold; the framework is the roles, the palette is the client's.
4. **Reference library entries.** VA and VB need `signature_palette` and `brand_text` entries in
   `references/reference-library.json` (SPF022) so the reference bleed check can flag a copied palette;
   the values are recorded under `hosted_links` in `assets/page-references/substitutions.json`.
