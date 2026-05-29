# Sales Frameworks — BANT / MEDDIC / SPICED Deep-Dive

> Deep-dive reference for `protocols/sales-best-practices-protocol.md`. The protocol
> file is the behavioral contract; this file is the framework-by-framework breakdown
> the agent picks from per Conversation Workflow. Consolidated from v5.14 playbook
> Step 9.23. See `references/v6.0-source-playbook.md` for the canonical block.

## The three frameworks shipped in v5.14

Adapted from established B2B sales methodologies, simplified for conversational AI:

### BANT — Budget · Authority · Need · Timeline

Fast qualification, good for low-ticket (< $1k typically). Four questions:
- **B**udget — can they afford it? (explicit dollar mentions, "what's the cheapest option," "do you have payment plans")
- **A**uthority — are they the decision-maker? ("I" vs "we" / "my partner / spouse / boss" / "I'll have to ask")
- **N**eed — what problem are they solving? Drill until they describe the pain in their own words, not yours
- **T**imeline — when do they need this? ("ASAP," "by [date]," "I'm just exploring")

### MEDDIC — Metrics · Economic buyer · Decision criteria · Decision process · Identify pain · Champion

Deeper qualification for high-ticket ($1k+) and longer sales cycles. Six elements:
- **M**etrics — what numbers will improve if they buy?
- **E**conomic buyer — who controls the budget? (often not the person you're talking to)
- **D**ecision criteria — what factors will their decision turn on?
- **D**ecision process — how does this kind of purchase get made in their org?
- **I**dentify pain — what specific pain is driving them to look NOW?
- **C**hampion — who internally is rooting for this purchase?

### SPICED — Situation · Pain · Impact · Critical event · Decision

Coaching/services-friendly. Opens with their current state:
- **S**ituation — where are they NOW?
- **P**ain — what hurts about that situation?
- **I**mpact — what does that pain COST them? (money, time, relationships, energy)
- **C**ritical event — what's making them act NOW, not last month or next year?
- **D**ecision — how will they make this call?

## How the agent picks one

The Conversation Workflow Builder (v5.14 Step 9.20) tags each sales workflow with a
preferred framework. Per-product policy in `products/` typed knowledge base may override.
The agent never tries to apply all three at once — it picks the framework that matches
the deal size and customer type.

## The 6 objection patterns (each has a response template in the protocol)

1. "Too expensive" → reframe value, payment plan, ROI surface, optional discount per discount-code-protocol.md
2. "Not the right time" → identify what changes the timing; offer to follow up at the right time
3. "Need to think about it" → probe the REAL concern (almost never "thinking"); offer a low-commitment next step
4. "Comparing with competitors" → ask what they're comparing on; speak to differentiation without trash-talking
5. "I'll get back to you" → soft close; if no, schedule the follow-up explicitly with date/time
6. "Send me info" → don't just send; ask what specifically would help them decide

## Buyer-signal recognition (the agent surfaces these in the analytics dashboard)

- **Urgency words** ("need this soon," "by [date]," "ASAP")
- **Decision-maker indicators** ("I" vs "we" / "my partner / spouse / boss")
- **Budget signals** (explicit dollar mentions, "cheapest option," "payment plans")
- **Comparison signals** (mentions other providers, asks about competitor features)
- **Trust signals** ("I've been following you," "my friend recommended you")
- **Ready-to-buy signals** ("how do I sign up," "what's next," "when can we start")

## Pricing reveal timing rules

- If customer explicitly asks price in first message → answer directly but qualify their need in the same response
- If customer asks "how much" without context → ask 1-2 qualifying questions FIRST, then quote a range
- If customer is mid-discovery and hasn't asked → don't volunteer; complete discovery
- If customer asks for "cheapest option" → don't lead with the cheapest; surface the right-fit option, then mention price tiers
- For high-ticket items (over $1k): never quote in cold first message; always qualify first

## Honesty floor (NON-NEGOTIABLE)

Never fabricate. Never deceive. Never false urgency. If the agent does not know, it says
so and (per `confidence-threshold-protocol.md`) escalates rather than bluffing.

