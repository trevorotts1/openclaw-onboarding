# Signature grade gold set (Skill 71, Item 8)

This folder holds Trevor's accepted anchor images: calibration anchors
and validation for the documented look. The look itself is defined by
the governing documents (the image guide, the Secret Sauce, the style
libraries); these images anchor the grade screen's numbers to that
look and validate them. Floors are derived from these images, never
invented.

## Status

EMPTY on purpose. Trevor supplies accepted anchor images (5 to 10 per
family and posture class he wants certified; plus, if handy, 3 to 5
known-bad ones, which live OUTSIDE this folder and are passed to the
calibrator with `--bad`). Until the images land and Trevor approves the
proposed floors, the brand file's grade thresholds stay null and
production image stages cannot close (that block is the gate's Item 8
close rule).

## Calibration is per family and per posture class

Calibration Redesign (Rulings 1 and 2, 2026-10-14):

- Floors are derived per rendering family (photographic, cinematic,
  visual-artist) and per posture class (the entry's recorded
  hero_color_chroma blend mode). The old pooled brand-level floor is
  gone: pooling dragged the floor toward the pool's most muted cases
  and under-tested the full-strength look.
- FULL class: color floors (saturation, colorfulness) from that
  family's FULL anchors only, 5th percentile x 0.95, minimum 4
  anchors. Fewer is refused by name; no floor is derived from less.
- ADAPT class: a two-sided band, not a floor and not N/A (saturation
  and colorfulness each get a lower and upper bound, plus a luma_std
  tonal floor: Guide section 13, check 1). 4 or more anchors make a
  binding band; 1 to 3 print as PROVISIONAL and the class stays
  uncalibrated (the screen WARNs for it); 0 anchors derive nothing.
- SUPPRESS class: no color floors or bands, ever (Guide section 13).
  SUPPRESS anchors still anchor their family's non-color floors.
- Non-color floors (luma_std, sharpness) are computed per family,
  pooled across all of that family's anchors, minimum 4.
- The mandatory restrained case (Amendment 6 validity rule: at least
  one definingly monochrome or restrained-style entry) lands in the
  ADAPT or SUPPRESS class by construction, so it can never drag the
  FULL floors down.
- Family span is REQUIRED (Ruling 2): brand calibration needs anchors
  for every family the brand uses. The used families are declared in
  the brand file's `grade.families_used`, or at the top level of this
  manifest as `families_used`; absent both, all three Router families
  count as used. A set that cannot derive a floor set for a used family
  is refused, naming the family. There is NO family-scoped calibration
  mode: a partial set certifies nothing. One exception exists at
  designation: a family whose governing posture is not FULL may be
  recorded under the manifest's top-level `family_exceptions`, and it
  then derives from its governing class.
- Option B (Ruling 3): the calibrator also proposes, per family, a
  protected-region saturation ceiling from the FULL anchors (95th
  percentile x 1.05). A ceiling has been approved and written
  (0.3660, Decision 14 write-in), and the metric remains WARN-only
  under the owner's Resolution A ruling (S71-OPTION-B, 2026-10-16):
  an image measuring over the written ceiling warns and never fails
  on this metric; the Item 12 judgment gate remains the enforcement
  of record for selective saturation.

## Manifest format: gold-set.json

`gold-set.json` sits in this folder and lists every gold image:

```json
{
  "families_used": ["photographic", "cinematic", "visual-artist"],
  "images": [
    {
      "file": "gold-01-hero.png",
      "source_page": "Name or URL of the accepted page this image ran on",
      "approved_by": "Trevor Otts",
      "date": "2026-10-13",
      "active_family": "photographic",
      "style_case": "full-color hero portrait",
      "blend_profile": {"hero_color_chroma": "FULL"}
    }
  ]
}
```

Rules for entries:

- `file`: the image's filename inside this folder. PNG, JPG, or WebP.
- `source_page`: where the image was accepted (page name or public
  URL), so a future reader can see the context the approval happened
  in.
- `approved_by`: who approved it as gold. Calibration gold is approved
  by Trevor Otts; an image nobody approved does not belong here.
- `date`: the approval date, ISO format (YYYY-MM-DD).
- `active_family` (REQUIRED): one of `photographic`, `cinematic`,
  `visual-artist`, the family the Page Art Direction Router assigns.
  The calibrator refuses an entry with a missing or unknown family,
  naming it: calibration is per family, and an anchor with no recorded
  family cannot be placed.
- `style_case` (REQUIRED): free text naming the case the anchor
  represents (for example "full-color hero portrait", "monochrome
  restrained case"). The restrained-case validity rule reads this
  field.
- `blend_profile` (required for color-floor calibration): the entry's
  recorded Secret Sauce Blend Profile, a dict of dimension to FULL,
  ADAPT, or SUPPRESS. The posture class is the recorded mode of
  `hero_color_chroma`. An entry WITHOUT a blend profile is posture
  class UNRECORDED: it is excluded from every color-floor computation,
  listed by name in the calibrator's output, and still contributes its
  non-color measurements to its family. Postures are recorded, never
  assigned by inspection after the fact.

The file currently in this folder is the empty format scaffold:
`{"images": []}`. `scripts/calibrate_grade.py` refuses to calibrate
from an empty manifest and says why.

## Calibrating

```
python3 scripts/calibrate_grade.py \
  --brand assets/brand/blackceo-brand.json \
  --gold assets/brand/gold-set \
  [--bad <folder of known-bad images>]
```

The script measures every gold image with the exact code the grade
screen runs, prints the table, and proposes each family's floors per
posture class. It proposes only; it never writes the brand file.
Trevor approves or adjusts the numbers, and only then are they written
into `assets/brand/blackceo-brand.json` by hand (nested `grade.floors`,
with the photographic FULL floors mirrored to the legacy flat keys),
with the calibration date and this manifest's SHA-256 recorded in the
brand file's calibration record (see `assets/brand/brand.schema.json`,
grade block).

## Changing the gold set

Adding or removing a gold image changes what the floors mean. Any
change here requires a fresh calibration run and Trevor's approval of
the new floors, recorded the same way. Do not quietly swap an image.
