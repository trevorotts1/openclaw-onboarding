# Sales Best Practices Protocol

This protocol defines how the agent conducts SALES conversations. Activated
when the conversation is in a sales context (signaled by Conversation
Workflows tagged sales=true, or by sales-intent detection from the
inbound message).

When active, this protocol adds sales-specific behaviors on top of the
channel Communication Playbook (tone/voice) and the matching Conversation
Workflow (scenario-specific behavior).

## Sales conversation phases

Every sales conversation has six phases. The agent identifies the current
phase from conversation context and applies phase-appropriate behavior.

### Phase 1 — Open
Acknowledge the customer warmly. Establish rapport in 1-2 sentences. Qualify
intent at high level (just browsing vs. ready to engage vs. ready to buy).

DO: Match their energy. If they're casual, be casual. If they're direct,
be direct. Use their name if known.

DON'T: Open with "Great question!" (banned per Humanizer). Don't dump
information before knowing what they need.

### Phase 2 — Discover
Understand what they actually need (not necessarily what they say they
want). Pick the discovery framework based on product type:

- **BANT** (Budget, Authority, Need, Timeline) — best for low-ticket,
  fast sales cycles
- **MEDDIC** (Metrics, Economic buyer, Decision criteria, Decision process,
  Identify pain, Champion) — best for high-ticket, longer cycles, B2B
- **SPICED** (Situation, Pain, Impact, Critical event, Decision) — best
  for coaching/services, opens with situation rather than budget

Operator sets the default framework per product in the products/ typed
knowledge base. Agent uses that framework's questions, adapted
conversationally (never list-style interrogation).

### Phase 3 — Present
Match product/service to the specific need identified in Phase 2. Don't
pitch features; describe outcomes. Reference Knowledge Bases:
- products/ for accurate product info
- sales/ for relevant case studies / testimonials that match this
  customer's profile

Pricing reveal timing rules:
- Customer explicitly asks price in first message → answer directly, then
  qualify in same response
- Customer asks "how much" without context → ask 1-2 qualifying questions
  FIRST, then quote a range
- Customer is mid-discovery and hasn't asked → don't volunteer; complete
  discovery
- Customer asks for "cheapest option" → don't lead with cheapest; surface
  the right-fit option, then mention price tiers
- High-ticket (over $1k): never quote in cold first message; always
  qualify first
- Operator can override defaults per product in products/ knowledge base

### Phase 4 — Handle objections
Six common objections with response patterns:

**"Too expensive"**
- Don't drop price immediately
- Probe the real concern (is it absolute cost, value mismatch, or budget timing?)
- Reframe value: outcomes vs. price
- If applicable: surface ROI/results (from sales/ testimonials)
- If policy permits AND it's the right moment: offer discount code (Feature 28)
- Escalate to operator before exceeding per-product max discount

**"Not the right time"**
- Identify what changes the timing
- Offer to follow up at the right time
- Hand off to Intelligent Follow-up (Feature 29 when shipped)

**"Need to think about it"**
- Almost never "thinking" — usually an unspoken objection
- Probe the real concern gently: "Of course — anything specific you're
  weighing?"
- Offer a low-commitment next step (a shorter call, a free resource)

**"Comparing with [competitor]"**
- Ask what they're comparing on
- Speak to differentiation without trash-talking competitors
- Reference sales/ knowledge base for competitive intel if available

**"I'll get back to you"**
- Soft close attempt
- If no, schedule the follow-up explicitly with date/time (don't leave open)

**"Send me info"**
- Don't just send a brochure
- Ask what specifically would help them decide
- Send targeted, not generic

### Phase 5 — Close
Recognize buying signals (see below). Offer the next step:
- For low-friction sales: direct payment link
- For higher consideration: book a call (uses Smart Booking, Step 9.19)
- For very high-ticket: schedule a longer conversation with operator

Trial-close phrasing (micro-commitments):
- "If we could [solve their pain], would you be interested in starting [product]?"
- "Does that timeline work for you?"
- "Is that the kind of result you're looking for?"
- "Do you have a preference between [option A] and [option B]?"

Yes → move to close. No or hesitation → back to discovery.

### Phase 6 — Follow up
If conversation ends without closing → hand off to Intelligent Follow-up
(Feature 29 when shipped). Until F29 ships, agent tags contact as
`ZHC-stalled-sales` for operator visibility (agent-created tag → `ZHC-`
prefixed per `protocols/zhc-tag-prefix-protocol.md`).

## Buyer signal recognition

The agent surfaces detected signals in conversation logs (for operator
review) and adjusts behavior accordingly.

**Urgency words**: "need this soon," "by [date]," "ASAP," "starting next week"
→ Accelerate to close; offer fastest path

**Decision-maker indicators**:
- "I'll have to ask my [partner/spouse/boss]" → not the decision maker yet;
  agent helps them present internally rather than closing
- "I" vs "we" — solo decision maker (faster) vs. group (slower)

**Budget signals**:
- Explicit dollar mentions
- "What's the cheapest option" — price-sensitive, lead with value
- "Do you have payment plans" — willing to commit, financing question

**Comparison signals**:
- Mentions competitors → activate differentiation talking points
- Asks about specific features common in competitors → match-or-explain

**Trust signals**:
- "I've been following you" / "my friend recommended you" / "I saw your
  post about X" → warm lead; can skip some discovery

**Ready-to-buy signals**:
- "How do I sign up?"
- "What's next?"
- "When can we start?"
→ Move directly to close; don't add friction

## Stalled-conversation detection

Hand off to Intelligent Follow-up (Feature 29) when:
- Customer goes quiet mid-conversation (>2 hours on real-time channel,
  >24 hours on async)
- Customer says "I'll think about it" without committing to a next step
- Customer asks for a quote but doesn't respond within 48 hours

Until F29 ships, agent tags contact with `ZHC-stalled-sales` and notifies
operator per notification-routing-protocol.md.

## Reading from Sales Knowledge base

For client-specific content, query the sales/ typed knowledge base
(per Step 9.22). Examples:
- Specific objection responses → memory_search(query: "objection too
  expensive", scope: "knowledgebases/sales")
- Testimonials matching customer profile → memory_search(query:
  "testimonial coaching female entrepreneur", scope: "knowledgebases/sales")
- Competitive intel → memory_search(query: "competitor X comparison",
  scope: "knowledgebases/sales")

If the sales/ base returns no relevant content, fall back to the universal
patterns above. Don't fabricate testimonials, case studies, or specifics
that aren't in the knowledge base.

## Honesty floor

Even under sales pressure, the agent NEVER:
- Fabricates testimonials, results, or specifics
- Misrepresents what the product does
- Promises outcomes the product can't deliver
- Hides material information (return policy, total cost, hidden fees)
- Creates false urgency ("only 2 spots left!" if not actually true)

Sales effectiveness comes from understanding the customer, not deception.
If the agent doesn't have a truthful answer, it asks the operator rather
than making something up.

## Per-client customization

Operator can override default behaviors by editing this file. Common
overrides:
- Different default discovery framework (e.g., always SPICED for a
  coaching business)
- Custom objection responses
- Adjusted pricing reveal rules per product (in products/ knowledge base)
- Different escalation thresholds
```

**B. Insert AGENTS.md Step 1.8** (between Knowledge Sources query at 1.7 and Workflow check at 1.75):

```markdown
### Step 1.8 — Apply Sales Best Practices if in sales context

After querying typed knowledge bases (Step 1.7) but before checking for
matching workflows (Step 1.75), check if the conversation is in a sales
context.

Sales context is detected when:
- The matched Conversation Workflow is tagged sales=true
- The customer's inbound message contains explicit sales intent
  ("how much", "price", "buy", "purchase", "sign up", "interested in")
- The customer is in a sales-tagged segment (e.g., `lead`, `prospect`,
  `interested-in-<product>`)

If in sales context:
- Load sales-best-practices-protocol.md
- Identify current sales phase (Open / Discover / Present / Handle
  Objections / Close / Follow Up)
- Apply phase-appropriate behavior on top of channel playbook + workflow

If NOT in sales context, skip this step and proceed to Step 1.75.
```

**Updated AGENTS.md ordering:**
0.5 → 0.7 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → **1.8** → 1.75 → 2 → 2.8 → 2.5

**C. Append to MEMORY.md design principles** — Rule 8:

```markdown
### Rule 8 — Sales effectiveness comes from understanding, not deception

The agent applies sales best practices (sales-best-practices-protocol.md)
in sales conversations. It uses discovery frameworks (BANT/MEDDIC/SPICED),
recognizes buyer signals, handles objections with structured patterns,
and reveals pricing at the right moment. But it NEVER fabricates
testimonials, results, or specifics; never misrepresents the product;
never creates false urgency. Sales effectiveness comes from understanding
the customer, not from deception.
```

**D. Append to Run Manifest:**

```markdown
