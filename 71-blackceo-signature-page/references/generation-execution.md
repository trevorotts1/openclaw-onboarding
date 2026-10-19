# Generation execution path (the command that was missing)

Authority: `references/kie-generation-route.md` for the route. This file only names the
execution command and its input record.

`scripts/shared_page_service.py` admits a page; `scripts/stage_gate.py` checks and closes a
stage. Neither produces an image. `scripts/stage_executor.py` is the production command the
service's documented `--pipeline-command` seam expects, and it is the command a
`scripts/swarm_runner.py` `--worker-cmd` worker can run for one generation item.

## Command

```sh
# the four image stages, end to end (inert by default)
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
  "style": "<one-line direction>",
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

## Composition

`stitch_sections.py` (wireframe full-page PNG) and `build_hybrid_board.py` (mockup board) are
the repo's own pinned composers, unchanged by this wire. The executor runs them only in `kie`
mode and only when their own input records exist; both refuse to compose from inputs that do
not pass their validation. Stub mode never composes: a placeholder is not an approved input.
