# shared-utils/reminders

Version: v1.0.0 (see `skill-version.txt`)

## v1.0.0 — 2026-10-24

PBB-114 / ledger task T-17: shared reminder slots and the reserved
final-action window.

- `reminder_state_machine.py` — initial invitation kept separate from at most
  three shared reminder slots (one budget for FB/IG/SMS), proposed 2h/8h/20h
  offsets and a 30-minute quiet interval adopted as an explicit policy before
  activation; no catch-up burst (later overdue slots are recorded skipped and
  never replaced); t0, the used count and recorded refusals never reset on a
  returning or overlapping request, a reply, or a restart.
- Reserved final action under the contact lock: one reservation per contact
  sequence (primary key + deterministic action id), `closing_final` entered at
  one state version, sibling reminders canceled, only the exact reserved
  action able to pass the ordinary gate. There is no bypass-stop exception:
  STOP/refusal/human fence refuses the reservation itself or cancels the
  reserved action before dispatch.
- Terminal outcomes: provider acceptance → `stopped_final`; STOP →
  `stopped_complete`; permanent nonexecution or an expired final slot →
  `stopped_ineligible` without ever recording a dispatch receipt. Unknown
  stays reserved/reconciling and can never mint a second final.
- Reuses the accepted upstream modules — `tenant_identity`,
  `collection_lock` (T-11), `durable_store`, `outbound_gate` (T-12) and
  `consent_gate` (T-18). No second consent, gate or lock implementation.
- `tests/test_reminder_state_machine.py` — 30 tests, including the refusal
  cases, the pause/window/STOP races, and a real child-process crash trace.
