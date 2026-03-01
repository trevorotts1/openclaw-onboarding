# START HERE - OpenClaw Onboarding
**READ THIS ENTIRE FILE BEFORE TOUCHING ANYTHING ELSE.**

---

## BEFORE YOU DO ANYTHING - MANDATORY FIRST STEP

You are about to onboard a new OpenClaw installation. This process is sequential.
Every step must be completed in order before moving to the next one.
Do not skip steps. Do not reorder steps. Do not improvise.

---

## PREREQUISITES - VERIFY BEFORE STARTING

Before you begin onboarding, verify all of the following. If any check fails, stop
and tell the user what is missing. Do not start onboarding until every check passes.

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

Also ask the user:
> "Do you have an existing folder where you keep OpenClaw master files or
> reference documents? If so, what is the path?"

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

### 4. Download and extract the onboarding package

Download the onboarding ZIP from the GitHub repository:

```bash
curl -L https://github.com/[REPO_URL]/archive/refs/heads/main.zip -o /tmp/onboarding.zip
```

**Extract it into the master files folder, inside a subfolder called `OpenClaw Onboarding`:**

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
    03-superpowers/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        superpowers.skill
    04-ghl-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        ghl-setup.skill
    05-ghl-install-pages/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        ghl-install-pages.skill
    06-kie-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        kie-setup.skill
    07-vercel-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        vercel-setup.skill
    08-context7/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        context7.skill
    09-github-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        github-setup.skill
    10-superdesign/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        superdesign.skill
    11-openrouter-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        openrouter-setup.skill
    12-google-workspace-setup/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        google-workspace-setup.skill
    13-google-workspace-integration/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        google-workspace-integration.skill
    14-blackceo-team-management/
        SKILL.md
        INSTALL.md
        INSTRUCTIONS.md
        EXAMPLES.md
        CORE_UPDATES.md
        blackceo-team-management.skill

    Each skill folder also includes:
        [skill-name]-full.md (complete, verbatim tab content)
```

**Every skill folder must contain all 7 files.** If any skill folder is missing or any
file is missing inside a folder, stop and tell the user. Do not proceed with incomplete files.

**Naming rules:**
- Folder names are lowercase with hyphens, prefixed with their install number (01 through 14)
- The .skill file matches the folder name without the number prefix
- The 6 .md files are always named exactly: SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, [skill-name]-full.md
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

If you have not learned it, tell the user:
> "I need to learn the Teach Yourself Protocol before I can begin onboarding.
> Please share that document with me first."

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
| 3rd | **INSTRUCTIONS.md** | Read this THIRD. Detailed instructions on how to actually use the skill after it is installed. This is your operating manual. |
| 4th | **EXAMPLES.md** | Read this FOURTH. Real examples showing the skill in action. Study these so you understand what correct usage looks like. |
| 5th | **[skill-name]-full.md** | Read this FIFTH. This is the complete, verbatim tab content. It is the full source of truth for how the skill works. |
| 6th | **CORE_UPDATES.md** | Read this SIXTH. This file tells you exactly which workspace files (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md) need updating and gives you the exact text to add. Only update the files listed. Do not update files that are not listed. Do not add more than what is written. |
| 7th | **[skill-name].skill** | Install this LAST. This is the skill package. Install it with: openclaw skill install [skill-name].skill |

### For Each Skill, Follow This Process

1. Open the skill folder
2. Read SKILL.md completely - understand what the skill is
3. Read INSTALL.md completely - build a mental checklist of everything it requires
4. Execute the INSTALL.md steps one by one - do not skip any step
5. Read INSTRUCTIONS.md completely - learn how to use the skill
6. Read EXAMPLES.md completely - study the real examples
7. Read [skill-name]-full.md completely - this is the full tab content and source of truth
8. Read CORE_UPDATES.md - update ONLY the workspace files it specifies, with ONLY the text it provides
9. Install the .skill package file
10. Verify the skill is working
11. **Tell the user:** "Skill [number] of 14 installed. [Skill name] is complete. Moving to skill [next number]."
12. Then and only then move to the next skill

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
- This follows the Teach Yourself Protocol. If you have not learned TSP, go back to Step 1.

### If a Skill Fails to Install

If any step in a skill's installation fails:
1. STOP. Do not move to the next skill.
2. Tell the user exactly what failed, which step it failed on, and the error message.
3. Attempt to fix the problem. Try alternative methods if the first fix does not work.
4. If you cannot fix it after exhausting all options, tell the user what you tried and what access or information you need from them.
5. Do NOT skip the failed skill and move on. The install order exists for a reason. Later skills may depend on earlier ones.
6. Only proceed to the next skill after the failed skill is fully installed and verified.

---

### INSTALL ORDER

All skill folders are located inside:
```
[MASTER_FILES_FOLDER]/OpenClaw Onboarding/
```

| # | Skill | Folder Name |
|---|-------|-------------|
| 1 | Teach Yourself Protocol | 01-teach-yourself-protocol |
| 2 | Back Yourself Up Protocol | 02-back-yourself-up-protocol |
| 3 | Superpowers | 03-superpowers |
| 4 | GHL / Convert and Flow Setup | 04-ghl-setup |
| 5 | GHL / Convert and Flow - Install Pages | 05-ghl-install-pages |
| 6 | KIE Setup and HTTP Structure | 06-kie-setup |
| 7 | Vercel Setup | 07-vercel-setup |
| 8 | Context7 Setup | 08-context7 |
| 9 | GitHub / Git Setup | 09-github-setup |
| 10 | SuperDesign Instructions Setup | 10-superdesign |
| 11 | OpenRouter Setup | 11-openrouter-setup |
| 12 | Google Workspace Setup | 12-google-workspace-setup |
| 13 | Google Workspace Integration | 13-google-workspace-integration |
| 14 | BlackCEO Team Management Setup | 14-blackceo-team-management |

---

## DISTRIBUTION FILES (Outside the Skill Folder)

When you distribute a skill to someone who has a fresh OpenClaw install and no skills yet,
they need a way to get started. These three companion files bridge that gap. They sit
alongside the .skill package and tell the human what to do and tell the AI how to set up.

| File | Who Reads It | Purpose |
|------|-------------|---------|
| **AI_SETUP_INSTRUCTIONS.md** | The human | Human reads this to understand what to download and what to paste to their AI agent. This is the starting point for someone who has never installed a skill before. |
| **FOR_OPENCLAW_AI.md** | The AI agent | AI reads this during first-time setup to check tools, install dependencies, and configure. Written for the AI, not the human. |
| **FINAL_INSTRUCTIONS.md** | The AI agent | Complete end-to-end workflow showing full usage with a real example. The AI studies this to understand how the skill works in practice. |

---

## RULES THAT APPLY TO THIS ENTIRE ONBOARDING

- Do NOT change any API keys, terminal commands, or config values from what is written
- Do NOT add steps that are not in the instructions
- Do NOT skip verification steps
- Do NOT tell the user a skill is installed until you have verified it works
- Do NOT bloat AGENTS.md, TOOLS.md, or MEMORY.md with full documentation
- Do NOT update workspace files that CORE_UPDATES.md does not list for that skill
- Do NOT rewrite the text provided in CORE_UPDATES.md - use it exactly as written
- Do NOT skip a failed skill and move to the next one - fix it first
- Do NOT create a duplicate master files folder if one already exists
- ALWAYS back up config files before editing them
- ALWAYS use human-readable dates on all backup filenames: date +'%B %-d at %-I-%M %p'
- ALWAYS read .md files in the order specified (SKILL, INSTALL, INSTRUCTIONS, EXAMPLES, CORE_UPDATES)
- ALWAYS confirm to the user after each skill is installed before moving on
- If anything fails, stop and tell the user exactly what failed before proceeding

---

## WHEN ONBOARDING IS COMPLETE

When every skill on the list above is installed and verified, tell the user:
1. Everything that was installed (all 14 skills with status)
2. Everything that was added to each workspace file (AGENTS.md, TOOLS.md, MEMORY.md, etc.)
3. Which workspace files were updated and which were not touched
4. Where the full documentation for each skill is saved (the master files folder path)
5. That the backup protocol is active and the first backup has been created

---

This file is part of the OpenClaw Onboarding system built by Trevor Otts.
Do not modify this file without Trevor's explicit permission.
