# Reference image use: structure only

Owner order (Trevor, 2026-10-19): give the generating agent the reference image as a link, with a
structure for how to use it. Use the reference to understand the look and structure we are going for;
never copy its style, its color scheme, or anything else that belongs to that example. This file is
that structure, and it is permanent: every stage that attaches a reference image carries it.

## The rule in one line

A reference image teaches **structure**. It never supplies **style or identity**. Everything that makes
the output this client's own comes from the client.

## Where the references live

Each reference has a public link in the operator's GoHighLevel media library (BlackCEO LLC, folder
`sigpage-reference-images`), recorded with its SHA-256 and its fingerprint in
`references/reference-library.json`. Request builders take links from that file
(`reference_use.library_urls("design-board")`), never from a one-off upload.

| name | kind | what it teaches |
|---|---|---|
| `design-board-example` | design-board | the look and structure of a brand design board: panel arrangement, hierarchy, density, polish |
| `set-for-life-desktop-wireframe` | wireframe | block structure, annotation style and section rhythm of a long-form page |
| `set-for-life-desktop-mockup` | mockup | how a finished long-form page is composed: framing, whitespace, polish |

The previous transport for these images was the KIE tempfile upload (`tempfile.redpandaai.co`, via the
Skill 74 adapter). That host is a short-lived generation transport, not the operator's library. A
reference that is not in the library is reported by `--preflight` (`PREFLIGHT_REFERENCES ...
not_in_library=N`) and the QC check returns UNDETERMINED for it.

## The contract block (verbatim from `scripts/reference_use.py`)

Every composed prompt for a job that attaches reference images carries a section labelled
`REFERENCE IMAGE - structure only`, placed after the verbatim copy and before the frame contract:

- **TAKE:** layout grid and block arrangement; section order and rhythm; information hierarchy; density
  and whitespace balance; composition and framing; how blocks are annotated or grouped; overall level
  of polish.
- **NEVER take:** its color palette or gradients; font styling; logo; brand names, taglines or any copy;
  people, photography subjects or icons; any client identity.
- **Owners:** colors come only from this client's resolved brand palette; the logo only from this client;
  imagery only from this client's selected images; every word only from this client's copy. Where the
  reference and the client differ, the client wins.
- **Self-check:** if any part of the output could be mistaken for the reference's brand, redo it.
- **Attach order:** the request-level references are the first attached images, and the block says how
  many. Any further attached images are this page's own earlier-stage slices, which are the layout
  source for that job.

The block is about 1,000 characters and counts against the model's prompt budget next to the copy and the
other contract blocks. Builders must compose their design prose through `stage_executor.stage_prompt`
with the request's `references` set, so the budget they fit to already includes the block.

## Request fields

| field | meaning |
|---|---|
| `references` | media-library links, first in attach order (existing field) |
| `reference_roles` | optional, same order, lowercase words such as `design-board`, `wireframe`, `mockup`; named in the block |
| `client_palette` | optional list of the client's resolved hex colors; used by the QC check so a client who owns a color is never flagged for it |

## Where it is wired

- `scripts/stage_executor.py` `stage_prompt()` adds the block to every stage prompt that has references
  (desktop-wireframe, mobile-tablet, visual-mockup, final-mockups), and counts it in `contract_chars`.
- `run_item()` prepends the block to image-inventory item prompts when the request carries references,
  and refuses an item whose prompt plus block is over the model maximum.
- `--preflight` prints `PREFLIGHT_REFERENCES total= library= not_in_library= roles=` once.
- `run_stage()` and `run_item()` both run the QC check on every delivered image of a paid (kie) run
  (stage images, and the `Image-NN.png` items that go on the page) and record it as `reference_bleed`
  in `stage-executor-record.json` (per image, or per item), with a named `WARN reference_bleed` line when
  the result is not PASS. A stub run or a request with no references records nothing. An image the check
  cannot open records `UNDETERMINED`; it never aborts the stage and never loses the records of images
  already paid for.
- **Enforcement status: recorded, not yet gating.** Nothing in `stage_gate.py`, `qc-contract.md` or the
  reviewer instructions reads `reference_bleed` today. Until the gate reads it (a follow-up in the files
  the brand-colors and Design Board lanes also edit, so it lands in the batch merge), the reviewer reads
  the record and the WARN line by hand, and treats a `reference_bleed` that is not PASS as a failed image.
- **Design Board stage (R71, Design Board unit):** the stage calls
  `reference_use.reference_block(request["references"], request.get("reference_roles"))`, puts it in its
  prompt, attaches the board link first, and runs `reference_use.check(...)` on the board it generates. The
  board's client-specific content (palette, type, imagery, icons, copy) comes from the client's resolved
  brand and selected images, exactly as the contract states. No second wording of the rule is allowed.

## The QC check: outputs must not reproduce the reference's palette or brand text

`python3 scripts/reference_use.py check OUTPUT.png --reference <library url> [--client-palette '#hex,#hex'] [--text-file F] [--no-ocr]`

Exit 0 PASS, 1 FAIL, 3 UNDETERMINED. It never reports PASS for something it could not check.

1. **Palette.** The reference's declared `signature_palette` (hex codes printed on the board, chromatic
   colors only; ivory and near-black cannot be bled) minus any color the client owns. The output's pixels
   within RGB distance 36 of each remaining color are measured. FAIL when one color covers 8% or more,
   when the colors together cover 10% or more, or when four or more of them are each present at 1% or more
   (the palette recombined).
2. **Brand text.** The reference's `brand_text` strings (brand name, taglines, headlines, copy) searched in
   the output's text, normalized for case and punctuation. The text is the OCR of the image (tesseract),
   or `--text-file` (a transcript, the composed prompt, the page copy).
3. **UNDETERMINED, never PASS:** a reference with no fingerprint in the library; OCR unavailable on this
   host; no OCR and no text supplied (the text leg never ran); an output that is not a file.

Measured on the bundled standards: the Set for Life mockup (the reference's own brand) FAILs at 33% to 77%
coverage; an unrelated sales page with a different green PASSes at 6% on the nearest color; a fixture that
reuses the board palette FAILs; a fixture in another palette PASSes; a client that owns the palette PASSes.

Known ceiling: bleed below about 5% of pixels (a photo-heavy slice with a few reference-colored accents)
passes the pixel test and is the reviewer's side-by-side leg. Text matching is exact after normalization,
so an OCR misread can hide a match. Both thresholds are named constants in `reference_use.py`.

## Adding a reference

1. Upload it to the operator media library (`~/.claude/skills/spec-protocol/scripts/ghl-media-upload.sh`,
   folder `sigpage-reference-images`; HEAD the URL and compare a re-download byte for byte).
2. Add an entry to `references/reference-library.json`: name, kind, use, url, sha256, bytes, origin,
   `signature_palette` (its chromatic colors, with the source of the list) and `brand_text` (every brand
   string it prints).
3. Add it to `reference_roles` in the request. Nothing else changes: the block and the check read the
   library.
