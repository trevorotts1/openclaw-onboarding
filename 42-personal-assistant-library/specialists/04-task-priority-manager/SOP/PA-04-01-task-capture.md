# PA-04-01 — Task Capture

**Department:** Task & Priority Management (04)
**SOP Type:** Core Process
**DMAIC Phase:** Measure
**Last Updated:** 2026-06-02

---

## Purpose

Capture every task, request, idea, and commitment reaching {{TOKEN}} into a single trusted system — immediately, completely, with enough context to action later.

## DMAIC Section 3 — Measure (Current-State Task Intake)

### 3.1 Intake Channels

| Channel | Volume (Est.) | Leak Risk | Capture Method |
|---|---|---|---|
| Email ({{OWNER_EMAIL}}) | 40-80/day | Medium | Extract action items, log in task manager |
| Telegram / Direct Messages | 15-30/day | High | Real-time capture via bot integration |
| Slack | 10-20/day | Medium | Flag actionable messages |
| Meetings (Zoom / in-person) | 5-15/week | Very High | Post-meeting extraction; validate with {{TOKEN}} |
| Voice notes / verbal requests | 5-10/day | Very High | Transcribe → extract → confirm |
| Self-generated ideas | 3-8/day | High | Direct entry or prompted capture |
| Automated triggers (cron, webhooks, alerts) | Variable | Low | Auto-log with structured metadata |
| Convert and Flow / CRM | 5-15/day | Medium | Extract from pipeline events |

### 3.2 Capture Gap Analysis

Primary loss: task enters one channel, expected elsewhere. Secondary loss: vague descriptions that resist categorization.

### 3.3 The Capture Standard

Every captured task must include:
1. **What** — actionable description (verb + object: "Review {{CLIENT_NAME}}'s proposal")
2. **Source** — where it came from (email, meeting, voice note)
3. **When captured** — timestamp
4. **Deadline (if known)** — or a "needs deadline" flag
5. **Priority signal** — initial urgency/importance estimate
6. **Context link** — reference to the original message, document, or recording

### 3.4 Inbox Zero vs. Task Zero

The capture inbox is a holding tank, not a to-do list. Capturing = committing to DECIDE, not to do. Decisions happen in PA-04-02 and PA-04-05.

### 3.5 Capture Prompts

Proactively prompt {{TOKEN}} at natural gaps:
- End of meeting: "I captured X and Y — anything else?"
- End of day: "Quick capture check — anything on your mind?"
- Monday morning: "Let's sweep for weekend ideas."

## Success Criteria
- 100% of meeting action items captured within 30 minutes
- No task cited by {{TOKEN}} as "I thought I told you about that"
- Capture-to-system: under 5 minutes (digital), under 2 hours (verbal/meeting)

---

## CTQ Checks

- [ ] Every meeting action item captured within 30 minutes of meeting end
- [ ] Every captured task has all 6 required fields: what, source, timestamp, deadline/flag, priority signal, context link
- [ ] Zero tasks cited by {{TOKEN}} as "I thought I told you about that" — full capture confidence
- [ ] Capture prompts delivered at natural gaps: post-meeting, end-of-day, Monday morning
- [ ] Digital-channel tasks captured within 5 minutes; verbal/meeting tasks captured within 2 hours

## Definition of Done

Every task, request, idea, and commitment that reaches {{TOKEN}} through any channel is captured into {{TASK_TOOL}} with complete metadata — nothing exists only in someone's memory.

## Escalation

- **Specialist 01 (Inbox Manager)** — if email action items were missed during triage and need retroactive capture
- **Specialist 05 (Meeting Assistant)** — if meeting action items differ from what was logged
- Escalate to {{TOKEN}} — if a captured task is too vague to action and needs the owner to clarify what "done" looks like

## Tone & Persona Note

Give {{TOKEN}} an empty mental desktop. Every captured commitment is one less thing they carry. Be thorough but never overwhelming. Prompts should feel like a gentle ritual, not an interrogation.
