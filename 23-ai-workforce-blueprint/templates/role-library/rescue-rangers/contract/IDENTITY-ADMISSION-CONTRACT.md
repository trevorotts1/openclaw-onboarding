# Rescue Rangers — Identity Admission Contract (client-facing addendum, SANITIZED)

**RR-003 addendum to the Public Client Contract.** Audience: client-box and
client-facing consumers. This file is safe for public repositories. It carries
**no credential values, no client identities, no table IDs, no private workflow
IDs, no deployment internals.** The authoritative private contract is
`blackceo-fleet-ops:rescue/identity-schema.json` (which itself extends
`blackceo-fleet-ops:rescue/contract-manifest.json`); this file is the sanitized
projection.

**Contract version:** identity admission schema `1` (2026-09-08).

---

## What changes for a client box (and what does not)

Nothing changes yet. The server now **supports both** admission schemas at the
same time:

| Schema | Credential | Header(s) | Status |
|---|---|---|---|
| `v1` | the existing shared fleet secret | `X-Rescue-Secret` (`RESCUE_RANGERS_WEBHOOK_SECRET`, unchanged) | active — continues to work exactly as before |
| `v2` | this box's OWN per-enrollment credential | `X-RR-Box-Cred` (secret value) + `X-RR-Box-Id` (public enrollment id) | rolling out — the box is enrolled by the operator; no self-service |

**No existing credential is rotated.** The shared fleet secret keeps working
until the operator explicitly retires it per box, after an auditable deadline
and a verified-uptake window.

## The three identity fields are not free text (unchanged, now enforced harder)

- `boxName` MUST be this box's canonical fleet slug (`FLEET_STANDING_BOX_SLUG`).
- The credential the box presents is **bound to exactly one canonical company
  box and a closed set of permitted actions** on the server. A request whose
  identity fields contradict that binding is refused **before anything is
  written** — no ticket, no dedup entry, no budget consumption.
- `returnTo` in the body is **never trusted** for delivery. The answer
  destination is derived from the operator's own enrollment records. Keep the
  field filled correctly; it is informational, not authoritative.

## Refusals you may see (all explicit, never silence)

| Response `status` | HTTP | Meaning |
|---|---|---|
| `identity_mismatch` | 403 | identity fields contradict the box this credential is enrolled to |
| `unknown_identity` | 403 | credential id is not enrolled |
| `credential_revoked` / `credential_disabled` | 403 | enrollment exists but is not usable; operator action required |
| `schema_version_unexpected` | 403 | credential version not accepted right now (transition window) |
| `forbidden_action` | 403 | the action is outside this enrollment's permitted actions |
| `return_to_unauthorized` | 403 | the requested target is outside this enrollment's scope |
| `shared_client_retired` | 403 | the shared fleet secret is retired for this box; switch to the per-enrollment credential |

A refused request is recorded operator-side in an isolated triage ledger for
review. It never shares context with any client ticket.

## Rollout timeline (server-driven; the box does nothing until told)

1. **Compatible support** (now): server accepts both schemas.
2. **Enroll + verify**: the operator seeds the box's per-enrollment credential
   and confirms uptake from server-side counters.
3. **Retire shared client**: after the published deadline, and only when the
   pending-client list is clear, `v1` is refused with `shared_client_retired`.
   Boxes keep using `X-Rescue-Secret` until their operator explicitly switches
   them to `X-RR-Box-Cred` / `X-RR-Box-Id`.

## What a client box must NEVER do

- Never send another box's enrollment id or slug as its own identity.
- Never treat a 403 refusal as "retry later" — it is terminal; the operator
  triages it.
- Never place credential values in any payload field (reference env var names
  instead, exactly as the base contract already requires).
