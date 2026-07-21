# Skill 25: Video Creator - CORE_UPDATES

## Core .md files this skill is allowed to update

- `TOOLS.md`
- `MEMORY.md`

Do NOT update any other core files for this skill unless the user explicitly requests it.

## What to add (exact text)

### TOOLS.md
Add this section:

```md
## Video Skills Suite

### Video Creator (Skill 25)
- Location: `~/.openclaw/skills/video-creator/`
- Purpose: generate and assemble videos (for example: text to video, image to video, multi-clip assembly)
- Primary provider: KIE.ai (uses `KIE_API_KEY`)
- Default outputs: text-to-video writes a prompt/timestamp filename in the current working directory; script-to-video writes beside the input script; multi-clip assembly writes `assembled.mp4` in the current working directory.
```

### MEMORY.md
Add this pointer:

```md
## Video Skills Suite
- Video Creator (Skill 25): `~/.openclaw/skills/video-creator/`
```
