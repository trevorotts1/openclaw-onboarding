# BlackCEO Page Brand Law

Every stage of a BlackCEO Signature page run loads this file plus the run's brand file
(`intake.json` → `brand_file`). Client pages use the client's own brand file (from
`assets/brand/client-brand.template.json`, filled by the client). BlackCEO pages use
`assets/brand/blackceo-brand.json`.

## The five brand-law rules

Quoted verbatim from
`~/.openclaw/workspace/departments/graphics/roles/blackceo-brand-law-steward.md:23-27`:

> 1. Palette is Gold, Navy, and Cream. No substitutions.
> 2. BlackCEO is a Black company. Never use white, Spanish, or non-Black imagery in a BlackCEO-branded design. People depicted in BlackCEO assets are Black.
> 3. Trevor appears on every BlackCEO cover, the way Oprah appears on every O Magazine cover. Always his real image, never stock.
> 4. The masthead is a single-letter B. The logo is CEO bold plus BLACK white on a horizontal black bar through the E.
> 5. Image generation defaults to KIE.ai. Text overlay defaults to PIL. Video defaults to KIE.ai gemini-omni-video. Voice defaults to Fish Audio s2-pro. OpenAI image generation is forbidden without Trevor's express, per-instance permission.

## Hex values

From `~/.openclaw/workspace/departments/graphics/*/TOOLS.md:1073`:

- Gold `#C9A227`
- Navy `#1A1A2E`
- Cream `#F5F0E8`

Logo-only colors: `#000000` (black) and `#FFFFFF` (white) — allowed only inside elements
marked `data-brand="logo"`.

## Trevor's archived page look (his own words)

Quoted verbatim from
`~/clawd/projects/Signature-Landing-Page-ARCHIVED/SOURCE-FRAMEWORK.md:99-105`:

> 1. Vibrant, high-contrast colors; bold eye-catching palettes; strong visual impact.
> 2. Creative use of people (close-ups, striking poses).
> 3. Artistic flair — fashion-photography feel; composition, lighting, mood.
> 4. Disruptive + edgy; provocative, unconventional.
> 5. Emotional storytelling — each image conveys emotion/narrative/journey.
> 6. Signature page design = high-contrast color use; each section is its own piece of art, like a fashion show.

Quoted verbatim from `SOURCE-FRAMEWORK.md:141`:

> very vibrant, heavily color-graded, oversaturated (~140% saturation), high-contrast, distinct look

## Page design rules (from the brand file)

1. High-contrast color use: alternate Navy and Cream grounds; Gold is the accent and CTA color.
2. Each section is its own piece of art, like a fashion show: no two consecutive sections share a composition.
3. Image-led sections use the image at the wireframe's full slot width; no shrunken images floating in empty space.
4. The B masthead / CEO logo appears in the first viewport.

## Banned page patterns (from the brand file)

1. beige or off-white minimalism outside the Cream token
2. Inter or system fonts
3. small identical black rectangular buttons on every CTA
4. 40% or more of a section's width left empty at 1440px
5. numbered black circles on a thin rail
6. repeated identical card grids
7. purple/blue SaaS gradients
8. glassmorphism
9. emoji icons
10. every section centered
11. same image ratio everywhere
12. warm amber 'cozy shop' stock look (wood counters, Edison bulbs, kraft boxes, coffee-and-keys flat-lays)

## Fail closed

If the brand file has any `TREVOR_MUST_SUPPLY` / `CLIENT_MUST_SUPPLY` value, the intake
stage is BLOCKED and the run stops with the exact missing item named. Never invent a
palette, font, logo, or photo.

**Font carve-out:** missing brand fonts are the one exception. `font_policy` in the brand
file sets `when_brand_fonts_missing: "derive-document"`: if the brand fonts are still
`TREVOR_MUST_SUPPLY` / `CLIENT_MUST_SUPPLY`, the agent derives the best display/body/accent
faces for the job, documents the rationale in the visual bible (`fonts_source: "derived"`,
`font_rationale`, `font_reviewer`), and the reviewer approves — fonts are never blocked.
Every other `MUST_SUPPLY` / `CLIENT_MUST_SUPPLY` value (palette, logo, masthead files,
founder photos) still blocks intake until the owner supplies it. Derived fonts remain bound
by `banned_fonts`: a derived face may never be a banned font.

## Signature Grade Block

The canonical grade block lives at `assets/brand/signature-grade-block.txt` (extracted
byte-for-byte from
`~/clawd/projects/Signature-Landing-Page-ARCHIVED/IMPROVED-FRAMEWORK-v2.md`, section 2.4).
In `SECRET_SAUCE_ONLY`, every image prompt embeds it verbatim. Until the grade thresholds
(`grade.min_mean_saturation`, `grade.min_luma_std`) are calibrated by Trevor-approved
images, they stay `null` and grade checks run as uncalibrated WARN.
