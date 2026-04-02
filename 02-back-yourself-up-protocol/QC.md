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
