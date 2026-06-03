# PA-02-05 — Reschedule & Cancellation

| Field | Value |
|---|---|
| **SOP ID** | PA-02-05 |
| **Title** | Reschedule & Cancellation |
| **Version** | 1.0 |
| **Department** | Calendar & Scheduling (Specialist 2) |

## Purpose
Handle reschedules and cancellations with speed and grace — preserving relationships and {{OWNER_NAME}}'s reputation.

## Trigger & Inputs
A meeting needs moving/canceling — {{OWNER_NAME}} initiates, an attendee requests, or an external event forces it. Inputs: original event, reason, {{CALENDAR_TOOL}} for new slots, communication history.

## Diagnose
**Problem:** Last-minute changes cascade into disruptions, handled reactively. **Root causes:** slow acknowledgment, alternatives not offered immediately, related tasks not updated, transactional tone. **Track:** reschedule frequency within 24h, follow-up rounds to land new time.

## Improve

1. **Acknowledge immediately.** The moment you know a change is needed, acknowledge it to all parties. Speed matters more than perfect wording. "Just got word we need to shift our Thursday time — let me find an option that works and I'll be right back with you."

2. **Assess the relational stakes.** Is this a one-time vendor call or a key client relationship? The level of warmth and personalization scales accordingly. For high-stakes relationships, {{OWNER_NAME}} may want to send a personal note — offer to draft one.

3. **For reschedules: propose specific alternatives immediately.** Don't just say "let's find a new time" — open {{CALENDAR_TOOL}}, check availability applying all protection rules (PA-02-03), and offer 2-3 concrete options in your next message. "Here are three windows that work: Friday at 10 AM, Monday at 1 PM, or Tuesday at 3 PM Eastern."

4. **For cancellations: close the loop cleanly.** Confirm the cancellation, remove the event from {{CALENDAR_TOOL}}, cancel any related prep brief or reminder tasks in {{TASK_TOOL}}, and — if the meeting was important — offer to reconnect when timing is better. "No problem at all. I've cleared it from the calendar, and just say the word when you'd like to reschedule."

5. **Update all connected systems.** Remove the old event from {{CALENDAR_TOOL}}. Create the new event if rescheduled. Update or delete the prep brief and confirmation tasks in {{TASK_TOOL}}. If other meetings depended on this one, adjust those too.

6. **Log the change.** Brief note: what moved, why (if known), and any relational flags. Patterns emerge — the same stakeholder always reschedules? A particular time slot keeps getting bumped? Logging enables prevention.

7. **For {{OWNER_NAME}}-initiated changes: protect their reputation.** When {{OWNER_NAME}} needs to cancel or move, take the relational heat. Frame it warmly: "{{OWNER_NAME}} sends their sincere apologies — an urgent priority came up. They really value this conversation and want to give it proper attention, so they'd love to reschedule for a time when they can be fully present."

## Control
Verify old event gone, new event exists, no new conflict. Weekly: review log for patterns.

## CTQ (Critical to Quality) — Binary Checks

- [ ] All parties acknowledged within 30 minutes of change decision
- [ ] For reschedules: 2-3 specific alternative times proposed in the same communication thread
- [ ] Old event removed from {{CALENDAR_TOOL}}; new event created with all original details preserved
- [ ] Related {{TASK_TOOL}} items (prep brief, confirmation) updated or deleted
- [ ] Change logged for pattern analysis

## Metrics

| Metric | Target |
|---|---|
| Reschedule landed in ≤ 2 message rounds | ≥ 85% |
| Stakeholder acknowledgment within 30 min | 100% |
| Orphaned calendar events | 0 |

## Escalation

Escalate to {{OWNER_NAME}} when: a VIP stakeholder reacts negatively to a change, you need to cancel a meeting {{OWNER_NAME}} hasn't approved canceling, or the change creates a cascade affecting multiple high-priority commitments.

**Partner escalation:**
- **Specialist 05 (Meeting Assistant)** — if the rescheduled meeting needs rebuilt agenda, new action items, or attendee re-notification
- **Specialist 03 (Daily Briefing & Debrief)** — if the reschedule changes the daily/weekly landscape enough for an updated briefing

## Definition of Done

A reschedule or cancellation is complete when: all parties are notified, the calendar event is updated or removed, all related {{TASK_TOOL}} tasks are synchronized, no downstream conflicts exist, and the change is logged.
