# Rescue Rangers — Public Client Contract (SANITIZED)

**Audience:** client-box and client-facing documentation consumers. This file is
safe for public repositories. It carries **no credential values, no client
identities, no table IDs, no private workflow IDs, no deployment internals.**

**Canonical contract version:** `1.0.0` (2026-09-08). Authoritative private copy:
the private `blackceo-fleet-ops` repository, `rescue/contract-manifest.json`.
**Never copy private Fleet Ops content into a public repo — this file is the
sanitized projection, and the private file is the authority.**

---

## What a client box participates in

A client box **escalates** to Rescue Rangers when its agent hits a wall it cannot
fix. A client never summons Rescue Rangers directly. The box's only job is:
send a well-formed escalation, keep it outbound-only, and relay the outcome back
to its owner. Everything else (triage, ticketing, fixing, verification, board)
is operator-side.

## The escalation contract (nine fields)

An escalation POSTs to the fleet webhook URL (`RESCUE_RANGERS_WEBHOOK_URL`,
seeded at onboarding) with the `X-Rescue-Secret` header (`RESCUE_RANGERS_WEBHOOK_SECRET`,
same posture). The JSON body carries the **nine advertised fields**:

| Field | Meaning |
|---|---|
| `person` | who the box works for |
| `clientName` | the client account label |
| `agentName` | the requesting agent |
| `boxName` | the box slug (canonical identity key) |
| `boxType` | one of `VPS` / `Mac Mini` / `MacBook Pro` (closed vocabulary) |
| `openclawVersion` | runtime version |
| `problem` | what broke |
| `alreadyTried` | what was attempted (so nobody repeats it) |
| `returnTo` | where the answer goes |

Partial payloads are never dropped: they are accepted as degraded INCOMPLETE
tickets and worked with degraded context. A completely empty body is rejected.

## The lifecycle (what happens after you POST)

1. **Admission** — intake verifies your box identity and enrollment, applies
   rate/cap guards, and mints a durable ticket. A non-admitted call is answered
   with a structured refusal, never silence.
2. **Ownership** — the ticket gets exactly one owner; routing picks the coaching
   path (an answer is composed) or the direct-fix path (a mandate is queued).
3. **Queue + receiver** — the mandate waits in a durable outbox; the box's own
   receiver claims it (authenticated, leased, at most one claimer), runs one
   bounded turn, and ACKs the result with a verdict.
4. **Verification + sweeps** — SLA sweeps age unanswered tickets and escalate;
   heartbeat monitors watch receiver liveness; digests close the loop.
5. **Board** — an operator-side Kanban view mirrors ticket state. **Boarding is a
   view, never a gate:** a board outage never blocks a rescue.

## Status vocabulary (canonical, uppercase)

`OPEN` → `ACK` → `IN_PROGRESS` → `RESOLVED` | `ESCALATED` | `NEEDS_HUMAN` →
`CLOSED`, with `REOPENED` and `AWAITING_BOX` in the set. Legacy words
(`answered`, `fixed`, `awaiting_box`) are folded server-side; unknown statuses
are rejected, never written.

## What is RETIRED and must not be revived

- **The old "Rescue Rangers Relay" webhook path** (`/webhook/rescue-rangers`) is
  **retired**. It is inactive; any box env still carrying it is a false-pass trap
  (the canonical intake is `rr-v2-intake`). Do not point new wiring at it.
- **The Python SQLite ledger** (`rescue_ledger.py` / `rescue_cc_board.py`) is
  **compatibility-only**: offline drill/migration tooling. It is NOT the live
  system of record and must never run against production ticket state.
- **Do not restore any removed store blob from public git history.** The public
  Command Center tombstone throws on purpose; the real module lives only in the
  private Fleet Ops repo / operator machine.

## Guarantees

- Exactly one durable ticket per incident (dedup by identity; replays fold).
- No distress call is silently dropped: degraded tickets are flagged, refusals
  are structured, cap events notify once per day.
- One writer owns ticket state; no second ledger may be started by any path.
- Credential VALUES never appear in any escalation, ticket, log or repo — names
  only, values live in the operator secret env.