# Presentations Conversational Layer Protocol (FIX-PLAN Item 33b)

This protocol is Skill 38's doctrine for ONE bounded job: the human-facing
conversation around presentation runs. It covers exactly three seams, and
nothing else:

1. **park-notice**: park and resume client communication.
2. **delivery-followup**: the conversational follow-up after a deck is
   verifiably delivered.
3. **intake-frontdoor**: the greeting and qualification conversation that
   hands a client INTO Skill 51's gated intake.

The department side of this layer is
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/conversation_layer.py`,
and the department's message templates live beside it in
`conversation_templates.json`. This protocol is the conversational side:
the copy rules, the contracts, and the bounds. Where this protocol and the
adapter disagree, that is a defect to report, not a choice to improvise
(the department's Item 33b suite machine-checks the agreement).

## The scope bound (hard)

Skill 51's gated intake is OUT of scope for this layer, in both
directions:

- The layer never asks the intake questions. Not the Signature 8, not
  the standard turns, not a paraphrase of them, not "just one quick
  question about your deck" at the front door.
- The layer never writes intake answers. It writes no intake.json, no
  transcript, no ledger entries. Its only intake-adjacent artifact is
  the hand-off token, which carries no answers by construction (closed
  key set; answer-shaped keys are refused by the writer).
- The layer hands off at the gate. Once the hand-off token is issued,
  the gated intake owns the conversation until the run exists.
- Skill 38 is client-facing only. Operator and board communication stays
  on the existing board and gateway machinery; nothing in this protocol
  routes a staff notice through a client conversation.

## The contract (brief out, receipt back)

At a seam event, the department writes `conversation-brief.json` in the
run folder (immutable per-event copies under
`working/conversation/briefs/`): run id, GHL contact id, seam name
(`park-notice` / `delivery-followup` / `intake-frontdoor`), the approved
copy points for this run, the escalation target, and the consent posture
already captured for the client.

Skill 38 builds or reuses the playbook for the seam. Any workflow the
layer creates goes through Skill 44 and must pass the TRINITY gate
(Skill 44 structure + the Skill 38 playbook + the generated Workflow-AI
prompt, machine-enforced by `qc-trinity-registry.sh`). Booking uses the
smart-booking protocol with calendars resolved through Skill 44.

Skill 38 returns its record by appending to `conversation-receipt.json`
in the run folder, through the department adapter's one receipt writer
(`conversation_layer.py record-receipt`): playbook id, workflow id if
any, memory log pointer, messages sent count, and the client outcome
(booked, replied, opted out, escalated).

**Recording rule.** Every client-facing message the layer sends is
recorded in the run record. A message with no receipt record did not
happen, by definition of this layer. The conversation memory rules still
apply in full: read the per-contact conversation log before drafting,
append after sending (machine-enforced by `qc-conversation-memory.sh`),
and a drafted reply is never a sent one (the mandatory SEND directive,
`qc-send-directive.sh`).

**Fallback.** If Skill 38 is not available on a box, the department
falls back to today's one-way gateway notify, unchanged, and the run
record states the conversational layer was not available. The fallback
says the same words the layer would have said (the department's
templates are the single source of the copy); what is lost is the
conversation, never the notice.

## Seam 1: park-notice (park and resume communication)

The department supplies the park state; this layer owns the client's
experience of the wait. The input is Item 10's client-safe park record
(`park_status` in the run's state.json): park class, plain-words label,
what is needed in plain words, and who the run waits on. The raw blocked
reason is an engineering artifact: it never reaches client copy, in
whole, in part, or paraphrased with its internal codes intact.

The three park classes produce three different client surfaces:

- **client_action**: the client hears it, in plain words, once per
  park: what is needed, in the client's terms, and how to give it
  (reply here). The approved copy points in the brief carry the exact
  wording; the conversation that follows is a continuation, not a cold
  restart, and the client is never re-asked a settled question.
- **operator_action**: the client hears NOTHING. The wait belongs to
  the operating team. Messaging the client as if it were their move is
  a doctrine violation, not a courtesy.
- **transient_infra**: the client hears NOTHING. A temporary problem is
  retrying on its own under the bounded auto-resume cadence; there is
  nothing to ask the client for.

**The reply hand-off.** When the client replies to a client_action
park, the conversation side qualifies the reply (which outstanding need
it answers, and the client's own message id) and calls the department
adapter exactly once per reply:

```
conversation_layer.py reply --run-dir <dir> --message-id <id> \
    --kind style_pick --value B
conversation_layer.py reply --run-dir <dir> --message-id <id> \
    --kind resource_plan --value "$100/month"
```

The adapter verifies the kind against the run's artifacts and produces
at most one resume signal, through the engine's own machinery: a style
pick is recorded by the sanctioned driver writer (with the client's
message id, never an invented one) and followed by exactly one dispatch
of the existing launcher resume; a resource-plan answer is locked onto
the resource profile by the capacity writer, and that locked answer is
the signal the bounded auto-resume honors on its next tick. A reply
that satisfies nothing outstanding produces no signal; a reply kind
with no sanctioned writer is recorded and escalated, never improvised
into an artifact. Duplicate deliveries of the same message id are
deduplicated by the adapter and never signal twice.

After a qualified reply lands, the client hears the department's
resumed message (in `conversation_templates.json`) once the run is
moving again. If the reply cannot be used (a pick that matches nothing
offered, a plan tier the cap table does not know), the client is told
plainly what would work, in the same conversation, with the accepted
options named: a refusal is a conversational turn, not a silence.

## Seam 2: delivery-followup (post-delivery follow-up)

The trigger is a VERIFIED delivery: the run's delivery record shows
every destination verified (the Delivery Concierge's SOP 9.4 ground
truth), never an engine self-report. The bounded sequence, rendered
from the delivery record by the department adapter into the brief:

1. **Thank-you and receipt confirmation**: the deck is ready, the final
   quality score, and the verified locations, in the client's terms.
2. **Package questions**: one follow-up window later, an invitation to
   raise anything about the package that looks off.
3. **Review-call booking ask**: offer to book the review call. Booking
   runs through Skill 44 calendars under the smart-booking protocol
   (offer two or three real slots, confirm the picked one, record the
   booking in the receipt with outcome booked).

The sequence is bounded: three touches, then it ends. Quiet hours
(Step 9.8), the proactive-outreach frequency cap, and opt-out respect
govern every proactive touch; a client who opts out is out, globally,
and the receipt records it. Reactive replies to a client who writes
first are not capped by this sequence.

**Boundary with Item 33c.** The EMAIL half of post-delivery follow-up
(Skill 50's sequences) is an election under FIX-PLAN Item 33c, deployed
draft-only through Skill 44 after human approval. It is not part of
this seam, this layer never sends it, and a delivery-followup brief
says so in its copy points so the two are never conflated.

## Seam 3: intake-frontdoor (greeting and qualification)

The front door is the conversation BEFORE the gate: a greeting, a
short qualification, and the hand-off. The qualification confirms only
three things, in the department template's own words: the visitor wants
a presentation created, they are the person it is for (or arranging it
for them), and the consent posture for continuing the conversation.
Consent posture follows the standing rule for every form this system
ships: benefit-first copy, all required, captured once and never
re-asked.

On qualification, the department adapter issues the hand-off token
(`pres-intake-handoff`: token id, scope `skill51-gated-intake`, the
bridge-minted capability link carried verbatim, the qualification
summary, timestamps) and the conversation delivers the link with the
template's hand-off message. The layer's involvement ends there. It
holds no intake state of its own beyond the token: no answers, no
partial answers, no shadow copy of anything the intake collects.

If the visitor does not qualify, nothing is started and there is
nothing to cancel; the template's not-qualified close says exactly
that, and no hand-off token is issued.

Post-intake clarification follow-up (a client who finished the intake
and writes back about scheduling, reminders, or where things stand) is
this seam's conversation too, under the same bound: it never touches
the gated questions or their answers; anything that would change an
answer routes to the operator and the run's own amendment machinery,
never through this layer.

## Inherited gates (unchanged, and they bind this layer)

- The two-strike gate at the top of SKILL.md applies to every
  conversation this layer runs, exactly as to the rest of the skill.
- Quiet hours, compliance keywords, the honesty floor, and the
  mandatory SEND directive apply to every message.
- A customer can never drive the layer outward: no campaigns, no sends
  to third parties, no calendar changes outside the booking the
  playbook grants. Operator-only surfaces stay operator-only.
- Per-client isolation: every artifact of this layer is per-run and
  per-contact. A brief, a receipt, a hand-off, or a conversation log
  from one client's run is never read into another client's
  conversation (N0 no co-mingling).

## What this layer deliberately does not do

- It does not ask, hold, or write intake answers (the scope bound).
- It does not classify parks: the park class, label, and needed line
  are Item 10's one definition, consumed, never re-derived.
- It does not write run state: briefs and receipts are its only run
  artifacts, written through the department adapter; the engine's
  state.json is written by the engine's own sanctioned writers.
- It does not send email, and it does not build the Item 33c election.
- It does not replace the board or the gateway notify: the board
  surfaces the same state for staff, and the gateway notify remains
  the fallback when this layer is unavailable.
