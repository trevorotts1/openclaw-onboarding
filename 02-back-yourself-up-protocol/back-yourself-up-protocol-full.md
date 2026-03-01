
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.
   Example: ~/Downloads/OpenClaw Master Files/kie-ai-reference.md

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE TREVOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask Trevor first. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════
Back Yourself Up Protocol
OpenClaw Standard Operating Procedure (SOP)
Version: 1.0
Created: February 23, 2026
Status: Active - Mandatory for all OpenClaw agents
Classification: Core Safety Protocol

Table of Contents
Purpose and Overview
Why This Protocol Exists
Part 1 - Config Backup (Before Every Edit)
When This Applies
Step-by-Step Procedure
Backup Folder Detection
File Naming Convention
Permission Requirement
Post-Edit Verification
Decision Tree - Config Edit
Config Backup Checklist
Cross-File Documentation Requirement
Part 2 - Full Instance Backup
What This Covers
Backup Contents - What to Include
Exclusion List - What NOT to Back Up
Folder Structure
Version Rotation Policy
Automated Schedule
Full Backup Step-by-Step Procedure
Decision Tree - Full Backup
Full Backup Checklist
Restoration Procedures
Restoring a Config File
Restoring a Full Instance
Error Handling
Examples
Frequently Asked Questions

Purpose and Overview
The Back Yourself Up Protocol is a mandatory safety procedure for all OpenClaw agents. It has two distinct parts that serve two different purposes:
Part 1 - Config Backup protects against configuration corruption. Every single time an agent needs to edit the OpenClaw config file (~/.openclaw/openclaw.json), the agent MUST create a human-readable backup first, and MUST get explicit user permission before making any change. No exceptions. No shortcuts. No "it's just a small change." Every edit, every time.
Part 2 - Full Instance Backup protects against catastrophic failure. Once every two weeks, the agent creates a complete backup of the entire OpenClaw installation - every file, every config, every secret, every memory log - so that if the worst happens, everything can be restored from scratch. This runs automatically and keeps only the last two versions to prevent storage bloat.
Together, these two parts ensure that no config edit can permanently break the system, and no catastrophic event can permanently destroy the installation.

Why This Protocol Exists
This protocol exists because of a real incident that happened on February 21, 2026.
What happened: An agent was asked to make changes to the OpenClaw config. The agent backed up the WRONG file (it backed up clawdbot.json instead of openclaw.json). The config got corrupted during the edit. When it was time to restore, there was no valid backup. The user had to manually fix the gateway from the terminal for over an hour.
What went wrong: 
The agent did not verify it was backing up the correct file
The agent did not verify the backup was valid before proceeding
The agent did not have a standardized backup procedure to follow
There was no full-system backup to fall back on
What this protocol prevents: 
Backing up the wrong file (the procedure specifies the exact path)
Proceeding without a valid backup (verification is a mandatory step)
Making unauthorized changes (user permission is required every time)
Total data loss from catastrophic failure (full instance backups exist)
This is not theoretical. This happened. This protocol makes sure it never happens again.

Part 1 - Config Backup (Before Every Edit)
When This Applies
This procedure applies EVERY TIME an agent needs to edit the file at this exact path:
~/.openclaw/openclaw.json
This is the OpenClaw models configuration file. It controls which models are available, their API keys, temperature settings, routing rules, and other critical gateway configuration.
Examples of edits that trigger this procedure: 
Adding a new model
Removing a model
Changing a model's temperature setting
Updating an API key
Fixing a typo in a model name
Changing any parameter, no matter how small
Any modification of any kind to this file
There are ZERO exceptions. If the edit seems tiny, back up first. If you are "just fixing a typo," back up first. If the user says "just quickly change this," back up first. The backup takes seconds. Recovering from a corrupted config takes hours.
Step-by-Step Procedure
Here is the exact sequence of steps an agent must follow when it needs to edit ~/.openclaw/openclaw.json. Every step is mandatory. No steps can be skipped.
Step 1: Announce the Intent
Before doing anything, tell the user what you intend to change and why. Be specific.
Example:
> "I need to update the OpenClaw config to add the new Gemini 3.1 Pro model. Before I touch anything, I am going to create a backup of the current config file."
Step 2: Locate or Create the Backup Folder
Check for existing backup folders in ~/Downloads/. Different users may have named their backup folder differently. The agent must search for any folder that serves as the OpenClaw backup location.
Common folder name variations to check for: 
openclaw-backups
openclaw-backup
openclaw backups (with space)
openclaw backup (with space, singular)
OpenClaw Backups (capitalized)
OpenClaw Backup (capitalized, singular)
open-claw-backups
open claw backups (two words)
backups
backup
How to search: List folders in ~/Downloads/ and look for any folder name containing keywords like "openclaw," "open claw," "backup," or "backups" in any combination. Match case-insensitively. If you find a folder that clearly serves as the backup location (contains .txt backup files or a full-backup subfolder), use that folder. Do not create a duplicate.
Decision logic: 
Search ~/Downloads/ for any folder matching the variations above or similar patterns
If a matching folder is found, use it
If MULTIPLE matching folders exist, prefer the most specific one (the one with "openclaw" in the name)
If NO matching folder is found, create ~/Downloads/openclaw-backups/ (this is the standard default)
See the Backup Folder Detection section below for the detailed decision logic and shell commands.
Step 3: Create the Backup File
Copy the config file to the backup folder as a plain readable text file (.txt extension, not .json). The file name must follow the human-readable naming convention described in File Naming Convention.
cp ~/.openclaw/openclaw.json ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt
The .txt extension is deliberate. It ensures any human can open and read the file on any system without needing a JSON viewer. The contents are still valid JSON - it is just saved with a .txt extension for accessibility.
Step 4: Verify the Backup
This step is NOT optional. After creating the backup, the agent must verify:
The backup file exists at the expected path
The backup file is NOT empty (has a file size greater than zero)
The backup file contains valid content (spot-check a few lines)
# Check that the file exists and is not empty
ls -la ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt

# Verify it has content (should show line count greater than zero)
wc -l ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt

# Spot-check the first few lines to confirm it is the right file
head -5 ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt
If the backup is empty or missing: STOP. Do not proceed. Do not edit the config. Diagnose why the backup failed and fix it before continuing.
Step 5: Ask for Permission
After the backup is confirmed, ask the user for explicit permission to make the edit. This is mandatory every single time, no exceptions. Even if the user already said "go ahead" in a previous message, ask again right before the edit. Even if the change seems obvious or trivial, ask.
Example:
> "Backup created successfully at ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt. I am ready to add the Gemini 3.1 Pro model to the config. Here is exactly what I will change: [describe the specific change]. Do I have your permission to proceed?"
Wait for an affirmative response. Do not interpret silence as permission. Do not interpret "maybe" as permission. The user must clearly say yes, approved, go ahead, do it, or an equivalent affirmative.
Step 6: Make the Edit
Only after BOTH conditions are met (backup verified AND permission granted), make the edit to ~/.openclaw/openclaw.json.
Be surgical. Change only what was discussed. Do not "clean up" other things while you are in there. Do not reformat the file. Do not reorder keys. Change exactly what was approved and nothing else.
Step 7: Verify the Edit
After editing, verify the config file is valid:
# Check that the file is valid JSON
cat ~/.openclaw/openclaw.json | python3 -m json.tool > /dev/null 2>&1 && echo "Valid JSON" || echo "INVALID JSON - RESTORE FROM BACKUP"
If the JSON is invalid, immediately restore from the backup you just created:
cp ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt ~/.openclaw/openclaw.json
Then diagnose what went wrong and try again.
Step 8: Restart the Gateway
After a successful edit, restart the OpenClaw gateway to apply the changes:
openclaw gateway restart
This confirms the new configuration takes effect. Watch the output for any errors. If the gateway fails to restart, the config change may have introduced an issue - restore from backup and investigate.
Step 9: Confirm to the User
Tell the user what happened:
> "Config updated successfully. Gateway restarted and running. The backup is saved at ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt in case you ever need to roll back."
Backup Folder Detection
The agent must search ~/Downloads/ for any existing folder that serves as the OpenClaw backup location. Different users may have named this folder differently - some use hyphens, some use spaces, some capitalize, some use singular "backup" vs plural "backups."
Decision logic: 
START
  |
  v
Search ~/Downloads/ for folders matching backup-related names
(case-insensitive search for folders containing "openclaw" + "backup" 
or just "backup/backups")
  |
  v
Found a folder with "openclaw" in the name? (e.g., "openclaw-backups", 
"OpenClaw Backup", "openclaw backups", etc.)
  |
  YES --> Use that folder (prefer the most specific match)
  |
  NO --> Found a generic "backups" or "backup" folder?
           |
           YES --> Use that folder
           |
           NO --> Create ~/Downloads/openclaw-backups/
                  Use ~/Downloads/openclaw-backups/
Shell commands for the smart detection: 
# Smart backup folder detection - checks for multiple naming variations
BACKUP_DIR=""

# First, look for any folder with "openclaw" AND "backup" in the name (case-insensitive)
FOUND=$(find "$HOME/Downloads" -maxdepth 1 -type d -iname "*openclaw*backup*" 2>/dev/null | head -1)

if [ -n "$FOUND" ]; then
    BACKUP_DIR="$FOUND"
# Next, check for a generic "backups" or "backup" folder
elif [ -d "$HOME/Downloads/backups" ]; then
    BACKUP_DIR="$HOME/Downloads/backups"
elif [ -d "$HOME/Downloads/backup" ]; then
    BACKUP_DIR="$HOME/Downloads/backup"
else
    # Nothing found - create the standard default
    mkdir -p "$HOME/Downloads/openclaw-backups"
    BACKUP_DIR="$HOME/Downloads/openclaw-backups"
fi

echo "Using backup directory: $BACKUP_DIR"
Why smart detection matters: When OpenClaw is set up for different users, some may have already created a backup folder with a slightly different name. The agent should find and use whatever exists rather than creating a duplicate folder. This prevents confusion and scattered backups.
File Naming Convention
Backup files must be named in a format that a human can read and understand at a glance. The format is:
models-backup-<Full Month> <Day> at <Hour>-<Minutes> <AM/PM>.txt
Rules: 
Month is abbreviated to three letters with the first letter capitalized (Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec)
Day is the numeric day of the month with no leading zero (1, 2, 3, ... 31)
Format: Full month name, day number, 'at', hour-minutes (no leading zeros), AM/PM uppercase. Use hyphens instead of colons for minutes. Example: February 23 at 11-00 AM
am/pm is lowercase
The entire filename uses hyphens as separators, never underscores or spaces
Extension is always .txt
Examples: 
Date and Time  |  Filename
February 23, 2026 at 11:00 AM  |  models-backup-February 23 at 11-00 AM.txt
March 5, 2026 at 2:00 PM  |  models-backup-March 5 at 2-00 PM.txt
January 15, 2026 at 9:00 AM  |  models-backup-January 15 at 9-00 AM.txt
December 1, 2026 at 12:00 PM  |  models-backup-December 1 at 12-00 PM.txt
July 30, 2026 at 6:00 PM  |  models-backup-July 30 at 6-00 PM.txt
October 8, 2026 at 7:00 AM  |  models-backup-October 8 at 7-00 AM.txt

Always include minutes using hyphens instead of colons (9-00 not 9:00). Use full month name spelled out (February not Feb). Use uppercase AM/PM. No leading zeros on hours or days. The purpose of this naming convention is quick human recognition, not precision timestamps. If two backups happen in the same hour (which should be rare), append a number: models-backup-Feb23-11am-2.txt.
Generating the filename in shell: 
# Generate a human-readable backup filename
BACKUP_NAME="models-backup-$(date +'%B %-d at %-I-%M %p').txt"
# Example output: models-backup-February 23 at 11-00 AM.txt
Note: The %-d and %-I format specifiers remove leading zeros. The %P gives lowercase am/pm. The %b gives the abbreviated month name.
Permission Requirement
This cannot be overstated: the agent MUST ask the user for permission before every config edit. Every. Single. Time.
Why every time?
The user needs to know what is about to change
The user needs the opportunity to say "wait, not right now" or "actually, change this instead"
The user is the owner of the system - the agent is the administrator, not the decision-maker
If something goes wrong, the user should never be surprised by a change they did not approve
What counts as permission: 
"Yes"
"Go ahead"
"Do it"
"Approved"
"Sounds good, proceed"
Any clear affirmative statement
What does NOT count as permission: 
Silence (no response)
"Maybe" or "I guess"
"Let me think about it"
A previous "yes" from a different conversation or session
The user asking "what would happen if you changed X?" (that is a question, not permission)
The user saying "I want to add model X eventually" (that is a wish, not an instruction)
If the user says no: Stop. Do not make the edit. Acknowledge their decision and move on. The backup you already created can stay in the folder - it does no harm.
Post-Edit Verification
After every config edit, the agent must perform these verification steps:
JSON Validation - Confirm the edited file is still valid JSON
Gateway Restart - Run openclaw gateway restart and confirm it succeeds
Functional Check - If possible, verify the change works (for example, if a model was added, confirm it appears in the available models list)
User Notification - Tell the user the edit is complete, the gateway restarted successfully, and where the backup is located
If any verification step fails, immediately restore from the backup and notify the user.
Decision Tree - Config Edit
This is the complete decision tree an agent must follow when a config edit is needed:
USER REQUESTS OR TASK REQUIRES A CONFIG CHANGE
  |
  v
Step 1: Announce what you intend to change
  |
  v
Step 2: Check for backup folder
  |
  +-- ~/Downloads/openclaw-backups/ exists? --> Use it
  |
  +-- ~/Downloads/backups/ exists? --> Use it
  |
  +-- Neither exists? --> Create ~/Downloads/openclaw-backups/
  |
  v
Step 3: Copy ~/.openclaw/openclaw.json to backup folder
         Use human-readable filename (models-backup-MonDD-HHampm.txt)
  |
  v
Step 4: Verify backup
  |
  +-- Backup file exists and is not empty? --> Continue
  |
  +-- Backup is missing or empty? --> STOP. Fix the backup. Do NOT proceed.
  |
  v
Step 5: Ask user for explicit permission
  |
  +-- User says yes? --> Continue
  |
  +-- User says no or does not respond? --> STOP. Do not edit.
  |
  v
Step 6: Make the edit (surgical - only what was approved)
  |
  v
Step 7: Validate the JSON
  |
  +-- Valid JSON? --> Continue
  |
  +-- Invalid JSON? --> RESTORE from backup immediately. Try again.
  |
  v
Step 8: Run "openclaw gateway restart"
  |
  +-- Gateway restarts successfully? --> Continue
  |
  +-- Gateway fails? --> RESTORE from backup. Investigate the error.
  |
  v
Step 9: Confirm to user (what changed, gateway status, backup location)
  |
  v
DONE
Config Backup Checklist
Use this checklist every time. No skipping steps.
[ ] Announced intent to user (what will change and why)
[ ] Checked for existing backup folder (openclaw-backups or backups in ~/Downloads/)
[ ] Backup folder exists or was created
[ ] Copied ~/.openclaw/openclaw.json to backup folder with human-readable filename
[ ] Verified backup file exists
[ ] Verified backup file is not empty
[ ] Verified backup file contains the right content (spot-checked first few lines)
[ ] Asked user for explicit permission to edit
[ ] Received clear affirmative response from user
[ ] Made the edit (only the approved change, nothing else)
[ ] Validated the edited file is still valid JSON
[ ] Ran openclaw gateway restart
[ ] Confirmed gateway restarted successfully
[ ] Notified user of completion and backup location
Cross-File Documentation Requirement
The config backup rules must be documented in ALL FOUR of the following workspace files:
IDENTITY.md - Under the agent's core principles or safety rules section. The agent must know that config backup is part of its identity and non-negotiable behavior.
AGENTS.md - Under the behavioral rules section. This is where operational rules live, and config backup is a core operational rule.
MEMORY.md - As a permanent lesson learned. The February 21, 2026 incident should be referenced, and the backup protocol should be noted as the permanent fix.
TOOLS.md - Under the tools and configuration section. Since the config file is a tool-adjacent resource, the backup procedure belongs here with specific commands and paths.
Why all four files? Because agents do not have persistent memory between sessions. They read these files at startup to know who they are and how to behave. If the backup rule only exists in one file, an agent might miss it depending on which files it reads. Putting it in all four files ensures the rule is encountered no matter what.
What to add to each file (minimum): 
For IDENTITY.md:
> "Before editing ~/.openclaw/openclaw.json, I ALWAYS create a backup first. I check for ~/Downloads/openclaw-backups/ or ~/Downloads/backups/, create the backup as a human-readable .txt file, verify it is not empty, ask the user for permission, and only then make the edit. After editing, I run openclaw gateway restart. This is non-negotiable."
For AGENTS.md:
> "BACKUP BEFORE EVERY CONFIG EDIT - NON-NEGOTIABLE. Before ANY edit to ~/.openclaw/openclaw.json: (1) check for backup folder in ~/Downloads/, (2) create backup with human-readable filename, (3) verify backup is not empty, (4) ask user for permission, (5) make the edit, (6) validate JSON, (7) run openclaw gateway restart. If backup fails, STOP. Do not edit."
For MEMORY.md:
> "Config Backup Protocol established February 23, 2026. After the February 21 incident where the wrong file was backed up and the config was corrupted, the Back Yourself Up Protocol is now mandatory. Full procedure documented in projects/back-yourself-up-protocol/BACK-YOURSELF-UP-PROTOCOL.md."
For TOOLS.md:
> "CONFIG BACKUP - MANDATORY BEFORE EVERY EDIT. Config file path: ~/.openclaw/openclaw.json. Backup folder: ~/Downloads/openclaw-backups/ (or ~/Downloads/backups/ if that exists). Backup command: cp ~/.openclaw/openclaw.json ~/Downloads/openclaw-backups/models-backup-$(date +'%B %-d at %-I-%M %p').txt. Verify backup is not empty. Ask permission. Edit. Validate JSON. Run openclaw gateway restart."

Part 2 - Full Instance Backup
What This Covers
A Full Instance Backup captures everything needed to restore an OpenClaw installation from scratch. If the machine dies, the disk corrupts, or something catastrophic happens, this backup folder contains everything needed to rebuild.
This is NOT about backing up one config file. This is about backing up the entire OpenClaw ecosystem - workspace files, configs, secrets, memories, skills, scripts, schedules, and anything else the agent depends on to function.
The goal: Someone with zero context should be able to take this backup folder and restore a fully functional OpenClaw agent on a fresh machine.
Backup Contents - What to Include
Here is the complete list of what a Full Instance Backup must contain, organized by category:
Category 1: Workspace Markdown Files
These are the files that define who the agent is, how it behaves, and what it knows. They live in the workspace directory (the clawd folder or wherever the agent's home is).
File  |  Purpose
AGENTS.md  |  Behavioral rules, golden rules, operational procedures
TOOLS.md  |  Tool usage notes, credentials locations, API patterns
MEMORY.md  |  Persistent memory, lessons learned, permanent context
IDENTITY.md  |  Who the agent is, personality, core principles
USER.md  |  Information about the user the agent serves
SOUL.md  |  The agent's foundational identity document
HEARTBEAT.md  |  Daily routine, scheduled tasks, heartbeat configuration

If additional .md files exist in the workspace root (such as THINKING.md, BOOTSTRAP.md, or any custom files), include those too. The rule is: any .md file in the workspace root gets backed up.
Category 2: Configuration Files
File/Path  |  Purpose
~/.openclaw/openclaw.json  |  The main OpenClaw gateway config (models, keys, routing)
~/.openclaw/ (entire directory)  |  Any additional OpenClaw config files that may exist
~/.clawdbot/clawdbot.json  |  Legacy config file (if it exists)

If other config files exist in the OpenClaw directory, include them. When in doubt, include it.
Category 3: Secrets and Credentials
File/Path  |  Purpose
~/clawd/secrets/.env  |  API keys, tokens, passwords
~/clawd/secrets/ (entire directory)  |  Service account JSON files, certificate files, any credential files
GCP service account files  |  Google Cloud Platform service account key files (wherever they are stored)

IMPORTANT SECURITY NOTE: The full backup folder will contain sensitive credentials. It should be stored locally only. Do not upload it to cloud storage, do not commit it to git, do not share it. If the backup needs to be moved to external storage, encrypt it first.
Category 4: Scripts and Tools
File/Path  |  Purpose
~/clawd/bin/  |  Custom scripts and tools (cliclick, custom utilities)
~/clawd/scripts/  |  Automation scripts
~/clawd/tools/  |  Tool configurations or custom tool files

Category 5: Memory Files
File/Path  |  Purpose
~/clawd/memory/  |  Daily memory logs (YYYY-MM-DD.md files)
~/clawd/memory/master-files/  |  Master reference documents
~/Downloads/openclaw-master-files/  |  Master files folder (if it exists)

Category 6: Installed Skills
OpenClaw skills are extensions that add capabilities. Back up any installed skill configurations or custom skill files. The exact location depends on the OpenClaw version, but check:
File/Path  |  Purpose
~/.openclaw/skills/  |  Installed skills directory (if it exists)
Skills config within openclaw.json  |  Skill definitions within the main config

Category 7: Cron Jobs and Schedules
Item  |  Purpose
OpenClaw cron job definitions  |  Scheduled tasks (daily briefings, automated reports, etc.)
Cron job IDs and descriptions  |  So they can be recreated if needed

To capture cron jobs, the agent should export the current cron schedule to a text file as part of the backup:
# Export OpenClaw cron jobs to a file
openclaw cron list > full-backup/cron-jobs-export.txt 2>&1
If the openclaw cron list command is not available, document the known cron jobs manually in a cron-jobs.txt file within the backup, including their IDs, schedules, and descriptions.
Category 8: Project Files
File/Path  |  Purpose
~/clawd/projects/  |  Project directories (protocols, templates, etc.)
~/clawd/data/  |  Data files (contact lists, user databases, etc.)
~/clawd/assets/  |  Brand assets, logos, headshots (small image files only - see exclusions below)

Exclusion List - What NOT to Back Up
The following items must be EXCLUDED from Full Instance Backups to prevent bloat:
Exclude  |  Reason
node_modules/  |  Package dependencies - can be reinstalled with npm install
.git/  |  Git history - can be re-cloned from remote
__pycache__/  |  Python bytecode cache - regenerated automatically
.cache/ or any cache/ directories  |  Temporary cached data - regenerated automatically
tmp/ or temp/ directories  |  Temporary files - not needed for restoration
Large image files (over 5 megabytes each)  |  Can be re-downloaded or regenerated
Video files (.mp4, .mov, .avi, .mkv, .webm)  |  Too large, not needed for restoration
Audio files (.mp3, .wav, .aac, .flac)  |  Too large, not needed for restoration
.DS_Store files  |  macOS metadata - not needed
Log files (.log)  |  Historical logs - not needed for restoration
Downloaded media in chat history  |  Can be re-downloaded if needed
Backup files themselves  |  Do not back up the backup folder recursively
Any single file over 10 megabytes  |  Flag it and skip it to prevent bloat

The principle: If it can be reinstalled, re-downloaded, or regenerated, do not back it up. Back up things that are unique, custom, or would be lost forever without a backup.
Folder Structure
The full backup lives inside the same backup folder used for config backups, in a subfolder called full-backup:
~/Downloads/openclaw-backups/
    |
    +-- models-backup-February 23 at 11-00 AM.txt        (config backup)
    +-- models-backup-Feb21-3pm.txt         (config backup)
    +-- models-backup-Feb19-9am.txt         (config backup)
    |
    +-- full-backup/
         |
         +-- full-backup-2026-02-23/        (most recent full backup)
         |    |
         |    +-- workspace/
         |    |    +-- AGENTS.md
         |    |    +-- TOOLS.md
         |    |    +-- MEMORY.md
         |    |    +-- IDENTITY.md
         |    |    +-- USER.md
         |    |    +-- SOUL.md
         |    |    +-- HEARTBEAT.md
         |    |    +-- (any other .md files)
         |    |
         |    +-- config/
         |    |    +-- openclaw.json
         |    |    +-- (other config files)
         |    |
         |    +-- secrets/
         |    |    +-- .env
         |    |    +-- (service account files)
         |    |
         |    +-- memory/
         |    |    +-- (daily log files)
         |    |    +-- master-files/
         |    |
         |    +-- scripts/
         |    |    +-- (custom scripts)
         |    |
         |    +-- skills/
         |    |    +-- (skill files)
         |    |
         |    +-- cron-jobs-export.txt
         |    +-- projects/
         |    |    +-- (project files, excluding bloat)
         |    |
         |    +-- data/
         |    |    +-- (data files)
         |    |
         |    +-- assets/
         |    |    +-- (small brand assets only)
         |    |
         |    +-- MANIFEST.txt             (list of everything in this backup)
         |    +-- BACKUP-INFO.txt          (date, time, agent version, notes)
         |
         +-- full-backup-2026-02-09/        (previous full backup)
              |
              +-- (same structure as above)
Version Rotation Policy
To prevent the backup folder from growing indefinitely, the Full Instance Backup follows a strict version rotation policy:
Keep only the LAST 2 full backup versions at any time.
When a new (third) full backup is created:
Identify the oldest full backup directory
Delete the oldest full backup directory completely
The two remaining directories are now the previous backup and the new backup
Example: 
Before the third backup:
full-backup/
    full-backup-2026-01-12/    (oldest - will be deleted)
    full-backup-2026-01-26/    (previous)
After the third backup:
full-backup/
    full-backup-2026-01-26/    (now the older of the two)
    full-backup-2026-02-09/    (newest)
How to determine which is oldest: Sort the directories by name. Since they are named with dates in YYYY-MM-DD format, alphabetical sorting equals chronological sorting. The first one alphabetically is the oldest.
Shell command for rotation: 
BACKUP_BASE="$HOME/Downloads/openclaw-backups/full-backup"

# Count existing backup directories
BACKUP_COUNT=$(ls -d "$BACKUP_BASE"/full-backup-* 2>/dev/null | wc -l | tr -d ' ')

# If there are already 2 or more, delete the oldest
if [ "$BACKUP_COUNT" -ge 2 ]; then
    OLDEST=$(ls -d "$BACKUP_BASE"/full-backup-* | head -1)
    echo "Rotating backups: deleting oldest backup at $OLDEST"
    rm -rf "$OLDEST"
fi
Automated Schedule
The Full Instance Backup runs automatically once every two weeks (biweekly).
Schedule: Every other Sunday at 3:00 AM Eastern Standard Time (EST)
Why 3:00 AM? The user is almost certainly asleep. The backup process involves reading many files and creating copies, which could cause minor system load. Running it during off-hours ensures zero disruption.
Why every two weeks? This balances safety against storage use. Weekly backups would accumulate too much data too quickly. Monthly backups would risk losing too much work if something fails. Biweekly is the sweet spot.
Implementation: This should be set up as an OpenClaw cron job. The agent should create or verify this cron job exists during its first session after this protocol is adopted.
# Example cron schedule (syntax depends on OpenClaw cron implementation)
# Runs every other Sunday at 3:00 AM EST
# The agent should set this up using openclaw's cron system
If the automated backup fails: The agent should detect the failure on the next session and:
Notify the user that the automated backup failed
Run the backup manually
Investigate why the automation failed and fix it
Full Backup Step-by-Step Procedure
Step 1: Determine the Backup Directory
Use the same backup folder detection logic as Part 1. Then ensure the full-backup subfolder exists:
# Smart backup folder detection (same logic as Part 1)
BACKUP_ROOT=""
FOUND=$(find "$HOME/Downloads" -maxdepth 1 -type d -iname "*openclaw*backup*" 2>/dev/null | head -1)

if [ -n "$FOUND" ]; then
    BACKUP_ROOT="$FOUND"
elif [ -d "$HOME/Downloads/backups" ]; then
    BACKUP_ROOT="$HOME/Downloads/backups"
elif [ -d "$HOME/Downloads/backup" ]; then
    BACKUP_ROOT="$HOME/Downloads/backup"
else
    mkdir -p "$HOME/Downloads/openclaw-backups"
    BACKUP_ROOT="$HOME/Downloads/openclaw-backups"
fi

# Ensure full-backup subfolder exists - create if it does not
mkdir -p "$BACKUP_ROOT/full-backup"
Step 2: Rotate Old Backups
Before creating a new backup, check if rotation is needed:
FULL_BACKUP_DIR="$BACKUP_ROOT/full-backup"
BACKUP_COUNT=$(ls -d "$FULL_BACKUP_DIR"/full-backup-* 2>/dev/null | wc -l | tr -d ' ')

if [ "$BACKUP_COUNT" -ge 2 ]; then
    OLDEST=$(ls -d "$FULL_BACKUP_DIR"/full-backup-* 2>/dev/null | head -1)
    echo "Deleting oldest backup: $OLDEST"
    rm -rf "$OLDEST"
fi
Step 3: Create the New Backup Directory
TODAY=$(date +%Y-%m-%d)
NEW_BACKUP="$FULL_BACKUP_DIR/full-backup-$TODAY"
mkdir -p "$NEW_BACKUP"/{workspace,config,secrets,memory,scripts,skills,projects,data,assets}
Step 4: Copy Workspace Markdown Files
# Copy all .md files from the workspace root
cp ~/clawd/*.md "$NEW_BACKUP/workspace/" 2>/dev/null
Step 5: Copy Configuration Files
# Copy the main OpenClaw config
cp ~/.openclaw/openclaw.json "$NEW_BACKUP/config/" 2>/dev/null

# Copy any other files in the OpenClaw config directory
cp ~/.openclaw/*.json "$NEW_BACKUP/config/" 2>/dev/null
cp ~/.openclaw/*.yaml "$NEW_BACKUP/config/" 2>/dev/null
cp ~/.openclaw/*.yml "$NEW_BACKUP/config/" 2>/dev/null
cp ~/.openclaw/*.toml "$NEW_BACKUP/config/" 2>/dev/null

# Copy legacy config if it exists
cp ~/.clawdbot/clawdbot.json "$NEW_BACKUP/config/" 2>/dev/null
Step 6: Copy Secrets and Credentials
# Copy secrets directory
cp -r ~/clawd/secrets/ "$NEW_BACKUP/secrets/" 2>/dev/null

# Copy any service account files that live elsewhere
# (Adjust paths based on actual installation)
Step 7: Copy Memory Files
# Copy memory directory (daily logs and master files)
cp -r ~/clawd/memory/ "$NEW_BACKUP/memory/" 2>/dev/null

# Copy master files if they exist in Downloads
if [ -d "$HOME/Downloads/openclaw-master-files" ]; then
    cp -r "$HOME/Downloads/openclaw-master-files/" "$NEW_BACKUP/memory/openclaw-master-files/" 2>/dev/null
fi
Step 8: Copy Scripts and Tools
# Copy custom scripts and tools
cp -r ~/clawd/bin/ "$NEW_BACKUP/scripts/bin/" 2>/dev/null
cp -r ~/clawd/scripts/ "$NEW_BACKUP/scripts/scripts/" 2>/dev/null
cp -r ~/clawd/tools/ "$NEW_BACKUP/scripts/tools/" 2>/dev/null
Step 9: Copy Skills
# Copy installed skills
cp -r ~/.openclaw/skills/ "$NEW_BACKUP/skills/" 2>/dev/null
Step 10: Export Cron Jobs
# Export cron job definitions
openclaw cron list > "$NEW_BACKUP/cron-jobs-export.txt" 2>&1

# If the command fails, create a note
if [ $? -ne 0 ]; then
    echo "NOTE: openclaw cron list command failed. Cron jobs may need to be documented manually." > "$NEW_BACKUP/cron-jobs-export.txt"
fi
Step 11: Copy Project Files (Excluding Bloat)
# Copy projects, excluding node_modules, .git, caches, and large media
rsync -a \
    --exclude='node_modules/' \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='.cache/' \
    --exclude='cache/' \
    --exclude='tmp/' \
    --exclude='temp/' \
    --exclude='.DS_Store' \
    --exclude='*.mp4' \
    --exclude='*.mov' \
    --exclude='*.avi' \
    --exclude='*.mkv' \
    --exclude='*.webm' \
    --exclude='*.mp3' \
    --exclude='*.wav' \
    --exclude='*.aac' \
    --exclude='*.flac' \
    --exclude='*.log' \
    ~/clawd/projects/ "$NEW_BACKUP/projects/" 2>/dev/null
Step 12: Copy Data Files
# Copy data directory
cp -r ~/clawd/data/ "$NEW_BACKUP/data/" 2>/dev/null
Step 13: Copy Small Brand Assets
# Copy assets but skip files over 5MB
find ~/clawd/assets/ -type f -size -5M -exec cp --parents {} "$NEW_BACKUP/" \; 2>/dev/null

# Alternative approach if --parents is not available on macOS:
rsync -a --max-size=5M ~/clawd/assets/ "$NEW_BACKUP/assets/" 2>/dev/null
Step 14: Generate the Manifest
Create a file listing everything in the backup:
# Generate a manifest of all backed-up files
find "$NEW_BACKUP" -type f | sort > "$NEW_BACKUP/MANIFEST.txt"
Step 15: Generate Backup Info
Create a metadata file about this backup:
cat > "$NEW_BACKUP/BACKUP-INFO.txt" << EOF
Full Instance Backup
Date: $(date '+%A, %B %d, %Y')
Time: $(date '+%I:%M %p %Z')
Hostname: $(hostname)
User: $(whoami)
Backup Type: Full Instance (Automated Biweekly)
Protocol: Back Yourself Up Protocol v1.0

Files backed up: $(find "$NEW_BACKUP" -type f | wc -l | tr -d ' ')
Total size: $(du -sh "$NEW_BACKUP" | cut -f1)

Notes:
- This backup contains sensitive credentials. Store securely.
- Do not upload to cloud storage without encryption.
- To restore, follow the restoration procedure in BACK-YOURSELF-UP-PROTOCOL.md
EOF
Step 16: Verify the Backup
# Check that key files exist in the backup
MISSING=""

[ ! -f "$NEW_BACKUP/config/openclaw.json" ] && MISSING="$MISSING openclaw.json"
[ ! -f "$NEW_BACKUP/workspace/AGENTS.md" ] && MISSING="$MISSING AGENTS.md"
[ ! -f "$NEW_BACKUP/workspace/TOOLS.md" ] && MISSING="$MISSING TOOLS.md"

if [ -n "$MISSING" ]; then
    echo "WARNING: The following expected files are missing from the backup:$MISSING"
else
    echo "Backup verification passed. All critical files present."
fi

# Report total backup size
echo "Total backup size: $(du -sh "$NEW_BACKUP" | cut -f1)"
Decision Tree - Full Backup
FULL BACKUP TRIGGERED (biweekly cron or manual request)
  |
  v
Step 1: Determine backup root directory
  |
  +-- ~/Downloads/openclaw-backups/ exists? --> Use it
  +-- ~/Downloads/backups/ exists? --> Use it
  +-- Neither? --> Create ~/Downloads/openclaw-backups/
  |
  v
Step 2: Ensure full-backup/ subfolder exists
  |
  v
Step 3: Count existing full backups
  |
  +-- 2 or more exist? --> Delete the oldest one
  +-- Fewer than 2? --> Continue (no rotation needed)
  |
  v
Step 4: Create new backup directory (full-backup-YYYY-MM-DD/)
  |
  v
Step 5: Copy all items per the inclusion list
  |
  +-- Workspace .md files
  +-- Config files
  +-- Secrets and credentials
  +-- Memory files and daily logs
  +-- Scripts and tools
  +-- Installed skills
  +-- Cron job export
  +-- Project files (excluding bloat items)
  +-- Data files
  +-- Small brand assets (under 5 megabytes)
  |
  v
Step 6: Generate MANIFEST.txt (list of all files)
  |
  v
Step 7: Generate BACKUP-INFO.txt (metadata)
  |
  v
Step 8: Verify critical files are present
  |
  +-- All critical files present? --> Report success
  +-- Missing critical files? --> Warn and log which files are missing
  |
  v
Step 9: Report completion
  |
  +-- If automated: Log the result
  +-- If manual: Notify the user with size and file count
  |
  v
DONE
Full Backup Checklist
[ ] Backup root directory determined (openclaw-backups or backups in ~/Downloads/)
[ ] full-backup subfolder exists or was created
[ ] Old backup rotation performed if needed (max 2 versions)
[ ] New backup directory created with today's date
[ ] Workspace .md files copied
[ ] OpenClaw config files copied (~/.openclaw/)
[ ] Legacy config files copied (if they exist)
[ ] Secrets and credentials copied (~/clawd/secrets/)
[ ] Memory files copied (daily logs and master files)
[ ] Scripts and tools copied (~/clawd/bin/, ~/clawd/scripts/)
[ ] Installed skills copied
[ ] Cron jobs exported to text file
[ ] Project files copied (excluding node_modules, .git, caches, media)
[ ] Data files copied
[ ] Brand assets copied (files under 5 megabytes only)
[ ] MANIFEST.txt generated
[ ] BACKUP-INFO.txt generated
[ ] Verification passed (critical files present)
[ ] Total backup size is reasonable (not bloated)
[ ] Completion reported (to log or to user)

Restoration Procedures
Restoring a Config File
If the OpenClaw config gets corrupted or a change needs to be rolled back, here is how to restore from a Part 1 config backup:
Step 1: Find the backup you want to restore
# List all config backups, newest first
ls -lt ~/Downloads/openclaw-backups/models-backup-*.txt
Step 2: Preview the backup to confirm it is the right one
# Look at the first 20 lines to verify it is the version you want
head -20 ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt
Step 3: Copy the backup over the current config
cp ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt ~/.openclaw/openclaw.json
Step 4: Validate the restored config
cat ~/.openclaw/openclaw.json | python3 -m json.tool > /dev/null 2>&1 && echo "Valid JSON" || echo "INVALID JSON"
Step 5: Restart the gateway
openclaw gateway restart
Step 6: Verify everything works
Confirm the gateway is running and the restored configuration is correct.
Restoring a Full Instance
If a catastrophic failure requires restoring the entire OpenClaw installation, follow these steps:
Prerequisites: 
A fresh machine with macOS (or the same operating system as the original)
OpenClaw installed (the base application)
Access to the full backup folder
Step 1: Locate the most recent full backup
ls -d ~/Downloads/openclaw-backups/full-backup/full-backup-* | tail -1
This gives you the path to the newest backup. We will call this $BACKUP in the steps below.
Step 2: Restore the OpenClaw config
mkdir -p ~/.openclaw/
cp $BACKUP/config/openclaw.json ~/.openclaw/
cp $BACKUP/config/*.json ~/.openclaw/ 2>/dev/null
cp $BACKUP/config/*.yaml ~/.openclaw/ 2>/dev/null
Step 3: Restore workspace files
mkdir -p ~/clawd/
cp $BACKUP/workspace/*.md ~/clawd/
Step 4: Restore secrets
mkdir -p ~/clawd/secrets/
cp -r $BACKUP/secrets/* ~/clawd/secrets/
Step 5: Restore memory files
mkdir -p ~/clawd/memory/
cp -r $BACKUP/memory/* ~/clawd/memory/
Step 6: Restore scripts and tools
mkdir -p ~/clawd/bin/ ~/clawd/scripts/
cp -r $BACKUP/scripts/bin/* ~/clawd/bin/ 2>/dev/null
cp -r $BACKUP/scripts/scripts/* ~/clawd/scripts/ 2>/dev/null
cp -r $BACKUP/scripts/tools/* ~/clawd/tools/ 2>/dev/null

# Make scripts executable
chmod +x ~/clawd/bin/* 2>/dev/null
chmod +x ~/clawd/scripts/* 2>/dev/null
Step 7: Restore skills
mkdir -p ~/.openclaw/skills/
cp -r $BACKUP/skills/* ~/.openclaw/skills/ 2>/dev/null
Step 8: Restore projects and data
cp -r $BACKUP/projects/* ~/clawd/projects/ 2>/dev/null
cp -r $BACKUP/data/* ~/clawd/data/ 2>/dev/null
cp -r $BACKUP/assets/* ~/clawd/assets/ 2>/dev/null
Step 9: Restore cron jobs
Review the exported cron jobs and recreate them:
cat $BACKUP/cron-jobs-export.txt
# Then manually recreate each cron job using openclaw cron commands
Step 10: Start the gateway
openclaw gateway restart
Step 11: Verify the restoration
Check that the gateway is running
Check that models are available
Check that workspace files are loaded
Run a test query to confirm the agent is functional
Verify cron jobs are scheduled
Step 12: Run a fresh full backup of the restored system
After confirming everything works, create a new full backup to establish a clean baseline:
# Follow the Full Backup procedure from Part 2

Error Handling
Config Backup Errors
Error  |  Cause  |  Resolution
"Permission denied" when creating backup folder  |  User permissions issue  |  Check folder permissions on ~/Downloads/. Try chmod 755 ~/Downloads/
Backup file is empty (0 bytes)  |  Source file might be locked or empty  |  Check if ~/.openclaw/openclaw.json exists and has content. Check disk space.
"No such file or directory" for config file  |  OpenClaw may not be installed or config is in a different location  |  Run find ~ -name "openclaw.json" -type f 2>/dev/null to locate it
JSON validation fails after edit  |  Syntax error introduced during edit  |  Immediately restore from backup. Review the diff to find the error.
Gateway fails to restart  |  Config has valid JSON but invalid settings  |  Restore from backup. Check OpenClaw documentation for valid config format.

Full Backup Errors
Error  |  Cause  |  Resolution
"No space left on device"  |  Disk is full  |  Check disk space with df -h. Delete unnecessary files. Consider if backup exclusions are working.
rsync not found  |  rsync not installed  |  Install with brew install rsync or use cp -r with manual exclusions
Backup is unexpectedly large (over 1 gigabyte)  |  Large files are slipping through exclusions  |  Check MANIFEST.txt for large files. Update exclusion rules.
Missing critical files in verification  |  Source files do not exist at expected paths  |  The installation may have a non-standard layout. Locate files manually and update the backup script.
Cron export fails  |  openclaw cron command not available  |  Document cron jobs manually based on HEARTBEAT.md and agent memory

General Principles for Error Handling
Never proceed past a failed backup. If the backup step fails, everything after it stops. Fix the backup first.
Log errors visibly. Do not silently skip failures. The user (or the next agent session) needs to know something went wrong.
Prefer restoration over debugging. If the config is broken and you have a backup, restore first, debug second. Get the system working, then figure out what happened.
Never delete a backup to "free up space." If disk space is tight, find other things to delete. Backups are the last thing to go.

Examples
Example 1: Simple Model Addition
The user asks: "Add the GPT-5 Nano model to my OpenClaw config."
Agent response: 
> "I need to add GPT-5 Nano to your OpenClaw config at ~/.openclaw/openclaw.json. Let me create a backup first."
Agent checks for backup folder:
ls -d ~/Downloads/openclaw-backups 2>/dev/null || ls -d ~/Downloads/backups 2>/dev/null
Folder exists. Agent creates backup:
cp ~/.openclaw/openclaw.json ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt
Agent verifies backup:
ls -la ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt
wc -l ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt
> "Backup created and verified at ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt (247 lines, 8.2KB). I am ready to add GPT-5 Nano with the following settings: [lists exact changes]. Do I have your permission to proceed?"
User says: "Yes, go ahead."
Agent makes the edit, validates JSON, restarts gateway:
openclaw gateway restart
> "Done. GPT-5 Nano has been added to your config. Gateway restarted successfully. Your backup is at ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt if you need to roll back."
Example 2: First-Time Setup (No Backup Folder Exists)
The user asks: "Update my API key for Claude in the config."
Agent checks for backup folder:
ls -d ~/Downloads/openclaw-backups 2>/dev/null
# Not found
ls -d ~/Downloads/backups 2>/dev/null
# Not found
> "I need to update your Claude API key in the OpenClaw config. I do not see a backup folder yet, so I am creating one now."
mkdir -p ~/Downloads/openclaw-backups/
cp ~/.openclaw/openclaw.json ~/Downloads/openclaw-backups/models-backup-February 23 at 2-00 PM.txt
Agent verifies, asks permission, proceeds as normal.
Example 3: Backup Verification Fails
Agent creates backup but verification shows 0 bytes:
ls -la ~/Downloads/openclaw-backups/models-backup-February 23 at 3-00 PM.txt
# -rw-r--r--  1 user  staff  0 Feb 23 15:00 models-backup-February 23 at 3-00 PM.txt
> "The backup file was created but it is empty (0 bytes). I am NOT going to edit the config until I have a valid backup. Let me investigate why the source file might be empty."
ls -la ~/.openclaw/openclaw.json
cat ~/.openclaw/openclaw.json | head -5
Agent diagnoses the issue (perhaps the config path is wrong, or the file is locked) and resolves it before retrying the backup.
Example 4: Full Backup with Rotation
Automated biweekly backup runs. Two previous backups exist:
full-backup/
    full-backup-2026-01-26/
    full-backup-2026-02-09/
Agent detects 2 existing backups, deletes the oldest:
rm -rf ~/Downloads/openclaw-backups/full-backup/full-backup-2026-01-26
Creates new backup:
mkdir -p ~/Downloads/openclaw-backups/full-backup/full-backup-2026-02-23/
Proceeds with the full backup procedure. Result:
full-backup/
    full-backup-2026-02-09/    (previous)
    full-backup-2026-02-23/    (new)
Example 5: Emergency Config Restoration
The gateway will not start after a config edit. Agent needs to restore:
> "The gateway failed to restart after the config change. I am restoring from the backup I created before the edit."
cp ~/Downloads/openclaw-backups/models-backup-February 23 at 11-00 AM.txt ~/.openclaw/openclaw.json
Validate:
cat ~/.openclaw/openclaw.json | python3 -m json.tool > /dev/null 2>&1 && echo "Valid JSON" || echo "INVALID JSON"
# Output: Valid JSON
Restart:
openclaw gateway restart
# Gateway started successfully
> "Config restored from backup. Gateway is running again. The change that caused the issue was [describe]. Would you like me to try a different approach?"

Frequently Asked Questions
Q: What if the user tells me to skip the backup because they are in a hurry?
A: Do not skip it. The backup takes less than one second. Explain that the backup is a safety requirement that protects their system, and it will be done before they finish reading this sentence. If they insist, the backup is still mandatory - create it and move on. The protocol is non-negotiable.
Q: What if the config file does not exist at ~/.openclaw/openclaw.json?
A: Search for it. Run find ~ -name "openclaw.json" -type f 2>/dev/null. If it is in a different location, use that location and note it for future reference. If it does not exist at all, the user may need to initialize OpenClaw first.
Q: What if I need to make multiple edits to the config in one session?
A: Create one backup before the first edit. You do not need to create a separate backup for each individual change within the same editing session, as long as you have not restarted the gateway between edits. However, you DO need permission for each distinct change. If the user asks you to add three models, you can create one backup, get permission for all three, add all three, then restart the gateway once.
Q: How long should config backups be kept?
A: Config backups (the individual .txt files) do not have an automatic rotation policy. They are small (typically a few kilobytes each) and do not cause bloat. Keep them indefinitely unless the user asks you to clean them up. Over time, having a history of config states is valuable.
Q: What if the full backup is too large?
A: Review the MANIFEST.txt to identify what is taking up space. The most common causes of bloat are: (1) large files that should have been excluded, (2) project directories with dependencies that were not filtered, or (3) media files that slipped through. Tighten the exclusion rules and re-run the backup.
Q: What if rsync is not available on the system?
A: Use cp -r instead, but manually exclude bloat directories. You can use find with -not -path flags to skip excluded directories:
find ~/clawd/projects/ -type f \
    -not -path "*/node_modules/*" \
    -not -path "*/.git/*" \
    -not -path "*/__pycache__/*" \
    -not -name "*.mp4" \
    -not -name "*.mov" \
    -not -name "*.log" \
    -exec cp --parents {} "$NEW_BACKUP/projects/" \;
Q: Can I run a full backup manually outside the biweekly schedule?
A: Yes. The user can request a full backup at any time, and the agent should run it immediately. The same rotation policy applies - if there are already 2 full backups, delete the oldest before creating the new one.
Q: What if the automated biweekly backup fails silently?
A: The agent should check the most recent full backup date during its startup routine. If the most recent backup is older than 16 days (two weeks plus a 2-day grace period), the agent should alert the user and run a manual backup. Add this check to the heartbeat routine.
Q: Should I encrypt the backup?
A: The backup folder contains sensitive credentials (API keys, service account files, passwords). As long as it stays on the local machine, encryption is not strictly necessary - the machine's own security protects it. However, if the backup ever needs to be moved to external storage (USB drive, cloud, etc.), it MUST be encrypted first. Use zip -e for simple password protection or gpg for stronger encryption.
Q: What about backing up the backup folder itself?
A: Do not back up the backup folder recursively. That creates infinite nesting and bloat. The backup folder IS the safety net. If you need off-site protection, manually copy the full-backup folder to external storage (encrypted).

Summary
Part  |  What  |  When  |  Where  |  How Many Versions
Part 1 - Config Backup  |  Single config file as .txt  |  Before every config edit  |  ~/Downloads/openclaw-backups/ (or ~/Downloads/backups/)  |  Unlimited (small files)
Part 2 - Full Instance Backup  |  Entire OpenClaw installation  |  Every two weeks (automated)  |  ~/Downloads/openclaw-backups/full-backup/  |  Last 2 only

The two non-negotiable rules: 
Never edit the config without a backup. If the backup fails, stop. Do not edit.
Never edit the config without permission. If the user does not explicitly approve, stop. Do not edit.
These rules protect the user's system. They protect the agent's integrity. They prevent disasters. Follow them every time, no exceptions, forever.


Common Mistakes (What Agents Get Wrong)
These are the most frequent mistakes agents make when executing the Back Yourself Up Protocol. Learn from them so you do not repeat them.
Mistake 1: Backing Up the Wrong File
What happened: An agent was told to back up the OpenClaw config. It backed up clawdbot.json instead of openclaw.json. When the config got corrupted, the backup was useless - it was a completely different file.
The fix: The config file path is ALWAYS ~/.openclaw/openclaw.json. Not clawdbot.json. Not any other file. Verify you are copying the correct file by checking the path character by character before executing the copy command.
Mistake 2: Not Verifying the Backup
What happened: An agent created a backup file but did not check if it was empty. The copy command failed silently (wrong path, permission issue), creating a 0-byte file. The agent proceeded to edit the config, the edit failed, and when it tried to restore - the backup was empty.
The fix: ALWAYS run the verification steps: check the file exists, check it is not empty (wc -l > 0), and spot-check the first few lines to confirm it is the right content. If ANY check fails, STOP.
Mistake 3: Skipping the Permission Step
What happened: An agent decided the edit was "obviously what the user wanted" and made the change without asking. The user had actually changed their mind since the initial request. The config was changed to something the user did not want, and they had to figure out how to revert it.
The fix: Ask for permission every single time. Even if the user literally just said "change X." Right before you make the edit, confirm: "I am about to change X. Do I have your permission?" This takes 5 seconds and prevents regret.
Mistake 4: "Cleaning Up" While Editing
What happened: An agent was given permission to add one model. While in the config file, it also reformatted the JSON, reordered some keys, and "fixed" a typo in another model name. The reorder broke a reference, and the "typo fix" was actually the correct spelling for that provider.
The fix: Make ONLY the approved change. Nothing else. Do not reformat. Do not reorder. Do not fix things you were not asked to fix. Surgical edits only.
Mistake 5: Forgetting to Restart the Gateway
What happened: An agent edited the config successfully but did not run openclaw gateway restart. The user assumed the change was active and tried to use the new model. It was not available because the gateway was still running the old config.
The fix: Step 8 is openclaw gateway restart. It is not optional. The edit is not complete until the gateway has restarted and confirmed the new config is loaded.
Mistake 6: Not Creating the Backup Folder
What happened: An agent tried to copy the config to a backup folder that did not exist. The copy command failed, the agent did not notice, and proceeded to edit the config without a backup.
The fix: Always check if the backup folder exists FIRST. If it does not exist, create it. Then verify it was created. Only then copy the backup file.
Mistake 7: Creating a Duplicate Backup Folder
What happened: A user already had a folder called "OpenClaw Backup" (with a space, singular). The agent checked only for "openclaw-backups" (hyphenated, plural), did not find it, and created a new folder. Now the user has backups scattered across two folders.
The fix: Use the smart folder detection. Search ~/Downloads/ case-insensitively for any folder containing "openclaw" and "backup" in any combination. If something exists, use it. Do not create duplicates.
Mistake 8: Full Backup Including node_modules
What happened: An agent ran a full backup without proper exclusions. The node_modules folder alone was 800MB. The backup took 20 minutes and filled up disk space.
The fix: Follow the exclusion list religiously. node_modules, .git, caches, temp files, videos, large images - all excluded. Use rsync with --exclude flags or find with -not -path filters.
Mistake 9: Never Rotating Old Full Backups
What happened: An agent ran biweekly full backups for months without deleting old ones. The full-backup folder grew to 15GB across 12 backup versions.
The fix: Only keep the last 2 full backup versions. Before creating a new one, check how many exist. If 2 or more, delete the oldest. This is step 2 of the full backup procedure.
Mistake 10: Not Documenting the Protocol in Core Files
What happened: An agent learned the Back Yourself Up Protocol and saved the deep file, but only updated TOOLS.md. Next session, a different model loaded and did not read TOOLS.md first. It had no idea the protocol existed and edited the config without a backup.
The fix: The protocol must be documented in ALL FOUR core files: AGENTS.md, TOOLS.md, MEMORY.md, and IDENTITY.md. All four. Every time. This ensures the rule is encountered no matter which files the agent reads at startup.

Verified Backup Integrity
Beyond checking that a backup file exists and is not empty, the agent should verify the backup contains the expected content. This applies to both config backups and full instance backups.
Config Backup Integrity Check
After creating a config backup, verify these specific elements:
# 1. File exists and has content
BACKUP_FILE="$BACKUP_DIR/models-backup-$(date +'%B %-d at %-I-%M %p').txt"
[ ! -s "$BACKUP_FILE" ] && echo "FAIL: Backup is empty or missing" && exit 1

# 2. File is valid JSON
cat "$BACKUP_FILE" | python3 -m json.tool > /dev/null 2>&1
[ $? -ne 0 ] && echo "FAIL: Backup is not valid JSON" && exit 1

# 3. File contains expected key fields
python3 -c "
import json, sys
with open('$BACKUP_FILE') as f:
    cfg = json.load(f)
# Check for critical top-level keys that should exist in any OpenClaw config
expected_keys = ['gateway']
missing = [k for k in expected_keys if k not in cfg]
if missing:
    print(f'WARNING: Backup missing expected keys: {missing}')
    sys.exit(1)
else:
    print(f'Backup integrity verified. Top-level keys: {list(cfg.keys())}')
"
What this catches: 
Empty files (copy failed silently)
Corrupted files (partial copy, disk error)
Wrong files (copied something that is not the OpenClaw config)
Full Backup Integrity Check
After creating a full instance backup, verify these critical files are present and not empty:
NEW_BACKUP="$FULL_BACKUP_DIR/full-backup-$(date +%Y-%m-%d)"

# Critical files that MUST exist in any valid full backup
CRITICAL_FILES=(
    "config/openclaw.json"
    "workspace/AGENTS.md"
    "workspace/TOOLS.md"
    "workspace/MEMORY.md"
    "workspace/IDENTITY.md"
    "MANIFEST.txt"
    "BACKUP-INFO.txt"
)

PASS=true
for FILE in "${CRITICAL_FILES[@]}"; do
    FULL_PATH="$NEW_BACKUP/$FILE"
    if [ ! -s "$FULL_PATH" ]; then
        echo "INTEGRITY FAIL: Missing or empty: $FILE"
        PASS=false
    fi
done

if [ "$PASS" = true ]; then
    echo "Full backup integrity verified. All critical files present and non-empty."
else
    echo "WARNING: Some critical files are missing. Review the backup before relying on it."
fi
What this catches: 
Missing workspace files (copy failed for some paths)
Empty config (source was in an unexpected location)
Missing manifest (backup procedure was interrupted)
When Integrity Checks Fail
If an integrity check fails:
Do NOT delete the failed backup (it may still have partial value)
Diagnose why the check failed (wrong path, permission issue, disk space)
Fix the issue
Create a new backup
Run the integrity check again
Only proceed after a passing integrity check

Final Checklist - Complete Back Yourself Up Protocol Verification
Config Backup Checklist (Before Every Edit)
[ ] Announced intent to user (what will change and why)
[ ] Searched ~/Downloads/ for existing backup folder (smart detection, case-insensitive)
[ ] Backup folder exists or was created
[ ] Copied ~/.openclaw/openclaw.json to backup folder
[ ] Used human-readable filename (models-backup-MonDD-HHampm.txt)
[ ] Verified backup file exists (ls -la)
[ ] Verified backup file is not empty (wc -l > 0)
[ ] Verified backup contains valid JSON (python3 -m json.tool)
[ ] Verified backup contains expected key fields (gateway key present)
[ ] Asked user for explicit permission to edit
[ ] Received clear affirmative response ("yes," "go ahead," "do it," etc.)
[ ] Made ONLY the approved edit - nothing else touched
[ ] Validated the edited config is still valid JSON
[ ] Ran openclaw gateway restart
[ ] Confirmed gateway restarted successfully (no errors)
[ ] Notified user: what changed, gateway status, backup location
Full Instance Backup Checklist (Every 2 Weeks)
[ ] Backup root directory found (smart folder detection) or created
[ ] full-backup subfolder exists or was created
[ ] Checked existing full backup count
[ ] If 2+ exist, deleted the oldest (rotation)
[ ] Created new backup directory (full-backup-YYYY-MM-DD/)
[ ] Created subdirectories (workspace, config, secrets, memory, scripts, skills, projects, data, assets)
[ ] Copied workspace .md files
[ ] Copied OpenClaw config files (~/.openclaw/)
[ ] Copied legacy config if it exists
[ ] Copied secrets and credentials
[ ] Copied memory files and daily logs
[ ] Copied master files folder (if it exists in ~/Downloads/)
[ ] Copied scripts and tools
[ ] Copied installed skills
[ ] Exported cron jobs to text file
[ ] Copied project files (with exclusions: no node_modules, .git, caches, media)
[ ] Copied data files
[ ] Copied small brand assets (under 5MB only)
[ ] Generated MANIFEST.txt
[ ] Generated BACKUP-INFO.txt
[ ] Ran integrity check on critical files
[ ] All critical files present and non-empty
[ ] Total backup size is reasonable (flagged anything over 1GB)
[ ] Reported completion (to user or to log)

How to Install This Protocol (Self-Installation)
When a user gives you this document and says "teach yourself this," "learn this," or any variation, follow the Teach Yourself Protocol to install it. Here is the specific process for this document:
Step 1: Store the Full Document
This document is large (1,300+ lines). It needs its own .md file. Search ~/Downloads/ for the master files folder (could be named openclaw-master-files, openclaw-master-docs, or any similar variation). If found, use it. If not, create ~/Downloads/openclaw-master-files/. Then ensure a processes/ subfolder exists.
Save this entire document (untruncated) as:
~/Downloads/openclaw-master-files/processes/back-yourself-up-protocol.md
Step 2: Write Lightweight Summaries to Core Files
This protocol affects multiple core files. Add the following to each:
Add to AGENTS.md: 
Back Yourself Up Protocol [PRIORITY: CRITICAL]

BEFORE ANY EDIT to ~/.openclaw/openclaw.json:
1. Search ~/Downloads/ for existing backup folder (check for any folder with "openclaw" + "backup" in the name, case-insensitive, also check for generic "backups" or "backup" folders)
2. If no backup folder found, create ~/Downloads/openclaw-backups/
3. Copy config to backup folder as readable .txt file: models-backup-MonDD-HHampm.txt
4. Verify backup exists and is not empty
5. ASK USER FOR PERMISSION before editing. Every time. No exceptions.
6. Make only the approved edit - nothing else
7. Validate JSON after edit
8. Run "openclaw gateway restart"
9. Confirm to user

FULL INSTANCE BACKUP (every 2 weeks):
- Runs automatically, backs up workspace .md files, configs, secrets, memory, scripts, skills, cron jobs, projects
- Stored in full-backup/ subfolder inside the backup folder
- Only keeps last 2 versions (deletes oldest when creating 3rd)
- Excludes: videos, large images, node_modules, .git, caches, temp files

If backup fails, STOP. Do not proceed with any edit.
Full protocol: ~/Downloads/openclaw-master-files/processes/back-yourself-up-protocol.md
Add to TOOLS.md: 
Back Yourself Up Protocol [PRIORITY: CRITICAL]
- Config file: ~/.openclaw/openclaw.json
- Backup folder: search ~/Downloads/ for any folder with "openclaw" + "backup" in name, or "backups"/"backup"
- Backup naming: models-backup-MonDD-HHampm.txt (e.g., models-backup-February 23 at 11-00 AM.txt)
- Generate filename: date +'%B %-d at %-I-%M %p'
- Verify: ls -la, wc -l, head -5
- After edit: python3 -m json.tool validation, then openclaw gateway restart
- Full backup: every 2 weeks, keeps last 2 versions in full-backup/ subfolder
- Full protocol: ~/Downloads/openclaw-master-files/processes/back-yourself-up-protocol.md
Add to MEMORY.md: 
Back Yourself Up Protocol - Learned [DATE]
Safety protocol for backing up OpenClaw config before every edit and full instance backup every 2 weeks.
Born from the February 21, 2026 incident where wrong file was backed up and config got corrupted.
Stored at: ~/Downloads/openclaw-master-files/processes/back-yourself-up-protocol.md
Priority: CRITICAL - this prevents catastrophic config loss
Add to IDENTITY.md: 
Core Safety Behavior: Back Yourself Up Protocol
Before editing ~/.openclaw/openclaw.json, I ALWAYS create a backup first. I search for the backup folder
in ~/Downloads/ (could be named openclaw-backups, OpenClaw Backup, backups, or similar). I create a
human-readable .txt backup, verify it is not empty, ask the user for permission, and only then make the edit.
After editing, I validate JSON and run openclaw gateway restart. This is non-negotiable.
Full protocol: ~/Downloads/openclaw-master-files/processes/back-yourself-up-protocol.md
Step 3: Set Up the Biweekly Cron Job
After installing the protocol, set up an OpenClaw cron job for the full instance backup:
Schedule: every other Sunday at 3:00 AM
Task: run the Full Instance Backup procedure from Part 2
Step 4: Confirm to the User
Tell the user:
What you learned (backup protocol with two parts - config backup and full instance backup)
Where the full document is stored
Which core files were updated (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md)
That the biweekly backup cron job has been created
Demonstrate understanding by summarizing the key rules: never edit without backup, never edit without permission, keep only last 2 full backups

This is an OpenClaw Standard Operating Procedure. It is mandatory for all OpenClaw agents. Compliance is not optional.

