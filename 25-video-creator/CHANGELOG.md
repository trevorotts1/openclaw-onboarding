# Changelog — video-creator (Skill 25)

## [7.0.4] - 2026-10-06 — fix: enforce per-model KIE input types; explicit image field type

### Fixed
- **Per-model input types** (`KIE_INPUT_SPECS` in `ai_providers.py`, from each mapped model's KIE docs page input
  schema): `duration`, `resolution`, `aspect_ratio`, `seed`, `mode`, `quality` are coerced to the documented type and
  enum before sending. Examples: Kling v2.5 turbo and Gemini Omni `duration` is a string (`"5"`), MiniMax H3 `duration`
  is an integer 4 to 15, `resolution` uses each model's own spelling (`1080P`, `2K`, `4k`), and Pixverse takes
  `quality` (Skill 25's resolution option is renamed). Invalid values fail BEFORE any HTTP call (including before the
  image upload) with a message naming the allowed values. Documented-required inputs the client cannot know (for
  example `mode`/`sound`/`multi_shots` on kling-3.0/video, `quality` on Pixverse) fail the same way and are supplied
  with `input_extra` / new CLI `--input-extra '{"key": value}'` (also on `text_to_video.py`). Models not in the table
  pass through unchanged.
- **`--image-field` no longer guesses the type from a trailing "s".** New `--image-field-type string|array`
  (`image_field_type=` in code); required with `--image-field` unless it names the model's own mapped key.
- CI: the Skill 25 workflow job and step names no longer hard-code a test count (the 93-test anti-vacuity floor stays).

## [7.0.3] - 2026-10-05 — fix-forward of #1498: correct image field per model

### Fixed
- Image-to-video sent `input.image_urls`, which is not an input of the default model `wan/3-0-video` (its schema at
  docs.kie.ai/market/wan/3-0-video takes `first_frame_url` as a single string, plus `last_frame_url` and
  `reference_image_urls[]`). The image field is now chosen per model from what Skill 67 and the KIE docs establish:
  `first_frame_url` (string): wan/3-0-video, wan/3-0-video-prime, wan/2-7-image-to-video, bytedance/seedance-2-5,
  bytedance/seedance-2-mini, minimax-h3/image-to-video. `image_url` (string): kling/v2-5-turbo-image-to-video-pro.
  `image_urls` (list): kling-3.0-omni/image-to-video, kling-3.0/video, pixverse-v6/image-to-video,
  happyhorse-1-1/image-to-video, happyhorse/image-to-video, gemini-omni-video. Each is read from the model's KIE docs
  page (source table in `ai_providers.py`). runway and veo3* use dedicated APIs and fail with a clear error; any other
  model fails before any HTTP call with an error naming the model. `image_field` (CLI `--image-field`) overrides.
- Tests updated and extended (established models, unknown model, override wins).

## [7.0.2] - 2026-10-05 — fix: replace dead KIE video endpoint with live createTask flow

### Fixed (root cause — the default `kieai` video path could never work)
- **Evidence (live probe 2026-10-05, with known-good and fake-path controls):** `POST https://api.kie.ai/v1/video/generate`
  (what `scripts/ai_providers.py` posted to) returns **HTTP 404 under both the `/v1` and `/api/v1` prefixes**; the control
  (a known-live KIE route) answered normally and a fabricated path also 404'd, so the endpoint is dead, not the probe.
  The old payload also carried **no model id**, and `_image_to_video_kieai` raised `NotImplementedError`.
  `text_to_video.py` defaults to `--provider kieai`, so Skill 25's default video path failed on every box.
- **Text-to-video and image-to-video now use KIE's live unified job API:** `POST /api/v1/jobs/createTask`
  `{model, input:{...}}` -> `data.taskId`, then `GET /api/v1/jobs/recordInfo?taskId=` (states
  waiting/queuing/generating/success/fail) with 3 s start and backoff to 15 s and a 900 s deadline. The body `code` is
  checked on every call (HTTP 200 with code 402/429 is an error, not success). Results are read from
  `data.response.resultUrls` or the parsed `data.resultJson`, then downloaded and ffprobe-validated immediately
  (existing `_download_video`).
- **Local images are uploaded** to `https://kieai.redpandaai.co/api/file-stream-upload` (multipart, `uploadPath`
  `video-creator/inputs`) and `data.downloadUrl` is sent in `input.image_urls`.
- **Model is never invented here:** it comes from Skill 67's selector (`67-kie-video/scripts/select_video_model.py`), located
  as a sibling of the skills dir (`<skills>/67-kie-video`, then `~/.openclaw/skills`, `/data/.openclaw/skills`). If Skill 67 is
  not installed the call fails with an actionable error before any HTTP. New `--model` on `text_to_video.py` and
  `image_to_video.py` (KIE only): an explicit model id always wins and is sent unchanged. `--resolution` is mapped to the
  spelling in Skill 67's `models.json` for that model.
- **Key resolution** goes through the shared canon (`shared-utils/key_resolver.py`, service `kie`) with the previous
  `KIE_API_KEY` / `KIEAI_API_KEY` environment read as fallback. Auth failures (401/403) stop after one attempt, never loop.
- Legacy `https://api.kie.ai/v1` endpoints in old `config.json` files are replaced by `https://api.kie.ai/api/v1`.
- Runway, Pika, mock, local, and all non-KIE behavior are unchanged.

### Notes
- Skill 74 (`74-kie-live-adapter`, landing separately) is the intended shared KIE transport. Skill 25 does not import it;
  this fix is self-contained so the default path works today. Migrate to Skill 74 when it ships.
- Not rebuilt: `video-creator.skill` (zip). It has been stale since 2026-03 (no CHANGELOG, tests, or `wire.sh`, and an older
  `ai_providers.py`); installs copy from the numbered source via `wire.sh`, and no gate compares the zip to the sources.
  Rebuilding would be an unrelated repackaging of the whole skill.
- `style` is not a KIE input and is no longer sent; `seed`, `negative_prompt`, `aspect_ratio` are sent only when supplied.
  The image field for image-to-video defaults to `image_urls` (Skill 67 registry convention); override with `image_field`.

### Added
- `tests/test_kie_live_flow.py` (30 tests, fake HTTP transport): createTask payload, poll states/backoff/timeout, body-code
  errors, auth stop, upload, explicit-model passthrough, missing Skill 67, key resolution.

## [7.0.1] - 2026-09-28 — fix: venv out of the skill root + no duplicate SKILL.md registration

### Fixed (root cause — OpenClaw's skill scanner walked the runtime copy's venv on every rescan)
- **`wire.sh`'s venv now lives OUTSIDE every skill root.** It previously built its ~215 MB venv at
  `<VC_DIR>/venv`, inside `~/.openclaw/skills/` (VPS: `/data/.openclaw/skills/`). OpenClaw's skill
  discovery walks every skill root up to depth 6 on every rescan, skipping only dot-prefixed names
  and `node_modules` — never `venv` — so that tree got walked on every scan. The venv now defaults to
  `$(dirname "$SKILLS_PARENT")/venvs/video-creator` (Mac `~/.openclaw/venvs/video-creator`, VPS
  `/data/.openclaw/venvs/video-creator`), still overridable by `VENV_DIR`.
- **Idempotent migration, not a rebuild.** A legacy `<VC_DIR>/venv` is `mv`'d to the new location
  (fast, no reinstall); if both exist, the new one wins when its python can `import moviepy.editor`,
  otherwise the legacy one replaces it. A venv relocated by `mv` (by this fix, or already moved by
  hand before it existed) keeps a stale `bin/activate`/`bin/pip` pointing at the old path — wire.sh
  now repairs `bin/activate` in place with `python -m venv --without-pip` and always invokes pip as
  `"$VENV_DIR/bin/python" -m pip`, never bare `pip` or `source activate`.
- **No more duplicate `video-creator` skill registration.** The runtime copy carried its own
  `SKILL.md`, identical to this skill's, so OpenClaw registered `video-creator` twice and logged a
  precedence collision on every scan. The copy step now excludes `SKILL.md`, `venv`, and `.venv`; any
  stale `<VC_DIR>/SKILL.md` from an older install is removed on every pass.
- **Docs and the drift-check registry updated to match:** `INSTALL.md`, `QC.md`, `INSTRUCTIONS.md`,
  `SKILL.md`, `CORE_UPDATES.md`, and `scripts/tool-drift-check.sh`'s `video-creator` probe path.

### Added
- `tests/test_wire_contracts.py` — hermetic (no network, no pip) coverage of the migration: legacy
  venv only, both present with a healthy new one, both present with a broken new one, and proof the
  runtime copy gets neither a `SKILL.md` nor a copied venv.

## [7.0.0] - 2026-07-21 — feat: document Agnes Video 2.0 as an optional alternative generator

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

## [v7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
