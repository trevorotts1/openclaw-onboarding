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
outright. Deterministic gate enforcement of these traits (the
wireframe annotation, slot-label, and brand-color checks, and the
mockup placeholder-slot gate check) is Item 15 and is not part of
this section; until it lands, these traits bind through review.

Wireframe traits (a designed, annotated build spec rendered as an
image, in the client's brand colors):

- W1: every section is numbered and named against the 12-section
  standard.
- W2: type specs are printed on the sheet (H1, H2, body, and CTA
  sizes, desktop and mobile).
- W3: every image slot is a deliberate placeholder (a
  black-and-white photographic plate or a crossed box), labeled with
  its aspect ratio AND its art direction (what the image must show).
- W4: the sheet is rendered in the client's brand colors.
- W5: a header strip states the page width and the content width.
- W6: behavior notes are printed per section (for example "CTA
  before portrait on mobile", "No CTA", "Typography-only response").
- W7: CTAs are shown as designed chips carrying the real button text
  and microcopy specs, and copy is the run's real copy where it
  exists.

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
  and a missing annotation (W1, W2, W5, W6) or an unlabeled slot
  (W3) is a named defect, never a general impression)
