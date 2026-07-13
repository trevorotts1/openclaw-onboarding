# Installation Guide — Movie Producer — Automated Video Production (Skill 47)

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under `skills/01-teach-yourself-protocol/` and follow its procedural read-order. No shortcuts.

## Teach Yourself Protocol (TYP) — Mandatory read order

Before running any commands:

1. Discover every Markdown file in this skill folder:
   ```bash
   find ~/.openclaw/skills/47-movie-producer -name "*.md" | sort
   ```
2. Read every `.md` in order: `SKILL.md` → `INSTALL.md` → `INSTRUCTIONS.md` → `EXAMPLES.md` → `CORE_UPDATES.md` → `DEPENDENCY-MANIFEST.md`.

---

## Prerequisites — FAIL-LOUD PREFLIGHT (run this before anything else)

The installer will abort with a clear error message if any required binary is missing. The table below shows what is checked and how to fix a failure:

| Binary | Check | How to install if missing |
|---|---|---|
| `ffmpeg` | `command -v ffmpeg` | macOS: `brew install ffmpeg` / Ubuntu: `apt-get install -y ffmpeg` |
| `ffprobe` | `command -v ffprobe` | Ships with FFmpeg — same install |
| `node` (>=22) | `node -v` and version check | macOS: `brew install node` / Ubuntu: `curl -fsSL https://deb.nodesource.com/setup_22.x \| sudo -E bash - && apt-get install -y nodejs` |
| `npx` | `command -v npx` | Ships with Node.js — same install |
| `git` | `command -v git` | macOS: `xcode-select --install` / Ubuntu: `apt-get install -y git` |
| `python3` | `command -v python3` | macOS: `brew install python3` / Ubuntu: `apt-get install -y python3 python3-pip` |

Run the preflight now:

```bash
bash ~/.openclaw/skills/47-movie-producer/preflight.sh
```

If ANY check fails the script exits non-zero and prints an exact fix command. Do NOT continue until the preflight exits 0.

---

## Step-by-step installation

### Step 1 — Run the fail-loud preflight

```bash
bash ~/.openclaw/skills/47-movie-producer/preflight.sh
```

Expected output ends with:

```
[PASS] All required binaries present. Preflight OK.
```

### Step 2 — Clone OpenMontage onto this client box

> **Why this path?** The OpenMontage clone (~56MB) lives in a runtime dir
> **outside** the hashed skill dir (`~/.openclaw/skills/47-movie-producer/`).
> The onboarding updater hashes the skill dir for its content-integrity gate;
> a clone inside it would break that hash and block fleet version stamps.

```bash
mkdir -p ~/.openclaw/openmontage-runtime
git clone https://github.com/calesthio/OpenMontage.git \
  ~/.openclaw/openmontage-runtime/OpenMontage
```

Verify the clone is the correct remote:

```bash
git -C ~/.openclaw/openmontage-runtime/OpenMontage \
  remote get-url origin
```

Expected: `https://github.com/calesthio/OpenMontage.git`

**Pin the clone to the verified commit (FIX-S36-43).** `install.sh` does this for you
(`OPENMONTAGE_PINNED_SHA`); if you are cloning by hand, check out the same SHA so the
pipeline table in `INSTRUCTIONS.md` cannot drift under an unpinned HEAD:

```bash
git -C ~/.openclaw/openmontage-runtime/OpenMontage \
  fetch --quiet origin ce11f6a24f5c92e97d1461ffe1cd7a238dda1417
git -C ~/.openclaw/openmontage-runtime/OpenMontage \
  checkout --quiet ce11f6a24f5c92e97d1461ffe1cd7a238dda1417
git -C ~/.openclaw/openmontage-runtime/OpenMontage rev-parse HEAD
# Expected: ce11f6a24f5c92e97d1461ffe1cd7a238dda1417
```

This tree ships exactly the 13 `pipeline_defs/*.yaml` documented in `INSTRUCTIONS.md`.
Only re-pin (via `OPENCLAW_OPENMONTAGE_SHA`) after re-verifying that table against the
new tree.

**AGPLv3 note:** The cloned directory lives on the client's own box. The fleet template repo does NOT contain OpenMontage source. The AGPLv3 obligation is the client's.

### Step 3 — Run `make setup` (fetches all dependencies)

```bash
cd ~/.openclaw/openmontage-runtime/OpenMontage && make setup
```

This installs:
- Python packages: `pyyaml`, `pydantic`, `jsonschema`, `python-dotenv`, `Pillow`, `requests`, `google-auth`
- Remotion + React: `cd remotion-composer && npm install`
- HyperFrames CLI: `npx --yes hyperframes --version` (cache-warm)
- Piper free TTS: `pip install piper-tts` (soft-fail; Piper is OPTIONAL/opt-in — see Step 3.5)

`make setup` must exit 0. If it exits non-zero, re-read the error message and fix the missing dependency (do NOT vendor anything — all deps are fetchable at install time; see `DEPENDENCY-MANIFEST.md`).

### Step 3.5 — Provision the render runtime (macOS AND Linux/VPS)

`make setup` installs the npm/pip packages but **no Chromium system libraries**, so a fresh
Linux/VPS container fails every Remotion/HyperFrames (headless-Chromium) render. `install.sh`
runs this for you; if installing by hand, run it after `make setup`:

> **Narration / TTS voice order:** the **primary narrator is Fish Audio 2.1 Pro (`s2.1-pro`)**;
> **Gemini TTS, OpenAI TTS, and MiniMax (a.k.a. "Mimo") are the cloud fallbacks**; **Piper is an
> OPTIONAL, opt-in, offline-only fallback that is NOT installed by default**. Because Piper isn't
> installed by default, OpenMontage's TTS auto-discovery simply uses the cloud providers. Opt in
> to the offline Piper fallback with `SKILL47_INSTALL_PIPER=1`.

```bash
bash ~/.openclaw/skills/47-movie-producer/provision-render-deps.sh
```

Arch/OS-aware and idempotent. It:
- **(Linux)** `apt-get` installs the Chromium system libraries + ffmpeg headless Chrome needs
  to launch (`libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libgbm-dev libxrandr2
  libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2
  libasound2 fonts-liberation`). On macOS this step is a no-op.
- Installs the pinned latest **Remotion 4.0.489** + the arch/OS-specific
  `@remotion/compositor-<os>-<arch>[-<libc>]` and runs `npx remotion browser ensure`
  (Chrome-Headless-Shell). Source: <https://registry.npmjs.org/remotion/latest>,
  <https://www.remotion.dev/docs/docker>.
- Cache-warms the pinned latest **HyperFrames 0.7.56** CLI + its bundled Chrome. Source:
  <https://registry.npmjs.org/hyperframes/latest>.
- **(OPTIONAL, opt-in — OFF by default)** Only when `SKILL47_INSTALL_PIPER=1`: installs the
  latest arch-aware **Piper `piper-tts==1.4.2`** and **pre-stages** the `en_US-lessac-medium`
  voice ONNX model to `~/.piper/models`. This is an offline-only last-resort fallback and
  **never aborts the install**. Source: <https://github.com/OHF-voice/piper1-gpl/releases>,
  <https://huggingface.co/rhasspy/piper-voices>. **Default path skips Piper entirely** — no
  `pip install piper-tts`, no voice-model download — and TTS uses the cloud providers.

Optional toggles: `SKILL47_SKIP_RENDER_PROVISION=1` (free-path-only box — skip entirely),
`SKILL47_INSTALL_PIPER=1` (opt in to the optional offline Piper TTS fallback), `SKILL47_SKIP_APT=1`
(system libs already provisioned). To bump a version, edit the pinned constants at the top of
`provision-render-deps.sh` (and the matching `ARG`s in the `Dockerfile`).

### Step 4 — Drop the Kie adapters into the clone

```bash
cp ~/.openclaw/skills/47-movie-producer/kie-adapters/tools/graphics/kie_image.py \
   ~/.openclaw/openmontage-runtime/OpenMontage/tools/graphics/kie_image.py

cp ~/.openclaw/skills/47-movie-producer/kie-adapters/tools/video/kie_video.py \
   ~/.openclaw/openmontage-runtime/OpenMontage/tools/video/kie_video.py
```

Verify syntax:

```bash
python3 -c "import ast; ast.parse(open('$HOME/.openclaw/openmontage-runtime/OpenMontage/tools/graphics/kie_image.py').read()); print('kie_image OK')"
python3 -c "import ast; ast.parse(open('$HOME/.openclaw/openmontage-runtime/OpenMontage/tools/video/kie_video.py').read()); print('kie_video OK')"
```

### Step 5 — Write the client `.env` (Kie key only)

Create a `.env` in the cloned OpenMontage directory with **only** the client's own Kie.AI key. No FAL, Runway, HeyGen, OpenAI, or Google keys — leaving those absent ensures native paid providers report UNAVAILABLE and all asset generation routes through Kie:

```bash
cat > ~/.openclaw/openmontage-runtime/OpenMontage/.env << 'ENVEOF'
# Kie.AI API key — client's own key. Get one at https://kie.ai
# All image/video generation routes through Kie.AI when this is set.
# Remove this line (or leave blank) to run the free stock-footage path only.
KIE_API_KEY=YOUR_CLIENT_KIE_API_KEY_HERE
ENVEOF
```

Replace `YOUR_CLIENT_KIE_API_KEY_HERE` with the client's actual key. If the client has no key yet, leave it blank — the free documentary-montage path still works.

**OPERATOR KEY RULE:** The operator's own KIE_API_KEY MUST NEVER appear in this file. This is the client's deployment using the client's own funded key.

### Step 6 — Budget cap is WRITTEN automatically (FIX-S36-39)

`install.sh` **writes** the Rule-Zero budget cap into
`~/.openclaw/openmontage-runtime/OpenMontage/config.yaml` for you via PyYAML —
idempotently, preserving every other key, and never RAISING an already-lower client
cap. The QC gate then only *verifies* it (`budget.mode: cap`). The written config is:

```yaml
budget:
  mode: cap
  total_usd: 5.00                   # left lower if the client already set a smaller cap
  single_action_approval_usd: 0.50
  require_approval_for_new_paid_tool: true

checkpoint:
  policy: guided

preferred_provider: kie
```

This enforces the Rule-Zero budget discipline: the system announces provider + model + estimated cost before any paid call, gates on $0.50 per action, and requires approval for new paid tools. If you install by hand instead of via `install.sh`, set the block above yourself before running the QC.

### Step 7 — Verify provider routing

```bash
cd ~/.openclaw/openmontage-runtime/OpenMontage && make preflight
```

With `KIE_API_KEY` set, the output should show `kie` listed under both `image_generation` and `video_generation`. Native paid **generation** providers (flux, veo, runway, heygen, openai, imagen/google-image) should all be UNAVAILABLE. Note (FIX-S36-42): a bare `GOOGLE_API_KEY`/`GEMINI_API_KEY` used for **embeddings** (memory / Skill 45) is permitted and does NOT trip the provider audit — the ban is scoped to Google/Gemini *generation* tools, not the mere presence of an embedding key.

### Step 8 — Run the install QC

```bash
bash ~/.openclaw/skills/47-movie-producer/qc-movie-producer.sh
```

Expected: `Skill 47 QC PASS`

---

## Attestation spine — how every run is gated (BINDING)

This skill ships a deterministic **attestation spine** under
`~/.openclaw/skills/47-movie-producer/scripts/`. It is OUR code that gates *around*
OpenMontage (AGPLv3-safe — no upstream source vendored). Every production run MUST go
through it: drive the 5 DMAIC phases in order and attest each before the next can
dispatch. Skipping/reordering/forging a phase is a HARD ABORT (`AF-VID-PHASE-SKIPPED`).

```bash
D=~/.openclaw/skills/47-movie-producer/scripts
RUN=~/.openclaw/openmontage-runtime/OpenMontage/runs/<job-id>
python3 $D/executive_producer.py --run-dir "$RUN" --plan
python3 $D/executive_producer.py --run-dir "$RUN" --phase V-DEFINE
python3 $D/executive_producer.py --run-dir "$RUN" --phase V-MEASURE
python3 $D/executive_producer.py --run-dir "$RUN" --phase V-ANALYZE   # paid jobs (free path = logged owner skip)
python3 $D/executive_producer.py --run-dir "$RUN" --phase V-IMPROVE
python3 $D/executive_producer.py --run-dir "$RUN" --phase V-CONTROL
```

The full binding procedure (including the free-path owner-authorized skip, the
`--adhoc` rule, and the fail-soft Command Center carding that walks each phase card
`in_progress → review → done`) is in `INSTRUCTIONS.md` ("Attestation spine").

**Files in `scripts/`:** `executive_producer.py` (driver), `video_build_check.py`
(receipt validators + V-CONTROL postflight), `video_sync_check.py` (manifest↔code↔ruleset
lockstep), `video_gate_integrity_check.py` (Guard A), `test_video_preflight.py`
(negative-test suite), `test_kie_adapter_resultjson_decode.py`, `cc_board.py` (fail-soft
board caller) + `test_cc_board.py`.

---

## Verify deps on a clean box

See `verify-deps.sh` and `DEPENDENCY-MANIFEST.md` for the clean-box dependency proof. Short version:

```bash
bash ~/.openclaw/skills/47-movie-producer/verify-deps.sh
```

---

## Linux / VPS install (Docker)

The browser-based render paths (Remotion, HyperFrames) need Chromium system libraries that a
slim Linux image does not ship. The included `Dockerfile` bakes them in on `node:22-bookworm-slim`
(Remotion's recommended base; Node 22 satisfies HyperFrames' `engines: node>=22`), clones the
pinned OpenMontage tree, runs `make setup`, then the render provisioner:

```bash
# Build (context = the skill directory)
docker build -t openmontage-skill47 ~/.openclaw/skills/47-movie-producer/

# Run — the client's OWN Kie key is injected at RUNTIME, never baked into the image.
# Omit -e KIE_API_KEY to run the free documentary-montage path.
docker run --rm -e KIE_API_KEY=YOUR_CLIENT_KIE_KEY \
  -v "$PWD/out:/work/out" openmontage-skill47 \
  bash -lc 'cd $OPENCLAW_OPENMONTAGE_DIR && make demo'
```

Bump a pinned version with a build arg, e.g. `--build-arg REMOTION_VERSION=4.0.500`
(mirrors the constants in `provision-render-deps.sh`).

**Root-in-container Chrome:** Remotion's Chrome-Headless-Shell renders fine as root (matching
Remotion's official Docker image). HyperFrames drives its own bundled Chrome; if a render fails
to launch Chrome as root, run the container as a non-root user or pass the renderer's
`--no-sandbox` option. The free ffmpeg documentary-montage path and the Kie.AI remote path need
no browser at all and are VPS-ready without any of this.

**Bare VPS (no Docker):** run `provision-render-deps.sh` directly (Step 3.5) — its Linux branch
`apt-get`s the same libraries.

## Gateway restart protocol

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

When a gateway restart is needed:
1. STOP — do NOT execute the restart command
2. NOTIFY the user: "This installation requires an OpenClaw gateway restart."
3. INSTRUCT: "Type `/restart` in Telegram to trigger it"
4. WAIT for user action before proceeding

---

## Uninstall

```bash
rm -rf ~/.openclaw/openmontage-runtime/OpenMontage
```

The skill wrapper files (`~/.openclaw/skills/47-movie-producer/`) are managed by `update-skills.sh` and are NOT removed by this command.
