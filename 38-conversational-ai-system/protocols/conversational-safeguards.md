# Conversational Safeguards Protocol

This document defines the three hard guardrails the agent applies to
every active conversation. They're checked BEFORE the agent drafts a
reply on each turn.

## Safeguard 1 — High-volume activity warning (20 messages / 1 hour)

If a single contact has exchanged more than 20 back-and-forth messages
with the agent within any rolling 1-hour window, the agent must:

1. Continue replying to the current turn (don't drop the customer mid-
   conversation — that's worse than the warning).
2. After sending the reply, notify the operator via their primary admin
   channel (Telegram if available, otherwise email).
3. The notification should include: contact name, contact ID, channel,
   message count in past hour, brief summary of what the conversation
   is about.
4. Suggested operator actions: review the conversation in the log file,
   decide whether this is a real engaged customer (great) or a runaway
   loop / abuse (intervene).
5. Don't notify again for the same contact for another hour, to avoid
   notification spam.

Implementation: count messages logged in `<MASTER_FILES_DIR>/
conversational-logs/<contact_id>__<name>.md` with timestamps in the past
60 minutes. If count > 20 AND no warning fired for this contact in the
past hour, fire the warning.

## Safeguard 2 — Long-conversation pause (50 messages cumulative)

If a single contact has exchanged more than 50 back-and-forth messages
with the agent in their full conversation history (cumulative across all
time, all channels), the agent must:

1. Send the customer a polite holding message: "Thanks for your patience —
   I want to make sure I'm helping you well. I'm bringing in a teammate
   to review our conversation and get back to you shortly."
2. STOP replying to further messages from this contact until the
   operator explicitly grants permission to resume.
3. Publish the full conversation history (the contact's log file) to
   the operator via their primary admin channel.
4. The notification to the operator includes: contact name + ID, total
   message count, link to the full log file, and three action options:
   "Resume — continue replying," "Pause indefinitely — let me handle
   this manually," "Block — don't reply to this contact ever again."
5. The operator's choice is logged in the contact's log file and acted
   on next time a webhook arrives from this contact.

Implementation: count total entries in the contact's log file (verbatim
+ daily summaries + historical summaries combined). If > 50, set a
"paused" flag in the file header and trigger the operator notification.
On every subsequent inbound webhook, check the flag first — if paused,
don't reply.

## Safeguard 3 — Bot-detection protocol

If the agent detects it's talking to another AI/bot/automated system
(not a human), it must STOP the conversation at the first turn it can
confirm this.

Signals that suggest the other party is a bot:

- Replies are inhumanly fast (under 2 seconds, repeatedly)
- Replies contain templated patterns: "I am an AI assistant trained to..."
  / "As a language model..." / "I cannot..." / "I'm here to help with..."
- Replies are exactly the same length / structure across multiple turns
- Replies reference platforms/APIs that humans wouldn't typically
  reference in casual conversation ("according to my training data",
  "per my context window")
- Auto-reply markers: "[Auto-reply]", "This is an automated message",
  "Do not reply"
- Reply opens with formal greeting + immediately asks for a meeting/
  demo without acknowledging the agent's previous message (mass-send
  bot pattern)
- Customer's contact ID has no phone number, no email, no first name —
  just a generated identifier (bot account)

If two or more signals are present in a single reply, OR a single
extremely strong signal (like "I am an AI assistant"), the agent must:

1. Stop replying immediately. Do not send another message.
2. Log the bot-detection event in the contact's log file with the
   triggering message text and which signals fired.
3. Apply a `bot-detected` tag to the contact in GHL via the GHL skill
   (or `POST /contacts/{contactId}/tags`).
4. Notify the operator with: contact ID, triggering message, signals
   that fired. No further action needed unless the operator wants to
   investigate.
5. Don't reply to future messages from this contact unless the operator
   explicitly clears the bot-detected flag.

If only one weak signal is present, continue replying but log the
suspicion. Two weak signals = escalate.

> **Tag note (v1.5.0).** Bot detection is NOT rebuilt by the aggression work —
> this Safeguard 3 logic is unchanged. The only change going forward is the tag:
> NEW bot-suspicion firings apply `ZHC-bot-suspected` (the reserved `ZHC-`
> namespace, per `protocols/zhc-tag-prefix-protocol.md`). The legacy
> `bot-detected` tag is not migrated (the prefix rule is not retroactive).

## Safeguard 4 — Aggression detection (two-tier) — F50 extension

The safeguard family is EXTENDED (not rebuilt) with a two-tier aggression
classifier that runs PRE-routing, before any workflow match and before any
reply-drafting LLM spend (AGENTS.md Step 1.35). It does NOT replace bot-detection
(Safeguard 3) — the two are independent.

- **Tier 1 — TENSION (low):** multiple irritation words, a sustained 3+ message
  frustration streak, or `!!!`/`???` → tag `ZHC-tension-detected`, heighten
  attention, NO reroute, no operator notify.
- **Tier 2 — AGGRESSION (high):** profanity directed AT the agent, threats
  (legal/physical/public), ALLCAPS+profanity+direct-address, or 3+ signals in one
  message → tag `ZHC-aggression-detected`, route to the `aggression-handler`
  workflow (an F44 detour-and-return), notify the operator.
- **ALL CAPS ALONE does NOT fire.** Sensitivity is operator-tunable
  (`lenient`/`standard`/`strict`) in `openclaw.json`
  (`skill38.aggression_detection.{enabled,sensitivity}`). Firings + reasoning are
  logged to `<MASTER_FILES_DIR>/aggression-detection-log.md` AND emitted as JSONL
  to `<MASTER_FILES_DIR>/aggression-detection-log.jsonl`.

Full rules, signals, the sensitivity threshold table, and the JSONL data
contract: `protocols/aggression-detection-protocol.md` (Step 9.37).

## Safeguard ordering

The agent checks safeguards in this order on every reply turn:

1. Is contact flagged as bot? → if yes, don't reply, exit.
2. Is contact paused (50+ messages)? → if yes, don't reply, exit.
3. Does this turn trip bot-detection signals? → if yes, stop, log, tag
   (`ZHC-bot-suspected` going forward), notify, exit.
3.5. Does this turn trip AGGRESSION (Safeguard 4 / Step 1.35,
   aggression-detection-protocol.md)? Tier 2 → tag `ZHC-aggression-detected`,
   route to the aggression-handler sub-flow (F44 detour), notify operator. Tier 1
   → tag `ZHC-tension-detected`, continue with heightened attention. ALL CAPS
   ALONE never fires. This runs PRE-routing, before LLM spend.
4. Has this contact hit 20+ messages in past hour? → if yes, reply
   normally but queue a warning to operator after reply.
5. Has this contact hit 50+ total messages with this reply? → if yes,
   send holding message instead of normal reply, pause contact, notify.
6. Normal reply path.

## Operator override

The operator can clear any flag at any time by editing the contact's
log file header (removing the `bot-detected` / `paused` line) or by
telling the agent "resume contact <id>" / "unblock contact <id>" —
the agent updates the log file accordingly.
```

### Update AGENTS.md to reference the safeguards

In the AGENTS.md "Inbound Webhook Message Classification" section (added in Step 7), insert a new Step 1.4 right before Step 1.5 (the conversation log read):

```markdown
### Step 1.4 — Check safeguards BEFORE reading the log or drafting a reply

Read the contact's log file header. If it has `bot-detected: true` OR
`paused: true`, do not reply. Exit silently.

Read the past hour of verbatim entries. If count > 20, queue a high-
volume warning to operator (to fire after this reply is sent).

Read the total message count (verbatim + summaries). If > 50, send the
holding message described in conversational-safeguards.md Section 2,
set the `paused: true` flag in the log header, publish the conversation
to the operator. Exit.

Examine the customer's current message for bot-detection signals per
conversational-safeguards.md Section 3. If two or more signals fire,
stop, log, tag, notify operator. Exit.

Otherwise, proceed to Step 1.5 (read full log for continuity) and Step
2 (draft and send reply).
```

### Add the safeguards check to the System Health Heartbeat (Step 3.5H)

The monthly heartbeat should also report:
- Number of high-volume warnings fired in past 30 days
- Number of paused contacts currently active
- Number of bot-detected contacts blocked in past 30 days

This gives the operator a clear picture of conversation hygiene each month.

### ✅ Checkpoint E — Agent is safety-ready and memory-ready (Phase 4 complete)

Before proceeding to Phase 5, verify ALL of the following pass:

- [ ] AGENTS.md backup exists AND "Inbound Webhook Message Classification" section successfully appended
- [ ] All eight communication playbooks (SMS, Email, Facebook Messenger, Facebook Comments, Instagram, LinkedIn, Live Chat, All-in-One Chat) were created
- [ ] AGENTS.md pointer section references real playbook URLs/paths (no `<will be added>` placeholders)
- [ ] `conversational-logs/` folder created in `MASTER_FILES_DIR`
- [ ] `conversation-log-protocol.md` written to `MASTER_FILES_DIR`
- [ ] `conversational-safeguards.md` written to `MASTER_FILES_DIR`
- [ ] AGENTS.md Step 1.4 (safeguards check) and Step 1.5 (log read) both inserted
- [ ] Cron job `conversation-log-summarizer` registered (visible in `openclaw cron list`)
- [ ] Cron job `system-health-heartbeat` registered (visible in `openclaw cron list`)

Append to Run Manifest with checkpoint result, then proceed.

If FAILED → STOP, do not proceed to Phase 5, report to operator.

---

# PHASE 5 — Install Advanced Features (v5.0)

This phase installs the seven advanced features that elevate the system to top-tier conversational AI. Each feature creates its own protocol document and modifies AGENTS.md to reference it. The agent reads these protocols on every reply turn.

**Execution order matters.** Some features check each other's outputs (e.g., compliance check happens before PII scrubbing, which happens before sentiment analysis). Follow the order strictly.

