# Visual standard set: wireframes, mockups, and the hybrid board (Item 14)

This folder is the skill's visual standard for three artifact kinds:
the **wireframe**, the **mockup**, and the **hybrid board**. It bundles
Trevor Otts' own two example folders, supplied by him as the worked
standard, alongside the existing page references in
`assets/page-references/` (which anchor page layout and copy quality;
this set anchors what the wireframe, mockup, and hybrid artifacts
themselves must look like).

## What is here

- `wireframes/` — the wireframe examples: the BlackCEO standard
  desktop and mobile sheets, the BlackCEO long-form desktop sheet and
  its mobile contact sheet (the `chatgpt-wireframe-*.png` presentation
  renders), and the Set for Life long-form desktop wireframe
  (`set-for-life-desktop-wireframe.png`, 1440 x 16736) with its two
  slicings (six `*-slice*.png` files and five `sfl-wireframe-part*.png`
  files).
- `mockups/` — the mockup examples: the Set for Life desktop mockup
  (`set-for-life-desktop-mockup.png`, 1440 x 16723, the pixel-mate of
  the desktop wireframe) with six slices; the Set for Life mobile
  mockup (`set-for-life-mobile-mockup.png`, 780 x 48894) with
  seventeen slices; the two Set for Life full-page presentation renders
  (`chatgpt-mockup-2.png`, `chatgpt-mockup-4.png`); and the hybrid
  board (`hybrid-mockup-wireframe-mashup.png`, 1536 x 1024).
- `ANALYSIS.md` — the 2026-10-15 analysis of these folders: the
  classification rule (wireframe vs mockup vs hybrid), how the set was
  produced, and the fix list this item implements. Read it with the set.
- `manifest.json` — the machine-readable inventory: every bundled
  file with its byte size, SHA-256, and pixel dimensions. Reviewers
  and tests verify the set against it; a bundled file whose hash does
  not match the manifest is not the standard.

Counted as logical artifacts the set is five wireframes and five
mockups including the hybrid board (per `ANALYSIS.md`); counted as
files it is 44 images, because the long-form pages also ship cut into
slices and parts for native-resolution review.

## Provenance and handling

Source: Trevor's Drive folder, downloaded 2026-10-15 and held at
`~/workspace/wireframe-mockup-standards/` until this bundling. The
bundled files are byte-exact copies of the supplied files (SHA-256
recorded in `manifest.json` and verified at bundling time). Never
re-render, resize, recompress, or regenerate a file in this set: it
is the owner's worked standard, not production material. Known flaws
in the set itself (small-text garbles noted in `ANALYSIS.md`) are part
of the record; they are why the production method carries a
per-section text-fidelity QC leg, not a reason to alter the standard.

## How reviewers use this set

Reviewers score wireframe, mockup, and hybrid artifacts against the
trait lists in `references/qc-contract.md` (section "Visual standard
set traits"), with this set open beside the artifact under review.
Gates check traits, not general impressions: a review record cites
traits by their IDs (W1 to W7, M1 to M5, H1 and H2) and names the
standard file compared. A trait that fails is recorded by name; a
mockup with any placeholder slot fails trait M1 outright.

## 999-copy parity (tracking note, not part of this change)

This set is neutral-class material under the FIX-PLAN Item 27 parity
machinery (`repo-integration/skill71-sync-allowlist.json`: anything
not otherwise classified is byte-parity). The bundled set, this
README, `ANALYSIS.md`, `manifest.json`, and the trait text in
`references/qc-contract.md` must therefore land in the 999 copy
(`.claude/skills/blackceo-signature-page`) file-for-file through the
Item 27 sync (or assembly equivalent), and parity is verified with
`scripts/check-skill71-parity.py` after the sync. That landing rides
assembly/batch; it is NOT done by this change, and Item 14 does not
close on the 999 leg until the sync and the parity check are on
record.
