# Teach Yourself Protocol - Installation

## Prerequisites
- OpenClaw installed and running (`openclaw status`)
- Write access to workspace files (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md)
- ~/Downloads/ folder accessible

## Step 1: Find or Create the Master Files Folder

Search ~/Downloads/ for an existing master files folder. Check these names:
- openclaw-master-files
- openclaw-master-docs
- OpenClaw Master Files
- master-files

If found, use it. Do NOT create a duplicate.

If not found:
```bash
mkdir -p ~/Downloads/openclaw-master-files/
```

Create subfolders:
```bash
mkdir -p ~/Downloads/[MASTER_FILES_FOLDER]/apis/
mkdir -p ~/Downloads/[MASTER_FILES_FOLDER]/skills/
mkdir -p ~/Downloads/[MASTER_FILES_FOLDER]/processes/
mkdir -p ~/Downloads/[MASTER_FILES_FOLDER]/references/
```

## Step 2: Place the Skill Files

Copy this entire `01-teach-yourself-protocol/` folder into the master files folder.
All files stay together:
- SKILL.md
- INSTALL.md (this file)
- INSTRUCTIONS.md
- EXAMPLES.md
- CORE_UPDATES.md
- teach-yourself-protocol-full.md (complete protocol - all 19 sections)
- teach-yourself-protocol.skill

## Step 3: Install the Skill Package

```bash
openclaw skill install teach-yourself-protocol.skill
```

## Step 4: Read the Full Protocol

Read teach-yourself-protocol-full.md completely. This contains:
- The three-layer knowledge architecture (core summaries, deep files, folder structures)
- The decision tree (understand, assess size, check conflicts, create files, write summaries)
- Trigger recognition (explicit and implicit)
- Conflict resolution procedures
- Priority tagging system
- The Five Question Test for lightweight summaries
- Staleness detection rules
- 19 common mistakes to avoid

## Step 5: Update Core Workspace Files

Follow CORE_UPDATES.md exactly. It tells you which files to update and provides the exact text.

## Step 6: Verify Installation

Ask the agent these questions. It must answer all correctly:

1. "What is the Teach Yourself Protocol?"
   Expected: Structured learning protocol with three layers - core summaries, deep files, folder structures

2. "Where do full documents go?"
   Expected: Master files folder (not core workspace files)

3. "What goes in AGENTS.md or TOOLS.md?"
   Expected: Lightweight summaries (10-25 lines) with file path references

4. "What triggers TYP?"
   Expected: Explicit ("teach yourself this") and implicit (large documents, corrections, preferences)

5. "What do you do before creating any new knowledge files?"
   Expected: Search existing core files and master files folder for existing knowledge first

If the agent cannot answer any of these, re-read the full protocol document.
