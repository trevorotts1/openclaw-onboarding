# HTML QC Rubric — Skill 71 responsive-html stage

Scored by an independent reviewer (author ≠ reviewer) on the compare sheets in
`responsive-html/compare/` produced by `scripts/compare_sheet.py`, plus the page
rendered at 1440 / 768 / 390 from `scripts/render_page.py`. Every criterion is
scored 0–10; every criterion must be **≥ 8** for the stage to close. Any
auto-fail below fails the stage outright regardless of scores.

The palette, fonts, logo, and banned-pattern list referenced here come from the
run's brand file (`intake.json` → `brand_file`). Never score against tokens an
agent invented.

## Criteria (each 0–10, each must be ≥ 8)

1. **Brand palette fidelity** — every visible color (text, backgrounds, borders,
   SVG fill/stroke) is a brand palette color or a logo-only color inside a
   `data-brand="logo"` element. No invented tints, no "close enough" shades.
   10 = exact tokens only; below 8 = any off-palette color visible.
2. **Brand typography** — every text element's first font family is a brand
   font; the brand fonts actually load (`document.fonts.check` true). 10 = only
   brand fonts render everywhere; below 8 = any system/banned font renders.
3. **Logo / masthead present** — on a BlackCEO page the B masthead / CEO logo is
   visible in the first viewport at 1440, 768, and 390. 10 = present and crisp at
   every width; below 8 = missing or cropped at any width.
4. **Section-by-section match to final mockup** — score EACH section separately
   (record one score per section; every section must itself be ≥ 8). Ground
   colors, composition, image slot placement, and heading scale must match the
   final mockup piece for that section. 10 = visually identical layout; below 8
   = any section whose structure, ordering, or visual weight drifts from the
   mockup.
5. **Image crops and sizes match slots** — each image renders at ≥ 90% of its
   slot width from `image-map-upload/image-map.json` (`desktop_slot_px`), with
   the intended crop, no stretching, no distortion, no shrunken image floating
   in empty space. 10 = every slot filled at full width; below 8 = any slot
   under-filled or wrongly cropped.
6. **CTA hierarchy and styling** — primary CTA is the brand gold accent and the
   visually dominant action at every width; secondary CTAs are visually
   subordinate; no repeated identical black rectangles. 10 = clear hierarchy
   matching the mockup; below 8 = flat hierarchy or off-brand button styling.
7. **Copy parity** — every paragraph, heading, and button label in
   `copy/public-copy.md` appears in the DOM `innerText` (whitespace-normalized),
   and nothing that is not public copy appears. 10 = exact parity; below 8 = any
   missing public copy or any leaked private text.
8. **Mobile readability (390px)** — body text ≥ 18px computed, public microcopy
   ≥ 16px, buttons ≥ 56px tall, no horizontal overflow, tap targets do not
   overlap. 10 = clean at 390; below 8 = any cramped or overflowing element.
9. **Tablet reflow (768px)** — layout reflows sensibly between the 390 and 1440
   presentations: no desktop layout squeezed, no mobile layout stretched, no
   horizontal overflow. 10 = intentional 768 presentation; below 8 = broken or
   degenerate middle layout.
10. **No banned page pattern** — none of the `banned_page_patterns` from the
    brand file appears anywhere on the page (for BlackCEO: beige minimalism,
    Inter/system fonts, identical black CTA rectangles, ≥ 40% empty section
    width at 1440, numbered black circles on a thin rail, repeated identical
    card grids, purple/blue SaaS gradients, glassmorphism, emoji icons, every
    section centered, same image ratio everywhere, warm amber "cozy shop" stock
    look). 10 = none present; below 8 = any banned pattern present.
11. **No placeholders** — no visible bracket placeholders (`[LIKE_THIS]`), no
    "PLACEHOLDER", "NOT WIRED", "TODO", "lorem ipsum", `{{` templates, no empty
    image boxes. 10 = none anywhere; below 8 = any visible placeholder. (When
    `intake.test_run` is true, a validator reports these as WARN instead of
    FAIL — the reviewer still records the score honestly.)

## Auto-fails (any one = stage FAIL regardless of scores)

- Any banned font from the brand file's `banned_fonts` renders on the page.
- Any off-palette color outside `color_tolerance` renders outside a
  `data-brand="logo"` element.
- Missing logo/masthead on a BlackCEO page (not visible in the first viewport
  at any required width).
- A generated (non-real) image in the founder slot of a BlackCEO page — the
  founder photo must be one of `founder_photos` (SHA-256 verified by
  `validate_page.py`).
- Visible placeholder text when `intake.test_run` is false.

## Reviewer receipt

The reviewer's `private/receipts/responsive-html.json` must list every
`compare-<width>-NN.png` file by name with a score, e.g.:

```json
"compare_scores": {
  "compare-1440-01.png": 9,
  "compare-390-01.png": 8
}
```

`stage_gate.py close responsive-html` fails if any compare file on disk is not
listed. The reviewer must be a different agent from the HTML builder and must
open each compare image.
