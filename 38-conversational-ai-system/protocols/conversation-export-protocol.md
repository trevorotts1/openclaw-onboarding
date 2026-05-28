# Conversation Export Protocol

When a customer requests a copy of their conversation history, the agent
compiles a clean export and sends it to them.

## Trigger phrases (case-insensitive substring match)

| Trigger | Action |
|---|---|
| "send me a copy of our conversation" | Compile + send export |
| "send me a transcript" | Compile + send export |
| "I want a copy of our messages" | Compile + send export |
| "email me what we discussed" | Compile + send export to email |
| "transcript of our chat" | Compile + send export |
| "history of our conversation" | Compile + send export |

(Operator can add channel-specific or language-specific triggers.)

## Compilation process

1. Read the contact's log file (verbatim + daily summaries + historical
   summaries).
2. Strip out:
   - Sentiment scores
   - Bot-detection signals
   - Confidence scores
   - Internal classification flags
   - Operator notes
   - PII redaction metadata markers (the redactions stay — the metadata
     about WHY they were redacted is internal)
3. Keep:
   - Customer messages (PII-scrubbed versions)
   - Agent replies
   - Timestamps
   - Channels
4. Format as clean markdown organized by date.

## Delivery

- If asked via SMS: SMS is too small for a transcript. Reply with: "Happy
  to send that — what email address should I use?" Wait for email, then
  send via email channel.
- If asked via email: Send as a markdown attachment OR as email body if
  short enough.
- If asked via Facebook/Instagram: Same as SMS — ask for email, send
  there.
- If asked via Live Chat / All-in-One: If on website, ask for email; if
  already in email-equipped chat, send inline.

## Confirmation

Before sending, confirm the email address you'll use:
"I'll send the transcript to <email>. Confirm that's the right address?"

After sending: "Sent — check your inbox at <email>. Anything else?"

## Compliance note

This is also how the agent satisfies GDPR Article 15 (right of access)
when applicable. Tag the contact `transcript-sent` so future audits show
the customer received their data.
```

**B. Append to `agent-capabilities-playbook.md`** Section 2 (Actions the agent can take) — add 2.5 — Send conversation transcript on customer request. Brief mention pointing to the protocol document.

**C. Append to Run Manifest:** "Step 9.12 complete — conversation-export-protocol.md created, capabilities playbook updated."

