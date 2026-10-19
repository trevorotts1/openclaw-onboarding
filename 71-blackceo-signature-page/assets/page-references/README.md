# Page-layout reference files: REQUIRED READS, RESOLVED IN ORDER

Standard v6 cites three page-layout reference files by exact name. They are
REQUIRED reads for the desktop-wireframe, mobile-tablet, and visual-mockup
stages (Item 13 wires them into those stages' `reads` arrays in
`references/stage-contract.json`).

## How each reference resolves (Item 17, ruled 2026-10-15)

Each reference resolves in this order:

1. The supplied or bundled original file in this folder.
2. The approved house default recorded for it in the standing registry,
   `substitutions.json` in this folder (per reference: the approved
   default and its owner ruling).
3. A recorded owner waiver in the run's `intake.json`
   (`layout_references_waived: true` with a non-empty
   `layout_references_waiver_reason`, or a `layout_waivers` entry for
   `layout-references` with a reason), kept for true exceptions.

Only a reference with none of the three stops the stage, and the stage
gate names it. Every run records per reference which source it used,
and REPORT.md prints it (original file, house default by name, or
waiver): a fallback is visible, never silent. No agent may fabricate,
generate, or substitute a reference or a default; a default counts
only when the owner has ruled on it and the ruling is recorded in the
registry.

## The three references

1. `Sales Page - Elevation Conference - Desktop(1).jpg`
   Bundled in this folder: the ruled live-preview capture
   (2026-10-15, Update Plan Decision 4; provenance below).
2. `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07.png`
   The original PNG is not bundled; the approved house default is the
   GoFullPage va PDF capture (Ruling 5; see the registry).
3. `screencapture-blackceochallenge-reg-va-2026-09-29-15_52_07-2.png`
   The original PNG is not bundled; the approved house default is the
   same va PDF capture, whose full-page stack contains this file's
   continuation content (Ruling 5; see the registry).

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

This section qualifies the resolution text above. It is a recorded
exception to "Do not substitute similar-but-different files":
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

**File 1 status at the close of the Ruling 5 record.** Named file 1,
`Sales Page - Elevation Conference - Desktop(1).jpg`, was NOT
substituted and NOT waived under Ruling 5. It has since been satisfied
by the ruled capture recorded in the next section (2026-10-15).

## Owner substitution recorded 2026-10-15 (Update Plan Decision 4)

**The ruling.** Trevor Otts, 2026-10-15 (Skill 71 Update Plan
Decision 4): a capture of the Elevation Conference sales page, taken
from its live Convert and Flow preview, STANDS as named file 1,
`Sales Page - Elevation Conference - Desktop(1).jpg` (Standard v6
substitution). Update Plan Item 18 executed the capture and this
placement.

**The file.** The capture is bundled in this folder under the cited
filename itself: a full-page JPEG, 2,880 x 27,010 px (1440 CSS px
desktop width at device scale factor 2), 7,108,476 bytes, SHA-256
e35b45939e99634c4302366cf23f1f262af0dc91ead3cbeb440d8f77a5ccab4b
(the hash is also recorded in `substitutions.json`). It was captured
on 2026-10-15 from the live Convert and Flow preview of the Elevation
Conference sales page (preview code n1ZoDWZ0csqYm5q4oaZe), stitched
from per-viewport screenshots taken after a full scroll-through, so
every scroll-triggered section background renders as a visitor sees
it. The diagnostic-side record is
`skill-71-diagnostic/owner-examples/CAPTURE-NOTE.md`.

**Verification at capture.** Section-by-section visual comparison
against the live preview: all 12 sections present in order (big
claim, three pain movements, invitation, who it is for, what to
expect, the H.E.R. sessions and keynote, transformation panels, next
steps, founder letter); the founder letter from Mary H. Davis
present in full; no pricing anywhere on the page.

**Scope of the exception.** This substitution covers file 1 only.
The non-substitutes warning above stands for everything else: no
other file may be fabricated, generated, or substituted without its
own recorded owner ruling.

## Hosted links for the GoFullPage PDFs (2026-10-19, SPF020)

The two PDFs (108 MB together) are never bundled in the skill. They are
bundled as links: downscaled renders hosted in the operator media library
(BlackCEO LLC, folder `sigpage-reference-images`), each link re-downloaded
and compared byte for byte at upload. The machine-readable record, with the
SHA-256 of every file, is `hosted_links` in `substitutions.json`; a run reads
the links, not the binaries.

| Variant | What it is | Long stack (1000 px wide, 14 pages) | Overview sheet |
|---|---|---|---|
| VA | clean and graphic: flat white, hero and black bands, one headline treatment | https://assets.cdn.filesafe.space/Mct54Bwi1KlNouGXQcDX/media/14843a81-8078-4f9a-8114-7238642d7e5e.jpg | https://assets.cdn.filesafe.space/Mct54Bwi1KlNouGXQcDX/media/c2fe1ba2-6b8f-4e39-82b6-6b9cc5ccca1d.jpg |
| VB | layered and maximal: arched and rounded crops, patterned grounds, a second accent | https://assets.cdn.filesafe.space/Mct54Bwi1KlNouGXQcDX/media/08a32404-9d2c-4143-bd3d-fd72a01236b4.jpg | https://assets.cdn.filesafe.space/Mct54Bwi1KlNouGXQcDX/media/30936148-dc9b-4fe7-815f-6b4c7ad6d3d4.jpg |

Each variant also has its 14 pages as separate 1000 px renders (`hosted_links`
in `substitutions.json`), for jobs that attach a few pages instead of the
whole stack.

**What these teach.** The page-level color system and section rhythm, as
roles: one hero color as full-bleed grounds, hard dark and light grounds,
two-tone heavy headlines, photos graded to the page. The rules are
`references/hypersaturation-framework.md`. They are STRUCTURE ONLY, under
`references/reference-image-use.md`: the pages' own red, black and white, the
green and tan buttons, the brand name and the copy never reach a client page.
The sampled colors and brand strings are recorded in `hosted_links` so the
reference bleed check can flag them. Use VA for structure and VB for its accent
use and shape vocabulary (its arches and rounded crops map to the circle and
arch treatments of the design styles and composition library), never VB's many
type faces.
