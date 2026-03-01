# Skill 14: BlackCEO Team Management

## What This Skill Is About

This skill sets up a system where multiple people can send messages to the same AI bot on Telegram, and each person gets their own dedicated worker running in the background. Instead of messages piling up and bleeding into each other, the main AI session acts as a "dispatcher" that routes each person's request to their own private worker sub-agent.

Think of it like a receptionist at a front desk. When Person A calls, the receptionist routes them to Assistant A. When Person B calls, they get routed to Assistant B. Each assistant only sees their own conversation. The receptionist (dispatcher) can see everything, but the assistants stay separate.

This is the BlackCEO team management protocol - built for Trevor's team but designed to be copied and customized for any client deployment.

## When to Use This Skill

- You are setting up OpenClaw to serve multiple team members through one Telegram bot
- You need to configure message routing so each person gets their own worker sub-agent
- You are adding new team members or clients to an existing dispatcher setup
- You need to create or update the WORKFLOW_AUTO.md routing table
- You are troubleshooting why messages are crossing between users or workers are not spawning
- You need to configure Telegram ID allowlists so new people can message the bot
- You are setting up model selection rules for different types of worker tasks
- You need to understand the difference between "worker" team members and "client" users

## What This Skill Covers

- The dispatcher/worker architecture and how it works step by step
- How to configure sub-agent settings in openclaw.json (max concurrent workers, archive timing, model selection)
- Adding Telegram IDs to the allowFrom list so the bot accepts messages from team members
- Creating the WORKFLOW_AUTO.md routing table that maps each person to their worker
- Worker lifecycle: how workers are created, stay active, go idle, get archived, and respawn
- Message isolation rules so one person's conversation never leaks into another person's worker
- Cross-worker communication through the dispatcher (when someone asks to share info between workers)
- Model selection for different task types (routine work vs. creative vs. complex reasoning)
- The difference between "worker" sub-agents (team members who give instructions) and "client" sub-agents (clients who are served, never assigned tasks)
- Scaling guidelines for teams of different sizes
- A complete WORKFLOW_AUTO.md template ready to copy and customize
- Deployment checklist for setting up a new client
- What to add to AGENTS.md, TOOLS.md, and MEMORY.md so the agent remembers team IDs across sessions

## Files in This Folder and Reading Order

1. **SKILL.md** - You are here. Start here for the overview.
2. **blackceo-team-management-full.md** - The complete protocol with all details. Read this to execute the setup.
3. **INSTRUCTIONS.md** - Execution instructions and rules for the AI agent.
4. **INSTALL.md** - Installation steps specific to this skill.
5. **EXAMPLES.md** - Example routing tables and spawn commands.
6. **CORE_UPDATES.md** - What to add to your core .md files (AGENTS.md, TOOLS.md, MEMORY.md).
7. **blackceo-team-management.skill** - Skill metadata file.

## Prerequisites

- All previous 13 onboarding skills must be installed
- An active Telegram bot connected to OpenClaw
- Telegram user IDs for every team member and client who will use the bot
- The Teach Yourself Protocol (TSP) must be learned first

## Key Things the AI Agent Must Know

1. **The main session is the dispatcher, not a worker.** It receives all incoming messages, looks up the sender's Telegram ID, and routes the task to the correct worker sub-agent. It does not do the work itself.

2. **Three BlackCEO team IDs are always present in every deployment.** Trevor Otts (5252140759), LeAnne (6663821679), and E.R. Spaulding (6771245262). These must be in the Telegram allowFrom list before anything else works.

3. **Workers stay alive between tasks.** When you spawn a worker with cleanup: keep, it stays active even after finishing a task. The next message from that same person goes to the existing worker instead of spawning a new one. Workers only archive after 30 days of inactivity.

4. **All workers are lost on gateway restart.** This is expected. The dispatcher automatically re-spawns each worker when that person sends their next message. No manual fix needed.

5. **Message isolation is strict by default.** Person A's results never go to Person B's chat. Cross-posting only happens when someone explicitly asks for it (like "send this update to LeAnne").

6. **WORKFLOW_AUTO.md is not read at boot.** It is a custom file, not a standard OpenClaw file. The critical team IDs must also be written to AGENTS.md and MEMORY.md so the agent remembers them every session.

7. **Client sub-agents are different from worker sub-agents.** Workers receive instructions and execute tasks. Clients are served respectfully - the AI never assigns them tasks or bosses them around. Mark clients clearly in the routing table.

8. **The sub-agent model must support tool calls.** Models that only do reasoning (no tool calls) will fail silently as workers. Use MiniMax M2.5, Codex, or Sonnet as defaults.
