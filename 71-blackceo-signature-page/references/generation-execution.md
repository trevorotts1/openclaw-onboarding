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

## Composition

`stitch_sections.py` (wireframe full-page PNG) and `build_hybrid_board.py` (mockup board) are
the repo's own pinned composers, unchanged by this wire. The executor runs them only in `kie`
mode and only when their own input records exist; both refuse to compose from inputs that do
not pass their validation. Stub mode never composes: a placeholder is not an approved input.
