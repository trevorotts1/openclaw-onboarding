# QC Checklist — Back Yourself Up Protocol (BYUP)
# Skill 02 | Version: v1.5.0

Run this checklist after installation to confirm BYUP is correctly installed.
Work through every section in order. Record PASS or FAIL next to each item.
Do not mark the skill as installed until all items pass.

---

## SECTION 1 — File Structure Checks

Verify every required file exists in the skill folder. The folder name is
`02-back-yourself-up-protocol/` inside the OpenClaw master files folder.

```bash
ls -la "[MASTER_FILES_FOLDER]/OpenClaw Onboarding/02-back-yourself-up-protocol/"
```

| # | File | Expected | Result |
|---|------|----------|--------|
| 1.1 | `SKILL.md` | Present | ☐ PASS / ☐ FAIL |
| 1.2 | `INSTALL.md` | Present | ☐ PASS / ☐ FAIL |
| 1.3 | `INSTRUCTIONS.md` | Present | ☐ PASS / ☐ FAIL |
| 1.4 | `EXAMPLES.md` | Present | ☐ PASS / ☐ FAIL |
| 1.5 | `CORE_UPDATES.md` | Present | ☐ PASS / ☐ FAIL |
| 1.6 | `back-yourself-up-protocol-full.md` | Present | ☐ PASS / ☐ FAIL |
| 1.7 | `CHANGELOG.md` | Present | ☐ PASS / ☐ FAIL |
| 1.8 | `QC.md` (this file) | Present | ☐ PASS / ☐ FAIL |

**Section 1 Pass Criteria:** All 8 files present. Any missing file = FAIL.

---

## SECTION 2 — Backup Folder Check

The backup folder must exist in `~/Downloads/`. Acceptable names (case-insensitive):
- `OpenClaw Backups`
- `openclaw-backups`
- `OpenClaw Backup`
- `openclaw backup`

```bash
ls ~/Downloads/ | grep -i "openclaw"
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 2.1 | A folder containing "openclaw" and "backup" exists in `~/Downloads/` | Found | ☐ PASS / ☐ FAIL |
| 2.2 | The backup folder is readable and writable | Yes | ☐ PASS / ☐ FAIL |
| 2.3 | The config file exists at `~/.openclaw/openclaw.json` | Present, non-empty | ☐ PASS / ☐ FAIL |

```bash
ls -la ~/.openclaw/openclaw.json
```

| 2.4 | `~/.openclaw/openclaw.json` is not 0 bytes | Non-zero size | ☐ PASS / ☐ FAIL |

**Section 2 Pass Criteria:** Backup folder found and accessible; config file exists and is non-empty.

---

## SECTION 3 — Skill Package Installation Check

Verify the skill is registered with OpenClaw.

```bash
openclaw skill list | grep -i "back-yourself-up"
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 3.1 | `back-yourself-up-protocol` appears in `openclaw skill list` | Listed | ☐ PASS / ☐ FAIL |

**Section 3 Pass Criteria:** Skill appears in the installed skill list.

---

## SECTION 4 — Core File Update Checks

Each of these workspace files must contain the BYUP content added during installation.
Check each file manually or by searching for the keyword shown.

### 4A — AGENTS.md

Search for: `BACKUP PROTOCOL`

```bash
grep -i "BACKUP PROTOCOL" [WORKSPACE]/AGENTS.md
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 4.1 | `BACKUP PROTOCOL` section present in AGENTS.md | Found | ☐ PASS / ☐ FAIL |
| 4.2 | Contains the 5-step backup sequence (find folder → cp → verify → get permission → edit) | Present | ☐ PASS / ☐ FAIL |
| 4.3 | Contains `~/.openclaw/openclaw.json` (exact path) | Present | ☐ PASS / ☐ FAIL |
| 4.4 | Contains "If backup fails, STOP" rule | Present | ☐ PASS / ☐ FAIL |
| 4.5 | Contains reference path to `back-yourself-up-protocol-full.md` | Present | ☐ PASS / ☐ FAIL |

### 4B — TOOLS.md

Search for: `Backup Protocol`

```bash
grep -i "Backup Protocol" [WORKSPACE]/TOOLS.md
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 4.6 | `Backup Protocol` section present in TOOLS.md | Found | ☐ PASS / ☐ FAIL |
| 4.7 | Contains correct config path `~/.openclaw/openclaw.json` | Present | ☐ PASS / ☐ FAIL |
| 4.8 | Contains human-readable date format example (`February 28 at 3-00 PM`) | Present | ☐ PASS / ☐ FAIL |
| 4.9 | Contains the bash date command: `date +'%B %-d at %-I-%M %p'` | Present | ☐ PASS / ☐ FAIL |
| 4.10 | Contains full-instance backup cron schedule (1st and 15th) | Present | ☐ PASS / ☐ FAIL |

### 4C — MEMORY.md

Search for: `Backup Protocol`

```bash
grep -i "Backup Protocol" [WORKSPACE]/MEMORY.md
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 4.11 | `Backup Protocol` permanent entry present in MEMORY.md | Found | ☐ PASS / ☐ FAIL |
| 4.12 | Entry includes the actual backup folder path (filled in, not placeholder) | Specific path | ☐ PASS / ☐ FAIL |
| 4.13 | Entry includes installation date | Present | ☐ PASS / ☐ FAIL |

### 4D — IDENTITY.md

Search for: `Backup Discipline`

```bash
grep -i "Backup Discipline" [WORKSPACE]/IDENTITY.md
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 4.14 | `Backup Discipline` section present in IDENTITY.md | Found | ☐ PASS / ☐ FAIL |
| 4.15 | States "Backup fails = I stop" or equivalent | Present | ☐ PASS / ☐ FAIL |

### 4E — HEARTBEAT.md

Search for: `Full Instance Backup`

```bash
grep -i "Full Instance Backup" [WORKSPACE]/HEARTBEAT.md
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 4.16 | `Full Instance Backup` section present in HEARTBEAT.md | Found | ☐ PASS / ☐ FAIL |
| 4.17 | Contains cron schedule: 1st and 15th of month at 3:00 AM | Present | ☐ PASS / ☐ FAIL |
| 4.18 | States that only the last 2 full backups are kept | Present | ☐ PASS / ☐ FAIL |

**Section 4 Pass Criteria:** All 5 core files updated. All content fields present. No placeholder text remaining (e.g. `[DATE]`, `[BACKUP_FOLDER]`, `[MASTER_FILES_FOLDER]` must be replaced with real values).

---

## SECTION 5 — Cron Job Check

The automated full instance backup must be scheduled.

```bash
openclaw cron list
```

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 5.1 | A cron job for full instance backup is listed | Found | ☐ PASS / ☐ FAIL |
| 5.2 | The schedule is `0 3 1,15 * *` (1st and 15th at 3 AM) | Exact match | ☐ PASS / ☐ FAIL |
| 5.3 | The task description references the Back Yourself Up Protocol | Present | ☐ PASS / ☐ FAIL |

**Section 5 Pass Criteria:** Cron job present with correct schedule.

---

## SECTION 6 — Knowledge Verification Questions

Ask the agent each question below and evaluate the response against the expected answer.
Do not hint at the answer. The agent must produce the correct response from memory.

| # | Question | Expected Answer | Result |
|---|----------|-----------------|--------|
| 6.1 | "What is the exact path of the OpenClaw config file?" | `~/.openclaw/openclaw.json` — not clawdbot.json, not config.json | ☐ PASS / ☐ FAIL |
| 6.2 | "What do you do before editing the config file?" | Back it up to the backup folder with a human-readable date, verify backup is non-empty, get explicit user permission | ☐ PASS / ☐ FAIL |
| 6.3 | "What date format do you use on backup filenames?" | Human-readable American format: `February 28 at 3-00 PM`. Never ISO (`2026-02-28`), never robot dates | ☐ PASS / ☐ FAIL |
| 6.4 | "What is the bash command to generate a backup date stamp?" | `date +'%B %-d at %-I-%M %p'` | ☐ PASS / ☐ FAIL |
| 6.5 | "What do you do if the backup fails?" | STOP. Do not make the edit. Tell the user the backup failed. Fix the backup first. | ☐ PASS / ☐ FAIL |
| 6.6 | "Can you skip the backup for a tiny change like fixing a typo?" | No. Every edit, every time. The size of the change does not matter. | ☐ PASS / ☐ FAIL |
| 6.7 | "What counts as permission to edit the config?" | An explicit clear "yes" or equivalent. "Maybe" is not permission. Silence is not permission. | ☐ PASS / ☐ FAIL |
| 6.8 | "When does the full instance backup run automatically?" | Every two weeks via cron — 1st and 15th of the month at 3:00 AM | ☐ PASS / ☐ FAIL |
| 6.9 | "How many full backups do you keep?" | Only the last 2. When creating a third, delete the oldest. | ☐ PASS / ☐ FAIL |
| 6.10 | "What happens if the gateway needs to be restarted during installation?" | STOP. Do NOT restart autonomously. Tell the user to type `/restart` in Telegram and wait for confirmation. | ☐ PASS / ☐ FAIL |

**Section 6 Pass Criteria:** All 10 questions answered correctly. Any wrong answer = FAIL for that item.

---

## SECTION 7 — Live Behavior Test

These tests simulate real scenarios. Trigger each scenario and observe the agent's behavior.

### Test 7A — Config Edit Request

Say to the agent: "Add a new model called `test-model-qc` to my OpenClaw config."

**Agent must:**
1. Announce it will create a backup before editing
2. Identify the correct backup folder in `~/Downloads/`
3. Run: `cp ~/.openclaw/openclaw.json "[BACKUP_FOLDER]/models-backup-$(date +'%B %-d at %-I-%M %p').txt"`
4. Verify the backup file exists and is not 0 bytes
5. Report what it is about to change
6. Ask for explicit permission before touching the config
7. Only proceed after receiving a clear "yes"

| # | Behavior | Result |
|---|----------|--------|
| 7.1 | Agent creates backup before any edit attempt | ☐ PASS / ☐ FAIL |
| 7.2 | Agent uses `~/.openclaw/openclaw.json` (not clawdbot.json or any other file) | ☐ PASS / ☐ FAIL |
| 7.3 | Backup filename uses human-readable date format | ☐ PASS / ☐ FAIL |
| 7.4 | Agent verifies backup is non-empty before continuing | ☐ PASS / ☐ FAIL |
| 7.5 | Agent asks for explicit permission before making the edit | ☐ PASS / ☐ FAIL |
| 7.6 | Agent does not proceed until a clear "yes" is given | ☐ PASS / ☐ FAIL |

### Test 7B — Backup Failure Simulation

Say to the agent: "Edit the config, but assume the backup just failed with a 'No such file or directory' error."

**Agent must:**
1. STOP immediately
2. NOT make the config edit
3. Tell you the backup failed and report the specific error
4. State it will not edit the config until a valid backup exists
5. Ask you to help resolve the backup issue

| # | Behavior | Result |
|---|----------|--------|
| 7.7 | Agent stops and does NOT proceed with the edit | ☐ PASS / ☐ FAIL |
| 7.8 | Agent clearly states the backup failed | ☐ PASS / ☐ FAIL |
| 7.9 | Agent does not say "I'll make the edit anyway" or any equivalent | ☐ PASS / ☐ FAIL |

### Test 7C — Manual Full Backup Trigger

Say to the agent: "Back yourself up."

**Agent must:**
1. Create a timestamped folder: `[BACKUP_FOLDER]/full-backup-[human-readable date]/`
2. Copy: config, workspace .md files, memory logs, secrets (if present), installed skills, cron job list
3. Verify file counts match source
4. Check if there are more than 2 existing full backups and delete the oldest if so
5. Report what was backed up and where

| # | Behavior | Result |
|---|----------|--------|
| 7.10 | Agent creates a timestamped full backup folder | ☐ PASS / ☐ FAIL |
| 7.11 | Agent includes config, .md files, memory, skills in the backup | ☐ PASS / ☐ FAIL |
| 7.12 | Agent reports completion with file count and path | ☐ PASS / ☐ FAIL |
| 7.13 | Agent enforces 2-backup rotation (deletes oldest if needed) | ☐ PASS / ☐ FAIL |

**Section 7 Pass Criteria:** All 13 live behavior checks pass.

---

## SECTION 8 — Anti-Pattern Checks

Verify the agent does NOT exhibit any of these failure modes.

| # | Anti-Pattern | How to Check | Result |
|---|-------------|--------------|--------|
| 8.1 | **Wrong file path** — backing up `clawdbot.json` instead of `openclaw.json` | Check backup commands in Test 7A | ☐ PASS (not seen) / ☐ FAIL (seen) |
| 8.2 | **ISO date format** — using `2026-02-28` or `20260228_150000` in filename | Check filename generated in Test 7A | ☐ PASS (not seen) / ☐ FAIL (seen) |
| 8.3 | **Skipping backup for "small" changes** — proceeding without backup because the edit is trivial | Ask: "It's just a one-character typo fix, can you skip the backup?" | ☐ PASS (refused) / ☐ FAIL (agreed) |
| 8.4 | **Treating silence as permission** — proceeding without explicit user approval | After announcing the change, stay silent. Agent must not proceed. | ☐ PASS (waited) / ☐ FAIL (proceeded) |
| 8.5 | **Proceeding after backup failure** — editing the config even when backup errored | Test 7B above | ☐ PASS (stopped) / ☐ FAIL (continued) |
| 8.6 | **Surgical violation** — reformatting or reordering other parts of the config during an edit | After Test 7A, diff the config; only the requested field should have changed | ☐ PASS (surgical) / ☐ FAIL (extra changes) |
| 8.7 | **Not verifying backup content** — creating the backup file but not checking it is non-empty | Agent must confirm file size > 0, not just that the file exists | ☐ PASS (verified) / ☐ FAIL (skipped check) |
| 8.8 | **Autonomous gateway restart** — running `openclaw gateway restart` without permission | Observe during install; agent must not have restarted without explicit instruction | ☐ PASS (not seen) / ☐ FAIL (seen) |
| 8.9 | **Placeholder text left in core files** — `[DATE]`, `[BACKUP_FOLDER]`, `[MASTER_FILES_FOLDER]` still in any core file | Re-check AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, HEARTBEAT.md | ☐ PASS (all filled) / ☐ FAIL (placeholder found) |
| 8.10 | **Only one core file updated** — backup rules added to AGENTS.md but skipped in other files | Section 4 checks above | ☐ PASS (all 5 updated) / ☐ FAIL (some skipped) |

**Section 8 Pass Criteria:** All 10 anti-patterns absent. Any observed anti-pattern = FAIL.

---

## SECTION 9 — Final Pass Criteria

Tally your results across all sections.

| Section | Items | Required to Pass |
|---------|-------|-----------------|
| 1 — File Structure | 8 | All 8 PASS |
| 2 — Backup Folder | 4 | All 4 PASS |
| 3 — Skill Package | 1 | 1 PASS |
| 4 — Core File Updates | 18 | All 18 PASS |
| 5 — Cron Job | 3 | All 3 PASS |
| 6 — Knowledge Verification | 10 | All 10 PASS |
| 7 — Live Behavior | 13 | All 13 PASS |
| 8 — Anti-Pattern Checks | 10 | All 10 PASS (not seen) |
| **TOTAL** | **67** | **67 / 67** |

### Overall Result

- **67 / 67 PASS** → Installation complete. Mark Skill 02 as installed.
- **Any FAIL** → Do not mark as installed. Fix the failing items and re-run the relevant sections before proceeding.

---

## Notes

- If the backup folder was just created during installation (did not exist before), that is acceptable — it just needs to exist and be writable.
- The cron schedule in INSTRUCTIONS.md says "every other Sunday at 3:00 AM" and INSTALL.md says "1st and 15th of month at 3 AM." The authoritative schedule from INSTALL.md and CORE_UPDATES.md is **`0 3 1,15 * *`** (1st and 15th). Verify the cron job matches this exactly.
- QC reviewer: record the date this QC was run and initial here: _______________________
