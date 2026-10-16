# Placement and Layout Variants

How one motion job becomes several destinations without lying about
any of them. This is the doctrine behind `runtime/src/layout/`
(Directive MG-014). It consumes two earlier layers and adds nothing
to them: type is measured by the typography layer
(`references/typography-and-layout.md`, MG-013) and image crops are
solved by the compositing layer (MG-012). Data scales come from the
chart layer (MG-015).

## One content record, one layout record per destination

A job's message, data, and assets are stored ONCE, in the shared
content record: the headline, support copy, call to action,
disclosure, the chart dataset, and the image with its focal point
and protected regions. Nothing destination-specific lives there.

Every destination carries its OWN layout record:

- `powerpoint_full_slide`: the graphic fills the slide.
- `powerpoint_inset`: the graphic sits in a declared box on a slide
  that carries other content.
- `vsl_desktop`: the 16:9 desktop VSL canvas.
- `vsl_mobile`: the 9:16 mobile VSL canvas.
- `standalone`: a standalone video, 16:9 or 9:16 as declared.

A layout record holds the arrangement (rows, columns, or staged
rows), the plot geometry, every text element's role, size, and box,
the image placement box, the safe-area profile, and the placement
(full-frame, or an inset with a declared display size). Text
elements REFERENCE the shared copy (a field, a row label, a row
value); they never restate it. Two destinations can never quietly
drift into telling two different stories, because there is only one
story to tell, and a variant that drops a category, a value, or the
headline fails resolution: dropping part of the message is not a
recomposition.

## Recomposition, not cropping, not scaling

A vertical destination is composed for the vertical canvas. The
resolver proves this geometrically: a mobile variant whose
arrangement, element boxes, plot, and bar thickness all match the
desktop variant under one uniform scale is rejected as
`LAYOUT_SCALED_DUPLICATE`. Renaming the arrangement does not help;
the boxes are what is compared. A genuine mobile variant differs
materially: rows stack under their labels, the plot is re-derived
for the narrow canvas, or complex information is staged across
beats.

Staging is the standard answer for comparisons that do not fit a
vertical frame side by side. A three-column comparison becomes
three beats, one column per beat, at full readable size
(`staged_rows`, each slot naming its beat). Every row of the shared
dataset must appear in some beat; staging spreads the message
across time, it never drops parts of it.

Center-cropping a landscape composition into a vertical frame is
not a variant. Images are handled the same way: each variant solves
its own crop around the asset's focal point and protected regions
through the compositing solver, so the subject that matters
survives in both ratios by construction, and text is then checked
against the protected regions as they actually land in that
variant.

## Comparable data scales

Variants of one message keep ONE data scale contract. The domain
and scale type come from the shared dataset (MG-015), and the same
value must land at the same fraction of the plot extent in every
variant. Pixels per unit legitimately differ: the reference chart
job maps its [0, 30] domain across 1200 px on desktop (40 px per
unit) and 740 px on mobile (about 24.67 px per unit), and the
values 12, 18, 30 sit at 0.4, 0.6, 1.0 of the extent in both.
What may not happen is a variant quietly re-domaining the data so
the same bar means something different on the phone than on the
desktop. The resolver checks the normalized positions numerically
and reports `LAYOUT_SCALE_NOT_COMPARABLE` on any drift.

## Safe areas come from the player, not from habit

Every variant names a safe-area profile: a measured record of the
zones the destination's own chrome will occupy. A desktop VSL
composes on a clean full frame. A mobile VSL composes for its
PLAYER: the registered player profile carries a caption band
(1080x1920: y 1660 to 1920) and a title chrome strip, because that
is where the player's captions and title render. A webinar overlay
profile carries the presenter picture-in-picture and the
lower-third band.

A social-platform controls profile (action rail, platform caption
zone) exists only for destinations that declare platform delivery.
Applying it to an ordinary mobile VSL is refused
(`LAYOUT_PROFILE_NOT_APPLICABLE`): social chrome is not drawn on
every phone screen, and composing around controls that will never
appear wastes the canvas and distorts the layout. Any text element,
the plot, or the image box intersecting a profile's unsafe zone is
a finding (`LAYOUT_UNSAFE_ZONE`), with the overlap measured.

## The placement audit: judged at the size it will be seen

Resolving a variant proves the composition is honest. The placement
audit proves it is legible where it will actually play. For each
variant the audit:

1. Computes the placement facts: full-frame, or an inset's display
   size. Inset sizes may be declared in pixels, or in millimetres
   converted through the slide's own pixel-per-millimetre ratio
   (a 169.333 mm box on a 338.667 mm wide, 1920 px slide is a
   960 px box). No display DPI is ever assumed.
2. Measures every text element with the actual font through the
   typography audit at its EFFECTIVE size: authored size times the
   placement scale. Role floors never shrink to meet a small
   placement.
3. Solves the image crop for the variant's own image box and maps
   the protected regions onto the canvas, so text is checked
   against the face or proof region as it will appear in this
   variant.

The acceptance consequence is deliberate: a PowerPoint graphic
that passes full-frame can still fail as an inset, and it must.
The reference fixture authors its headline at 128 px, comfortably
over the 96 px headline floor full-frame; placed as a 960x540
inset (scale 0.5) the headline's effective size is 64 px and the
audit fails it with `TYPO_BELOW_FLOOR`. "It was readable in the
original render" is not a placement result.

## The 16:9 export rule

An export keeps its own aspect regardless of the slide layout it
sits in. A 16:9 motion graphic placed inside a slide layout is
still a 16:9 file; the placement declares where it sits and how
large it displays, and never rewrites what it is. Each variant
therefore declares its export aspect, and the resolver refuses a
record whose export aspect disagrees with its canvas
(`LAYOUT_EXPORT_ASPECT`). Canvases follow Section 4.1: PowerPoint
and desktop VSL are 16:9, mobile VSL is 9:16, and a standalone
declares one of the two.

## Where things live

- Model, validation, resolver, audit: `runtime/src/layout/`
  (`types.ts`, `validate.ts`, `profiles.ts`, `resolve.ts`,
  `audit.ts`).
- Profiles are data with their source stated in the record; a new
  player or overlay profile is a new record, not a code change.
- Fixtures: `tests/fixtures/layout/` (passing desktop and mobile
  chart variants, a scale-only mobile variant, the PowerPoint
  inset case in pixels and in millimetres, a caption-band
  violation, a staged three-column comparison, an image-led job).
- Pinned expectations: `tests/evidence/mg014/measurements.json`.
  The suite fails on drift; it never rewrites the record.
- Suite: `runtime/tests/run-layout.ts`, chained last in
  `npm test`.
