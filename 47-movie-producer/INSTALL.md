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
| `node` (>=18) | `node -v` and version check | macOS: `brew install node` / Ubuntu: `apt-get install -y nodejs` |
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

**AGPLv3 note:** The cloned directory lives on the client's own box. The fleet template repo does NOT contain OpenMontage source. The AGPLv3 obligation is the client's.

### Step 3 — Run `make setup` (fetches all dependencies)

```bash
cd ~/.openclaw/openmontage-runtime/OpenMontage && make setup
```

This installs:
- Python packages: `pyyaml`, `pydantic`, `jsonschema`, `python-dotenv`, `Pillow`, `requests`, `google-auth`
- Remotion + React: `cd remotion-composer && npm install`
- HyperFrames CLI: `npx --yes hyperframes --version` (cache-warm)
- Piper free TTS: `pip install piper-tts` (soft-fail — if it fails, TTS uses cloud providers)

`make setup` must exit 0. If it exits non-zero, re-read the error message and fix the missing dependency (do NOT vendor anything — all deps are fetchable at install time; see `DEPENDENCY-MANIFEST.md`).

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

### Step 6 — Set a low budget cap in `config.yaml`

Open `~/.openclaw/openmontage-runtime/OpenMontage/config.yaml` and set:

```yaml
budget:
  mode: cap
  total_usd: 5.00
  single_action_approval_usd: 0.50
  require_approval_for_new_paid_tool: true

checkpoint:
  policy: guided
```

This enforces the Rule-Zero budget discipline: the system announces provider + model + estimated cost before any paid call, gates on $0.50 per action, and requires approval for new paid tools.

### Step 7 — Verify provider routing

```bash
cd ~/.openclaw/openmontage-runtime/OpenMontage && make preflight
```

With `KIE_API_KEY` set, the output should show `kie` listed under both `image_generation` and `video_generation`. Native paid providers (flux, veo, runway, heygen, openai, google) should all be UNAVAILABLE.

### Step 8 — Run the install QC

```bash
bash ~/.openclaw/skills/47-movie-producer/qc-movie-producer.sh
```

Expected: `Skill 47 QC PASS`

---

## Verify deps on a clean box

See `verify-deps.sh` and `DEPENDENCY-MANIFEST.md` for the clean-box dependency proof. Short version:

```bash
bash ~/.openclaw/skills/47-movie-producer/verify-deps.sh
```

---

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
