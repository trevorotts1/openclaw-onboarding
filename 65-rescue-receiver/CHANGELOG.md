# Changelog - 65 Rescue Receiver (65-rescue-receiver)

## [23.4.0] - 2026-09-13 - RR-028 enrollment + cron reconciliation report REAL readiness

RR-W4-INSTALL. Enrollment and cron status were PROSE. `UNENROLLED` existed only
as a comment inside `wire.sh`; the four-state vocabulary did not exist anywhere
in this repo. A job registered with a stale poll path, the wrong cadence, or
client-facing delivery left ON was indistinguishable from a correct one,
because presence was decided by `cron list --json | grep '"name": ..."'` — a
text match that proves nothing about the job. And nothing separated "files were
installed" (the installer's claim) from "the receiver is READY" (a claim about
the intended runtime).

New engine `shared-utils/rr-readiness.sh` + operator surface
`65-rescue-receiver/rr-readiness.sh`:

- **Four explicit states with explicit reasons** — `UNENROLLED`,
  `ENROLLED_PENDING`, `SCHEDULED`, `VERIFIED`; every outcome carries a
  machine-readable reason code and a detail that names NAMES, never values.
  Anything unproven is `ENROLLED_PENDING` naming exactly what is missing.
- **Version-independent** — no input to reconciliation is a software version.
  A `.wired-<version>` sentinel says "files were copied"; it is never evidence
  that a cron exists. `update-skills.sh` now runs this skill's reconciler on
  every pass, BEFORE the sentinel gate, so a cron an operator removed is
  repaired on the next roll instead of waiting for a version bump.
- **Keyed by a desired-config digest** — name, schedule, command, enabled bit,
  delivery mode, slug, URL and a SALTED token commitment (the token itself is
  never printed, logged or exported). A verified receipt is keyed by that
  digest AND by the runtime, so a changed desired config or a probe taken in a
  different runtime can never inherit an old verdict.
- **All required resolutions** — slug, token and URL from the store, plus the
  parser, curl, base64, the OpenClaw CLI and node. Anything unresolved is
  reported by name.
- **Readback, never assume** — two views (`cron list --json` and the gateway's
  stored `cron_jobs.job_json`, the only one that shows a DISABLED job);
  duplicates collapsed, command / schedule / enabled / delivery compared and
  repaired (`cron edit` in place, else replace), with a FRESH readback after
  every write. An operator-disabled cron or a tombstone is never resurrected.
- **argv-safe** — every external command runs as an argv vector; no eval, no
  `sh -c`, no string re-splitting. The host/container identity comes from
  `shared-utils/oc-env-descriptor.sh`.
- **Installer success != ready** — `wire.sh` exit 0 means files installed and
  now prints `files-installed=1` plus the readiness line. `VERIFIED` requires a
  receipt from a capacity-0 `dry_run` probe that starts no agent turn, acks
  nothing, and is refused outright if the receiver hands it an instruction.

Skill package version 23.3.0 -> 23.4.0. Gates: `tests/rescue/RR-028`
(readiness states 43 assertions, safe probe 35, wire reconciliation 42), plus
RR-027 credential gates, RR-004, RR-015, RR-025 and RR-026 re-run green.

## [23.3.0] - 2026-09-10 - RR-025 claim envelope identity + RR-026 process/lock supervision (RECEIVER_VERSION 1.6.0)

RR-W3-RECEIVER. Two defect classes, both of which let the poller be *wrong* on a
live box rather than merely unavailable.

**RR-025 — the claim envelope had no identity, so a claim could not be tied to
the work it authorized.** A claim is now validated as a TYPED envelope against
the SPEC's canonical tuple (company, runtime, incident, attempt) plus the
instruction, session, capability, lease and schema members. Every member is
presence-checked and (when a JSON type reader is available) type-checked, so a
mistyped `lease_seconds` or a stringified `attempt_generation` is refused
instead of silently coerced. Identity is hashed over a LENGTH-PREFIXED encoding,
so `company="a/b"` and `company="a_b"` — or a shift at a member boundary — can no
longer collide into the same identity. An unknown `agent_id` is a ROUTING
decision: the local roster is read and the capability must actually exist, with
a recorded substitution when a declared fallback is used and an explicit refusal
when none is. A refused claim sends NO verdict ack (a verdict about a turn that
never ran would be a lie); it is recorded structurally with the member, reason
and taxonomy, the ticket stays non-terminal, and the next owner is named.

**Compatible by design**: the deployed RR-07 does not send `attempt_id`,
`attempt_generation` or `lease_expires_at`, so the attempt member is DERIVED
(server value when present, else the session-key retry suffix, else `a0` for a
first handout) rather than hard-required — a hard requirement would have
rejected every claim on every live box.

**RR-026 — the poller's only bound was a stale constant, and its lock was
age-based.** v1.5.0 delegated its entire deadline to the CLI's own
`--timeout 600`; a CLI that ignores or mis-parses the flag hangs forever, and a
child that forks a grandchild leaves the grandchild running after the direct
child is signalled. And the lock was an age-only `mkdir` ("older than 20 minutes
is stale") — age is not ownership, so a still-running previous poll could have
its lock removed underneath it and a recycled PID looked like the original
owner. Neither was provable from the shell: `exit 0` after a kill is not proof
that anything exited.

Now a shared runtime adapter (`shared-utils/rescue-supervise.py`, stdlib,
Python 3.6+, Mac and Linux) supervises the turn in its own process group under
ONE monotonic budget measured from the claim and covering discovery, the model
turn, the unknown-agent fallback and the ACK margin. It TERMs the group, waits a
grace window, KILLs the group, reaps, and VERIFIES the group is gone — a killed
child is never read as a delivery. The lease the SERVER granted (900s live) is
the deadline; the 600 is only a per-turn cap. If discovery has already eaten the
window the poll STOPS without starting a turn, so RR-07 cannot re-hand a ticket
to a second poller while the first is still delivering.

The lock is now a RECORD, not a directory marker: owner token, the owning
process's START identity (so a recycled PID is reconciled as reused, never
mistaken for a live owner), the shared target/resource fence fields
(`target_key`, `generation`, `attempt_id`, `operation_id`) and the lease
deadline. A genuinely RUNNING incumbent is refused outright however old its
record is — age is deliberately never consulted. A lapsed record is not free
either: takeover requires `allowTakeover` + the observed generation + a note,
per the shared fence contract, and a stale owner can never release a newer
holder's lock.

Fail-closed must not be fail-SILENT: a missing supervisor or an unusable lock
subsystem is RECORDED (`state/rr-receiver/rejected/degraded-*.json`), logged
with `next_owner=operator`, and returned as rc=2 — distinct from contention,
which stays quiet because it is normal. Folding the two together was how a box
went silently dark: every fire exited 0 having done nothing, forever, with no
trace. Timeout and cancellation outcomes are persisted with the next owner.

Skill package version 23.2.0 -> 23.3.0. Gates: `tests/rescue/RR-025` (claim
envelope, 39 assertions), `tests/rescue/RR-026` (process-group supervision,
lock fencing, lease budget, 47 assertions), plus RR-004 and the RR-027
credential gate re-run green.

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
