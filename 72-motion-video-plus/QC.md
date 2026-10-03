# Skill 72 QC

## Package / install QC

- Folder is exactly `72-motion-video-plus/` in the onboarding repo.
- `SKILL.md` top-level version equals `skill-version.txt`.
- Required references exist: authority-map, animation-contract, manifest-schema, brand-bible-template, fish-audio-tts, untested-alternatives.
- `assets/example-manifest.json` validates against `references/manifest-schema.json`.
- `bash verify.sh` exits 0.
- No em dashes anywhere in the skill files.
- Skill 72 is present in `skill-department-map.json` as client-facing.
- Primary owner is `video` / `video-editor`.
- Repo stamper/hash/repo-consistency gates pass after integration.

## Runtime QC (per run)

- Preflight ran and its worker/segment recommendation was followed.
- Preview gate: every scene approved at 960x540/15fps before full render.
- `scripts/tts.py` served-model check passed for every chunk (or the operator explicitly accepted `--allow-unverified`).
- Audio-first timing: manifest scene durations match `durations.json`.
- `scripts/qc.sh` exits 0: frame counts match, no zero-byte files, blackdetect and freezedetect clean, audio duration equals video duration.
- Contact sheet reviewed by a human (the 30-second review).
- `scripts/sweep-chromium.sh` ran; no orphaned headless browsers remain.
- Frame PNGs deleted; final MP4, animation sources, voiceover, script, and manifest kept in `motion-videos/<video-name>/`.

## Design QC

- Bright, human look: no dark-style designs, no generic AI-polished look.
- Real brand assets and real typography on screen.
- Voiceover delivery matches the brand bible voice notes.
- Music bed is continuous across the whole video with no seams at joins.
