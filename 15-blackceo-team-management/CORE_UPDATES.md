# BlackCEO Team Management Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

TYP RULE: Add LEAN SUMMARIES + FILE PATH POINTERS to core files only.
Full protocol content lives in:
~/Downloads/[master-files-folder]/OpenClaw Onboarding/15-blackceo-team-management/blackceo-team-management-full.md
Team config lives in: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md

---

> 🔴 CO-MINGLING GUARD (v12.4.0): the blocks below are the CLIENT-box defaults —
> reply-to-sender + owner-only. The BlackCEO operator team (Trevor / LeAnne /
> Spaulding) must NEVER be stamped here as routable "workers." Operators get
> INBOUND access via the separate remote-rescue agent (Skill 15 Step 0.5). The
> multi-member operator "Dispatcher Protocol" block is OPERATOR-BOX ONLY
> (IS_OPERATOR_BOX=1) — see INSTALL.md Step 0c. Replace {{OWNER_CHAT_ID}} /
> {{OWNER_NAME}} with the client owner's real values.

## AGENTS.md - UPDATE REQUIRED

Add (CLIENT box — reply-to-sender, owner-only):

```
## Telegram Routing - Reply-To-Sender (single owner) [PRIORITY: CRITICAL]
- This is a single-client box. Reply ONLY to the sender of each incoming message.
- Do NOT spawn per-person operator worker sub-agents. There is NO operator team on this box.
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Routing config (source of truth): ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md

### Owner (the client)
| Name | Telegram ID | Role | Lane |
|------|-------------|------|------|
| {{OWNER_NAME}} | {{OWNER_CHAT_ID}} | Owner (the client) | serve directly |

### Reply Rules
- Reply ONLY to the originating sender's DM.
- Directed sends are ALWAYS allowed: if the owner says "send [name] a message" or "tell [person] X," execute the Telegram send immediately.
- NEVER proactively message an operator ID from this `main` agent. Operator
  (BlackCEO) inbound access is the remote-rescue agent's job, not this routing.
```

---

## TOOLS.md - UPDATE REQUIRED

Add (CLIENT box — reply-to-sender, owner-only):

```
## Message Routing - Reply-To-Sender (single owner)
- WORKFLOW_AUTO.md: ~/clawd/WORKFLOW_AUTO.md (owner-only routing table)
- Routing config: ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
- Reply only to the sender. To send to a specific person when the owner asks,
  use the message tool with target = that person's Telegram ID.
- NEVER proactively send to an operator ID — there is no operator team on this box.
```

---

## MEMORY.md - UPDATE REQUIRED

Add (CLIENT box — reply-to-sender, owner-only):

```
## Telegram Routing - Owner-Only (Reply-To-Sender) - Installed [DATE]
- Single-client box: reply ONLY to the sender. No operator team is routed here.
- Operator (BlackCEO) inbound access is via the remote-rescue agent (Step 0.5), never as a worker.
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Routing config (source of truth): ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md

### Owner (the client)
| Name | Telegram ID | Role |
|------|-------------|------|
| {{OWNER_NAME}} | {{OWNER_CHAT_ID}} | Owner (the client) |
```

---

## OPERATOR BOX ONLY (IS_OPERATOR_BOX=1)

The multi-member BlackCEO "Dispatcher Protocol" core-file blocks (Main session =
dispatcher; per-person worker sub-agents; cross-worker visibility; the operator
roster table) belong ONLY on BlackCEO's own internal operator box. Do NOT add
them to a client box. See blackceo-team-management-full.md sections 15 and INSTALL.md
Step 0c for the operator-box variant.

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

(Team routing is session-aware via AGENTS.md. No heartbeat entry required.)

---

## USER.md - NO UPDATE NEEDED

(Team member data lives in TEAM_CONFIG.md, not USER.md. USER.md is for the primary operator only.)

---

## SOUL.md - NO UPDATE NEEDED
