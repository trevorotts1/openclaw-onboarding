# Core Updates: Skill 72

Skill 72 uses the onboarding repo's **native skill invocation** mechanism rather than manually pasting a second hard-coded skill list into workspace core files.

Canonical binding:

`23-ai-workforce-blueprint/skill-department-map.json`

After adding the Skill 72 entry, run the repo's canonical stamper and fleet-standard generators described in `REPO-INTEGRATION.md`. Do not hand-edit the generated `SKILLS_YOU_OPERATE_V1` blocks.

No secret values belong in AGENTS.md, TOOLS.md, MEMORY.md, or this skill. The Fish Audio key is read from `FISH_AUDIO_API_KEY` at runtime, only by jobs whose resolved audio plan calls for Fish Audio narration, and never written to disk.

Installed managed guidance must match the shipped behavior: the
Skill 72 entry's description in the department map (and its
repo-integration mirror) describes the V2 governed pipeline (four
modes, two production renderers, model-agnostic authoring), and the
video roles' generated `Skills You Operate` blocks are refreshed by
the canonical stamper after any map change, never hand-edited.
`python3 scripts/check_authority.py` verifies the mirrors agree and
that no managed Skill 72 guidance carries the obsolete V1
description.
