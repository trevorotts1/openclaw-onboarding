# Intelligent Follow-up Protocol

Activated when a sales conversation goes stalled. Runs a 10-touchpoint
sequence over 30 days. First 5 touchpoints fire in first 72 hours.

Hands off from Sales Brain (Step 9.23) when stalled-conversation detection
fires. Operator can also manually trigger ("follow up with <contact>").

## Tags this protocol creates (all `ZHC-` prefixed)

Every tag this protocol applies is created BY THE AGENT, so per the ZHC
Tag-Prefix Rule (`protocols/zhc-tag-prefix-protocol.md`) each one carries the
`ZHC-` prefix:

| Tag | Applied when |
|---|---|
| `ZHC-stalled-sales` | a sales conversation is detected as stalled (entry signal) |
| `ZHC-followup-cadence-1` … `ZHC-followup-cadence-10` | the matching touchpoint (T1…T10) fires — one per touch, so the operator can see exactly how far a contact has progressed through the sequence |
| `ZHC-cold-lead-released` | T10 fires and the contact is released (sequence complete, no conversion) |
| `ZHC-followup-opted-out` | the customer sends a negative signal (stop/unsubscribe/not interested) at any touchpoint |

The agent CREATES these tags (CREATE-TAG-FIRST per
`conversation-workflows-protocol.md` §D.1) before applying them, so they all
live in the reserved `ZHC-` namespace and never collide with operator tags.

## 10-touchpoint cadence

### First 72 hours — the critical window (5 touchpoints)

**T1 — Hour 1-2** (within 2 hours of conversation going quiet) — tag `ZHC-followup-cadence-1`
Soft check-in. Acknowledges they may still be considering. Doesn't ask
for anything yet.
Example: "Hey [name], no rush at all — just wanted to make sure you got
my last message. Around when works to circle back?"

**T2 — Hour 6-12** — tag `ZHC-followup-cadence-2`
Value-add touch. Share a relevant resource (case study, testimonial,
FAQ link) that matches their stage of consideration. NOT a sales pitch.
Reads from `knowledgebases/sales/` for relevant material.
Example: "Thought of you when I saw this — [link/testimonial]. No reply
needed, just figured it might be useful."

**T3 — Hour 24** — tag `ZHC-followup-cadence-3`
Direct re-engagement. Asks ONE specific question to get them talking
again.
Example: "Quick question while it's fresh — was the [specific thing
they mentioned] the main thing you were weighing?"

**T4 — Hour 48** — tag `ZHC-followup-cadence-4`
Concern probe. By now if they're going to come back, it's because of
an unspoken objection. Surface it gently.
Example: "If I'm overstepping, just say the word — but I get the sense
there might be something specific holding you back. Anything I can help
clarify?"

**T5 — Hour 72** — tag `ZHC-followup-cadence-5`
Soft close attempt. This is the last touchpoint in the critical window.
If they're going to buy, this is the moment.
Example: "Last thought from me on this round: [specific reason it makes
sense for them]. If you want to lock it in, here's the link. If not, I
won't keep pestering — I'll check back in a few days."

### Days 5-30 — long tail (5 touchpoints)

**T6 — Day 5** — tag `ZHC-followup-cadence-6`
Pattern interrupt. Switch channel or angle. If they originally came in
via SMS, try email here (or vice versa). Different format entirely.
Example: Short audio note, or a screenshot of something relevant, or a
question framed completely differently.

**T7 — Day 10** — tag `ZHC-followup-cadence-7`
Social proof. Share a fresh case study or recent customer result that
matches their profile. Reads from `knowledgebases/sales/`.
Example: "Random update — [customer] just hit [result]. Made me think
of our conversation."

**T8 — Day 15** — tag `ZHC-followup-cadence-8`
Incentive offer (IF policy permits). Discount code via Feature 28 (when
shipped) if operator has approved discount-as-recovery policy for this
product. If not permitted, send a free resource instead.
Example: "Wanted to send one last thing your way — [discount code] is
yours if it helps make this a yes."

**T9 — Day 22** — tag `ZHC-followup-cadence-9`
Final value touch. Pure helpfulness, no ask. Builds goodwill even if
this lead never converts.
Example: "Came across [resource] and figured I'd share — totally
unrelated to working together, just thought it was useful."

**T10 — Day 30** — tag `ZHC-followup-cadence-10`
Last call / release. Honest goodbye.
Example: "Last note from me — going to stop following up so I'm not
cluttering your inbox. If anything changes, you know where to find me.
Wishing you well with [their goal]."

After T10, tag contact as `ZHC-cold-lead-released` and stop the sequence.
Re-engagement only resumes if the customer reaches out themselves.

## Smart timing rules

- **Respect quiet hours** (Step 9.8) — never send during 10pm-7am local
  time. If a touchpoint is due during quiet hours, defer to start of
  next active window.
- **Respect channel preferences** — if customer originally engaged via
  SMS, send touchpoints via SMS (unless T6 pattern-interrupt switches
  channel). Don't switch to email/social without reason.
- **Re-engagement detection** — if customer responds at ANY point during
  the sequence, pause the sequence and return to normal conversation
  (likely back to Sales Brain Step 9.23). Resume only if they go silent
  again.
- **Negative signal detection** — if customer says "stop", "unsubscribe",
  "not interested", "leave me alone", or similar at any touchpoint, end
  the sequence immediately and tag `ZHC-followup-opted-out`. Also respect
  Step 9.9 compliance keyword handling.
- **Operator override** — operator can manually pause, skip, or end any
  contact's follow-up sequence at any time.

## Stalled detection (entry triggers)

The agent enters this sequence when ANY of these fire:

1. Customer was mid-sales-conversation, then no response for:
   - 2+ hours on real-time channel (SMS, FB Messenger, Instagram DM, Live Chat)
   - 24+ hours on async channel (email, LinkedIn)
2. Customer said "I'll think about it" or similar, without committing
   to a specific next step (date/time)
3. Customer asked for a quote/invoice, agent sent it, no response within
   48 hours
4. Customer was in active workflow, conversation ended without success
   AND without escalation

The Sales Brain (Step 9.23) hands off to this protocol when it detects
stalling. Until v5.7 ships F29 hand-off, agent tags contact
`ZHC-stalled-sales` for operator manual handling.

## Implementation — cron job per stalled conversation

When a conversation stalls, agent schedules cron jobs for each touchpoint:

```bash
# Pseudocode — actual cron management uses openclaw cron commands.
# Each touchpoint, when it fires, applies its own ZHC-followup-cadence-N tag
# (created CREATE-TAG-FIRST per conversation-workflows-protocol.md §D.1) so the
# operator can see exactly how far a contact got through the sequence.
schedule_touchpoint("T1",  contact_id, now + 1h,  tag="ZHC-followup-cadence-1")
schedule_touchpoint("T2",  contact_id, now + 8h,  tag="ZHC-followup-cadence-2")
schedule_touchpoint("T3",  contact_id, now + 24h, tag="ZHC-followup-cadence-3")
schedule_touchpoint("T4",  contact_id, now + 48h, tag="ZHC-followup-cadence-4")
schedule_touchpoint("T5",  contact_id, now + 72h, tag="ZHC-followup-cadence-5")
schedule_touchpoint("T6",  contact_id, now + 5d,  tag="ZHC-followup-cadence-6")
schedule_touchpoint("T7",  contact_id, now + 10d, tag="ZHC-followup-cadence-7")
schedule_touchpoint("T8",  contact_id, now + 15d, tag="ZHC-followup-cadence-8")
schedule_touchpoint("T9",  contact_id, now + 22d, tag="ZHC-followup-cadence-9")
schedule_touchpoint("T10", contact_id, now + 30d, tag="ZHC-followup-cadence-10")
```

When customer responds, all pending touchpoints for that contact are
canceled. When sequence completes (T10 fires or customer responds), all
crons are cleaned up. T10 additionally applies `ZHC-cold-lead-released`; a
negative signal at any touch applies `ZHC-followup-opted-out` and ends the
sequence immediately.

## Pre-Feature-15 implementation

This protocol uses direct OpenClaw cron scheduling until Feature 15
(Proactive Outreach Campaigns) ships. Once F15 lands, this protocol
will migrate to F15's outreach infrastructure for centralized campaign
management.

## Per-workflow customization

Operator can override the cadence per Conversation Workflow (Step 9.20)
by creating a `<workflow-id>--followup.md` file in the workflow's folder.
That overrides the default 10-touchpoint cadence for stalled conversations
of that specific workflow.

Example: a high-ticket coaching workflow might use a longer cadence (10
touchpoints over 60 days with first 5 in 7 days), while an impulse-buy
product might use a shorter cadence (5 touchpoints over 7 days).
```

**B. Append to MEMORY.md design principles — Rule 10:**

```markdown
### Rule 10 — Follow-up sequences front-load the first 72 hours

When a sales conversation stalls, the agent runs a 10-touchpoint sequence
over 30 days with the first 5 touchpoints in the first 72 hours. Industry
data: most sales close in 72h or never. The remaining 5 touchpoints over
27 days serve as long-tail re-engagement. Respect quiet hours, channel
preferences, and negative signals (stop/unsubscribe/not interested ends
sequence immediately).
```

**C. Append to Run Manifest:**

```markdown
