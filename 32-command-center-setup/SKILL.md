# Skill 32: Command Center Setup

## What This Skill Is About

The Command Center Setup activates your AI workforce as a live, operational system. It takes the department structure you created in Skill 23 (AI Workforce Blueprint) and makes it real with persistent department agents, a Telegram control room with organized topics, and a visual Kanban dashboard for task management.

Think of Skill 23 as the blueprint phase. This is the construction phase.

## When to Use This Skill

Use this skill when:
- You have completed Skill 23 (AI Workforce Blueprint) and have department folders created
- You want to activate your AI workforce with live department heads
- You need a centralized control room to manage all departments
- You want persistent agents that remember conversations and tasks
- You need a visual dashboard to track work across all departments

## Prerequisites

| Prerequisite | Required | Why It Matters |
|--------------|----------|----------------|
| Skill 23: AI Workforce Blueprint | MANDATORY | This skill builds on the department structure created in Skill 23. Without it, there are no departments to activate. |
| Skill 22: Book-to-Persona | Recommended | Department heads use personas from your coaching system. Without them, heads will be generic. |
| Skill 31: Upgraded Memory System | Recommended | Department heads need the 8-layer memory system for persistent operation. |
| Memory Wiki | Recommended | Department heads use wiki_search and wiki_get for structured knowledge retrieval across coaching theories and SOPs. |

### Active Memory Note
This skill requires an active memory system. Department agents maintain persistent state using:
- **Session Memory**: Conversation context within each department topic
- **Semantic Memory**: memory-core for long-term fact retrieval
- **Structured Memory**: Memory Wiki for coaching theories and SOPs

Before activating, verify memory is working: `openclaw memory status`

## What Gets Created

### 1. Persistent Department Agents
Each department gets its own persistent agent:
- Unique identity and role definition
- Dedicated workspace with memory system
- Direct binding to Telegram topics
- No sandboxing (full tool access for department work)

### 2. Telegram Command Center
A Telegram group with topics for each department:
- One topic per department (e.g., "Marketing", "Sales", "Operations")
- Cross-Department topic for interdepartmental work
- Each topic bound to its department agent
- Bot promoted to admin with topic management permissions

### 3. Visual Kanban Dashboard
A web dashboard accessible at localhost:4000:
- All departments visible at a glance
- 5 Kanban columns: Backlog, Ready, In Progress, Review, Complete
- Task creation and assignment
- Real-time updates
- Persona pills showing which coaching blueprint each agent is using

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Overview and context.
2. **INSTALL.md** - Step-by-step installation process.
3. **INSTRUCTIONS.md** - How to use the Command Center after installation.
4. **CORE_UPDATES.md** - Exact additions for MEMORY.md, TOOLS.md, and HEARTBEAT.md.
5. **command-center-setup.skill** - Skill metadata file.

## How Department Heads Work

Once activated, each department head:
- Responds to messages in their dedicated Telegram topic
- Can spin up worker agents for specific tasks
- Assigns personas to workers based on task type
- Maintains memory of ongoing work and decisions
- Reports status and escalates when needed

## Standup Cadence

The Command Center operates on a 3-check rhythm:

**Morning Check-In (9 AM)**
- Department heads review overnight activity
- Prioritize today's work
- Identify blockers

**Midday Sync (1 PM)**
- Progress updates
- Cross-department coordination
- Resource reallocation if needed

**End of Day Report (5 PM)**
- Completed work summary
- Tomorrow's priorities
- Escalations for your review

## Security Note

Department agents do NOT run in sandboxes. They have full tool access to accomplish their work. This is by design. Trust your department heads like you would trust human department heads.

## Verification Checklist

After installation, verify:
- [ ] Telegram group created with topics enabled
- [ ] One topic exists for each department
- [ ] Cross-Department topic exists
- [ ] Bot is admin with topic management permissions
- [ ] Department workspaces created at ~/.openclaw/workspaces/command-center/
- [ ] Each department has IDENTITY.md, MEMORY.md, and memory/ folder
- [ ] Agent config entries added for each department
- [ ] Telegram bindings configured for each topic
- [ ] Dashboard accessible at localhost:4000
- [ ] Dashboard shows all departments and 5 Kanban columns
- [ ] Test message in one topic gets response from correct department head

## Troubleshooting

**Issue: Topics not appearing in Telegram**
- Verify bot is admin with "Manage Topics" permission
- Check that group was converted to supergroup (topics enabled)

**Issue: Department agents not responding**
- Check `openclaw config validate` for errors
- Verify agent workspace paths are absolute, not tilde paths
- Check that topic bindings use correct topic IDs

**Issue: Dashboard not loading**
- Verify PM2 process is running: `pm2 list`
- Check logs: `pm2 logs command-center`
- Ensure port 4000 is not in use by another service

## Support

For issues or questions about the Command Center Setup, refer to:
- INSTRUCTIONS.md for usage guidance
- CORE_UPDATES.md for configuration details
- The main OpenClaw documentation at https://docs.openclaw.ai

---
<!-- BREADCRUMB: skill-32-mac | 2026-04-12 | v6.5.7 | SKILL.md updated with wiki capability and Active Memory note | Memory Surgery Playbook v3.5 -->
