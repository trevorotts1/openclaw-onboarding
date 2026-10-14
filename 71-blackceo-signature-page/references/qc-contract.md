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

Two screen checks are unconditional and need no threshold: near-duplicate detection (8x8 average hash; a pair at Hamming distance 4 or less fails as a possible duplicate or near-identical shot, unless the pair is declared in the inventory's `continuity_group` as an intentional continuity series) and aspect-ratio truth (an image's actual ratio must match its inventory slot ratio within 2 percent, checked when the validator is given `--inventory`).

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
