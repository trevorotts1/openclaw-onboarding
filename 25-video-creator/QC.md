# Skill 25: Video Creator — QC Checklist

Run this after installation to verify the skill is correctly installed and functional.
Each section lists checks, the exact command or verification step, and the expected result.

---

## 1. File Structure Checks

Confirm the skill folder and all required files are present.

```bash
SKILL_DIR="$HOME/.openclaw/skills/video-creator"

# Check top-level files
for f in SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

# Check scripts
for s in text_to_video.py script_to_video.py image_to_video.py \
          add_music.py multi_clip_assembly.py template_video.py \
          avatar_video.py export.py transitions.py ai_providers.py \
          test_installation.py __init__.py; do
  [ -f "$SKILL_DIR/scripts/$s" ] && echo "PASS: scripts/$s" || echo "FAIL: scripts/$s missing"
done

# Check templates folder
for t in README.md product_showcase.json social_post.json \
          tutorial.json testimonial.json podcast_clip.json sample_script.txt; do
  [ -f "$SKILL_DIR/templates/$t" ] && echo "PASS: templates/$t" || echo "FAIL: templates/$t missing"
done
```

**Pass criteria:** Every line prints `PASS`. No `FAIL` lines.

---

## 2. Script Executability Checks

All `.py` scripts in `scripts/` must be executable.

```bash
SKILL_DIR="$HOME/.openclaw/skills/video-creator"

for s in "$SKILL_DIR"/scripts/*.py; do
  [ -x "$s" ] && echo "PASS: $(basename $s) is executable" \
               || echo "FAIL: $(basename $s) is NOT executable"
done
```

**Pass criteria:** All scripts print `PASS`. If any fail, fix with:
```bash
chmod +x "$HOME/.openclaw/skills/video-creator/scripts"/*.py
```

---

## 3. Core File Update Checks

Verify that `TOOLS.md` and `MEMORY.md` were updated as specified in `CORE_UPDATES.md`.

### TOOLS.md

```bash
grep -q "Video Creator (Skill 25)" "$HOME/.openclaw/TOOLS.md" \
  && echo "PASS: Video Creator entry found in TOOLS.md" \
  || echo "FAIL: Video Creator entry missing from TOOLS.md"

grep -q "KIE_API_KEY" "$HOME/.openclaw/TOOLS.md" \
  && echo "PASS: KIE_API_KEY reference found in TOOLS.md" \
  || echo "FAIL: KIE_API_KEY reference missing from TOOLS.md"

grep -q "video-creator" "$HOME/.openclaw/TOOLS.md" \
  && echo "PASS: video-creator path found in TOOLS.md" \
  || echo "FAIL: video-creator path missing from TOOLS.md"
```

### MEMORY.md

```bash
grep -q "Video Creator (Skill 25)" "$HOME/.openclaw/MEMORY.md" \
  && echo "PASS: Video Creator pointer found in MEMORY.md" \
  || echo "FAIL: Video Creator pointer missing from MEMORY.md"

grep -q "video-creator" "$HOME/.openclaw/MEMORY.md" \
  && echo "PASS: video-creator path found in MEMORY.md" \
  || echo "FAIL: video-creator path missing from MEMORY.md"
```

**Pass criteria:** All 5 checks print `PASS`.

---

## 4. Dependency Checks

Verify system and Python dependencies are installed.

### System dependencies

```bash
ffmpeg -version > /dev/null 2>&1 \
  && echo "PASS: ffmpeg found ($(ffmpeg -version 2>&1 | head -1))" \
  || echo "FAIL: ffmpeg not found — install with: brew install ffmpeg"

convert --version > /dev/null 2>&1 \
  && echo "PASS: imagemagick found" \
  || echo "WARN: imagemagick not found (optional but recommended)"
```

### Python version

```bash
python3 -c "import sys; v=sys.version_info; \
  print('PASS: Python', v.major, v.minor) if v >= (3,8) \
  else print('FAIL: Python 3.8+ required, found', v.major, v.minor)"
```

### Python packages

```bash
cd "$HOME/.openclaw/skills/video-creator"
source venv/bin/activate 2>/dev/null || true  # activate venv if present

for pkg in moviepy cv2 requests PIL numpy; do
  python3 -c "import $pkg" 2>/dev/null \
    && echo "PASS: $pkg importable" \
    || echo "FAIL: $pkg not installed"
done

# Confirm MoviePy is v1 (v2 breaks this skill)
python3 -c "
import moviepy
v = moviepy.__version__
major = int(v.split('.')[0])
if major == 1:
    print('PASS: MoviePy v' + v + ' (v1 confirmed)')
else:
    print('FAIL: MoviePy v' + v + ' — this skill requires v1 (pin with: pip install moviepy==1.0.3)')
" 2>/dev/null || echo "FAIL: moviepy not installed"
```

**Pass criteria:** ffmpeg PASS, Python 3.8+ PASS, all 5 packages PASS, MoviePy v1 PASS.

---

## 5. Knowledge Verification Questions

Answer these to confirm the agent understands the skill. All answers are in the skill docs.

| # | Question | Expected Answer |
|---|----------|----------------|
| 1 | What Python package version must be pinned, and why? | `moviepy==1.0.3` — MoviePy v2 removed `moviepy.editor`, which all scripts import |
| 2 | Which two core OpenClaw files is this skill allowed to update? | `TOOLS.md` and `MEMORY.md` only |
| 3 | What flag lets you run `text_to_video.py` without any API key? | `--provider mock` |
| 4 | What are the three optional AI provider environment variables? | `KIE_API_KEY`, `RUNWAY_API_KEY`, `PIKA_API_KEY` |
| 5 | What are the five built-in templates? | `product_showcase`, `social_post`, `tutorial`, `testimonial`, `podcast_clip` |
| 6 | What is the correct workflow order for this skill within the Video Skills Suite? | Storyboard Writer → Video Creator → Caption Creator → Video Editor |
| 7 | Where should the agent instruct the user to trigger a gateway restart? | The user must type `/restart` in Telegram — the agent must NEVER trigger it autonomously |
| 8 | What subcommands does `add_music.py` support beyond the default mix? | `extract` (extract audio) and `remove` (strip audio) |
| 9 | What is the default output directory for videos? | `~/Videos/Output/` |
| 10 | Which script is used to verify the installation itself? | `scripts/test_installation.py` |

**Pass criteria:** Agent answers all 10 correctly without referencing files mid-answer.

---

## 6. Live Behavior Test

Run the built-in test script, then a manual mock generation.

### Step 1: Built-in test

```bash
cd "$HOME/.openclaw/skills/video-creator"
source venv/bin/activate 2>/dev/null || true
python3 scripts/test_installation.py
```

**Expected:** Script exits with no Python tracebacks. Confirms imports and FFmpeg presence.

### Step 2: Mock text-to-video (no API key required)

```bash
cd "$HOME/.openclaw/skills/video-creator"
source venv/bin/activate 2>/dev/null || true

mkdir -p output

python3 scripts/text_to_video.py "A calm ocean at sunrise" \
  --provider mock \
  --duration 5 \
  --output output/qc_test.mp4
```

**Expected:**
- Script runs without traceback
- `output/qc_test.mp4` is created
- File is non-zero size: `ls -lh output/qc_test.mp4`

### Step 3: Verify output file

```bash
[ -s "$HOME/.openclaw/skills/video-creator/output/qc_test.mp4" ] \
  && echo "PASS: qc_test.mp4 created and non-empty" \
  || echo "FAIL: qc_test.mp4 missing or empty"
```

**Pass criteria:** All three steps complete, `qc_test.mp4` exists and is non-empty.

---

## 7. Anti-Pattern Checks

Verify the agent does NOT exhibit these incorrect behaviors.

| # | Anti-Pattern | How to Check |
|---|-------------|-------------|
| 1 | **Wrong MoviePy version** — importing from `moviepy` (v2) instead of `moviepy.editor` (v1) | Run `python3 -c "from moviepy.editor import VideoFileClip"` — must succeed without error |
| 2 | **Autonomous gateway restart** — agent triggers `openclaw gateway restart` without user confirmation | Inspect any install log or chat transcript; this command must never appear without explicit `/restart` from user in Telegram |
| 3 | **Updating wrong core files** — agent modifies files other than `TOOLS.md` and `MEMORY.md` | Check git diff or file timestamps on other core files; only `TOOLS.md` and `MEMORY.md` should be touched |
| 4 | **Missing `--provider mock`** — agent tries to call a real API when no key is set | Confirm test run above used `--provider mock` and produced output without API errors |
| 5 | **Scripts not executable** — agent runs scripts via `python3 scripts/x.py` but scripts are not chmod +x | Covered in Section 2; all scripts must be executable |
| 6 | **Wrong install path** — skill placed somewhere other than `~/.openclaw/skills/video-creator/` | Confirm: `ls "$HOME/.openclaw/skills/video-creator/SKILL.md"` returns the file |

**Pass criteria:** None of the anti-patterns are present.

---

## 8. Pass / Fail Summary

Fill this in after running all checks:

| Section | Status | Notes |
|---------|--------|-------|
| 1. File structure | PASS / FAIL | |
| 2. Script executability | PASS / FAIL | |
| 3. Core file updates | PASS / FAIL | |
| 4. Dependencies | PASS / FAIL | |
| 5. Knowledge questions | PASS / FAIL | |
| 6. Live behavior test | PASS / FAIL | |
| 7. Anti-pattern checks | PASS / FAIL | |

**Overall PASS:** All 7 sections must be PASS.
**If any section is FAIL:** Do not mark the skill as installed. Resolve the failing section using the fix hints above, then re-run that section's checks.
