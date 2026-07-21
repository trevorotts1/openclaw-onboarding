# QC Checklist — Skill 28: Cinematic Forge

Run this after installation to verify the skill is installed, the dependencies exist, and the agent understands the production workflow.

---

## Section 1: File Structure + Version Check

```bash
# ONE resolver, the PREFIXED directory, matching the repository, INSTALL.md and
# SKILL.md's Phase 0. The old two-step fallback (unprefixed first, prefixed
# second) is what let a mis-placed install pass this checklist while the runtime
# looked somewhere else for the helper scripts (T2-30).
if [ -d /data/.openclaw/skills/28-cinematic-forge ]; then
  SKILL_DIR="/data/.openclaw/skills/28-cinematic-forge"     # VPS
else
  SKILL_DIR="$HOME/.openclaw/skills/28-cinematic-forge"     # Mac
fi

[ -d "$SKILL_DIR" ] \
  && echo "PASS: skill dir $SKILL_DIR" \
  || echo "FAIL: no 28-cinematic-forge directory — the skill is not installed where the runtime looks"

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
- Optional, REFERENCE IMAGES ONLY: `IMGBB_API_KEY` — imgBB serves still images and animated GIFs and will not host the final MP4
- Optional for reference-video analysis: one of `GEMINI_API_KEY` or `OPENAI_API_KEY`

```bash
for var in KIE_API_KEY GOHIGHLEVEL_API_KEY GOHIGHLEVEL_LOCATION_ID IMGBB_API_KEY GEMINI_API_KEY OPENAI_API_KEY; do
  [ -n "$(printenv "$var" 2>/dev/null)" ] \
    && echo "PASS: $var set" \
    || echo "INFO: $var not set"
done
```

**Pass criteria:** `ffmpeg`, `curl`, `jq` and `KIE_API_KEY` are present, and the client has a VIDEO-CAPABLE destination for the finished MP4 — GHL/Convert and Flow, or a store they control. imgBB does not satisfy this: it cannot host the deliverable.

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

**Q10.** What is the fallback if GHL media upload is not available for the FINAL VIDEO?
> **Expected:** a video-capable store the client controls — their own object
> storage or CDN, their site's media library, or a video host they own — verified
> the same way (asset identifier from the upload response, then download and
> probe the hosted object). **NOT imgBB:** imgBB hosts still images and animated
> GIFs only and will not host an MP4. imgBB is for reference images.

**Q11.** What does the delivery gate check the finished file against?
> **Expected:** the delivery-requirements record derived from the APPROVED
> intake before generation (approved aspect ratio, approved duration, and each
> requested overlay), plus a post-production receipt per requested
> transformation whose output hash is the artifact being delivered — never
> numbers supplied by the caller at delivery time.

**Q12.** Which file is uploaded when the client asked for captions and a logo?
> **Expected:** `$FINAL_ARTIFACT` — the variable that each post-production step
> advances only after its command succeeds. Never a fixed filename: reading a
> fixed `final_video.mp4` is how the un-transformed file used to ship while every
> stage reported success.

**Pass criteria:** 12/12 answers correct.

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

This verifies the gate actually enforces its rules, in BOTH directions. It spends
no credits.

```bash
if [ -d /data/.openclaw/skills/28-cinematic-forge ]; then
  SKILL_DIR="/data/.openclaw/skills/28-cinematic-forge"
else
  SKILL_DIR="$HOME/.openclaw/skills/28-cinematic-forge"
fi
QC="$SKILL_DIR/qc-output.sh"
W="$(mktemp -d)"

# A) TECHNICAL mode — a silent black clip must FAIL (exit 1)
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -t 2 "$W/silent.mp4" >/dev/null 2>&1
bash "$QC" "$W/silent.mp4" 2 1080x1920; echo "silent clip exit=$?  (expected 1)"

# B) TECHNICAL mode — a clip with a sine tone must PASS (exit 0), and must say
#    IN AS MANY WORDS that this is not a delivery verdict.
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -f lavfi -i "sine=frequency=440:duration=2" \
  -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$W/tone.mp4" >/dev/null 2>&1
bash "$QC" "$W/tone.mp4" 2 1080x1920; echo "tone clip exit=$?  (expected 0)"

# C) DELIVERY mode — the client asked for captions and a logo, and the file
#    carries NEITHER. It must FAIL, naming the missing transformation. This is
#    the case the old gate passed: it only ever compared caller-supplied numbers.
cat > "$W/reqs.json" <<JSON
{"approval_ref":"qc-selftest","aspect_ratio":"9:16","dimensions":"1080x1920",
 "duration_seconds":2,"requires_captions":true,"requires_logo":true}
JSON
bash "$QC" --artifact "$W/tone.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts"
echo "un-transformed artifact exit=$?  (expected 1 — the receipts are missing)"

# D) DELIVERY mode — the same file WITH a receipt chain that ends at it must
#    PASS. (Anti-false-positive: a gate that fails everything enforces nothing.)
mkdir -p "$W/receipts"
SHA="$(shasum -a 256 "$W/tone.mp4" | awk '{print $1}')"
for step in captions logo; do
  printf '{"step":"%s","output":"%s","output_sha256":"%s"}\n' "$step" "$W/tone.mp4" "$SHA" > "$W/receipts/$step.json"
done
bash "$QC" --artifact "$W/tone.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts"
echo "receipted artifact exit=$?  (expected 0)"

# E) DELIVERY mode — a request-WRONG file (approved 9:16, delivered 16:9) must
#    FAIL even though it is a perfectly valid video.
ffmpeg -y -f lavfi -i "color=c=black:size=1920x1080:rate=30" -f lavfi -i "sine=frequency=440:duration=2" \
  -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$W/wrong.mp4" >/dev/null 2>&1
bash "$QC" --artifact "$W/wrong.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts"
echo "wrong aspect ratio exit=$?  (expected 1)"

rm -rf "$W"
```

**Pass criteria:** A exits **1**, B exits **0** and prints that it is not a
delivery verdict, C exits **1**, D exits **0**, E exits **1**. The agent must see
the DELIVERY mode exit 0 on the real deliverable — after post-production, before
the upload — and again with `--upload-response` after the upload, before sending
any link.

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

**Expected:** Valid JSON for the location. If GHL is unavailable, the final video goes to a video-capable store the client controls — never imgBB, which cannot host an MP4.

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
- Agent delivers the final video without `qc-output.sh` **delivery mode** exiting 0 (the technical mode is not a delivery verdict)
- Agent uploads a fixed filename instead of `$FINAL_ARTIFACT`, so a requested caption/overlay/logo pass is dropped from the delivered file
- Agent sends a link without re-running the gate with `--upload-response` against the returned asset identifier
- Agent points the final-video fallback at imgBB

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
