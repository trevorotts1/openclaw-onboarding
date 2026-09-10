# Changelog - 65 Rescue Receiver (65-rescue-receiver)

## [23.3.0] - 2026-09-10 - RR-008 durable delivery journal + structured receipts (RECEIVER_VERSION 1.6.0)

RR-W3-PROTOCOL RR-008, receiver side. Delivery is no longer "a 2xx went out"
-- it is a named state transition with durable evidence on both ends.

TRANSPORT CLASSIFICATION. `_post` accepted `2*|3*)` as success, so a redirect
(a CF Access login wall, a moved webhook, an http->https bounce) recorded an
ACK the box never landed and the incident stayed open with no visible error.
`_post` now succeeds ONLY on 2xx; new `_post_class` names the failure as
`redirect` / `unauthorized` (401,403) / `throttled` (429) / `server` (5xx) /
`transport` (dropped) / `ok_nonjson` (a 2xx whose body is HTML or empty).

SUBSHELL DEFECT FIXED. `_ack_send` called `_post` inside a command
substitution, so the `_POST_CODE` / `_POST_BODY` globals died with the subshell
and EVERY ack classified as `transport` -- a matching receipt could never be
recognised. `_post` is now called directly, with stdout discarded (its body
echo would otherwise leak into `_ack_send`'s own stdout verdict token).

DURABLE ATTEMPT JOURNAL. `_journal_put` writes the operation state before any
effect; `_journal_phase` reads it back. The journal row is written BEFORE the
agent turn (`effect_started`), after it (`effect_executed`), before the send
(`ack_attempt`) and on settle (`ack_confirmed` / `ack_pending`). If the journal
write fails the ack is HELD and nothing is sent -- journal failure stops new
effects.

ACK_PENDING. The COMPLETE outcome and proof are stored byte-for-byte before the
send, so a crash at any point leaves an identical body to resend, never a
reconstructed one that could drift. `_resend_pending` retries the retained
bytes (bounded by RR_MAX_RESENDS, default 5) until a matching receipt arrives.

STRUCTURED RECEIPT REQUIRED. A bare 2xx is NEVER a confirmation. The response
must carry `receipt.operation_id` + `receipt.attempt_id` + `receipt.state_revision`
matching this box's operation; a distinct refusal is logged otherwise
(`no_receipt_operation_id`, `receipt_operation_mismatch`,
`receipt_attempt_mismatch`, `no_receipt_state_revision`). Only then is the
pending row removed and `ack_confirmed` written.

UNIQUE OPERATION IDs. `op_<sha256("rr-delivery|<idempotency_key>|<attempt_id>|<generation>")>`
-- deterministic, so a re-delivery of the SAME attempt yields the SAME id and
the server records an idempotent receipt instead of a second effect; a new
attempt yields a new id.

CACHED RE-ACKS NO LONGER DROP PROOF. `_write_done` persists `reply_excerpt`,
`operation_id`, `attempt_id` and `attempt_generation`; `_reack_cached` reads
them back and re-establishes the ORIGINAL attempt identity, so a replayed
delivery carries the same evidence and the same operation id as the live one.

PRIVACY + RETENTION. Journal / ack-pending / reconcile live under the 0700
state root, records are 0600, and the box token reaches no persisted artifact.
`_gc_journal` removes `ack_confirmed` rows past 14 days; an UNCONFIRMED row
past 30 days is MOVED to `reconcile/` with an owned-obligation log line -- it
is never silently deleted. Skill package version 23.2.0 -> 23.3.0.

## [23.2.0] - 2026-09-09 - RR-027 keep rescue credentials out of worker environments (RECEIVER_VERSION 1.5.0)

RR-W3-INSTALL RR-027. The secret store is PARSED, not executed: the shared
dotenv parser (`shared-utils/rescue-env.sh`) reads ONLY the three required
rescue values — no `.` sourcing of the store (arbitrary shell semantics gone),
no expansion of `$` inside values, quoting/space behavior preserved, malformed
lines FAIL VISIBLY (file + line + shape on stderr; values never printed).
Child-env scrub: every child (agent turn, default-agent probe) runs with the
rescue credential aliases REMOVED from its environment, so a synthetic
`export RR_BOX_TOKEN` from any upstream env file can no longer reach the child
agent (the CONFIRMED RCV05 leak); necessary authorized model/tool credentials
pass through untouched. Agent stderr is reduced to a failure CLASS (never
logged verbatim) so a stack-trace env echo cannot leak a credential into the
poll log. wire.sh no longer exports the store (`set -a; . file` removed) —
enrollment values are existence-checked then dropped, and the cron command
carries no credential. Skill package version 23.1.0 -> 23.2.0.

## [23.1.0] - 2026-09-09 - RR-004 additive lease/attempt fields (RECEIVER_VERSION 1.4.0)

RR-W2-CORE RR-004 pairing. ADDITIVE ONLY, no behavior change: the claim
response's new `attempt_id` / `attempt_generation` / `lease_expires_at` fields
are parsed and echoed verbatim on every ack, so the server can fence
acknowledgments against the current lease owner (rejecting stale generations,
expired leases and replaced owners). Fields are omitted when the server does
not send them (pre-RR-004 servers unaffected). Strict enforcement arrives
later, only after the additive server contract is confirmed fleet-wide
(SPEC shared rollout contract). Skill package version 23.0.0 -> 23.1.0.

## [23.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
