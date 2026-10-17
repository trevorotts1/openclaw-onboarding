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
4. Set for Life full-page mockup render (724 x 2172, mobile presentation)
5. Hybrid board: "Mockup & Wireframe Mashup" (1536 x 1024)

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
