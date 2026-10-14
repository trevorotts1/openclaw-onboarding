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

## Owner substitution recorded 2026-10-14 (Ruling 5)

This section qualifies the supply-status text above. It is the one
recorded exception to "Do not substitute similar-but-different files":
a substitution counts only when the owner has ruled on it and the
ruling is recorded here and in the machine-readable record,
`substitutions.json` in this folder, which the stage gate reads.

**The ruling.** Trevor Otts, 2026-10-14 (Ruling 5): the two
owner-supplied GoFullPage PDF captures of the BlackCEO 6-Figure Launch
Challenge registration page stand in for named files 2 and 3:

- `gofullpage-blackceochallenge-reg-va.pdf` (48,701,310 bytes) is the
  primary stand-in for
  `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07.png`:
  the same capture subject (the va design variant of the Challenge
  registration page), captured full-page top to bottom at higher
  resolution (2658 px wide, 334.5 PPI) than the named screenshot.
- The va PDF also covers
  `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07-2.png`:
  the named file is the continuation of the same page (Day 5 and the
  closing founder letter), and the va PDF's full-page stack
  (2658 x 45,736 px) contains that content, founder letter included.
- `gofullpage-blackceochallenge-reg-vb.pdf` (59,269,104 bytes) is the
  second design variant of the same page, registered alongside the
  primary. Two variants of one page are not two distinct references,
  and the vb capture does NOT reach the continuation's tail: it ends
  at the first sliver of the grid photograph, so the master-grid
  section, founder letter, and founder portrait are absent from it.
  Coverage of file 3 rests on the va PDF alone.

**Reading order effect.** For the Challenge page, read the va PDF
(which replaces reading steps 2 and 3 above). Step 1, the Elevation
Conference file, is unchanged: see below.

**Where the files live.** The PDF binaries are NOT bundled in this
folder. They are held in the diagnostic record
(`skill-71-diagnostic/owner-examples/`, registered 2026-10-14 with
sizes and dimensions verified at intake). At 108 MB combined, bundling
them into the skill is a separate owner-visible step awaiting
Trevor's word. The stage gate satisfies files 2 and 3 from
`substitutions.json`, not from the binaries.

**Still outstanding.** Named file 1,
`Sales Page - Elevation Conference - Desktop(1).jpg`, is NOT
substituted and NOT waived. It remains a required original, and the
stage gate still refuses to open desktop-wireframe, mobile-tablet, or
visual-mockup for any run whose intake carries no recorded
layout-references waiver, naming this file. A waiver excuses it for
one run only; it does not retire the requirement.
