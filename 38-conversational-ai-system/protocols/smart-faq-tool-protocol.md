# Smart FAQ Tool Protocol (F47) — Step 9.41

F47 is the **lightweight sibling** of F44 (smart-playbook-switching-protocol.md).
Where F44 runs a heavy interrupt SUB-FLOW (save state → run sub-flow → return),
F47 answers a quick factual question in **one SENTENCE inline** and immediately
continues the current step — no state save/restore, no sub-flow, no workflow
switch. It is the cheapest, most common detour: the customer asks a simple known
question mid-workflow, gets a one-line answer, and the workflow keeps going.

## The model — a parallel FAQ-match layer

While any workflow is active, a parallel FAQ-match layer runs on every inbound
(alongside the F44 always-listening layer, after safeguards Step 1.4, aggression
Step 1.35, and the F44 interrupt check Step 1.42). It asks: "is this a simple
factual question I already have an answer to?" If yes, and the answer is short
enough to state in a sentence, F47 handles it inline.

## FAQ source

The agent matches the question against the client's FAQ knowledge base:

```
<MASTER_FILES_DIR>/KnowledgeBases/business/faqs.md
```

Format (Q/A pairs the agent matches semantically):

```markdown
# Frequently Asked Questions

## Q: What are your hours?
A: <ANSWER — one or two sentences>

## Q: Do you offer refunds?
A: <ANSWER — one or two sentences>

## Q: Where are you located?
A: <ANSWER — one or two sentences>
```

A match requires reasonable confidence that the customer's question is the same
question as a stored FAQ. If confidence is low, F47 does NOT answer from the FAQ
file — it falls through to the normal reply path (or F44 if a heavier detour is
warranted), and the confidence-threshold protocol (Step 9.11) governs.

## Behavior — brief answer, then RETURN to the current step

On a match, the agent:

1. Gives the brief FAQ answer inline.
2. Immediately returns to the current workflow step with a soft transition — the
   answer is an aside, not a topic change:

> "By the way, [answer]. Coming back to [topic]…"

Examples:

> "By the way, we're open 9-5 weekdays. Coming back to picking your appointment
> time — did Tuesday or Wednesday work better for you?"

> "Quick answer — yep, full refunds within 30 days. Now, back to your order…"

Because there is no sub-flow, there is nothing to save or restore — the workflow
step is unchanged; the agent simply prepended a one-line answer.

If the FAQ question is bigger than one sentence (it needs follow-up, a
calculation, or a mini-flow), the agent does NOT cram it inline — it hands off to
the F44 interrupt layer as an FAQ-type detour (`ZHC-faq-detoured`).

## Per-workflow FAQ scope

Each conversation workflow can scope WHICH FAQs are in-bounds for it, in:

```
<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>/faq-scope.md
```

Format:

```markdown
# FAQ scope for workflow: <workflow-id>

## In-scope FAQ topics (answer inline during this workflow)
- hours
- refunds
- shipping

## Out-of-scope (do NOT inline; defer or hand to F44)
- pricing negotiation   # too involved for a one-liner — route via sales workflow
```

Scoping prevents a booking workflow from inlining a deep pricing-negotiation
answer that really deserves the sales workflow's full treatment (that is an F33
route or an F44 detour, not an F47 sentence). If no `faq-scope.md` exists for a
workflow, the default is "all FAQs are in-scope as one-liners."

## Relationship to F44

| | F44 — Smart Switching | F47 — Smart FAQ Tool |
|---|---|---|
| Weight | a SUB-FLOW (save → execute → return) | a SENTENCE (inline answer, no state change) |
| When | the interrupt needs real handling (operator-urgent, compliance, aggression) | the interrupt is a simple known factual question |
| State | saves + restores workflow state | none — the step is unchanged |
| Tag | `ZHC-interrupt-handled` / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed` | `ZHC-faq-answered` |
| Step | 9.38 | 9.41 |

The F44 always-listening layer hands a simple-factual-question interrupt to F47
(the cheaper path); F44 keeps the heavier sub-flow detours.

## Tag

Applied programmatically → `ZHC-` prefix (zhc-tag-prefix-protocol.md):

- `ZHC-faq-answered` — an FAQ was answered inline during a workflow. (Distinct
  from F44's `ZHC-faq-detoured`, which marks a heavier FAQ sub-flow.)

## openclaw.json toggles

```json
{
  "skill38": {
    "smart_faq": {
      "enabled": true
    }
  }
}
```

- `smart_faq.enabled` — default **true** (inline FAQ answering on).

## Logging (the data contract — F52)

Every inline FAQ answer is recorded as JSONL, one line appended to
`<MASTER_FILES_DIR>/faq-detour-log.jsonl`:

```json
{"timestamp":"2026-05-30T18:20:09Z","event_type":"faq_answered","contact_id":"<CONTACT_ID>","channel":"sms","workflow_id":"appointment-booking","faq_topic":"hours","matched":true,"in_scope":true,"returned_to_step":"phase-1-acknowledge-qualify","tag_applied":"ZHC-faq-answered"}
```

JSONL schema (one object per line):

| field | type | meaning |
|---|---|---|
| `timestamp` | string (ISO-8601 UTC) | when the FAQ was answered |
| `event_type` | string | `faq_answered` (always, for F47 firings) |
| `contact_id` | string | GHL contact id |
| `channel` | string | inbound channel |
| `workflow_id` | string | the workflow active when the FAQ was answered |
| `faq_topic` | string | the matched FAQ topic/key |
| `matched` | boolean | whether a stored FAQ matched (always `true` for a firing) |
| `in_scope` | boolean | whether the topic was in the workflow's faq-scope |
| `returned_to_step` | string | the workflow step the conversation continued on (unchanged) |
| `tag_applied` | string | `ZHC-faq-answered` |

The JSONL schema is also documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## MEMORY.md (Rule 25)

The agent answers quick known FAQs INLINE — a SENTENCE, not a sub-flow — then returns to
the current step in the same reply ("By the way, [answer]. Coming back to [topic]…").
Matches `KnowledgeBases/business/faqs.md`, scoped per workflow via `faq-scope.md`. Bigger
FAQ questions hand off to F44 as a detour. Tag `ZHC-faq-answered`. See MEMORY Rule 25,
appended by `scripts/06-append-memory-rules.sh`.

## Cross-references

- Heavier sibling: `protocols/smart-playbook-switching-protocol.md` (F44, Step 9.38).
- Confidence gate on low-confidence matches: `protocols/confidence-threshold-protocol.md` (Step 9.11).
- FAQ knowledge base: `<MASTER_FILES_DIR>/KnowledgeBases/business/faqs.md`.
- Per-workflow scope: `conversation-workflows/<workflow-id>/faq-scope.md`.
- Tag namespace: `protocols/zhc-tag-prefix-protocol.md`.
- AGENTS.md Step 1.42 (always-listening layer covers both F44 + F47): `scripts/05-update-agents-md.sh` (marker `STEP_1_42_INTERRUPTS_AND_FAQ`).
- INSTRUCTIONS.md Step 9.41.
