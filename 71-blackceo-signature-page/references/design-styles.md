# Design styles: A Block, B Circle, C Hybrid

Trevor's rule: a client chooses the page's DESIGN STYLE before any wireframe is made, after seeing
an example of each. The choice is recorded at intake (`intake.json` -> `design_style`) and from then
on it drives the wireframes, the mockups, the image slot shapes and the shape QC check.

| Id | Name | One line | Photo shape |
|---|---|---|---|
| A | Block | Traditional editorial: straight-edged sections, rectangular photos. | rectangle |
| B | Circle | Round framed photos with ring accents, circular text panels and soft curved shapes. | circle |
| C | Hybrid | Block structure with circle accents on the personal pictures. | rectangle by default, circle on named accent slots |

Machine-readable form (names, one-liners, example links, the intake question):
`references/design-styles.json`. Code that needs a style reads that file through
`scripts/design_style.py`; nothing hardcodes a style's wording.

## Rules that hold in every style

1. **Client brand colors always.** Every color on a page comes from the run's brand file
   (`scripts/brand_colors.py` resolves it). The examples below show SHAPE and RHYTHM only. Never copy an
   example's colors, brand name, words, people or copy. The Oprah-design example's coral and pink wash,
   and the Set for Life green and rust, are that example's own; a client page that carries them is a
   defect. (`references/reference-image-use.md` states the same rule for every reference image.)
2. **Palette independence.** A rule below names a role ("accent", "deep accent", "neutral panel"), never a
   hex value. A ring is drawn in a brand accent; a text panel is a brand neutral.
3. **One style per page.** A page is A, B or C. Mixing is Style C's job and Style C has its own rules; an
   agent never blends styles ad hoc.
4. **Copy still leads.** The style changes how a section is shaped, never what it says. Approved copy is
   never shortened to fit a circle.
5. **Fonts come from the brand file.** The examples pair a display serif with a bold sans label; that is
   a role pairing only. The brand file's fonts apply.

## Style A: Block (traditional editorial)

Source: the Set for Life desktop and mobile references bundled in `assets/visual-standards/`.

- **Image shape.** Rectangles with square corners, in the ratios the inventory declares (portrait 3:4
  or 2:3 for people, 16:9 or 4:3 for scenes). No circle crops, no rounded corners on photos. An offset
  solid block behind a hero portrait is allowed (a rectangle, not a ring).
- **Section rhythm.** Full-width bands in alternating brand grounds (light, deep, tinted). Inside a band,
  a text column and a photo column alternate sides from section to section.
- **Cards and text panels.** Rectangular, square or barely rounded, hairline top rule, no shadow
  or only a faint one. Numbered lists run in full-width rows separated by rules.
- **Headlines.** Two-line editorial pair: roman headline, then an italic accent line. Small uppercase
  kicker above.
- **CTA.** Rectangular button with a small arrow. Repeated at the section ends the copy guide names.
- **Mobile.** Single column; photo above or below its text, full content width, square corners kept.

## Style B: Circle (the Oprah-design pattern)

Source: the owner-supplied Oprah-design sales page (desktop 1920 wide, mobile 375 wide), analyzed for
structure only. Its palette, its brand and its words are not part of the style.

- **Circle is the organizing unit of the core body.** Every photo-bearing row in the feature, curriculum,
  benefit or people sequence is one large photo circle paired with one circular text panel. Measured on the
  example: the photo circle is about 44 percent of the page width, the text circle about 34 percent, and the
  text circle overlaps the photo circle by about 14 percent of the photo diameter. The text circle is
  vertically centered on the photo circle.
- **Row rhythm.** Rows alternate: photo circle on the right with the text circle on the left, then the
  reverse. Rows sit close together (a gap of roughly 5 percent of the photo diameter between one row's
  bottom and the next row's top), so the sequence reads as a connected chain rather than separate cards.
- **Ring accent.** Each photo circle carries a partial ring: a crescent of the same circle offset toward
  the OUTER-BOTTOM side (away from its text circle), about 6 percent of the diameter at its thickest point
  (`--ring-width-pct 4` with a diagonal offset gives that). The ring
  is a brand accent; one row may use a deeper shade of the accent, but never a color outside the brand
  file. The pipeline draws it into the PNG (`--ring-style crescent`).
- **Text circle treatment.** Near-white or brand-neutral fill, one-pixel hairline border, centered content
  in a fixed order: small bold uppercase label ("MODULE 1" role), display title in the accent color, a
  short rule in a deep accent, then the body paragraph (six to seven lines at most; longer copy moves to a
  rectangular row, never a bigger circle).
- **Section headers.** A soft wash band (brand tint, texture allowed) with a small kicker, a boxed
  headline strip in the accent, one very large display word, and a round arrow button straddling the band
  edge.
- **Soft shapes everywhere else.** Pill buttons, rounded panels, curved wave dividers, a very light paper or
  marble texture behind the body. No hard rectangular cards in the core sequence.
- **Rectangles are still allowed outside the core sequence.** The example keeps its hero offer card,
  testimonial panels, bonus cards and guarantee as rectangles. Style B means circles carry the
  main promise sequence, not that no rectangle exists on the page.
- **CTA.** Fully rounded pill, solid brand accent, short uppercase label, centered. An urgency or offer
  band (accent or neutral ground) repeats the pill at the top and again after the core sequence.
- **Mobile stacking.** Each row stacks into one centered column: the text circle FIRST (about two thirds of
  the viewport width), then the photo circle below it (about four fifths of the viewport width) with the
  text circle overlapping the photo's top edge slightly. Alternation stops; every row is centered. The ring
  crescent sits at the bottom of the photo circle. Rows keep the same order as desktop.

## Style C: Hybrid (block structure with circle accents)

Style C has no bundled example yet. It is defined here from A and B; the example link for C stays a
placeholder until a real Hybrid page has been generated (`design-styles.json` records `status: placeholder`
and nothing is invented).

- **Structure is Block.** Full-width alternating bands, a text column and a photo column, rectangular hero,
  proof and offer panels, editorial headlines, rectangular buttons or lightly rounded ones. Section
  rhythm is exactly Style A.
- **Circles are accents, named in the plan.** A circle slot is allowed only where a person or a single object
  should feel personal: the founder or host portrait, the "who this is for" personas, the testimonial
  avatars, and at most one hero or "meet" portrait. The wireframe declares each circle slot with
  `shape: "circle"`; every other slot stays `rect`.
- **Budget.** At most one circle slot in three of the page's photo slots (enforced by `design_style.py validate` on the request and `design_style.py validate-inventory` on the image inventory). A page whose photos are mostly circles is Style B, not C.
- **Ring.** Circle slots may carry a full ring or a crescent ring in a brand accent. One ring treatment
  per page, used on every circle slot.
- **Overlap.** A circle portrait may overlap its text panel's edge by about 10 percent of its diameter; a
  circle never overlaps a rectangular photo.
- **CTA.** The Style A button, plus a pill secondary button only if the brand file's button spec has one.
- **Mobile.** Bands stack as in A. Circle slots become centered circles at about 70 percent of the
  viewport width, above their text, with the ring at the bottom.

## Circle images: how the "round" photo is made

The image model returns only square or rectangular images. A circle slot is therefore delivered as a
SQUARE PNG whose pixels outside a circle are fully transparent. Anyone placing the file sees a round photo
and nobody needs a mask or `border-radius`.

1. **Prompt for a square.** A circle slot's inventory entry carries `shape: "circle"` and aspect ratio
   `1:1`. The prompt asks for a square image, the subject centered, with safe margins (the circle
   removes the corners), and carries the circle clause below. The stage refuses to generate a circle slot
   whose prompt omits it.
2. **Mask.** `scripts/circle_image.py apply` (run by `scripts/stage_executor.py` right after a
   circle slot is generated, before the file is hashed for the receipt): center or `crop_focal` crop to a
   square, scale, anti-aliased circular alpha mask (4x supersampled), optional ring in a client brand color,
   write RGBA PNG. The raw square is kept under `image-generation-qc/raw-square/` and recorded.
3. **Deliver.** The masked PNG replaces `Image-NN.png`; the raw is the audit trail.
4. **QC shape check.** `scripts/circle_image.py check` (a per-file validator on `image-generation-qc`, also
   inside `scripts/validate_image_manifest.py`): a circle slot passes only if the file is a real PNG (format checked, not the extension) that is square RGBA, all four corner regions (8 percent per axis) have alpha 0, the center region (middle 20 percent
   per axis) is fully opaque, and 10 to 35 percent of the pixels are transparent. An unmasked square fails
   by name. A rect slot is not checked for shape.

Circle clause (a circle slot's prompt carries it, inside the model's character band, verbatim in spirit):

> CIRCLE CROP SAFE FRAME: compose a perfectly square 1:1 image for a round crop. Place the subject
> centered in the frame with the face or main object inside the central 60 percent. Keep every important
> element inside the inscribed circle; the four corners are cropped away, so leave them as quiet,
> out-of-focus background with no text, no hands, no props and no edges of objects touching the corners.

Ring colors come only from the run's brand file. `ring.color` is required when a ring is requested; there is
no default color.

## Slot fields (the contract the code reads)

On an inventory entry in `desktop-wireframe/image-inventory.json`, and the same keys on a section slot in
`production-request.json`:

| Field | Values | Meaning |
|---|---|---|
| `shape` | `rect` (default), `circle` | Delivered shape. `mask: "circle"` (the composition library's name) is read as the same thing. |
| `ring` | `{style: full or crescent, color: "#RRGGBB", width_pct: 3, direction: br, bl, tr or tl}` | Optional; color is a client brand color. |
| `crop_focal` | `"x,y"`, `[x, y]` or `{x, y}`, fractions 0 to 1 | Where the subject sits; the crop centers there. Default: image center. |

Style rules enforced in code (`scripts/design_style.py`), on the request AND on `desktop-wireframe/image-inventory.json` (the file that drives circle generation: `stage_executor.py` checks the whole inventory before generating any item, and `design_style.py validate-inventory RUN_DIR` is a gate validator on `desktop-wireframe` and `image-generation-qc`): Style A refuses a circle slot by name; Style B and C
accept `shape` on any slot; a circle slot must declare ratio `1:1`. `production-request.json` carries
`design_style` (a letter) and each section's slots carry `shape`; when the request omits `design_style`,
the executor reads it from `intake.json`.

## What each stage does with the style

| Stage | Effect |
|---|---|
| intake | Asks the style question (below), records `design_style` and `design_style_source`. |
| design board | The Design Board prompt carries one DESIGN STYLE paragraph (name, one line) and draws circle slots as circular tiles in the imagery grid: `design_style.board_prompt_block(style, slots)` for the prompt, `board_block` for the record's data. The board request carries `design_style` and each slot's `shape`. |
| desktop-wireframe, mobile-tablet | The stage prompt carries the style block; circle slots are drawn as circles with the slot label beside them. |
| visual-mockup, final-mockups | The style block repeats; circle slots show a round photo with the ring in the brand accent. |
| image-inventory-prompts | A circle slot's prompt is 1:1 and carries the circle clause. |
| image-generation-qc | Generation, then the mask step, then the shape check beside the grade check. |
| production record | `design_style` is recorded at the top of the per-section production record. |

## The intake question

Asked at intake, in the interview voice, with an example link per style. The wording and links live in
`references/design-styles.json` (`question`); do not reword them per run. Record the answer with
`scripts/write_intake.py ... --design-style A|B|C --design-style-source client_choice`. If the client is unsure,
the agent recommends one with a one-sentence reason from the brand's feel and records
`--design-style-source recommended_accepted` once the client agrees. There is no default style: a run that
never asked records nothing, intake prints a named note, and a production run cannot close `intake`
(`gate:intake_design_style`); test runs are exempt and carry no style block.
