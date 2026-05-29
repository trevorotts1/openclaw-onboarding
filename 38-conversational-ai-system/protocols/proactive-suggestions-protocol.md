# Proactive Features Suite Protocol (Step 9.34)

> **Triangle cross-reference (builder ↔ router ↔ proactive engine):** This protocol is the **PROACTIVE
> ENGINE** corner. Sub-feature 34.1 below is the pattern-based "I've seen N customers ask about X with no
> playbook — want one?" engine; on YES it drafts a playbook *via the Step 9.20 builder*
> (`conversation-workflows-protocol.md`) into `conversation-workflows/drafts/`. Once built, those playbooks
> become routable destinations for **Step 9.33 — Intelligent Playbook Routing**
> (`intelligent-routing-protocol.md`). See Step 9.20 Section K for the full triangle.

Seven proactive capabilities, each independently triggerable. Each
analyzes recent conversation logs / workflow outcomes / escalation
patterns / buyer signals and surfaces 0-3 suggestions per week to the
operator.

All suggestions delivered via notification-routing-protocol.md
(Step 9.16) with event type `proactive-suggestion`. Operator can
dismiss, defer, or accept. Accepting triggers the underlying action
(workflow build, knowledge source add, tag creation, discount code
creation, etc.).

Cool-down: same suggestion not re-surfaced for 30 days unless materially
new data emerges.

## Sub-feature 34.1 — Proactive workflow suggestions (pattern-based)

After the agent observes the same conversation pattern 5+ times without
an existing workflow handling it, it surfaces:

> "I've noticed 7 customers this month asking about [topic]. I don't
> have a Conversation Workflow for it, so I've been improvising each
> time. Want me to draft one? Saves time on every future one."

Trigger: 5+ conversations matching a topic with no matching workflow
in past 30 days.

Acceptance: drafts a workflow via Conversation Workflow Builder
(Step 9.20) to `conversation-workflows/drafts/` for operator review.

## Sub-feature 34.2 — Proactive Knowledge Source suggestions

After the agent answers low-confidence (per Step 9.11) on the same
topic 3+ times, it surfaces:

> "I keep getting asked about [topic] but I don't have a Knowledge
> Source for it — I've answered low-confidence 4 times this week.
> Want to add one? I can pull from any doc or URL you point me at
> (using the Web Scraper from Step 9.24)."

Trigger: 3+ low-confidence answers on similar topic in past 30 days.

Acceptance: prompts operator for source URL/doc, then uses Web Scraper
to populate the appropriate typed knowledge base (Step 9.22).

## Sub-feature 34.3 — Proactive tag suggestions

After the agent classifies several conversations as a similar pattern
(e.g., 10 customers all asked about a specific product and didn't book),
it surfaces:

> "I'd like to create a tag `interested-in-X-no-booking` for these 10
> customers — they all asked about [product] but didn't move forward.
> Want me to tag them and set up a follow-up campaign?"

Trigger: 8+ contacts matching a clear pattern in past 30 days.

Acceptance: creates the tag via GHL skill (per Step 9.20 v5.4 allow-list
action 13), applies to matching contacts, optionally drafts a follow-up
workflow.

## Sub-feature 34.4 — Proactive discount code suggestions

If the agent detects a pattern of price objections on a specific product,
it surfaces:

> "I've handled 4 price objections on [product] this week. Want me to
> create a `PRICEOBJ-[product]` discount code per Discount Code Protocol
> (Step 9.26)? You can cap it at any percent off you want."

Trigger: 3+ price objections on the same product in past 14 days.

Acceptance: walks operator through Discount Code policy setup for that
product if none exists, or creates the code per existing policy.

## Sub-feature 34.5 — Proactive workflow improvements

After a workflow has fired 20+ times, the agent reviews outcomes and
surfaces improvement suggestions:

> "The 'pricing inquiry' workflow has fired 23 times this month. 16
> booked, 7 didn't. Of the 7 who didn't, 5 went silent after I quoted
> the price. Want to adjust the workflow to qualify budget BEFORE
> quoting? I can update it for you."

Trigger: workflow fired 20+ times AND has a discernible outcome pattern
(escalation rate, completion rate, stall point).

Acceptance: drafts a workflow update to
`conversation-workflows/drafts/<workflow-id>--proposed-update.md` for
operator review.

## Sub-feature 34.6 — Proactive escalation pattern detection

If the agent escalates to the operator multiple times for similar
reasons, it surfaces:

> "I've escalated 4 conversations this week because customers wanted to
> reschedule outside business hours. Do you want to expand the booking
> window, or should I set up an after-hours auto-response?"

Trigger: 3+ escalations for similar reason in past 14 days.

Acceptance: depends on choice — may expand quiet hours (Step 9.8),
create new workflow (Step 9.20), or update existing workflow.

## Sub-feature 34.7 — Proactive sales opportunity detection

When a customer's behavior shows buyer signals (per Sales Brain
Step 9.23) but the conversation didn't progress to a close, the agent
surfaces:

> "Customer [name] showed strong buying signals yesterday ('how soon
> can we start?', mentioned timeline) but the conversation ended without
> a next step. Want me to follow up with [specific suggestion]?"

Trigger: conversation ended with strong buyer signals (per Sales Brain
recognition rules) but without a booking, payment, or scheduled
follow-up.

Acceptance: drafts a personalized follow-up message for operator review
OR triggers Intelligent Follow-up (Step 9.25) if not already running.

## Cron schedule

Single weekly cron `proactive-suggestions-scan` runs Saturdays 11pm
(operator-configurable). Why Saturday 11pm: gives operator the
suggestions in time for Monday planning, doesn't conflict with Sunday
2am Weekly Tune-up (Step 9.32), doesn't conflict with nightly 3am
Dreaming.

Each sub-feature runs its own analyzer during the cron pass:

```
openclaw run proactive-suggestions-scan
  -> 34.1 analyzer
  -> 34.2 analyzer
  -> 34.3 analyzer
  -> 34.4 analyzer
  -> 34.5 analyzer
  -> 34.6 analyzer
  -> 34.7 analyzer
  -> aggregates results
  -> delivers via notification-routing-protocol.md
```

Aggregated weekly suggestion report saved to:
`<MASTER_FILES_DIR>/proactive-suggestions/YYYY-MM-DD-weekly.md`

## Operator response handling

Operator replies to each suggestion with:
- `YES` — accept and execute
- `DEFER` — push to next weekly review
- `IGNORE` — dismiss permanently (won't re-surface unless
  materially-new data emerges)
- `MODIFY: <text>` — accept with modifications

Suggestions accepted execute the underlying action with operator approval
recorded.

## Recommended model

Like Weekly Tune-up (Step 9.32), this is analytical work requiring
deep reasoning. Use highest-reasoning model available — DeepSeek V4
Pro with thinking:max, Kimi 2.6+, or current top-reasoning model at
execution time. Configure in `openclaw.json` under
`proactive.model`.

## Allow-list

All seven sub-features rely on existing allow-list actions:
- 34.1, 34.5 use action 13 (workflow drafts during operator-invoked builds)
- 34.2 uses action 14 (web scraping with cost limits)
- 34.3 uses action 13 (tag creation)
- 34.4 uses action 11 (discount code creation)
- 34.6, 34.7 surface suggestions; acceptance triggers existing allow-list actions

No new allow-list actions needed.
```

**B. Register cron:**

```bash
openclaw cron add proactive-suggestions-scan "0 23 * * 6" "openclaw run proactive-suggestions-scan"
```

Cron expression `0 23 * * 6` = "minute 0, hour 23, any day, any month, Saturday".

**C. Create suggestions folder:**

```bash
mkdir -p "$MASTER_FILES_DIR/proactive-suggestions"
```

**D. Append to MEMORY.md design principles — Rule 13:**

```markdown
### Rule 13 — The agent suggests; the operator decides

Seven proactive analyzers run weekly to surface suggestions: new
workflows the operator should build (pattern-based), missing Knowledge
Sources, useful tags for customer patterns, discount codes for
recurring objections, workflow improvements based on outcome data,
escalation patterns suggesting policy changes, sales follow-up
opportunities. Each suggestion is delivered with full context;
operator approves, defers, or dismisses. The agent NEVER auto-acts
on a proactive suggestion. Cool-down: 30 days before re-surfacing
the same suggestion unless materially new data emerges.

See `<MASTER_FILES_DIR>/proactive-suggestions-protocol.md` for the
seven sub-features.
```

**E. Append to Run Manifest:**

```markdown
