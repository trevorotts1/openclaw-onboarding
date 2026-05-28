<!-- OPERATOR HEADER (5 lines) — DO NOT EDIT BELOW -->
<!-- Source: openclaw-cloudflare-tunnel-prompt (1).md v5.14 — lines 2499-2545 -->
<!-- Section: Step 9.10 — Install Multi-Language Detection -->
<!-- This file is a VERBATIM extraction from the v5.14 playbook. Do not summarize. -->
<!-- Patch source: skill-38-patch-1 agent — 2026-05-28 -->

## Step 9.10 — Install Multi-Language Detection

When a customer writes in a non-English language, the agent matches their language.

**A. Append to `agent-capabilities-playbook.md`** a new Section 7 — Multi-Language Support (or write inline if the file doesn't exist yet — Step 10 creates it):

```markdown
## 7. Multi-language detection and matching

On every inbound message, before drafting a reply:

1. Detect the language of the customer's message. Use the agent's own
   model with a structured prompt: "Identify the language of this
   message in two-letter ISO 639-1 code (en, es, fr, etc.) or return
   'unknown' if unclear. Return only the code."

2. If the contact's log file header has a `preferred_language` field,
   default to that. The detection result becomes a soft signal.

3. If the detected language ≠ stored preferred language, the customer
   may have switched intentionally. Match the current message's
   language for this reply.

4. If no preferred language is stored, write the detected language to
   the log file header on first contact.

5. If detection returns "unknown" or confidence is low, ask the
   customer once: "Would you prefer English or [detected language]?"
   Lock in the answer.

## Reply language

Once language is determined, the agent's reply MUST be in that
language. The same model handles most major languages natively; just
prompt for the target language in the reply.

## Communication Playbooks

If the operator has per-language sections in a channel's Communication
Playbook (e.g., "SMS Communication Playbook — Spanish section"), the
agent reads that section. Otherwise, the agent uses the default
English-language playbook content translated by the model.
```

**B. Update the contact's log file header structure** (in conversation-log-protocol.md) to include a `preferred_language` line populated on first contact.

**C. Append to Run Manifest:** "Step 9.10 complete — multi-language section added to capabilities playbook (or pending Step 10 if file not yet created), log header format updated."
