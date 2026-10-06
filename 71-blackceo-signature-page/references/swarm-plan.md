# Skill 71 Swarm Plan

One agent = one item. Reviewers start as soon as their item lands, never after
the whole batch. The orchestrator learns results only from
`scripts/stage_gate.py check/close` output — never from an agent's chat reply
(see D3 in the enforcement order). No re-read or recovery lanes.

Every agent writes its receipt to `private/receipts/<stage>.json` and its files
to the run folder. The gate re-runs every validator itself at `close`.

| Stage | Fan-out |
|---|---|
| `copy` | 1 writer -> 1 independent reviewer |
| `font-action-plan` | 1 |
| `desktop-wireframe` | 1 layout lead writes the section plan -> 1 renderer per wireframe part, in parallel -> 1 reviewer |
| `mobile-tablet` | same pattern as desktop |
| `visual-mockup` | 1 agent writes `page-visual-bible.json` first -> then desktop mock renderer and mobile mock renderer in parallel |
| `image-inventory-prompts` | starts as soon as `visual-mockup/page-visual-bible.json` exists (stage contract `requires_artifacts`), in parallel with the mock renderers: **1 prompt writer per image**; each prompt's reviewer starts when that prompt passes `scripts/validate_prompt.py` |
| `image-generation-qc` | **1 generation agent per image** (never fixed-size chunks), shared limiter of 20 createTask submissions per 10 seconds per account (rule 3), every submission through Skill 74; each image's QC reviewer starts when that image lands |
| `image-map-upload` | 1 |
| `final-mockups` | desktop and mobile in parallel |
| `responsive-html` | 1 builder -> then in parallel: `validate_page.py` + `compare_sheet.py` (scripts) and 1 independent visual reviewer |
| `report` | `scripts/stage_gate.py report` — no agents |

Reading lists per stage come from `references/stage-contract.json`'s `reads`
field. Agents load only what that field lists (order D2) — never the full
100-400 KB guides unless the stage's `reads` names them.

Stage-contract notes:
- `image-inventory-prompts.depends_on = ["mobile-tablet"]` and
  `requires_artifacts = ["visual-mockup/page-visual-bible.json"]`.
- `image-generation-qc` per-image work may start per image as prompts pass,
  but the stage closes only when all images pass.
