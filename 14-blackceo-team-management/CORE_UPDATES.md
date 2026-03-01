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
- Workers are isolated from each other
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/14-blackceo-team-management/blackceo-team-management-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## BLACK CEO Dispatcher - Message Routing
- WORKFLOW_AUTO.md: ~/clawd/WORKFLOW_AUTO.md (routing table)
- To send to specific person: message tool with target = their Telegram ID
- Worker results go ONLY to the requesting DM
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/14-blackceo-team-management/blackceo-team-management-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## BLACK CEO Team Management - Installed [DATE]
- Dispatcher architecture configured
- Routing table: ~/clawd/WORKFLOW_AUTO.md
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/14-blackceo-team-management/blackceo-team-management-full.md
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
