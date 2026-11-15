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

## Section 2: Client Voice, Model and Credential Checks

Run the bundled read-only checker, which resolves this installation through `lib-shared.sh`. It reads the live environment first, then this root's `secrets/.env`, `.env`, and `openclaw.json` `env.vars`. It never searches a different client's installation or executes a dotenv file.

```bash
bash "$SKILL_DIR/qc-fish-audio-api-reference.sh"
```

Required: `FISH_AUDIO_API_KEY`, `FISH_AUDIO_VOICE_ID`, `MC_COMPANY_ID`, and a valid independent approval at `<resolved OpenClaw root>/config/fish-audio-voice.json` (or an absolute `FISH_AUDIO_VOICE_BINDING_FILE`). Follow [client voice approval](references/client-voice-approval.md). Missing/wrong voice, foreign company, absent approval, unsupported/free model, malformed data and placeholders must fail. Never print keys, voice IDs or their fingerprints.

**Pass criteria:** checker exits 0. A pending-setup note records unfinished setup; it cannot satisfy this gate. Configuration QC does not assert API authentication, availability or acoustic identity.

---

## Section 3: Core Knowledge Verification

**Q1.** What is the base URL?
> **Expected:** `https://api.fish.audio`

**Q2.** What is the main TTS endpoint?
> **Expected:** `POST /v1/tts`

**Q3.** What model should BlackCEO use by default for client/production work?
> **Expected:** `drama-3` (PAID). Never `s2.1-pro-free` for client production (`s2.1-pro` permitted only via explicit `FISH_AUDIO_MODEL`; no automatic fallback).

**Q4.** What bitrate should be used for phone calls?
> **Expected:** 64 kbps

**Q5.** What bitrate should be used for content / podcasts?
> **Expected:** 192 kbps

**Q6.** What latency should be used for most generation work?
> **Expected:** `normal`

**Q7.** What latency is the real-time exception?
> **Expected:** `balanced` for live streaming / real-time call situations

**Q8.** How does Drama-3 emotion tagging work?
> **Expected:** open-domain natural-language tags in square brackets, like `[calm and professional]`

**Q9.** What inline paralanguage effects are available?
> **Expected:** `(breath)`, `(break)`, `(long-break)`, `(laugh)`, `(sigh)`

**Q10.** What should happen to scripts longer than about 15,000 characters?
> **Expected:** split into about 4,000-character chunks and stitch them after generation.

**Q11.** Why is `s2.1-pro-free` forbidden for client production?
> **Expected:** No SLA/uptime/latency guarantee (best-effort, not contractual), data-retention risk (requests "may be used to improve model quality"), a commercial restriction (products over $1M ARR must contact Fish Audio first), and it is time-limited (free access ends end of July 2026).

**Pass criteria:** 11/11 answers correct.

---

## Section 4: Separate Approved Live Test

After Section 2 passes, announce the provider, selected model and estimated USD and follow the client's paid-call approval/budget. Resolve `OC_ROOT` with `lib-shared.sh` and use:

```bash
python3 "$SKILL_DIR/scripts/fish_audio_config.py" tts --root "$OC_ROOT" \
  --text-file approved-test-script.txt --output /tmp/fish_audio_qc_test.mp3 --use-case phone
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /tmp/fish_audio_qc_test.mp3
```

**Pass criteria:** helper exits 0, nonempty decodable audio, and a listening review against the client's approved voice sample confirms the intended speaker. Do not automatically play audio. Provider failure must not switch models, voices or providers. Report live tests/listening as NOT RUN until performed; offline QC is not live proof.

---

## Section 5: Anti-Pattern Checks

Fail the skill if any of these happen:

- agent accepts a nonempty voice ID without independent client approval, or derives the expected fingerprint from the active setting
- agent silently substitutes a model, voice or provider after a failure
- agent uses `s1`, the interim `s2-pro`, or the free `s2.1-pro-free` tier for CLIENT PRODUCTION content instead of `drama-3` — `s2.1-pro-free` is operator-internal dev/prototyping only (no SLA, data-retention risk, $1M ARR commercial restriction, expires end of July 2026; see SKILL.md "Model Selection: Paid vs Free")
- agent hardcodes `s2.1-pro-free` anywhere as a durable/default model value
- agent puts the `model` value in the request BODY instead of the HTTP header
- agent uses 192 kbps for a phone call
- agent uses 64 kbps for a podcast/content file
- agent uses `balanced` latency for normal offline generation
- agent uses parenthesis-based emotion syntax instead of square-bracket natural language for Drama-3
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
