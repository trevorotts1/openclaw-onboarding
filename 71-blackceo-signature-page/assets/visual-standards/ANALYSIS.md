# Wireframe / Mockup / Hybrid standard: analysis and Skill 71 fix list
Source: Trevor's Drive folder 1xzD60xunVH-eFOZkk4Ev28ZFziRZBxQ0 (downloaded 2026-10-15, reviewed visually by Martin at native resolution in slices).

## What Trevor supplied

Wireframes folder (5):
1. BlackCEO Signature Landing Page, Standard Desktop Wireframe (12 sections, annotated)
2. BlackCEO Signature Landing Page, Standard Mobile Wireframe (annotated)
3. BlackCEO Signature Landing Page, Long-Form Desktop Wireframe (pain/solution alternation, 5A/5B/5C why beats)
4. BlackCEO Signature Landing Page, Long-Form Mobile Wireframe (3-column contact sheet of the full page)
5. Set for Life Desktop Wireframe, long-form (1440 x 16736)

Mockups folder (5):
1. Set for Life Desktop Mockup, long-form (1440 x 16723, the pixel-mate of wireframe 5)
2. Set for Life Mobile Mockup, long-form (780 x 48894, 2x of 390 CSS px, stitched sections)
3. Set for Life full-page mockup render (724 x 2172, desktop presentation)
4. Set for Life full-page mockup render (724 x 2172; labelled mobile, but its rows are multi-column, so it is a DESKTOP layout; do not use it as a 390 px mobile reference)
5. Hybrid board: "Mockup & Wireframe Mashup" (1536 x 1024; titled Long-Form, but its structure is the 12-section Standard, with no 2A, 3A or 4A)

## The difference (the classification rule)

WIREFRAME (Trevor's standard): a designed, annotated build spec rendered as an image, in the client's brand colors. Every section numbered and named against the 12-section standard; type specs printed on the sheet (H1/H2/body/CTA sizes, desktop and mobile); image slots rendered as deliberate placeholders (black-and-white photographic plates in the BlackCEO set; crossed boxes in the Set for Life set) each labeled with aspect ratio AND art direction (what the image must show); copy is the real copy when it exists (Set for Life) or structural placeholder copy (BlackCEO set: "GOES HERE" headlines, lorem bodies); CTAs shown as designed chips with real button text and microcopy specs; behavior notes printed per section (e.g., "CTA before portrait on mobile", "No CTA", "Typography-only response"). A header strip states page width and content width.

MOCKUP: the same page with nothing left as a placeholder except genuinely unknown data (event date, start time). Real final copy, real logo, filled brand-color buttons, and real color photography generated to each slot's art direction. Indistinguishable from a screenshot of the finished page. The Set for Life desktop mockup matches its wireframe section for section, same layout, same copy; only the image boxes come alive and the buttons fill.

HYBRID: one presentation board that pairs the mockup-fidelity desktop and mobile pages with a section guide column (numbered sections, mini wireframe thumbnails, typography specs), so structure and finished look are approved from a single sheet. Note: the hybrid board's own column headers say "wireframe" over mockup-fidelity columns; the hybrid is about pairing, not a third fidelity level.

## How Trevor's were produced (read from the artifacts)

Generated with an image model in the GPT-image family (file names are ChatGPT Image exports; Trevor's direction: KIE.ai GPT-image going forward), section by section under a section guide, then stitched into single full-page images (the Set for Life pair are both ~16,700 px tall at 1440 wide; the mobile mockup is 17 stitched sections). Known artifact flaw even in his set: small-text garbles (a "DESKTOR" typo, a module numbered 42, garbled step descriptions in the steps band). Text fidelity is the weak point of fully model-rendered pages and needs a QC leg.

## What the Simulator Room produced, against this bar

- Its wireframe was an HTML screenshot render: real copy and brand-derived grounds (navy/cream), but NO printed annotations (no section numbers/names, no type specs, no behavior notes), image slots as bare empty boxes with an inventory ID, no header spec strip, no logo slot treatment. It reads as a web page screenshot, not a build spec sheet.
- Its mockup was the same render with the same empty boxes: by Trevor's definition not a mockup at all, because the skill's stage order puts visual-mockup (stage 6) BEFORE image generation (stage 8), so a stage-6 mockup can never carry real images.
- Root inversion: Skill 71 treats HTML as the design source and images as a late fill. Trevor's standing method (also his 2026-10-11 rule) is the reverse: the image is the design source of truth; the live HTML page is then built to MATCH the approved mockup.

## Fix list for the signature page skill (Skill 71)

1. REDEFINE the wireframe artifact: an annotated spec IMAGE (desktop + mobile), generated per section with the GPT-image model on KIE.ai, in the client's brand colors, carrying section numbers/names, printed type specs, image slots as designed placeholders labeled with ratio plus art direction, real copy (the run's copy stage precedes wireframes), CTA chips with real button text, per-section behavior notes, and a header strip with page/content widths. Deliver as one stitched full-page PNG plus a combined PDF plus section slices.
2. REORDER the mockup: image generation moves BEFORE the mockup stage (or visual-mockup and final-mockups merge into one post-generation mockup stage). The mockup is generated per section under the same section guide, real photography composited into every slot, real logo and supplied assets placed as files (never generated), buttons filled in brand color. Same deliverable formats as the wireframe.
3. ADD the hybrid board as a standard deliverable at mockup close: desktop mockup + mobile mockup + section guide on one sheet for the client's single approval pass.
4. PRODUCTION METHOD, pinned: per-section generation via KIE.ai GPT-image (exact model ID pinned from the model registry at build time), with the approved wireframe section as layout reference and the page visual bible (palette, fonts, grade) as style input; generate each section at its native aspect; deterministic stitcher; PDF combiner. Text-fidelity QC at native resolution per section: any garbled word in a section fails that section and regenerates it before stitching (never accept a garbled section into the combined artifact).
5. REFERENCE LIBRARY: Trevor's two folders become the skill's visual standard set for wireframes, mockups, and the hybrid (alongside the existing page references), and the gates check traits (annotations present, slots labeled, brand colors, zero placeholder slots in a mockup), not general impressions.
6. GATE CHANGES: wireframe gate fails on missing annotations, unlabeled slots, or off-brand colors. Mockup gate fails if any image slot remains a placeholder. The stage order amendment in item 2 replaces the current order and structurally resolves the 2026-10-15 mockup-fidelity finding.
7. HTML PARITY: the responsive-html stage builds to MATCH the approved mockup, with a side-by-side parity check (render vs mockup) as its gate evidence, per Trevor's standing rule that the live page must match the approved mockup.

Status: analysis delivered to Trevor 2026-10-15; skill changes NOT yet ordered or built. The current Simulator Room run continues under the old stage design; its final-mockups stage is where a real-image artifact first appears in that run.

## Addendum 2026-10-19 (composition library, unit SPF023)

Trevor supplied more images on 2026-10-19. They are classified, deduplicated and hosted in the BlackCEO media library; the typed list is `reference-catalog.json` in this folder (63 rows, each with the hosted URL and the sha256 of the uploaded bytes). Nothing new is bundled as a PNG: a catalog row names its bundled source where one exists (`source_bundle`) and a crop box where it is a slice or crop.

Added to the library: the Gen 2 long-form image maps and mockups (three each, Parts A to C), the 12-section Standard hybrid board, the annotated desktop pair (07_01_47 and 07_01_49), the mobile wireframe and mobile mockup cut into 24 section slices each (at most 780 x 3000, paired by section number), and three Go Full Page crops that show one composition trait each (a light line-art field behind type, type over a dark full-bleed photo, a shaped photo mask with a brush stroke).

Kept OUT of the library as anti-examples (an anti-example sent as a reference teaches the model the wrong thing):
- 07_01_50 PM-3: a mood board that leaked into the page. Its "sections" are palette, type and size guidance. It is the anti-example of mood board versus wireframe.
- 07_01_52 PM-4 (bundled as chatgpt-mockup-4): claims mobile but uses multi-column rows. It is a desktop layout.
- 04_55_03 AM: titled "Mobile wireframe" but it is a full-colour seven-phone mockup storyboard that adds testimonials, an FAQ and a hard date the Standard forbids. Format reference only, in words.

Tagged `counter-example-composition` in the catalog (structure and labelling only): the Gen 1 desktop pair and the mobile mockup slices. Every image in them is a rectangle beside or above text, which is the AI default; the Gen 2 mockups are the ones that put captions and panels on photos.

Gaps the catalog does not yet fill (the prompt rules in `references/composition-treatments.json` carry them): a true circle-cropped photo, a hero-scale light field behind type, and a hero with the headline on a flat bright zone of a full-bleed photo. The plan is to build these as HTML renders with CSS masks so a reference shows the exact technique the build uses.

Reference-only text: two mobile slices (12 Part 2 to 4) carry the placeholder copy "Trevor's story"; the catalog flags them `contains_reference_only_text`. The Set for Life brand, palette, people and copy never carry into a client page.

## Update 2026-10-19 (wireframe style reference)

The fix list above has since been built. One decision was added: the wireframe
stages no longer send the greyscale Set for Life sheet as their style
reference. They send `chatgpt-wireframe-1` (Standard desktop), `-3` (Long-Form
desktop) or `-4` (mobile) by stage and form, and the prompt asks for an annotated
build spec in the client's resolved brand colors. See `README.md` in this
folder ("Which sheet is the wireframe style reference") and
`references/wireframe-build-spec.json`.
