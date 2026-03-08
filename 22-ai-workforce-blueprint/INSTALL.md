# Installing the AI Workforce Blueprint Skill

## STEP 0 - TSP PREREQUISITE CHECK (Do This Before Anything Else)

**Before installing this skill, the agent must have already learned Skill 01: Teach Yourself Protocol.**

Check now:
```
Search AGENTS.md and MEMORY.md for: "Teach Yourself Protocol" or "TSP"
```

**If TSP IS found in your core files:** Proceed to Step 1.

**If TSP is NOT found:** STOP immediately. Tell the user:

> "Before we can install this skill, you need to complete Skill 01 - Teach Yourself Protocol first.
> Download it from: https://github.com/trevorotts1/openclaw-onboarding (folder: 01-teach-yourself-protocol)
> Tell your AI to read SKILL.md in that folder and complete the full TSP installation.
> Come back to this skill after that is done."

Do NOT proceed with this installation until TSP is confirmed installed.

---

## Step 1 - Activate TSP on This Skill Folder

Run the Teach Yourself Protocol on this skill folder now. Read every .md file in this order:

1. SKILL.md (already read if you are here)
2. ai-workforce-blueprint-full.md (the full 66,819-character blueprint - read it completely)
3. INSTRUCTIONS.md
4. EXAMPLES.md
5. CORE_UPDATES.md
6. INSTALL.md (this file - you are reading it now)

**Announce to the user after each file:** "Read [filename]. Moving to next."
**Do not proceed to Step 2 until all 6 files are confirmed read.**
After all reads: announce "TSP complete for AI Workforce Blueprint skill. Proceeding with installation."

---

## Prerequisites
- OpenClaw installed and running
- A workspace folder (e.g., `~/Downloads/my-ai-workforce/` or wherever your business files live)
- Python 3.8+ (for the automated scaffold script)

## Installation Steps

### Step 1 - Download the skill
```bash
curl -L https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip -o ~/Downloads/openclaw-onboarding.zip
unzip ~/Downloads/openclaw-onboarding.zip -d ~/Downloads/
```

### Step 2 - Copy skill to your skills folder
```bash
cp -r ~/Downloads/openclaw-onboarding-main/22-ai-workforce-blueprint ~/.openclaw/skills/
```

### Step 3 - Tell your AI to read the skill
Say to your AI: "Read the AI Workforce Blueprint skill at ~/.openclaw/skills/22-ai-workforce-blueprint/SKILL.md"

### Step 4 - Start your workforce build
Say to your AI: "Build my AI workforce. Use Option A."

Your AI will ask you questions about your business and create the full folder structure.

### Step 5 - Set Up Weekly Auto-Update (Agent Handles This)

Run this now - agent executes it, human does nothing:

```bash
mkdir -p ~/.openclaw/skills/scripts
curl -s https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/setup-weekly-update.sh -o ~/.openclaw/skills/scripts/setup-weekly-update.sh
chmod +x ~/.openclaw/skills/scripts/setup-weekly-update.sh
bash ~/.openclaw/skills/scripts/setup-weekly-update.sh
```

**Verify:**
```bash
crontab -l | grep update-skills
```

This installs a cron that runs every Sunday at 2:00 AM - checks GitHub, applies updates to installed skills, sends Telegram notification with changelog. Runs automatically forever. Human never has to touch it.

---

## What Happens After Install
- Your AI knows the full blueprint system and can build or audit department structures
- You can say "add a new department" at any time and the AI knows exactly what files to create
- The skill works standalone - no personas or other skills required

## To Add a New Department Later
Just say: "Add a [department name] department to my workforce structure."
Your AI will create the folder, role subfolders, and all required files.
