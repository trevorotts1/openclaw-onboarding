# Smart Playbook Switching / Always-Listening Interrupts Protocol (F44) — Step 9.38

> **This is NOT F33 (Intelligent Playbook Routing).** F33
> (`intelligent-routing-protocol.md`, Step 9.33) is **route-and-stay**: the
> conversation has genuinely pivoted to a new topic, so the agent SWITCHES the
> active workflow and stays there. F44 is **detour-and-return**: the active
> workflow is still the customer's real goal, but something urgent must be
> handled *right now* without abandoning it — so the agent SAVES the current
> state, runs a short sub-flow, and RETURNS to exactly where it left off. F33
> changes the destination; F44 takes a detour and comes back. They are distinct
> and both ship.
>
> **BUILD path:** caf-direct (Skill 44, Option 1 — PRIMARY) when the Firebase token is present; else Build-with-AI paste (Option 2). See references/GHL_AI_LAYERS.md.

## The model — an always-listening layer parallel to the active workflow

While ANY conversation workflow is active, a lightweight **always-listening
layer** runs in parallel on every inbound. It does NOT draft the reply; it only
asks: "does this inbound contain something that must interrupt the current
workflow?" If yes, it fires a DETOUR:

```
SAVE workflow state  →  EXECUTE the interrupt sub-flow  →  RETURN to saved state (soft transition)
```

The active workflow's step, gathered data, and context are preserved across the
detour, so the customer never has to repeat themselves.

## Interrupt triggers (what the always-listening layer watches for)

A detour fires when the inbound matches any of:

1. **Operator urgent keywords** — operator-configured words that mean "stop and
   handle this" (e.g. "urgent", "emergency", "cancel my order now", or custom
   per-client words). Operator-defined in `<MASTER_FILES_DIR>/interrupt-triggers.md`.
2. **FAQ types** — a question that the FAQ layer (F47,
   `smart-faq-tool-protocol.md`) can answer in one sentence. NOTE: F47 is the
   *lightweight sibling* — a SENTENCE, not a sub-flow — and is the preferred,
   cheapest detour for a simple factual question. F44 owns the heavier
   sub-flow detours; F47 handles the one-liner case (see "Relationship to F47").
3. **Compliance redirects** — a mid-workflow message that trips a compliance
   keyword (Step 0.7) requiring an immediate compliance response before anything
   else.
4. **F50 aggression** — a Tier-2 aggression firing
   (`aggression-detection-protocol.md`) routes to the aggression-handler sub-flow
   as a detour, then returns (tag `ZHC-aggression-handled-and-resumed`).
5. **F49 pixel-priority** — if pixel/tracking-priority signals are enabled, a
   high-priority pixel event can interrupt to capture the moment, then return.

## State save / execute / return

### 1. SAVE workflow state

Before executing the sub-flow, the agent writes a state snapshot (to the contact
log header and the interrupt JSONL) capturing:

- `active_workflow_id`
- `active_step` (which phase/step of the workflow the customer was in)
- `gathered_data` (everything collected so far — name, package interest, dates,
  answers — so nothing is re-asked)
- `context` (a one-line summary of where the conversation was)

Persist this snapshot to the interrupt stack in the contact's conversation log
header AND emit it to the interrupt JSONL (below). The stack is per-contact and
ordered (LIFO).

### 2. EXECUTE the interrupt sub-flow

Run the triggering sub-flow (operator-urgent handler, compliance response,
aggression-handler, etc.) to completion or to a natural handoff point. The
sub-flow is itself a workflow and follows all normal rules (safeguards,
send-directive, conversation-log append).

### 3. RETURN to the saved state with a SOFT transition

Restore the saved workflow + step + gathered data, and re-enter with a soft,
human transition so the customer feels the agent never lost the thread:

- "Coming back to where we were…"
- "Okay — back to your booking. You'd told me [gathered_data], so the next thing
  is…"
- "Thanks for your patience on that — picking up the [topic] we were working on…"

Apply the tag matching the detour kind (see Tags) on return.

## Depth and multiple triggers

- **Max 2 levels deep.** A detour may itself be interrupted once (level 2). A
  THIRD nested interrupt is not allowed — at that point the agent **escalates to
  a human** (the conversation is too tangled to keep auto-detouring) and notifies
  the operator. This prevents infinite nesting / state-stack blowups.
- **Multiple triggers in one inbound → highest priority first, queue the rest.**
  Priority order (highest → lowest):
  1. Compliance redirect (hard-gate, always wins)
  2. F50 aggression (Tier 2)
  3. Operator urgent keyword
  4. F49 pixel-priority
  5. FAQ type (→ usually handed to F47 as a one-liner, not a full detour)

  The highest-priority trigger detours first; the others queue and fire in order
  after the current detour returns (subject to the 2-level cap — if firing a
  queued trigger would exceed depth 2, escalate instead).

## Tags

All applied programmatically → `ZHC-` prefix (zhc-tag-prefix-protocol.md):

- `ZHC-interrupt-handled` — a detour fired and returned cleanly.
- `ZHC-faq-detoured` — the detour was an FAQ-type interrupt.
- `ZHC-aggression-handled-and-resumed` — an F50 aggression detour ran and the
  conversation returned to its saved state.

## Relationship to F47 (smart FAQ tool)

F47 (`smart-faq-tool-protocol.md`) is the **lightweight sibling**: a SENTENCE,
not a sub-flow. When the interrupt is a simple factual question the FAQ knowledge
base can answer in one line, the always-listening layer hands it to F47, which
answers inline ("By the way, [answer]. Coming back to [topic]…") and the
conversation continues on the same step — no state save/restore needed. F44 owns
the heavier case where the interrupt needs an actual sub-flow (operator-urgent
handler, compliance response, aggression-handler). Use F47 for one-liners; use
F44 for sub-flows.

## Relationship to F33 (intelligent routing) — the disambiguation

| | F33 — Intelligent Routing (route-and-stay) | F44 — Smart Switching (detour-and-return) |
|---|---|---|
| Trigger | the conversation genuinely PIVOTED to a new topic | something urgent must be handled, but the original goal stands |
| Action | SWITCH the active workflow; stay there | SAVE state → run sub-flow → RETURN to the saved workflow |
| State | the old workflow is left behind | the old workflow's step + data are preserved and resumed |
| Soft transition | "Sounds like this is more about X now — switching gears" | "Coming back to where we were…" |
| Cap | max 3 switches / conversation | max 2 detour levels deep, then escalate |
| Step | 9.33 | 9.38 |

If a customer permanently moves on, that is F33. If they need a quick aside and
then want to finish what they started, that is F44.

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

## Logging (the data contract — F52)

Every interrupt is recorded as JSONL, one line appended to
`<MASTER_FILES_DIR>/interrupt-log.jsonl`:

```json
{"timestamp":"2026-05-30T15:01:12Z","event_type":"interrupt_detour","contact_id":"<CONTACT_ID>","channel":"sms","trigger_kind":"operator_urgent","priority":3,"depth":1,"saved_workflow_id":"appointment-booking","saved_step":"phase-2-gather-context","gathered_data_keys":["name","preferred_day"],"subflow":"urgent-cancellation-handler","queued_triggers":[],"tag_applied":"ZHC-interrupt-handled","returned":true,"escalated":false}
```

JSONL schema (one object per line):

| field | type | meaning |
|---|---|---|
| `timestamp` | string (ISO-8601 UTC) | when the interrupt fired |
| `event_type` | string | `interrupt_detour` (always, for F44 firings) |
| `contact_id` | string | GHL contact id |
| `channel` | string | inbound channel |
| `trigger_kind` | string | `operator_urgent` / `faq_type` / `compliance_redirect` / `aggression` / `pixel_priority` |
| `priority` | number | 1 (highest) … 5 (lowest), per the priority order above |
| `depth` | number | nesting depth at firing (1 or 2; 3 = escalate, not allowed) |
| `saved_workflow_id` | string | the workflow paused for the detour |
| `saved_step` | string | the step within that workflow |
| `gathered_data_keys` | array of string | the keys of the preserved gathered data (NOT the values — keeps PII out of the log) |
| `subflow` | string | the interrupt sub-flow that ran |
| `queued_triggers` | array of string | any other triggers queued behind this one |
| `tag_applied` | string | `ZHC-interrupt-handled` / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed` |
| `returned` | boolean | whether the conversation returned to the saved state |
| `escalated` | boolean | whether the 2-level cap was hit and the agent escalated to a human |

The JSONL schema is also documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## MEMORY.md (Rule 22)

The agent always listens for interrupts in parallel with the active workflow. On an
interrupt (operator-urgent keyword, FAQ type, compliance redirect, F50 aggression, F49
pixel-priority) it SAVES the workflow state, EXECUTES the sub-flow, then RETURNS to the
saved step with a soft "coming back to where we were" transition. This is
DETOUR-AND-RETURN, distinct from Step 9.33's route-and-stay. Max 2 levels deep, then
escalate. Multiple triggers: highest priority first, queue the rest. See MEMORY Rule 22,
appended by `scripts/06-append-memory-rules.sh`.

## Cross-references

- Distinct from: `protocols/intelligent-routing-protocol.md` (F33, Step 9.33).
- Lightweight sibling: `protocols/smart-faq-tool-protocol.md` (F47, Step 9.41).
- Feeds aggression detours: `protocols/aggression-detection-protocol.md` (F50, Step 9.37).
- Tag namespace: `protocols/zhc-tag-prefix-protocol.md`.
- AGENTS.md Step 1.42: `scripts/05-update-agents-md.sh` (marker `STEP_1_42_INTERRUPTS_AND_FAQ`).
- INSTRUCTIONS.md Step 9.38.
