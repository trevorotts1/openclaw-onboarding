
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)
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

RULE 2: DO NOT CHANGE TREVOR'S INTENT
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
Ask Trevor first. Do not guess. Do not assume.

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

# BlackCEO Team Management - Installation Guide

This guide walks you through setting up the BlackCEO dispatcher system so your AI can serve multiple team members at the same time through Telegram, without messages getting mixed up between people.

---

## What This Sets Up

Right now, if multiple people message your AI bot on Telegram, their messages all go into the same conversation. Person A is waiting while Person B's task runs. Commands get mixed up. Responses go to the wrong people.

This setup fixes that by turning your AI into a "dispatcher" that gives each person their own dedicated worker. Think of it like a receptionist who routes each caller to the right department - except your AI does it automatically.

---

## What You Need Before Starting

- All previous 13 OpenClaw skills must be installed and working
- An active Telegram bot connected to OpenClaw
- The Telegram user IDs for each person who will use the bot (a number like 5252140759)
- Access to your OpenClaw configuration file at ~/.openclaw/openclaw.json

---

## Step 1: Back Up Your Configuration

Before making any changes, back up your current configuration. This is mandatory - no exceptions.

1. Open Terminal on your Mac (search for "Terminal" in Spotlight)
2. Type this command and press Enter:

```bash
mkdir -p ~/Downloads/OpenClaw\ Backup
cp ~/.openclaw/openclaw.json "~/Downloads/OpenClaw Backup/openclaw-config-backup-$(date +'%B %-d at %-I-%M %p').json"
```

3. Verify the backup exists:

```bash
ls -la ~/Downloads/OpenClaw\ Backup/
```

You should see a file with today's date. If the backup is empty or missing, STOP. Do not continue until you have a valid backup.

---

## Step 2: Configure Sub-Agent Settings

Open your OpenClaw configuration file and add settings that tell the AI how to manage multiple workers at the same time.

1. Open the configuration file. You can ask your AI to do this, or edit it manually:

```bash
nano ~/.openclaw/openclaw.json
```

2. Find the "agents" section (or create it if it does not exist). Add or update the "subagents" settings:

```json
{
  "agents": {
    "defaults": {
      "subagents": {
        "maxConcurrent": 8,
        "maxChildrenPerAgent": 5,
        "archiveAfterMinutes": 43200,
        "model": {
          "primary": "your-preferred-model",
          "fallbacks": [
            "fallback-model-1",
            "fallback-model-2"
          ]
        }
      }
    }
  }
}
```

Here is what each setting means:
- **maxConcurrent: 8** - Up to 8 workers can run at the same time
- **maxChildrenPerAgent: 5** - Each worker can have up to 5 sub-tasks running
- **archiveAfterMinutes: 43200** - Workers that have not been used in 30 days (43200 minutes) get cleaned up automatically
- **model.primary** - The AI model that workers will use (must support tool calls)
- **model.fallbacks** - Backup models if the primary one is unavailable

---

## Step 3: Approve Telegram IDs

Every person who will use the bot needs their Telegram ID added to the "allowed" list. Without this, the bot will ignore their messages completely.

1. In the same configuration file (~/.openclaw/openclaw.json), find the "channels" section
2. Add each person's Telegram ID to the allowFrom list:

```json
{
  "channels": {
    "telegram": {
      "allowFrom": [
        "5252140759",
        "6663821679",
        "6771245262"
      ]
    }
  }
}
```

The three IDs shown above are the BLACK CEO management team. They are ALWAYS included in every deployment:
- 5252140759 - Trevor Otts (Operations Lead / AI Director)
- 6663821679 - LeAnne (Head of Marketing)
- 6771245262 - E.R. Spaulding (Chief of Operations)

3. Add any additional team members or client IDs to the same array
4. Save the file

---

## Step 4: Create the Routing Table

The routing table tells the dispatcher which worker belongs to which person. Create a file called WORKFLOW_AUTO.md in your workspace.

1. Create the file:

```bash
nano ~/clawd/WORKFLOW_AUTO.md
```

2. Paste this template and fill in your team's information:

```markdown
# WORKFLOW_AUTO.md - BLACK CEO Management Protocol (Dispatcher Routing)

## Dispatcher Pattern (ACTIVE)
Main session = dispatcher/router. Route all incoming messages by sender ID.

## BLACK CEO Management Team (Always Present)
| Sender ID | Name | Role | Worker Label | Reply To |
|---|---|---|---|---|
| 5252140759 | Trevor Otts | Operations Lead / AI Director | trevor-worker | 5252140759 |
| 6663821679 | LeAnne | Head of Marketing | leanne-worker | 6663821679 |
| 6771245262 | E.R. Spaulding | Chief of Operations | spaulding-worker | 6771245262 |

## Client Team (Customize Per Deployment)
| Sender ID | Name | Role | Worker Label | Reply To |
|---|---|---|---|---|
| CLIENT_ID | Client Name | Client (NOT a worker) | client-name-worker | CLIENT_ID |

## Reply Rules
- Results go ONLY to requesting DM
- No cross-posting unless explicitly requested
- Tag: [Dispatcher] / [worker-label]

## Worker Config
- Model: [primary model]
- Fallbacks: [fallback 1], [fallback 2]
- cleanup: keep
- archiveAfterMinutes: 43200

## Client Rules
- [Client name] is the CLIENT - never assign tasks, serve respectfully
- BLACK CEO team members are workers - they give instructions, AI executes
```

3. Save the file

---

## Step 5: Add Team IDs to Core Files

WORKFLOW_AUTO.md is a custom file. Your AI does NOT read it automatically at startup. The AI only reads AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, and SOUL.md every session. So you MUST also add the team IDs to your core files.

### Add to AGENTS.md:

```markdown
## BLACK CEO Team - Telegram Routing (Dispatcher Protocol)
- Protocol doc: ~/Downloads/[master-files-folder]/blackceo-management-protocol.md
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Architecture: Main session = dispatcher. Each person gets a dedicated worker sub-agent.

### Permanent Team IDs (Always Present in Every Deployment)
| Name | Telegram ID | Role | Worker Label |
|------|-------------|------|-------------|
| Trevor Otts | 5252140759 | Operations Lead / AI Director | trevor-worker |
| LeAnne | 6663821679 | Head of Marketing | leanne-worker |
| E.R. Spaulding | 6771245262 | Chief of Operations | spaulding-worker |

### Dispatcher Rules
- Route incoming messages by sender Telegram ID to the correct worker
- If worker exists and is active: use sessions_send to relay the task
- If worker does not exist: spawn with sessions_spawn (label, model, cleanup: keep)
- Results go ONLY to the requesting DM unless sender says "send this to [person]"
- Dispatcher has FULL VISIBILITY across all workers (can read any worker's history via sessions_history)
- Workers are isolated from each other but the dispatcher bridges them when asked
```

### Add to TOOLS.md:

```markdown
## BLACK CEO Dispatcher - Message Routing
- WORKFLOW_AUTO.md: ~/clawd/WORKFLOW_AUTO.md (routing table with all Telegram IDs)
- Full protocol: ~/Downloads/[master-files-folder]/blackceo-management-protocol.md
- To send to a specific person: use message tool with target set to their Telegram ID
- Trevor: 5252140759 | LeAnne: 6663821679 | Spaulding: 6771245262
- Worker sub-agent model must support tool calls (MiniMax M2.5, Codex, Sonnet - NOT reasoning-only models)
```

### Add to MEMORY.md:

```markdown
## BLACK CEO Team Telegram IDs (Permanent)
| Name | Telegram ID | Role |
|------|-------------|------|
| Trevor Otts | 5252140759 | Operations Lead |
| LeAnne | 6663821679 | Head of Marketing |
| E.R. Spaulding | 6771245262 | Chief of Operations |
- These 3 IDs are ALWAYS approved in channels.telegram.allowFrom
- Routing protocol: ~/clawd/WORKFLOW_AUTO.md
```

---

## Step 6: Validate and Restart

1. Validate that your configuration file is valid JSON:

```bash
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
```

If you see no output, the JSON is valid. If you see an error message, there is a typo in your config file. Fix it before continuing.

2. Restart the OpenClaw gateway:

```bash
openclaw gateway restart
```

3. Wait 10 seconds, then check it is running:

```bash
openclaw gateway status
```

You should see "running" in the output.

---

## Step 7: Test the Setup

1. Send a message from each team member's Telegram account to the bot
2. The dispatcher should create a dedicated worker for each person
3. Verify that:
   - Each person's response goes ONLY to their own DM
   - No messages leak between people
   - Workers are created with the correct labels

---

## Config Safety Rules (Important)

When making configuration changes for client deployments:

1. **Always announce** the intended change to the client in plain language before making it
2. **Always back up** the current config before editing (Step 1 above)
3. **Always validate** the JSON after editing (Step 6 above)
4. **Always get explicit permission** from the operator before writing changes
5. **Never guess** about config fields - look them up in the OpenClaw docs first
6. If backup fails, STOP. Do not edit.
7. If validation fails, revert from backup immediately.

---

## Deployment Checklist (New Client)

Use this checklist when setting up this protocol for a new client:

```
[ ] Copy this SOP to client's master files
[ ] Copy WORKFLOW_AUTO.md template to client's workspace
[ ] Add BLACK CEO team IDs (Trevor, LeAnne, Spaulding) - these never change
[ ] Add client principal ID as client-worker (not a worker)
[ ] Add any client team members as additional workers
[ ] Set sub-agent model chain (primary + fallbacks with tool-call support)
[ ] Set archiveAfterMinutes: 43200 (30 days)
[ ] Back up config, validate JSON, restart gateway
[ ] Test: send message from each team member, confirm routing + DM isolation
[ ] Confirm no cross-posting between DMs
```
