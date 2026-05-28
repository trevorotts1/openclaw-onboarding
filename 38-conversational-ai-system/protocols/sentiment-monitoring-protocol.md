# Sentiment Monitoring Protocol

The agent scores every inbound customer message and escalates when
sentiment crosses thresholds.

## Scoring

On every inbound webhook (after safeguards check, before reply draft):
prompt the agent's own model with: "Score the sentiment of this customer
message as exactly one of: positive, neutral, negative, hostile. Return
only the single word."

Store the score in the contact's log file along with the message.

## Escalation triggers

Escalate to human (stop replying, notify operator) when ANY of these
fire:

1. Three CONSECUTIVE messages from this contact scored `negative` or
   `hostile` — pattern indicates frustration building
2. ANY single message scored `hostile` AND contains legal trigger words:
   "lawyer", "attorney", "sue", "lawsuit", "BBB", "Better Business
   Bureau", "FTC", "complaint", "fraud"
3. ANY single message scored `hostile` AND contains refund trigger
   words: "refund", "money back", "chargeback", "dispute", "cancel and
   refund"
4. ANY single message containing self-harm keywords: "kill myself",
   "end it all", "suicide", "harm myself", "give up on life" —
   immediate escalation, do NOT engage further, send a brief message
   pointing to crisis resources and alerting human

## Holding message on escalation

When escalating, send the customer this short message in their channel:

"Thanks for reaching out. I want to make sure you're taken care of
properly — I'm bringing in a teammate to follow up with you directly.
You'll hear from them soon."

For self-harm escalations, use this instead:

"I'm here. If you're in immediate crisis, please reach out to your
local emergency services. In the U.S., the 988 Suicide and Crisis
Lifeline is available 24/7 by calling or texting 988. I've also
notified our team so a real person can follow up with you."

Then: stop replying, tag contact as `escalated-sentiment`, notify
operator with the contact ID, the triggering message(s), the sentiment
scores, and the holding message that was sent.

## Operator override

Operator can clear the `escalated-sentiment` tag and tell the agent
"resume contact <id>" to reactivate AI replies.
```

**B. Insert into AGENTS.md** as Step 1.6 (right after the conversation-log-read in Step 1.5):

```markdown
### Step 1.6 — Score sentiment and check escalation triggers

Score the inbound message per sentiment-monitoring-protocol.md. If any
escalation trigger fires (3 consecutive negative/hostile, legal/refund
keywords, self-harm keywords), follow the holding-message + notify-
operator flow defined in the protocol. Exit.

Otherwise, continue to Step 2 (draft reply).
```

**C. Append to Run Manifest:** "Step 9.6 complete — sentiment-monitoring-protocol.md created, AGENTS.md Step 1.6 inserted."

