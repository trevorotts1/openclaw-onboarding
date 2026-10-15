# Install / Update Contract: Motion Video Plus (Skill 72)

## Install model

This skill is repository-native. It is intended to live at:

`72-motion-video-plus/`

inside `openclaw-onboarding` and be installed/updated by the repository's existing install/update mechanism. Do not invent a second installer just for this skill.

## Prerequisites (host)

- Node.js 22 or newer.
- FFmpeg with libx264 (for encode, concat, xfade, sidechaincompress, blackdetect, freezedetect).
- Python 3 for `scripts/tts.py`, plus `numpy` (`pip install numpy` or `pip3 install numpy`) for `scripts/synth-score.py` and `scripts/synth-sfx.py`.
- Only for jobs whose resolved audio plan calls for Fish Audio narration: the client's OWN Fish Audio API key, collected by the client's agent at first use into the client environment (`export FISH_AUDIO_API_KEY=...`). It is never written into the repo or the skill files. Silent jobs (PowerPoint graphics, silent standalone pieces) and VSL inserts (parent owns the audio) need no TTS key at all, and the narration tooling exits cleanly without consulting one for them.
- No authoring-model credential is a prerequisite. Rendering approved scene source is a local operation; which model authors scene code is resolved per job (client selection or configured default) and is never an install requirement.
- Disk headroom: the preflight script measures and refuses plainly when the run does not fit.
- Legacy renderer only: `playwright-core` installed, plus a Chromium build for it. Acquire Chromium once with `npx -y playwright@latest install --with-deps chromium` (browsers land in `~/.cache/ms-playwright`, where `playwright-core` finds them; or set `PLAYWRIGHT_BROWSERS_PATH` to a custom location). Without this step, the legacy `scripts/render.js` fails on `chromium.launch()` and the client is stranded before step one. The V2 engines below do not use this browser.

## Render runtime provisioning (shared with Skill 47)

The V2 render engines (Remotion and HyperFrames) are not installed by this skill alone. They come from the shared motion render runtime at `shared-utils/motion-render-runtime/` in this repository, the same runtime Skill 47 uses, so both skills always render with identical pinned engine versions (Remotion 4.0.535 and HyperFrames 0.8.155, installed with `npm ci` from the committed `package-lock.json`; nothing resolves `latest` at install or render time). Skill 72 does NOT require an OpenMontage clone; that clone belongs to Skill 47's own pipelines only.

Provision (or re-verify) the runtime from the repository root:

```bash
bash shared-utils/motion-render-runtime/provision.sh
```

The provisioner installs the Chromium system libraries on Linux, installs the engines into `shared-utils/motion-render-runtime/.runtime/`, ensures the Remotion Chrome-Headless-Shell browser, and then runs the readiness probe (`probe.mjs` in the same directory). The probe is a real launch-and-render check, not a presence check: it bundles a minimal Remotion composition, renders an actual frame, runs the HyperFrames health check, and only then passes. The provisioner exits 0 only when every engine passes the probe, and it records the measured package versions, the resolved browser revision, and the per-engine results in `shared-utils/motion-render-runtime/.runtime/runtime-lock.json`. Treat a non-zero exit as "not installed", whatever the output above it says. A repeat run is idempotent: it re-runs the probe against the already-installed runtime instead of reinstalling, and an interrupted or failed run leaves the previously verified runtime active.

## Required repository wiring

Follow `REPO-INTEGRATION.md`:

- add Skill 72 to `23-ai-workforce-blueprint/skill-department-map.json` using `repo-integration/skill-department-map-entry.json`;
- bind it to `video` / `video-editor` (primary), with `storyboard-pre-production-specialist` and `head-of-video-production` as secondary;
- refresh generated `Skills You Operate` blocks with the canonical stamper;
- rehash content and run repo-consistency gates.

## Safe upgrade path for existing installations

Delivery still happens through the repository mechanism above; this is not a second installer. What this skill adds is a guarded transaction around the swap, for installations that already hold client work: `scripts/migrate_install.py`. It keeps system code separate from client-owned data (assets, brand profiles, style cards, renders, histories, plus anything the new tree does not ship), runs readiness checks on the staged tree before anything is promoted, refuses to start while a render is active, and rolls the skill tree and the runtime pointer back on any failure without deleting job data.

Typical run, from this skill directory:

```bash
python3 scripts/migrate_install.py discover --skills-root <skills dir> --storage-root <job storage root>
python3 scripts/migrate_install.py upgrade --skills-root <skills dir> --storage-root <job storage root> --source <new 72-motion-video-plus tree> [--runtime-version-dir <staged runtime version dir>] [--migrate-jobs --mode <mode> --company-id <id>]
python3 scripts/migrate_install.py rollback --skills-root <skills dir> --storage-root <job storage root>
```

`<skills dir>` is the directory that contains both `72-motion-video-plus/` and `shared-utils/`. `--migrate-jobs` additionally migrates V1 job manifests into new V2 revisions beside the originals (originals are never edited); it requires `--mode` and `--company-id`, and the tool refuses without them rather than guessing. A command the new release removed is replaced by a compatibility wrapper at its old path that fails with a named error (`MG_INSTALL_COMMAND_REMOVED`) stating the supported replacement. To roll the shared runtime pointer back on its own, use `bash shared-utils/motion-render-runtime/rollback.sh [version-id]` from the repository root; it flips only to versions whose probe record passed and refuses while a render is active.

Full semantics (discovery inventory, separation rules, transaction states, readiness gates, findings, exit codes): `references/install-and-migration.md`.

## Skill-local verification

From this skill directory:

```bash
bash verify.sh
```

This checks package integrity, required references, script syntax (node, bash, python), the manifest schema against the example manifest, the SKILL.md to skill-version.txt version lockstep, and the references and authority check (`scripts/check_authority.py`: no dead paths from the entrypoints, no obsolete production promises in the reconciled documents, the department-map mirrors in step).

This command is for install/update maintenance only. Normal runtime use does not begin by rerunning it.
