# Smart Playbook Switching — Always-Listening Interrupts Protocol (F44) — Step 9.38

> **DISTINCT from Step 9.33 (Intelligent Playbook Routing, `intelligent-routing-protocol.md`).**
> F33 is **ROUTE-AND-STAY**: the conversation has clearly and permanently pivoted to a new
> topic, so the agent switches workflows and continues there (it does NOT come back).
> **F44 is DETOUR-AND-RETURN**: the agent handles a short interruption (an urgent operator
> keyword, an FAQ, a compliance redirect, an aggression incident, a pixel-priority event)
> and then **returns to exactly where it was** in the original workflow. The original
> workflow is paused and resumed, never abandoned. The two coexist: F33 decides the
> long-run topic; F44 services brief interrupts without losing the long-run topic.

## The always-listening layer

In parallel with whatever workflow is currently active, the agent maintains an
"always-listening" interrupt layer. On EVERY inbound message, after the safeguards check
(Step 1.4) and the aggression scan (Step 1.35, F50), the agent checks the message against
the interrupt trigger set BEFORE continuing the active workflow.

### Interrupt triggers (what fires a detour)

1. **Operator urgent keywords** — operator-configured words that mean "stop and handle
   this now" (e.g. an internal escalation phrase, "URGENT", a VIP code). Operator-defined
   in `<MASTER_FILES_DIR>/interrupt-triggers.md`.
2. **FAQ types** — a question that the FAQ layer (F47, `smart-faq-protocol.md`) can answer
   in one sentence. (F47 is the LIGHTWEIGHT sibling: a SENTENCE, not a sub-flow. F47
   handles single-sentence FAQ detours itself; F44 handles heavier FAQ types that need a
   short sub-flow.)
3. **Compliance redirects** — a compliance trigger (`compliance-keyword-detection-protocol.md`,
   Step 9.9) that must be serviced immediately (e.g. a data-deletion request mid-booking),
   then control returns to the original flow.
4. **F50 aggression** — a Tier-2 aggression firing
   (`aggression-detection-protocol.md`) detours to the `aggression-handler` sub-flow, then
   returns with `ZHC-aggression-handled-and-resumed`.
5. **F49 pixel-priority** — a high-value pixel/intent signal (when F49 is installed) that
   warrants an immediate priority sub-flow, then a return to the original topic.

## DETOUR-AND-RETURN mechanics

When an interrupt fires, the agent does this, in order:

### 1. SAVE workflow state

Snapshot the active workflow so it can be resumed verbatim:

- `workflow_id` — the active conversation workflow.
- `step` — the exact step/phase the customer was on.
- `gathered_data` — everything collected so far (name, slots, answers, partial booking).
- `context` — the in-progress topic + the last agent turn.

Persist this snapshot to the interrupt stack in the contact's conversation log header AND
emit it to the interrupt JSONL (below). The stack is per-contact and ordered (LIFO).

### 2. EXECUTE the sub-flow

Run the interrupt's handler (FAQ answer, compliance action, aggression handler, pixel
priority sub-flow, or operator-urgent sub-flow). The sub-flow is itself a workflow and
follows all normal rules (safeguards, send-directive, conversation-log append).

### 3. RETURN to the saved state with a SOFT transition

When the sub-flow resolves, pop the stack and resume the saved workflow at the saved step
with a soft, natural re-entry line so the customer feels continuity, e.g.:

- "Coming back to where we were — you were telling me about [topic]…"
- "Okay, handled. Back to your [booking/quote] — we were on [step]."
- "Thanks for bearing with me. Picking back up: [the next question]."

Restore `gathered_data` so the agent never re-asks what it already had.

## Depth limit

**Maximum 2 levels deep.** An interrupt may itself be interrupted once (e.g. an FAQ detour
during which a compliance request arrives). After 2 levels, a third interrupt is NOT
nested — the agent escalates to the operator (it does not silently drop it, and it does
not keep nesting). The depth counter lives on the interrupt stack.

## Multiple simultaneous triggers

If more than one interrupt fires on the same message:

1. Handle them **highest priority first**. Priority order (highest → lowest):
   **compliance redirect → F50 aggression → operator urgent keyword → F49 pixel-priority
   → FAQ type.**
2. **Queue the rest** behind the first. After the highest-priority detour returns, drain
   the queue in priority order, each as its own detour-and-return, respecting the 2-level
   depth cap.
3. Only after the queue is empty does the agent resume the original saved workflow.

## Tags this protocol creates (all ZHC-prefixed, per MEMORY Rule 20)

- `ZHC-interrupt-handled` — a generic interrupt was serviced and the original flow resumed.
- `ZHC-faq-detoured` — an FAQ-type interrupt (heavier than a one-sentence F47 answer) was
  serviced via a short sub-flow and the original flow resumed.
- `ZHC-aggression-handled-and-resumed` — a Tier-2 aggression detour (F50) was serviced and
  the original flow resumed.

## Interrupt log (JSONL data contract, F52)

Every save / execute / return is appended to
`<MASTER_FILES_DIR>/interrupt-log.jsonl` — one JSON object per line:

```json
{"timestamp":"2026-05-30T14:30:00Z","event_type":"interrupt_saved","contact_id":"<contact_id>","trigger":"compliance_redirect","priority":1,"depth":1,"saved_workflow":"appointment-booking","saved_step":"collect-time-slot","gathered_data_keys":["name","service"]}
{"timestamp":"2026-05-30T14:30:18Z","event_type":"interrupt_executed","contact_id":"<contact_id>","trigger":"compliance_redirect","sub_flow":"gdpr-data-deletion","depth":1}
{"timestamp":"2026-05-30T14:30:40Z","event_type":"interrupt_returned","contact_id":"<contact_id>","resumed_workflow":"appointment-booking","resumed_step":"collect-time-slot","soft_transition":true,"tag":"ZHC-interrupt-handled"}
```

The JSONL schema is documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## openclaw.json toggles

```json
{
  "skill38": {
    "smart_playbook_switching": {
      "enabled": true,
      "max_interrupt_depth": 2
    }
  }
}
```

- `smart_playbook_switching.enabled` — default **true** (always-listening interrupts on).
- `smart_playbook_switching.max_interrupt_depth` — default **2**; beyond it, escalate to
  the operator rather than nest further.

## MEMORY.md (Rule 22)

The agent always listens for interrupts in parallel with the active workflow. On an
interrupt (operator-urgent keyword, FAQ type, compliance redirect, F50 aggression, F49
pixel-priority) it SAVES the workflow state, EXECUTES the sub-flow, then RETURNS to the
saved step with a soft "coming back to where we were" transition. This is
DETOUR-AND-RETURN, distinct from Step 9.33's route-and-stay. Max 2 levels deep, then
escalate. Multiple triggers: highest priority first, queue the rest. See
`<MASTER_FILES_DIR>/smart-playbook-switching-protocol.md`.
