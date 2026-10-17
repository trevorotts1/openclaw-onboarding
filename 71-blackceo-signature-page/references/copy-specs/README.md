# Copy specs: how copy_version selects one guide, one spec, one criteria extract

FIX-PLAN Item 19 (as amended by Amendment 6, Part D). This directory holds
the machine-readable copy specs extracted from the two v6 copy guides
(Item 17) and the emotional-quality extracts the reviewer scores against.
The validator that enforces the specs is
`scripts/validate_copy_structure.py` (Item 18).

## The selector: one field, one version, no mixing

Every run's intake record (`intake.json`, written by `write_intake.py`)
carries a required field:

    copy_version: "standard" | "long-form"

That single field selects exactly one row of this table. Nothing else in
the run may mix versions: a Standard run never opens the Long-Form guide,
and a Long-Form run never inherits a Standard rule (the Standard's
per-step character bands are the standing example: they apply to Standard
only, and the Long-Form spec records them as explicitly not applied).

| copy_version | Author writes from | Validator spec | Reviewer scores against |
|---|---|---|---|
| standard | `references/BlackCEO-Signature-Landing-Page-Standard-v6.md` | `references/copy-specs/standard-v6.json` | `references/copy-specs/standard-emotional-quality.md` |
| long-form | `references/BlackCEO-Signature-Landing-Page-Long-Form-v6.md` | `references/copy-specs/long-form-v6.json` | `references/copy-specs/long-form-emotional-quality.md` |

How the selection is written: `write_intake.py --copy-version
{standard,long-form}` records `copy_version` in `intake.json`, and the
intake gate fails closed when the field is missing (no default version is
ever assumed). The stage contract then resolves the copy stage's reads
and validator arguments from that field. Both wirings are requested in
this stream's CHANGE-REQUESTS.md; they land with the S1 contract stream,
not in this tree.

## Reads by role (the one-guide rule is layer-scoped)

- Author (copy writer): the Brand Law plus the ONE selected guide. Not
  the other version's guide, not the SOP, not the Image Guide.
- Reviewer: the selected spec, the selected emotional-quality extract,
  the internal manuscript, and the public copy. The emotional-quality
  extract is a reviewer read, not an author read: without its criteria
  text in front of the reviewer, the 8/10 per-section scoring law in the
  spec's `procedural_law` block has nothing to score against.
- Other layers keep their own documents: the Production and QC SOP and
  the Image Guide v5 remain linked documents for the production and image
  layers. The one-guide rule governs the copy layer only; it does not
  unlink the SOP or the Image Guide from their own stages.

## Fallback for runs that predate the field

A run directory created before Item 18 landed may have no `copy_version`
in its intake record. For those runs only:

- The copy stage lists BOTH guides in its reads and prints a warning
  naming the missing field and the fallback.
- No validator spec is auto-selected: `validate_copy_structure.py`
  always takes its spec as an explicit `--spec` argument, so a fallback
  run must name the spec by hand until its intake is re-recorded.
- New runs never take this path: the intake gate fails closed without
  the field. (Gate and reads-resolution behavior are owned by the S1
  contract stream; see CHANGE-REQUESTS.md.)

## What the specs contain

Each spec JSON carries, with a guide source anchor on every value:

- `counting_convention`: what counts and what is excluded, the word
  tokenization, and the character-counting rule. The validator implements
  exactly this convention; it is verified against the guides' own
  measured examples (81 lesson examples plus both assembled path B
  manuscripts reproduce the published counts exactly; fixtures live in
  `tests/fixtures/copy_examples/`).
- `sequence` and `sections`: the section order, each section's job, and
  its limits. Every limit carries its `unit` (`words` or `chars`) and a
  `kind`: `hard` (a validator failure), `target` (guidance; a warning,
  never a failure), or `descriptive` (an editorial aid the guide states
  is not a limit; never checked). Standard lengths are mostly hard law;
  Long-Form lengths are suggested working ranges, so they are `target`
  and a material change is documented in the non-public QC note instead
  of being padded away.
- `cta_map`: required standalone positions, forbidden standalone
  positions, and the exact total (Standard 6, Long-Form 7). Section 5 is
  one family with a single module at its end, never one per panel. The
  Long-Form Section 12 invitation is prose inside the letter (plus an
  optional contextual link), never an eighth module.
- `containment`: 5A/5B/5C are optional children of Section 5 with one
  family total; 7A/7B/7C are internal labels inside Section 7; visual
  panels (`Section N / P01`) and export parts are not sections and never
  trip the no-extras rule. Long-Form Section 7 carries two declared word
  bands (compact, expanded six-card); the validator accepts either and
  never invents a third.
- `founder_letter`: the six required internal parts of Section 12, in
  order, with their per-part allocations nested inside the section total.
- `procedural_law`: per-section criterion scoring at 8/10 or better, an
  overall score may not conceal a weak section, failed-only repair,
  maximum three attempts, deviation notes in the non-public QC note, and
  the anti-requirement that no independent claim audit may be added
  (claim verification belongs to the human reviewer).
- `qualitative_rules` and `emotional_quality_criteria`: the either/or
  and judgment rules, kept as data (`kind: "qualitative"` or
  `"conditional"`) so nothing the guide requires is silently dropped.
  The validator runs only their mechanical prefilters and emits FLAG
  lines for the reviewer; it never fails a run on a judgment call.

## Maintenance rule

Numbers in these specs change only by re-extraction from the guide text,
followed by Trevor's spot-check (the Item 17 acceptance gate). If a guide
changes, re-run the fixture tests: the guides' published counts are the
contract, and a fixture failure means the spec or the counter is wrong,
never that the fixture should be adjusted to fit.

Open extraction flags:

- F1: the Standard guide concentrates Section 5's three movements into
  the single Section 5 limit and never states the status of labeled
  5A/5B/5C panels as cleanly as the Long-Form guide does. The Standard
  spec therefore accepts optional children under the family total (the
  reading that cannot reject a guide-legal manuscript) and says so in
  its containment note. Trevor's spot-check may tighten this.
