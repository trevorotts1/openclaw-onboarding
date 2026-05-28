<!-- OPERATOR HEADER (5 lines) — DO NOT EDIT BELOW -->
<!-- Source: openclaw-cloudflare-tunnel-prompt (1).md v5.14 — lines 2327-2401 -->
<!-- Section: Step 9.8 — Install Quiet Hours -->
<!-- This file is a VERBATIM extraction from the v5.14 playbook. Do not summarize. -->
<!-- Patch source: skill-38-patch-1 agent — 2026-05-28 -->

## Step 9.8 — Install Quiet Hours

Operator-configurable time windows when the agent doesn't proactively send messages. Reactive replies to customer-initiated messages still go through.

**A. Write `$MASTER_FILES_DIR/quiet-hours.md`:**

```markdown
# Quiet Hours Configuration

Defines when the AI agent does NOT proactively send messages, and when
the operator does NOT receive admin notifications.

## Default windows

**Customer-facing quiet hours** (no proactive outbound to customers):
- 10:00 PM to 7:00 AM local time
- All days

**Operator-facing quiet hours** (no admin notifications):
- 11:00 PM to 7:00 AM local time
- All days

## What's affected

Customer-facing quiet hours block:
- Scheduled follow-ups
- Appointment reminders sent by the agent
- Re-engagement messages

Customer-facing quiet hours do NOT block:
- Replies to customer-initiated messages (if a customer texts at 3 AM,
  the agent replies at 3 AM — that's what they wanted)
- Urgent escalations to a customer (e.g., "the appointment you booked
  for 8 AM tomorrow needs to be moved")

Operator-facing quiet hours block:
- High-volume warnings (queue them; deliver at 7 AM)
- Routine system notifications

Operator-facing quiet hours do NOT block:
- Self-harm sentiment escalations (Step 9.6) — these fire immediately
- Hard system failures (tunnel down, OpenClaw crashed) — these fire
  immediately
- Any notification tagged `urgent`

## Override

Operator can edit this file to change the windows, set per-channel
rules, or disable quiet hours entirely (set `enabled: false`).

## Time zone

Default: client's local time zone as configured in OpenClaw
(`agent.timezone` in openclaw.json). If not set, defaults to UTC and
operator should configure.
```

**B. Insert into AGENTS.md** as Step 0.5 (BEFORE Step 1 safeguards, since quiet hours can block proactive sends entirely):

```markdown
### Step 0.5 — Quiet hours check (proactive outbound only)

If this turn is PROACTIVE (scheduled follow-up, reminder, re-engagement),
check quiet-hours.md. If current time is within customer-facing quiet
hours, queue the message for the next valid send window. Exit.

If this turn is REACTIVE (responding to a customer-initiated webhook),
proceed normally — quiet hours don't apply.

For operator notifications: if current time is within operator-facing
quiet hours AND the notification is NOT tagged urgent, queue for the
next valid send window.
```

**C. Append to Run Manifest:** "Step 9.8 complete — quiet-hours.md created, AGENTS.md Step 0.5 inserted."
