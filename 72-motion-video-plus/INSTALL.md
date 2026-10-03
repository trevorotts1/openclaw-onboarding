# Install / Update Contract: Motion Video Plus (Skill 72)

## Install model

This skill is repository-native. It is intended to live at:

`72-motion-video-plus/`

inside `openclaw-onboarding` and be installed/updated by the repository's existing install/update mechanism. Do not invent a second installer just for this skill.

## Prerequisites (host)

- Node.js 18 or newer, with `playwright-core` installed and a Chromium build available to it.
- FFmpeg with libx264 (for encode, concat, xfade, sidechaincompress, blackdetect, freezedetect).
- Python 3 for `scripts/tts.py`.
- A Fish Audio API key in `FISH_AUDIO_API_KEY` (asked at install with a skip option; voiceover cannot run without it).
- Disk headroom: the preflight script measures and refuses plainly when the run does not fit.

## Required repository wiring

Follow `REPO-INTEGRATION.md`:

- add Skill 72 to `23-ai-workforce-blueprint/skill-department-map.json` using `repo-integration/skill-department-map-entry.json`;
- bind it to `video` / `video-editor` (primary), with `storyboard-pre-production-specialist` and `head-of-video-production` as secondary;
- refresh generated `Skills You Operate` blocks with the canonical stamper;
- rehash content and run repo-consistency gates.

## Skill-local verification

From this skill directory:

```bash
bash verify.sh
```

This checks package integrity, required references, script syntax (node, bash, python), the manifest schema against the example manifest, and the SKILL.md to skill-version.txt version lockstep.

This command is for install/update maintenance only. Normal runtime use does not begin by rerunning it.
