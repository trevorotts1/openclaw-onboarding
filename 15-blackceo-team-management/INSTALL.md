╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: VERIFY TEACH YOURSELF PROTOCOL (TYP) IN CONTEXT

Before executing ANY instruction in this document, verify TYP has been taught:
- Check AGENTS.md, TOOLS.md, or MEMORY.md for "Teach Yourself Protocol" or "TYP"
- Check session context for prior TYP training
- Check for a "Teach Yourself Protocol" tab in this document

IF TYP IS CONFIRMED IN CONTEXT:
Proceed to execution. Follow the TYP file storage structure.

IF TYP IS NOT CONFIRMED:
HALT IMMEDIATELY. Do not read further. Do not execute. Report:
  "TYP not found in context. Cannot safely execute. Require Teach Yourself
   Protocol training before proceeding. Without TYP, core .md files will
   bloat and tokens will be wasted."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any file in this skill folder
conflicts with TYP regarding WHICH core .md files to update or WHAT content
to add, follow this skill's files. The skill takes precedence over TYP on
core file update decisions. TYP governs the storage method (lean summaries +
file paths). The skill governs the content and which files it touches. When
in doubt: skill docs win.


══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (execute only if TYP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Locate the OpenClaw master files folder in ~/Downloads/. Possible names:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder exists, create: ~/Downloads/OpenClaw Master Files/

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

EXECUTION DISCIPLINE - MANDATORY BEFORE EXECUTION
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time instructions from this document are executed.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE EXECUTING ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE INTENT
These instructions specify exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If uncertain whether something should be changed, the answer is NO.
Do not guess. Do not assume.

RULE 4: BUILD CHECKLIST BEFORE EXECUTING
Before running a single command or making a single change, create a numbered
checklist of every action this document requires. Write it out. Show it to
the requester before starting. Get confirmation. Then execute.

RULE 5: CHECK AGAINST CHECKLIST WHEN DONE
When execution is believed complete, go back to the checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before reporting done.
Do NOT report done until the checklist is 100% complete.

RULE 6: REPORT WHAT WAS DONE
When finished, give the requester a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

# BlackCEO Team Management - Agent Installation Protocol

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


This protocol configures the dispatcher system so the AI agent can serve multiple team members simultaneously through Telegram without message mixing between senders.

---

## What This Configures

Current state: Multiple Telegram senders result in messages entering the same conversation. Messages queue. Commands mix. Responses route incorrectly.

Target state: AI agent operates as a dispatcher that assigns each sender a dedicated worker sub-agent. Each sender gets isolated execution space. Messages route correctly. No cross-contamination.

---

## Prerequisites

- All 14 prior OpenClaw skills installed and functional
- An active Telegram bot connected to OpenClaw
- Telegram user IDs for each team member (numeric format: e.g., 1234567890)
- Write access to ~/.openclaw/openclaw.json

---

## Execution Checklist

Before starting, create this checklist and confirm completion after each step:

```
[ ] Step 0: Determine box type (CLIENT vs OPERATOR), load the correct roster
[ ] Step 0.5: Operator INBOUND access (remote-rescue) + OPT-IN escalation chat
[ ] Step 1: Back up ~/.openclaw/openclaw.json
[ ] Step 2: Configure sub-agent settings in openclaw.json
[ ] Step 3: Add Telegram IDs to channels.telegram.allowFrom
[ ] Step 4: Generate TEAM_CONFIG.md (CLIENT box: owner-only reply-to-sender)
[ ] Step 5: Create WORKFLOW_AUTO.md routing table (CLIENT box: reply-to-sender)
[ ] Step 6: Add routing to AGENTS.md (CLIENT box: owner-only)
[ ] Step 7: Add routing to TOOLS.md (CLIENT box: owner-only)
[ ] Step 8: Add routing to MEMORY.md (CLIENT box: owner-only)
[ ] Step 9: Validate JSON syntax
[ ] Step 10: Restart OpenClaw gateway
[ ] Step 11: Verify gateway is running
[ ] Step 12: Test routing with the owner (and operators inbound via remote-rescue)
[ ] Step 13: Confirm message isolation (operator session != owner session)
[ ] Step 14: (OPT-IN only) Completion confirmation to operator — resolves via
            shared-utils/operator-chat-id.sh; SKIPPED if no operator escalation
            chat is configured (NO hardcoded personal-chat default)
```

---

## Step 0: Determine Box Type, Then Load the CORRECT Routing Roster

**🔴 CO-MINGLING GUARD (v12.4.0): a CLIENT box must ship reply-to-sender +
owner-only routing. The BlackCEO operator team (Trevor / LeAnne / Spaulding)
must NEVER be stamped as "workers" on a client's `main` agent. Operators get
INBOUND access via the separate `remote-rescue` agent in Step 0.5 — that is the
only place operator IDs belong on a client box.**

### Step 0a: Is this the OPERATOR box or a CLIENT box?

- **CLIENT box** (the default — every box you onboard for a paying client):
  the box serves ONE owner (the client). There is NO operator "team" routed on
  the `main` agent. Set the routing roster to the single client owner.
- **OPERATOR box** (BlackCEO's own internal management box ONLY): set
  `IS_OPERATOR_BOX=1` in the environment before running this skill. Only an
  operator box materializes the multi-member BlackCEO dispatcher table.

Detect: if `IS_OPERATOR_BOX=1` is set (or you have been told explicitly that
this is BlackCEO's own internal box), use the OPERATOR roster below. Otherwise
this is a CLIENT box — use the CLIENT roster.

### Step 0b (CLIENT box — the default): owner-only reply-to-sender

Collect the ONE owner chat id (the paying client). It is normally already known:
it is the client's own Telegram chat id, the same id approved in
`channels.telegram.allowFrom` for the client bot (NOT an operator id). If you do
not already have it, ask the owner once for their Telegram chat id.

| Telegram ID | Name | Role | Type | Reply To |
|-------------|------|------|------|----------|
| {{OWNER_CHAT_ID}} | {{OWNER_NAME}} | Owner (the client) | Owner | {{OWNER_CHAT_ID}} |

Routing rule for a client box: **reply ONLY to the sender of each incoming
message. Do NOT spawn per-person operator worker lanes. There is no operator
team on this box.** Proceed to Step 0.5 (which configures operator INBOUND
access via remote-rescue, separately and correctly).

### Step 0c (OPERATOR box ONLY — `IS_OPERATOR_BOX=1`): BlackCEO dispatcher roster

The operator box (and ONLY the operator box) routes the BlackCEO management team:

| Telegram ID | Name | Role | Type | Worker Label |
|-------------|------|------|------|--------------|
| 5252140759 | Trevor Otts | CEO | Worker | trevor-worker |
| {{TEAM_MEMBER_CHAT_ID}} | A Client | Client | Client | client-worker |
| {{TEAM_MEMBER_CHAT_ID}} | Chief of Operations | Chief of Operations | Worker | ops-worker |

**If `IS_OPERATOR_BOX` is NOT set, do NOT use this roster on the box. Using it on
a client box is the co-mingling defect this guard exists to prevent.**

---

## Step 0.5: Operator INBOUND Access (Remote Rescue) + OPT-IN Escalation Chat

**This step provisions the operator-side "Remote Rescue by T Otts" agent
(operator INBOUND access — desired and preserved) and, ONLY if you explicitly
provide one, an OPT-IN operator escalation chat in
`env.vars.OPERATOR_ESCALATION_CHAT_ID` (schema-compliant under the 2026.5.22
openclaw.json schema).**

Why it exists: operators (Trevor / LeAnne / Spaulding) must be able to message
the client agent (inbound), landing in the isolated `remote-rescue` session —
NEVER in the owner's `main` session, and NEVER as routed "workers." Separately,
some skills (23/35/37 + cron-prompt) can escalate maintenance/build status to an
operator. That escalation destination is now **opt-in and configurable** via
`env.vars.OPERATOR_ESCALATION_CHAT_ID` (back-compat: `OPERATOR_TELEGRAM_CHAT_ID`),
resolved at runtime via `shared-utils/operator-chat-id.sh`. **There is NO
hardcoded personal-chat default** — if no escalation chat is configured, every
escalation NO-OPs (logs only). A client box installed without one therefore
never proactively messages any operator. (This is the v12.4.0 co-mingling fix —
the old hardcoded `5252140759` default was the leakage vector.)

### ISOLATION GUARANTEE

OpenClaw keys every conversation as `agent:<agentId>:telegram:<chatId>`. For operators and the owner to have fully separate sessions the routing must resolve to a different `agentId`. This step achieves that by:

- Giving `remote-rescue` its own `workspace` directory (physically separate session storage from `main`).
- Binding operator chat IDs to `remote-rescue` via `agents.list[remote-rescue].telegram.allowFrom`. OpenClaw checks per-agent `allowFrom` before falling back to the default agent.
- Adding operator IDs to `channels.telegram.allowFrom` (bot must accept their messages) but NOT to `channels.telegram.groupAllowFrom` (the owner's Command Center group stays owner-only).

Resulting session keys (fully disjoint):
- Owner: `agent:main:telegram:<ownerChatId>`
- Each operator: `agent:remote-rescue:telegram:<operatorChatId>`

### Interactive install (default)

```bash
bash 15-blackceo-team-management/scripts/install-remote-rescue.sh
```

The script will:
1. Prompt for the operator escalation Telegram chat ID. **Leave BLANK to DISABLE
   operator escalation on this box (the safe client-box default — no hardcoded id).**
2. ONLY if a chat id was provided: write it to `env.vars.OPERATOR_ESCALATION_CHAT_ID`
   (and back-compat `OPERATOR_TELEGRAM_CHAT_ID`) via `openclaw config set ... --strict-json`.
   If blank, nothing is written and operator escalation stays disabled.
3. Add operator IDs to `channels.telegram.allowFrom` and STRIP them from
   `channels.telegram.groupAllowFrom` (operator INBOUND access — always applied).
4. Append or update `remote-rescue` in `agents.list` with `workspace`,
   `telegram.allowFrom` binding, and `subagents.allowAgents: ["*"]` (idempotent).
5. Create the workspace directory at `~/.openclaw/workspaces/remote-rescue`.
6. (Only if an escalation chat was provided) send a one-time bootstrap message to
   that operator chat explaining the isolated routing (no `/agent` switch needed).

### Non-interactive install (rollout automation)

```bash
# CLIENT box default: leave OPERATOR_ESCALATION_CHAT_ID UNSET to ship with
# operator escalation disabled (operator inbound access is still configured).
# To OPT IN, set OPERATOR_ESCALATION_CHAT_ID="<operator chat id>" explicitly.
NONINTERACTIVE=1 \
CLIENT_NAME="<Client Name>" PERSONA="<Persona>" \
CLIENT_BOT_USERNAME="<bot_username>" HOST_NAME="$(hostname)" \
bash 15-blackceo-team-management/scripts/install-remote-rescue.sh
```

For repair/re-apply on previously installed boxes:

```bash
NONINTERACTIVE=1 bash 15-blackceo-team-management/scripts/install-remote-rescue.sh --repair
```

### Verification (MANDATORY before proceeding to Step 1)

```bash
openclaw config get env.vars.OPERATOR_ESCALATION_CHAT_ID   # empty == escalation disabled (OK on a client box)
openclaw config get agents.list | grep -A15 "remote-rescue"
python3 -c "
import json, os
cfg=json.load(open(next(p for p in ['$HOME/.openclaw/openclaw.json','/data/.openclaw/openclaw.json'] if os.path.exists(p))))
op_ids={'5252140759','6663821679','6771245262'}
leak=op_ids & set(cfg.get('channels',{}).get('telegram',{}).get('groupAllowFrom') or [])
print('FAIL groupAllowFrom leak:',leak) if leak else print('PASS groupAllowFrom clean')
rr=next((a for a in cfg.get('agents',{}).get('list',[]) if a.get('id')=='remote-rescue'),None)
print('PASS' if rr and rr.get('workspace') and rr.get('telegram',{}).get('allowFrom') else 'FAIL remote-rescue binding missing')
"
openclaw config validate
```

All four checks must pass. Then verify with a live DM from an operator account (config check alone is a false pass).

---

## Step 1: Back Up Configuration

Create backup of ~/.openclaw/openclaw.json before any modifications.

Execute:
```bash
mkdir -p ~/Downloads/OpenClaw\ Backup
cp ~/.openclaw/openclaw.json "~/Downloads/OpenClaw Backup/openclaw-config-backup-$(date +'%B %-d at %-I-%M %p').json"
```

Verify backup exists:
```bash
ls -la ~/Downloads/OpenClaw\ Backup/
```

Confirm: File with current date appears in output. If empty or missing, STOP. Do not proceed.

---

## Step 2: Verify Sub-Agent Settings

Sub-agent concurrency settings were already configured during Step 2.5 of the onboarding walkthrough. Verify they are present:

Read ~/.openclaw/openclaw.json and confirm these values exist under agents.defaults.subagents:
- maxSpawnDepth: 4
- maxConcurrent: 20
- maxChildrenPerAgent: 12

If any are missing, add them. If all are present, proceed to Step 3.

Do NOT overwrite existing values. Only add what is missing.

---

## 🔴 CRITICAL: Steps 3-8 Must Use REAL Data
**Do NOT leave placeholder text like [TEAM_MEMBER_NAME] or [TEAM_MEMBER_ID] in any file.**
After collecting team data in Step 0, you MUST replace ALL placeholders with the actual names, Telegram IDs, and roles collected from the user. If you finish Steps 3-8 and any file still contains square-bracket placeholders, you failed this skill.

**After completing Steps 6-8, verify:**
1. Open AGENTS.md and confirm real names and Telegram IDs are present (not placeholders)
2. Open MEMORY.md and confirm the Team Telegram IDs table has real data
3. Open TOOLS.md and confirm the routing reference has real paths
4. Read back the team roster to the user and ask them to confirm it is correct

---

## Step 3: Add Telegram IDs to Allowlist

In the same configuration file, locate the "channels" section. Add each team member's Telegram ID to the allowFrom array using the IDs collected in Step 0.

```json
{
  "channels": {
    "telegram": {
      "allowFrom": [
        "[TEAM_MEMBER_1_ID]",
        "[TEAM_MEMBER_2_ID]",
        "[TEAM_MEMBER_3_ID]"
      ]
    }
  }
}
```

Replace [TEAM_MEMBER_N_ID] with the actual numeric Telegram IDs collected during Step 0.

Add all team members and clients to the same array. If a person's ID is not in this list, the bot will ignore their messages completely.

Save file.

---

## Step 4: Generate TEAM_CONFIG.md

Create a TEAM_CONFIG.md file that records all team member data collected in Step 0.
Save it at: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md

Execute:
```bash
mkdir -p ~/.openclaw/skills/15-blackceo-team-management
nano ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
```

**CLIENT box (default):** paste the owner-only reply-to-sender config. Replace
`{{OWNER_CHAT_ID}}` / `{{OWNER_NAME}}` with the client owner's real values from
Step 0b. Do NOT add operator IDs here — operators get inbound access via
remote-rescue (Step 0.5), never as workers on this box.

```markdown
# TEAM_CONFIG.md - Routing Configuration (CLIENT box: reply-to-sender, owner-only)
# Generated during skill 15 setup
# This is a single-client box. Reply ONLY to the sender. No operator team here.

## Owner

| Telegram ID | Name | Role | Type | Reply To |
|-------------|------|------|------|----------|
| {{OWNER_CHAT_ID}} | {{OWNER_NAME}} | Owner (the client) | Owner | {{OWNER_CHAT_ID}} |

## Notes
- This box serves ONE owner (the paying client). Reply only to the sender.
- Do NOT spawn per-person operator worker lanes. There is no operator team on this box.
- Operator (BlackCEO) inbound access is configured separately via the
  remote-rescue agent (Step 0.5) — operator IDs NEVER appear here as workers.
```

**OPERATOR box ONLY (`IS_OPERATOR_BOX=1`):** use the multi-member BlackCEO
dispatcher roster from Step 0c instead (one row per operator with a worker label).

Replace all placeholder brackets with real data from Step 0. Save file.

---

## Step 5: Create Routing Table

Create WORKFLOW_AUTO.md in ~/clawd/ to define dispatcher routing.

Execute:
```bash
nano ~/clawd/WORKFLOW_AUTO.md
```

**CLIENT box (default):** paste the reply-to-sender routing block. Replace
`{{OWNER_CHAT_ID}}` / `{{OWNER_NAME}}` with the client owner's real values.

```markdown
# WORKFLOW_AUTO.md — Reply-To-Sender (single owner / CLIENT box)

## Routing
- This is a single-client box. Reply ONLY to the sender of each incoming message.
- Do NOT spawn per-person operator worker sub-agents. There is no operator team on this box.

| Telegram Chat ID | Role | Lane |
|---|---|---|
| {{OWNER_CHAT_ID}} | Owner (the client) | serve directly |

## Reply Rules
- Reply ONLY to the originating sender's DM.
- Directed sends are always allowed: if the owner says "send [person] X," execute it.
- No proactive sends to operator IDs. Operator inbound access is handled by the
  separate remote-rescue agent — not by routing on this `main` agent.

## Notes
- {{OWNER_NAME}} is the CLIENT — serve respectfully; the AI never assigns them tasks.
```

**OPERATOR box ONLY (`IS_OPERATOR_BOX=1`):** use the multi-member dispatcher
routing table instead (one row per operator: Sender ID / Name / Role / Worker
Label / Reply To, plus Worker Config + Dispatcher rules). Do NOT use the operator
dispatcher table on a client box.

Replace all placeholder brackets with the real data from TEAM_CONFIG.md. Save file.

---

## Step 6: Add Routing to AGENTS.md

**CLIENT box (default):** open ~/clawd/AGENTS.md and add the owner-only
reply-to-sender block (replace `{{OWNER_CHAT_ID}}` / `{{OWNER_NAME}}` with the
client owner's real values):

```markdown
## Telegram Routing — Reply-To-Sender (single owner)
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Team config: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
- This is a single-client box. Reply ONLY to the sender of each incoming message.
- Do NOT spawn per-person operator worker sub-agents. There is NO operator team on this box.

### Owner (the client)
| Name | Telegram ID | Role | Lane |
|------|-------------|------|------|
| {{OWNER_NAME}} | {{OWNER_CHAT_ID}} | Owner (the client) | serve directly |

### Reply Rules
- Reply ONLY to the originating sender's DM.
- Directed sends are always allowed when the owner asks ("send [person] X").
- NEVER proactively message an operator ID. Operator (BlackCEO) inbound access is
  handled by the separate `remote-rescue` agent — not by routing on `main`.
```

**OPERATOR box ONLY (`IS_OPERATOR_BOX=1`):** instead add the full
"Team Management - Dispatcher Protocol" block with the multi-member operator
roster and dispatcher rules (route by sender ID to per-person worker sub-agents).
Do NOT add the operator dispatcher block on a client box.

Save file.

---

## Step 7: Add Routing to TOOLS.md

**CLIENT box (default):** open ~/clawd/TOOLS.md and add:

```markdown
## Message Routing — Reply-To-Sender (single owner)
- WORKFLOW_AUTO.md: ~/clawd/WORKFLOW_AUTO.md (owner-only routing table)
- Team config: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
- Reply only to the sender. To send to a specific person when the owner asks,
  use the message tool with target = that person's Telegram ID.
- NEVER proactively send to an operator ID — there is no operator team on this box.
```

**OPERATOR box ONLY (`IS_OPERATOR_BOX=1`):** add the "Team Dispatcher - Message
Routing" block referencing the multi-member roster instead.

Save file.

---

## Step 8: Add Routing to MEMORY.md

**CLIENT box (default):** open ~/clawd/MEMORY.md and add (replace
`{{OWNER_CHAT_ID}}` / `{{OWNER_NAME}}` with real values):

```markdown
## Telegram Routing — Owner-Only (Reply-To-Sender)
| Name | Telegram ID | Role |
|------|-------------|------|
| {{OWNER_NAME}} | {{OWNER_CHAT_ID}} | Owner (the client) |
- Single-client box: reply ONLY to the sender. No operator team is routed here.
- Operator inbound access is via the remote-rescue agent (Step 0.5), never as a worker.
- Routing protocol: ~/clawd/WORKFLOW_AUTO.md
- Team config: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
```

**OPERATOR box ONLY (`IS_OPERATOR_BOX=1`):** add the multi-member
"Team Telegram IDs (Dispatcher Protocol)" table instead.

Save file.

---

## Step 9: Validate JSON Syntax

Execute:
```bash
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
```

Expected: No output (JSON is valid).
If error message appears: JSON contains syntax error. Fix before continuing.

---

## Step 10: Restart OpenClaw Gateway

Execute:
```bash
openclaw gateway restart
```

Wait 10 seconds for restart to complete.

---

## Step 11: Verify Gateway Running

Execute:
```bash
openclaw gateway status
```

Expected: Output contains "running".
If output shows "stopped" or error: Investigate and resolve before proceeding.

---

## Step 12: Test Routing

Send a test message from each team member's Telegram account to the bot.

Observe: Dispatcher creates dedicated worker for each sender.

---

## Step 13: Verify Message Isolation

### 13A: Intra-owner isolation (dispatcher/worker layer)

Confirm:
- Each sender receives response ONLY in their own DM
- No messages leak between senders
- Workers created with correct labels
- No cross-posting between DMs

### 13B: Operator-owner session isolation (HARD gate -- must pass before calling skill complete)

```bash
python3 - <<'EOF'
import json, os
cfg_candidates = [os.path.expanduser("~/.openclaw/openclaw.json"), "/data/.openclaw/openclaw.json"]
cfg_path = next((p for p in cfg_candidates if os.path.exists(p)), None)
if not cfg_path:
    print("FAIL -- cannot locate openclaw.json"); raise SystemExit(1)
cfg = json.load(open(cfg_path))
op_ids = {"5252140759", "6663821679", "6771245262"}
group_allow = set(cfg.get("channels", {}).get("telegram", {}).get("groupAllowFrom") or [])
leak = op_ids & group_allow
if leak:
    print(f"ISOLATION FAIL -- operator IDs in groupAllowFrom: {leak}"); raise SystemExit(1)
agents = cfg.get("agents", {}).get("list", [])
rr = next((a for a in agents if a.get("id") == "remote-rescue"), None)
if not rr or not rr.get("workspace") or not rr.get("telegram", {}).get("allowFrom"):
    print("ISOLATION FAIL -- remote-rescue missing workspace or telegram.allowFrom"); raise SystemExit(1)
main_agent = next((a for a in agents if a.get("id") == "main"), None)
main_bound = set((main_agent or {}).get("telegram", {}).get("allowFrom") or [])
if op_ids & main_bound:
    print(f"ISOLATION FAIL -- operator IDs bound to main agent"); raise SystemExit(1)
print("PASS -- operator/owner session isolation verified")
EOF
```

HARD FAIL: if this gate fails, the operator/owner session isolation is broken. Fix via `--repair` before proceeding.

---
## Step 14: (OPT-IN) Completion Confirmation to the Operator

**Send this confirmation ONLY if an operator escalation chat is configured. If
`$OPERATOR_CHAT_ID` resolves empty (the safe client-box default), SKIP this step —
do NOT send to any hardcoded chat.**

After Steps 1-13 are complete, resolve the operator escalation destination via the
shared helper. It reads `env.vars.OPERATOR_ESCALATION_CHAT_ID` (back-compat:
`OPERATOR_TELEGRAM_CHAT_ID`) and returns EMPTY if none is configured — there is NO
hardcoded personal-chat default:

```bash
source ~/.openclaw/skills/shared-utils/operator-chat-id.sh
# $OPERATOR_CHAT_ID is now populated (may be EMPTY).
if [ -z "$OPERATOR_CHAT_ID" ]; then
  echo "operator escalation chat not configured — skipping completion confirmation (opt-in only)"
fi
```

If `$OPERATOR_CHAT_ID` is non-empty, send the confirmation to it. Otherwise skip.

The message must include:

1. The exact Telegram IDs that were added to allowFrom (read them back from openclaw.json to confirm they are really there — do not assume)
2. The names matched to those IDs
3. A statement that the gateway was restarted and is running
4. Any IDs that could NOT be added and why

Example message format:
```
Skill 15 complete. Here is what was configured:

Telegram IDs now approved in allowFrom:
- [Name 1]: [ID 1]
- [Name 2]: [ID 2]
- [Name 3]: [ID 3]

Gateway restarted and running. All team members above can now message the bot.

[List any issues or IDs that were skipped]
```

Send it:
```bash
openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "<the message above>"
```

**Read the IDs back from the actual openclaw.json file before sending.** Do not write from memory. Verify they are actually in the file, then report.

If you cannot send the confirmation message, write it to ~/clawd/memory/skill-15-completion.md and tell the operator to check that file.

---

## Configuration Safety Rules

When making configuration changes for client deployments:

1. **Always announce** the intended change to the operator in plain language before making it
2. **Always back up** the current config before editing (Step 1 above)
3. **Always validate** the JSON after editing (Step 9 above)
4. **Always get explicit permission** from the operator before writing changes
5. **Never guess** about config fields - look them up in the OpenClaw docs first
6. If backup fails, STOP. Do not edit.
7. If validation fails, revert from backup immediately.

---

## Deployment Checklist (New Client)

Use this checklist when setting up this protocol for a new client:

```
[ ] Run Step 0 intake - collect all team member names, IDs, roles, types
[ ] Run Step 0.5 — operator chat ID + Remote Rescue install
[ ] Copy this SOP to client's master files
[ ] Copy WORKFLOW_AUTO.md template to client's workspace
[ ] Generate TEAM_CONFIG.md with client's actual team data
[ ] Add all collected IDs to channels.telegram.allowFrom
[ ] Mark client principals as "Client (NOT a worker)" in routing table
[ ] Add any additional team members as workers
[ ] Set sub-agent model chain (primary + fallbacks with tool-call support)
[ ] Set archiveAfterMinutes: 43200 (30 days)
[ ] Back up config, validate JSON, restart gateway
[ ] Test: send message from each team member, confirm routing + DM isolation
[ ] Confirm no cross-posting between DMs
```

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
