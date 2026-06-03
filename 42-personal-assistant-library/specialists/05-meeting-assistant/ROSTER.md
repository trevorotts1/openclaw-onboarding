# ROSTER — Meeting Assistant

## Owner

| Field | Value |
|---|---|
| **Name** | {{OWNER_NAME}} |
| **Email** | {{OWNER_EMAIL}} |
| **Timezone** | {{OWNER_TIMEZONE}} |
| **Role** | {{ROLE_TITLE}} |
| **Note-Taking Preference** | Live silent attendee preferred. Recorded as fallback when schedule conflicts. |
| **Agenda Preference** | {{DOCS_TOOL}} linked doc, bullet format, pre-read materials attached inline |
| **Distribution Preference** | Full notes to all attendees. Individual action-item lists to owners. Channel varies by recipient. |

---

## Meeting Types & Default Handling

| Meeting Type | Default Duration | Agenda Required? | Note Mode | Distribution Tier |
|---|---|---|---|---|
| **Client Meeting** | {{DEFAULT_MEETING_LENGTH}} min | Always — full structured agenda | Live capture preferred | Full package + individual lists |
| **Internal Team Meeting** | {{DEFAULT_MEETING_LENGTH}} min | Always — lean agenda | Live or recorded | Full notes to attendees only |
| **1:1 (Direct Report)** | 30 min | Light agenda — 2-3 topics | Live capture | Notes to {{OWNER_NAME}} only unless items need delegation |
| **Vendor / Partner Call** | 30-45 min | Structured agenda | Live capture | Full package + individual lists |
| **Prospect / Sales Call** | 30-60 min | Full agenda with discovery questions | Live capture | Notes to {{OWNER_NAME}} + CRM log; follow-up to prospect via {{CRM_TOOL}} |
| **Recurring Standup / Check-In** | 15-30 min | Light agenda — carry-forward items | Recorded acceptable | Notes to attendees; action items only if commitments made |
| **Strategic / Planning Session** | 60-90 min | Full structured agenda with pre-reads | Live capture MANDATORY | Full package + stakeholder summary for non-attendees |
| **Emergency / Urgent Call** | As needed | Retrospective agenda within 24 hours | Live capture if possible; notes from memory if not | Minimal — action items only |

---

## Recurring Meeting Commitments

| Day/Time | Meeting | Attendees | Notes |
|---|---|---|---|
| (Populate with {{OWNER_NAME}}'s standing meetings) | — | — | Check {{CALENDAR_TOOL}} weekly for changes |
| (Populate with recurring 1:1s) | — | — | Confirm with Specialist 2 (Calendar) |
| (Populate with weekly team syncs) | — | — | Set agenda-prep reminder 24 hours before |
| (Populate with monthly reviews) | — | — | Full agenda + pre-reads required |

---

## Key Contacts for Meeting Coordination

| Specialist / Person | Department | What to Consult Them For |
|---|---|---|
| Specialist 1 | Executive Assistant | Priority alignment, briefing integration, sensitive-attendee flags |
| Specialist 2 | Calendar & Scheduling Manager | Meeting bookings, reschedule windows, availability conflicts |
| Specialist 4 | Communications Manager | Client-facing message formatting, channel preferences, CRM contact data |
| Specialist 9 | Client Success | Client meeting follow-through, VIP relationship flags, no-show escalation |
| {{OWNER_NAME}} | Principal | Agenda confirmation, note approval, priority calls on distribution |

---

## Delivery Cadence & Windows

| Deliverable | Window | Recipient |
|---|---|---|
| Agenda (PA-05-01) | Minimum 3 hours before meeting start | {{OWNER_NAME}} (review); shared with attendees at host's discretion |
| Draft Notes (PA-05-02) | Within 60 min of meeting end (live) / 90 min of recording (recorded) | {{OWNER_NAME}} only — NOT attendees |
| Action-Item Preview (PA-05-03) | Within 30 min of notes approval | {{OWNER_NAME}} for validation |
| Full Follow-Up Package (PA-05-04) | Within 2 hours of host approval | All attendees + designated stakeholders |
| Individual Action-Item Lists (PA-05-04) | Within 2 hours of host approval | Each action-item owner |
| No-Show Check-In (PA-05-05) | 5 minutes after scheduled meeting start | No-show attendee |
| No-Show Options to Host (PA-05-05) | 10 minutes after scheduled meeting start | {{OWNER_NAME}} |
| Reschedule Proposals (PA-05-05) | Within 30 minutes of cancellation | Canceling attendee + {{OWNER_NAME}} |

---

## Meeting Preferences & Notes

| Preference | Setting |
|---|---|
| Agenda Format | {{DOCS_TOOL}} document, linked in calendar event and sent to host |
| Note Format | Structured {{DOCS_TOOL}} document: Objective → Decisions → Discussion → Action Items → Open Questions |
| Live Note-Taking | Silent attendee, camera off, muted. Introduced by {{OWNER_NAME}} only if needed. |
| Recording Handling | {{RECORDING_TOOL}} transcript as reference layer. NEVER rely on transcript alone. |
| Distribution Channels | Internal: {{MESSAGING_TOOL}}. External/Clients: {{INBOX_TOOL}} or {{CRM_TOOL}} messaging per contact preference. |
| Sensitive Meetings | Confirm with {{OWNER_NAME}} whether notes should be created at all. Some meetings are deliberately off-record. |
| Action-Item Tracking | Owner-specific lists + calendar reminders 24h before deadline + {{TASK_TOOL}} integration |

---

## Maintenance Notes

- Update recurring meeting commitments whenever {{OWNER_NAME}} adds, removes, or changes a standing meeting.
- Review meeting type defaults quarterly — has the duration or format preference shifted?
- If {{OWNER_NAME}} mentions a preference about agenda format, note delivery, or distribution channel, capture it here immediately.
- Check with Specialist 2 and Specialist 4 monthly to ensure meeting logistics and contact data are accurate.
- Flag any meeting series that has produced zero action items for 4+ consecutive sessions — it may not need to exist.

---

*This roster is a living document. The more accurate your meeting map, the smoother every conversation runs.*
