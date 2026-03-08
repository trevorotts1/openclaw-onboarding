# BlackCEO Team Management Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## BLACK CEO Team - Dispatcher Protocol [PRIORITY: CRITICAL]
- Main session = dispatcher. Each person gets a dedicated worker sub-agent.
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Dispatcher has full cross-worker visibility via sessions_history
- Workers operate in isolated context windows. No conversation data from one worker bleeds into another.
- Workers CAN send directed Telegram messages to any ID when explicitly asked. There is no messaging lockdown - only context isolation.
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/15-blackceo-team-management/blackceo-team-management-full.md

### Contact Directory (Outbound - People We Message)
| Name | Telegram ID | Notes |
|------|-------------|-------|
(Add entries as contacts are discovered)
When sending to someone not in the routing table, check here. If not found, ask once, then save.

### Context Isolation Rule (NOT Communication Lockdown)
- Worker conversation data is STRICTLY isolated per worker. One worker's context NEVER leaks to another.
- Directed sends are ALWAYS allowed: if any team member says "send [name] a message" or "tell [person] X," execute the Telegram send immediately.
- "Cross-posting" means auto-sharing results without being asked. It does NOT mean blocking directed sends.
- Workers CAN use the message tool to send to any Telegram ID when explicitly asked.
- Workers CANNOT read, reference, or expose another worker's conversation history.
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## BLACK CEO Dispatcher - Message Routing
- WORKFLOW_AUTO.md: ~/clawd/WORKFLOW_AUTO.md (routing table)
- To send to specific person: message tool with target = their Telegram ID
- Worker results go ONLY to the requesting DM
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/15-blackceo-team-management/blackceo-team-management-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## BLACK CEO Team Management - Installed [DATE]
- Dispatcher architecture configured
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Context isolation: Workers have isolated context windows (no data bleed between workers). Workers CAN send directed messages to any Telegram ID when explicitly asked - isolation is context only, not communication lockdown.
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/15-blackceo-team-management/blackceo-team-management-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - UPDATE REQUIRED

Add:

```
## Team Management
- Dispatcher monitors incoming Telegram messages and routes to correct worker
- Check WORKFLOW_AUTO.md for routing rules
```

---

## USER.md - UPDATE REQUIRED

Add:

```
## Team Members
- Telegram IDs and roles are in WORKFLOW_AUTO.md routing table
- Each team member gets a dedicated worker sub-agent
```

---

## SOUL.md - NO UPDATE NEEDED
