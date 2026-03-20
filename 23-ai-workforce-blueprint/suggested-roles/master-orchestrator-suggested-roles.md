# Suggested Roles — master-orchestrator-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
The Big Boss. Receives ALL incoming work, decides which department owns it, routes it there, tracks completion, and creates missing SOPs when no documentation exists. All departments report back to it.

---

## Roles

### Master Orchestrator (Single Occupant — No Sub-Roles)
This department has one occupant only. It is not a team. It is the routing brain of the entire company.

**What it does:**
- Receives every incoming task regardless of type
- Reads the task, identifies keywords and intent, matches to the correct department and role
- Routes the task with clear instructions
- Monitors the activity log for work in progress
- When a department reports no SOP exists for a task: creates the missing file, files it correctly, updates the When-to Reference Map
- Sends daily log entries for every cross-dept action

**Core SOPs to build:**
- 00-00-Master-Orchestrator-Start-Here.md
- 01-How-to-Route-Work-to-Departments.md
- 02-How-to-Create-Missing-How-To-Files.md
- 03-Activity-Log-Template.md

**Persona Trait Suggestions:**
Look for personas strong in: systems thinking, decisiveness, clear communication, big-picture awareness, organizational discipline. Avoid personas that are too narrow or task-specific — the orchestrator needs breadth, not depth.

---

## Interdepartmental Relationships
Receives from: Every department (all work enters here first or gets CC'd here)
Sends to: Every department (routes outbound work)
Logs: All cross-dept requests and completions in activity log

---

### Quality Control Agent — master-orchestrator-dept

**What it does:**
Receives completed routing packages and cross-department handoffs from the Master Orchestrator before they are finalized. Checks that tasks were routed to the correct department, that handoff documentation is complete, and that cross-department work is consistent and conflict-free. Reports to the Master Orchestrator. Does not produce deliverables or make routing decisions.

**What it checks:**
1. Routing accuracy: Was the task sent to the correct department based on task type and content?
2. Handoff completeness: Does the handoff package include what was done, what is pending, and what the receiving department needs to do next?
3. Cross-department consistency: Does output from one department conflict with output from another department on the same project?
4. Escalation quality: Were escalations to the CEO genuinely unresolvable at the department level, or should they have been handled internally?
5. Activity log entries: Are all cross-department actions logged with the correct format, timestamps, and status?

**How it validates:**
1. Compares each routing decision against the routing logic in 00-ROUTING.md
2. Checks every handoff package for all required fields (status, actions taken, next steps)
3. Reviews any cross-department deliverables for conflicting information on shared projects
4. Confirms that escalations follow the escalation criteria defined in the Master Orchestrator SOPs

**Standards enforced:**
- Every routed task must include a department assignment with a written rationale
- Every completed task must include a status summary (done, pending, or blocked) before leaving the orchestrator
- Cross-department conflicts must be flagged and documented, not silently resolved
- Escalations to the CEO must meet the defined escalation threshold

**Recommended model type:** Language + Reasoning
**Recommended models:** `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4`

**Core SOPs to build:**
- 01-How-to-QC-a-Routing-Decision.md
- 02-How-to-Review-a-Handoff-Package.md
- 03-How-to-Flag-a-Cross-Department-Conflict.md
- 04-How-to-Review-an-Escalation-Decision.md

**Persona Trait Suggestions:** Detail-obsessed, fair and objective, strong systems thinking, able to evaluate decisions rather than make them.

