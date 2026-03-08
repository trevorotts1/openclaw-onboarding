# Back Yourself Up Protocol (BYUP)

## What This Skill Is About

The Back Yourself Up Protocol is a mandatory safety procedure that protects the
OpenClaw system from two types of disaster: config file corruption (small but common)
and total system loss (rare but catastrophic). It has two parts that work together.

**Part 1 - Config Backup:** Every single time the agent needs to edit the OpenClaw
config file (~/.openclaw/openclaw.json), it must create a backup first and get the
user's permission before making any change. No exceptions, no matter how small the
edit seems.

**Part 2 - Full Instance Backup:** Every two weeks, an automated backup captures the
entire OpenClaw installation - workspace files, configs, secrets, memory, scripts,
skills, and cron jobs - so that if the worst happens, everything can be restored.

## Why This Exists

On February 21, 2026, an agent backed up the wrong file (clawdbot.json instead of
openclaw.json). When the config got corrupted during an edit, there was no valid
backup to restore from. The user had to manually fix the gateway from the terminal
for over an hour. This protocol makes sure that never happens again.

## When This Skill Triggers

**Part 1 triggers** any time the agent is about to edit ~/.openclaw/openclaw.json.
Adding a model, removing a model, changing a temperature, updating an API key,
fixing a typo - every edit, every time.

**Part 2 triggers** automatically via a cron job every two weeks (every other Sunday
at 3:00 AM). The user can also request a manual full backup at any time.

**The one rule that overrides everything:** If the backup fails, STOP. Do not make
the edit. Do not proceed. Fix the backup first.

## What It Covers

- **Config Backup Step-by-Step** - the exact 9-step sequence: announce intent, find
  or create the backup folder, copy the config, verify the backup is not empty, ask
  for permission, make the edit, validate the JSON, restart the gateway, confirm
- **Backup Folder Detection** - smart search for existing backup folders in
  ~/Downloads/ using case-insensitive matching (users may have named the folder
  differently)
- **Human-Readable File Naming** - backup files use names like
  "models-backup-February 23 at 11-00 AM.txt" instead of robot dates
- **Permission Requirement** - the agent must ask for explicit user approval before
  every config edit, every single time
- **Post-Edit Verification** - JSON validation, gateway restart, and functional check
- **Full Instance Backup Contents** - what to include (workspace files, configs,
  secrets, memory, scripts, skills, cron jobs, projects, small assets) and what to
  exclude (node_modules, .git, caches, videos, large files)
- **Version Rotation** - only the last 2 full backups are kept to prevent storage bloat
- **Restoration Procedures** - step-by-step instructions for restoring a single config
  file or an entire OpenClaw installation from scratch
- **Backup Integrity Checks** - verifying backups contain valid content, not just that
  they exist
- **Error Handling** - what to do when common backup problems occur
- **Cross-File Documentation** - the backup rules must be documented in AGENTS.md,
  TOOLS.md, MEMORY.md, and IDENTITY.md so no agent session misses them
- **Common Mistakes** - 10 real mistakes agents make and how to avoid them

## Files in This Folder

Read them in this order:

1. **SKILL.md** (this file) - overview and orientation
2. **back-yourself-up-protocol-full.md** - the complete protocol with all sections,
   decision trees, shell commands, checklists, examples, and FAQs. This is the
   authoritative reference.
3. **INSTRUCTIONS.md** - step-by-step execution guide
4. **INSTALL.md** - how to install BYUP into a new agent's workspace
5. **EXAMPLES.md** - worked examples showing the protocol in action
6. **CORE_UPDATES.md** - the lightweight summaries to add to each core workspace file
7. **back-yourself-up-protocol.skill** - the skill definition file

## Prerequisites

The Teach Yourself Protocol (skill 01) must be installed first. BYUP uses TYP's
storage structure and file organization rules when installing itself into the agent's
workspace. If TYP is not installed, the agent will not know how to properly store and
reference this protocol.

## Key Things the Agent Needs to Know

1. **The config file path is always ~/.openclaw/openclaw.json.** Not clawdbot.json.
   Not any other file. Verify the path character by character before copying.

2. **Backup before every edit means every edit.** "It is just a small change" is not
   an excuse. The backup takes less than one second. Recovering from corruption takes
   hours.

3. **Permission is required every time.** Even if the user just asked for the change
   two messages ago, confirm right before making the edit. "Maybe" is not permission.
   Silence is not permission. Only a clear "yes" or equivalent counts.

4. **Surgical edits only.** When given permission to change one thing, change only
   that thing. Do not reformat, reorder, or "clean up" anything else in the file.

5. **The backup folder lives in ~/Downloads/.** Search for it using smart detection
   (case-insensitive, checks multiple naming patterns). If nothing exists, create
   ~/Downloads/openclaw-backups/ as the default.

6. **Human-readable dates on all backup filenames.** Use the format
   "models-backup-February 23 at 11-00 AM.txt". Generate with:
   date +'%B %-d at %-I-%M %p'

7. **Full backups keep only the last 2 versions.** When creating a third, delete the
   oldest. This prevents the backup folder from growing out of control.

8. **Document the rules in all four core files.** AGENTS.md, TOOLS.md, MEMORY.md, and
   IDENTITY.md must all contain the backup rules. If it only exists in one file, an
   agent in a future session might miss it entirely.

9. **If any backup step fails, everything stops.** No backup means no edit. Period.
   Diagnose the failure, fix it, get a valid backup, and only then continue.
