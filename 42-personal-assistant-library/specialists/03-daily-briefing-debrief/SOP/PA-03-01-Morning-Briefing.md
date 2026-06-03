# PA-03-01 — Morning Briefing

| Field | Value |
|---|---|
| **SOP ID** | PA-03-01 |
| **Title** | Morning Briefing |
| **Version** | 1.0 |
| **Department** | Daily Briefing & Debrief (Specialist 3) |

## Purpose
Deliver a prioritized snapshot of {{OWNER_NAME}}'s day every morning so they begin with focus, not reactive scrambling.

## Trigger & Inputs
Fires 6:00–8:00 AM {{OWNER_TIMEZONE}} each workday. Inputs: calendar ({{CALENDAR_TOOL}}), tasks ({{TASK_TOOL}}), overnight messages ({{INBOX_TOOL}}), yesterday's debrief, {{OWNER_NAME}}'s priorities if shared.

## Define / Measure / Analyze
**Problem:** {{OWNER_NAME}} starts mornings reacting to whatever is loudest — important work gets crowded out. **Root causes:** no pre-work landscape review, inbox-first behavior, no visible top-3, no link between yesterday's loops and today. **Track:** clear-priority starts, reactive vs. intentional time.

## Improve

Follow these steps every morning:

1. **Pull the landscape.** Open {{CALENDAR_TOOL}} and {{TASK_TOOL}}. Note every scheduled event, every active task with a deadline, and any items flagged urgent. Pull the previous evening's debrief for open loops.

2. **Identify the Top 3 priorities.** From all inputs, select the three items that create the most value if completed today. One should be the "if nothing else gets done" item.

3. **Check for friction.** Scan the calendar for: back-to-back meetings with no breaks, prep gaps, double-bookings, or timezone mismatches.

4. **Add energy context.** Note anything affecting {{OWNER_NAME}}'s capacity: a late finish yesterday, travel, a high-stakes meeting, or a lighter day suited for deep work.

5. **Draft the briefing** in a consistent, scannable format:
   - **Today's landscape:** 1-line weather report ("Light day — 2 meetings, 3 focus blocks")
   - **Top 3 priorities:** Numbered, with one sentence of context each
   - **Schedule highlights:** Key meetings with time, attendees, and prep status
   - **Watch list:** Deadlines, urgent messages, or decisions needed today
   - **Energy note:** One sentence of encouragement or awareness

6. **Deliver.** Send via {{MESSAGING_TOOL}}. Keep it under a screen of text — scannable in 60 seconds or less.

## Control
Maintain 30-day archive. Weekly: check Top-3 completion; below 60% = tighten. Monthly: ask {{OWNER_NAME}} for format changes.

## CTQ (Critical to Quality) — Binary Checks

- [ ] Briefing delivered within the 6:00–8:00 AM {{OWNER_TIMEZONE}} window
- [ ] Top 3 priorities are specific, actionable, and not just "check email"
- [ ] Every meeting on today's calendar is acknowledged (even if "no prep needed")
- [ ] At least one item connects to yesterday's carryover or a larger goal
- [ ] Briefing is scannable in 60 seconds or less

## Metrics

| Metric | Target |
|---|---|
| On-time delivery rate | ≥ 95% of workdays |
| Top-3 completion rate | ≥ 70% |
| {{OWNER_NAME}} satisfaction | ≥ 8/10 |
| Briefing read rate | ≥ 90% |

## Escalation

Escalate to {{OWNER_NAME}} immediately when: a critical deadline is being missed today, a high-stakes meeting lacks prep materials, an urgent overnight message requires a same-morning response, or the calendar shows a triple-booking. Flag with "Action Needed" and your recommended fix.

**Partner escalation:**
- **Specialist 01 (Inbox Manager)** — if an urgent overnight email requires VIP-level handling before the briefing is consumed
- **Specialist 04 (Task & Priority Manager)** — if Top-3 priorities conflict with deadlines flagged as today-critical

## Definition of Done

A morning briefing is complete when: all five CTQ checks pass, the briefing has been sent to {{OWNER_NAME}} via {{MESSAGING_TOOL}}, and a copy has been logged for pattern tracking. Done means {{OWNER_NAME}} can open one message and know exactly how to win the day.
