# Smart FAQ Tool Protocol (F47) — Step 9.41

> F47 is the lightweight sibling of F44 — a SENTENCE, not a sub-flow.

F47 is the **lightweight sibling** of F44 (smart-playbook-switching-protocol.md).
Where F44 runs a heavy interrupt SUB-FLOW (save state → run sub-flow → return),
F47 answers a quick factual question in **one SENTENCE inline** and immediately
continues the current step — no state save/restore, no sub-flow, no workflow
switch. It is the cheapest, most common detour: the customer asks a simple known
question mid-workflow, gets a one-line answer, and the workflow keeps going.

**The one-line rule:** if the honest answer fits in one sentence and changes
nothing about where the conversation is, it is an **F47 sentence**. If answering
it well needs a follow-up question, a calculation, a quote, or a mini-flow, it is
an **F44 sub-flow** (`ZHC-faq-detoured`) — never an inline cram.

## The model — a parallel FAQ-match layer alongside the active workflow

While ANY workflow is active, a parallel FAQ-match layer runs on every inbound
**alongside the F44 always-listening layer** (both live in AGENTS.md Step 1.42:
after safeguards Step 1.4, aggression Step 1.35, and the F44 interrupt check). It
asks one question of every inbound: "is this a simple factual question I already
have an answer to?" If yes, and the answer is short enough to state in a sentence,
F47 handles it inline and the active workflow is never paused. F44 and F47 are the
TWO halves of the same always-listening layer — F44 owns the heavy detours, F47
owns the one-sentence asides.

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
step is unchanged; the agent simply prepended a one-line answer and continued the
SAME step in the SAME reply.

## When the question is bigger than one sentence → hand to F44

If the FAQ question is bigger than one sentence — it needs a follow-up, a
calculation, a quote, or a mini-flow — the agent does NOT cram it inline. It hands
off to the F44 interrupt layer as an FAQ-type detour (save state → run the
sub-flow → return), tagged `ZHC-faq-detoured` (F44's tag, NOT F47's). The split is
deliberate: F47 keeps replies fast and the customer on-task; F44 gives heavier
questions the room they need without losing the customer's place. A deep
pricing-negotiation question is an F33 route or an F44 detour, never an F47
sentence.

## Per-workflow FAQ scope (sales-relevant vs ops-relevant)

Each conversation workflow can scope WHICH FAQs are in-bounds for it, in:

```
<MASTER_FILES_DIR>/conversation-workflows/<workflow-id>/faq-scope.md
```

The scope sorts the client's FAQs into the ones this workflow may answer inline
(its **in-scope** topics) and the ones it must NOT inline (its **out-of-scope**
topics — defer or hand to F44). The practical split is **sales-relevant vs
ops-relevant**: a sales workflow inlines sales-relevant one-liners (pricing tiers,
guarantees, what's included) and defers ops questions (order status, returns
mechanics); an ops/booking workflow inlines ops-relevant one-liners (hours,
location, what to bring) and defers a deep sales/pricing-negotiation answer to the
sales workflow.

Format:

```markdown
# FAQ scope for workflow: <workflow-id>

## In-scope FAQ topics (answer inline during this workflow — sales-relevant or ops-relevant for THIS flow)
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

## Relationship to F44 — sub-flow vs sentence (the explicit difference)

| | F44 — Smart Switching | F47 — Smart FAQ Tool |
|---|---|---|
| Weight | a SUB-FLOW (save → execute → return) | a SENTENCE (inline answer, no state change) |
| Trigger | the interrupt needs real handling (operator-urgent, compliance, aggression, a heavier FAQ) | the interrupt is a simple known factual question answerable in one line |
| State | SAVES + RESTORES workflow state (step + gathered data + context) | NONE — the step is unchanged; the answer is prepended in the same reply |
| Reply shape | "…handling the aside… Coming back to where we were…" (state restored) | "By the way, [answer]. Coming back to [topic]…" (step never left) |
| Tag | `ZHC-interrupt-handled` / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed` | `ZHC-faq-answered` |
| Step | 9.38 | 9.41 |

The F44 always-listening layer hands a simple-factual-question interrupt DOWN to
F47 (the cheaper path); F44 keeps the heavier sub-flow detours. The reverse is
also true: when F47 sees a question that is bigger than one sentence, it hands it
UP to F44 as a detour (`ZHC-faq-detoured`).

## Tag

Applied programmatically → `ZHC-` prefix (zhc-tag-prefix-protocol.md):

- `ZHC-faq-answered` — an FAQ was answered inline during a workflow. (Distinct
  from F44's `ZHC-faq-detoured`, which marks a heavier FAQ sub-flow handed up to
  F44 — the inline sentence and the sub-flow detour carry DIFFERENT tags.)

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
Matches `KnowledgeBases/business/faqs.md`, scoped per workflow via `faq-scope.md`
(sales-relevant vs ops-relevant). Bigger FAQ questions hand off to F44 as a detour
(`ZHC-faq-detoured`). Tag `ZHC-faq-answered`. See MEMORY Rule 25, appended by
`scripts/06-append-memory-rules.sh`.

## Cross-references

- Heavier sibling: `protocols/smart-playbook-switching-protocol.md` (F44, Step 9.38).
- Confidence gate on low-confidence matches: `protocols/confidence-threshold-protocol.md` (Step 9.11).
- FAQ knowledge base: `<MASTER_FILES_DIR>/KnowledgeBases/business/faqs.md`.
- Per-workflow scope: `conversation-workflows/<workflow-id>/faq-scope.md`.
- Tag namespace: `protocols/zhc-tag-prefix-protocol.md`.
- AGENTS.md Step 1.42 (always-listening layer covers both F44 + F47): `scripts/05-update-agents-md.sh` (marker `STEP_1_42_INTERRUPTS_AND_FAQ`).
- INSTRUCTIONS.md Step 9.41.
