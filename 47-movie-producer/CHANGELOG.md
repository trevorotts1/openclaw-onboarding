# Changelog — Skill 47 (Movie Producer / Automated Video Production)

## v14.3.0 — 2026-07-13 — Piper demoted to OPTIONAL/opt-in (Fish Audio 2.1 Pro is the primary narrator)

Demotes Piper to an **optional, opt-in, offline-only** TTS fallback that is **OFF by default**.
The operator already has cloud TTS (Fish Audio / Gemini / OpenAI / MiniMax), so a box without
Piper must install cleanly. This reverses the v14.2.0 FAIL-LOUD Piper behavior. Remotion +
HyperFrames provisioning and the Node ≥ 22 preflight are unchanged.

- **`provision-render-deps.sh`** — the Piper step (§5) is now gated behind an explicit opt-in
  flag **`SKILL47_INSTALL_PIPER=1`**. **Default path skips Piper entirely** — no
  `pip install piper-tts`, no `en_US-lessac-medium` voice-model download. The former FAIL-LOUD
  behavior is removed: a Piper install/download failure is now **WARN-only and NEVER aborts the
  install**. Removed the `SKILL47_PIPER_OPTIONAL` toggle (superseded by the off-by-default gate).
  Remotion + arch/OS compositor + Chrome-Headless-Shell, HyperFrames CLI + bundled Chrome, and
  the Linux Chromium system libs + ffmpeg are **unchanged** (still installed by default).
- **`install.sh` (Step 3.5)** — messaging updated: Piper is optional/opt-in and never causes the
  render-provisioning step to abort; removed the `SKILL47_PIPER_OPTIONAL` guidance.
- **`qc-movie-producer.sh`** — the two HARD asserts that *required* Piper (pinned `PIPER_VERSION`
  default, pre-staged voice ONNX model) are replaced by asserts that Piper is **optional/opt-in**
  (the `SKILL47_INSTALL_PIPER` gate is present) and that **Piper is never installed on the default
  path** (the opt-in gate precedes any `piper-tts` install). Remotion/HyperFrames/Chromium-libs
  and Node ≥ 22 asserts are kept as-is. The runtime `import piper` check stays soft (WARN).
- **Docs (`SKILL.md`, `INSTALL.md`, `DEPENDENCY-MANIFEST.md`)** — new voice order documented:
  **Fish Audio 2.1 Pro (`s2.1-pro`) primary; Gemini TTS / OpenAI TTS / MiniMax (a.k.a. "Mimo")
  cloud fallbacks; Piper optional, opt-in, offline-only, not installed by default.** Notes that
  OpenMontage's TTS auto-discovery uses the cloud providers when Piper is absent.
- **Unchanged:** the `Dockerfile` stays the opt-in Linux/VPS artifact (native install remains the
  default); the Node ≥ 22 preflight requirement is left exactly as-is.
- `skill-version.txt` + `SKILL.md` frontmatter: **v14.2.0 → v14.3.0**.

## v14.2.0 — 2026-07-13 — Render runtime provisioned for macOS AND Linux/VPS (Piper/Remotion/HyperFrames)

Fixes the "Mac-only in practice" gap in the OpenMontage engine's browser-based render
paths and the silent Piper soft-fail. `make setup` installed the upstream npm/pip deps but
NO Chromium system libraries and NO Piper voice model, so a fresh Linux/VPS container FAILED
every Remotion/HyperFrames (headless-Chromium) render and often ended up with no offline
Piper TTS. All version claims are pinned to their source registry (bump in one place).

- **NEW `provision-render-deps.sh`** — arch/OS-aware, idempotent render-runtime provisioner
  wired into `install.sh` as Step 3.5. For BOTH macOS and Linux it: (Linux) `apt-get`s the
  Chromium system libraries + ffmpeg that headless Chrome needs to launch (Remotion's
  documented Debian/Ubuntu set, incl. the `libasound2`→`libasound2t64` rename fallback);
  installs the pinned latest **Remotion 4.0.489** + the arch/OS-specific
  `@remotion/compositor-<os>-<arch>[-<libc>]` + `npx remotion browser ensure`
  (Chrome-Headless-Shell); cache-warms the pinned latest **HyperFrames 0.7.56** CLI +
  bundled Chrome; installs the latest arch-aware **Piper `piper-tts==1.4.2`**
  (OHF-voice/piper1-gpl) **FAIL-LOUD** (root-cause fix for the Makefile's silent
  `pip install piper-tts || echo skip`) and **pre-stages the default `en_US-lessac-medium`
  voice ONNX model** (direct from the pinned `rhasspy/piper-voices` HuggingFace tag).
  Toggles: `SKILL47_SKIP_RENDER_PROVISION=1`, `SKILL47_PIPER_OPTIONAL=1`, `SKILL47_SKIP_APT=1`.
- **NEW `Dockerfile`** — Linux/VPS image on `node:22-bookworm-slim` (Remotion's recommended
  base; Node 22 satisfies HyperFrames' `engines: node>=22`) that bakes the Chromium system
  libs + ffmpeg, clones OpenMontage at the pinned SHA, runs `make setup` then the
  provisioner. The client's own `KIE_API_KEY` is injected at RUNTIME, never baked in.
- **`preflight.sh`** — Node floor raised **18 → 22** (HyperFrames hard-requires Node ≥ 22;
  a box on 18–21 passed preflight yet failed every HyperFrames render). nodesource hint
  bumped to `setup_22.x`.
- **`qc-movie-producer.sh`** — `node >= 18` assertion raised to `node >= 22`; added HARD
  asserts that the provisioner + Dockerfile exist, the provisioner is valid bash, pins all
  three versions, installs a compositor, ensures Chrome-Headless-Shell, and pre-stages a
  voice model, that `install.sh` wires the provisioner, and that preflight/Dockerfile carry
  the Node-22 floor + Chromium libs.
- **`.github/workflows/video-pipeline-lockstep.yml`** — adds an `actions/setup-node@v4`
  (Node 22) step so the `qc-movie-producer.sh` Node≥22 assertion is provisioned in CI; adds
  the provisioner + Dockerfile to the path triggers.
- Docs (`INSTALL.md`, `DEPENDENCY-MANIFEST.md`) updated: Node ≥ 22, the new Step 3.5, the
  Linux/VPS + Docker provisioning path, and the pinned versions with source URLs.

## v14.1.4 — 2026-07-05 (Wave-0 merge-train T-47-movie-producer)

Seven fixes from the 2026-07-05 master fix-plan (skills-36-to-end weakness sweep).
All changes are scoped to `47-movie-producer/`.

- **FIX-S36-38** — `qc-movie-producer.sh`: the `.github/workflows/video-pipeline-lockstep.yml` CI-workflow assertion is now gated behind repo detection (HARD only when a `.git`/`.github` tree exists beside the skill; a PRE note on a client box). It no longer aborts every client install at Step 8, since no installer copies the repo-root CI workflow to client boxes.
- **FIX-S36-39** — `install.sh` Step 6 now idempotently **WRITES** the Rule-Zero budget cap into the clone's `config.yaml` via PyYAML (`budget.mode: cap`, `total_usd` ≤ 5 — never raising an already-lower client cap, `single_action_approval_usd: 0.50`, `require_approval_for_new_paid_tool: true`, `checkpoint.policy: guided`), preserving all other keys. QC stays pure verification. `INSTALL.md` Step 6 updated.
- **FIX-S36-40** — new `scripts/cc_board.py` (ported from Skill 48, fail-soft): the production run now lands on the Command Center as one campaign with 5 phase cards, and `executive_producer.py` walks each attested phase card `in_progress → review → done` via the legal-transition path (the QC `review` column is never skipped). At V-CONTROL the `campaign_id` + finished MP4 path are stamped into `render-receipt.json`. Board outage / missing token is a clean no-op. New `scripts/test_cc_board.py` proves the contract; QC wires both in.
- **FIX-S36-41** — added a binding **Attestation spine** section to `INSTRUCTIONS.md`, `CORE_UPDATES.md`, and `INSTALL.md` requiring per-phase `executive_producer.py --phase V-*` attestation, and listed the `scripts/` inventory in `SKILL.md` / `INSTALL.md`.
- **FIX-S36-42** — `video_build_check.py`: the provider-audit / native-provider ban is scoped to imagery/video **generation** tools. A bare `GOOGLE_API_KEY`/`GEMINI_API_KEY` embedding key (legitimately present on fleet boxes for memory / Skill 45) is allowlisted and no longer hard-stops a paid video job; a real Google generation tool (`imagen`, `provider_used` naming google, etc.) still fails. Regression probes added to `test_video_preflight.py`.
- **FIX-S36-43** — `install.sh` pins the OpenMontage clone to a verified upstream commit (`OPENMONTAGE_PINNED_SHA=ce11f6a…`, overridable via `OPENCLAW_OPENMONTAGE_SHA`); the `INSTRUCTIONS.md` pipeline table was regenerated from that pinned tree's real 13 `pipeline_defs/*.yaml` (removing the invented `script-to-video`/`explainer-video`/`brand-video`/`news-recap` entries). `SKILL.md` pipeline list + documentary-montage source list corrected to the pinned tree.
- **FIX-S36-44** — `video_build_check.py` `run_postflight_gate`: the `final_mp4` deliverable is validated against the render receipt's specific `final_mp4_path` (falling back to `output_path`), excluding any path under `assets/` (raw stock footage), instead of a blind recursive `**/*.mp4` glob; the downstream handoff must be an EXACT enum token, not a substring. Fixtures updated; regression probes added.
