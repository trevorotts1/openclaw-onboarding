# QC Checklist — Skill 15: BlackCEO Team Management
# Run this after installation to verify the skill is correctly configured.
# Grade each item PASS / FAIL / SKIP (SKIP only if item is not applicable to this deployment).

---

## SECTION 1: File Structure Checks

Verify the following files exist and are non-empty.

```
[ ] 1.1  ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md exists
         - Must contain at least one populated row (no placeholder brackets like [Name 1])
         - Must have Name, Telegram ID, Role, Type, and Worker Label columns

[ ] 1.2  ~/clawd/WORKFLOW_AUTO.md exists
         - Must contain a populated Team Members table (no placeholder brackets)
         - Must contain Reply Rules, Worker Config, and Client Rules sections

[ ] 1.3  ~/.openclaw/openclaw.json exists and is readable

[ ] 1.4  Backup file exists in ~/Downloads/OpenClaw Backup/
         - File name must contain today's date
         - Run: ls ~/Downloads/OpenClaw\ Backup/
         - FAIL if directory is empty or missing
```

---

## SECTION 2: Core File Update Checks

Verify that AGENTS.md, TOOLS.md, and MEMORY.md were updated correctly per CORE_UPDATES.md.
Do NOT check for full protocol content dumped in — only lean summaries + file path pointers.

```
[ ] 2.1  ~/clawd/AGENTS.md contains "Team Management - Dispatcher Protocol"
         - Must include routing table path: ~/clawd/WORKFLOW_AUTO.md
         - Must include team config path: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
         - Must include a populated team member table with real names and Telegram IDs
         - Must include "Context Isolation Rule" section
         - Must NOT contain full protocol content (thousands of lines) — lean summary only

[ ] 2.2  ~/clawd/TOOLS.md contains "Team Dispatcher - Message Routing"
         - Must reference ~/clawd/WORKFLOW_AUTO.md
         - Must reference ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
         - Must state that worker results go only to the requesting DM
         - Must NOT contain the full protocol content — lean summary only

[ ] 2.3  ~/clawd/MEMORY.md contains "Team Management - Installed"
         - Must contain a populated team member table with real names and Telegram IDs
         - Must reference ~/clawd/WORKFLOW_AUTO.md
         - Must reference ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
         - Must include the context isolation note (context only, not communication lockdown)
         - Must NOT contain the full protocol content — lean summary only

[ ] 2.4  IDENTITY.md was NOT modified (no update required per CORE_UPDATES.md)

[ ] 2.5  HEARTBEAT.md was NOT modified (no update required per CORE_UPDATES.md)

[ ] 2.6  USER.md was NOT modified (no update required per CORE_UPDATES.md)
```

---

## SECTION 3: openclaw.json Configuration Checks

```
[ ] 3.1  JSON is valid
         Run: python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
         Expected: no output (no errors)
         FAIL if any error message appears

[ ] 3.2  agents.defaults.subagents.maxConcurrent is set (any integer >= 4)

[ ] 3.3  agents.defaults.subagents.maxChildrenPerAgent is set (any integer >= 1)

[ ] 3.4  agents.defaults.subagents.archiveAfterMinutes is set to 43200
         (30 days — this is a required value, not a recommendation)

[ ] 3.5  agents.defaults.subagents.model.primary is set to a model that supports tool calls
         Acceptable: MiniMax M2.5, Codex, Sonnet 4.6, Opus 4.6, Gemini Flash, Mistral Creative
         FAIL if set to a reasoning-only model

[ ] 3.6  agents.defaults.subagents.model.fallbacks is an array with at least one entry

[ ] 3.7  channels.telegram.allowFrom is an array containing at least the IDs from TEAM_CONFIG.md
         - Every Telegram ID in TEAM_CONFIG.md must appear here
         - FAIL if any team member ID is missing from allowFrom
         - FAIL if allowFrom still contains placeholder strings like "[TEAM_MEMBER_1_ID]"
```

---

## SECTION 4: Knowledge Verification Questions

Answer each question by reading the installed files — do not rely on memory alone.
Mark PASS only if the answer matches what is actually written in the files.

```
[ ] 4.1  What is the dispatcher's role?
         PASS answer: The main session is the dispatcher/router. It receives all incoming
         messages, identifies the sender by Telegram ID, and routes the task to the
         correct worker sub-agent. It does NOT do the work itself.

[ ] 4.2  What happens to workers after a gateway restart?
         PASS answer: All workers are lost. This is expected and normal. Workers are
         automatically re-spawned when each person sends their next message.
         No manual fix is needed.

[ ] 4.3  What does "context isolation" mean — and what does it NOT mean?
         PASS answer: Each worker has its own isolated conversation history. One
         worker's context never leaks into another worker's context. However, this
         is NOT a communication lockdown — workers CAN send directed Telegram messages
         to any ID when explicitly asked. Isolation is context-only.

[ ] 4.4  What is the difference between a Worker and a Client in this system?
         PASS answer: Workers are team members who give instructions to the AI — the AI
         executes their requests. Clients are business owners or principals who are
         SERVED by the AI — the AI never assigns them tasks or bosses them around.
         Clients are marked "Client (NOT a worker)" in the routing table.

[ ] 4.5  Where does the agent read team configuration data from at boot?
         PASS answer: AGENTS.md and MEMORY.md (boot-persistent). For full routing details
         the agent reads ~/clawd/WORKFLOW_AUTO.md. For the source of truth when
         updating or onboarding, the agent reads TEAM_CONFIG.md.

[ ] 4.6  What model types are forbidden for worker sub-agents?
         PASS answer: Reasoning-only models that do not support tool calls. These will
         fail silently or produce incomplete results.

[ ] 4.7  When is cross-posting between DMs allowed?
         PASS answer: Only when the sender explicitly asks — e.g., "send this to [person]"
         or "share this with [person]." Auto-sharing results without being asked is never allowed.

[ ] 4.8  What is the archiveAfterMinutes value and what does it mean?
         PASS answer: 43200 minutes (30 days). Workers inactive for 30 days are
         automatically cleaned up. Their conversation history is gone but shared files
         on disk remain.
```

---

## SECTION 5: Live Behavior Test

Run these tests only after the gateway is confirmed running (`openclaw gateway status` shows "running").

```
[ ] 5.1  Single sender routing test
         Action: Send a message to the bot from a team member's Telegram account
         Expected: Bot responds ONLY in that person's DM
         Expected: A worker is spawned with the correct label (e.g., alice-worker)
         FAIL if: Response appears in a different DM, or no worker is spawned

[ ] 5.2  Parallel sender test (if 2+ team members available)
         Action: Have two team members send messages within a few seconds of each other
         Expected: Each person gets their own response in their own DM
         Expected: Neither person sees the other's message or response
         FAIL if: Messages bleed between DMs, or one person gets the other's result

[ ] 5.3  Unknown sender test
         Action: Send a message from a Telegram account NOT in the allowFrom list
         Expected: Bot ignores the message completely (no response)
         FAIL if: Bot responds to the unauthorized sender

[ ] 5.4  Worker persistence test
         Action: Have the same person send two messages in a row (a few seconds apart)
         Expected: The second message is routed to the EXISTING worker (not a new spawn)
         FAIL if: A new worker is spawned for every single message

[ ] 5.5  Client behavior test (if a Client-type member is configured)
         Action: Have the configured Client send a request
         Expected: AI responds respectfully and serves the request — it does NOT
                   assign the client tasks, ask them to do work, or boss them around
         FAIL if: AI tells the client to do something or assigns them a task

[ ] 5.6  Worker label format test
         Action: Spawn or list active workers after routing tests
         Expected: Worker labels follow the format [firstname]-worker (all lowercase)
         Example: Alice Johnson → alice-worker, Bob Smith → bob-worker
         FAIL if: Labels are uppercase, use full names, or deviate from the pattern
```

---

## SECTION 6: Anti-Pattern Checks

These are failure modes documented in the skill files. Check that none of the following are present.

```
[ ] 6.1  NO full protocol content dumped into AGENTS.md, TOOLS.md, or MEMORY.md
         FAIL if any core .md file contains thousands of lines from this skill

[ ] 6.2  NO hardcoded placeholder text remaining in config or routing files
         Check for: [TEAM_MEMBER_ID], [TEAM_MEMBER_NAME], [ROLE], [Name 1], [ID 1]
         Locations to check: WORKFLOW_AUTO.md, TEAM_CONFIG.md, openclaw.json, AGENTS.md, MEMORY.md
         FAIL if any placeholder bracket syntax remains in any of these files

[ ] 6.3  NO team member IDs stored ONLY in WORKFLOW_AUTO.md
         WORKFLOW_AUTO.md is not read at boot — IDs must also be in AGENTS.md and MEMORY.md
         FAIL if team IDs appear only in WORKFLOW_AUTO.md and not in core files

[ ] 6.4  NO reasoning-only model set as the primary worker model
         Re-verify: agents.defaults.subagents.model.primary supports tool calls
         FAIL if using a model known to lack tool-call capability

[ ] 6.5  NO gateway restart was triggered autonomously during installation
         The agent must have STOPPED and NOTIFIED the operator to run /restart in Telegram
         FAIL if the agent ran `openclaw gateway restart` without explicit operator permission

[ ] 6.6  NO team member is missing from channels.telegram.allowFrom
         Cross-reference: every ID in TEAM_CONFIG.md must be in allowFrom
         FAIL if any team member's ID is absent from allowFrom (bot will ignore them)

[ ] 6.7  NO CLIENT is marked as "Worker" in TEAM_CONFIG.md or WORKFLOW_AUTO.md
         Any person marked Client must appear as "Client (NOT a worker)" in the routing table
         FAIL if a known client has a Worker designation

[ ] 6.8  NO config changes were made without a backup being created first
         Verify backup file exists (Section 1.4) before any config change is valid
         FAIL if the backup is missing
```

---

## SECTION 7: Pass Criteria

### PASS — Skill is correctly installed
All of the following must be true:

- All items in Sections 1, 2, 3 are checked PASS (no FAILs)
- All 8 Knowledge Verification questions in Section 4 answered correctly
- All applicable Live Behavior Tests in Section 5 returned PASS
- All Anti-Pattern checks in Section 6 are PASS (none of the failure modes are present)

### CONDITIONAL PASS — Minor gaps, document and proceed
Acceptable only if:

- 1 or 2 items in Section 5 are SKIP due to insufficient team members available for live testing
- All config and file checks (Sections 1–3, 6) are fully PASS
- All knowledge questions (Section 4) are PASS
- Any SKIP items are logged with a reason and flagged for follow-up testing

### FAIL — Do not mark skill as installed
Fail conditions (any one of these = FAIL):

- Any item in Section 3 (JSON config) returns FAIL
- Section 6.1 (protocol dumped into core files) returns FAIL
- Section 6.2 (placeholder text remains) returns FAIL
- Section 6.3 (IDs only in WORKFLOW_AUTO.md, not in core files) returns FAIL
- Section 6.6 (team member missing from allowFrom) returns FAIL
- Any Section 5 live test returns FAIL (unless SKIP with documented reason)
- Knowledge question 4.3 (isolation vs. lockdown) answered incorrectly — this is a critical distinction

---

## QC Run Log

Fill this in after running the checklist:

```
Date run:
Run by (agent or operator):
Gateway status at time of QC:
Team members configured (count):
Any FAILs encountered:
Any SKIPs and reasons:
Overall result: [ ] PASS  [ ] CONDITIONAL PASS  [ ] FAIL
Notes:
```
