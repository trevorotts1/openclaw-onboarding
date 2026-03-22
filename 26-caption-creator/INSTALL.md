# Installation Guide - Caption Creator Skill

## Teach Yourself Protocol (TYP) - Mandatory read order

Before you run any commands in this skill:

1. Discover every Markdown file in this skill folder (including subfolders):
   ```bash
   cd "$(dirname "$0")" 2>/dev/null || true
   find . -name "*.md" | sort
   ```
2. Read every discovered `.md` file.
3. Use this read order:
   1) `SKILL.md`
   2) `INSTALL.md`
   3) `INSTRUCTIONS.md` and `EXAMPLES.md`
   4) `CORE_UPDATES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.

## What must be installed

This skill uses:

1. **Python 3** (3.8+)
2. **FFmpeg** (for rendering captions into video)
3. **Whisper CLI** (for transcription)

## Step-by-step install

### Step 1: Install FFmpeg

#### macOS

1. Open the Terminal app.
2. Run:

```bash
brew install ffmpeg
```

3. Verify:

```bash
ffmpeg -version
```

#### Ubuntu / Debian

1. Open Terminal.
2. Run:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

3. Verify:

```bash
ffmpeg -version
```

### Step 2: Install Whisper (includes the `whisper` command)

1. Open Terminal.
2. Run:

```bash
pip install --upgrade openai-whisper
```

3. Verify:

```bash
whisper --help
```

### Step 3: First run downloads the model

Whisper downloads the model the first time you use it. You can also pre-download a model by running any Whisper command once.

Example (downloads the `base` model):

```bash
whisper --model base --help >/dev/null 2>&1 || true
```

Common models:
- `tiny`, `base`, `small` (faster)
- `medium`, `large` (more accurate)

## Install the skill

### Install with OpenClaw

```bash
The .skill file is an archive. No CLI command needed - install by following SKILL.md, INSTALL.md, and CORE_UPDATES.md instructions.
```

### Confirm install location

```bash
ls -la ~/.openclaw/skills/caption-creator
```

## Development install (optional)

Only do this if you are modifying the skill source code in a local checkout.

```bash
cd "$HOME/clawd/skills/caption-creator"
```

## Uninstall

1. Remove the Python package (optional, only if you do not use Whisper anywhere else):

```bash
pip uninstall -y openai-whisper
```

2. Remove downloaded Whisper models (optional):

```bash
rm -rf ~/.cache/whisper
```

3. Remove the skill:

```bash
rm -rf ~/.openclaw/skills/caption-creator
```

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
