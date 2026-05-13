# QC Checklist: Back Yourself Up Protocol (BYUP)

## 1. Purpose
Enables mandatory config backups and recurring full-instance backups before any risky OpenClaw changes.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] The correct config file path from the skill is used: `~/.openclaw/openclaw.json` for this repo context, with no fallback to unrelated config filenames.
- [ ] A backup folder is detected or created under the documented downloads location, with human-readable backup filenames.
- [ ] The scheduled backup job exists: `openclaw cron list` includes the BYUP backup entry.
- [ ] No executable helper script is required in the skill folder; if a local backup shell script was added later, it must be executable.

## 3. Dependency Checks
- [ ] TYP (skill 01) is already installed.
- [ ] The config file exists and is readable before the first backup attempt.
- [ ] OpenClaw cron support is available: `openclaw cron add ...` and `openclaw cron list` work.
- [ ] Write access exists to the backup folder and to core workspace files updated by `CORE_UPDATES.md`.

## 4. Key Detection
- [ ] No external API key is required for BYUP.
- [ ] Smart detection should validate paths, not secrets: check `~/.openclaw/openclaw.json`, then `~/.openclaw/openclaw.json`, then the repo-specific data path if the environment is containerized.
- [ ] QC fails if the agent asks for a backup “key” or treats this skill as credential-driven.

## 5. Functional Checks
- [ ] Run a test backup of `~/.openclaw/openclaw.json` into the backup folder and confirm the file exists and is not 0 bytes.
- [ ] Verify the filename uses the required human-readable format, e.g. `models-backup-February 23 at 11-00 AM.txt`.
- [ ] Simulate a config edit request and verify the agent asks for explicit permission **after** backup creation and **before** editing.
- [ ] Validate the cron entry exists and matches the documented cadence.
- [ ] Ask the agent what happens if backup creation fails. Expected answer: STOP and do not proceed with the edit.

## 6. QC Score
- Score this skill from **0 to 10** after running the checks above.
- Suggested rubric:
  - **10/10**: All installation, dependency, key-detection, and functional checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, but one or two non-critical items need cleanup or documentation fixes.
  - **6-7/10**: Basic install exists, but the skill is missing a meaningful validation, dependency, or behavior requirement.
  - **0-5/10**: Missing prerequisite pieces, broken verification path, wrong secrets handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 7. QC Loop Rule
- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round:
  1. Record exactly which checklist items failed.
  2. Apply the smallest targeted fix.
  3. Re-run only the failed checks plus any directly affected dependencies.
- If the skill still fails after the **5th round**, stop and escalate instead of continuing to loop.

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
