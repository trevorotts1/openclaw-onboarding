# Conversation Analytics Dashboard Protocol

The agent generates two periodic reports for the operator:
- Weekly digest (Monday mornings)
- Monthly comprehensive report (1st of each month — merges into the
  existing System Health Heartbeat)

## Weekly digest contents

Generated every Monday at 8 AM local time. Sent to the operator via
the analytics-digest notification channel (per notification-routing-
protocol.md). Includes:

### Volume metrics
- Total conversations in past 7 days
- New contacts vs returning contacts
- Conversation count by channel (SMS, email, Facebook, etc.)
- Peak conversation hours (heatmap as ASCII or table)

### Topic clustering
- Top 10 topics customers asked about (clustered by semantic similarity
  using memory_search embeddings — requires embeddings provider, Step
  O.6)
- For each topic: count, % change from prior week, sample customer
  message excerpt

### Quality metrics
- Escalation rate (% of conversations that escalated to human)
- Sentiment distribution (% positive / neutral / negative / hostile)
- Average reply latency (real-time channels vs async)
- Confidence threshold trigger rate (% of replies that escalated due
  to low confidence)

### Safeguard activations
- Drift events by category (sexual / inappropriate / hostile)
- Prompt injection events by severity
- High-volume warnings issued
- Bot detections triggered

### Communication playbook insights
- Which channel playbooks are filled in vs still using defaults
- Recommendation: "You're getting 40% of conversations on SMS but
  your SMS playbook only has 2 example replies. Consider adding
  more for better quality."

## Monthly comprehensive report

Generated on the 1st of each month at 9 AM. Replaces the standalone
System Health Heartbeat (Step 3.5H) — same cron job, expanded scope.
Includes everything from the weekly digest, plus:

- Knowledge Source utilization (which sources are queried, which
  aren't, which fail)
- Model degradation tracking (40%+ slower than prior month?)
- Outreach campaign results (open rate, response rate, conversion
  rate — once Feature 15 ships)
- Document generation usage (# of quotes/proposals generated — once
  Feature 22 ships)
- Smart Booking metrics (bookings made, declines, 3-strike escalations)
- Conversation Workflow trigger counts (which workflows fire most)

## Output format

Generated as markdown. The agent appends each report to
`<MASTER_FILES_DIR>/analytics/YYYY-MM-DD-<cadence>.md` and also delivers
the highlights via the configured notification channel.

If the operator has Notion access (per Step 8), the analytics also
publish to a Notion database "Convert and Flow Analytics" for visual
browsing.

## Implementation

The agent reads conversation logs, run manifest entries, system-health-
log.md, and the embeddings-powered semantic clustering for topic
analysis. No external dependencies beyond what's already configured.
```

**B. Update cron job registration** — the existing `system-health-heartbeat` cron (Step 3.5H) becomes the monthly comprehensive report. Add a new cron for the weekly digest:

```json
{
  "id": "analytics-weekly-digest",
  "schedule": "0 8 * * 1",
  "agentId": "<ROUTING_AGENT_ID>",
  "model": "<BATCH_MODEL>",
  "message": "Generate the weekly analytics digest per analytics-dashboard-protocol.md. Append to <MASTER_FILES_DIR>/analytics/<date>-weekly.md and notify operator per notification-routing-protocol.md (analytics-digest event type)."
}
```

**C. Append to Run Manifest:** "Step 9.17 complete — analytics-dashboard-protocol.md created, weekly digest cron registered, monthly report merged into existing heartbeat."

