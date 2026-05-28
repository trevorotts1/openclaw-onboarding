# Weekly Conversation AI Tune-up Protocol

Runs every Sunday at 2:00 AM (operator-configurable). Analyzes the past
7 days, identifies adjustment opportunities, presents them for operator
approval.

## What it analyzes

### 1. Recent conversation patterns (past 7 days)

- Topics asked about with no matching Conversation Workflow
- Conversations where the agent escalated repeatedly for the same reason
- Conversations where customers expressed frustration despite "successful"
  outcomes
- Drift detection events that didn't quite hit thresholds but are
  trending up
- Service-to-support mode switches (per Step 9.30) trending up in a
  specific workflow

### 2. Dreams diary review (past 7 days)

Reads `DREAMS.md` entries from the past week. Dreaming has already done
pattern-finding work; the tune-up surfaces what Dreaming noticed but
didn't escalate.

### 3. Bug surface scan

- Knowledge Source fetch failures
- GHL webhook delivery failures
- Stripe/Shopify webhook delivery failures (if integrated)
- Model timeouts or fallback chain triggers
- Confidence threshold hit rates trending higher than baseline
- Sentiment escalation events spiking
- Humanizer skill failures (per Step 9.21)

### 4. Workflow performance check

For each Conversation Workflow:
- How many times it fired this week
- Success vs escalation rate
- Any workflow firing zero times (potentially obsolete)
- Any workflow firing too often (potentially over-broad)

## Output

A weekly tune-up report saved to `<MASTER_FILES_DIR>/tune-ups/YYYY-MM-DD-weekly.md`
and delivered via notification-routing-protocol.md (event type:
`weekly-tune-up`):

```
# Weekly Tune-up — <date>

## Quick health summary
- Conversations this week: <N>
- New patterns detected: <N>
- Bugs surfaced: <N>
- Suggested adjustments: <N>

## Adjustments to consider (no action without your approval)

### High priority
1. [issue + suggested fix]
2. ...

### Medium priority
1. ...

### Low priority / FYI
1. ...

## Next steps
Reply YES to any item to authorize the fix.
Reply DEFER to push it to the monthly review.
Reply IGNORE to dismiss.
```

## What it does NOT do

- Does NOT make changes without operator approval
- Does NOT replace the monthly comprehensive review (Feature 36, when shipped)
- Does NOT generate full new workflows — only suggests where they might
  be needed
- Does NOT touch model configs — that's Feature 37's job (when shipped)

## Recommended model

This is an analytical task requiring deep reasoning. Use the highest-
reasoning model available — typically DeepSeek V4 Pro with thinking:max,
or Kimi 2.6+ via Ollama Cloud, or the latest top-reasoning model at
execution time. Configure in openclaw.json under `tuneup.model`.

## Implementation

Register a cron job:

```
openclaw cron add weekly-tune-up "0 2 * * 0" "openclaw run weekly-tune-up"
```

Cron expression `0 2 * * 0` = "minute 0, hour 2, any day, any month,
day-of-week 0 (Sunday)".

## Operator override

Operator can manually run the tune-up at any time:

> "Run a tune-up now"
> "Show me this week's tune-up"

Agent runs the same analysis on-demand.
```

**B. Register cron:**

```bash
openclaw cron add weekly-tune-up "0 2 * * 0" "openclaw run weekly-tune-up"
```

**C. Create the tune-ups folder:**

```bash
mkdir -p "$MASTER_FILES_DIR/tune-ups"
```

**D. Append to Run Manifest:**

```markdown
