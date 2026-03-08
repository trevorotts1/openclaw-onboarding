# Skill 27: Video Editor - Core File Updates

## Core .md files this skill is allowed to update

- `AGENTS.md`
- `TOOLS.md`
- `MEMORY.md`

## Update instructions (TYP-lean)

Add a short pointer only. Do not paste full documentation into core files.

### TOOLS.md
Add a short section called `Video Skills Suite` with pointers to:
- `~/.openclaw/skills/27-video-editor/`

### MEMORY.md
Add a single pointer entry:
- `Skill 27: Video Editor` docs live at `~/.openclaw/skills/27-video-editor/`

### AGENTS.md (only if listed above)
If this skill touches AGENTS.md, add a short `Video QC` rule:
- After producing a video file, verify it exists and is playable
- Verify duration and resolution match the spec for the target platform
- If the file is missing audio when it should have audio, treat as FAILED
