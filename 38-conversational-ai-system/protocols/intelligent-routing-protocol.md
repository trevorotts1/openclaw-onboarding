# Intelligent Playbook Routing Protocol (Step 9.33)

> **Triangle cross-reference (builder ↔ router ↔ proactive engine):** This protocol is the **ROUTER**
> corner. The destinations it transitions between are the playbooks created by **Step 9.20 — Conversation
> Playbook Builder** (`conversation-workflows-protocol.md`). The **Step 9.34 — Proactive Features Suite**
> (`proactive-suggestions-protocol.md`) proposes NEW playbooks the builder then creates, which immediately
> become routable destinations here. See Step 9.20 Section K for the full triangle.

The agent re-evaluates workflow match after EVERY customer message,
not just at conversation start. Routes to a different workflow when
the conversation has clearly moved to a different topic. This is
cross-playbook TRANSITIONS: a customer who starts in one playbook gets
moved to another based on their responses; the agent detects the shift,
caps switches at 3 per conversation, and uses soft transition language.

## When routing evaluation runs

After every inbound customer message, BEFORE drafting the reply:

1. Semantic-score the current message against the trigger phrases of
   ALL registered workflows in `conversation-workflows/registry.md`
2. Compare top-scoring workflow against the CURRENT active workflow
3. If a different workflow scores significantly higher → route
4. If current workflow still scores highest → continue

## Routing thresholds

- **Stay** if current workflow's score is within 0.3 cosine similarity
  of any alternative (default — operator can tune in
  intelligent-routing-protocol.md)
- **Switch** if a different workflow scores 0.3+ higher than current
- **Fall back to channel playbook** if NO workflow scores above 0.5
  (no workflow really matches — use default channel voice)

## Routing safeguards

1. **Maximum 3 workflow switches per conversation.** Prevents thrashing.
   After 3 switches, the agent locks to whatever workflow is active and
   notes "topic-shifting customer" in conversation log for operator review.
2. **Customer must clearly signal a topic shift.** Agent does NOT
   preemptively jump to a workflow because the customer mentioned
   something in passing. Requires a full message focused on the new topic.
3. **Soft transition language.** When routing, the agent acknowledges
   the shift naturally before continuing:
   - "Sounds like this is more about [new topic] now — let me switch gears."
   - "Got it, that's a different question — let me help with that."
   - "Happy to talk through [new topic] — give me a sec."

   This signals to the customer that the agent followed the pivot, not
   that it got confused.
4. **Routing decisions LOGGED.** Every route is appended to the
   conversation log with: from_workflow_id, to_workflow_id, trigger_message,
   similarity_scores. The analytics dashboard (Step 9.17) can show which
   routing patterns happen most often.
5. **Operator override.** Operator can pin a conversation to a specific
   workflow ("stay on the refund workflow regardless of what they say next")
   for situations where the operator wants tight control.

## What stays the same when routing happens

When the agent switches workflows mid-conversation, these carry over:

- Communication Playbook (channel voice — doesn't change with workflow)
- Customer context (name, history, tags)
- Sales Brain phase if in sales context (per Step 9.23)
- Humanizer pass (per Step 9.21 — always-on regardless of workflow)
- Confidence threshold (per Step 9.11)

What changes when routing happens:

- Workflow-specific Layer 2 instructions (the conversation behavior
  defined in `<workflow-id>/layer-2.md`)
- Workflow-specific allow-list permissions (if the workflow has any)
- Workflow-specific knowledge base scope (if defined)

## Edge cases

### Customer asks 3 questions in 1 message

Example: "Hey — wondering about pricing for the 6-month package, also
when do you have availability next week, and one of my colleagues
mentioned a refund issue..."

Three topics: pricing (sales), availability (booking), refund (support).

The agent handles this by:
1. Identifying ALL workflows that match
2. Picking the PRIMARY workflow (whichever the customer led with — pricing here)
3. Acknowledging the other two: "Happy to talk pricing first — I'll
   come back to the availability question and the refund issue after we
   sort that out."
4. After resolving pricing, naturally transitioning: "On the availability
   question..."
5. After that: "And on the refund — let me get that pulled up for you."

This is "queued routing" — multiple workflows are queued, primary
handled first, others picked up in order. Maximum 3 queued workflows
per conversation.

### Customer pivots back to original topic

Customer: "Wait, actually about that pricing question from earlier..."

The agent recognizes the back-reference and routes BACK to the original
workflow. Conversation log shows full routing path: pricing → availability
→ pricing.

This counts as 2 switches (pricing→avail, then avail→pricing), so still
within the 3-switch cap.

### Ambiguous pivot

Customer: "Hmm, okay, but what about delivery?"

If multiple workflows could match "delivery" (shipping workflow, product
delivery workflow, course access workflow), the agent asks for
clarification before routing:

"Quick clarification — are you asking about shipping for a physical
product, or how you get access to the course content?"

Once clarified, route to the appropriate workflow.

## AGENTS.md Step 1.75 update

Step 1.75 (workflow check) gets upgraded from "match a workflow at start"
to "evaluate routing every message." The upgrade is backward-compatible
— if only one workflow matches and never changes during the conversation,
behavior is identical to the prior v5.4 setup.

Updated Step 1.75 logic:
1. Score current message against all workflow triggers
2. If conversation just started → pick top-scoring workflow (this is
   the v5.4 behavior)
3. If conversation has an active workflow → run routing evaluation
   (NEW in v5.13)
4. If routing decision is SWITCH → load new workflow, add soft
   transition phrasing to reply, log switch
5. If routing decision is STAY → continue current workflow
6. If no workflow scores above 0.5 → fall back to channel playbook

## Implementation

- Protocol document: `intelligent-routing-protocol.md`
- Uses `memory_search` (per O.6 embeddings — Google text-embedding-004
  default) to semantically score messages against workflow trigger phrases
- Routing threshold configurable in `openclaw.json` under
  `routing.switch_threshold` (default 0.3)
- Routing cap configurable under `routing.max_switches_per_conversation`
  (default 3)
- All routing decisions logged to conversation log with full metadata

## MEMORY.md Rule 12

Customers don't follow scripts. The agent re-evaluates which workflow
matches the conversation after every customer message, routes
naturally with soft transition phrasing, and never thrashes (max 3
switches per conversation). Routing decisions are logged for operator
review and analytics.
```

**B. Append to MEMORY.md design principles — Rule 12:**

```markdown
### Rule 12 — Conversations route, they don't lock

Customers don't follow scripts. The agent re-evaluates workflow match
after every customer message, routes to a different workflow when
the conversation clearly pivots, uses soft transition phrasing
("Sounds like this is more about X now — let me switch gears"), and
caps switches at 3 per conversation to prevent thrashing. Routing
decisions are logged.

See `<MASTER_FILES_DIR>/intelligent-routing-protocol.md` for full rules.
```

**C. Update existing Step 1.75 in AGENTS.md** from "first-match workflow check" to "evaluate routing every message." The upgrade is backward-compatible.

**D. Append to Run Manifest:**

```markdown
