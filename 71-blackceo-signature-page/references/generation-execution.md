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

## Composition

`stitch_sections.py` (wireframe full-page PNG) and `build_hybrid_board.py` (mockup board) are
the repo's own pinned composers. The executor runs them only in `kie` mode and only when their
own input records exist; both refuse to compose from inputs that do not pass their validation.
Stub mode never composes: a placeholder is not an approved input.
