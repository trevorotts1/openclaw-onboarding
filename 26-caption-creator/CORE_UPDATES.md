# Skill 26: Caption Creator - Core File Updates

## Core .md files this skill is allowed to update

- `TOOLS.md`
- `MEMORY.md`

## Update instructions (TYP-lean)

Add a short pointer only. Do not paste full documentation into core files.

### TOOLS.md
Add a short section called `Video Skills Suite` with pointers to:
- `~/.openclaw/skills/26-caption-creator/`

### MEMORY.md
Add a single pointer entry:
- `Skill 26: Caption Creator` docs live at `~/.openclaw/skills/26-caption-creator/`

### AGENTS.md (only if listed above)
If this skill touches AGENTS.md, add a short `Video QC` rule:
- After producing a video file, verify it exists and is playable
- Verify duration and resolution match the spec for the target platform
- If the file is missing audio when it should have audio, treat as FAILED
