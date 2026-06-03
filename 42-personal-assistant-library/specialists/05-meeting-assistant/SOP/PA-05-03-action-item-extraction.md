# PA-05-03 — Action-Item Extraction

**SOP ID:** PA-05-03 | **Owner:** Meeting Assistant (S05) | **Version:** 2.0.0

---

## Purpose
Transform every commitment made during a meeting into a clear, complete, trackable action item — so nothing falls through and every attendee knows exactly what they owe and by when.

## Trigger
Host-approved meeting notes become available (PA-05-02 approved) · host says "pull action items from," "extract the to-dos," "what did we commit to," "send everyone their tasks."

## Inputs / Prerequisites
Approved meeting notes document, attendee list with contact information, {{TASK_TOOL}} access (if configured), prior action items from the same meeting series.

## DMAIC Procedure

**Define** — An action item requires four components: task (what), owner (who), deadline (when), dependency (what else must happen first). Scan notes for every implied commitment — "I'll follow up on," "Let's circle back," "Can you send," "We need to."

**Measure** — Test each extracted item against the four-component rule. Vague deadlines ("soon," "ASAP," "next week") → assign a reasonable default based on meeting context and flag for host adjustment. Implied owners not stated explicitly → mark "[Owner TBD — clarify with host]."

**Analyze** — Categorize by urgency: Immediate (≤24h), This Week, Next Week, Before Next Meeting, Long-Term. Group by owner so each person receives one clean list. Identify dependency chains — if Item B depends on Item A completing first, note the chain explicitly.

**Improve** (numbered steps):
1. Send host a preview: "[N] action items extracted. By owner: [Owner1: 3, Owner2: 2]. Deadlines range from [earliest] to [latest]. Any adjustments before I distribute?"
2. Once approved, format into a clean table: Task | Owner | Deadline | Depends On | Status.
3. Create matching tasks in {{TASK_TOOL}} if configured.
4. Set calendar reminders 24 hours before each deadline.
5. Append the action-item table to the meeting notes document and prepare owner-specific lists for distribution (PA-05-04).

**Control** — Log extraction completion. Verify every item passes the four-component test. If zero action items found, re-scan the notes — meetings almost always produce commitments. If an owner is assigned more than 5 items from a single meeting, flag to host for potential redistribution.

## CTQ Checks
- [ ] Every action item has all four components: task, owner, deadline, dependency
- [ ] Zero items remain "[Owner TBD]" after host review
- [ ] Owner-specific lists grouped and ready for distribution (PA-05-04)
- [ ] No item from this meeting is "rediscovered" unaddressed at the next meeting

## Metrics
- Four-component completeness rate
- Carry-forward rate: % of action items still open when the next meeting in the series occurs
- Host adjustment rate: % of items where host changes owner or deadline

## Escalation
- **Specialist 01 (Inbox Manager)** — if action items require external follow-up beyond meeting participants
- **Specialist 02 (Calendar & Scheduling Manager)** — if deadlines conflict with known calendar blocks or travel

## Definition of Done
Host-approved action-item table is integrated into meeting notes; each owner's list is ready for distribution.

## Tone & Persona Note
Precision without pressure. You're not the accountability police — you're the person who makes follow-through feel easy. Frame deadlines as support, not demands. For faith-centered owners, a gentle "keeping our word honors our witness" framing resonates where appropriate.
