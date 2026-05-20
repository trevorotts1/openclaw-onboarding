# Installation Guide (Video Editor)

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


## Teach Yourself Protocol (TYP) - Mandatory Read Order

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
   3) `INSTRUCTIONS.md` and `EXAMPLES.md` (and any `*-full.md`)
   4) `CORE_UPDATES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.

---

## What this skill needs

This skill runs locally using:

- **FFmpeg** (video processing)
- **yt-dlp** (downloading videos from URLs)
- **Whisper CLI** (captions)
- **PySceneDetect** (scene detection for B-roll planning)
- **MoviePy** (used by the B-roll merge helper)

## Step 1: Install FFmpeg

### macOS

1. Install Homebrew (if you do not have it): https://brew.sh/
2. Install FFmpeg:

```bash
brew install ffmpeg
```

3. Verify:

```bash
ffmpeg -version
```

### Ubuntu or Debian

1. Update package lists:

```bash
sudo apt update
```

2. Install FFmpeg:

```bash
sudo apt install -y ffmpeg
```

3. Verify:

```bash
ffmpeg -version
```

### Windows

Option A (recommended): use WSL2 (Windows Subsystem for Linux), then follow the Ubuntu steps.

Option B: install FFmpeg from https://ffmpeg.org/download.html and add it to your PATH.

Verify in PowerShell:

```powershell
ffmpeg -version
```

## Step 2: Install Python packages

1. Make sure you have Python 3 installed:

```bash
python3 --version || python --version
```

2. Install the required packages:

```bash
python3 -m pip install -U yt-dlp scenedetect openai-whisper moviepy
```

Notes:
- `openai-whisper` installs the `whisper` command used by `scripts/caption.sh`.
- Whisper models download the first time you run it. This can take a while.

3. Verify each tool:

```bash
yt-dlp --version
scenedetect --version
whisper --help | head
```

## Step 3: Make the scripts executable (macOS/Linux)

From inside the skill folder:

```bash
chmod +x scripts/*.sh
```

## Step 4: Quick smoke tests

### Test 1: Download

```bash
./scripts/download.sh \
  --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --output test-input.mp4
```

### Test 2: Cut

```bash
./scripts/cut.sh \
  --input test-input.mp4 \
  --start 00:00:05 \
  --duration 5 \
  --output test-clip.mp4
```

### Test 3: Resize

```bash
./scripts/resize.sh \
  --input test-clip.mp4 \
  --platform tiktok \
  --output test-clip-vertical.mp4
```

### Test 4: Captions

```bash
./scripts/caption.sh \
  --input test-clip-vertical.mp4 \
  --output test-clip-vertical-captioned.mp4 \
  --model small
```

What to expect:
- The first caption run may take longer because Whisper downloads a model.

## Troubleshooting

### "ffmpeg not found"

1. Run:

```bash
which ffmpeg
```

2. If it prints nothing, FFmpeg is not installed or not on your PATH.

### "scenedetect not found"

1. Run:

```bash
python3 -m pip show scenedetect
```

2. If it is not installed, run:

```bash
python3 -m pip install -U scenedetect
```

### "whisper: command not found"

1. Install Whisper:

```bash
python3 -m pip install -U openai-whisper
```

2. Then verify:

```bash
whisper --help | head
```

### Permission denied running scripts

From the skill folder:

```bash
chmod +x scripts/*.sh
```

## Done

Next:
- Read `INSTRUCTIONS.md` for workflows.
- Read `EXAMPLES.md` for copy-paste commands.

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
