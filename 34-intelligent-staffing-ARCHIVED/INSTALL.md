# Skill 34: Intelligent Workspace Staffing - Installation Guide

## Prerequisites

Before installing Skill 34, make sure the following are already set up:

1. **OpenClaw installed and running** on the target machine
2. **Skill 33 (Department Heads)** already installed - this creates the 17 department directories that Skill 34 builds on
3. **Python 3** available on the system (for JSON parsing and the interactive interview)
4. **Bash shell** available (macOS Terminal or Linux shell)

## What This Skill Does

Skill 34 interviews you about your business operations and creates specialist AI agents based on your answers. It asks 6 questions per department (102 total) and uses a decision matrix to determine which specialist roles should be permanent agents with persistent memory vs temporary sub-agents.

## Installation Steps

### Step 1: Navigate to the Skill Directory

```bash
cd ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/34-intelligent-staffing/
```

### Step 2: Run the Installer

```bash
bash install.sh
```

### Step 3: Answer the Interview Questions

The installer will present 6 questions per department. For each question, answer:

- **yes** (or **y**) - This function is active in your business
- **no** (or **n**) - Skip this function

The interview covers all 17 departments:
1. Marketing
2. Sales
3. Billing/Finance
4. Customer Support
5. Operations
6. Creative
7. HR/People
8. Legal/Compliance
9. IT/Tech
10. Web Development
11. App Development
12. Graphics
13. Video
14. Audio
15. Research
16. Communications
17. CEO/Executive

### Step 4: Review the Summary

After answering all questions, the installer shows:
- How many permanent specialists will be created
- How many sub-agent templates will be created
- How many roles were skipped

### Step 5: Restart OpenClaw

After installation completes, restart to apply the new agents:

```
Type /restart in Telegram
```

## What Gets Created

### Permanent Specialist Workspaces

For each "yes" answer to a permanent-type question:

```
~/clawd/departments/[department]/specialists/[specialist-name]/
  SOUL.md      - Identity, purpose, operating rhythm, boundaries
  MEMORY.md    - Long-term memory scaffold
  AGENTS.md    - Behavior rules
```

Example:
```
~/clawd/departments/marketing/specialists/social-media-manager/
  SOUL.md
  MEMORY.md
  AGENTS.md
```

### Sub-Agent Templates

For each "yes" answer to a subagent-type question:

```
~/clawd/subagents/templates/[role-name]/
  SOUL.md      - Task template (no persistent memory)
```

Example:
```
~/clawd/subagents/templates/creative-producer/
  SOUL.md
```

### openclaw.json Updates

Each permanent specialist gets added to `~/.openclaw/openclaw.json` as an agent entry:

```json
{
  "id": "spec-social-media-manager",
  "name": "Social Media Manager",
  "model": "moonshot/kimi-k2.5",
  "system": "file://~/clawd/departments/marketing/specialists/social-media-manager/SOUL.md",
  "workspace": "~/clawd/departments/marketing/specialists/social-media-manager",
  "parent": "dept-marketing"
}
```

## The Decision Matrix

The installer uses this logic to decide permanent vs sub-agent:

| Condition | Agent Type |
|-----------|-----------|
| Task runs daily, weekly, or monthly AND needs memory of past work | Permanent agent |
| Task is one-time, occasional, or batch processing | Sub-agent (template only) |
| Client-facing ongoing relationship | Permanent agent |

## Questions Reference

The full list of 102 questions is in `questions.json` in this directory. Each question includes:
- The question text
- The specialist role it maps to
- Whether the role is permanent or sub-agent
- The recommended AI model

## Troubleshooting

### "questions.json not found"
Make sure you are running `install.sh` from inside the `34-intelligent-staffing/` directory.

### "Skill 33 not installed"
Run Skill 33 first:
```bash
cd ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/33-department-heads/
bash install.sh
```

Then re-run Skill 34.

### "python3 not found"
Install Python 3:
```bash
# macOS (with Homebrew)
brew install python3

# Ubuntu/Debian
sudo apt install python3
```

### Agents not showing up after install
Restart OpenClaw:
```
Type /restart in Telegram
```

### Re-running the installer
The installer is safe to re-run. It skips any agents that already exist (no duplicates). If you want to add specialists you previously skipped, just answer "yes" to those questions on the next run.

## File Inventory

```
34-intelligent-staffing/
  install.sh                          - Main installer script
  questions.json                      - 102 interview questions (6 x 17 departments)
  SKILL.md                            - Skill description
  INSTALL.md                          - This file
  specialist-templates/
    SOUL-template.md                  - Generic SOUL.md template
    social-media-manager.md           - Social Media Manager SOUL.md
    email-marketing-specialist.md     - Email Marketing Specialist SOUL.md
    crm-specialist.md                 - CRM Specialist SOUL.md
    paid-ads-specialist.md            - Paid Ads Specialist SOUL.md
    lead-nurturing-specialist.md      - Lead Nurturing Specialist SOUL.md
    support-ticket-agent.md           - Support Ticket Agent SOUL.md
    operations-coordinator.md         - Operations Coordinator SOUL.md
```

## After Installation

Your AI workforce now has three layers:

1. **Department Heads** (Skill 33) - 17 permanent department directors
2. **Permanent Specialists** (Skill 34) - Recurring-function agents with persistent memory
3. **Sub-Agent Templates** (Skill 34) - Ready-to-spawn templates for one-time tasks

Each specialist reports to its department director. Department directors report to the CEO. The hierarchy is:

```
CEO Director
  -> Department Directors (17)
       -> Permanent Specialists (based on your answers)
       -> Sub-Agent Templates (available on demand)
```
