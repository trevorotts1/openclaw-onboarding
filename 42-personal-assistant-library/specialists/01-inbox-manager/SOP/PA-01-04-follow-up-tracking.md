# SOP PA-01-04: Follow-Up Tracking

**Department:** Inbox Manager (01-inbox-manager)
**SOP Type:** DMAIC
**Version:** 1.0
**Last updated:** 2026-07-23
**Generated for:** the company

---

## When to Run

Continuous — every time an email is sent that requires a response by a deadline. Also: daily morning review of the follow-up tracker.

**Frequency:** Tracking is real-time; review is daily.

**Inputs:** Sent emails that contain: action requests, questions requiring answers, proposals awaiting decisions, or any explicit "let me know by [date]" language.

---

## Define

- **Problem:** Sent emails that require a response often go untracked. {{OWNER_NAME}} sends a proposal, asks a question, requests a decision — and then moves on to the next thing. Without systematic follow-up tracking, the response never comes, the opportunity stalls, and by the time anyone remembers, the window has closed. Research shows that 80% of sales require 5 follow-ups, but 44% of salespeople give up after 1 follow-up (IRL). A systematic follow-up tracker prevents this entirely.
- **Goal:** Every sent email that requires a response is tracked as a task in {{TASK_TOOL}} with a deadline. Follow-ups are sent at graduated intervals: gentle nudge 1 day before deadline, direct follow-up on the deadline date, second follow-up 2 days after deadline, and escalation to {{OWNER_NAME}} after 5 days of silence. Zero tracked follow-ups are allowed to expire without action.
- **Scope:** All business emails sent by {{OWNER_NAME}} or sent on {{OWNER_NAME}}'s behalf that require a response. Includes: proposals, price quotes, contract questions, scheduling requests, partnership inquiries, and any email containing "let me know," "what do you think," "please confirm," or similar response-triggering language.

---

## Measure

- **CTQ 1 — Tracking completeness:** Percentage of response-required emails that are tracked in {{TASK_TOOL}}. Target: 100% — every email that needs a reply is tracked.
- **CTQ 2 — Follow-up timeliness:** Percentage of tracked follow-ups where the first nudge is sent on or before the deadline date. Target: 95% or higher.
- **CTQ 3 — Resolution rate:** Percentage of tracked follow-ups that reach resolution (reply received, deal closed, or formally abandoned by {{OWNER_NAME}}). Target: 90% or higher.
- **Metrics:** Active follow-ups in tracker (count), follow-ups due today (count), overdue follow-ups (count), follow-ups resolved this week (count), average time to resolution (days).

---

## Analyze

1. **Response-required detection.** Not every sent email needs a follow-up. Detection rules: (a) contains a question mark (explicit ask), (b) contains request language — "please review," "let me know," "confirm," "approve," (c) contains a proposal or attachment that is clearly awaiting feedback, (d) contains a deadline — "by Friday," "before EOW," "by [date]," (e) is part of an active negotiation or sales pipeline. If none of these apply, the email is informational and does not need tracking.
2. **Common follow-up failures:** (a) The "they will reply when they are ready" assumption — most people will NOT reply unless nudged. They are busy. They forget. Your nudge is a service, not a nuisance. (b) Tracking with no deadline — "follow up on the Acme proposal" with no date is not a follow-up; it is a wish. Every follow-up needs a specific deadline date. (c) Sending the same nudge twice — escalating your language is effective: Nudge 1 is gentle ("wanted to bump this to the top of your inbox"), Nudge 2 is direct ("checking in — the deadline for this was [date]"), Nudge 3 is escalatory ("I have not heard back — is this still a priority?")

---

## Improve

1. **The graduated nudge cadence.** Pre-write the follow-up sequence when the original email is sent: (a) Nudge 1 — 1 day before deadline: gentle, helpful, "bumping to the top of your inbox," (b) Nudge 2 — on the deadline date: direct, references the deadline, "the deadline for this is today — wanted to make sure it did not get buried," (c) Nudge 3 — 2 days after deadline: still warm but clearly waiting, "checking in — have not heard back on this. Still interested?," (d) Nudge 4 — 5 days after deadline: brief, final, "one last check on this — if I do not hear back by [date], I will assume the timing is not right and close this out. No hard feelings either way." After Nudge 4, mark the follow-up as "Closed — no response" and notify {{OWNER_NAME}}.
2. **The follow-up tracker dashboard.** In {{TASK_TOOL}}, maintain a single view of all active follow-ups sorted by deadline. Every morning, check: what is due today? What is overdue? What is about to go overdue (within 48 hours)? This dashboard is the first thing you look at after inbox triage.
3. **Escalate, do not stall.** If a follow-up reaches 2 weeks past deadline with no response, do not keep nudging. Escalate to {{OWNER_NAME}}: "[Name] has not replied to 3 follow-ups since [date] about [topic]. Recommendation: close this out or have you reach out directly. What should I do?"

---

## Control

- **Daily tracker review:** Every morning, review the follow-up dashboard. Send any due nudges. Flag any stalling follow-ups for {{OWNER_NAME}}.
- **Weekly metrics check:** Follow-ups created vs. resolved. Resolution rate. Average time to resolution. Any patterns? (e.g., "proposals to [Industry] clients consistently go unanswered after Nudge 2 — maybe the proposal format needs work.")
- **Monthly tracker audit:** Are there follow-ups in the tracker older than 30 days? If yes, each one needs a decision from {{OWNER_NAME}}: close, escalate, or send one final attempt.

---

---

## CTQ Checks

- [ ] Every response-required sent email is tracked as a task in {{TASK_TOOL}} with a specific deadline date
- [ ] First follow-up nudge sent on or before the deadline date — zero missed windows
- [ ] Follow-up cadence follows graduated escalation: nudge → direct → escalatory → final close
- [ ] No follow-up older than 30 days remains in the tracker without an explicit {{OWNER_NAME}} decision
- [ ] Daily morning review of the follow-up tracker completed — all due nudges sent

## Definition of Done

Every sent email requiring a response is tracked with a deadline, follow-ups fire at graduated intervals, and the tracked item reaches resolution (reply received, deal closed, or formally abandoned by {{OWNER_NAME}} decision).

## Escalation

- **Specialist 04 (Task & Priority Manager)** — if a follow-up reveals an overdue task or deadline that needs to be integrated into {{OWNER_NAME}}'s active priorities
- **Specialist 02 (Calendar & Scheduling Manager)** — if a follow-up response requests a meeting that needs immediate scheduling
- Escalate to {{OWNER_NAME}} — when a tracked follow-up has received 3+ nudges with zero response over 2+ weeks, with the recommendation: "Close this out or have you reach out directly."

## Tone & Persona Note

You are not nagging — you are serving. Every follow-up you send protects a relationship, an opportunity, or a commitment from being lost to the noise of everyone's busy inbox. Frame each nudge as helpful, not demanding. Escalate gently: you want clarity for the sender and {{OWNER_NAME}}, not guilt. A well-timed follow-up says "I value this enough to make sure it doesn't slip." That's a gift, not a nuisance.

---

*See also: how-to.md Section 3 (Daily Operations — morning tracker review step)*
