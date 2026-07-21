# Changelog — video-creator (Skill 25)

## [6.6.1] - 2026-07-21 — feat: document Agnes Video 2.0 as an optional alternative generator

### Added
- **Agnes Video 2.0 documented as an OPTIONAL alternative generator** in `SKILL.md`. KIE.ai (VEO)
  stays the default/primary provider (`--provider kieai`); Runway, Pika, mock, and local are
  unchanged (additive only — no existing instruction reworded or downgraded). Agnes ships as its own
  skill (model `agnes-video-v2.0`, asynchronous create+poll at
  `https://apihub.agnes-ai.com/v1/videos` → `/agnesapi?video_id=…`); there is deliberately **no
  `--provider agnes` flag** — the raw Agnes clip is brought back into this skill for assembly/export.
- **Tier behavior is operator-set, not hardcoded.** The SOP reads the box's Agnes plan from an
  operator-set config value (e.g. `AGNES_TIER`) and treats HTTP 429 backoff + the account console as
  the live rate-limit source of truth, because Agnes publishes quotas as non-contractual, mutable
  reference values. Notes that paid tiers do not raise image/video throughput. Credential
  `AGNES_AI_API_KEY` (already provisioned fleet-wide) is checked SET/NOT-SET only, never printed.

## [6.6.0] - 2026-07-21 — fix: fail closed on unmet requests (no silent substitution, dropping, or partial output)

### Fixed (root cause — the skill reported success while delivering something other than what was requested)
- **Real-provider failure no longer becomes a placeholder.** `text_to_video.py` deleted
  `create_placeholder_video()` entirely; a provider exception now raises and the CLI exits
  nonzero instead of printing "Video ready" over a MoviePy title card. `--provider mock`
  remains a supported explicit keyless mode.
- **Downloaded provider output is validated before it is published.** `ai_providers._download_video`
  streams to a temp file and requires a `video/*` Content-Type, a non-trivial payload, and a
  successful `ffprobe` decode with a positive duration before `os.replace` publishes it. An HTML
  error page returned by a provider was previously saved and reported as the video.
- **Failed scenes abort the render.** `script_to_video.py` collects failed scene numbers and
  raises rather than concatenating the survivors and reporting the partial video complete.
- **Script directives can no longer be parsed and discarded.** `VOICEOVER`, `BGM`, `TRANSITION`,
  `IMAGE`, and unknown `NAME:` directives are rejected with the scene number and "No video was
  generated". `sample_script.txt` and `EXAMPLES.md` no longer bundle unsupported directives.
- **Selected image and avatar providers cannot degrade to a local renderer.** `image_to_video.py`
  and `avatar_video.py` no longer catch provider errors and fall back; unimplemented
  provider methods raise `NotImplementedError`.
- **Multi-clip assembly requires every requested clip.** Missing and undecodable inputs are
  collected and raised instead of skipped, so a reduced montage is never reported ready.
- **Requested audio must resolve.** `add_music.py` raises when a music file, a genre, or a
  voiceover is unavailable rather than returning the unchanged video; `--music` and `--genre`
  are mutually exclusive. Also adds `from __future__ import annotations`, which fixes a
  module-level `NameError: AudioFileClip` that made `add_music.py` and `template_video.py`
  fail to import at all.
- **Templates validate before rendering.** Required fields, referenced image/audio/music files,
  and unsupported keys are all checked up front; no fabricated `'Product'` / `'Learn More'`
  defaults. `template_video.py --output` is now honored instead of ignored.
- **Accepted-but-ignored options removed or enforced.** `script_to_video.py` dropped `--template`
  and `--chapters`; `--seed`/`--negative-prompt` are rejected for providers that do not support them.
- **Batch export reports the truth.** `export.py --batch` exits nonzero when any individual export
  fails or when nothing matched, and rejects `--output` and non-directory input.
- **Quality presets are honored end to end.** Script presets map to real provider resolution tiers,
  scene clips are normalized to the requested canvas, and `ffprobe` verifies the encoded
  dimensions. `--quality social` previously requested 1080x1920 and silently encoded 1920x1080.
- **Only deliverable transitions are advertised.** `crossfade`, `zoom_*`, `flip_*`, `spin`, and
  `pixelate` were removed rather than aliased to a fade. `slide_*` was likewise removed: MoviePy's
  `concatenate_videoclips(method="compose")` re-applies `set_position('center')` to every clip
  (`moviepy/video/compositing/concatenate.py:98`), discarding the animation `slide_in` installs, so
  all four directions rendered byte-identical frames and the requested direction was never
  delivered. The retained `wipe_*` effects are frame-verified distinct from fade AND from each other.
- **Install QC accepts the documented keyless configuration.** `qc-video-creator.sh` keys off
  `VIDEO_CREATOR_PROVIDER`: `mock`/`local` pass without any API key, a selected real provider
  requires its own key, and an unset value warns instead of failing.
- **Version and output-path documentation match reality.** `scripts/__init__.py` derives
  `__version__` from `skill-version.txt`; `CORE_UPDATES.md`/`QC.md` list the actual per-command
  output defaults instead of the nonexistent `~/Videos/Output/`.

### Added
- `tests/` — 93 contract tests covering provider, media, script/template, transition, QC, and
  static-documentation failure contracts, including pairwise distinctness for every advertised
  transition so an advertised variant can never silently collapse onto another.

## [6.5.7] - 2026-06-30 — fix: re-sync the installed `video-creator` copy on every update (skill-root wire.sh) + drift stamp

### Fixed (root cause — same class as skill 44's `caf` drift)
- The routine update path never reconciled the INSTALLED skill. `update-skills.sh`'s
  wiring loop walks only NUMBERED skill dirs (`[0-9]*/`, update-skills.sh:1617) and runs a
  skill installer only when one is found at the skill ROOT (`wire.sh > install.sh >
  scripts/install.sh > setup-*.sh`, update-skills.sh:1631-1646). Skill 25 does NOT install in
  place: per INSTALL.md it COPIES the whole skill into an UN-numbered
  `~/.openclaw/skills/video-creator/` (the runtime location named by TOOLS.md /
  CORE_UPDATES.md / qc-video-creator.sh) and builds a local `venv` with pinned deps. The loop
  re-syncs the numbered SOURCE but never re-copies the un-numbered runtime copy and never
  rebuilds its venv — so the installed `video-creator` silently drifted behind the synced
  source fleet-wide (source on disk != working install).

### Added
- `wire.sh` at the skill root: idempotent, fail-soft (re)sync that the wiring loop DOES pick up.
  Copies the skill source into `~/.openclaw/skills/video-creator/` (additive, mirrors
  INSTALL.md's `cp -r`), creates/keeps the `venv`, pip-installs the pinned runtime
  (`moviepy==1.0.3 opencv-python requests pillow numpy`), makes the scripts executable, and
  writes the `.installed-from` drift stamp. Fast no-op when the stamp version already matches
  AND the venv python can `import moviepy.editor` (which also catches the documented MoviePy
  v1-vs-v2 hazard, since v2 removed that module). Always exits 0; no bare `gws`; no destructive
  ops; honours `VIDEO_CREATOR_DIR` / `VENV_DIR` / `PYTHON` overrides for tests.
- Registered `video-creator` in `scripts/tool-drift-check.sh` (repo root scripts/): reads the
  `.installed-from` stamp, compares to this `skill-version.txt`, and capability-probes the
  copy's own venv python with creds-free `import` checks of the pinned deps. Read-only; prints
  (never runs) the rebuild command unless `--rebuild` is passed.

### Notes
- `skill-version.txt`: `v6.5.6` → `v6.5.7` (required by CI guard G3 — skill-dir content changed).
- Global version markers (`/version`, `install.sh`/`update-skills.sh` ONBOARDING_VERSION, root
  CHANGELOG header) are intentionally NOT touched here — the operator rolls them with
  `scripts/bump-version.sh` at merge.
