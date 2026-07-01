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

for s in qc-cinematic-forge.sh qc-output.sh; do
  [ -f "$SKILL_DIR/$s" ] \
    && echo "PASS: $s present" \
    || echo "FAIL: $s missing"
done

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
- GHL / Convert and Flow Private Integration Token for uploads: `GOHIGHLEVEL_API_KEY` (a PIT) + `GOHIGHLEVEL_LOCATION_ID`
- Optional fallback (reference images only): `IMGBB_API_KEY`
- Optional for reference-video analysis: one of `GEMINI_API_KEY` or `OPENAI_API_KEY`

```bash
for var in KIE_API_KEY GOHIGHLEVEL_API_KEY GOHIGHLEVEL_LOCATION_ID IMGBB_API_KEY GEMINI_API_KEY OPENAI_API_KEY; do
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

### 4.4 Output-QC gate self-test (`qc-output.sh`)

This verifies the delivery gate actually enforces the rules. It spends no credits.

```bash
SKILL_DIR="$HOME/.openclaw/skills/cinematic-forge"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/28-cinematic-forge"
[ -d /data/.openclaw/skills/28-cinematic-forge ] && SKILL_DIR="/data/.openclaw/skills/28-cinematic-forge"
QC="$SKILL_DIR/qc-output.sh"

# A) 1080x1920, 2s, SILENT black clip (no audio stream) -> must FAIL (exit 1)
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -t 2 /tmp/qc_silent.mp4 >/dev/null 2>&1
bash "$QC" /tmp/qc_silent.mp4 2 1080x1920; echo "silent clip exit=$?  (expected 1)"

# B) 1080x1920, 2s, with a sine tone -> must PASS (exit 0)
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -f lavfi -i "sine=frequency=440:duration=2" \
  -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest /tmp/qc_tone.mp4 >/dev/null 2>&1
bash "$QC" /tmp/qc_tone.mp4 2 1080x1920; echo "tone clip exit=$?  (expected 0)"
```

**Pass criteria:** the silent clip exits **1**, the tone clip exits **0**. The agent must see `qc-output.sh` exit 0 on the real deliverable before sending any link (enforced in Phase 4 and Phase 6).

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
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" | python3 -m json.tool | head -20
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
- Agent delivers the final video without `qc-output.sh` exiting 0 (the output-QC gate is mandatory)

**Pass criteria:** Zero anti-patterns triggered.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
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
