# Typography and layout: role-based hierarchy with measured placement

Directive: Section 6, MG-013. Machine-readable tokens: `references/typography-tokens.json`.
Measurement utilities and the rendered-layout audit: `runtime/src/typography/`, exercised by
`runtime/tests/run-typography.ts` over fixtures in `tests/fixtures/typography/`.

This document replaces the tiny-type era of Skill 72. A 28-pixel minimum at 1080p was a
floor a designer could hide behind: it said nothing about hierarchy, nothing about the
size a viewer actually sees at the destination, and nothing about what to do when copy
does not fit. The system here answers all three. Typography is assigned by role, sized
from the role table, measured with the actual font at the actual destination, and
overflow is resolved by editing copy, never by shrinking it into illegibility.

## The role hierarchy

Every text element in a layout declares exactly one role. The role states what the text
is for; the size follows from the role, not from what happens to fit in the leftover
space.

| Role | Full-frame range (1920x1080) | Floor | Essential |
| --- | --- | --- | --- |
| headline | 96-160 px | 96 px | yes |
| hero_number | 180-300 px | 180 px | yes |
| essential_support | 54-72 px | 54 px | yes |
| cta | 72-110 px | 72 px | yes |
| chart_category_label | 54-72 px | 54 px | yes |
| chart_value | 60-96 px | 60 px | yes |
| disclosure | 40-54 px | 40 px | yes, under the disclosure-small-print exception |
| axis_tick | 28-40 px | 28 px | no, exception role |
| caption_metadata | 28-44 px | 28 px | no, exception role |
| decorative_label | 24-48 px | 24 px | no, exception role |

These ranges are BlackCEO design defaults for motion graphics composed at the
1920x1080 reference canvas. They are not universal accessibility standards and must
never be quoted as such. They are starting sizes for full-frame work: a headline starts
inside 96-160, it does not start at 40 and grow if someone complains.

The chart roles are chart-internal: inside a chart, the headline carries the message
and the labels and values are read as part of the data. Their floors are calibrated so
the shipped C05 design record (headline 112, label 60-64, value 64-72, disclosure 48)
passes its own audit. The disclosure role exists because honesty lines are small print
by convention; its exception below bounds exactly what it may carry.

The motion grammar (references/motion-grammar.md, masked-word rule 5) names the
hierarchy informally as display, headline, body, and caption. The mapping is: display
is hero_number and headline in display usage, body is essential_support, caption is the
nonessential label roles (caption_metadata, axis_tick, decorative_label). The tokens
file is the canonical table both documents point at.

Above-range sizes are a warning, not a failure: a hero moment may legitimately exceed
the band, and the reviewer decides. Below-floor sizes for essential roles are failures,
full stop. When fonts have different cap heights or narrow counters, the reviewer may
demand a larger size than the default for the same role; the audit reports cap height
with every measurement so that judgment has numbers behind it.

## Exceptions discipline

Exceptions exist for nonessential labels, and each one is named, bounded, and recorded
in the tokens file:

- axis-tick-labels: axis graduations may sit below the essential floors only when every
  value they show is also carried by a chart_value, a chart_category_label, or an axis
  title at an essential size. A tick may never be the sole carrier of a needed value.
- metadata-captions: caption_metadata may carry only metadata: timestamps, source
  attributions, slide numbers, speaker names. The moment it becomes a claim or an
  instruction, it must be re-roled.
- decorative-only: decorative_label is pure ornament and carries no information. If
  removing it would remove information, it is mis-roled.
- disclosure-small-print: disclosure may carry only the honesty or source line for the
  data shown. It may never carry message copy, a claim, or an instruction.

An exception role is never a way to make essential copy smaller. Copy the planner marked
essential (MG-009 essential_text) must land in an essential role at an essential size.
Exception roles are still measured and still have floors: small is a bounded
convention, not an exemption from measurement.

## The effective-size rule

A size is judged where the viewer sees it, not where the author typed it.

- Full-frame placement: the authored size on the destination canvas is the effective
  size.
- Recomposed placement (mobile, portrait): the layout is re-authored on its own
  canvas, and the authored sizes on that canvas are judged directly against the same
  floors. Recomposition earns legibility by choosing sizes that meet the floors on the
  destination canvas, not by inheriting a passing grade from the landscape original.
  The shipped portrait design holds its headline at 112 px on the 1080-wide canvas for
  exactly this reason.
- Inset placement (a 16:9 graphic placed inside a larger slide or page): the effective
  size is the authored size multiplied by destination width over source canvas width.
  A 112 px headline inset at half width renders at 56 px and fails the 96 px floor,
  even though the source file "passed". The floor never scales down to meet the
  placement.

CTA and chart elements are audited at their destination size in every mode. A chart
label that is legible in the authoring file and illegible in the placed deck is an
illegible chart label.

## The overflow law

If essential copy cannot fit above its role floor, shorten it or split it. Never solve
overflow by indefinite shrinking.

The fit decider (runtime/src/typography/fit.ts) returns exactly one of three outcomes:

- fits: the copy fits inside its box at a size inside the role band (the search starts
  at the requested size and may settle lower inside the band, never below the floor),
  with measured line breaks, box dimensions, and cap height.
- below_floor: the copy would fit only under the role floor, within a near miss of it
  (a shrink of at most a quarter). This is a failure report with the would-fit size as
  evidence, not a size anyone may use. A copy that only fits after a deeper shrink is
  not a near miss; the restructure path decides it.
- restructure_required: the copy cannot be saved by size at all. The decider names the
  viable path: split, when the copy at floor size fits inside two sequential boxes or
  beats; shorten, when even that cannot hold it (including a single unbreakable word
  wider than the box at floor size).

The decider is structurally incapable of returning a shrunk below-floor size as a
solution: its result type has no field that could carry one. Shrinking inside the legal
band is normal design work; shrinking below the floor is the failure this item exists
to remove.

## The substitution law

The requested family and weight must be the family and weight that render. Measurement
parses the actual font binary the job names: units per em, per-glyph advance widths,
cap height, and weight class all come from that file's own tables. If the file is
missing, if its internal family name does not match the request, or if its weight class
does not match the requested weight, the audit reports a named finding
(TYPO_FONT_MISSING or TYPO_FONT_SUBSTITUTED). It never measures with a fallback font and
calls it the requested one. This is the same discipline MG-006 established for render
fonts: substitution is forbidden, and a font problem is a loud failure, not a quiet
approximation. Pair kerning (GPOS/kern) is intentionally not applied: un-kerned advance
sums are the conservative, wider estimate, so a fit decision made on them is safe.

## The rendered-layout audit

The audit consumes a layout record: a canvas, the font request (family, weight, file),
declared protected areas, and text elements with role, copy, size, box, and placement.
It measures every element with the actual font and reports structured findings:
TYPO_BELOW_FLOOR (effective size under the role floor), TYPO_CLIPPING (a line wider
than its box, or wrapped text taller than its box), TYPO_PROTECTED_CONFLICT (a text box
intersecting a declared protected area: faces, logos, and proof detail stay clear of
text), TYPO_FONT_MISSING, TYPO_FONT_SUBSTITUTED, TYPO_MISSING_GLYPH (a codepoint the
font has no glyph for), TYPO_UNKNOWN_ROLE, plus warnings TYPO_ABOVE_RANGE and
TYPO_LOW_CAP_HEIGHT (cap-height ratio under 0.60, the point where the reviewer should
demand a larger size for the same role). Every measurement in the audit output carries
the measured line widths, the line count, the cap height in pixels, and the effective
size, so a reviewer can see the numbers instead of trusting a verdict.

The fixtures under tests/fixtures/typography/ are the worked examples: three passing
layouts (full-frame, inset that still passes at effective size, recomposed mobile) and
the failure shapes T07 names (long copy, missing font, small placement, clipping,
overlap), each isolated to the finding it exists to prove.
