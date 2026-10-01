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
