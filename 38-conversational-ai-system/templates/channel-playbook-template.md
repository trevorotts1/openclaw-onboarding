<!--
Operator note: This file is a VERBATIM extraction from the source playbook
`openclaw-cloudflare-tunnel-prompt (1).md` (v5.14), lines 1675–1764 (Step 8
Channel Communication Playbook seed template). When scaffolding a real channel
playbook, substitute placeholders: `<Channel>` / `<CHANNEL_NAME>` (e.g. SMS,
Email, IG DM), `<Client Name>` / `<CLIENT_BUSINESS_NAME>`, and the escalation
target referenced in "Escalation rules" (`<ESCALATION_TARGET>`).
-->

# <Channel> Communication Playbook — <Client Name>

**Status:** STARTER TEMPLATE — fill in the sections below to teach your
agent how to respond on this channel. Until you fill these in, the agent
will use generic professional defaults.

Last updated: <date>
Created by: OpenClaw GHL Webhook Playbook v5.4

---

## 1. Tone & Voice

How should the agent sound on <channel>?
- Formality level (casual / professional / formal):
- Personality traits to embody:
- Brand voice phrases the agent should USE:
- Phrases the agent should NEVER USE:

## 2. Signature

How does the agent sign off on <channel>?
- Default signature:
- Brand name to reference:
- Contact info to include (if any):

## 3. Reply length

How long should typical replies be on <channel>?
- (SMS-specific: keep under 160 chars when possible)
- (Email-specific: 2–4 short paragraphs)
- (Facebook/Instagram-specific: 1–3 sentences, conversational)

## 4. Common scenarios & example replies

### Scenario A: Customer asking a general question
Example reply:
> [Fill in with a real example reply]

### Scenario B: Customer interested in a service
Example reply:
> [Fill in]

### Scenario C: Customer with a complaint
Example reply:
> [Fill in]

### Scenario D: Customer asking for pricing
Example reply:
> [Fill in]

## 5. Escalation rules

When should the agent NOT reply and instead alert a human?
- Triggers (e.g., legal threats, refund requests over $X, urgent medical):
- How to escalate (Telegram alert to operator, mark flow as "needs human"):
- Who gets the alert:

## 6. Off-limits topics

What should the agent never discuss on <channel>?
- (e.g., pricing specifics, medical advice, legal advice, competitor names)

## 7. Channel-specific notes

<For Facebook: "Replies must happen within 24 hours of the customer's
last message — Facebook's policy. Outside the window, escalate to human.">

<For Instagram: "Same 24-hour rule. Also: don't reply to first-time DMs
that look like the standard 'hey beautiful' or 'love your content' spam
opener.">

<For SMS: "Watch for STOP / UNSUBSCRIBE keywords — never reply to those
to avoid violating SMS compliance.">

<For Email: "Match the subject line format the customer used. Reply-all
only if the original email had multiple recipients.">

---

## How to use this playbook

The agent reads this document on every reply turn for this channel.
Fill in the sections above with examples and rules specific to YOUR
business. The more concrete examples you give, the better the agent's
replies will sound.

You can edit this playbook anytime — the agent will pick up changes on
the next message.
```
