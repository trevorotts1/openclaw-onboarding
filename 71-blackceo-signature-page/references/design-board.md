# Design Board (Official Visual Direction)

Trevor's rule: once the images for a page's sections have been created, the client sees one
Design Board for that page and approves it first, before the page is built. The board shows the
client's own brand colors, their logo and the page's actual images. It is the framework the
mockup and everything after it follow.

Structure reference only: Trevor's approved example is a Set for Life board. Its brand, colors,
words and people belong to that client and never appear on another client's board
(`scripts/design_board.py` refuses a board that carries them).

## One board per page role

A funnel gets one board for each page it actually has. Page roles are the page-request enum
(`references/page-request.schema.json`), all seven already supported:

| Trevor's page | page_role | Owning skill |
|---|---|---|
| signature sales page | `landing` + page kind `sales` | 71 |
| signature landing (opt-in) page | `landing` + page kind `opt_in` | 71 |
| order page (package choice) | `product_selection` | 78 |
| checkout page | `checkout` | 79 |
| upsell page | `upsell_1`, `upsell_2` | 80 |
| downsell page | `downsell_1` | 81 |
| thank-you page | `thank_you` | 82 |

The role a run's board is made for is read from the same place as the page's section structure,
`scripts/page_role.py` (`intake.json` `page_role` or `launch.page_role`, else `page-request.json`,
else `landing`), so the board, the section-count check, the wireframe prompt and the gate cannot
disagree about which page they are for. The thank-you page (`thank_you`) draws its board with the
icon row required and the celebration-imagery emphasis; its one image is the page's only slot.
The landing role's board names its kind: the run's `page_kind` (intake) selects the label and the page-role emphasis printed on the board (`references/page-kinds.json`), the record stores `page_kind`, and `validate` fails a board whose kind differs from the run's.

A single-offer funnel in combined mode has no product-selection page, so it has no order-page
board; its `checkout` page carries the order form and gets its own board. A run is one page, so
one run makes one board; a six-page funnel makes six.

## Where it sits

`... -> visual-mockup -> image-inventory-prompts -> image-generation-qc -> image-map-upload` ->
**`design-board`** -> `final-mockups` -> ...

Trevor's rule is that the board is made once the images that will be used in the page's
sections have been created, and that the client approves it first, before the page is built. So
the board is the first thing that shows the client the page's real images in the client's own
brand colors and logo, and it is the framework the mockup and everything after it follow. It is
never made from art-direction text: a board whose images are drawn by the model from a
description is not the page's board.

Preconditions, in order: (1) the client's brand colors are resolved by
`scripts/brand_colors.py` (check the run's own brand file first, ask the client only when none is
known; the board consumes that resolution and never picks colors); (2) the image chain has
closed, so every image slot of the page has its generated or supplied file on disk. A slot with
no file refuses the board by name (`design_board.py` / `stage_executor.py --stages design-board`
both stop and list the slots); there is no "planned" tile.

Placement ruling (open for Trevor). Trevor's wording is that the board is made once the section
images exist and is approved first, before the page is built. This branch builds that reading:
after the image chain, before `final-mockups`, with the board as the client's first look at the
page (the wireframes and the layout proof are internal working stages, never sent to the client
as a design). The other reading, the board before the wireframes of every page role, cannot be
had together with "after the images": the slot list is `desktop-wireframe/image-inventory.json`,
a wireframe artifact, and `image-inventory-prompts` depends on `mobile-tablet`. Meeting it
would mean moving the image chain ahead of the wireframes, a change to the stage order that
belongs to Trevor, not to this unit. Until he rules, the stage order stays as above.

Gate: `final-mockups` depends on `design-board`. The stage closes only with a recorded client
approval (`validate --require-approval`). `scripts/stage_executor.py` refuses `final-mockups`
(preflight included, and before any call in a multi-stage run) while the approval is missing or
stale. The wireframe, mobile, layout-proof and image-chain stages come before the board and are
not gated by it.

## The page's actual images

The board's images are found from the run's own artifacts, never from what a request says:

1. Slot universe: `desktop-wireframe/image-inventory.json` (the production request's slots when a
   run has no inventory). Each slot's section comes from `desktop-wireframe/section-plan.json`.
2. A slot's file: `image-map-upload/image-map.json`, else `image-generation-qc/Image-NNN.png`
   (generated); the inventory entry's supplied `file`, else the request's `file` (supplied
   assets: the supplied file leads and is never replaced by a generated one).
3. A named file that is not on disk refuses the board; a slot with no file refuses it.

The same resolution runs again at every `validate`, `approve` and `gate`. The record keeps the
resulting image set (slot, section, source, origin, file, SHA-256) and its hash, and the
approval is bound to that hash, so any later change is stale: a replaced supplied image, an image
map that now names another file, an edited image, an added or removed slot. Deleting the
request or the inventory does not hide a change; the gate fails when the set cannot be
re-derived.

Optional grid extras, for tiles that are not page slots: `imagery_extras` is a list of
`{"text": "..."}` (a text tile, printed exactly) or `{"file": "..."}` (a supplied prop image,
hashed into the image set). A prop is a supplied picture, never drawn.

The image-transport limit is `MAX_REFERENCES` attachments (logo + images). The board call sends
exactly those attachments and nothing else: the production request's request-level `references`
(style references for the other stages) and any `input_urls` in `input_extra` are never added to
it, so the prompt's "REFERENCES - N attached" count, the preflight `refs=` count, the record's
`generation.references` and the images actually sent are the same list, logo first. A page with more
images attaches the first ones individually and the rest as one contact sheet built from the real
files (`design-board/overflow-sheet.png`, written by the executor when it generates, never by
preflight); the prompt tells the model to place each as its own tile.

## Board blocks

| Block | Content | landing | other roles |
|---|---|---|---|
| Header | title line `<brand name> — OFFICIAL VISUAL DIRECTION` across the top edge, brand name, client logo (placed as supplied), positioning line | required | required |
| Header side taglines | `side_taglines`: taglines flanking the logo | optional | optional |
| Brand aesthetic | five or six words (`aesthetic_words`, chips), with one phrase line under them (`aesthetic_phrase`) | required | optional, but whole when given |
| Official palette | one swatch per resolved color, printed `Name #HEX` | required | required |
| Gradient / accent strip | blends only palette colors; optional `gradient_caption` printed under it | optional | optional |
| Typography system | display, body, accent (and optional editorial serif): font, sample line, usage note | required | required |
| Imagery direction | one line, then a grid with one tile per image of the page, plus any `imagery_extras` text or prop tiles | required | required |
| Icon style row | matching line icons with labels | required | required on `product_selection`, `thank_you`; else optional |
| Size guidance | label and px size, desktop and mobile | required | optional |
| Application / design cues | checklist, at least five lines | required | required |
| Hero / brand banner strip | wide strip with a brand line (`banner_line`) and the logo, plus an optional second line beside the logo (`banner_subline`) | required | optional |
| Footer taglines | one or more taglines | required | required |

Every block that is on the board is checked in the read-back, required or optional: a declared
side tagline, gradient caption or text tile that is not legible fails the board.

Page-role adaptation (the imagery line and grid follow the page): `landing` full-page
persuasion images; `product_selection` package imagery; `checkout` trust and guarantee imagery,
few images, calm; `upsell_*` and `downsell_1` the offer's own imagery in the main offer's look;
`thank_you` celebration and next-step imagery. The grid always has one tile per image of that page.

Content is never invented. Palette comes from the resolved brand; fonts from
`font-action-plan/font-map.json`; size rows from that map's typography sizes; everything else
from the `design_board` block below. A required block with no content refuses the board.

## Request: the `design_board` block

In `production-request.json`, beside `sections`. Every value comes from the client's own brand,
copy and font map; the placeholders below are the shape, never content to copy:

```json
"design_board": {
  "brand_name": "<the client's brand name>", "positioning_line": "<the client's own line>",
  "logo": "<run-relative path of the client's logo file>",
  "color_names": {"<palette role or palette hex>": "<the client's name for that color>"},
  "aesthetic_words": ["<five or six words from the client's own brand>"],
  "aesthetic_phrase": "<one phrase line for the client's brand, under the chips>",
  "typography": {"display": {"sample": "<line>", "usage": "<where it is used>"},
                 "body": {"sample": "<line>", "usage": "<...>"},
                 "accent": {"sample": "<line>", "usage": "<...>"}},
  "imagery_line": "<one direction line for this client's imagery>",
  "icons": ["<one label per icon>"], "size_guidance": true,
  "cues": ["<at least five application cues for this client>"],
  "banner_line": "<the banner strip's line>", "banner_subline": "<optional second line beside the logo>",
  "footer_taglines": ["<one or more taglines>"],
  "side_taglines": ["<optional header flank taglines>"],
  "gradient": false, "gradient_caption": "<optional, needs gradient: true>",
  "imagery_extras": [{"text": "<optional text tile>"}, {"file": "<optional supplied prop image>"}]
}
```

`color_names` keys must be palette roles or palette hexes (a name for a color the client does not
have is refused). A request whose aesthetic words, icons, cues or color names are lifted from
the example board is refused (`copied_example_hits`), and the example's own strings are refused
anywhere on another client's prompt or read-back (`foreign_hits`). The board prompt takes its
tone only from the client's own `aesthetic_words`.

Slots may carry `file` (run-relative or absolute) and `source` (`supplied`, `generated`) in a run
that has no wireframe inventory; in a normal run the files come from the image chain.

## How the board is made

Model-generated, one image per page, 4:3, through the existing stage executor:

```sh
python3 scripts/stage_executor.py <run_dir> --stages design-board --preflight   # free
python3 scripts/stage_executor.py <run_dir> --stages design-board --provider kie --allow-paid
```

`design_board.py compose_prompt` carries the contract blocks, the exact `Name #HEX` palette,
the logo and the page's real images as references (every picture tile is one of them; none is
drawn from a description), a negative block against any other client's brand, and follows the
executor's prompt-budget band and sanitizer. The default provider is the inert stub; a stub
board never validates. Paid cost: one generation per board (see the report's count); each
failed-only repair is one more, at most three per board (SOP rule).

## The read-back is the image's, not the caller's

`design_board.py finalize --readback-file` takes a transcript of the board (a reviewer's
reading, or a vision model's), but it records it only after reading the board image itself with
`tesseract` (a free local reader; install with `brew install tesseract` or
`apt install tesseract-ocr`; without it the board cannot validate, it fails closed).
`finalize` and every `validate` / `gate` re-read the image and require:

- the machine read supports at least 60 percent of the transcript's words overall, and the image
  shows every declared text on its own: each side tagline, caption, text tile, cue, icon label,
  line and the title line needs at least 70 percent of its own words in the machine read, each
  machine-read word used up by the one text it matches (a word printed once cannot show two
  texts), a word matching exactly or, from five characters, within one misread character (so
  `grow` is not shown by `growth`). One text missing from the image fails its block by name,
  even when the rest of the block is there;
- the machine read is two reads of the image (as is, and inverted grayscale, so light text on a
  dark or colored swatch is read), a word counting as many times as it appears in one read;
  the prompt asks for swatch labels in contrast ink; a label too faint for the machine to read
  fails the board and is repaired, never waved through;
- the transcript carries every block's text exactly, every palette hex, and no hex outside the
  palette (a hex the machine read differs from by one character is a misread, not a stray);
- every palette color is present in the board's pixels;
- the transcript was taken from this board image (its SHA-256 is recorded).

## Record and approval

`design-board/production-record.json` (`artifact: "design-board"`): page role, revision,
brand and logo hash, the resolved palette and its hash, typography, image set (slot, section,
source, origin, file, hash) and its hash, expected text per block, board file hash, generation
provenance, read-back (transcript, the machine read, the board hash it was taken from), and
`approval`. Approval is the client's, recorded after QC and after the client has seen the board
(delivery to the client follows the fleet's own client-message rules; this skill sends nothing):

```sh
python3 scripts/design_board.py approve <run_dir> --by "<client name>" --evidence "<message id or link>"
```

`approve` refuses a board that fails the QC floor. The approval is bound to the board hash, the
image-set hash, the palette hash and the page role; any change (remade board, replaced or edited
image, an image map that names another file, added or removed slot, new palette) makes it stale
and the gate refuses until the client approves again. `finalize` and a remade board both clear a
prior approval.

## QC checklist (the validator is the deterministic floor; the reviewer scores the rest)

Deterministic (`design_board.py validate`):

1. Palette on the board equals the run's resolved client palette (roles and hex), hash recorded,
   and every palette color is present in the board's pixels.
2. Client logo file present and unchanged since the board was made.
3. Images equal the page's actual section images, re-derived from the run's own artifacts now:
   same slots, same files, same bytes as recorded; no slot without a file.
4. Every block on the board (required ones for this page role, and any optional one declared) is
   legible, text by text: each declared text is in the transcript and the board image itself
   shows that text (not just most of its block).
5. Every hex printed on the board is a palette hex, and every palette hex is printed.
6. No foreign client brand text: no other client's name (derived from the visual-standards
   manifest) and none of the example board's words, unless the client's own brand uses them.
7. Not a stub placeholder; board file unchanged since recorded; page role matches the run.
8. With `--require-approval`: approval present, `decision` approved, approver, evidence and
   time recorded, and bound to the current board, image set, palette and role.

Reviewer (Review Receipt v2, scores at least 8 each): the board reads as the client's brand,
the logo is rendered faithfully and not restyled, each image tile is the page's image and is
not distorted, spacing and hierarchy are clean, no garbled or invented text.

## Effect on the pipeline

The image chain runs before the board, so the first client look at the page's real images is the
approval of this board; the wireframe, mobile, layout-proof and image stages are not held for it.
The client-judged mockup (`final-mockups`), the responsive build, the install and the publish all
follow the approved board. The board needs `tesseract` on the box that validates it.
