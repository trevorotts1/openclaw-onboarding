# Client Test Mode Protocol (U-6) - the testing-portal equivalent

Mirrors CloseBot CB-8 (client testing portal). Instead of a hosted web portal,
Skill 38 gives the client a safe rehearsal LANE inside the channel they already
use: Telegram. The client role-plays a customer conversation against the REAL
playbook, with REAL tool-gating and REAL knowledge, but with ALL external side
effects suppressed. Nothing reaches a real contact, no booking is made, no tag is
applied, no CRM field is written, no webhook fires.

This is an OPERATOR / CLIENT-ONLY surface. A real customer inbound can NEVER enter
test mode (see the invariant at the end).

## Invocation grammar

The client sends the agent a Telegram message with their personal trigger word,
the word `test`, and a playbook id:

```
<trigger word> test <playbook-id>
```

Example: `Playbook time! test appointment-booking`

- `<trigger word>` is the client's personal trigger word set on their first
  playbook build (see references/communications-playbook-standard.md Section 6).
- `test` is the literal keyword that opens the lane.
- `<playbook-id>` is a registered workflow id from registry.md.

Only a message from the CLIENT on the operator Telegram channel opens test mode.

## Enforcement mechanism (three layers)

Test mode is not a soft prompt instruction. It is enforced by three concrete
layers, so a single-turn hook session can never drift out of it.

### Layer 1 - state flag (read-before-anything)

On invocation the agent writes a state file:

```
<MASTER_FILES_DIR>/test-sessions/active-test.md
```

with at least:

```markdown
test_mode: true
session_id: <opaque session id>
playbook_id: <playbook-id>
started_at: <ISO-8601 UTC>
```

Every subsequent turn RE-READS this file FIRST, at AGENTS.md Step 0.4 (earlier
than Step 0.5 quiet hours), the same read-before pattern the per-contact
conversation log already uses. Because the flag is recovered from disk on every
turn, a stateless hook session cannot forget it is in test mode.

### Layer 2 - gate composition (reuse the hardest gate)

While `test_mode` is true, the U-1 tool gate (protocols/tool-gating-protocol.md)
forces the resolved `enabled_tools` for EVERY phase to the EMPTY set plus
`reference_documents`. No external call can pass the gate regardless of prompt
drift, because the actual block is performed by the hardest capability gate in the
system, not by a new rule that could be talked around.

### Layer 3 - narration contract (auditable dry run)

Each would-be side effect is emitted as a `WOULD HAVE` line naming the EXACT
`caf` command that would have run, so the client and the operator get an auditable
dry run:

```
WOULD HAVE booked Tuesday 2pm on calendar CAL_A via: caf calendars book ...
WOULD HAVE applied tag ZHC-discovery-scheduled via: caf contacts tag add ...
```

Escalation is NARRATED, never fired ("WOULD HAVE escalated to the operator").

## Side-effect suppression list (every allow-list action category)

In test mode, EVERY allow-list action category is SIMULATED, never executed:

- **Bookings** - book_appointment, check_availability, cancel_reschedule: simulated
  (no calendar write).
- **Tags** - update_tags: simulated (no tag applied to any contact).
- **Contact / CRM writes** - update_contact, crm_field_write: simulated (no CRM
  field written).
- **Webhook chains** - webhook_chain: simulated (no webhook fired).
- **Invoices** - send_invoice: simulated (no invoice sent).
- **Discount codes** - create_discount_code: simulated (no code created).
- **Escalation** - escalate_to_human: NARRATED, not fired (no operator alert, no
  human task created).

If a future allow-list action is added, it defaults to SIMULATED in test mode.

## TEST MODE banner

EVERY message the agent sends while in test mode is clearly labeled with a
`TEST MODE` banner at the top, so the client always knows this is a rehearsal and
never mistakes it for a live conversation.

## Transcript offer

On completion (client types `end test`, or the session expires) the agent offers
the client the transcript of the rehearsal plus a short one-tap list of tweaks
they might want (tone, pacing, a phase that felt off), routing any accepted change
into the normal brainstorm / edit flow.

## Isolation - test transcripts NEVER touch the real logs

Test-mode transcripts NEVER enter the per-contact conversation logs
(`conversational-logs/`). They log ONLY to:

```
<MASTER_FILES_DIR>/test-sessions/
```

This keeps rehearsal chatter out of real contact history and out of analytics.

## Expiry

Test mode auto-expires after 60 minutes OR when the client types `end test`,
whichever comes first. Expiry DELETES `active-test.md`, so the next turn resolves
to normal (live) mode. An expired-but-undeleted file (found by the Step 0.4
re-read) is treated as expired and deleted on read.

## openclaw.json toggle

```json
{
  "skill38": {
    "client_test_mode": {
      "enabled": true
    }
  }
}
```

- `client_test_mode.enabled` - default **true**.

## Operator-only / never customer-invoked invariant

Test mode is reachable ONLY from the operator Telegram channel, by the client.
A real customer typing the word "test" (or a customer naming a playbook id) does
NOTHING: customer inbound is classified and answered normally, and can never open
the test lane (see prompt-injection-protection-protocol.md). The lane is an
operator-only surface, exactly like every other v1.8.0 update.

## Cross-references

- AGENTS.md Step 0.4 re-read + the Client Test Mode handler: inserted by
  `scripts/05-update-agents-md.sh` (markers `STEP_0_4_TEST_MODE_REREAD` and
  `CLIENT_TEST_MODE`).
- The gate that forces the empty tool set: `protocols/tool-gating-protocol.md` (U-1).
- MEMORY.md Rule 37 (Client Test Mode): appended by
  `scripts/06-append-memory-rules.sh`.
- Machine-enforced by `scripts/qc-client-test-mode.sh` (+ its negative test),
  wired into `scripts/11-run-qc-checklist.sh` + CI `.github/workflows/qc-static.yml`.
