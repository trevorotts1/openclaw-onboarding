# Monthly Comprehensive Playbook Review Protocol

Runs 1st of each month at 9:00 AM (operator-configurable). Performs a
deep audit of the entire system based on a full month of conversation
data, weekly tune-up history, and outcome metrics.

## What it analyzes (six dimensions)

### 1. All Conversation Playbooks

For every Communication Playbook (8 channels) and every Conversation
Workflow registered in `conversation-workflows/registry.md`:

- Has it been updated this month?
- Performance this month: book rate, conversion, escalation rate,
  sentiment trajectory
- Outdated references (retired products, ex-team members, old policies)
- Scope duplication with another playbook
- Workflows that fired zero times this month (retirement candidates)
- Workflows firing 100+ times this month (over-broad — split candidate)

### 2. All GHL workflows

For every workflow built via Step 9.20 Layer 1 (or pre-existing in
operator's GHL):

- Still firing? Volume change vs prior month?
- Webhook calls still succeeding (or failure rate climbing)?
- Verification checklist still passing if re-run today?
- Should it be split per MEMORY.md Rule 1 (smaller workflows beat
  massive ones)?

### 3. Typed Knowledge Bases

For each of the four bases (business/, products/, sales/, conversations/):

- When was each source last updated?
- Is the agent successfully fetching it (no broken links)?
- Hit rate via memory_search — sources never queried this month are
  retirement candidates
- Conversation knowledge growth (Dreaming consolidation pace healthy?)

### 4. Model configurations

- Real-time model latency trend (up/down/stable)
- Async model latency trend
- Batch model usage and cost
- Fallback chain hit rates (rising = primary degradation)
- Cost per conversation trend
- Recommendations: switch primary model? adjust fallback order?

### 5. Accumulated weekly tune-ups

For each of the 4 (or 5) weekly tune-up reports from past month:

- Which suggestions were accepted, deferred, ignored?
- Of accepted: did the fix actually solve the problem?
- Of deferred: ready for action now?
- Of ignored: pattern repeating despite dismissal? May warrant escalation.

### 6. Bug log

Any errors, failures, or anomalies recorded in
`system-health-log.md` during the month:

- Recurring failures (same error 3+ times)
- New error types
- Integration-specific failure rates (GHL, Stripe, Shopify, OpenRouter)
- Humanizer skill failures
- Knowledge Source fetch failures

## Output

A comprehensive monthly report saved to
`<MASTER_FILES_DIR>/tune-ups/YYYY-MM-comprehensive.md` and delivered
via notification-routing-protocol.md (event type: `monthly-review`):

```
# Monthly Comprehensive Review — <month> <year>

## Executive summary
<3-5 sentence overview of the month and key recommendations>

## Conversation Playbook health
- 8 of 8 Communication Playbooks reviewed
- <N> of <N> Conversation Workflows reviewed
- Recommended retirements: <list>
- Recommended consolidations: <list>
- Recommended expansions: <list>

## GHL workflow health
- <N> workflows still firing
- <N> workflows zero-fired this month
- <N> workflows with webhook failures
- Recommended changes: <list>

## Knowledge Base health
- business/: <N> entries, <N> queried this month, <N> stale
- products/: <N> entries, <N> queried this month, <N> stale
- sales/: <N> entries, <N> queried this month, <N> stale
- conversations/: <N> entries (Dreaming growth: <healthy/slow/stalled>)
- Recommended refreshes: <list>
- Recommended retirements: <list>

## Model performance
- Real-time latency trend: <up/down/stable>
- Async latency trend: <up/down/stable>
- Fallback hit rate trend: <up/down/stable>
- Cost trend: <up/down/stable>
- Recommendations: <list, may include "switch primary to X">

## Weekly tune-up follow-through
- <N> suggestions accepted, <N> deferred to this review, <N> ignored
- Of accepted: <N> verified as actually fixing the problem
- Deferred items ready for action: <list>
- Ignored-but-recurring items: <list — operator may want to reconsider>

## Bug log
- <N> total error events this month (vs last month: <N>)
- Recurring failures: <list>
- New error types: <list>

## Major recommendations (require operator decision)
1. ...
2. ...
3. ...

## Minor improvements (agent can apply with approval)
1. ...
2. ...

Reply with item numbers to authorize.
Reply DEFER to push to next monthly review.
Reply IGNORE to dismiss permanently.
```

## What it does NOT do

- Does NOT make changes without operator approval
- Does NOT replace the Weekly Tune-up (Step 9.32) — they complement
- Does NOT touch model configs (that's Step 9.36's job)
- Does NOT auto-retire workflows or Knowledge Sources

## Recommended model

Same as Weekly Tune-up — highest-reasoning model available. This is
deep analytical work across 30 days of data. Use DeepSeek V4 Pro
thinking:max, Kimi 2.6+ via Ollama Cloud, or current top-reasoning
model. Configure in `openclaw.json` under `monthly_review.model`.

## Implementation

Cron-wise: the existing `system-health-heartbeat` cron (registered
during initial setup at `0 9 1 * *` — 9am on the 1st of each month) is
EXTENDED to invoke this review. If `system-health-heartbeat` doesn't
exist yet (older setup), register it:

```
openclaw cron add system-health-heartbeat "0 9 1 * *" "openclaw run monthly-comprehensive-review"
```

If `system-health-heartbeat` already exists, just update its command to
include the comprehensive review.

## Operator override

Manual trigger anytime:
> "Run a monthly review now"
> "Show me last month's comprehensive review"
```

**B. Register or extend the cron:**

```bash
# Check if system-health-heartbeat cron exists
if openclaw cron list | grep -q "system-health-heartbeat"; then
  echo "Extending existing system-health-heartbeat to include monthly review"
  openclaw cron update system-health-heartbeat --command "openclaw run monthly-comprehensive-review"
else
  openclaw cron add system-health-heartbeat "0 9 1 * *" "openclaw run monthly-comprehensive-review"
fi
```

**C. Append to Run Manifest:**

```markdown
