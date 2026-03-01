# Back Yourself Up Protocol - How to Use

## Part 1: Config Backup (Before Every Config Edit)

### When This Applies
Every single time you edit ~/.openclaw/openclaw.json. No exceptions. Not for typos.
Not for one model. Not for a temperature change. Every edit, every time.

### Process
1. Find the backup folder in ~/Downloads/ (search for openclaw + backup)
2. Create backup:
   ```bash
   cp ~/.openclaw/openclaw.json "[BACKUP_FOLDER]/models-backup-$(date +'%B %-d at %-I-%M %p').json"
   ```
3. Verify backup exists and is not 0 bytes
4. Tell the user what you are about to change and why
5. Wait for explicit permission
6. Only then make the edit

### If Backup Fails
STOP. Do not make the edit. Tell the user: "Backup failed with [error]. I will not
edit the config until I can create a valid backup." Fix the backup problem first.

### Date Format
- ALWAYS: `February 28 at 3-00 PM`
- NEVER: `2026-02-28`, `20260228_150000`, `Feb-28-2026`
- bash: `date +'%B %-d at %-I-%M %p'`
- No four-digit year. No military time. No zero-padded months or days.

---

## Part 2: Full Instance Backup (Every Two Weeks)

### What Gets Backed Up

| Item | Location |
|------|----------|
| Main config | ~/.openclaw/openclaw.json |
| Workspace .md files | AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md |
| Memory logs | memory/*.md |
| Secrets | ~/clawd/secrets/.env (if exists) |
| Installed skills | ~/.openclaw/skills/ |
| Cron jobs | openclaw cron list (export) |

### Process
1. Create timestamped folder:
   ```bash
   BACKUP_DIR="[BACKUP_FOLDER]/full-backup-$(date +'%B %-d at %-I-%M %p')"
   mkdir -p "$BACKUP_DIR"
   ```
2. Copy all items above into the backup folder
3. Verify file counts match source
4. Delete full backups older than the most recent 2 (prevent storage bloat)

### Automated Schedule
Cron runs at 3:00 AM on the 1st and 15th of every month.

### Manual Trigger
User says: "Back yourself up", "Run a full backup", "Create a full instance backup"

---

## Config File Identity

The config file is always:
```
~/.openclaw/openclaw.json
```

NOT clawdbot.json. NOT config.json. NOT any other file. If you are unsure, it is
~/.openclaw/openclaw.json.
