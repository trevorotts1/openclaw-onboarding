# PII Scrubbing Protocol

Before writing any customer message to a conversation log file, the
agent scans for and redacts sensitive data patterns. Original digits
are never written to disk.

## Patterns to detect and redact

| Pattern type | Regex (Python-style) | Replacement |
|---|---|---|
| SSN (US) | `\b\d{3}-\d{2}-\d{4}\b` | `[REDACTED — SSN]` |
| Credit card | `\b(?:\d[ -]*?){13,19}\b` (Luhn-validated) | `[REDACTED — credit card, last 4: NNNN]` |
| Password label | `(?i)(password|pwd|passwd)\s*[:=]\s*\S+` | `password: [REDACTED]` |
| API key label | `(?i)(api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*\S+` | `api_key: [REDACTED]` |
| Bank routing | `\b\d{9}\b` (if context includes "routing" / "ABA") | `[REDACTED — bank routing]` |
| Driver's license | varies by state — match alphanumeric IDs near "DL", "driver's license", "DLN" | `[REDACTED — driver's license]` |

For credit cards: keep last 4 digits in the redaction marker so the
operator can investigate (e.g., "[REDACTED — credit card, last 4:
4242]") without retaining the full number.

## When to apply

PII scrubbing runs BEFORE the customer's message is appended to the
verbatim section of their conversation log. Apply once at log-write
time. Once redacted, never un-redact.

The agent's REPLY can still reference the data to act on the
customer's request (e.g., look up an account by partial card) — but
the agent's reply also gets scrubbed before being written to the log.

## What's NOT redacted

Email addresses, phone numbers, first/last names, and addresses are
NOT redacted by default. These are routine contact data that lives
in GHL and is needed for conversation continuity. Operator can extend
the patterns list if they need stricter redaction for compliance
(e.g., healthcare clients may want addresses redacted).

## Redaction metadata in logs

The redacted entry still carries enough metadata for an operator audit
trail without holding the raw data:

```
> Customer (12:34): "My card is [REDACTED — credit card, last 4: 4242]"
> Agent (12:34): "Thanks — I see the card ending in 4242. Let me look that up..."
```
```

**B. Modify `conversation-log-protocol.md`** to add at the top of "Logging rules":

```markdown
### Pre-write step: PII scrubbing

Before appending ANY entry (customer or agent) to the verbatim section,
apply pii-scrubbing-protocol.md to the entry text. Write the scrubbed
text, not the original.
```

**C. Append to Run Manifest:** "Step 9.7 complete — pii-scrubbing-protocol.md created, conversation-log-protocol.md updated."

