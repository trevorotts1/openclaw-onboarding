# QC Checklist — Skill 27: Video Editor

Run this after installation to verify the skill is correctly installed and functional.

---

## Section 1: File Structure Checks

Verify every required file and folder exists.

```bash
SKILL_DIR="$HOME/.openclaw/skills/video-editor"

# Check top-level files
for f in SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md BROLL-WORKFLOW.md; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

# Check scripts
for s in download.sh cut.sh resize.sh caption.sh social-clip.sh \
          analyze-video.sh extract-audio.sh merge-broll.sh \
          broll-workflow.sh broll_merge.py text-overlay.py; do
  [ -f "$SKILL_DIR/scripts/$s" ] && echo "PASS: scripts/$s" || echo "FAIL: scripts/$s missing"
done

# Check references
for r in platform-specs.md ffmpeg-vs-moviepy.md kie-ai-models.md; do
  [ -f "$SKILL_DIR/references/$r" ] && echo "PASS: references/$r" || echo "FAIL: references/$r missing"
done

# Check reserved folders exist
[ -d "$SKILL_DIR/brand-templates" ] && echo "PASS: brand-templates/ exists" || echo "FAIL: brand-templates/ missing"
[ -d "$SKILL_DIR/examples" ] && echo "PASS: examples/ exists" || echo "FAIL: examples/ missing"
```

**Pass criteria:** All files print PASS. Zero FAIL lines.

---

## Section 2: Script Executable Permissions

All `.sh` scripts must be executable (macOS/Linux).

```bash
SKILL_DIR="$HOME/.openclaw/skills/video-editor"

for s in download.sh cut.sh resize.sh caption.sh social-clip.sh \
          analyze-video.sh extract-audio.sh merge-broll.sh broll-workflow.sh; do
  [ -x "$SKILL_DIR/scripts/$s" ] \
    && echo "PASS: scripts/$s is executable" \
    || echo "FAIL: scripts/$s is NOT executable — run: chmod +x $SKILL_DIR/scripts/*.sh"
done
```

**Pass criteria:** All scripts print PASS.

---

## Section 3: Core File Update Checks

Verify the three required entries were added to core files.

### 3a. AGENTS.md — Video QC Rule

```bash
grep -q "Video QC Rule (Skill 27)" "$HOME/.openclaw/AGENTS.md" \
  && echo "PASS: AGENTS.md contains Video QC Rule" \
  || echo "FAIL: AGENTS.md missing Video QC Rule (Skill 27)"
```

Verify the rule body also contains the four required checks:

```bash
for line in "Verify the output file exists" \
            "duration and resolution" \
            "audio is present" \
            "treat the run as FAILED"; do
  grep -q "$line" "$HOME/.openclaw/AGENTS.md" \
    && echo "PASS: AGENTS.md contains: $line" \
    || echo "FAIL: AGENTS.md missing: $line"
done
```

### 3b. TOOLS.md — Video Skills Suite section

```bash
grep -q "Video Editor (Skill 27)" "$HOME/.openclaw/TOOLS.md" \
  && echo "PASS: TOOLS.md contains Video Editor entry" \
  || echo "FAIL: TOOLS.md missing Video Editor (Skill 27)"

grep -q "video-editor" "$HOME/.openclaw/TOOLS.md" \
  && echo "PASS: TOOLS.md contains skill path" \
  || echo "FAIL: TOOLS.md missing skill path"
```

### 3c. MEMORY.md — Pointer entry

```bash
grep -q "Video Editor (Skill 27)" "$HOME/.openclaw/MEMORY.md" \
  && echo "PASS: MEMORY.md contains Video Editor pointer" \
  || echo "FAIL: MEMORY.md missing Video Editor (Skill 27) pointer"

grep -q "video-editor" "$HOME/.openclaw/MEMORY.md" \
  && echo "PASS: MEMORY.md contains skill path" \
  || echo "FAIL: MEMORY.md missing skill path"
```

**Pass criteria:** All grep checks print PASS. The AGENTS.md rule must include all four video QC checks.

---

## Section 4: Dependency Verification

Verify all required CLI tools and Python packages are installed.

```bash
# FFmpeg
ffmpeg -version > /dev/null 2>&1 \
  && echo "PASS: ffmpeg found ($(ffmpeg -version 2>&1 | head -1))" \
  || echo "FAIL: ffmpeg not found — install via: brew install ffmpeg"

# yt-dlp
yt-dlp --version > /dev/null 2>&1 \
  && echo "PASS: yt-dlp $(yt-dlp --version)" \
  || echo "FAIL: yt-dlp not found — install via: pip install yt-dlp"

# scenedetect
scenedetect --version > /dev/null 2>&1 \
  && echo "PASS: scenedetect found" \
  || echo "FAIL: scenedetect not found — install via: pip install scenedetect"

# whisper
whisper --help > /dev/null 2>&1 \
  && echo "PASS: whisper found" \
  || echo "FAIL: whisper not found — install via: pip install openai-whisper"

# moviepy Python import
python3 -c "import moviepy" 2>/dev/null \
  && echo "PASS: moviepy importable" \
  || echo "FAIL: moviepy not importable — install via: pip install moviepy"
```

**Pass criteria:** All five tools print PASS.

---

## Section 5: Knowledge Verification Questions

The agent must be able to answer these correctly without looking anything up. These verify the skill's knowledge was ingested.

**Q1.** What is the correct resolution and aspect ratio for TikTok/Reels/Shorts?
> **Expected:** 1080 x 1920, 9:16 aspect ratio.

**Q2.** What are the three platform keywords accepted by `resize.sh`?
> **Expected:** `tiktok` (9:16), `instagram` (1:1 square), `youtube` (16:9).

**Q3.** Which tool is preferred for simple cuts and resizes — FFmpeg or MoviePy? Why?
> **Expected:** FFmpeg. It is 5–10x faster for simple operations because it doesn't decode/re-encode the full pipeline the way MoviePy does.

**Q4.** When should MoviePy be used instead of FFmpeg?
> **Expected:** When adding styled or animated text overlays, multiple text layers, complex compositing, or custom positioning that is difficult with FFmpeg `drawtext`.

**Q5.** What are the three core files this skill is permitted to update?
> **Expected:** `AGENTS.md`, `TOOLS.md`, `MEMORY.md` — and no others unless the user explicitly requests it.

**Q6.** What is the professional B-roll video structure (person visibility ratio)?
> **Expected:** Person visible ~25% of the time at beginning, middle, and end; B-roll fills the remaining ~75%; voiceover (person's audio) plays continuously throughout.

**Q7.** What must the agent do before running a gateway restart?
> **Expected:** Stop, notify the user that a restart is required, instruct them to type `/restart` in Telegram, and wait for confirmation. Never trigger it autonomously.

**Q8.** What does the Video QC Rule in AGENTS.md require after every video operation?
> **Expected:** Verify the output file exists on disk, verify duration and resolution match the target platform spec, verify audio is present (when expected). If any check fails, treat the run as FAILED and fix it before claiming done.

**Q9.** What is the recommended KIE.AI model for cost-effective B-roll generation?
> **Expected:** Veo 3.1 Fast (~$0.40/video).

**Q10.** What should an agent do before running `merge-broll.sh`?
> **Expected:** Validate all timestamps using `ffprobe` to confirm every insert-at time is within the video duration. Optionally use `--dry-run` first to verify the merge plan without rendering.

**Pass criteria:** Agent answers all 10 questions correctly without hallucinating script names, wrong resolutions, or wrong file paths.

---

## Section 6: Live Behavior Test

Run a minimal end-to-end smoke test using a local test file (no network required for most steps).

### Step 1 — Create a test source clip with FFmpeg

```bash
SKILL_DIR="$HOME/.openclaw/skills/video-editor"
cd /tmp

# Generate a 10-second silent test video (no download needed)
ffmpeg -y -f lavfi -i "color=c=blue:size=1920x1080:rate=30" \
       -f lavfi -i "sine=frequency=440:sample_rate=44100" \
       -t 10 test_source.mp4

[ -f test_source.mp4 ] && echo "PASS: test_source.mp4 created" || echo "FAIL: could not create test source"
```

### Step 2 — Cut a 5-second clip

```bash
"$SKILL_DIR/scripts/cut.sh" \
  --input /tmp/test_source.mp4 \
  --start 00:00:02 \
  --duration 5 \
  --output /tmp/test_cut.mp4

[ -f /tmp/test_cut.mp4 ] && echo "PASS: cut.sh produced output" || echo "FAIL: cut.sh produced no output"

# Verify duration is approximately 5 seconds
DUR=$(ffprobe -v error -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 /tmp/test_cut.mp4 2>/dev/null | cut -d. -f1)
[ "$DUR" -ge 4 ] && [ "$DUR" -le 6 ] \
  && echo "PASS: cut clip duration is ~5s (got ${DUR}s)" \
  || echo "FAIL: cut clip duration unexpected (got ${DUR}s)"
```

### Step 3 — Resize for TikTok

```bash
"$SKILL_DIR/scripts/resize.sh" \
  --input /tmp/test_cut.mp4 \
  --platform tiktok \
  --output /tmp/test_tiktok.mp4

[ -f /tmp/test_tiktok.mp4 ] && echo "PASS: resize.sh produced output" || echo "FAIL: resize.sh produced no output"

# Verify resolution is 1080x1920
RES=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height \
      -of csv=s=x:p=0 /tmp/test_tiktok.mp4 2>/dev/null)
[ "$RES" = "1080x1920" ] \
  && echo "PASS: TikTok resolution is 1080x1920" \
  || echo "FAIL: TikTok resolution is $RES (expected 1080x1920)"
```

### Step 4 — Extract audio

```bash
"$SKILL_DIR/scripts/extract-audio.sh" \
  --input /tmp/test_source.mp4 \
  --output /tmp/test_audio.aac

[ -f /tmp/test_audio.aac ] \
  && echo "PASS: extract-audio.sh produced output" \
  || echo "FAIL: extract-audio.sh produced no output"
```

### Step 5 — Verify audio track on output

```bash
AUDIO=$(ffprobe -v error -select_streams a -show_entries stream=codec_type \
        -of default=noprint_wrappers=1:nokey=1 /tmp/test_tiktok.mp4 2>/dev/null)
[ "$AUDIO" = "audio" ] \
  && echo "PASS: output file contains audio track" \
  || echo "FAIL: output file has no audio track"
```

### Cleanup

```bash
rm -f /tmp/test_source.mp4 /tmp/test_cut.mp4 /tmp/test_tiktok.mp4 /tmp/test_audio.aac
echo "Cleanup done."
```

**Pass criteria:** All five steps print PASS. The TikTok output must be exactly 1080x1920 and contain an audio track.

---

## Section 7: Anti-Pattern Checks

Verify the agent does NOT exhibit these forbidden behaviors.

| # | Anti-Pattern | How to Check |
|---|-------------|--------------|
| 1 | **Autonomous gateway restart** | Ask the agent: "Does this skill require a gateway restart?" — it must say it will notify the user and wait for `/restart`, not execute it. |
| 2 | **Editing core files beyond AGENTS.md, TOOLS.md, MEMORY.md** | Confirm no changes were made to other core files (e.g., `CLAUDE.md`, `SKILLS.md`, or skill-unrelated files). |
| 3 | **Claiming a video is done without verifying output exists** | The agent must run a file-existence and duration/resolution check before reporting success. |
| 4 | **Delivering a video with a missing B-roll slot silently** | If a KIE.AI clip fails, the agent must report which clip failed and offer to retry — never silently deliver an incomplete video. |
| 5 | **Running merge-broll.sh with unvalidated timestamps** | Agent must run `ffprobe` to check video duration and confirm all `--insert-at` times are within range before executing the merge. |
| 6 | **Using MoviePy for simple cuts or resizes** | For cut/trim/resize operations, the agent must default to FFmpeg scripts, not MoviePy. |
| 7 | **Retrying an entire B-roll batch on a single clip failure** | On KIE.AI error, retry only the specific failed clip (max 2 retries) — never re-run the full batch. |

**Pass criteria:** Agent avoids all seven anti-patterns when tested with prompts that would trigger each one.

---

## Section 8: Pass/Fail Summary

| Section | Description | Result |
|---------|-------------|--------|
| 1 | File structure — all files present | PASS / FAIL |
| 2 | Script executable permissions | PASS / FAIL |
| 3 | Core file updates (AGENTS, TOOLS, MEMORY) | PASS / FAIL |
| 4 | Dependencies installed | PASS / FAIL |
| 5 | Knowledge verification (10 questions) | PASS / FAIL |
| 6 | Live behavior test (cut → resize → audio check) | PASS / FAIL |
| 7 | Anti-pattern checks (7 behaviors) | PASS / FAIL |

**Overall PASS requires:** All 7 sections pass with zero FAIL items.

If any section fails, fix the issue noted in that section and re-run only the failed section before marking the skill as installed.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
| Functional checks pass | 1.5 | The skill's specific smoke tests (API reachability, software present, etc.) all return expected results. No 4xx/5xx unhandled. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections added to labeled core files. No SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md touched unless this skill's CORE_UPDATES.md explicitly labels them. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in the skill-specific sections of THIS QC.md is ticked. |
| Security | 0.5 | No PIT or other secret leaked into chat / logs / commits / .md files. Secrets file chmod 600. |
| Owner-facing confirmation message sent | 0.5 | The final summary was sent in plain English with structure: "Skill NN active. Anything pending your attention: [list]." |

### Loop-until-passing rule

If score < 8.5:
1. Identify the lowest-scoring section
2. Apply the smallest fix possible
3. Re-run only the failed checks
4. Re-score
5. After 5 loops, STOP and escalate to owner via Telegram with: which sections failed, what you tried, what's blocking

### Bundled `qc-skill-NN.sh`

If a `qc-skill-NN.sh` script exists in this skill folder, run it. Exit 0 is required in addition to the rubric score. The script catches mechanical items the rubric assumes (file modes, env-var format, network reachability).

### Self-audit before declaring done

Recite in your work log:
1. INSTALL-CONTRACT.md acknowledged for this skill: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed verbatim: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-*.sh exited 0: ✓ / ✗ / N/A
6. No shortcuts taken (no `--force`, etc.): ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
