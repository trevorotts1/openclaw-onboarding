# Rescue Rangers — Provider Capacity & Model Selection Contract (client-facing addendum, SANITIZED)

**RR-013 addendum to the Public Client Contract.** Audience: client-box and
client-facing documentation consumers. This file is safe for public
repositories. It carries **no credential values, no client identities, no
table IDs, no private workflow IDs, no deployment internals.** The
authoritative private contract is `blackceo-fleet-ops:rescue/provider-capacity.json`
(which itself extends `blackceo-fleet-ops:rescue/contract-manifest.json`);
this file is the sanitized projection.

**Contract version:** provider capacity schema `1` (2026-09-09).

---

## What changes for a client box (and what does not)

Nothing on the box changes. Provider capacity, model selection and fallback
policy are **operator-side concerns**: a client box never calls a model
provider, never holds a reservation, and never sees a capacity refusal shaped
as its own fault. What the box may notice is timing (a queued escalation waits
longer when the fleet's diagnosis capacity is saturated) — never a lost
incident.

## The operator's selection contract

The operator — not code, not a workflow default — decides:

- **which provider and exact model ID** serves rescue diagnosis,
- **which account** it runs against,
- **which fallbacks are permitted** (each one explicitly authorized — an
  unauthorized or paid tier is never silently selected),
- **the spend budget**, and
- **whether speed or cost wins** when both are possible.

This choice is **persisted, not hardcoded**. Changing the model is a recorded
operator action that takes effect at the next call — no code edit, no workflow
re-import. Where no preference is persisted, the system **asks the operator**;
nothing is silently chosen on the operator's behalf.

## Capacity honesty (no assumed limits)

- A concurrency/limit number is enforced **only when it is verified** for the
  actual provider account, with a recorded source. A plan description is a
  desired budget until verified against that account and its supported API.
- Nothing infers "unlimited" or any concurrency figure from a provider name.
- An account whose capacity is not yet verified **refuses admission** rather
  than guessing. Refusals are owned events, never silent.

## Reservations are real, atomic and leased

- Concurrent diagnosis requests **reserve seats atomically per provider
  account** — parallel reservations can never exceed the verified capacity
  (the historical read-then-insert overshoot is retired).
- Every seat is a **lease with a deadline**, renewable by the holder up to a
  hard cap, and **released when the call ends, fails or is cancelled**. A
  stale timer alone never counts a still-running call as finished, and a
  wedged seat is reclaimed only through a recorded reconciliation of the
  uncertain external call.
- **A failed reservation does not dispatch.** The request is requeued as an
  owned, durable deferral — the incident is never dropped, and it is retried
  when capacity returns.
- Capacity is kept in **reserve for live P1 incidents**; backlog work is
  admitted below the live-reserve line.

## Provider pressure (429 / outage)

- On a provider 429, **Retry-After is honored**: admission pauses for the
  window, new work is deferred (never dropped), and the in-flight seat is
  freed.
- During a provider outage, that account refuses admission until the window
  passes and recovers without any code change; other accounts keep moving.
- A **permitted** fallback tier is chosen only when it is authorized, its own
  capacity is verified, and it has room. If no eligible tier remains, the
  result is an **owned escalation** — never a silent unauthorized or paid
  choice.

## What this means for the escalation experience

1. Your escalation is admitted and ticketed exactly as before.
2. If diagnosis capacity is momentarily full, the ticket **waits visibly in
   the queue** (a deferral with a retry time) — it does not fail, and it does
   not silently switch to a more expensive provider.
3. If a fallback runs the diagnosis, the outcome is delivered with its
   degraded-provider attribution preserved — a fallback is never presented as
   the primary.

## Guarantees (unchanged from the base contract)

- Exactly one durable ticket per incident; nothing here deletes or mints
  tickets. This contract governs **model-call capacity only** — the ticket
  ledger, admission and board contracts are separate and unaffected.
- No credential values ever reach a client box or a public repository:
  provider credentials stay operator-side by name, never by value.
