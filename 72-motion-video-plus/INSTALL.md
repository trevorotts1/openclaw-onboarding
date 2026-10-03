# Install / Update Contract: Motion Video Plus (Skill 72)

## Install model

This skill is repository-native. It is intended to live at:

`72-motion-video-plus/`

inside `openclaw-onboarding` and be installed/updated by the repository's existing install/update mechanism. Do not invent a second installer just for this skill.

## Prerequisites (host)

- Node.js 18 or newer, with `playwright-core` installed. `playwright-core` ships no browser: acquire Chromium once with `npx -y playwright@latest install --with-deps chromium` (browsers land in `~/.cache/ms-playwright`, where `playwright-core` finds them; or set `PLAYWRIGHT_BROWSERS_PATH` to a custom location). Without this step, `scripts/render.js` fails on `chromium.launch()` and the client is stranded before step one.
- FFmpeg with libx264 (for encode, concat, xfade, sidechaincompress, blackdetect, freezedetect).
- Python 3 for `scripts/tts.py`, plus `numpy` (`pip install numpy` or `pip3 install numpy`) for `scripts/synth-score.py` and `scripts/synth-sfx.py`.
- The client's OWN Fish Audio API key, collected by the client's agent at first use into the client environment (`export FISH_AUDIO_API_KEY=...`). It is never written into the repo or the skill files. Voiceover cannot run without it.
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
