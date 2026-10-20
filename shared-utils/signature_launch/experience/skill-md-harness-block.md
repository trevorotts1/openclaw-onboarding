<!-- HELD FOR STEP C: the integrator pastes everything between the markers into 49, 71 and 83 SKILL.md, replacing <SKILL_DIR> with the skill's folder name. Nothing else in this file is pasted. -->
<!-- HARNESS-EXPERIENCE:BEGIN -->
## Harness experience (Claude Code, claude-nine, OpenClaw)

The client gets the same questions, the same answers file and the same delivery report in every harness. Only the way we ask differs: Claude Code and claude-nine use the structured question tool; OpenClaw asks one short numbered chat message at a time and waits. Setup and exact commands: `<SKILL_DIR>/adapters/<harness>/README.md` (harness is `claude-code`, `claude-nine` or `openclaw`). Shared code: `shared-utils/signature_launch/experience/`. If the client says "I'm not sure" or "help", use the help path (colours from logo or website, three suggested palettes, then a safe default flagged "to confirm"); the build never blocks silently and every default is reported at delivery.
<!-- HARNESS-EXPERIENCE:END -->
