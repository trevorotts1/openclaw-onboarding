# Back Yourself Up Protocol - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided. Do not modify it.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add under behavioral rules:

```
### BACKUP PROTOCOL [PRIORITY: CRITICAL]
Before EVERY edit to ~/.openclaw/openclaw.json - no matter how small:
1. Find backup folder in ~/Downloads/ (search for openclaw + backup)
2. cp ~/.openclaw/openclaw.json "[BACKUP_FOLDER]/models-backup-$(date +'%B %-d at %-I-%M %p').json"
3. Verify backup exists and is not empty
4. Get explicit user permission before making the change
5. ONLY THEN edit the config
If backup fails, STOP. Do not make the edit. Fix the backup first.
Date format: Human-readable only (February 28 at 3-00 PM). Never ISO or robot dates.
Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/02-back-yourself-up-protocol/back-yourself-up-protocol-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add under config management:

```
## Backup Protocol [PRIORITY: CRITICAL]
- Config file: ~/.openclaw/openclaw.json (NOT clawdbot.json)
- Backup command: cp ~/.openclaw/openclaw.json "[BACKUP_FOLDER]/models-backup-$(date +'%B %-d at %-I-%M %p').json"
- Date format: Human-readable. Example: models-backup-February 28 at 3-00 PM.json
- Date bash: date +'%B %-d at %-I-%M %p'
- Rule: Every config edit gets a backup. No exceptions. Backup fails = STOP.
- Full instance backup: Cron every 2 weeks (1st and 15th). Backs up config, .md files, memory, secrets, skills.
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/02-back-yourself-up-protocol/back-yourself-up-protocol-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add as permanent entry:

```
## Backup Protocol - Installed [DATE]
- CRITICAL safety protocol. Every config edit requires backup + user permission first.
- Config file: ~/.openclaw/openclaw.json
- Backup folder: [BACKUP_FOLDER]
- Date format: date +'%B %-d at %-I-%M %p' (human-readable, no robot dates)
- Full instance backup: cron every 2 weeks
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/02-back-yourself-up-protocol/back-yourself-up-protocol-full.md
```

---

## IDENTITY.md - UPDATE REQUIRED

Add under core principles:

```
## Backup Discipline
I ALWAYS back up ~/.openclaw/openclaw.json before editing it. Human-readable dates
on all filenames. User permission before config changes. Backup fails = I stop.
```

---

## HEARTBEAT.md - UPDATE REQUIRED

Add under routine tasks:

```
## Full Instance Backup - Automated
- Cron: 1st and 15th of month at 3:00 AM
- Backs up: config, workspace .md files, memory logs, secrets, installed skills, cron list
- Keeps only last 2 full backups
- If cron fails, fix immediately
```

---

## USER.md - NO UPDATE NEEDED
Backup protocol does not change anything about the user.

## SOUL.md - NO UPDATE NEEDED
Backup protocol does not change personality or tone.
