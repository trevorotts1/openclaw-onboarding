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

Retain the stricter Graphics threshold:

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

## Residual judgment (Amendment 6, Part B6)

After the mechanical checks above, the following remain judgment, and no part of this skill may claim mechanical coverage for them:

1. whether locks and anchors are VISIBLY DOMINANT in the rendered image, the libraries' own pass standard, which no text defines a measurement for;
2. abstract anchors and properties a still cannot show (dignity, emotional attachment, social legibility, moral pressure; sequence-level properties such as montage and camera movement inside one shot);
3. process traits unverifiable from output (UV fluorescence in VDL-048, wet-plate process in VDL-029, collaborative authorship in VDL-014), where an output can mimic the appearance without the process;
4. stated parameters unrecoverable from a finished image (subject-to-backdrop distance in VDL-005, sun angle in VDL-015);
5. the copy guides' emotional-quality criteria, which are not a closed list in either guide;
6. the libraries' own production-ready claims, which rest on per-style QA scores (at least 8.0 of 10 on ten dimensions) that are published NOWHERE, making the claim unfalsifiable from the artifacts.

Mitigations, the strongest available: independent review under Item 2's receipt machinery as the floor for every judgment item; the per-style gate rubrics as the review FORM, so judgment is exercised against the style's own criteria rather than a generic impression; and this list, printed here so the coverage is never mistaken for total.

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
