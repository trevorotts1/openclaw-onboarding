# Composition patterns: how a section's photo and words relate

Read this with `references/composition-treatments.json` (the data: every
sentence, CSS rule and threshold named here lives there and nowhere else) and
`assets/visual-standards/reference-catalog.json` (hosted example images by
type).

## The problem this fixes

AI designs default to one layout for every section: a rectangular photo in one
column and the words in the other. Real pages, Go Full Page among them, also:

1. set a headline, a caption or a short block of copy directly ON a photo;
2. crop photos into circles, arches, pills and angled shapes, not only
   rectangles;
3. run a very light image or pattern behind the words, the full width of the
   screen, edge to edge.

GPT Image 2.5 does none of this unless the prompt names it. The wireframe has
to carry it too: a pipeline that obeys "the mockup matches the wireframe"
erases anything the wireframe never drew. So the treatment is data, set once
per image slot at the wireframe and carried unchanged to the HTML.

## The vocabulary (one treatment per image slot)

| id | family | what it is |
|---|---|---|
| `split` | baseline | photo column beside text column. The AI default; at most 40 percent of photo-bearing sections |
| `overlay-light` | words over image | full-bleed photo; headline and short copy on a flat, bright copy zone |
| `overlay-dark-scrim` | words over image | full-bleed photo; light type on a dark scrim |
| `caption-over-photo` | words over image | eyebrow, script accent or 3 to 8 word caption on a quiet corner |
| `band-over-texture` | words over image | full-width band, dark photo or fabric behind light type |
| `band-light-field` | light background | full-width very light image or line-art field behind type |
| `card-overlaps-photo` | intersecting | text card sits partly on the photo, partly off it |
| `mask-circle` | shaped crop | photo cropped to a circle |
| `mask-arch` | shaped crop | rounded-top photo |
| `mask-pill` | shaped crop | stadium-shaped photo |
| `mask-diagonal` | shaped crop | photo with an angled or curved cut edge |
| `break-the-frame` | intersecting | portrait extends past its container into the next band |
| `section-intersect` | intersecting | an element straddles the boundary between two sections |

A `backdrop-disc` (a solid brand-colored circle or arch behind an unmasked
cut-out subject) is a variant of `mask-circle`, and counts toward the
shaped-crop budget only when the subject visibly overlaps the shape.

## Choosing by section role

Default per role (rotate; never the same non-split treatment in two adjacent
sections). `scripts/composition.py` applies these when a slot declares no
treatment.

| Role | Default | Alternates |
|---|---|---|
| 1 Big Bold Claim (hero) | `overlay-light` | `overlay-dark-scrim`, `break-the-frame` |
| 2, 3, 4 Pains | `card-overlaps-photo` | `caption-over-photo`, `split` (at most one pain) |
| 2A, 3A, 4A Solutions | `band-light-field` | `split` |
| 5 and 5A to 5C Why | `band-over-texture` | `overlay-dark-scrim` |
| 6 Who | `mask-circle` | `mask-pill` |
| 7 What you get | `band-light-field` | `section-intersect` |
| 8, 9, 10 Benefits | rotate `mask-arch`, `caption-over-photo`, `card-overlaps-photo` | `mask-diagonal` |
| 11 How-to | `band-light-field` | `band-over-texture` |
| 12 Founder letter | `overlay-light` | `overlay-dark-scrim`, `break-the-frame` |
| Closing call to action | `band-over-texture` | `band-light-field` |

A brand's mood board may favor or forbid treatments through `composition_cues`
(see the hand-off below); the defaults apply when it says nothing. The code reads
them: `composition.assign_treatments` never picks a forbidden treatment and puts a
preferred one first in the role's own pool, the wireframe budget gate fails a slot
that declares a forbidden treatment and waives a minimum that only forbidden
treatments could meet, and `imagery_direction` fills the light-field motifs.

## Per-page budget (a gate, from the section plan and again on the built page)

- `split` is at most 40 percent of photo-bearing sections.
- At least one words-over-image hero (`overlay-light` or `overlay-dark-scrim`).
- At least one full-width band (`band-over-texture` or `band-light-field`).
- At least two shaped crops, at least one of them `mask-circle`.
- At least one intersecting treatment.
- No two adjacent sections share the same non-split treatment.

A slot with no declared treatment counts as `split`. The budget is judged from
six photo-bearing sections up; the standard 12-section page can carry all of it.

## The three-stage hand-off: mood board, wireframe, mockup

- **Mood board** sets the brand system: palette, type roles, imagery direction,
  icon style, signature phrases. For composition it supplies
  `composition_cues` (treatment ids the brand prefers or forbids) and
  `imagery_direction` (the `{motifs}` for light fields). It never sets a
  section's layout. A mood board is not a wireframe: a sheet whose "sections"
  are palette and type guidance is the anti-example.
- **Wireframe** fixes the skeleton: numbered sections, real copy, CTA
  positions and one slot record per image. It DRAWS the treatment: the text
  box ON the placeholder for overlays, masks drawn as their real shape, a
  light tint across the full width for a light field, overlap drawn as overlap.
- **Mockup** fills the same slots with real photography and finish. Rule M5
  extends: the mockup keeps each slot's declared treatment, not only the
  section's position.
- **HTML** builds from the wireframe's slots and the mockup's finish: it emits
  `data-image-slot` and `data-treatment` on every slot element.

The slot record, written at the wireframe and carried unchanged through the
prompts, generation, mockup, image map and HTML:

```json
{ "slot_id": "IMG-06", "section_id": "5", "aspect_ratio": "8:5",
  "generation_ratio": "16:9", "delivery_px": {"desktop": [1600, 1000], "mobile": [780, 560]},
  "treatment": "overlay-light", "text_relation": "beside|over|overlap-card|behind",
  "mask": "rect|circle|arch|pill|diagonal|rounded-N",
  "copy_zone": [x0, y0, x1, y1], "subject_zone": [x0, y0, x1, y1],
  "scrim": {"type": "gradient|solid|none", "token": "--brand-surface", "from_pct": 0, "to_pct": 60, "opacity": 1.0},
  "overlay_copy": ["copy-block-id"], "max_overlay_words": 12,
  "art_direction": "...", "mobile_role": "..." }
```

Zones are percent of the frame (0 to 100). `generation_ratio` must be one of
the executor's offered ratios; when the delivered ratio is not on that list,
record a deterministic crop from the generation to `delivery_px`.

## Prompt rules

- Photo prompts (image-inventory-prompts, image generation): each treatment
  has its own copy-space or crop-safe framing sentence in the JSON, and every
  photo prompt ends with the universal negative: no text, no lettering, no
  logos, do not compose the photo as a website section, do not leave a blank
  column. Reserve the copy space INSIDE the photo; never rely on a blank
  column.
- Wireframe prompts: draw the treatment, print each slot label with its pixel
  size, ratio and treatment. The wireframe stage may print its own annotations
  (section number and name, type specs, slot labels, behavior notes); the
  negative block for those stages allows them and nothing else.
- Mockup prompts: state the layering. Example for an overlay: the photograph
  spans the full section width as the BACKGROUND; a gradient from the page
  surface color (solid from 0 to 35 percent of the width) to transparent (by
  65 percent) lies between the photo and the headline; the headline sits ON the
  photograph inside the gradient zone; do not split the section into an image
  column and a text column. For a mask, the shape is visible against the
  section background.
- Build the treatment in CSS, never bake it into the photo.

## Legibility (fail closed in QC)

1. Text never overlaps the slot's `subject_zone`.
2. A 5 to 10 percent safe margin between overlaid text and the edge.
3. Contrast at the worse of the p5 and p95 backdrop luminance under the text:
   body 4.5:1; display type (24px or larger) 3:1.
4. Body copy over a photo needs a scrim or solid block at 55 percent opacity or
   more.
5. More than 60 words never sit directly on a photo.
6. A light field stays light: field-to-surface contrast at most 1.15:1 on every
   palette (white, beige or near-black; measured on the field behind the type with
   buttons and cards hidden), and textured (standard deviation at least 1.5),
   never a flat fill. The absolute floor of 235 of 255 applies only when no brand
   surface color is known.
7. Busyness under text is measured and reported as a warning until calibrated.

## QC checks

`scripts/composition.py` holds the checks as pure functions;
`scripts/validate_wireframe.py` runs the budget on the section plan;
`scripts/validate_page.py` runs the classifier, the shape check and the budget
on the built page.

- Q1 section classifier (OVERLAY, SPLIT, STACK) against the declared treatment;
- Q2 two-pass legibility render (text hidden, then sample the backdrop);
- Q3 shape check (corner patches match the background, center differs);
- Q4 light-field check (luminance floor plus texture);
- Q5 copy-space check on the raw generated photo (regenerate at most twice);
- Q6 face-zone check (text box and `subject_zone` do not intersect).

## Reference images

`assets/visual-standards/reference-catalog.json` lists the hosted examples by
type (wireframe, mockup, hybrid image map, mood board, mockup crop) with a
section, a viewport and the traits each shows. Attach a structure sheet that
matches the stage and section, plus one real example per non-split treatment.
Everything in the catalog is for structure and look only. Never carry its
brand, palette, people, copy, signatures or dates into a client page. Rows
tagged `counter-example-composition` show the split default. A row flagged
`contains_reference_only_text` (placeholder tokens, a signature, a person's
name) is never attached to a prompt. Rows store `media_path`; the url is
assembled from the operator-injected `SKILL71_REFERENCE_MEDIA_BASE`.
