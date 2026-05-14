# QC Checklist - Caption Creator (Skill 26)

Run this after installation to verify the skill is correctly installed and functional.

---

## 1. File Structure Checks

Confirm every required file is present at the correct install path.

```bash
ls ~/.openclaw/skills/caption-creator/
```

- [ ] `SKILL.md` exists
- [ ] `INSTALL.md` exists
- [ ] `INSTRUCTIONS.md` exists
- [ ] `EXAMPLES.md` exists
- [ ] `CORE_UPDATES.md` exists
- [ ] `Scripts/` directory exists

```bash
ls ~/.openclaw/skills/caption-creator/Scripts/
```

- [ ] `generate-captions.sh` exists
- [ ] `export-srt.sh` exists
- [ ] `animated_captions.py` exists

**Pass criteria:** All 8 items above are present. No missing files.

---

## 2. Script Permissions Check

Scripts must be executable, not just present.

```bash
ls -la ~/.openclaw/skills/caption-creator/Scripts/
```

- [ ] `generate-captions.sh` has execute bit set (`-rwx...`)
- [ ] `export-srt.sh` has execute bit set (`-rwx...`)
- [ ] `animated_captions.py` is readable (Python; execute bit optional)

**Fix if failing:**
```bash
chmod +x ~/.openclaw/skills/caption-creator/Scripts/generate-captions.sh
chmod +x ~/.openclaw/skills/caption-creator/Scripts/export-srt.sh
```

**Pass criteria:** Both `.sh` scripts are executable.

---

## 3. Core File Update Checks

Verify the two core files were updated during installation per `CORE_UPDATES.md`.

### 3a. TOOLS.md

```bash
grep -n "Caption Creator" ~/.openclaw/TOOLS.md
```

- [ ] Line containing `Caption Creator (Skill 26)` is present
- [ ] Line containing `caption-creator` path is present
- [ ] Line referencing `SRT subtitles` or `captioned videos` is present

### 3b. MEMORY.md

```bash
grep -n "Caption Creator" ~/.openclaw/MEMORY.md
```

- [ ] Line containing `Caption Creator (Skill 26)` is present
- [ ] Line containing `~/.openclaw/skills/caption-creator/` is present

**Pass criteria:** Both files contain the exact entries specified in `CORE_UPDATES.md`. No other core files were modified beyond `TOOLS.md` and `MEMORY.md`.

---

## 4. Dependency Checks

Verify the required system dependencies are installed and reachable.

### 4a. FFmpeg

```bash
ffmpeg -version
```

- [ ] Command exits with version output (not "command not found")
- [ ] Version string begins with `ffmpeg version`

### 4b. Python 3

```bash
python3 --version
```

- [ ] Command returns a version string
- [ ] Version is 3.8 or higher

### 4c. Whisper CLI

```bash
whisper --help
```

- [ ] Command exits without "command not found"
- [ ] Help output mentions `--model` flag

**Pass criteria:** All three commands succeed. If any fail, installation of that dependency is incomplete.

---

## 5. Knowledge Verification Questions

Answer these without looking at the files. If you cannot answer confidently, re-read the relevant `.md` file.

| # | Question | Expected Answer |
|---|----------|-----------------|
| 1 | What are the two main things this skill can do? | Export an SRT subtitle file; burn captions into a new video |
| 2 | What tool does the skill use for speech-to-text? | Whisper (openai-whisper) |
| 3 | What tool does the skill use for rendering captions into video? | FFmpeg |
| 4 | What are the three caption styles supported by `generate-captions.sh`? | `minimal`, `full`, `animated` |
| 5 | Which script handles the animated style internally? | `Scripts/animated_captions.py` |
| 6 | What flag selects the Whisper model? | `--model` |
| 7 | Name two "fast, lower accuracy" Whisper models. | Any two of: `tiny`, `base`, `small` |
| 8 | Name two "slower, higher accuracy" Whisper models. | `medium`, `large` |
| 9 | Which two core files is this skill allowed to update? | `TOOLS.md` and `MEMORY.md` only |
| 10 | What is the install path for this skill? | `~/.openclaw/skills/caption-creator/` |

- [ ] All 10 questions answered correctly

**Pass criteria:** 10/10 correct answers. Anything less means re-reading the relevant skill file before proceeding.

---

## 6. Live Behavior Test

Run a lightweight live check to confirm the scripts invoke without crashing. These tests do NOT require a real video file.

### Test A: `export-srt.sh` — help / no-args response

```bash
~/.openclaw/skills/caption-creator/Scripts/export-srt.sh 2>&1 | head -5
```

- [ ] Script runs (no "Permission denied" or "not found" error)
- [ ] Output indicates missing `--input` argument OR prints usage — it does NOT silently succeed with no output at all

### Test B: `generate-captions.sh` — help / no-args response

```bash
~/.openclaw/skills/caption-creator/Scripts/generate-captions.sh 2>&1 | head -5
```

- [ ] Script runs (no "Permission denied" or "not found" error)
- [ ] Output indicates missing argument OR prints usage

### Test C: `animated_captions.py` — Python syntax check

```bash
python3 -m py_compile ~/.openclaw/skills/caption-creator/Scripts/animated_captions.py && echo "SYNTAX OK"
```

- [ ] Output prints `SYNTAX OK` (no syntax errors)

### Test D: End-to-end SRT export (requires a real video)

> Skip this test if no video file is available. Mark as deferred, not failed.

```bash
~/.openclaw/skills/caption-creator/Scripts/export-srt.sh \
  --input "test_video.mp4" \
  --output "/tmp/qc_test_captions.srt" \
  --model tiny
```

- [ ] Script completes without fatal error
- [ ] `/tmp/qc_test_captions.srt` is created and non-empty
- [ ] SRT file contains timestamp lines in format `00:00:00,000 --> 00:00:00,000`

**Pass criteria for Tests A–C:** All three pass with no errors. Test D is a bonus — pass if attempted and successful.

---

## 7. Anti-Pattern Checks

Confirm the agent did NOT do any of the following during installation.

- [ ] Did NOT modify any core files other than `TOOLS.md` and `MEMORY.md`
- [ ] Did NOT trigger an OpenClaw gateway restart autonomously (must always wait for user `/restart` command)
- [ ] Did NOT add `--style` or `--model` flags to `CORE_UPDATES.md` beyond what is defined in `SKILL.md`
- [ ] Did NOT install Whisper globally with `sudo pip` (should be user-level `pip install`)
- [ ] Did NOT delete or overwrite an existing `~/.openclaw/skills/caption-creator/` folder without warning the user
- [ ] Did NOT run `openclaw gateway restart` without explicit user permission

**Pass criteria:** All six anti-patterns confirmed absent.

---

## 8. Final Pass / Fail Summary

| Section | Status |
|---------|--------|
| 1. File structure | PASS / FAIL |
| 2. Script permissions | PASS / FAIL |
| 3. Core file updates | PASS / FAIL |
| 4. Dependencies | PASS / FAIL |
| 5. Knowledge verification | PASS / FAIL |
| 6. Live behavior tests (A–C) | PASS / FAIL |
| 6d. End-to-end test | PASS / FAIL / DEFERRED |
| 7. Anti-pattern checks | PASS / FAIL |

**Overall result:** PASS only if sections 1–5, 6 (A–C), and 7 are all PASS. Section 6d may be DEFERRED without blocking overall pass.

---

*QC written for Skill 26 - Caption Creator. Re-run this checklist any time the skill is reinstalled or updated.*

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
