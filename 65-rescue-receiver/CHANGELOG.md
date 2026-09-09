# Changelog - 65 Rescue Receiver (65-rescue-receiver)

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
