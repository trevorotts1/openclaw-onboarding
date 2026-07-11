# Relay Brain Patch — nine-field validation + `status` return leg (DEFERRED live step)

**Applies FIX 4-B (kills R2) + FIX 4-D (kills R4).** This is the operator runbook for
pasting `scripts/relay_brain_validation.js` into the live n8n "Rescue Rangers Relay"
workflow (id on `main.blackceoautomations.com`). **This is a DEFERRED live step — the
repo build does NOT redeploy n8n.** Execute it by hand, following the ritual below.

---

## Why

- **R2:** the client AGENTS.md template advertises "the payload MUST carry all nine
  fields — partial payloads are rejected," but the live Relay Brain's ONLY input
  check is `missing_message`. Thin tickets (e.g. the Command Center's 3-field
  `notifySystem` payload) sail through with degraded context. The repo CHANGELOG has
  noted for a while that the relay-side enforcement "should be updated" — it never
  was. This patch enforces the contract at the edge.
- **R4:** VPS clients have no inbound return path (`returnEnabled:false`), so a VPS
  agent that escalates may never receive its answer programmatically. The new
  `status` branch lets any box poll `{action:"status", ticketId}` outbound-only —
  identical on VPS and Mac.

## Design law (do NOT weaken it)

**Never drop a distress call on a technicality.** A payload with missing fields is
REJECTED-to-SENDER (an error response) AND still POSTED-to-operator as a degraded
ticket flagged `INCOMPLETE`. A missing field never silences a box in trouble; it only
tells the operator the context is thin. The two sanctioned short forms
(`RESOLVED:` resolution signal, and the CC `notifySystem` shape) are whitelisted and
mapped up to the nine-field form.

## The ritual (MANDATORY — the live workflow is production)

1. **Export first.** Download the current workflow JSON as a pre-change backup
   (the same practice already used in `~/clawd/fleet-heartbeat/scripts/`, where 15+
   dated backups exist). Name it with a UTC timestamp.
2. **Diff the live workflow against the newest local export** before editing (Open
   Question 4: confirm live parity with the last FINAL-ENFORCED backup).
3. **Stage it.** Test against a STAGING webhook / a disabled copy of the workflow
   first — never edit the production Code node blind.
4. **Paste the module body** into the "Relay Brain" Code node and wire it:
   - In the `escalate` branch, REPLACE the single `missing_message` guard with a call
     to `validateEscalation(payload)`. Use the returned `{ok, postTicket, incomplete,
     missingFields, normalized, error}` to decide the response + whether to post a
     ticket. When `postTicket` is true, ALWAYS post (flag `INCOMPLETE` when
     `incomplete`), even if `ok` is false. Build the group header with
     `buildTicketHeader(normalized, meta)`.
   - Add a `status` case that calls `handleStatusQuery(payload, lookup)`, where
     `lookup(ticketId)` reads the transport-buffer queue in
     `$getWorkflowStaticData('global')` (or the operator ledger export). Return its
     result to the polling client.
5. **Re-test** on staging: a full nine-field payload (clean ticket), a thin payload
   (INCOMPLETE but posted), a `RESOLVED:` signal (closes, no new ticket), the CC
   `notifySystem` shape (accepted, degraded, mapped up), and a `status` poll for an
   answered + an open + an unknown ticket. `node relay_brain_validation.js --self-test`
   asserts all of these offline — the staging run must match.
6. **Promote** to production only after staging passes. Keep the pre-change export.

## Companion change (ONE fleet-wide payload contract)

Update the Command Center `notify.ts notifySystem()` to send the full nine-field form
(`person:"operator"`, `clientName:"command-center"`, `boxName:<CC host>`,
`boxType:"VPS"|"Mac Mini"`, `openclawVersion:"n/a"`,
`alreadyTried:"n/a (automated sweep alert)"`, `returnTo:""`). Until then, the
`system-sweep` whitelist in `validateEscalation` accepts the legacy short form and
flags it for upgrade — so the relay patch is safe to ship before the notify.ts change.
