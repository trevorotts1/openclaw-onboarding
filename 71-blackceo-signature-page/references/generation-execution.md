# Generation execution path (the command that was missing)

Authority: `references/kie-generation-route.md` for the route. This file only names the
execution command and its input record.

`scripts/shared_page_service.py` admits a page; `scripts/stage_gate.py` checks and closes a
stage. Neither produces an image. `scripts/stage_executor.py` is the production command the
service's documented `--pipeline-command` seam expects, and it is the command a
`scripts/swarm_runner.py` `--worker-cmd` worker can run for one generation item.

## Command

```sh
# the four image stages, end to end (inert by default); final-mockups needs the page's
# approved Design Board, so run the first three, the image chain and the board before it
python3 scripts/stage_executor.py <run_dir> --provider stub

# the real route: Skill 74, one `run --mode active` per image
python3 scripts/stage_executor.py <run_dir> --provider kie --allow-paid

# one item, as a runner worker command (generic-shell runtime)
python3 scripts/stage_executor.py <run_dir> --stage image-generation-qc --item IMG-001
```

`--provider kie` refuses unless `--allow-paid` is passed AND `KIE_API_KEY` is set. The key is
never printed. Skill 74 is found at `--kie-adapter PATH`, else `SKILL71_KIE_ADAPTER`, else the
sibling `74-kie-live-adapter` skill; a missing adapter is a named failure.

## Production request

`<run_dir>/production-request.json`:

```json
{
  "model": "<id resolved by Skill 66>",
  "copy_version": "standard | long-form",
  "style": "<one-line direction>",
  "copy_version": "standard | long-form (optional here: read from intake.json when absent)",
  "references": ["/abs/path/reference-1.png"],
  "stage_prompts": {"desktop-wireframe": "... {section_name} ... {copy} ... {slots} ... {width} ..."},
  "input_extra": {"<field the live schema requires>": "<value>"},
  "sections": [
    {"section_id": "hero", "section_name": "Hero", "copy": "...",
     "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9", "art_direction": "..."}]}
  ]
}
```

Each stage writes its images into its own stage folder and one
`<stage>/stage-executor-record.json` naming the file, its SHA-256, the prompt hash, the
provider, the mode and the task id. Later stages attach the actual PNGs the earlier stages
wrote as input references. The record is not a gate receipt: it cannot close a stage, and the
gate's validators and reviewers still run against the artifacts.

## Section count contract

One request section per canonical copy section of the selected form, never
band-compressed: Standard 12, Long-Form 15 (`references/copy-specs/<copy_version>-v6.json`,
`sequence`; Section 5 may expand to 5A, 5B, 5C, which makes 17). The form comes from the
request's `copy_version`, else its `metadata.copy_version`, else `<run_dir>/intake.json`.
`stage_executor.py` refuses, by name and before any prompt is composed, a request whose
canonical section ids (`S02A`, `02A` and `2A` all read as `2A`) differ from that sequence,
from the request's copy source (`copy_source` file), or from `copy/copy-manifest.json`. A
free run with no declared form prints a NOTE and skips the check; a paid run
(`--provider kie`) refuses. `--preflight` prints `PREFLIGHT_SECTIONS` (form, count, ids) and one
`PREFLIGHT_CTA` per section.

`scripts/build_production_request.py` is the request builder for this path. It reads
`copy/internal-manuscript.md`, writes one section per canonical id with the section's public
copy, its single CTA label, optional image slots (`--slots`) and optional design prose packed
to the model's 95 percent target (`--design-prose`), and runs the same check on its own
output before writing; that check reads the run the manuscript belongs to (`--run-dir`, else
the parent of `copy/`), never the working directory, and prints what it was checked against.
A section's copy always ends on a finished sentence: a signature or chip label (8 words or
fewer) is listed apart in the section's `labels` and printed as its own LABELS line, so
unfinished prose is refused even when the cut lands on its own line. The builder lands every
section at or above the 16,000-character floor and refuses (naming the section) when the
supplied `--design-prose` is too thin; it warns when the shortest section is below the
19,000-character target. `--preflight` and a paid run (`--provider kie`) fail a prompt under
the floor (owner Decision 1); a stub run only warns. Templates may use `{section_total}` and
`{layout}` besides the placeholders listed under Production request.

## Prompt and geometry contract

The executor enforces four rules on every job before a paid call; `--preflight`
composes and checks them with no provider call and no file write.

1. **Verbatim copy first.** The section's `copy` is the first block and appears
   once, followed by the exact CTA label. The run's production prose is never
   inside the copy block.
2. **Incomplete copy is refused.** A copy string that carries style padding
   ("Preserve the measured band order", …) or ends mid-sentence fails by
   section name, because a paid render of truncated copy is a wasted call.
3. **Provenance is stripped.** Local paths, reference filenames, hashes and the
   reference raster's absolute pixel size are removed; measured ratios and
   design tokens stay. The prompt states the target ratio and the full-frame
   contract (one section, no blank bands, no letterboxing).
4. **One section in, one section out.** Each job receives only the same-index
   slices of earlier stages, same platform first. It never receives every
   section at once, and its ratio is derived from its pixel-mate and snapped to
   the route's ratio enum (`RATIO_ENUM`), not one fixed 3:4 for all parts.
5. **Reference images are structure only.** Every job that attaches reference images carries the
   labelled `REFERENCE IMAGE - structure only` block (what to take, what never to take, who owns
   color, logo, imagery and copy), and every delivered image of a paid run is checked for the reference's palette and
   brand text and recorded as `reference_bleed` (recorded, not yet gating; see the reference doc). The contract, the media-library links and the check are `references/reference-image-use.md`.

## Wireframe stages: style reference and build spec

`desktop-wireframe` and `mobile-tablet` jobs are driven by
`references/wireframe-build-spec.json` through `scripts/wireframe_spec.py`.
Two things are fixed there, not left to each request:

1. **One style reference, chosen by stage and form.** The form is the
   request's `copy_version` (else `metadata.copy_version`, else the run's
   `intake.json` `copy_version`, which the executor reads when the request does
   not repeat it, else inferred from the section ids; a paid run never guesses). Desktop sends
   `chatgpt-wireframe-1` (Standard) or `chatgpt-wireframe-3` (Long-Form); mobile
   sends `chatgpt-wireframe-4`, and for Standard also the rule "true
   single-column phone stack, never side-by-side rows". The sheet travels as a
   standing-file link (the bundled file's public repository URL, per
   `references/kie-generation-route.md`) and is first in attach order. The
   greyscale Set for Life wireframe is never a wireframe style reference: a
   request whose `references` list it is refused by name before any prompt is
   composed. `--preflight` prints `PREFLIGHT_WIREFRAME_REFS` with the form and
   every reference the job sends; the stage-executor record's `inputs` is the
   merged list actually sent. Which file is which, and why:
   `assets/visual-standards/README.md`.
2. **An annotated build-spec prompt block** (section chip and name tab, inline
   type specs, image plates labelled with ratio and art direction, filled
   primary CTA with microcopy, contiguous bands, widths header strip on the
   first slice, one behaviour note, the pain and solution pair rule for
   Long-Form, one continuous founder letter, and the example flaws not to
   copy) is prepended to the stage's prose. It names no hex colour: the
   client's colours come from the `BRAND COLORS` line of the same prompt,
   which `scripts/brand_colors.py` supplies (sigpage-brand-colors, R69, is a
   required prerequisite of this change: merge it first). A request without a
   stage template still carries `request.style` as a `STYLE DIRECTION` line, and
   a paid (`--provider kie`) wireframe job whose composed prompt has no
   `BRAND COLORS` line is refused before any call. A request template that asks
   for a colourless sheet ("warm grey line work on ivory", "no colour fill" about
   the sheet) is refused by name; the same words in a negated sentence ("never
   grey line work") or about image plates ("plates are neutral grey with no
   colour fill") restate the spec and pass. A section may carry `type_specs` and
   `behavior_notes`; otherwise the house default scale and a CTA-derived note
   are printed. A slot `aspect_ratio` outside the one list in
   `wireframe-build-spec.json` `ratio_labels` (every `RATIO_ENUM` ratio plus the
   designed and substituted 2:1, 1:2, 3:1, 1:3, 9:21, 4:5 and 5:4, the same list
   W3 uses) is refused; a label that is not reduced or is invented (3:9) never passes.

Canvas geometry is per-image. `target_ratio()` derives each job's ratio from
its pixel-mate (or the section's slot), and the record carries
`requested_ratio` and `actual_pixels`; a delivered image more than 2% off the
requested ratio is recorded as `geometry_mismatch` and printed as a named
warning.

The assembly scripts `stitch_sections.py` and `build_hybrid_board.py` are
unchanged by this wire: they were already content-height. No assembly-canvas
fix is claimed here or in this change's history.

## Color: hypersaturation, built in

Trevor's order: the images are hypersaturated, always in the client's brand colors. The
executor adds two blocks, both from `scripts/hypersaturation.py` and filled from the run's
resolved client palette (never a default, never another client's colors):

- `visual-mockup` and `final-mockups` prompts carry the **PAGE COLOR SYSTEM** block (this
  section's ground, the hero, dark, light and accent slots, the rules) and the **IMAGE COLOR
  GRADE** block. Both are counted in `contract_chars`; `hypersaturation_chars` reports their
  size, and `--preflight` prints `PREFLIGHT_HYPERSAT` per prompt.
- every image-inventory item prompt (`--item`) gets the **IMAGE COLOR GRADE** block unless it
  already carries one, and is refused rather than trimmed if prompt plus block passes the model
  maximum.

Hypersaturation is never optional, and never against the client's palette. The executor
**refuses** (`REFUSED` in `--preflight`, `FAIL` otherwise, exit 1) a `visual-mockup`,
`final-mockups` or `--item` prompt when:

- no client palette resolves. The fallback reads the brand file the way the stage gate does
  (`private/brand.json`, else `intake.json` `brand_file`, else the skill's bundled file) and
  requires the file's `brand_id` to match `intake.json` `brand_owner`; a missing, unreadable or
  other-client file resolves nothing. Once `scripts/brand_colors.py` is on main it is the resolver.
- the design prose (the request's `stage_prompts` text, or the item prompt) carries any `#hex`
  that is not one of the client's palette colors (`hypersaturation.foreign_hexes`). A builder
  must delete old or example palette text; the PAGE COLOR SYSTEM block carries the palette.

The rules and evidence are `references/hypersaturation-framework.md`; the page-level pixel
check is `scripts/validate_page_color.py`.

## Design board (stage `design-board`)

`--stages design-board` produces the page's Design Board (`references/design-board.md`): one
4:3 image, the client logo and all of the page's real section images attached as references (a
page with more than fit is attached as individual images plus one contact sheet of the real
files), the resolved palette and the contract blocks in the prompt. The request-level
`references` above are not sent with it: the call carries exactly the logo and the page's images.
It runs alone, after the image
chain, and refuses a page with any image slot that has no file yet. `--preflight` composes and
checks it for free, and the stub board never validates. `final-mockups` refuses to start (preflight
included, and before any call in a multi-stage run) until `design_board.py gate` passes (a current
recorded client approval of the board's images, palette and file). The wireframe, mobile,
layout-proof stages and item mode are not gated by the board: they come before it.

## Composition

`stitch_sections.py` (wireframe full-page PNG) and `build_hybrid_board.py` (mockup board) are
the repo's own pinned composers, unchanged by this wire. The executor runs them only in `kie`
mode and only when their own input records exist; both refuse to compose from inputs that do
not pass their validation. Stub mode never composes: a placeholder is not an approved input.
