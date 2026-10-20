# QC Contract

This file summarizes the mechanical control rules. The detailed qualitative rubrics remain in the writing, production, and image-intelligence guides.

## General page-stage pass rule

A stage passes only when:

- every applicable required quality criterion is at least 8/10;
- no automatic failure remains;
- the current artifact is the repaired/rechecked version;
- required upstream artifacts are already ready.

Examples of automatic failure include missing required content, wrong image, leaked private production labels, truncated text, broken main action, unsupported route presented as complete, or unresolved public placeholders.

## Prompt and generated-image pass rule

This bar is Skill 71's own, vendored here and in the Image Guide's QC section (Update Plan Item 21, Decision 5: the skill carries its own standard and defers to no external repository for this bar). Retain it exactly:

- average at least 8.5;
- every applicable individual criterion at least 8;
- zero automatic failures.

The deterministic scripts check measurable constraints only. They do not replace an independent qualitative review of copy, composition, style fidelity, representation quality, emotional effect, visual distinctness, or final pixels.

## Deterministic image grade screen (Items 8 and 9)

`scripts/validate_image_grade.py` is the pixel screen for generated images. It measures, per image, with Pillow only: mean HSV saturation, luminance standard deviation, sharpness (variance of the FIND_EDGES convolution), and Hasler-Susstrunk colorfulness. Each measure has a floor in the brand file's `grade` block (`min_mean_saturation`, `min_luma_std`, `min_sharpness`, `min_colorfulness`). A threshold that is null is uncalibrated: the screen prints the measurement as WARN and applies no gate for that metric; thresholds are set only through Item 8's calibration (gold-set floors proposed by `scripts/calibrate_grade.py`, approved by Trevor), and the production gate refuses to close `image-generation-qc` while the brand is uncalibrated.

Two screen checks are unconditional and need no threshold: near-duplicate detection (8x8 average hash, retained as a tripwire only; a pair at Hamming distance 4 or less fails as a possible duplicate or near-identical shot, unless the pair is declared in the inventory's `continuity_group` as an intentional continuity series) and the native-ratio + crop-plan check (Amendment 6, Part B4: the rendered ratio must equal the entry's recorded native ratio after N43 remapping, the delivery export must equal the entry's recorded delivery dimensions, and a crop plan must be on file; checked when the validator is given `--inventory`). The distinctness enforcement layer is register-based, not pixel-based: an identical recorded skin-tone + hairstyle + facial-hair combination across two entries fails without recorded continuity, and adjacent entries with identical distinctness registers fail. When the run's Page Visual Bible blend profile marks the hero color/chroma dimension SUPPRESS or ADAPT, the saturation and colorfulness floors are N/A for the affected images and can never fail them.

## Style fidelity enforcement (Item 10, Amendment 6 Parts B and C)

Style fidelity is enforced against data, not impressions of the library texts. Before any prompt is authored, the run records a selection record (`image-inventory-prompts/style-selection.json`; see `references/style-selection.md`) naming the governing library, style, mode, any declared blend (Cinematic rule D blends pass only with recorded owner authorization), and the trait extraction the prompts are judged against (`references/style-traits/`). `scripts/validate_prompt.py` checks lock/anchor/trait expression by the extraction's checkable tokens, the recorded 3x3 subject zone in Element C, verbatim only where the guide mandates it, the human-only denylist, the Avoid list inside the generation instruction, undeclared foreign styles, and representation specificity. A lock with no checkable tokens is reported UNCHECKABLE-BY-DESIGN, never silently passed. Prompt length never passes or fails a prompt: element completeness governs, length is telemetry, a VERIFIED model cap is the only hard ceiling, and padding is a hard failure.

**Erratum (S71-06-Q1, ruled 2026-10-17):** the last sentence of the paragraph above states the retired length position and is superseded. Under owner Decision 1 (2026-10-15), which the Q1 ruling confirms governs in ALL contexts, including Signature Launch runs, prompt length is governed by the KIE rule 12 band (author each prompt to 95 to 100 percent of the model's recorded maximum, never below the 80 percent floor, genuine specification only): below the floor fails at the prompt stage (budget exit 3), above the maximum fails (budget exit 4), and cap_status is provenance only and carries no overflow semantics (no warn-only overflow). Element completeness governs acceptance of the prompt's elements alongside the band; length is not telemetry-only. Where the sentence above conflicts with the band, the band governs. Operative text: SKILL.md's prompt-validation paragraph, the Image Guide v5 rule 12 paragraph, and references/prompt-budget-policy.json.

Reviewers score the selected style's own gate (see `references/style-traits/README.md`): the Photographers ten-question Style Fidelity Check with the four-of-five locks rule, the Cinematic eight-dimension Fidelity Gate, or the Visual Artists entry's own dimensions at 8 or above with no averaging, plus its originality attestation. The per-artifact arithmetic above (average at least 8.5, every criterion at least 8, zero auto-fails) applies to EACH prompt and EACH image individually; scores are never pooled across artifacts.

**Fidelity-gate governing rule (Update Plan Item 28 / proposal P8):** When a style library supplies its own fidelity apparatus, that apparatus governs the style-level verdict for images under that selection. The guide's fidelity gate governs the page-level verdict (coherence across the page's images) and remains the only gate when no library apparatus applies. The two verdicts are recorded separately in the review; neither silently overrides the other.

## Residual judgment (Amendment 6, Part B6)

**Status (owner approval, 2026-10-15):** this section is approved governing doctrine, not commentary. Trevor approved the residual-judgment list below as governing text on 2026-10-15 (Skill 71 update plan, Decision 11; proposal P7 from the Item 30 reconciliation drafts; source: Amendment 6, Part B6). Review records cite this section as doctrine.

After the mechanical checks above, the following remain judgment, and no part of this skill may claim mechanical coverage for them:

1. whether locks and anchors are VISIBLY DOMINANT in the rendered image, the libraries' own pass standard, which no text defines a measurement for;
2. abstract anchors and properties a still cannot show (dignity, emotional attachment, social legibility, moral pressure; sequence-level properties such as montage and camera movement inside one shot);
3. process traits unverifiable from output (UV fluorescence in VDL-048, wet-plate process in VDL-029, collaborative authorship in VDL-014), where an output can mimic the appearance without the process;
4. stated parameters unrecoverable from a finished image (subject-to-backdrop distance in VDL-005, sun angle in VDL-015);
5. the copy guides' emotional-quality criteria, which are not a closed list in either guide;
6. the libraries' own production-ready claims, which rest on per-style QA scores (at least 8.0 of 10 on ten dimensions) that are published NOWHERE, making the claim unfalsifiable from the artifacts.

Mitigations, the strongest available: independent review under Item 2's receipt machinery as the floor for every judgment item; the per-style gate rubrics as the review FORM, so judgment is exercised against the style's own criteria rather than a generic impression; and this list, printed here so the coverage is never mistaken for total.

## Visual standard set traits (Item 14)

The skill's visual standard for wireframes, mockups, and the hybrid
board is Trevor's own example set, bundled at
`assets/visual-standards/` (inventory and hashes in its
`manifest.json`; the classification rule and production analysis in
its `ANALYSIS.md`). Reviewers score the traits below with that set
open beside the artifact under review, and the review record cites
traits by ID and names the standard file compared. Gates check
traits, not general impressions: any trait that fails is a named
defect in the review record, and a mockup failing M1 fails review
outright. Deterministic enforcement landed with Item 15 and runs
alongside review: `scripts/validate_wireframe.py` measures the
wireframe annotation traits W1, W2, W5 and W6 against the section plan
and the measured sheet, the slot-label trait W3 against the inventory,
and the brand-color trait W4 from the sheet's pixels, then writes all
six verdicts into the run record `private/wireframe-verdicts.json`,
one entry per wireframe stage (Fix 9, task 3.6);
`scripts/validate_mockup_slots.py` enforces the mockup placeholder-slot
trait M1 at final-mockups. The traits still bind through review, and a
trait-scored review must now name the standard file it compared the
artifact against: `scripts/write_review.py` rejects a review that
scores a wireframe or mockup trait criterion without a
`--standard-file` that exists under `assets/visual-standards/`.

Wireframe traits (a designed, annotated build spec rendered as an
image, in the client's brand colors):

- W1: every section is numbered and named against the selected
  version's sections (12 Standard, 15 Long-Form).
- W2: type specs are printed on the sheet (H1, H2, body, and CTA
  sizes, desktop and mobile).
- W3: every image slot is a deliberate placeholder (a
  black-and-white photographic plate or a crossed box), labeled with
  its aspect ratio AND its art direction (what the image must show),
  printed with its pixel box (for example `IMG-01 Hero portrait 1600 x
  1800 8:9`) and its composition treatment (`references/composition-
  treatments.json`). The wireframe DRAWS the treatment: the text box ON
  the placeholder for an overlay, a mask drawn as its real shape, a
  full-width tint for a light field, an overlap drawn as an overlap.
- W4: the sheet is rendered in the client's brand colors. The palette it
  is measured against is the one `scripts/brand_colors.py` resolved for
  this client (never a default or another client's palette), and the same
  palette is written into the wireframe prompt; with no resolved client
  palette W4 has nothing to measure against and the stage does not start.
- W5: a header strip states the page width and the content width.
- W6: behavior notes are printed per section (for example "CTA
  before portrait on mobile", "No CTA", "Typography-only response").
- W7: CTAs are shown as designed chips carrying the real button text
  and microcopy specs, and copy is the run's real copy where it
  exists.

Wireframe trait extensions (the look of the owner's wireframes 1, 3 and
4, drawn in the client's own colors). W1 to W7 keep their IDs. These
checks tighten them and add one negative trait; `scripts/validate_wireframe.py`
measures what it can, and a reviewer scoring W1 to W7 applies them all:

- W1, sequential numbering: the section chips run in sequence, each
  exactly once, none skipped, and a lettered tag follows its parent
  (1, 2, 2A, 3, 3A, and so on). A repeated or skipped number fails by name; the
  bundled examples print "SECTION 3" twice, skip 4, and read 44 and 52 on
  module badges, which is why no example is a numeral standard. Any badge
  sequence (the seven steps) reads 1 to n once each (01 and 1 are the
  same number), with no icon standing in for a number. The plan carries
  `section_tag` and `badge_reads`; the validator checks them, and also
  checks on the pixels that each slice carries a chip: a compact filled
  block in the client's accent colour in the slice's top-left zone.
- W3, valid ratios: a printed ratio label is a valid label. "3:9" (printed
  in two bundled examples; it is 1:3 written unreduced) and any ratio
  outside the skill's list fail by name.
- W4, palette share against the resolved client palette: counted on
  chromatic pixels only, so a grey pixel never counts toward a brand
  colour. A slice must show a chromatic colour of the client's palette
  (at least a quarter of one percent of its pixels), and a chromatic
  pixel that is a blend of that colour with white, black or grey is
  on-brand.
- W8, negative trait: a greyscale, no-colour sheet fails. When the client's
  resolved palette has a chromatic colour, a slice with next to no colour
  anywhere (the "warm grey line work on ivory, no colour fill" style) fails
  W8 by name, even if its greys sit close to a cream or a charcoal in the
  palette. A palette with no chromatic colour has nothing to measure.
- The founder letter stays one continuous reading block (SOP Stage 5),
  never six cards, columns or numbered parts, although bundled sheets 3
  and 4 draw it as six parts; a reviewer scores a six-part letter as a
  W1 defect.

Mockup traits (the same page with nothing left as a placeholder
except genuinely unknown data such as an event date or start time):

- M1: real photography in every slot; zero placeholder slots.
- M2: buttons are filled in the brand color.
- M3: the real logo is placed.
- M4: the copy is the final copy, not structural placeholder copy.
- M5: the mockup matches the approved wireframe section for section
  (same layout, same copy); only the image slots come alive and the
  buttons fill.

Hybrid board traits (one presentation sheet pairing structure and
finished look for a single approval pass):

- H1: all three panels are present on one sheet: the
  mockup-fidelity desktop page, the mockup-fidelity mobile page,
  and a section guide column.
- H2: the section guide matches the mockups it sits beside: numbered
  sections, mini wireframe thumbnails, and typography specs.

### B. Wireframe canon (dialects, confirmed from the bundled set)

One live dialect (B1), one retired dialect (B2) and a guide column. Review
the artifact against B1; a dialect mismatch is a named defect. The look to
follow is the owner's bundled sheets `chatgpt-wireframe-1` (Standard
desktop), `-3` (Long-Form desktop) and `-4` (Long-Form mobile); which sheet
each wireframe request sends is `references/wireframe-build-spec.json`.

B1, photo wireframe (the standard and long-form teaching sheets):

- edge-to-edge on desktop, a single centered column with internal 2-column
  splits on mobile, or a three-column newspaper board for long-form mobile;
- a black title bar carrying the page name; no device frame, legend or
  swatches;
- grayscale photography only, darkened, with white ratio labels, plus one
  accent family for tags and headlines (the bundled sheets measure
  #c8091a to #d90110 because they are drawn in their own brand's red; a
  client's sheet carries that client's primary colour in this role, never the
  example's red);
- two-tone headlines (black then red, or white then red on a black band);
- alternating white and black full-bleed bands;
- a thin red edge bar on most photographs, left or right edge;
- asymmetric alternating 2-3 column rows (text, photo, details), one allowed
  option among the composition treatments, capped by the per-page budget in
  `references/composition-treatments.json` (split at most 40 percent of
  photo-bearing sections);
- pains use "!" bullets or black checkmark circles; benefits use
  checkmarks;
- the 7-step sequence as red circles joined by chevrons or a dotted line on
  the dark band (a vertical black-circle timeline on the long-form mobile
  board);
- gray objection cards beside pains ("This feels familiar:", "You might be
  thinking:", "Sound familiar?"), Who side cards ("AND IT'S ALSO FOR YOU
  IF…" / "NOT FOR YOU IF…"), white icon cards on the black What band, and a
  founder block with a back-view or silhouette photo, letter, script
  signature and gray sidebar;
- CTA strips after persuasion blocks, first-person labels with microcopy;
- absent from the observed set and therefore never invented: testimonials,
  price, order form, FAQ, countdown, logo bar, guarantee block.

B2, grayscale wireframe (the long-form event opt-in): RETIRED as a target
dialect (owner, 2026-10-19). The Set for Life sheet is strictly grayscale
(measured #f6f6f6, #ffffff, #e8e8e8, #242424; saturated-pixel share 0.000%),
with a dark meta bar carrying page width and content width, 2 px outlined CTA
rectangles, crossed-box slots and art-direction briefs in the slots. It stays
in the bundled set as an annotation reference only: its widths header strip
and per-section behavior notes are the written rules W5 and W6, and its look
is not a style. A grayscale sheet fails W8, and the wireframe stages never
attach it as a style reference.

B3, section guide column: numbered rows with thumbnails and type specs;
each row states headline, subheadline, body, CTA and layout with its image
ratio.

### C. Mockup canon (two tiers)

Two tiers exist. Both repeat the copy; they differ in photo density and
decoration. Any trait that fails is a named defect, and a mockup failing M1
fails review outright.

- Tier R (layered, photo-dense): about 9 portraits per page, Black
  professional casting, hand-chin or upward-gaze poses, jewel and earth-tone
  blazers, gold hoops, golden-hour bokeh; shapes bleed out of their frames
  (arches, diagonals); botanicals, monstera and palm, leaf texture, gold
  rules, hairline dividers; rust and green pills with arrow glyphs and
  shadows; script overlays on photos; slogans printed on objects (mugs,
  books).
- Tier H (flat, sparse, same copy): plain-rectangle photography is allowed
  (about 7 photos with 7 content bands photo-free; the composition budget
  still applies to the photo-bearing sections), no botanicals and no
  script on photos (the script moves to a caption bar), square green or
  cream buttons with an arrow glyph and gray microcopy, six cream icon
  cards, rust or peach number badges, hairline dividers and gold left or top
  rules.
- Palette, measured (the canon example set's own colors, a structure and
  tonal-weight benchmark only; a client's mockup is judged against that
  client's resolved brand palette per W4/M2, never against these hexes):
  cream #f7f2e9, ivory #fffdf9, deep green #28513f,
  blush #f0dedb, rose #93504f, brick #bc5248; gold (#c49a45, #e2c98f) is an
  accent only; neither tier uses the wireframe red family. These are the
  canon example set's own colors, a structure benchmark: a client's mockup
  uses the client's colors under the page color system below.
- Page color (hypersaturation): hero color as full-bleed grounds, hard dark
  and light grounds, two-tone heavy headlines, photos graded to the hero
  color (`references/hypersaturation-framework.md`, R1 to R9). Measured with
  `scripts/validate_page_color.py` on the stitched page against thresholds
  derived from the two reference pages; reviewer-judged for ground order,
  divider bands and accent panels.
- Type: a two-tone statement-turn headline (the one exception is an upright
  Title-Case red second line); serif body in the layered tier, sans body in
  the flat tier; tracked-uppercase eyebrows; script overlays and a
  handwritten signature.
- Structure: the mockup matches its approved wireframe section for section
  (M5). The stitched desktop mockup is 1440 px wide; the stitched mobile
  mockup is 780 px (390 CSS px at 2x). The mobile mockup is stacked from the
  same order and copy, never a desktop image resized.

### E. Section order per page type

Section order is part of the trait set. A section out of order, missing or
duplicated is a named defect.

- Sales page: header, 1 Claim, 2 Pain 1, 3 Pain 2, 4 Pain 3, 5 Why, 6 Who,
  7 What, 8-10 Benefits, 11 How-to (7 steps), 12 Founder letter, closing
  CTA. Long form inserts 2A, 3A and 4A after each pain, splits Why into
  named beats, gives the founder letter six beats, and closes with a full
  CTA panel. The live challenge page observed follows hero, why-now-why-you,
  day 1-5 blocks, "deeper than business" band, mastery day cards, founder
  story.
- Opt-in page: 15-band order: header, 1 Claim, 2 Pain 1, 2A, 3 Pain 2, 3A,
  4 Pain 3, 4A, 5 Why (A recognition and reason, B commitment, C
  invitation), 6 Who, 7 What, 8-10 Benefits, 11 How-to, 12 Founder letter,
  footer, with 7 CTAs. Every opt-in example is long-form; no short opt-in
  example exists.
- No example exists for upsell, downsell, thank-you, order form/checkout or
  squeeze pages. Do not invent a precedent for them from the sales or opt-in
  order. The checkout page's five-section structure
  (`references/copy-specs/roles/checkout.json`) is a PROPOSAL built from Skill
  79's own spec, not a precedent from an example, and awaits Trevor's approval;
  its look still comes from the client's brand colours, design style and
  Trevor's wireframe rules.

### F. Generic-versus-Trevor discriminators

Sixteen confirmed discriminators. Score the artifact against the list; a
generic page fails several of them.

1. headline turn (two-tone);
2. twelve named sections, 7 steps, founder letter, no testimonials or FAQ;
3. pains before benefits, each pain answered;
4. layered-tier photo density (about 9 portraits per frame) against
   flat-tier or generic sparseness;
5. consistent casting, pose and styling;
6. gold script on the photo (flat tier: the caption bar); measured, not only
   reviewed, for pages that declare `caption-over-photo` or an overlay: the
   text sits inside the slot's `copy_zone`, clear of `subject_zone`, with the
   contrast in `references/composition-treatments.json` (checks Q2 and Q6);
7. slogans on props (mugs, books);
8. hue-shifting full-width bands;
9. arches and diagonal masks, monstera and palm, leaf texture (layered
   tier); the masks are measured (check Q3: corner patches match the
   section background, computed radius or clip-path agrees with the declared
   `mask-*` treatment);
10. red edge bars plus red offset blocks and bracket frames;
11. varied image ratios with art direction ("never a defeated stereotype");
12. a CTA after nearly every block, first-person outcome labels with
    microcopy;
13. asymmetric alternating rows (one allowed option, capped by the per-page
    composition budget);
14. six icon cards in tinted circles plus peach or rust sequence badges;
15. the four-line brand system reused in header, overlay, props and footer;
16. founder close: portrait, script signature, capitals name and title,
    final CTA.

## Design Board (stage design-board; SPF021)

`scripts/design_board.py validate` is the deterministic floor, run by the stage gate at close
with `--require-approval`. Contract and block list: `references/design-board.md`.

1. Palette on the board is the run's resolved client palette (roles and hex), every printed hex
   is a palette hex, every palette hex is printed, and every palette color is present in the
   board's pixels.
2. The client's logo file is present and unchanged since the board was made.
3. Images are the page's actual section images, re-derived from the run's own artifacts (wireframe
   inventory and section plan, image map, generation files, supplied assets) at every check: same
   slots, files and bytes as recorded; no slot without a real file (no art-direction tile).
4. Every block on the board (required for the page role, plus any optional one declared) is legible:
   each declared text (tagline, caption, tile, cue, label, title line, phrase line, banner second
   line) is in the transcript and the board image itself (read by tesseract, not the caller)
   shows that text, judged per text, not per block; the transcript is supported by the image overall.
5. No foreign client brand text (other clients' names, the example board's words).
6. Not a stub placeholder; the board file is unchanged since it was recorded; the page role matches the run.
7. A recorded client approval (`approved`, approver, evidence, time) bound to the current board, image
   set, palette and page role.

Reviewer criteria (Review Receipt v2, each applicable criterion at least 8): reads as the client's brand;
the logo is faithful, not restyled; each image tile is the page's image and undistorted; spacing and
hierarchy are clean; no garbled or invented text. A palette, logo, image or foreign-brand failure is an
auto-fail.

## Failed-only repair loop

1. Run initial QC.
2. If pass: advance immediately.
3. If fail: record the named defect and affected dependencies.
4. Perform one focused repair.
5. Recheck the repaired artifact and affected dependencies only.
6. Repeat only if still failed.
7. Stop after the third focused repair attempt and report the exact blocker.

Do not rewrite unrelated passing material. Do not perform three ceremonial re-reviews of unchanged passing work.

## Independent review

Where the workflow calls for independent QC, use a separate reviewer/pass that evaluates the artifact rather than merely accepting the builder's self-assertion. A writer or generator cannot invent an independent-review credential.

## Review Receipt v2 (the only format)

Scores never live in a stage receipt. Every reviewed item carries one file,
`private/reviews/<stage>/<item-id>.review.json`, created only by
`scripts/write_review.py` running inside the reviewing session. The writer
stamps the reviewer session from the environment, computes the artifact
SHA-256 itself, and refuses any criterion note under 40 characters. Every
review also carries the SOP's evidentiary fields: `automatic_failures`,
`repair_attempt`, `specific_defects`, `performed_check`,
`next_current_artifact`, and `independent_review`. If the environment
cannot name its reviewing session, the writer still writes the file with
`reviewer_session` recorded as `UNKNOWN` and `independent_review` false:
the limitation is reported, never simulated (Amendment 6, Item 2 delta).
At close, `scripts/stage_gate.py` verifies, per item: the review file
exists, its hash still matches the artifact on disk, `reviewer_session`
differs from both the review's `author_session` and the stage receipt's
author session, neither session is empty or a placeholder (an `UNKNOWN`
reviewer session is the recorded limitation above, not a placeholder
failure, and is never independent), the verdict is `pass`, the
evidentiary fields are present and valid, no automatic failures are
recorded, and every criterion meets the stage's `min_scores` per
artifact: each criterion at or above `each`, and where the contract sets
`average`, that item's own criterion mean must reach it (cross-file
pooling is not allowed; Amendment 6, Item 12 delta). A receipt that
still carries v1 `scores` fails close with a migration message. REPORT.md
stamps the run's review mode (INDEPENDENT / SELF-REVIEWED / UNKNOWN) from
these files; a run cannot argue with its own stamp.

## Named review criteria (data, provisional)

Criterion lists live here and in `references/stage-contract.json`, not in
gate code, so they can be corrected without a code change. The lists below
are PROVISIONAL pending the plan's Amendment 6 full-read corrections.

Visual design stages (`visual-mockup`, `final-mockups`), one review per
covered part, one for the stage's `mockup.html` (item `mockup`), and, for
`visual-mockup`, one per page visual bible file (item `page-visual-bible`
when only one bible file exists; `page-visual-bible-json` and
`page-visual-bible-md` when the JSON and markdown bibles are both
present):

- `composition_fidelity` (composition fidelity to wireframe)
- `brand_token_discipline` (brand token discipline)
- `banned_pattern_absence` (banned-pattern absence; until layout metrics
  automate the ban, this criterion is where it lives, with evidence notes)
- `section_rhythm_variety` (section rhythm and variety)
- `image_slot_integrity` (image-slot integrity)

Final-mockups stage (`final-mockups`) only, one review per covered
part and one for the stage's `mockup.html` (item `mockup`): the
mockup trait criterion binds only at the single client-judged mockup
stage (Update Plan Item 5, Decision 2 option (i)). It is never
scored at `visual-mockup`: that stage's layout proof is an internal
production artifact whose image slots are solid blocks by design, so
scoring it against the mockup traits would fail a correctly built
layout proof.

- `mockup_trait_fidelity` (Item 14: the mockup traits M1 to M5 in
  "Visual standard set traits" above, scored with the bundled
  standard set at `assets/visual-standards/` open beside the
  artifact; any placeholder slot is an M1 failure and an automatic
  failure of this criterion; where the stage produces the hybrid
  board, traits H1 and H2 are scored under this criterion as well)

Generated images (`image-generation-qc`), one review per generated file,
under the per-artifact rule: each file's own criterion mean must reach
the contract average of 8.5, every criterion must be at or above 8, and
no automatic failures may be recorded; a strong file cannot carry a
weak one:

- `scene_match` (scene match to prompt)
- `cast_expression` (cast and expression)
- `skin_hair_fidelity` (skin and hair fidelity)
- `grade_fidelity` (grade fidelity)
- `composition_slot_fit` (composition and slot fit)
- `text_logo_correctness` (text and logo correctness)
- `anatomy` (anatomy)

Prompt files (`image-inventory-prompts`) are reviewed per file under the
same per-artifact rule and the same 8.5 per-file average.

Wireframe stages (`desktop-wireframe`, `mobile-tablet`), one review per
covered part. The criterion list for these stages was not named anywhere
in the pre-build skill; the entry below is added at integration per S3's
gate-change Request 6 (Item 13), verbatim, and the list is otherwise
still provisional:

- `reference_fidelity` (fidelity of structure, spacing rhythm, and
  alignment to the run's selected layout reference; score 10 only when
  the correspondence is structural, not merely thematic; when the
  reference set is waived at intake, score against the brand file's
  layout thresholds and record the waiver in the note)
- `wireframe_trait_completeness` (Item 14: the wireframe traits W1
  to W7 in "Visual standard set traits" above, scored trait by trait
  with the bundled standard set at `assets/visual-standards/` open
  beside the artifact; the criterion note names each trait's verdict,
  and a missing annotation (W1, W2, W5, W6), an unlabeled slot
  (W3), a skipped or repeated number (W1), an invalid ratio label
  (W3), a palette that is not the client's (W4) or a greyscale
  no-colour sheet (W8) is a named defect, never a general impression)

## Graphics department hooks (SOP-GIP-02, Skill 83 lane)

Skill 71's generated images are external client deliverables, so the Graphics department's image QC applies to them. The automatic-fail list is kept as data in `references/stage-contract.json` under `graphics_autofails` (code, name, summary), and this table mirrors it for readers. Any hit is a FAIL regardless of the average, and `scripts/write_review.py` refuses a `pass` verdict that cites one.

| Code | Automatic failure |
| --- | --- |
| AF-G1 | garbled or misspelled baked text (pixel-vs-copy parity) |
| AF-G2 | logo mutated, recolored or invented mark |
| AF-G3 | legibility or contrast failure on a key text element |
| AF-G4 | anatomical artifact (fingers, limbs, face geometry) |
| AF-G5 | placeholder or bracket token rendered as visible text |
| AF-G6 | brand palette drift beyond the brand file's tolerances |
| AF-G7 | demographic default, mono-cast or skin-tone fidelity failure |
| AF-G8 | provenance gap: no generation receipt tying the pixels to the sanctioned KIE route |

Four hooks make the list enforceable:

1. **Independent reviewer model.** `write_review.py --author-model M1 --reviewer-model M2` (or `--require-model-independence`) marks the review independent only when both models are named and differ. An unnamed model counts as not independent. The reviewer is never the model that wrote the prompt.
2. **Text read-back.** `validate_production_record.py --ocr` reads each section image with the Design Board's own reader (`design_board.ocr_text`, tesseract) and fails a section whose recorded read-back is not supported by the pixels (AF-G1), or whose expected copy is not visible.
3. **Logo accuracy.** A section that declares `logo_expected: true` must carry a `logo_check` record (`logo_ref`, `method`, `verdict`). A missing record or a verdict other than `pass` fails the section (AF-G2).
4. **Text-capable model and PNG.** The paid route refuses a model that cannot render readable text (nano-banana and seedream classes) for wireframe and mockup sections, and refuses a saved file that is not a real PNG.
