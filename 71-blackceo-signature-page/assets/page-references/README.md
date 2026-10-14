# Page-layout reference files: BUNDLED, REQUIRED READS

Standard v6 cites three page-layout reference files by exact name. They ship
with the skill in this folder and are REQUIRED reads for the
desktop-wireframe, mobile-tablet, and visual-mockup stages (Item 13 wires
them into those stages' `reads` arrays in `references/stage-contract.json`).
Do not substitute similar-but-different files.

## The bundled files

1. `Sales Page - Elevation Conference - Desktop(1).jpg`
2. `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07.png`
3. `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07-2.png`

Supply status: Trevor supplies the three originals (order section G3); no
agent may fabricate, generate, or substitute them. If any of the three is
missing from an installed copy of the skill, the stage gate refuses to open
desktop-wireframe, mobile-tablet, or visual-mockup unless `intake.json`
carries `layout_references_waived: true` with a non-empty
`layout_references_waiver_reason` typed by Trevor himself. A missing file
with no recorded waiver is a hard stop, never a silent fallback to SOP
structure rules alone.

## What these files are (Standard v6's own framing)

They are low-resolution copy-and-layout CALIBRATION references: use their
legible display copy and their visible arrangement to calibrate copy quality
and layout rhythm. The Elevation Conference JPEG calibrates copy quality; it
does not prescribe a new format.

## Prescribed reading order

Read in this order, every time:

1. `Sales Page - Elevation Conference - Desktop(1).jpg`, for copy quality.
2. `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07.png`, the
   title-first BlackCEO challenge page.
3. `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07-2.png`, its
   continuation (it carries Day 5 and the closing founder letter). The
   challenge image is always read BEFORE its `-2.png` continuation.

## The written CTA map wins

Where a reference's historical CTA placements differ from the written CTA
map (the selected copy guide's CTA map as enforced by the copy stage), the
written map wins. Do not copy CTA placements out of these screenshots.

## Where the skill cites them

- `references/BlackCEO-Signature-Landing-Page-Standard-v6.md:137`
- `references/BlackCEO-Signature-Landing-Page-Standard-v6.md:1681`
- `references/BlackCEO-Signature-Landing-Page-Standard-v6.md:1690`

## Known non-substitutes (do NOT use these)

Verified present on Trevor's Mac but NOT the named files:

- `~/Downloads/screencapture-blackceochallenge-ds1-2026-09-08-14_16_30.pdf`
- `~/Downloads/screencapture-blackceochallenge-us1-2026-09-08-…pdf`
- `~/Downloads/Images/Brandy Henderson_Elevation COnference Overlay V2.png`

`assets/BlackCEO-Master-Visual-Reference-Guide.png` is an image-style menu
only. It is not a page-layout or page-color reference.
