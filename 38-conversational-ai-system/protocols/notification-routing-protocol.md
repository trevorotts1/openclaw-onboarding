# Notification Routing Protocol

Defines where each type of operator notification gets delivered.

## Routing table

| Event type | Primary channel | Fallback channel | Urgency |
|---|---|---|---|
| Drift detection (sexual content) | <primary> | <fallback> | IMMEDIATE (overrides quiet hours) |
| Drift detection (inappropriate question) | <primary> | <fallback> | Normal |
| Drift detection (hostile cursing) | <primary> | <fallback> | Normal |
| Prompt injection (heavy) | <primary> | <fallback> | IMMEDIATE (overrides quiet hours) |
| Prompt injection (repeat blocked) | <primary> | <fallback> | IMMEDIATE |
| Sentiment escalation (self-harm) | <primary> | <fallback> | IMMEDIATE |
| Sentiment escalation (legal/refund) | <primary> | <fallback> | IMMEDIATE |
| Sentiment escalation (3 consec negative) | <primary> | <fallback> | Normal |
| High-volume warning (20+ msgs/hr) | <primary> | <fallback> | Normal |
| Long-conversation pause (50+ cumulative) | <primary> | <fallback> | Normal |
| Bot detection blocked | <primary> | <fallback> | Normal |
| Low-confidence escalation | <primary> | <fallback> | Normal |
| GDPR deletion request | <primary> | <fallback> | IMMEDIATE |
| Smart Booking 3-strike escalation | <primary> | <fallback> | Normal |
| Knowledge source fetch failure | <primary> | <fallback> | Routine (next batch) |
| System Health Heartbeat (monthly) | <email or primary> | <fallback> | Report |
| Analytics digest (weekly) | <email or primary> | <fallback> | Report |

## Channel configurations

(Operator-filled at setup, includes auth tokens / webhook URLs / etc.)

- Telegram: bot_token, chat_id
- Slack: webhook URL, channel
- Discord: webhook URL
- Email: address, SMTP settings (or use SendGrid/Mailgun)
- SMS: Convert and Flow phone number to send FROM, operator's phone to send TO
- Webhook: URL, optional auth header

## Fallback behavior

If primary delivery fails (timeout, 4xx/5xx response, auth error), the
agent immediately retries via the fallback channel. If fallback also
fails, log the notification locally to `<MASTER_FILES_DIR>/
notifications-undelivered.md` for operator to review.

## Quiet hours interaction

Per quiet-hours.md, operator-facing quiet hours suppress non-urgent
notifications until quiet hours end. Events marked IMMEDIATE in the
routing table override quiet hours.

## Lifecycle status tags as tag-visible notification mirrors (U-7)

Two of the standard lifecycle status tags (zhc-tag-prefix-protocol.md, Lifecycle
Status Tags) are the TAG-VISIBLE MIRRORS of notifications this protocol already
routes, so a client can react from INSIDE Convert and Flow (GoHighLevel) without
touching the bot:

- `ZHC-ai-handoff` mirrors the human-handoff / NEEDS_HUMAN escalation
  notification: the same moment the operator is alerted, the tag is on the
  contact, so a client automation (notify the owner, assign a rep) can fire off
  the tag.
- `ZHC-ai-booking-error` mirrors the Smart Booking escalation notification: the
  same moment a booking failure is reported, the tag is on the contact, so a
  client automation (alert on booking error) can fire off the tag.

The Telegram / configured-channel notification is the OPERATOR path; the tag is
the CLIENT-AUTOMATION path. Both fire together; neither replaces the other.

## Handoff Task Creation (U-14)

When `ZHC-ai-handoff` fires (zhc-tag-prefix-protocol.md, Lifecycle Status Tags),
tagging alone is PASSIVE. The agent ADDITIONALLY creates a GHL Task on the contact
so a human actually picks it up:

- **Title:** `Handoff: <workflow name>`.
- **Body:** the handoff REASON plus the LAST THREE customer messages, PII-INTACT.
  (Tasks live inside the client's OWN CRM, so PII is in its home system - unlike
  the PII-free JSONL logs. The last three messages give the human immediate
  context.)
- **Due time:** now plus the configured SLA, `skill38.handoff_task.sla_minutes`,
  default **60**.
- **Assignee:** `skill38.handoff_task.assignee_user_id`, configured at install.
  When UNSET, the task is created UNASSIGNED and the Telegram notification (this
  protocol) tells the operator to set the assignee.
- **Route (Tier ladder):** Tier 0 `caf` if the CLI covers tasks, else Tier 3
  (`POST /contacts/{contactId}/tasks`) per the skill 29 references. Every GHL call
  discloses its tier.

**Logging.** Handoff task creation logs to the existing notification pathways and
adds a documented `event_type` value to `<MASTER_FILES_DIR>/workflow-exit-events.jsonl`
(PII-free; the sink is already seeded by `scripts/25-seed-round3-feature-files.sh`):

| `event_type` | fields |
|---|---|
| `handoff_task_created` | `contact_ref` (opaque), `workflow_id`, `assignee_set` (boolean), `sla_minutes` |

**Operator-only.** The assignee and SLA come from the operator's install config;
a customer can never create, assign, or alter a handoff task.

## Cross-references

- Lifecycle status tags (the five, with exact application moments):
  `protocols/zhc-tag-prefix-protocol.md` (Lifecycle Status Tags, U-7).
- Escalation flow that triggers the handoff task:
  `protocols/customer-service-support-protocol.md`.
- MEMORY.md Rule 42 (Handoff Task Creation): appended by
  `scripts/06-append-memory-rules.sh`.
```

**C. Update existing protocol references** — the notification calls inside drift-detection-protocol.md, sentiment-monitoring-protocol.md, conversational-safeguards.md, prompt-injection-protection-protocol.md, compliance-keywords.md all need to route through this protocol now. Update each to say "Notify operator per notification-routing-protocol.md" instead of "Notify operator via Telegram."

**D. Append to Run Manifest:** "Step 9.16 complete — notification-routing-protocol.md created with <N> channels configured."

