# Skill 33: Permanent Department Heads - Installation Guide

## Overview

This skill creates 17 permanent department head agents, each with its own workspace and SOUL.md. The install process has 4 steps and takes about 30 seconds.

---

## Prerequisites

Before running, make sure you have:

| Check | Command | Expected |
|-------|---------|----------|
| Python 3 | `python3 --version` | 3.6 or higher |
| OpenClaw config | `ls ~/.openclaw/openclaw.json` | File exists |
| ~/clawd directory | `ls ~/clawd/` | Directory exists |

---

## What install.sh Does

### Step 1: Create Departments Directory
Creates `~/clawd/departments/` if it does not exist.

### Step 2: Create 17 Department Subdirectories with SOUL.md
For each of the 17 departments, the script:
- Creates a subdirectory under `~/clawd/departments/` (e.g., `~/clawd/departments/marketing/`)
- Writes a `SOUL.md` file with the department's identity, role, responsibilities, and communication style
- Assigns a model to each department (Kimi K2.5, GPT-5.4, or Claude Sonnet 4.6 depending on the role)

### Step 3: Add 17 Agents to openclaw.json
Runs a Python script that:
- Reads `~/.openclaw/openclaw.json`
- Checks for existing agent IDs (skips duplicates)
- Adds each department head agent to the `agents.list[]` array
- Saves the updated config

Each agent entry includes:
- `id` - Unique identifier (e.g., `dept-marketing`)
- `name` - Display name (e.g., `Marketing Director`)
- `workspace` - Path to department folder (e.g., `~/clawd/departments/marketing`)
- `model` - AI model assigned to this department

### Step 4: Verify Installation
Checks that each department has its SOUL.md file and reports any missing files.

---

## Running the Install

```bash
cd ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/33-department-heads/
bash install.sh
```

---

## Verification Steps

### 1. Check Department Directories
```bash
ls ~/clawd/departments/
```
Expected: 17 subdirectories (ceo, marketing, sales, billing, support, operations, creative, hr, legal, it, webdev, appdev, graphics, video, audio, research, comms)

### 2. Check SOUL.md Files
```bash
for d in ~/clawd/departments/*/; do
  echo -n "$d: "
  [ -f "$d/SOUL.md" ] && echo "OK" || echo "MISSING"
done
```
Expected: All 17 show "OK"

### 3. Check Agent Entries in Config
```bash
python3 -c "
import json
with open('$HOME/.openclaw/openclaw.json') as f:
    config = json.load(f)
agents = [a['id'] for a in config.get('agents',{}).get('list',[]) if a['id'].startswith('dept-')]
print(f'{len(agents)} department head agents found:')
for a in sorted(agents): print(f'  - {a}')
"
```
Expected: 17 department head agents listed

### 4. Restart OpenClaw
Type `/restart` in Telegram to apply the new agent entries.

### 5. Test a Department Head
After restart, try spawning a department head to confirm it works.

---

## Troubleshooting

**"No module named json" error?**
Python 3 is required. Check with `python3 --version`.

**Agents already exist?**
The script skips duplicate agent IDs. This is safe to re-run.

**Missing SOUL.md files?**
Re-run the script. Step 2 will recreate any missing SOUL.md files.

**Want to start fresh?**
```bash
rm -rf ~/clawd/departments/
# Then re-run install.sh
```
Note: You will also need to manually remove the agent entries from `~/.openclaw/openclaw.json` if you want a clean slate.
