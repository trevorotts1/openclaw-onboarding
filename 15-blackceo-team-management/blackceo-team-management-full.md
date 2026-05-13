
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask the operator. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════
Team Management Protocol - Dispatcher Sub-Agent Routing SOP

Version: 1.0
Created: 2026-02-25
Author: Coach Trev (OpenClaw AI)
Organization: BLACK CEO
Applies to: Any OpenClaw deployment serving multiple operators via Telegram (or other messaging channels)


Team Configuration



Usage Note
When deploying this protocol for a new client:
Copy this SOP
Keep the team member IDs above as the management operators
Add the client's team members and their Telegram IDs to the routing table
The client principal (e.g., the business owner) gets a client-worker designation - never assigned tasks, always served respectfully


1) Problem This Solves

When multiple people send tasks to the same AI assistant through the same Telegram bot, messages stack up sequentially. Person A waits while Person B's task runs. Commands bleed across conversations. Context gets polluted. Response times tank.

This SOP eliminates that by turning the main AI session into a dispatcher that routes work to dedicated per-person worker sub-agents running in parallel.


2) Architecture Overview

[Telegram DMs]     │     ├── Person A (ID: xxx) ──► Main Session (Dispatcher) ──► person-a-worker (sub-agent)     ├── Person B (ID: yyy) ──► Main Session (Dispatcher) ──► person-b-worker (sub-agent)     ├── Person C (ID: zzz) ──► Main Session (Dispatcher) ──► person-c-worker (sub-agent)     └── Client (ID: www)   ──► Main Session (Dispatcher) ──► client-worker (sub-agent)


Key Roles




3) How It Works (Step by Step)

Message Arrives
Dispatcher receives incoming message
Identifies sender by their unique messaging ID (e.g., Telegram user ID)
Looks up the routing table to find the correct worker label

Task Routing
Checks if that worker's session already exists and is active
If active: sends the task to the existing worker via sessions_send
If not active: spawns a new worker with sessions_spawn using the correct label, model, and cleanup: keep

Result Delivery
Worker completes the task
Dispatcher relays the result back only to the sender's DM
Worker results go only to the requesting DM by default. Workers CAN send directed messages to any Telegram ID when explicitly asked.


4) Setup Checklist

Step 1: Configure Sub-Agent Settings

In ~/.openclaw/openclaw.json, set:

{  "agents": {    "defaults": {      "subagents": {        "maxConcurrent": 8,        "maxChildrenPerAgent": 5,        "archiveAfterMinutes": 43200,        "model": {          "primary": "your-preferred-model",          "fallbacks": [            "fallback-model-1",            "fallback-model-2"          ]        }      }    }  }}


Key settings explained:



Step 1B: Approve Team Telegram IDs (MANDATORY - First Thing)

Before anything else works, every team member's Telegram ID must be in the bot's allowFrom list so they can message the AI directly.

In ~/.openclaw/openclaw.json, add all team IDs (collected during Step 0 intake) to channels.telegram.allowFrom:

{  "channels": {    "telegram": {      "allowFrom": [        "[TEAM_MEMBER_1_ID]",        "[TEAM_MEMBER_2_ID]",        "[TEAM_MEMBER_3_ID]"      ]    }  }}


Replace placeholders with actual Telegram IDs collected during the Step 0 intake process.

Why this matters: If an ID is not in allowFrom, the bot ignores their messages completely. The AI agent should add all collected team IDs during setup.

Automation instruction for the AI agent:
When setting up a new client deployment using this protocol, the AI agent must:
Run the Step 0 intake to collect all team member names, IDs, roles, and types
Read the current channels.telegram.allowFrom array
Add all collected team member IDs
Back up config, validate JSON, restart gateway
Confirm all IDs are approved before proceeding with any other setup

Step 2: Create the Routing Table

Create a WORKFLOW_AUTO.md file in your workspace with:

## Routing Table| Sender ID | Name | Role | Worker Label | Reply To ||---|---|---|---|---|| 1234567890 | Person A | Role description | person-a-worker | 1234567890 || 0987654321 | Person B | Role description | person-b-worker | 0987654321 || 1111111111 | Client X | Client (not a worker) | client-x-worker | 1111111111 |


Step 3: Define Reply Rules

Add to the same file:

## Reply Rules- Worker results go ONLY to the requesting DM by default- Directed sends are always allowed: if sender says 'send [person] a message,' execute it- No context contamination: one worker's conversation data never appears in another- Tag replies so users know who's talking:  - 🏆 [Dispatcher] for main session messages  - 🔧 [worker-label] for worker responses


Step 3B: Config Safety Rules (MANDATORY)

NEVER touch the client's openclaw.json without their express permission.

Before making ANY config change, the AI agent must:

Announce the intended change to the client/operator in plain language
Research first - before editing config, the AI must:
Read the relevant OpenClaw docs (/opt/homebrew/lib/node_modules/openclaw/docs/ or https://docs.openclaw.ai)
Confirm the correct key paths, value types, and valid options
Verify the change won't break existing config (check for conflicts)
If unsure about any field, look it up - do NOT guess
Back up the current config to the client's backup folder (human-readable .txt with timestamp)
Verify the backup exists, is non-empty, and contains valid JSON
Get explicit permission from the operator before writing
Make only the approved change - nothing else
Validate the edited JSON (python3 -m json.tool)
Restart gateway (openclaw gateway restart)
Confirm completion + backup location to the operator

If backup fails → STOP. Do not edit.
If validation fails → revert from backup immediately.
If unsure about a config field → research it first, then ask.

Step 4: Restart Gateway

After config changes:
Back up config first (always)
Validate JSON
Restart gateway: openclaw gateway restart


5) Worker Lifecycle (Full Agent States)

State 1: NOT YET CREATED
Worker does not exist yet
Triggered by: first message ever from that sender
Action: Dispatcher spawns worker via sessions_spawn with label, actual task, cleanup: keep
Worker is now ACTIVE
State 2: ACTIVE (Running a Task)
Worker is executing a task
Has its own context window with conversation history
Can use all shared tools, files, and memory
When task completes: Worker stays alive (because cleanup: keep), moves to IDLE
State 3: IDLE (Alive, Waiting for Next Task)
Worker session exists but is not currently running a task
Context window is preserved
When new message arrives from same sender: Dispatcher sends task via sessions_send → worker moves back to ACTIVE
If no messages for 30 days: Worker auto-archives → moves to ARCHIVED
State 4: ARCHIVED (Auto or Manual)
Worker session has been cleaned up
Context window is gone
Shared files/memory still exist (they're on disk, not in the worker)
Triggers:
Auto: 30 days idle (archiveAfterMinutes: 43200)
Manual: team member says "archive [worker-label]" or /subagents kill
When next message arrives from that sender: Dispatcher spawns a fresh worker with same label → back to ACTIVE (new context, same files)
State 5: GATEWAY RESTART
All worker sessions are lost on gateway restart
This is expected behavior
Recovery: Dispatcher automatically re-spawns each worker on the next incoming message from that sender
Context windows reset, but all workspace/memory files persist
No manual intervention needed
Lifecycle Diagram

[First Message] → SPAWN → ACTIVE → (task done) → IDLE                                                    │                              [New message] ← ──────┘                                    │                                    ▼                                 ACTIVE → (task done) → IDLE                                                          │                                    [30 days no activity] ─┘                                              │                                              ▼                                          ARCHIVED                                              │                                    [Next message] ─────► SPAWN → ACTIVE                                    [Gateway Restart] → ALL WORKERS LOST → [Next message per sender] → SPAWN → ACTIVE


Manual Archive Commands
Archive one: "archive [worker-label]" or /subagents kill
Archive all: "archive all workers" or /subagents kill all
Re-spawn happens automatically on next incoming message

6) What Workers Share vs. What's Isolated

Shared (all workers access the same):
Workspace directory and all files
All shared workspace and memory files
All configured tools and skills (KIE.ai, GHL, Google Workspace, etc.)
Secrets and environment variables
Isolated (per worker):
Context window (conversation history within that worker session)
Token usage (each worker has its own)

7) Message Isolation Strategy

This section defines how conversation context and data stays isolated per worker to prevent bleed, confusion, and cross-contamination. NOTE: Message delivery (sending a Telegram message to another person when asked) is always permitted. What is isolated is conversation data and context - not the ability to communicate.

Inbound Isolation
Dispatcher reads the sender ID from message metadata on every incoming message
Sender ID determines which worker receives the task
One person's instructions are NEVER mixed into another person's worker context
If the dispatcher cannot identify the sender, it handles the message directly and asks for identity
Execution Isolation
Each person's work runs inside their own dedicated worker sub-agent
Workers have their own context window - they only see their own conversation history
Worker A has zero visibility into Worker B's active tasks or context
Workers share files on disk (workspace/memory), but not live conversation state

EXCEPTION - DISPATCHER VISIBILITY:
The dispatcher (main session) has FULL visibility across ALL workers.
The dispatcher CAN:
- Read any worker's conversation history via sessions_history
- Summarize what was discussed in any worker's session
- Relay information between workers when explicitly requested by the sender
- Forward results from one worker to another person's DM when told to

The dispatcher MUST:
- Only relay when the sender explicitly asks (e.g., "send [team member] the update from my last conversation")
- Tag forwarded messages: "Forwarded from [worker-label]"
- Never auto-share between workers without being asked

This means: Conversations stay separate per worker. But when a team member says "what did we discuss with [other member]?" or "send [person] the report from [another member]'s session," the dispatcher can do that because it has cross-worker read access.
Outbound Isolation
When a worker completes a task, the dispatcher sends the result ONLY to the Telegram DM of the person who requested it
The message tool is called with target explicitly set to that sender's Telegram ID
No other DMs receive the result
Context Isolation Rules
Default: Worker conversation data NEVER leaks to another worker. Ever.
Exception for directed sends: When a sender explicitly says "send [person] a message" or "tell [person] X" - the worker or dispatcher executes the Telegram send immediately. This is not cross-posting. This is a directed communication action.

What IS prohibited (context contamination):
- Auto-sharing Worker A's results with Worker B's DM without being asked
- One worker reading or referencing another worker's conversation history
- Context or instructions from one person's session appearing in another person's session
- The dispatcher forwarding information between workers without explicit instruction

What is NOT prohibited (directed sends):
- A worker or dispatcher sending a Telegram message to any team member's ID when asked
- A worker or dispatcher sending a Telegram message to another team member when asked
- Any team member saying "send [name] a message" - execute it immediately
- Relaying information between team members when explicitly requested
What This Prevents
- Command bleed: Person A's instructions leaking into Person B's worker context
- Result bleed: Person B seeing Person A's output without asking
- Context pollution: One person's conversation history affecting another person's AI responses
- Accidental broadcast: Same result sent to multiple DMs without being asked
Enforcement
- Dispatcher checks sender ID on EVERY message - no exceptions
- Workers never access, reference, or share another worker's conversation data or context. Workers CAN and SHOULD use the message tool to send to any Telegram ID when explicitly directed to do so by their assigned sender.
- If a worker needs to share data FROM another worker's session, it requests the dispatcher to retrieve it via sessions_history. Workers do not access other sessions directly.
 
7B) Contact Directory

The Routing Table maps INBOUND senders to workers. But team members also need to message people who don't message the bot (clients, external contacts, etc.).

Add a Contact Directory to WORKFLOW_AUTO.md alongside the Routing Table:

## Contact Directory (People We Message)
| Name | Telegram ID | Notes |
|------|-------------|-------|
| [Name] | [ID] | [Role/relationship] |

Rules:
- When a team member says "send [name] a message" and the name isn't in the Routing Table, check the Contact Directory
- If still not found, ask the sender for the Telegram ID once, then add it to the directory permanently
- Store in AGENTS.md and MEMORY.md so it survives restarts
 
8) Model Selection Rules

Critical: The sub-agent model MUST support tool calls. Models that don't support tool calls (e.g., some reasoning-only models) will fail silently or produce incomplete results.

Onboarding Question (Ask the Client)
During setup, ask the client which models they prefer for each task type. This is informational only - it does NOT change the client's primary agent model or their existing config. It only determines which models the dispatcher uses when spawning sub-agent workers for different task types.

The client's main agent model stays exactly as they configured it. This section only affects sub-agent worker model selection.

Present these categories and recommendations:

Model Roles (Sub-Agent Workers Only - Does Not Override Primary Agent)



Cost Strategy
Use OAuth/subscription models (GPT 5.3 Codex, Gemini) as defaults to keep per-token costs down
Reserve pay-per-token models for complex tasks only; for heavy reasoning prefer OAuth or Ollama-cloud models over OpenRouter to minimize cost
Route creative work to the creative model, not the thinking model
Route simple execution to the cheapest capable model
Recommended Default Config (Sub-Agents Only - Does NOT Touch Primary Agent Model)

Model selection is DYNAMIC via shared-utils/select_model.py (v9.5.0+). Three tier chains, NEVER Anthropic:

  Heavy reasoning (--purpose-tier heavy):
    1. ollama/kimi-k*:cloud (latest, thinking=high) — PREFERRED
    2. openrouter/moonshot/kimi-k* (thinking=high)
    3. ollama/deepseek-v*-pro:cloud
    4. openrouter/deepseek/deepseek-v*-pro (thinking=high)
    5. (openai-)codex/gpt-* (OAuth, latest)

  Mid-tier reasoning (--purpose-tier mid):
    1. ollama/minimax-m*:cloud
    2. openrouter/xiaomi/mimo-v*-pro (thinking=high)

  Fast / cheap (--purpose-tier fast):
    1. ollama/deepseek-v*-flash:cloud
    2. openrouter/deepseek/deepseek-v*-flash
    3. openrouter/google/gemini-*-flash-lite

Selector auto-picks the highest version found in the client's openclaw.json — when a new Kimi or GPT version ships and the client adds it, the selector picks it automatically. No skill update needed.


Important: This config block ONLY sets the model for sub-agent workers. The client's agents.defaults.model.primary (their main agent) is never modified by this protocol.

Per-Task Model Override (Sub-Agent Spawn Only)
The dispatcher can override the model per spawn when needed:
Creative task → call select_model.py --purpose-tier mid (Minimax/Mimo chain)
Complex reasoning → call select_model.py --purpose-tier heavy (Kimi-first; NEVER Anthropic)
Routine execution → call select_model.py --purpose-tier fast (DeepSeek-flash/Gemini-lite)
Model Selection Hierarchy (Decision Tree)

Is this a complex strategy/architecture/debugging task?  YES → --purpose-tier heavy (Kimi-first chain)  NO ↓Is this creative writing (copy, emails, scripts, hooks)?  YES → --purpose-tier mid (Minimax/Mimo)  NO ↓Is this routine execution (file ops, uploads, API calls)?  YES → --purpose-tier mid  NO ↓Is this bulk/simple/cost-sensitive?  YES → --purpose-tier fast (DeepSeek-flash/Gemini-lite)  NO → --purpose-tier heavy. Anthropic FORBIDDEN at every tier


Do NOT Use As Primary
Models without tool-call capability (e.g., some reasoning-only models)
Models with known rate-limit issues at your usage volume
Pay-per-token premium models for routine tasks (cost will explode)

9) Client vs. Worker Distinction

Some sub-agents serve team members (workers). Others serve clients.

Worker sub-agents:
Execute tasks assigned by team members
Can receive directives like "do this, fix that, create this"
Proactive suggestions are acceptable
Client sub-agents:
Serve the client's requests respectfully
Never assign the client tasks
Never boss the client around
Execute what they ask and report results
Mark client sub-agents clearly in the routing table with "Client (NOT a worker)" designation.


10) Scaling Guidelines



Cost note: Each worker has its own token usage. Monitor via usage-tracker reports. For high-volume teams, assign cheaper models to lower-priority workers.


11) Troubleshooting




12) Quick Reference Commands




13) Template: WORKFLOW_AUTO.md

Copy and customize for each client deployment:

# WORKFLOW_AUTO.md - Team Management Protocol (Dispatcher Routing)## Dispatcher Pattern (ACTIVE)Main session = dispatcher/router. Route all incoming messages by sender ID.## Team Members (Customize Per Deployment)| Sender ID | Name | Role | Worker Label | Reply To ||---|---|---|---|---|| [TEAM_MEMBER_1_ID] | [TEAM_MEMBER_NAME] | [ROLE] | [firstname1]-worker | [TEAM_MEMBER_1_ID] || [TEAM_MEMBER_2_ID] | [TEAM_MEMBER_NAME] | [ROLE] | [firstname2]-worker | [TEAM_MEMBER_2_ID] || [TEAM_MEMBER_3_ID] | [TEAM_MEMBER_NAME] | [ROLE] | [firstname3]-worker | [TEAM_MEMBER_3_ID] |## Client Team (Customize Per Deployment)| Sender ID | Name | Role | Worker Label | Reply To ||---|---|---|---|---|| CLIENT_ID | Client Name | Client (NOT a worker) | client-name-worker | CLIENT_ID || TEAM_ID | Team Member | Role | member-worker | TEAM_ID |## Reply Rules- Results go ONLY to requesting DM by default- Directed sends (sender says 'tell [person] X' or 'send [name] a message'): execute immediately, no confirmation needed- Context isolation: never share one worker's conversation data with another worker without being asked- Tag: 🏆 [Dispatcher] / 🔧 [worker-label]## Worker Config- Model: [primary model]- Fallbacks: [fallback 1], [fallback 2]- cleanup: keep- archiveAfterMinutes: 43200## Client Rules- [Client name] is the CLIENT - never assign tasks, serve respectfully- Team workers give instructions - AI executes their requests



14) Deployment Checklist (New Client)

[ ] Copy this SOP to client's master files
[ ] Copy WORKFLOW_AUTO.md template to client's workspace
[ ] Add all team member IDs collected during Step 0 intake
[ ] Add client principal ID as client-worker (not a worker)
[ ] Add any client team members as additional workers
[ ] Set sub-agent model chain (primary + fallbacks with tool-call support)
[ ] Set archiveAfterMinutes: 43200 (30 days)
[ ] Back up config, validate JSON, restart gateway
[ ] Test: send message from each team member, confirm routing + DM isolation
[ ] Confirm no context contamination between workers (conversation data stays isolated per worker)


15) CRITICAL: Persist IDs to Core .md Files

WORKFLOW_AUTO.md is a custom routing file - NOT a standard OpenClaw file. The agent does NOT read it at boot. It only reads AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, and SOUL.md every session. If Telegram IDs only live in WORKFLOW_AUTO.md, the agent will forget them next session.

The fix: Write the IDs to BOTH WORKFLOW_AUTO.md AND the core .md files.

[ADD TO AGENTS.md]

## BLACK CEO Team - Telegram Routing (Dispatcher Protocol)
- Protocol doc: ~/Downloads/[master-files-folder]/blackceo-management-protocol.md
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Architecture: Main session = dispatcher. Each person gets a dedicated worker sub-agent.

### Permanent Team IDs (Always Present in Every Deployment)
| Name | Telegram ID | Role | Worker Label |
|------|-------------|------|-------------|
| [TEAM_MEMBER_NAME] | [TEAM_MEMBER_ID] | [ROLE] | [firstname]-worker |
(Fill in from TEAM_CONFIG.md during setup - add one row per team member)

### Dispatcher Rules
- Route incoming messages by sender Telegram ID to the correct worker
- If worker exists and is active: use sessions_send to relay the task
- If worker does not exist: spawn with sessions_spawn (label, model, cleanup: keep)
- Results go ONLY to the requesting DM by default. Workers CAN send directed messages to any Telegram ID when explicitly asked.
- Dispatcher has FULL VISIBILITY across all workers (can read any worker's history via sessions_history)
- Context isolation is absolute - workers never share or reference another worker's conversation data
- Communication is NOT locked down - workers can message any Telegram ID when the sender asks them to


[ADD TO TOOLS.md]

## BLACK CEO Dispatcher - Message Routing
- WORKFLOW_AUTO.md: ~/clawd/WORKFLOW_AUTO.md (routing table with all Telegram IDs)
- Full protocol: ~/Downloads/[master-files-folder]/blackceo-management-protocol.md
- To send to a specific person: use message tool with target set to their Telegram ID
- All team Telegram IDs: see TEAM_CONFIG.md
- To check a worker's conversation: sessions_history(sessionKey) or sessions_list to find the session
- To relay between workers: dispatcher reads source worker history, summarizes, sends to target worker or target DM
- Worker sub-agent model must support tool calls (verified at selection time: Kimi 2.6+, Codex GPT, DeepSeek V4-pro all support tools; reasoning-only models are filtered)


[ADD TO MEMORY.md]

## BLACK CEO Team Telegram IDs (Permanent)
| Name | Telegram ID | Role |
|------|-------------|------|
| [TEAM_MEMBER_NAME] | [TEAM_MEMBER_ID] | [ROLE] |
(Fill in from TEAM_CONFIG.md during setup - add one row per team member)
- All team IDs are approved in channels.telegram.allowFrom
- Routing protocol: ~/clawd/WORKFLOW_AUTO.md
- Full SOP: ~/Downloads/[master-files-folder]/blackceo-management-protocol.md


16) What is WORKFLOW_AUTO.md?

WORKFLOW_AUTO.md is a CUSTOM file created by this protocol. It is NOT part of standard OpenClaw.

What it is: A routing table that maps Telegram IDs to worker sub-agent labels so the dispatcher knows where to send each person's messages.

Where it lives: ~/clawd/WORKFLOW_AUTO.md (in the workspace root)

What it contains:
- Table of sender IDs, names, roles, worker labels, and reply targets
- Reply rules (context isolation, directed messaging, tag format)
- Worker config (model, fallbacks, cleanup settings)
- Client-specific rules

When it gets updated:
- When a new team member or client is added
- When someone's role changes
- When model preferences change

What it does NOT do:
- It does NOT get read automatically at session boot (unlike AGENTS.md)
- It does NOT persist Telegram IDs to the agent's memory (that is what the [ADD TO] sections above fix)
- It is NOT an OpenClaw system file - it is a custom workspace file

The agent should read WORKFLOW_AUTO.md when it needs to look up routing details, but the critical IDs must ALSO be in AGENTS.md and MEMORY.md so the agent always knows them.


End of Team Management Protocol


