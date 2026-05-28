# Business-Logic Workflow Suggestions Protocol

The agent detects gaps between the operator's existing Conversation
Workflows and the complete customer journey for their business type
(per journey-templates/). When it finds gaps, it proposes the missing
workflows for operator approval.

## Trigger events

The agent runs gap detection when ANY of these fire:

1. **Operator adds a new product** to `knowledgebases/products/`
   (via setup or manual addition)
2. **Operator adds a new service tier** or pricing option
3. **Operator builds a sales workflow** via Step 9.20 Conversation
   Workflow Builder
4. **Operator imports a Knowledge Source** with product/service info
5. **Operator integrates Stripe/Shopify with new products** (Step 9.27
   import, or future Step for Shopify)
6. **Operator explicitly requests** gap analysis: "what workflows am I
   missing?" or similar
7. **Monthly comprehensive review** (Feature 36 when shipped) — runs
   gap detection as part of full audit

## Gap detection logic

When triggered:

1. Determine business type from Business Brain knowledge base (or use
   stored type from Step 9.28)
2. Load the journey template for that type from `journey-templates/<type>/journey.md`
3. Enumerate the workflows in the template (the "should have" list)
4. Enumerate the existing Conversation Workflows from
   `<MASTER_FILES_DIR>/conversation-workflows/registry.md`
5. Match existing workflows to template entries (by purpose, not just
   name — use semantic matching)
6. Build the gap list:
   - Template workflow NOT matched by any existing workflow = GAP
   - Existing workflow not in template = ORPHAN (informational, not
     necessarily wrong)

## Presenting gaps to operator

Surface gaps via notification-routing-protocol.md (event type:
`workflow-gap-detected`):

```
I noticed you just registered "6-Month Coaching Package" as a new product.

Looking at your existing workflows, you have:
✅ Discovery / Consultation Booking
✅ Pricing Inquiry
✅ Payment Confirmation

But for a complete customer journey (coaching template), you're missing:
❌ Welcome / Kickoff (welcome message + first-session scheduling)
❌ First-Session Preparation (prep questionnaire + reminders)
❌ Mid-Engagement Check-in (30 days in)
❌ Milestone Celebrations
❌ Renewal Reminder (45 days before subscription renewal)

Want me to draft these? You can review and edit each before they go live.

Reply YES to draft all 5, or specify which ones (e.g. "YES to 1,2,5").
```

## Drafting workflows

If operator says yes:

1. For each approved workflow, use the Conversation Workflow Builder
   (Step 9.20) to scaffold:
   - Workflow ID (derived from name)
   - Layer 0 (routing check)
   - Layer 1 (GHL side — tags, Workflow AI prompt, verification checklist)
   - Layer 2 (OpenClaw playbook — conversation behavior)
2. Save drafts to `<MASTER_FILES_DIR>/conversation-workflows/drafts/`
   (NOT directly to active workflows — operator must review first)
3. Notify operator: "Drafted N workflows. Review them at
   `conversation-workflows/drafts/`. When you're happy, move to
   `conversation-workflows/` to activate."

The agent does NOT auto-activate proposed workflows. Operator review
is required.

## Customization per business type

Different business types have different journey templates (Step 9.28).
The gap detection adapts automatically based on:

- Business type inferred from Business Brain
- Products being sold (subscription vs one-time vs service vs course)
- Operator's stated preferences

For example: a coaching business with a one-time signature workshop
(not a recurring engagement) won't be flagged for missing renewal
workflows.

## Orphan workflows (informational)

If the operator has workflows that aren't in the template, the agent
notes them but doesn't flag as problems:

> "FYI: You have a 'VIP-Day Booking' workflow that isn't in the standard
> coaching template. That's fine — it's custom to your business. I'll
> leave it as-is."

## Cool-down

After gap detection runs and operator dismisses/defers a suggestion,
the agent won't re-suggest the same gap for 30 days (avoids nagging).
Re-suggestion happens if:
- The gap is dismissed but a related event re-triggers detection
- 30 days have passed
- Operator explicitly asks "re-run gap analysis"

## Allow-list action

Per Step 9.15 allow-list, agent has action 13 (already exists from v5.4 —
create tags in GHL during operator-invoked workflow builds). Drafting
workflows uses the same authority. Customer messages CAN NEVER trigger
workflow drafts.
```

**B. Append to Run Manifest:**

```markdown
