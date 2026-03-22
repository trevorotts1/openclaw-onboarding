# Skill 33: Permanent Department Heads

## What This Skill Does

This skill installs **17 permanent department head agents** into your OpenClaw installation. Each department head is a dedicated agent with its own identity, workspace, and responsibilities. They live inside `agents.list[]` in `~/.openclaw/openclaw.json`, which means they survive restarts, context resets, and gateway reconnects.

## The 17 Departments

| # | Department ID | Director Role | Model |
|---|---------------|---------------|-------|
| 1 | dept-ceo | Chief Executive Officer | Kimi K2.5 |
| 2 | dept-marketing | Marketing Director | Kimi K2.5 |
| 3 | dept-sales | Sales Director | GPT-5.4 |
| 4 | dept-billing | Finance Director | Kimi K2.5 |
| 5 | dept-support | Support Director | Kimi K2.5 |
| 6 | dept-operations | Operations Director | Claude Sonnet 4.6 |
| 7 | dept-creative | Creative Director | Kimi K2.5 |
| 8 | dept-hr | HR Director | Kimi K2.5 |
| 9 | dept-legal | Legal Director | Claude Sonnet 4.6 |
| 10 | dept-it | IT Director | GPT-5.4 |
| 11 | dept-webdev | Web Development Director | GPT-5.4 |
| 12 | dept-appdev | App Development Director | GPT-5.4 |
| 13 | dept-graphics | Graphics Director | Kimi K2.5 |
| 14 | dept-video | Video Director | Kimi K2.5 |
| 15 | dept-audio | Audio Director | Kimi K2.5 |
| 16 | dept-research | Research Director | Kimi K2.5 |
| 17 | dept-comms | Communications Director | Kimi K2.5 |

## How agents.list[] Works

Each department head is added as an entry in `~/.openclaw/openclaw.json` under `agents.list[]`. This is OpenClaw's permanent agent registry. Agents in this list:

- **Survive restarts** - They are loaded every time OpenClaw starts
- **Have unique IDs** - Each agent has a stable identifier (e.g., `dept-marketing`)
- **Have dedicated workspaces** - Each agent works in `~/clawd/departments/[dept]/`
- **Can be spawned on demand** - You can talk to any department head at any time
- **Remember their context** - Their SOUL.md and workspace files persist across sessions

## What Gets Created

### 1. Directory Structure
```
~/clawd/departments/
├── ceo/SOUL.md
├── marketing/SOUL.md
├── sales/SOUL.md
├── billing/SOUL.md
├── support/SOUL.md
├── operations/SOUL.md
├── creative/SOUL.md
├── hr/SOUL.md
├── legal/SOUL.md
├── it/SOUL.md
├── webdev/SOUL.md
├── appdev/SOUL.md
├── graphics/SOUL.md
├── video/SOUL.md
├── audio/SOUL.md
├── research/SOUL.md
└── comms/SOUL.md
```

### 2. Agent Configuration
17 entries added to `~/.openclaw/openclaw.json` under `agents.list[]`.

### 3. SOUL.md Files
Each department gets a SOUL.md defining its identity, role, responsibilities, and communication style.

## How to Use Department Heads

### Talk to a Department
```bash
sessions_spawn --agent dept-marketing --task "Create a campaign brief for Q2"
```

### Assign Work Through the CEO
```
User: "Launch a new product next month"
CEO Agent: Spawns Marketing, Sales, Creative directors with coordinated tasks
```

### Direct Department Queries
```
User: "What is the status of the website redesign?"
WebDev Director: "Currently 70% complete. Design phase done, development in progress."
```

## After Installation

1. Restart OpenClaw (`/restart` in Telegram)
2. Test each department head
3. Set department goals and KPIs
4. Create a weekly rhythm (Monday goals, Friday reviews)

## Prerequisites

| Prerequisite | Required | Why It Matters |
|--------------|----------|----------------|
| OpenClaw installed | MANDATORY | Agents are registered in openclaw.json |
| Python 3 | MANDATORY | install.sh uses Python to modify JSON config |
| ~/clawd/ directory | MANDATORY | Department workspaces live here |

## Troubleshooting

**Department head not responding?**
```bash
grep "dept-" ~/.openclaw/openclaw.json     # verify agent exists
ls ~/clawd/departments/[dept]/              # verify workspace exists
cat ~/clawd/departments/[dept]/SOUL.md      # verify SOUL.md exists
```

**Need to reset a department?**
```bash
rm -rf ~/clawd/departments/[dept]/
# Re-run install.sh - existing agents are skipped, files are recreated
```
