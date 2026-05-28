# Confidence Threshold Protocol

Before sending any drafted reply, the agent self-scores its confidence.
Below threshold = escalate instead of send.

## Confidence scoring

After drafting a reply (after Step 2 in AGENTS.md), prompt the agent's
own model:

"On a scale of 0 to 1, how confident are you in the reply you just
drafted? 0 = totally guessing or could be wrong, 1 = absolutely certain
this is accurate and appropriate. Consider: did you have enough context
to answer accurately? Is the answer factually correct based on available
info? Is the tone appropriate? Return only the number."

## Thresholds (operator-configurable)

| Channel | Default threshold |
|---|---|
| sms | 0.70 |
| email | 0.60 |
| facebook | 0.70 |
| facebook_comment | 0.75 (public-facing — be more careful) |
| instagram | 0.70 |
| linkedin | 0.70 |
| livechat | 0.65 |
| allinone | match active sub-channel |

## Below-threshold action

If confidence score < threshold for that channel:
1. Do NOT send the drafted reply.
2. Send the customer this holding message:
   "Great question — I want to make sure I get this exactly right.
   Let me check with my teammate and come back to you shortly."
3. Tag contact as `agent-low-confidence`.
4. Send operator the customer's message + the drafted reply + the
   confidence score, with three actions: "Approve and send draft,"
   "Edit and send," "Write fresh."
5. Wait for operator action. Apply operator's choice.

## Operator override

Operator can adjust thresholds in this file. Operator can also tell the
agent "skip confidence check for contact <id>" if the agent is being
overcautious with a specific contact.
```

**B. Insert into AGENTS.md** as Step 2.5 (between Step 2 reply draft and Step 3 send):

```markdown
### Step 2.5 — Confidence threshold check

After drafting the reply but BEFORE sending it, score confidence per
confidence-threshold-protocol.md. If below the channel's threshold,
send the holding message instead, notify operator with the draft, and
exit. Otherwise proceed to Step 3 (send the reply).
```

**C. Append to Run Manifest:** "Step 9.11 complete — confidence-threshold-protocol.md created, AGENTS.md Step 2.5 inserted."

