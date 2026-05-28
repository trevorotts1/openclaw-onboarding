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
```

**C. Update existing protocol references** — the notification calls inside drift-detection-protocol.md, sentiment-monitoring-protocol.md, conversational-safeguards.md, prompt-injection-protection-protocol.md, compliance-keywords.md all need to route through this protocol now. Update each to say "Notify operator per notification-routing-protocol.md" instead of "Notify operator via Telegram."

**D. Append to Run Manifest:** "Step 9.16 complete — notification-routing-protocol.md created with <N> channels configured."

