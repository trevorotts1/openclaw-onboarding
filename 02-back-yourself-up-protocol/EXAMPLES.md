# Back Yourself Up Protocol - Examples

## Example 1: Adding a Model to Config

**User says:** "Add Gemini 3 Flash to my models."

**Agent:**
1. Finds backup folder in ~/Downloads/
2. Runs: `cp ~/.openclaw/openclaw.json "[BACKUP_FOLDER]/models-backup-March 1 at 3-15 PM.json"`
3. Verifies file exists and is not empty
4. Says: "Backed up config. I need to add Gemini 3 Flash. Permission to proceed?"
5. Waits for approval, then makes the edit

## Example 2: Backup Fails

**Agent tries to back up but gets a disk full error.**

**Agent:**
1. STOPS immediately
2. Says: "Backup failed: disk full. I will NOT edit the config until I can create a valid backup. Can you free up disk space?"
3. Does NOT proceed with the config change

**Never:** "Backup failed but I will make the edit anyway"

## Example 3: Tiny Change (Still Requires Backup)

**Agent notices a model name typo in config.**

**Agent:**
1. Even for a single character fix, backs up first
2. Creates backup with human-readable date
3. Verifies backup
4. Asks permission: "Found a typo in config. Backed up. Permission to fix?"
5. Waits, then fixes

**The size of the change does not matter. Every edit gets a backup.**

## Example 4: Full Instance Backup

**User says:** "Back yourself up."

**Agent:**
1. Creates folder: `[BACKUP_FOLDER]/full-backup-March 1 at 4-00 PM/`
2. Copies: config, all workspace .md files, memory/*.md, secrets, skills, cron list
3. Verifies file counts
4. Checks for old full backups beyond the most recent 2, deletes them
5. Reports: "Full backup complete. [X] files saved to [path]. Kept last 2 backups."

## Example 5: Wrong File (What NOT to Do)

**WRONG:**
```bash
cp ~/.clawdbot/clawdbot.json ~/Downloads/backup.json
```

**Why wrong:** Wrong file (clawdbot.json), wrong path (~/.clawdbot/), no date in filename.
If the real config gets corrupted, this backup is useless.

**RIGHT:**
```bash
cp ~/.openclaw/openclaw.json "[BACKUP_FOLDER]/models-backup-$(date +'%B %-d at %-I-%M %p').json"
```

This exact mistake happened February 21, 2026. That is why this protocol exists.
