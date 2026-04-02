# QC Checklist — Skill 28: Cinematic Forge

Run this after installation to verify the skill is installed, the dependencies exist, and the agent understands the production workflow.

---

## Section 1: File Structure + Version Check

```bash
SKILL_DIR="$HOME/.openclaw/skills/cinematic-forge"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/28-cinematic-forge"

echo "Using skill dir: $SKILL_DIR"

for f in SKILL.md INSTALL.md README.md CORE_UPDATES.md skill-version.txt; do
  [ -f "$SKILL_DIR/$f" ] \
    && echo "PASS: $f" \
    || echo "FAIL: $f missing"
done

[ -f "$SKILL_DIR/cinematic-forge.skill" ] \
  && echo "PASS: cinematic-forge.skill present" \
  || echo "INFO: cinematic-forge.skill not present in installed copy"

[ -f "$SKILL_DIR/skill-version.txt" ] && echo "Installed version: $(cat "$SKILL_DIR/skill-version.txt")"
```

**Pass criteria:** All five required files are present and `skill-version.txt` is readable.

---

## Section 2: Dependency Verification

```bash
ffmpeg -version >/dev/null 2>&1 \
  && echo "PASS: ffmpeg found" \
  || echo "FAIL: ffmpeg missing"

curl --version >/dev/null 2>&1 \
  && echo "PASS: curl found" \
  || echo "FAIL: curl missing"

which summarize >/dev/null 2>&1 \
  && echo "PASS: summarize found (recommended)" \
  || echo "INFO: summarize not installed yet"

if [ -d "$HOME/.openclaw/skills/video-frames" ] || [ -d "$HOME/.npm-global/lib/node_modules/openclaw/skills/video-frames" ]; then
  echo "PASS: video-frames skill folder found"
else
  echo "INFO: video-frames skill folder not found"
fi
```

**Expected env vars / credentials:**
- `KIE_API_KEY` for KIE.ai generation
- GHL / Convert and Flow Private Integration Token for uploads (`GHL_API_KEY` in Trevor's environment naming)
- Optional fallback: `IMGBB_API_KEY`
- Optional for reference-video analysis: one of `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`

```bash
for var in KIE_API_KEY GHL_API_KEY IMGBB_API_KEY GEMINI_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY; do
  [ -n "$(printenv "$var" 2>/dev/null)" ] \
    && echo "PASS: $var set" \
    || echo "INFO: $var not set"
done
```

**Pass criteria:** `ffmpeg`, `curl`, and `KIE_API_KEY` are present. Upload credentials must exist for either GHL or imgBB.

---

## Section 3: Core Behavior / Knowledge Verification

The agent should answer these correctly without inventing details.

**Q1.** How many intake questions does Cinematic Forge ask, and how are they asked?
> **Expected:** 14 questions, asked one at a time.

**Q2.** What aspect ratio is always produced first?
> **Expected:** 9:16 vertical first. 16:9 only after 9:16 is approved.

**Q3.** What VEO model should be used by default for generation?
> **Expected:** VEO 3.1 Fast via KIE.ai (`veo3_fast`).

**Q4.** What must happen before any paid generation starts?
> **Expected:** Check KIE.ai credits, calculate the budget estimate, present the estimate, and get user approval.

**Q5.** What file is used for session recovery if the run is interrupted?
> **Expected:** `project-state.json`.

**Q6.** Can narrator voiceover and character dialogue overlap in the same segment?
> **Expected:** No. Never overlap them.

**Q7.** What happens to VEO's built-in audio?
> **Expected:** It is discarded and replaced with separately generated audio layers.

**Q8.** What tools/models are used for audio layers?
> **Expected:** ElevenLabs TTS, ElevenLabs SFX, and Suno via KIE.ai.

**Q9.** Where are text overlays and logos added?
> **Expected:** In post-production with FFmpeg, not inside VEO.

**Q10.** What is the fallback if GHL media upload is not available?
> **Expected:** imgBB.

**Pass criteria:** 10/10 answers correct.

---

## Section 4: Functional Smoke Test

This does not spend credits. It verifies the local assembly parts of the pipeline.

### 4.1 Create a tiny test project structure

```bash
PROJECT_DIR="/tmp/cinematic-forge-qc"
rm -rf "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR"/{images,segments,audio/dialogue,audio/narrator,audio/sfx,audio/music,final}

cat > "$PROJECT_DIR/project-state.json" <<'JSON'
{
  "project_name": "qc-test",
  "status": "pre-production",
  "segments": [],
  "audio": {
    "dialogue": [],
    "narrator": [],
    "sfx": [],
    "music": []
  }
}
JSON

[ -f "$PROJECT_DIR/project-state.json" ] \
  && echo "PASS: project-state.json created" \
  || echo "FAIL: could not create project-state.json"
```

### 4.2 Create two short sample segments with FFmpeg

```bash
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -t 2 "$PROJECT_DIR/segments/segment_1.mp4" >/dev/null 2>&1
ffmpeg -y -f lavfi -i "color=c=white:size=1080x1920:rate=30" -t 2 "$PROJECT_DIR/segments/segment_2.mp4" >/dev/null 2>&1

for f in "$PROJECT_DIR/segments/segment_1.mp4" "$PROJECT_DIR/segments/segment_2.mp4"; do
  [ -f "$f" ] && echo "PASS: $(basename "$f") created" || echo "FAIL: $(basename "$f") missing"
done
```

### 4.3 Merge the two segments with FFmpeg concat

```bash
cat > "$PROJECT_DIR/final/concat_list.txt" <<EOF
file '$PROJECT_DIR/segments/segment_1.mp4'
file '$PROJECT_DIR/segments/segment_2.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i "$PROJECT_DIR/final/concat_list.txt" -c copy "$PROJECT_DIR/final/merged.mp4" >/dev/null 2>&1

[ -f "$PROJECT_DIR/final/merged.mp4" ] \
  && echo "PASS: merged.mp4 created" \
  || echo "FAIL: merged.mp4 missing"

ffprobe -v error -show_entries stream=width,height -of csv=p=0 "$PROJECT_DIR/final/merged.mp4"
```

**Expected:** merged file exists and reports `1080,1920`.

---

## Section 5: Optional Live API Checks

Run only if credentials are available and you are intentionally testing live generation.

### 5.1 Check KIE credits endpoint

```bash
curl -s "https://api.kie.ai/api/v1/user/credits" \
  -H "Authorization: Bearer $KIE_API_KEY" | python3 -m json.tool | head -20
```

**Expected:** Valid JSON response, not 401/403.

### 5.2 Verify GHL upload auth can at least read location info

```bash
curl -s \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28" \
  "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" | python3 -m json.tool | head -20
```

**Expected:** Valid JSON for the location. If GHL is unavailable, imgBB may be used as fallback instead.

---

## Section 6: Anti-Pattern Checks

Fail the skill if any of these happen:

- Agent skips the 14-question intake
- Agent asks multiple intake questions at once
- Agent starts generation before budget approval
- Agent produces 16:9 first instead of 9:16
- Agent keeps VEO's built-in audio instead of replacing it
- Agent overlaps narrator and dialogue in the same segment
- Agent puts logos or on-screen text inside VEO instead of post-production
- Agent upscales with Topaz before draft approval
- Agent fails to maintain `project-state.json` after each completed step

**Pass criteria:** Zero anti-patterns triggered.
