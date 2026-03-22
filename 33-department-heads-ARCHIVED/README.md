# Skill 33: Permanent Department Heads

## What This Skill Does

This skill establishes **17 permanent department head agents** as first-class citizens in your OpenClaw installation. Each department head is a dedicated agent with its own identity, workspace, and responsibilities.

## The 17 Departments

| Department | Director Role | Model |
|------------|---------------|-------|
| CEO | Chief Executive Officer | Kimi K2.5 |
| Marketing | Marketing Director | Kimi K2.5 |
| Sales | Sales Director | GPT-5.4 |
| Billing | Finance Director | Kimi K2.5 |
| Support | Support Director | Kimi K2.5 |
| Operations | Operations Director | Claude Sonnet 4.6 |
| Creative | Creative Director | Kimi K2.5 |
| HR | HR Director | Kimi K2.5 |
| Legal | Legal Director | Claude Sonnet 4.6 |
| IT | IT Director | GPT-5.4 |
| WebDev | Web Development Director | GPT-5.4 |
| AppDev | App Development Director | GPT-5.4 |
| Graphics | Graphics Director | Kimi K2.5 |
| Video | Video Director | Kimi K2.5 |
| Audio | Audio Director | Kimi K2.5 |
| Research | Research Director | Kimi K2.5 |
| Comms | Communications Director | Kimi K2.5 |

## Why Department Heads Need to Be Permanent Agents

### 1. **Persistent Identity**
Department heads maintain consistent personality, memory, and context across sessions. Unlike temporary task agents, they remember your company's history, KPIs, and ongoing projects.

### 2. **Dedicated Workspaces**
Each department head has its own workspace (`~/clawd/departments/[dept]/`) with:
- `SOUL.md` - Identity and role definition
- `MEMORY.md` - Department-specific memory
- `AGENTS.md` - Department workflows and SOPs
- `TOOLS.md` - Department tool configurations

### 3. **Chain of Command**
Department heads form the backbone of your AI company's organizational structure:
- **Trevor** (Human CEO) → CEO Director
- **CEO Director** → Department Directors
- **Department Directors** → Specialist Task Agents

### 4. **Accountability**
Each department head owns their metrics and reports weekly. This creates clear accountability loops and ensures nothing falls through the cracks.

### 5. **Scalable Delegation**
With permanent department heads, you can:
- Assign work to a department and let the director delegate
- Request status updates from specific departments
- Escalate issues up the chain of command
- Coordinate cross-department projects

## What Gets Created

### Directory Structure
```
~/clawd/departments/
├── ceo/
│   └── SOUL.md
├── marketing/
│   └── SOUL.md
├── sales/
│   └── SOUL.md
├── billing/
│   └── SOUL.md
├── support/
│   └── SOUL.md
├── operations/
│   └── SOUL.md
├── creative/
│   └── SOUL.md
├── hr/
│   └── SOUL.md
├── legal/
│   └── SOUL.md
├── it/
│   └── SOUL.md
├── webdev/
│   └── SOUL.md
├── appdev/
│   └── SOUL.md
├── graphics/
│   └── SOUL.md
├── video/
│   └── SOUL.md
├── audio/
│   └── SOUL.md
├── research/
│   └── SOUL.md
└── comms/
    └── SOUL.md
```

### Agent Configuration
17 new entries added to `~/.openclaw/openclaw.json` under `agents.list`:
- `dept-ceo` - CEO Director
- `dept-marketing` - Marketing Director
- `dept-sales` - Sales Director
- `dept-billing` - Finance Director
- `dept-support` - Support Director
- `dept-operations` - Operations Director
- `dept-creative` - Creative Director
- `dept-hr` - HR Director
- `dept-legal` - Legal Director
- `dept-it` - IT Director
- `dept-webdev` - Web Development Director
- `dept-appdev` - App Development Director
- `dept-graphics` - Graphics Director
- `dept-video` - Video Director
- `dept-audio` - Audio Director
- `dept-research` - Research Director
- `dept-comms` - Communications Director

## How to Use Department Heads

### Spawn a Department Head
```bash
# Talk to the Marketing Director
sessions_spawn --agent dept-marketing --task "Create a campaign brief for Q2"

# Get a status report from Sales
sessions_spawn --agent dept-sales --task "Generate weekly pipeline report"
```

### Assign Work Through the CEO
```
User: "Launch a new product next month"
CEO Agent: Spawns Marketing, Sales, Creative directors with coordinated tasks
```

### Direct Department Queries
```
User: "What's the status of the website redesign?"
WebDev Director: "Currently 70% complete. Design phase done, development in progress."
```

## After Installation

1. **Restart OpenClaw** - Type `/restart` in Telegram to apply agent changes
2. **Test each department** - Spawn a department head to verify it works
3. **Set department goals** - Work with each director to establish KPIs
4. **Create weekly rhythm** - Schedule Monday goal-setting and Friday reviews

## Integration with Other Skills

- **Skill 22 (Book-to-Persona)**: Department heads can leverage persona blueprints for coaching
- **Skill 23 (AI Workforce Blueprint)**: Department heads manage the workforce structure
- **Skill 31 (Upgraded Memory)**: Department heads use the 5-layer memory system
- **All Other Skills**: Department heads can spawn sub-agents using any installed skill

## Maintenance

Department heads are permanent agents. They persist across:
- OpenClaw restarts
- Model switches
- Context window resets
- Gateway reconnections

Their workspaces (`~/clawd/departments/`) should be backed up regularly as part of your standard backup protocol.

## Troubleshooting

**Department head not responding?**
- Check agent exists: `grep "dept-" ~/.openclaw/openclaw.json`
- Verify workspace exists: `ls ~/clawd/departments/[dept]/`
- Check SOUL.md exists: `cat ~/clawd/departments/[dept]/SOUL.md`
- Restart OpenClaw: Type `/restart` in Telegram

**Need to reset a department head?**
- Delete the department folder: `rm -rf ~/clawd/departments/[dept]/`
- Re-run this skill's install.sh
- The agent entry will be skipped (already exists), files will be recreated
