# QC Checklist — Skill 30: Fish Audio API Reference

Run this after installation to verify the reference files, credentials, and live TTS behavior.

---

## Section 1: File Structure + Version Check

```bash
SKILL_DIR="$HOME/.openclaw/skills/30-fish-audio-api-reference"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/fish-audio-api-reference"

echo "Using skill dir: $SKILL_DIR"

for f in SKILL.md INSTALL.md README.md fish-audio-voice-sop.md skill-version.txt; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

[ -f "$SKILL_DIR/references/fish-audio-api-reference.md" ] \
  && echo "PASS: references/fish-audio-api-reference.md" \
  || echo "FAIL: API reference missing"

[ -f "$SKILL_DIR/skill-version.txt" ] && echo "Installed version: $(cat "$SKILL_DIR/skill-version.txt")"
```

**Pass criteria:** all required files exist.

---

## Section 2: Credential + Env Checks

Required values:
- `FISH_AUDIO_API_KEY`
- `FISH_AUDIO_VOICE_ID`

```bash
source ~/clawd/secrets/.env 2>/dev/null || true
for var in FISH_AUDIO_API_KEY FISH_AUDIO_VOICE_ID; do
  [ -n "$(printenv "$var" 2>/dev/null)" ] \
    && echo "PASS: $var set" \
    || echo "FAIL: $var missing"
done
```

If credentials are intentionally pending, verify the pending note exists instead of failing silently:

```bash
grep -A5 -i "fish audio" "$HOME/.openclaw/skills/.pending-setup.md" 2>/dev/null || echo "INFO: no pending-setup note found"
```

**Pass criteria:** credentials exist OR there is an explicit pending-setup note.

---

## Section 3: Core Knowledge Verification

**Q1.** What is the base URL?
> **Expected:** `https://api.fish.audio`

**Q2.** What is the main TTS endpoint?
> **Expected:** `POST /v1/tts`

**Q3.** What model should BlackCEO use by default?
> **Expected:** `s2-pro`

**Q4.** What bitrate should be used for phone calls?
> **Expected:** 64 kbps

**Q5.** What bitrate should be used for content / podcasts?
> **Expected:** 192 kbps

**Q6.** What latency should be used for most generation work?
> **Expected:** `normal`

**Q7.** What latency is the real-time exception?
> **Expected:** `balanced` for live streaming / real-time call situations

**Q8.** How does S2-Pro emotion tagging work?
> **Expected:** open-domain natural-language tags in square brackets, like `[calm and professional]`

**Q9.** What inline paralanguage effects are available?
> **Expected:** `(breath)`, `(break)`, `(long-break)`, `(laugh)`, `(sigh)`

**Q10.** What should happen to scripts longer than about 15,000 characters?
> **Expected:** split into about 4,000-character chunks and stitch them after generation.

**Pass criteria:** 10/10 answers correct.

---

## Section 4: Live API Smoke Test

Run only if credentials are present.

```bash
source ~/clawd/secrets/.env 2>/dev/null || true

HTTP_CODE=$(curl -s -o /tmp/fish_audio_qc_test.mp3 -w "%{http_code}" \
  -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d "{\"text\":\"Fish Audio QC passed. Ready.\",\"reference_id\":\"$FISH_AUDIO_VOICE_ID\",\"format\":\"mp3\",\"mp3_bitrate\":64,\"normalize\":true,\"latency\":\"normal\"}")

echo "HTTP: $HTTP_CODE"
ls -lh /tmp/fish_audio_qc_test.mp3 2>/dev/null || true
```

**Expected:** HTTP `200` and a non-empty MP3 file.

Optional audio sanity check:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /tmp/fish_audio_qc_test.mp3
```

---

## Section 5: Anti-Pattern Checks

Fail the skill if any of these happen:

- agent uses `s1` instead of `s2-pro` without explicit instruction
- agent uses 192 kbps for a phone call
- agent uses 64 kbps for a podcast/content file
- agent uses `balanced` latency for normal offline generation
- agent uses parenthesis-based emotion syntax instead of square-bracket natural language for S2-Pro
- agent sends very long scripts in one call instead of chunking
- agent guesses endpoint details without consulting the reference

**Pass criteria:** zero anti-patterns triggered.

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
