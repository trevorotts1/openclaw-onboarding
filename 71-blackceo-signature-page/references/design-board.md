# Design Board (Official Visual Direction)

Trevor's rule: before any wireframe or mockup is made for a page, the client sees one Design
Board for that page and approves it. The board shows the client's own brand colors, their logo
and the images that page will use. It is the framework every later stage follows.

Structure reference only: Trevor's approved example is a Set for Life board. Its brand, colors,
words and people belong to that client and never appear on another client's board
(`scripts/design_board.py` refuses a board that carries them).

## One board per page role

A funnel gets one board for each page it actually has. Page roles are the page-request enum
(`references/page-request.schema.json`), all seven already supported:

| Trevor's page | page_role | Owning skill |
|---|---|---|
| landing / sales page | `landing` | 71 |
| order page (package choice) | `product_selection` | 78 |
| checkout page | `checkout` | 79 |
| upsell page | `upsell_1`, `upsell_2` | 80 |
| downsell page | `downsell_1` | 81 |
| thank-you page | `thank_you` | 82 |

A single-offer funnel in combined mode has no product-selection page, so it has no order-page
board; its `checkout` page carries the order form and gets its own board. A run is one page, so
one run makes one board; a six-page funnel makes six.

## Where it sits

`intake` -> `copy` -> `font-action-plan` -> **`design-board`** -> `desktop-wireframe` -> ...

Preconditions, in order: (1) the client's brand colors are resolved by
`scripts/brand_colors.py` (check the run's own brand file first, ask the client only when none
is known; the board consumes that resolution and never picks colors); (2) the page's section
images are selected: `production-request.json` lists every section and image slot, with a `file`
for each image that already exists (supplied assets, earlier generations). Slots with no file
yet appear on the board as their art direction, and the record lists them as `planned`.

Gate: `desktop-wireframe` depends on `design-board`. The stage closes only with a recorded
client approval (`validate --require-approval`). `scripts/stage_executor.py` refuses every
wireframe, mockup and image stage while the approval is missing or stale.

## Board blocks

| Block | Content | landing | other roles |
|---|---|---|---|
| Header | brand name, client logo (placed as supplied), positioning line | required | required |
| Brand aesthetic | five or six words, with a phrase line | required | optional |
| Official palette | one swatch per resolved color, printed `Name #HEX` | required | required |
| Gradient / accent strip | blends only palette colors | optional | optional |
| Typography system | display, body, accent (and optional editorial serif): font, sample line, usage note | required | required |
| Imagery direction | one line, then a grid with one tile per image slot of the page | required | required |
| Icon style row | matching line icons with labels | required | required on `product_selection`, `thank_you`; else optional |
| Size guidance | label and px size, desktop and mobile | required | optional |
| Application / design cues | checklist, at least five lines | required | required |
| Hero / brand banner strip | wide strip with a brand line and the logo | required | optional |
| Footer taglines | one or more taglines | required | required |

Page-role adaptation (the imagery line and grid follow the page): `landing` full-page
persuasion images; `product_selection` package imagery; `checkout` trust and guarantee imagery,
few images, calm; `upsell_*` and `downsell_1` the offer's own imagery in the main offer's look;
`thank_you` celebration and next-step imagery. The grid always has one tile per slot of that page.

Content is never invented. Palette comes from the resolved brand; fonts from
`font-action-plan/font-map.json`; size rows from that map's typography sizes; everything else
from the `design_board` block below. A required block with no content refuses the board.

## Request: the `design_board` block

In `production-request.json`, beside `sections`:

```json
"design_board": {
  "brand_name": "Client Brand", "positioning_line": "Their line.",
  "logo": "inputs/logo.png",
  "color_names": {"primary": "Evergreen", "#E2C98F": "Champagne"},
  "aesthetic_words": ["Chic", "Elevated"],
  "typography": {"display": {"sample": "...", "usage": "..."}, "body": {...}, "accent": {...}},
  "imagery_line": "...", "icons": ["Workbook", "Quotes"], "size_guidance": true,
  "cues": ["Oversized typography", "..."], "banner_line": "...",
  "footer_taglines": ["...", "..."], "gradient": false
}
```

Slots may carry `file` (run-relative or absolute) and `source` (`supplied`, `generated`,
`planned`). With a file the image is attached as a reference and shown as supplied.

## How the board is made

Model-generated, one image per page, 4:3, through the existing stage executor:

```sh
python3 scripts/stage_executor.py <run_dir> --stages design-board --preflight   # free
python3 scripts/stage_executor.py <run_dir> --stages design-board --provider kie --allow-paid
```

`design_board.py compose_prompt` carries the contract blocks, the exact `Name #HEX` palette,
the logo and the page's images as references, a negative block against any other client's
brand, and follows the executor's prompt-budget band and sanitizer. The default provider is the
inert stub; a stub board never validates. Paid cost: one generation per board (see the
report's count); each failed-only repair is one more, at most three per board (SOP rule).
Text fidelity: the board is read at native resolution and the text is recorded with
`design_board.py finalize --readback-file`; the validator checks it against the contract.

## Record and approval

`design-board/production-record.json` (`artifact: "design-board"`): page role, revision,
brand and logo hash, the resolved palette and its hash, typography, image set (slot, source,
file, hash) and its hash, expected text per block, board file hash, generation provenance,
read-back, and `approval`. Approval is the client's, recorded after QC and after the client
has seen the board (delivery to the client follows the fleet's own client-message rules; this
skill sends nothing):

```sh
python3 scripts/design_board.py approve <run_dir> --by "<client name>" --evidence "<message id or link>"
```

`approve` refuses a board that fails the QC floor. The approval is bound to the board hash, the
image-set hash, the palette hash and the page role; any change (remade board, replaced
supplied image, added or removed slot, new palette) makes it stale and the gate refuses until
the client approves again. `finalize` and a remade board both clear a prior approval.

## QC checklist (the validator is the deterministic floor; the reviewer scores the rest)

Deterministic (`design_board.py validate`):

1. Palette on the board equals the run's resolved client palette (roles and hex), hash recorded.
2. Client logo file present and unchanged since the board was made.
3. Images equal the page's actual section images: every slot of the request is in the record,
   no slot added or removed, every recorded file present with its hash.
4. Every required block (table above) for this page role is legible: its text is in the
   native-resolution read-back.
5. Every hex printed on the board is a palette hex, and every palette hex is printed.
6. No foreign client brand text: no other client's name (derived from the visual-standards
   manifest) and none of the example board's words, unless the client's own brand uses them.
7. Not a stub placeholder; board file unchanged since recorded; page role matches the run.
8. With `--require-approval`: approval present, `decision` approved, approver, evidence and
   time recorded, and bound to the current board, image set, palette and role.

Reviewer (Review Receipt v2, scores at least 8 each): the board reads as the client's brand,
the logo is rendered faithfully and not restyled, each image tile is the page's image and is
not distorted, spacing and hierarchy are clean, no garbled or invented text.

## Known limit

The current pipeline generates section images after the wireframes, so on a first pass most
slots are `planned` and appear as art-direction tiles. Where supplied assets or earlier
generations exist, the board shows the real files. To show final generated art on every board,
the image chain would have to run before the wireframes; that reorder is a pipeline decision,
not part of this stage.
