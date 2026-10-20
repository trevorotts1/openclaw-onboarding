# Overview boards (second deliverable of every image stage)

Every image stage (`desktop-wireframe`, `mobile-tablet`, `visual-mockup`,
`final-mockups`) delivers two views of the same sections:

1. the long review PDF: the whole page, top to bottom (`combine_review_pdf.py`);
2. the overview boards: all sections on one big image per board
   (`scripts/build_overview_board.py`, this contract): a desktop board, a
   mobile board, and the combined board that shows desktop and mobile together.

The boards are a second deliverable beside the PDF, never a replacement for it,
and the combined board never replaces the two separate boards.
The two models Trevor approved fix the structure only. Their brand, palette,
people and copy are never reused: every word and color on a board comes from
the run.

## Output

Written next to the PDFs, in `<run_dir>/review-pdfs/`:

| File | Content |
|---|---|
| `<role>_DESKTOP_<KIND>-BOARD.png` | desktop board (stages that deliver desktop images) |
| `<role>_MOBILE_<KIND>-BOARD.png` | mobile board (stages that deliver mobile images) |
| `<role>_DESKTOP-and-MOBILE_<KIND>-BOARD.png` | combined board: desktop and mobile together (see "Combined board") |
| the same name with `.json` |  receipt: sha256 of every input and of the board, sizes, chrome colors, fonts, geometry (mobile grouping, section positions), which source supplied each field |

`desktop-wireframe` owes the desktop board, `mobile-tablet` the mobile board,
`visual-mockup` and `final-mockups` both. `<role>` is the page role slug
(`landing`, `upsell-1`, `thank-you`, ...) and `<KIND>` is `WIREFRAME`,
`MOCKUP-VISUAL` or `MOCKUP-FINAL`; both come from `scripts/deliverable_labels.py`,
the one helper that names every deliverable. The two wireframe stages are one
pair (desktop wireframe, mobile wireframe), so their combined board is
`<role>_DESKTOP-and-MOBILE_WIREFRAME-BOARD.png`.

Labels: the title band reads `<PAGE TYPE> · <DEVICE> <KIND>` (for example
`UPSELL 1 · DESKTOP WIREFRAME`); the combined board heads its DESKTOP column
and its MOBILE parts the same way; every guide tile and mobile frame is
captioned with page type, device, kind and `SECTION N OF M`. The brand name
moves to the subtitle.
Sections are read from the same files the PDF combiner reads
(`section-NN.png`, or `desktop/part-NN.png` and `mobile/part-NN.png`).

## Desktop board

Model: one tall column of the full page beside a numbered section guide.

- Title band across the top: page title and `DESKTOP <STAGE LABEL> · N sections ·
  full page, top to bottom`.
- Left, `FULL PAGE`: every section image, in section order, stacked with no gap
  and no crop, scaled uniformly to one column width (960 px).
- A rail beside the column: a numbered badge at the top of each section and a
  line spanning its height.
- Right, `SECTION GUIDE`: one card per section, aligned to the section's top
  (pushed down only when the previous card would be overlapped), carrying the
  section number, the section name, a thumbnail (the section image, scaled
  uniformly to fit), then these lines:
  `Headline:`, `Body:`, `CTA:` (type sizes), `Image:` (every slot ratio the
  run declared, with its slot id), `Frame:` (the delivered section's ratio and
  pixel size, read from the file).
- Footer: a note when any type size is a skill standard (see below), and the
  no-crop, no-stretch statement.

## Mobile board

Model: phone frames side by side across the board.

- Title band: page title, `MOBILE <STAGE LABEL> (complete scroll)`, and a note
  box: `Optimized for mobile (<viewport range>)` and `Same content and flow as
  desktop · No section labels on the page`. The viewport range defaults to
  `320px – 430px` (the SOP's 320/360/390/430 check) and is overridable with
  `--viewport-range`.
- One phone frame per section group, one row, left to right, all the same height.
  The frame screen is 300 px wide; section images are scaled uniformly to that
  width and stacked inside it.
- A header tab above each frame: `SECTIONS a-b`, or `SECTION n` for a single
  section. Numbers are the sections' positions in the run.
- A caption under each frame saying what that part does: the section names of
  the group joined with ` & `, then `CTA: <label>` for the CTA labels the run
  gives those sections (omitted when none).

### How section groups are formed

Deterministic, greedy, in section order. After scaling to the screen width, a
section joins the current frame while the frame's stacked height stays within
2.8 times the screen width; the next section that would pass that limit starts a
new frame. A section taller than the limit gets a frame of its own. Every frame
is as tall as the tallest group (never shorter than a 2.16 : 1 phone), so a
shorter group leaves background-colored screen below its last section. No
section is split, dropped or reordered.

## Combined board

Model: Trevor's all-in-one reference. Five columns on one image, same section
order everywhere:

1. `DESKTOP <STAGE LABEL> (N SECTIONS)`: the desktop page, top to bottom, with
   the numbered rail beside it (page column 560 px wide, widened in 20 px steps
   up to 960 px until every section is tall enough for its guide card);
2. `DESKTOP SECTION GUIDE`: the same guide cards as the desktop board (name,
   thumbnail, `Headline:` `Body:` `CTA:` `Image:` `Frame:`), aligned to each
   desktop section;
3. to 5. `MOBILE <STAGE LABEL> (PART 1/3)`, `(PART 2/3)`, `(PART 3/3)`: the
   mobile page as flush, numbered section stacks.

- Title band as on the other boards: page title, `Desktop + Mobile <STAGE
  LABEL> · N sections · desktop page, guide and mobile page`, and a note box
  (`Optimized for mobile (<viewport range>)`).
- The mobile page is split into at most three consecutive parts that minimize
  the tallest part (ties go to taller earlier parts). A cut falls only between
  two sections, never inside one; fewer than three sections gives fewer parts.
  Section numbers on the rails are the sections' positions in the run, so the
  numbers run 1..N down the desktop column and then 1..N again across the parts,
  in the same order.
- Mobile column width is chosen so the tallest part is about as tall as the
  desktop column, within 240 to 520 px; images are scaled uniformly.
- The guide is the desktop guide: type sizes, ratios and names come from the
  desktop stage's records first (see below).
- It needs both devices. `visual-mockup` and `final-mockups` carry both in one
  stage. For the wireframe pair the board is built by whichever of the two
  stages runs once the other has delivered its full set; until then (nothing,
  a gap, or fewer images than sections) it is skipped without error and any
  older combined board is deleted, so a stale one never ships. `--device
  combined`, a fault in the stage's own images, or a sibling with more images
  than sections fails the board and the stage.
- Layout constants live at the top of the script (`C_*`). Everything else
  (chrome colors, receipts, determinism, no crop) is as for the other boards.

## Where the text comes from

Nothing is invented; a field the run does not carry is either skill-standard
and starred, or the board fails.

| Field | Source, first hit wins |
|---|---|
| Section names (guide, captions) | `<stage>/production-record.json`, `<stage>/section-plan.json`, the run's production request (`section_name`); fallback is the `section_id` |
| Section order and count | the production request when present, else the first source above that has sections |
| Headline, body, CTA sizes | `type_specs` in the stage production record, then the section plan, then the request. `type_specs` keys: `heading` (or `h1`/`h2`), `body`, `cta`. When none is recorded the skill standard from `references/section-image-prompt.md` "Type tokens" is printed with an asterisk and the footer says so |
| `Image:` ratios | slot ratios the record, plan or request declares (`slot_labels`, `image_slots`, `slots[].aspect_ratio`) |
| `Frame:` | the delivered image's real pixels (a nearest common ratio, `≈` when more than 1% off) |
| CTA caption | `cta` in the same sources (string or `{label}`) |
| Title | `--title`, else the brand id |

## Chrome colors

Brand palette only, resolved in the stage gate's order: `--brand`, else the
run's `private/brand.json`, else `intake.json` `brand_file`, else the skill's
own `assets/brand/blackceo-brand.json`. The lightest palette color is the
ground, the darkest is the ink (title band, frame bezel, text), and the most
saturated of the rest is the accent (column headers, badges, frame tabs). The
caption and card tint is the ground mixed 12% toward the accent. Text on a
band or accent picks the higher-contrast of ground or ink. A palette with fewer
than two valid hex colors fails the board.

## Rules and failure

- Pure code (Pillow), no generation, no network, no randomness. The same inputs
  give the same bytes.
- Section images are scaled by one factor for width and height. Nothing is
  cropped, stretched or recolored; chrome is drawn around the images.
- Fail closed, exit 1, one `FAIL:` line, and any existing board for that stage
  and device is deleted so a stale board never ships, when: no image matches the
  stage layout, the numbering has a gap, the image count differs from the run's
  section count (or `--expect`), an image is unreadable, the run carries no
  section names, or the brand palette is unusable. The combined board adds:
  the desktop and mobile section counts differ. A failure deletes the stage's
  combined board too.
- The stage executor runs the composer right after the stage's composition and
  review-PDF step (`overview_boards()` in `scripts/stage_executor.py`), which
  builds the separate boards and then the combined board in one call; a failed
  board fails the stage run the same way a failed PDF does. Stub mode never
  composes.

## Command

```
python3 scripts/build_overview_board.py <run_dir> --stage visual-mockup \
    [--device desktop|mobile|combined] [--request production-request.json] \
    [--brand brand.json] [--title "Page title"] [--viewport-range "320px – 430px"] \
    [--expect N] [--out-dir DIR]
```
