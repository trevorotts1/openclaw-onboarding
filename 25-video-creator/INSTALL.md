# Video Creator (Skill 25) - Installation Guide

## Teach Yourself Protocol (TYP) - Mandatory Read Order

Before you run any commands in this skill:

1. Open Terminal.
2. Go into the skill folder:
   ```bash
   cd ~/.openclaw/skills/video-creator
   ```
3. Discover every Markdown file in this skill folder (including subfolders):
   ```bash
   find . -name "*.md" | sort
   ```
4. Read every discovered `.md` file.
5. Use this read order:
   1) `SKILL.md`
   2) `INSTALL.md`
   3) `INSTRUCTIONS.md`
   4) `EXAMPLES.md`
   5) `CORE_UPDATES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.

---

## Prerequisites

- Python 3.8+
- FFmpeg installed on your system
- 4GB+ RAM (8GB+ recommended)
- Free disk space for videos (a few GB recommended)

---

## Step 1: Install system dependencies

### macOS (Homebrew)

1. Install FFmpeg and ImageMagick:
   ```bash
   brew install ffmpeg imagemagick
   ```
2. Confirm FFmpeg works:
   ```bash
   ffmpeg -version
   ```

### Ubuntu / Debian

1. Update packages:
   ```bash
   sudo apt-get update
   ```
2. Install FFmpeg and ImageMagick:
   ```bash
   sudo apt-get install -y ffmpeg imagemagick
   ```
3. Confirm FFmpeg works:
   ```bash
   ffmpeg -version
   ```

### Windows

1. Download FFmpeg from: https://ffmpeg.org/download.html
2. Extract it.
3. Add the `bin` folder to your PATH.

---

## Step 2: Install Python dependencies

This skill's scripts use `moviepy.editor` and are written for **MoviePy v1**.
MoviePy v2 removed `moviepy.editor`, so you must pin MoviePy to v1.

1. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   ```
2. Activate it:
   - macOS / Linux:
     ```bash
     source venv/bin/activate
     ```
   - Windows (PowerShell):
     ```powershell
     venv\Scripts\Activate.ps1
     ```
3. Upgrade pip:
   ```bash
   pip install --upgrade pip
   ```
4. Install dependencies:
   ```bash
   pip install "moviepy==1.0.3" opencv-python requests pillow numpy
   ```

---

## Step 3: Install the skill

### Option A (preferred): Install with OpenClaw

1. In Terminal, run:
   ```bash
   The .skill file is an archive. No CLI command needed - install by following SKILL.md, INSTALL.md, and CORE_UPDATES.md instructions.
   ```
2. After install, the skill should exist at:
   - `$HOME/.openclaw/skills/video-creator/`

### Option B (manual): Unzip

1. Create the skills folder if it does not exist:
   ```bash
   mkdir -p "$HOME/.openclaw/skills"
   ```
2. Copy the skill folder from the onboarding package:
   ```bash
   cp -r "$(find ~/Downloads -name '25-video-creator' -type d | head -1)" "$HOME/.openclaw/skills/video-creator"
   ```
3. Make scripts executable:
   ```bash
   chmod +x "$HOME/.openclaw/skills/video-creator/scripts"/*.py
   ```

---

## Step 4: Configure API keys (optional)

You can use this skill without any API keys by using the `mock` or `local` providers.

### KIE.ai

1. Get your API key from KIE.ai.
2. Set the environment variable:
   ```bash
   export KIE_API_KEY="your_kie_key_here"
   ```

### Other providers (optional)

- Runway:
  ```bash
  export RUNWAY_API_KEY="your_runway_key_here"
  ```
- Pika:
  ```bash
  export PIKA_API_KEY="your_pika_key_here"
  ```

---

## Step 5: Verify installation

1. Go into the installed skill folder:
   ```bash
   cd "$HOME/.openclaw/skills/video-creator"
   ```
2. Run the installation test:
   ```bash
   python3 scripts/test_installation.py
   ```

---

## Uninstall

1. Remove the skill folder:
   ```bash
   rm -rf "$HOME/.openclaw/skills/video-creator"
   ```
2. (Optional) Remove the virtual environment you created:
   ```bash
   rm -rf venv
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
