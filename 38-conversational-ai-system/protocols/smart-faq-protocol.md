# Smart FAQ Tool Protocol (F47) — Step 9.41

> **The LIGHTWEIGHT sibling of F44 (`smart-playbook-switching-protocol.md`).** Where F44 is
> a SUB-FLOW (save state → run a mini-workflow → return), F47 is a **SENTENCE**: the agent
> answers a quick, known FAQ inline and immediately keeps going. No state save, no
> sub-flow, no depth counter — just a brief answer woven into the same turn, then back to
> the current step. F47 handles the cheap, one-sentence FAQ case; F44 handles FAQ TYPES
> that genuinely need a short sub-flow.

## The parallel FAQ-match layer

On every inbound, in parallel with the active workflow (after safeguards Step 1.4,
aggression Step 1.35, and the F44 interrupt check Step 1.42), the agent runs a quick FAQ
match. If the customer's message contains a question that the FAQ knowledge base answers
directly, the agent answers it in ONE sentence and RETURNS to the current step in the same
reply — it does NOT abandon or pause the workflow.

### FAQ knowledge base

Matches against:

```
<MASTER_FILES_DIR>/KnowledgeBases/business/faqs.md
```

A simple Q/A list (hours, pricing ballpark, location, parking, return policy, "do you do
X", etc.). The agent semantic-matches the customer's question to an entry; a confident
match triggers the inline answer.

### Per-workflow FAQ scope

Each workflow can narrow which FAQs are eligible mid-flow (so a sensitive booking step
isn't derailed by an unrelated FAQ):

```
conversation-workflows/<id>/faq-scope.md
```

`faq-scope.md` lists the FAQ topics that ARE answerable during this workflow (allow-list)
or those that are NOT (deny-list) — operator-tunable per workflow. With no `faq-scope.md`,
all FAQs are in scope.

## Inline answer + return (a SENTENCE, not a sub-flow)

When an FAQ matches, the agent answers it briefly and pivots straight back, in the SAME
reply, e.g.:

- "By the way, we're open 9–6 Mon–Fri. Coming back to your booking — what day works?"
- "Quick answer: yes, parking's free out front. Back to where we were — I had you down for…"

The pattern is literally **"By the way, [answer]. Coming back to [topic]…"** — one
sentence of answer, one phrase of return. No state snapshot is taken (there's nothing to
pause), the workflow step is unchanged, and the conversation continues seamlessly.

If the FAQ question is bigger than one sentence (it needs follow-up, a calculation, or a
mini-flow), the agent does NOT cram it inline — it hands off to the F44 interrupt layer as
an FAQ-type detour (`ZHC-faq-detoured`).

## Tag this protocol creates (ZHC-prefixed, per MEMORY Rule 20)

- `ZHC-faq-answered` — an inline one-sentence FAQ answer was given and the workflow
  continued uninterrupted. (Distinct from F44's `ZHC-faq-detoured`, which marks a heavier
  FAQ sub-flow.)

## FAQ detour log (JSONL data contract, F52)

Every inline FAQ answer is appended to
`<MASTER_FILES_DIR>/faq-detour-log.jsonl` — one JSON object per line:

```json
{"timestamp":"2026-05-30T17:05:00Z","event_type":"faq_answered_inline","contact_id":"<contact_id>","workflow":"appointment-booking","current_step":"collect-time-slot","faq_matched":"business_hours","in_scope":true,"answered_inline":true,"tag":"ZHC-faq-answered"}
```

The JSONL schema is documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

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

## MEMORY.md (Rule 25)

The agent answers quick known FAQs INLINE — a SENTENCE, not a sub-flow — then returns to
the current step in the same reply ("By the way, [answer]. Coming back to [topic]…").
Matches `KnowledgeBases/business/faqs.md`, scoped per workflow via `faq-scope.md`. Bigger
FAQ questions hand off to F44 as a detour. Tag `ZHC-faq-answered`. See
`<MASTER_FILES_DIR>/smart-faq-protocol.md`.
