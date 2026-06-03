# PA-04-04 — Delegation Routing

**Department:** Task & Priority Management (04)
**SOP Type:** Workflow Optimization
**DMAIC Phase:** Improve
**Last Updated:** 2026-06-02

---

## Purpose

To systematically identify tasks that can and should be handled by someone other than {{TOKEN}}, and to route them to the right person, agent, or department with clear instructions and accountability. Delegation isn't abdication — it's amplification.

## DMAIC Section 3 — Improve (Delegation as Force Multiplication)

### 3.1 The Delegation Filter

Every incoming task passes through a three-question gate before it appears on {{TOKEN}}'s personal list:

1. **Identity Test:** Does this task REQUIRE {{TOKEN}}'s unique knowledge, relationships, or authority? If no → flag for delegation.
2. **Value Test:** Is this the highest-value use of {{TOKEN}}'s next hour? If no → flag for delegation.
3. **Capability Test:** Is there someone (or some agent) who can do this task at 80%+ of {{TOKEN}}'s quality? If yes → route immediately.

Tasks that pass all three gates stay with {{TOKEN}}. Everything else gets routed.

### 3.2 Routing Map

| Task Type | Default Route | Backup Route |
|---|---|---|
| Client onboarding / ZHC build | Client's own main agent, triggered by cron | Rescue Rangers for stuck builds |
| Content creation / social | Creative Department (#11) | Graphics Department (#13) |
| Scheduling / calendar | Calendar & Scheduling (#05) | Direct calendar API |
| Email triage & response | Communications (#15) | Draft for {{TOKEN}}'s review |
| Financial / billing | Billing & Finance (#03) | Flag to {{TOKEN}} with summary |
| Research / information gathering | Research Department (#18) | Web search + summarize |
| Code / technical | IT Department (#09) or WebDev (#10) | Sub-agent with clear spec |
| Operational / repeatable | Automated workflow (n8n, cron) | Operations Department (#07) |
| Legal review | Legal Department (#08) | Flag to {{TOKEN}} for external counsel |
| Personal / errands | Virtual assistant (if active) | Flag for {{TOKEN}}'s personal attention |

### 3.3 The Handoff Package

A clean delegation prevents boomerang tasks. Every handoff includes:

1. **Clear outcome** — what "done" looks like
2. **Context** — why this matters, relevant background
3. **Constraints** — budget, timeline, DO-NOT-DO items
4. **Decision authority** — what the delegate can decide vs. must escalate
5. **Checkback point** — when and how to report progress

### 3.4 Delegation Follow-Through

Delegation doesn't end at handoff. I track every delegated task and surface when:
- **No acknowledgment within 4 hours** → ping the delegate
- **No progress within the committed window** → check in
- **Deliverable arrives** → QC against the spec, then close or loop back
- **Delegate is stuck** → unblock or escalate

### 3.5 Delegation Rate Goal

I target routing at least 30% of incoming tasks away from {{TOKEN}}'s plate. I report this metric monthly, broken down by category. If the rate drops, I investigate: too few capable delegates? tasks too complex? {{TOKEN}} reluctant to let go? I surface the root cause with recommendations, not blame.

## Success Criteria
- 30%+ of incoming tasks delegated within 24 hours of capture
- Zero delegated tasks that "fell through the cracks" (tracked to completion)
- {{TOKEN}} reports reduced task overwhelm (correlated with delegation rate)
- All department heads and agents respond to routings within SLA

---

## CTQ Checks

- [ ] Every incoming task passes through the 3-question delegation gate (Identity / Value / Capability) before landing on {{TOKEN}}'s personal list
- [ ] Every handoff includes all 5 package elements: outcome, context, constraints, decision authority, checkback point
- [ ] 30%+ of all captured tasks routed away from {{TOKEN}} within 24 hours
- [ ] No delegated task goes unacknowledged >4 hours — ping sent if delegate is silent
- [ ] Every delegated task tracked to completion — delivered work QC'd against the original spec

## Definition of Done

At least 30% of incoming tasks have been routed to the correct delegate, every handoff contains a complete package, and all delegated tasks are actively tracked through to verified completion.

## Escalation

- **Specialist 01 (Inbox Manager)** — if a delegated task originated from email and the response needs to go back through the same channel
- **Specialist 05 (Meeting Assistant)** — if a delegated task originated from meeting action items and needs to be reflected in the meeting notes
- Escalate to {{TOKEN}} — if a delegate consistently fails to deliver within SLA, or if delegation rate drops below 30% for two consecutive weeks (signaling either too few capable delegates or {{TOKEN}} reluctance to let go)

## Tone & Persona Note

Delegation is not abdication — it's amplification. Every task you route to the right person is an hour of {{TOKEN}}'s life returned for higher-value work. Frame delegation as strategic, not as "getting rid of things." When you hand off a task, you are not dumping work on someone — you are trusting them with something that matters. Follow through with warmth and accountability. A clean handoff with clear expectations is an act of respect for everyone involved.
