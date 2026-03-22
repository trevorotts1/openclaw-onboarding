# Back Yourself Up Protocol - Installation

## Prerequisites
- OpenClaw installed and running
- Teach Yourself Protocol installed first
- Write access to workspace files
- ~/Downloads/ accessible

## Step 1: Find or Create Backup Folder

Search ~/Downloads/ for any folder with "openclaw" and "backup" in the name (case-insensitive):
- OpenClaw Backups  ← standard default name
- openclaw-backups
- OpenClaw Backup
- openclaw backup
- OpenClaw Backups

If found, use it. If not found:
```bash
mkdir -p ~/Downloads/OpenClaw\ Backups/
```

## Step 2: Place the Skill Files

Copy this entire `02-back-yourself-up-protocol/` folder into the master files folder.
All files:
- SKILL.md
- INSTALL.md (this file)
- INSTRUCTIONS.md
- EXAMPLES.md
- CORE_UPDATES.md
- back-yourself-up-protocol-full.md
- back-yourself-up-protocol.skill

## Step 3: Install the Skill Package

```bash
The .skill file is an archive. No CLI command needed - install by following SKILL.md, INSTALL.md, and CORE_UPDATES.md instructions.
```

## Step 4: Verify the Correct Config File

The config file is:
```
~/.openclaw/openclaw.json
```

Verify it exists:
```bash
ls -la ~/.openclaw/openclaw.json
```

It is NOT clawdbot.json. It is NOT config.json. It is NOT any other file.

## Step 5: Test Config Backup

Run a test backup right now:
```bash
cp ~/.openclaw/openclaw.json "~/Downloads/openclaw-backups/models-backup-$(date +'%B %-d at %-I-%M %p').txt"
```

Verify:
```bash
ls -la ~/Downloads/openclaw-backups/
```

The backup file should exist and not be 0 bytes.

## Step 6: Set Up Full Instance Backup Cron

```bash
openclaw cron add --schedule "0 3 1,15 * *" --task "Run full instance backup per Back Yourself Up Protocol"
```

Verify:
```bash
openclaw cron list
```

## Step 7: Update Core Workspace Files

Follow CORE_UPDATES.md exactly.

## Step 8: Verify Installation

Ask the agent:

1. "What do you do before editing the config?"
   Expected: Back it up to the backup folder with a human-readable date, verify backup is not empty, get user permission

2. "What is the config file path?"
   Expected: ~/.openclaw/openclaw.json

3. "What date format do you use for backups?"
   Expected: Human-readable American dates (February 28 at 3-00 PM), never ISO or robot dates

4. "What happens if the backup fails?"
   Expected: STOP. Do not make the edit. Fix the backup first.

5. "When does the full instance backup run?"
   Expected: Every two weeks via cron (1st and 15th of month at 3 AM)

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
