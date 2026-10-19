# Combined overview board (second deliverable of every image stage)

Every image stage (`desktop-wireframe`, `mobile-tablet`, `visual-mockup`,
`final-mockups`) delivers two views of the same sections, for desktop and for
mobile:

1. the long review PDF: the whole page, top to bottom (`combine_review_pdf.py`);
2. the combined overview board: all sections on one big image
   (`scripts/build_overview_board.py`, this contract).

The board is a second deliverable beside the PDF, never a replacement for it.
The two models Trevor approved fix the structure only. Their brand, palette,
people and copy are never reused: every word and color on a board comes from
the run.

## Output

Written next to the PDFs, in `<run_dir>/review-pdfs/`:

| File | Content |
|---|---|
| `<stage>-desktop-overview.png` | desktop board (stages that deliver desktop images) |
| `<stage>-mobile-overview.png` | mobile board (stages that deliver mobile images) |
| `<stage>-<device>-overview.json` | receipt: sha256 of every input and of the board, sizes, chrome colors, fonts, mobile grouping, which source supplied each field |

`<stage>` is the stage id. `desktop-wireframe` owes the desktop board,
`mobile-tablet` the mobile board, `visual-mockup` and `final-mockups` both.
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
  section names, or the brand palette is unusable.
- The stage executor runs the composer right after the stage's composition and
  review-PDF step (`overview_boards()` in `scripts/stage_executor.py`); a failed
  board fails the stage run the same way a failed PDF does. Stub mode never
  composes.

## Command

```
python3 scripts/build_overview_board.py <run_dir> --stage visual-mockup \
    [--device desktop|mobile] [--request production-request.json] \
    [--brand brand.json] [--title "Page title"] [--viewport-range "320px – 430px"] \
    [--expect N] [--out-dir DIR]
```
