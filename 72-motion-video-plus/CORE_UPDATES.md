# Core Updates: Skill 72

Skill 72 uses the onboarding repo's **native skill invocation** mechanism rather than manually pasting a second hard-coded skill list into workspace core files.

Canonical binding:

`23-ai-workforce-blueprint/skill-department-map.json`

After adding the Skill 72 entry, run the repo's canonical stamper and fleet-standard generators described in `REPO-INTEGRATION.md`. Do not hand-edit the generated `SKILLS_YOU_OPERATE_V1` blocks.

No secret values belong in AGENTS.md, TOOLS.md, MEMORY.md, or this skill. The Fish Audio key is read from `FISH_AUDIO_API_KEY` at runtime and never written to disk.
