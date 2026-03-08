# START HERE - OpenClaw Onboarding
**READ THIS ENTIRE FILE BEFORE TOUCHING ANYTHING ELSE.**

---

## INSTALL ORDER - FOLLOW THIS EXACTLY

The install script handles dependencies automatically. Your AI agent installs skills in this order:

---

### 🔴 STEP 1 (MANDATORY FIRST): Teach Yourself Protocol (TYP)
**Folder:** `01-teach-yourself-protocol/`
Teaches the AI how to store knowledge correctly - lean summaries and file path references only.
Without this, every skill install will bloat your core files and waste tokens every session.
**Nothing else installs until TYP is confirmed.**

### 🔴 STEP 2 (MANDATORY SECOND): Back Yourself Up Protocol
**Folder:** `02-back-yourself-up-protocol/`
Teaches the AI how to back up config files before touching anything.
Without this, one bad edit can corrupt your system with no way to recover.
**Nothing else installs until this is confirmed.**

### ✅ STEP 3: QMD (Semantic Search Engine)
**Handled automatically by the install script - no skill folder needed.**
QMD is installed as a system dependency before skills 4-29 run.
It powers the persona search in Skill 22 and the persona detection in Skill 23.
If the install script already ran, QMD is installed. No manual step needed.

### STEPS 4-29: All Remaining Skills (in numbered order)
Skills install sequentially. For each skill:
- The agent checks if API keys are already present in your env files
- If a key is found → proceeds automatically
- If a key is not found → asks you to enter it, or offers to skip and remind you later
- You can skip any skill and the agent moves to the next one automatically

**Every skill from 04 through 29 requires both TYP (Step 1) and Back Yourself Up (Step 2) to be installed first.**
No exceptions. If you skip those two, stop and go back.

---


---

## WEEKLY SKILL UPDATE CHECK

Once the onboarding package is installed, your agent should check for updates **every Sunday**.

**GitHub repo:** `https://github.com/trevorotts1/openclaw-onboarding`

### What to check

```bash
# From wherever the onboarding package is installed:
cd ~/.openclaw/onboarding   # or wherever the package lives
git fetch origin
git log HEAD..origin/main --oneline --name-only 2>/dev/null || \
  echo "No git history - check GitHub directly"
```

### Weekly check workflow

1. Pull the latest from `main`:
   ```bash
   git pull origin main
   ```
2. Compare CHANGELOGs for any skill folder that changed.
3. For each updated skill:
   - Re-run TYP on the updated SKILL.md
   - Re-apply CORE_UPDATES.md if it changed
   - Rebuild the `.skill` archive if scripts changed
4. Notify via your configured messaging channel: "3 skills updated this week: [list]. Re-learned. No action needed."

### If git is not available

Check `https://github.com/trevorotts1/openclaw-onboarding/commits/main` directly and compare the install date against recent commit dates.

---

## TYP CONFLICT RULE - UNIVERSAL (applies to every skill)

Every skill in this package uses the Teach Yourself Protocol. But skills have their
own SKILL.md, CORE_UPDATES.md, and supporting files that specify exactly what to
update and how.

**When a skill's files conflict with TYP about which core .md files to update
or what content to add - always follow the skill's files.**

- TYP governs the storage METHOD: lean summaries and file path references in core files
- The skill governs the CONTENT and which files it touches
- Skill docs always take precedence over TYP when there is a conflict
- This applies to every skill from 03 through 29

---

---

## RESUMING A PARTIAL ONBOARDING

Before starting fresh, check if a previous onboarding attempt was partially completed:

```bash
cat "$MASTER_FILES_FOLDER/OpenClaw Onboarding/.onboarding-status.json" 2>/dev/null
```

If this file exists and contains skill statuses, resume from the first skill that is not marked INSTALLED or ALREADY_INSTALLED. Do not re-run skills already marked complete.

After each skill completes, write or update this status file:

```json
{
  "started": "[ISO timestamp]",
  "master_files_folder": "[actual path used]",
  "skills": {
    "01-teach-yourself-protocol": "INSTALLED",
    "02-back-yourself-up-protocol": "INSTALLED"
  }
}
```

---

## BEFORE YOU DO ANYTHING - MANDATORY FIRST STEP

You are about to autonomously set up a new OpenClaw installation. This process is sequential.
You do the work. The human does not install skills, configure files, or execute steps.
Your job is to read each skill folder and execute the setup yourself.
Complete each step fully before moving to the next. Do not skip. Do not reorder. Do not improvise.
Only pause and request human input when you need something only they can provide:
an API key they have not yet entered, a 2FA code, or a first-time browser login.

---

## PREREQUISITES - VERIFY BEFORE STARTING

Before you begin onboarding, verify all of the following. If any check fails, stop
and tell the user what is missing. Do not start onboarding until every check passes.

### 0. Operating system
This onboarding package is designed for macOS. All install commands, paths, and tooling
assume macOS (Darwin). Proceed without asking about OS - if the machine is not macOS,
tell the user and stop.

```bash
uname -s
```

Expected output: Darwin

### 1. OpenClaw is installed and running

```bash
openclaw status
```

If this command fails or OpenClaw is not running, stop. The user needs to install
OpenClaw first before any skills can be added.

### 2. Workspace files exist

Check that these files exist in the workspace root:
- AGENTS.md
- TOOLS.md
- MEMORY.md
- IDENTITY.md
- USER.md
- SOUL.md
- HEARTBEAT.md

If any are missing, create them as empty files with a single header line.
These are the files that skills will update during installation.

### 3. Find or create the master files folder

This is where full skill documentation and reference files are stored. The Teach
Yourself Protocol requires that full documentation lives here, not inside your
core workspace files.

**Search first. Do not create a duplicate.**

Check if the user already has a master files folder. It may not be named exactly
the same on every machine. Look for any of these patterns:

```bash
ls -d ~/Downloads/openclaw-master-files 2>/dev/null
ls -d ~/Downloads/openclaw-master-docs 2>/dev/null
ls -d ~/Downloads/OpenClaw\ Master\ Files 2>/dev/null
ls -d ~/Downloads/master-files 2>/dev/null
ls -d ~/Documents/openclaw-master-files 2>/dev/null
```

If exactly one match is found: use it and continue. If multiple matches are found: ask the user which to use. If no match is found: create ~/Downloads/openclaw-master-files/ and continue.

**If a folder exists:** Use it. Store that path. All skills will be extracted there.
Do not create a second folder.

**If no folder exists:** Create one:
```bash
mkdir -p ~/Downloads/openclaw-master-files/
```

**Store the path.** Every reference to the master files folder in this onboarding
uses the path you found or created here. If the user's folder is called
`~/Downloads/OpenClaw Master Docs` instead of `~/Downloads/openclaw-master-files`,
use their path everywhere. Do not rename their folder.

### 4. Write permission check
Verify the workspace root and master files folder are writable:

```bash
touch [WORKSPACE_ROOT]/.write-test && rm [WORKSPACE_ROOT]/.write-test
```

If this fails, tell the user the folder is not writable and stop. Do not proceed.

### 5. Disk space check

```bash
df -h ~ | awk 'NR==2 {print $4}'
```

Ensure at least 2 GB of free space before starting. Playwright alone uses 500 MB+.
If less than 2 GB available, warn the user and ask if they want to proceed anyway.

### 6. Workspace root detection
The workspace root is the directory containing AGENTS.md, TOOLS.md, and other core files.
Detect it:

```bash
grep -o '"workspace"[[:space:]]*:[[:space:]]*"[^"]*"' ~/.openclaw/openclaw.json 2>/dev/null
```

If not found in the config, check these common locations in order: ~/clawd, ~/openclaw, current directory.
Store the workspace root path - every reference to "workspace root" in this document uses this path.

### 7. Messaging channel detection
Detect the user's primary messaging channel:

```bash
grep -o '"channel"[[:space:]]*:[[:space:]]*"[^"]*"' ~/.openclaw/openclaw.json 2>/dev/null
```

Store the channel name (telegram, slack, discord, etc.). Use this channel for all status
messages and the weekly update notification. If no channel is found, deliver messages
in the current conversation only.

### 8. Existing skills scan
Before starting, scan what OpenClaw skills are already installed:

```bash
openclaw skills list 2>/dev/null || ls ~/.openclaw/skills/ 2>/dev/null
```

Record the list. During each skill's pre-check, cross-reference this list to detect
already-installed skills without repeating setup steps.

### 9. Download and extract the onboarding package

Download the onboarding ZIP and extract it into the master files folder, inside a subfolder called `OpenClaw Onboarding`:

> **Install command:** See your instructor or onboarding package README for the latest install URL.

```bash
unzip /tmp/onboarding.zip -d /tmp/onboarding-temp/
mv /tmp/onboarding-temp/*/  [MASTER_FILES_FOLDER]/OpenClaw\ Onboarding/
rm -rf /tmp/onboarding-temp /tmp/onboarding.zip
```

Replace `[MASTER_FILES_FOLDER]` with the actual path from step 3.

**After extraction, verify the folder structure looks like this:**

```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/
    Start Here.md                          (this file)
    01-teach-yourself-protocol/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        teach-yourself-protocol.skill
    02-back-yourself-up-protocol/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        back-yourself-up-protocol.skill
    03-agent-browser/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
    04-superpowers/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        superpowers.skill
    05-ghl-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        ghl-setup.skill
    06-ghl-install-pages/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        ghl-install-pages.skill
    07-kie-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        kie-setup.skill
    08-vercel-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        vercel-setup.skill
    09-context7/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        context7.skill
    10-github-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        github-setup.skill
    11-superdesign/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        superdesign.skill
    12-openrouter-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        openrouter-setup.skill
    13-google-workspace-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        google-workspace-setup.skill
    14-google-workspace-integration/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        google-workspace-integration.skill
    15-blackceo-team-management/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        blackceo-team-management.skill
    16-summarize-youtube/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
        summarize-youtube.skill
    17-self-improving-agent/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        self-improving-agent-full.md
        self-improving-agent.skill
        upstream-original/
    18-proactive-agent/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        proactive-agent-full.md
        proactive-agent.skill
        upstream-original/
    19-humanizer/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        humanizer-full.md
        humanizer.skill
        upstream-original/
    20-youtube-watcher/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        youtube-watcher-full.md
        youtube-watcher.skill
        upstream-original/
    21-tavily-search/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        tavily-search-full.md
        tavily-search.skill
        upstream-original/
    22-book-to-persona-coaching-leadership-system/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
        PIPELINE.md
        QMD-RETRIEVAL-GUIDE.md
        PERSONA-ROUTER.md
        personas/
        pipeline/
    23-ai-workforce-blueprint/
        SKILL.md
        INSTALL.md
        CORE_UPDATES.md
        ai-workforce-blueprint.skill
    24-storyboard-writer/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        storyboard-writer.skill
    25-video-creator/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        video-creator.skill
    26-caption-creator/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        caption-creator.skill
    27-video-editor/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        video-editor.skill
    28-cinematic-forge/
        SKILL.md
        INSTALL.md
        README.md
```

**Each skill folder contains some combination of SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md.** Some skills also include a `[skill-name]-full.md`, a `.skill` package file, an `upstream-original/` subfolder, or additional reference documents. File count varies by skill. If SKILL.md or INSTALL.md is missing from a folder, stop and tell the user before proceeding.

**Naming rules:**
- Folder names are lowercase with hyphens, prefixed with their install number (01 through 29)
- The .skill file (when present) matches the folder name without the number prefix
- Do NOT rename any folder or file. Use the names exactly as listed above.


---

## STEP 1: LEARN THE TEACH YOURSELF PROTOCOL FIRST

Before installing any skill, before reading any other file in this folder,
you must learn the Teach Yourself Protocol.

**Why:** Without this protocol, you will learn things the wrong way. You will dump full
documentation into AGENTS.md, TOOLS.md, and MEMORY.md and bloat those files.
Bloated files burn tokens every session because they load every time you start.
This protocol teaches you HOW to store knowledge correctly - full docs go to the master
files folder, only summaries and file path references go into the core files.

**Where to find it:**
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/01-teach-yourself-protocol/
```

**DO NOT PROCEED TO STEP 2 UNTIL THIS PROTOCOL IS FULLY LEARNED AND CONFIRMED.**

If you have not yet read the TYP files, go read them now from the folder listed above.
Do not announce this to the user - just do it and proceed.

---

## STEP 2: INSTALL THE BACKUP PROTOCOL SECOND

Before installing any tools, models, or integrations, you must learn and install
the Back Yourself Up Protocol. This protects the user's system from the moment
you start making changes.

**Why:** Every time you edit a model config file or any system config, you must
back it up first. If you have not learned the backup protocol, you will make
changes without backups and corrupt the user's system.

**Where to find it:**
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/02-back-yourself-up-protocol/
```

**After installing backup protocol:**
- Confirm the backup folder exists or create it
- Confirm you know the correct date naming format: date +'%B %-d at %-I-%M %p'
  Example: models-backup-February 28 at 3-00 PM.txt
- Add the backup rules to AGENTS.md, TOOLS.md, MEMORY.md, and IDENTITY.md
- Set up the biweekly automated full backup cron job

**DO NOT PROCEED TO STEP 3 UNTIL BACKUP PROTOCOL IS INSTALLED AND VERIFIED.**

---

## STEP 3: INSTALL SKILLS IN THIS EXACT ORDER

Install one skill at a time. Complete each skill fully before starting the next.

### Files Inside Each Skill Folder

Every skill folder contains these files. Read them in this exact order:

| Order | File | Purpose |
|-------|------|---------|
| 1st | **SKILL.md** | Read this FIRST. Understand what this skill is, what it does, and when it triggers. Do not proceed until you understand the skill's purpose. |
| 2nd | **INSTALL.md** | Read this SECOND. Step-by-step installation and configuration. Follow every step exactly. Do not skip verification steps. |
| 3rd | **Full guide doc(s)** (if present) | Read any additional guide documents that exist in the folder: INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, PIPELINE.md, upstream-original/ files, etc. Not every skill has all of these - read whatever is present. |
| 4th | **CORE_UPDATES.md** | Read this LAST before installing. This file tells you exactly which workspace files (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md) need updating and gives you the exact text to add. Only update the files listed. Do not update files that are not listed. Do not add more than what is written. |
| Final | **[skill-name].skill** | Install this after reading all docs. This is the skill package. Install it with: openclaw skill install [skill-name].skill (only if a .skill file exists in this folder) |

### For Each Skill, Follow This Process

1. Open the skill folder
2. Read SKILL.md completely - understand what the skill is
3. Read INSTALL.md completely - build a mental checklist of everything it requires
4. Execute the INSTALL.md steps one by one - do not skip any step
5. Read all full guide docs that exist in this folder (INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, PIPELINE.md, upstream-original/ files, etc.) - read whatever is present
6. Read CORE_UPDATES.md - update ONLY the workspace files it specifies, with ONLY the text it provides
7. Install the .skill package file (if one exists in this folder)
8. Verify the skill is working
9. **Report to the user:** "Skill [number] of 29 installed. [Skill name] is complete." Then proceed to the next skill immediately. Do not wait for acknowledgment.
10. Start the next skill.

### What CORE_UPDATES.md Does

Each skill affects different workspace files. A video editing skill does not need to update
IDENTITY.md or SOUL.md. A team management skill does need to update USER.md with team member
information. CORE_UPDATES.md removes the guesswork.

It tells you:
- Which workspace files to update (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md)
- The exact text to add to each file
- Which files to NOT touch for this skill
- Where in each file to add the new content

**Rules for CORE_UPDATES.md:**
- Only update the files it lists. If a file is not listed, do not touch it.
- Use the exact text provided. Do not rewrite it, expand it, or summarize it.
- Add summaries and file path references only. Full documentation stays in the skill folder.
- This follows the Teach Yourself Protocol. If you have not learned TYP, go back to Step 1.

### If a Skill Fails to Install

If any step in a skill's installation fails:
1. Tell the user exactly what failed, which step failed, and the exact error.
2. Try at least one alternative fix before deciding final status.
3. Classify the skill:
   - CORE skills: 01 Teach Yourself Protocol, 02 Back Yourself Up Protocol, 03 Agent Browser
   - OPTIONAL skills: all platform/API-dependent skills (Superpowers, GHL, Vercel, Context7, GitHub, Google, KIE, etc.)
4. If a CORE skill fails, STOP onboarding and request what is needed.
5. If an OPTIONAL skill fails due to missing API key, missing account, or user says they do not use that system:
   - mark skill status as SKIPPED
   - record exact reason
   - continue to next skill
6. Never silently skip. Always report INSTALLED or SKIPPED with reason.
7. If failure appears network-related (timeout, DNS error, connection refused, download failure):
   retry the failing step up to 3 times with 10-second delays before classifying as FAILED.

---

### EXECUTION STRATEGY (MANDATORY)

1. Run skill 01 and skill 02 sequentially in the main agent.
2. After skill 02 completes, install skills sequentially by default.
   Sub-agents MAY be used for skills with no dependencies on each other.
   The following skills MUST remain sequential - do NOT parallelize:
   - Skill 05 (GHL Setup) must complete before Skill 06 (GHL Install Pages)
   - Skill 13 (Google Workspace Setup) must complete before Skill 14 (Google Workspace Integration)
   - Skill 22 (Book to Persona) must complete before Skill 23 (AI Workforce Blueprint)
   All other skills may be parallelized in batches of up to 3 sub-agents.
3. The agent executes all installs. The human is not asked to run steps. The agent runs them.
3. Keep OpenRouter setup for last after model config backup is verified.
4. Superdesign is the only skill allowed to rely on service CLI commands.

### API KEY DISCOVERY (MANDATORY BEFORE ASKING USER)

Before asking for any API key, scan these locations first:
- `.env` in the workspace root
- `secrets/.env` in the workspace root
- `~/.openclaw/secrets/` (any .env files in this directory)
- `~/.openclaw/openclaw.json` (check provider configs for existing keys)
- Shell environment: `printenv | grep -i <KEY_NAME>`

Use flexible matching for key names. Treat these as possible equivalents:
- OPENROUTER_API_KEY, OPEN_ROUTER_API_KEY, OPEN ROUTER API KEY
- CONTEXT7_API_KEY, CONTEXT_7_API_KEY, CONTEXT 7 API KEY
- VERCEL_TOKEN, VERCEL_API_TOKEN
- GITHUB_TOKEN, GH_TOKEN, GITHUB_PAT

If a usable key is found, use it and continue without asking the user.
If no key is found, ask once. If still missing and skill is optional, mark SKIPPED and continue.

### WHERE TO STORE NEW KEYS
When a user provides an API key during onboarding:
1. Check if the skill's INSTALL.md specifies a storage location - use that.
2. If INSTALL.md does not specify, write the key to `[WORKSPACE_ROOT]/secrets/.env`
   (create the file if it does not exist).
3. Never store API keys inside AGENTS.md, TOOLS.md, MEMORY.md, or any workspace .md file.

### DEFERRED KEYS - PENDING LIST
If a user says they will add a key later or wants to skip:
1. Mark the skill as SKIPPED with reason: "Missing [KEY_NAME] - user deferred"
2. Append an entry to `[MASTER_FILES_FOLDER]/OpenClaw Onboarding/.pending-keys.md`:
   ```
   ## [Skill Name] - PENDING
   - Key needed: [KEY_NAME]
   - Where to add it: [location from INSTALL.md or workspace secrets/.env]
   - To complete setup later: re-run this skill's INSTALL.md after adding the key
   ```
3. Include all pending keys in the final onboarding summary.

### GOOGLE ACCOUNT BRANCHING (MANDATORY)

At the start of Google setup, ask:
- "Do you use Google Workspace (custom domain) or regular Gmail?"

Routing:
- If Workspace domain account: use Workspace path (service account + delegated setup where required)
- If regular Gmail only: use Gmail path (OAuth/user-based setup)

### PLAYWRIGHT REQUIREMENT (MANDATORY)

Install Playwright early in onboarding before automation-heavy skills.
When Playwright is used, it must use persistent sessions with:
- `launchPersistentContext(userDataDir)`

Never use regular `launch()` for onboarding automation.


### ALREADY-INSTALLED DETECTION (MANDATORY)

Before starting each skill, run a quick pre-check to detect whether the skill is already configured.

Rule:
1. If pre-check shows the skill is already installed and verified, mark it as ALREADY_INSTALLED.
2. Record short proof (what check passed).
3. Skip re-installation and continue to the next skill.
4. Never re-run setup steps blindly when the system is already configured.

Examples of pre-checks:
- Tool exists (`command --version` succeeds)
- Required env key exists and is non-empty in discovered env files
- Required config block already exists in target file
- Required account/token already validated by API test

Status values allowed per skill:
- INSTALLED
- ALREADY_INSTALLED
- SKIPPED (optional only, with reason)
- FAILED (core skill failure stops onboarding)

### INSTALL ORDER

All skill folders are located inside:
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/
```

| # | Skill | Folder Name | Notes |
|---|-------|-------------|-------|
| 1 | Teach Yourself Protocol | 01-teach-yourself-protocol | 🔴 MANDATORY FIRST |
| 2 | Back Yourself Up Protocol | 02-back-yourself-up-protocol | 🔴 MANDATORY SECOND |
| — | **QMD** | *(installed by install script)* | ✅ Auto-installed before skills 3-29 |
| 3 | Agent Browser (Vercel) - preferred browser automation | 03-agent-browser |
| 4 | Superpowers | 04-superpowers |
| 5 | GHL / Convert and Flow Setup | 05-ghl-setup |
| 6 | GHL / Convert and Flow - Install Pages | 06-ghl-install-pages |
| 7 | KIE Setup and HTTP Structure | 07-kie-setup |
| 8 | Vercel Setup (Vercel CLI) | 08-vercel-setup |
| 9 | Context7 Setup (API/browser) | 09-context7 |
| 10 | GitHub / Git Setup (gh CLI + API) | 10-github-setup |
| 11 | SuperDesign Instructions Setup | 11-superdesign |
| 12 | Google Workspace Setup (branch: Workspace vs Gmail) | 13-google-workspace-setup |
| 13 | Google Workspace Integration | 14-google-workspace-integration |
| 14 | BlackCEO Team Management Setup | 15-blackceo-team-management |
| 15 | Summarize YouTube Setup | 16-summarize-youtube |
| 16 | Self-Improving Agent | 17-self-improving-agent |
| 17 | Proactive Agent | 18-proactive-agent |
| 18 | Humanizer | 19-humanizer |
| 19 | YouTube Watcher | 20-youtube-watcher |
| 20 | Tavily Search | 21-tavily-search |
| 21 | Book To Persona & Coaching & Leadership System | 22-book-to-persona-coaching-leadership-system |
| 22 | AI Workforce Blueprint | 23-ai-workforce-blueprint |
| 23 | Storyboard Writer | 24-storyboard-writer |
| 24 | Video Creator | 25-video-creator |
| 25 | Caption Creator | 26-caption-creator |
| 26 | Video Editor | 27-video-editor |
| 27 | Cinematic Forge | 28-cinematic-forge |
| 28 | OpenRouter Setup (MUST BE LAST, after model backup) | 12-openrouter-setup |
| 29 | GHL / Convert and Flow API v2 | 29-ghl-convert-and-flow |


---

## PACKAGE FILE LISTING

> **See README.md for the complete list of files included in this onboarding package.**

---

## RULES THAT APPLY TO THIS ENTIRE ONBOARDING

- Install TYP (01) FIRST. Install Back Yourself Up Protocol (02) SECOND. No exceptions.
- Every skill from 03 onward requires TYP to be confirmed before its install begins
- When a skill's files conflict with TYP about which core files to update - the skill wins
- TYP governs storage method. The skill governs content and which files it touches.
- Do NOT change any API keys, terminal commands, or config values from what is written
- Do NOT add steps that are not in the instructions
- GitHub setup uses GitHub CLI (gh) and GitHub API as needed
- Vercel setup uses Vercel CLI (official recommended path)
- Context7 setup uses API and browser setup (no Context7 CLI required)
- Superdesign may use its CLI install command as documented
- Do NOT skip verification steps
- Do NOT tell the user a skill is installed until you have verified it works
- Do NOT bloat AGENTS.md, TOOLS.md, or MEMORY.md with full documentation
- Do NOT update workspace files that CORE_UPDATES.md does not list for that skill
- Do NOT rewrite the text provided in CORE_UPDATES.md - use it exactly as written
- Do NOT silently skip any skill
- Optional skills with missing account/API may be marked SKIPPED with reason and onboarding should continue
- Core skills (01, 02, 03) cannot be skipped
- Do NOT create a duplicate master files folder if one already exists
- ALWAYS back up config files before editing them
- ALWAYS use human-readable dates on all backup filenames: date +'%B %-d at %-I-%M %p'
- ALWAYS read .md files in this order: SKILL.md → INSTALL.md → all full guide docs present (INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, upstream-original/ files, etc.) → CORE_UPDATES.md
- ALWAYS report skill completion to the user, then continue immediately without waiting
- If anything fails, report exact failure and classify as CORE stop or OPTIONAL skip

---

## IMPORTED SKILLS (16-29) - AUTHORITATIVE INSTALL RULES

Skills 16 through 29 are imported or recreated skills. Many preserve upstream source files under an `upstream-original/` subfolder. Some have additional reference documents (PIPELINE.md, QMD-RETRIEVAL-GUIDE.md, GOOD-AND-BAD-EXAMPLES.md, etc.).

**The file-read order for ALL imported skills is the same as for all skills:**
1. Read `SKILL.md` first
2. Read `INSTALL.md` second
3. Read all full guide docs present in the folder (INSTRUCTIONS.md, EXAMPLES.md, [skill-name]-full.md, PIPELINE.md, upstream-original/ files, etc.)
4. Read `CORE_UPDATES.md` last before installing

**Conflict rule:** If TYP wrapper instructions conflict with a skill's own `SKILL.md` or `CORE_UPDATES.md`, follow the skill's files. TYP governs storage method; the skill governs content.

**Mandatory TYP file-read rule:**
1. Discover every `.md` file in the skill folder (including all subfolders).
2. Read every `.md` file with no exceptions.
3. Report discovered count and read count.
4. If counts do not match, stop and mark install as failed.

**Core file update rule:**
- Apply only the updates listed in that skill's `CORE_UPDATES.md`.
- Do not edit workspace files that CORE_UPDATES.md does not list for that skill.

---

## AUTO-START RULE - READ THIS BEFORE INSTALLING ANYTHING

**When you receive this file, begin immediately. Do not ask the user if you should start. Do not say "Ready to begin?" Do not wait for confirmation. Just start.**

The install script has already downloaded all skills to disk. Your job is to install them in order, one by one, automatically.

- Install Skill 01 → confirm it worked → install Skill 02 → confirm → continue through all 29
- Only pause when you need something the user must provide (API key not in any env file, 2FA code, first-time browser login)
- When you need a key: ask clearly, wait for answer, then continue
- When a skill is optional and the user wants to skip: mark SKIPPED, move to next - do not stop the whole install
- Do not announce "I will now install skill X" - just do it and report when done

---

## RESUME DETECTION - CHECK BEFORE STARTING

Before installing skill 01, check if a previous onboarding attempt is partially complete:

```bash
cat ~/.openclaw/onboarding/.onboarding-status 2>/dev/null
```

If this file exists with skill statuses, resume from the first skill not marked INSTALLED, ALREADY_INSTALLED, or SKIPPED. Do not reinstall skills that are already complete.

After each skill completes, append to ~/.openclaw/onboarding/.onboarding-status:
```
SKILL-01: INSTALLED
SKILL-02: INSTALLED
```
(Use INSTALLED, ALREADY_INSTALLED, SKIPPED, or FAILED)

---

## PROGRESS UPDATES

Every 5 skills completed, send a brief status update via the user's configured messaging channel:
"Onboarding in progress: [X] of 29 skills complete. Currently on: [skill name]."

---

## FINAL STEP - SET UP WEEKLY AUTO-UPDATE (Agent Runs This)

After all 29 skills are installed, run this as the final step.
The agent executes these commands - the human does nothing.

> **Install script URL:** See your instructor or onboarding package README for the latest auto-update script URL.

Verify the cron job installed:
```bash
crontab -l | grep update-skills
```

This sets up a cron job that runs every Sunday at 2:00 AM. It checks for new skill versions, downloads and applies updates to installed skills only, and sends a Telegram notification with what changed. It runs automatically every week. No human action needed after this point.

---

## WHEN ONBOARDING IS COMPLETE

### Remove the ONBOARDING PENDING flag
Before sending the completion summary, remove the flag that install.sh wrote to AGENTS.md:

Open [WORKSPACE_ROOT]/AGENTS.md and delete the block that reads:
```
## ONBOARDING PENDING - EXECUTE NOW
...
```
If the block is not present, continue without error.

### How to deliver the completion summary
- If running in an active chat session: post the summary in that chat.
- If running as a background or sub-agent task: send the summary via the configured
  messaging channel (detected in prerequisites).
- Format the 29-skill status report as a table: Skill | Name | Status | Notes

Then write to MEMORY.md: "ONBOARDING COMPLETE - [date] - All 29 skills processed"

When every skill on the list above is installed and verified, tell the user:
1. Everything that was installed (all 29 skills with status: INSTALLED / ALREADY_INSTALLED / SKIPPED / FAILED)
2. Everything that was added to each workspace file (AGENTS.md, TOOLS.md, MEMORY.md, etc.)
3. Which workspace files were updated and which were not touched
4. Where the full documentation for each skill is saved (the master files folder path)
5. That the backup protocol is active and the first backup has been created

---

This file is part of the OpenClaw Onboarding system.
