# Fleet Standing Gate

Refuses Rescue Rangers service and repo updates to clients who are not current on payments.

## Where the leverage actually is

Rank any gate by **"does this consume operator compute or tokens?"**

- **Rescue Rangers — server-side, unbypassable, high value.** The client POSTs to the
  operator's n8n; the operator's Mac runs an agent turn; the operator's tokens burn. The
  gate sits in the `Rescue Rangers Relay` workflow between `Authorized?` and `Relay Brain`,
  i.e. before any side effect. Gating later would still burn a slot off the client's 25/day
  cap, because `Relay Brain` mutates workflow static data on entry.
- **Repo updates — client-side, low value.** `update-skills.sh` is fetched from *public*
  GitHub and executes on the *client's* hardware. It costs the operator nothing. This gate
  withholds a benefit; it is not cost control. Do not over-invest in it.

## The one rule

**Only an explicit `blocked` verdict ever refuses service.** Unreachable gate, HTTP error,
malformed body, missing config, unknown box — all PROCEED.

This is deliberate, not an oversight:
- Blast radius is asymmetric. Fail-closed freezes updates fleet-wide the instant n8n hiccups.
- The operator console forwards escalations without `boxName`; fail-closed would gate the
  operator out of his own rescue path during an outage.
- Refusing a paying client mid-emergency over a name mismatch is worse than one wasted call.

**Never "harden" this into fail-closed.** `tests/unit/fleet-standing-gate.test.sh` pins it.

That test earned its keep: it caught a fail-closed bug during development. Under
`set -euo pipefail` a non-matching `grep -o` exits 1, which killed the command substitution
parsing the verdict — so any malformed gate reply would have aborted `update-skills.sh`
outright, silently, on every box.

## Match on aliases, never an exact slug

The `boxName` field in a rescue escalation payload is free text an LLM fills in from a
hint ("Hostname or compose-project label"), and **three** slug conventions exist across
the fleet for the same box — a short hash-style id (e.g. `openclaw-0ht9`), a VPS
container name derived from the client's business, and a rescue SSH alias derived from
the client's own name. An exact `box_slug` match returns `unmatched`, and `unmatched`
**PROCEEDS**, so the gate silently blocks nobody while appearing to work.

Fix: load all rows and match `box_slug` + `client_label` + every pipe-delimited
`aliases` token, case-insensitive and trimmed. Also: if a caller matches multiple rows
and **any** is not in good standing, that wins — nobody slips through on a duplicate
good record.

Never fall back to name matching — there are ten same-first-name customers in one
Stripe account.

## n8n fires a node on the FIRST predecessor, not when all of them do

Seven parallel branches fed one input port of a Code node; the node ran the instant the
first branch completed and threw on branches that had not started yet. It would have
failed **silently every night** and no offline logic test would have caught it — only a
real execution did.

Fix: a `Merge` node (`n8n-nodes-base.merge`, typeVersion 3.2, `mode: append`,
`numberInputs: N`) as an explicit barrier, with all branches wired into it and its
single output feeding the consumer.

## Pieces

| Piece | Where |
|---|---|
| Update chokepoint | `update-skills.sh`, block `FLEET-STANDING-GATE-V1` |
| Tests (14 cases) | `tests/unit/fleet-standing-gate.test.sh` |
| Fleet seeding | `scripts/fleet-standing/propagate-fleet-standing-gate.sh` |
| n8n workflow backups | `scripts/fleet-standing/n8n-backups/` |

All three update paths — the Sunday `openclaw cron`, the legacy silent shell cron, and the
operator's fleet-roll SSH push — execute `update-skills.sh`, so one early exit gates all of
them. That includes the Sunday flow's 2-hour no-reply auto-apply.

## Env vars (per box)

`FLEET_STANDING_GATE_URL`, `FLEET_STANDING_GATE_HEADER`, `FLEET_STANDING_GATE_SECRET`,
`FLEET_STANDING_BOX_SLUG` (per box — the join key).

Escape hatches: `FLEET_STANDING_GATE_BYPASS=1` (skip), `FLEET_STANDING_GATE_SHADOW=1`
(report only, never block).

## Security rules

- **Client boxes NEVER receive an n8n API key.** Scoped keys are Enterprise-only; on this
  tier a key grants full access to every workflow and credential on the instance. Boxes get
  only the narrow header secret — one capability: ask about their own standing.
- **The gate response carries only** `{ok, good_standing, verdict, reason, client_message}`.
  It must never echo roster data; callers are client-side.
- **The `Rescue Rangers Relay` workflow export is NOT kept here.** Its `Relay Brain` node
  embeds a hardcoded roster of client names, boxes and personas, and this repo ships to
  every client box. Back it up locally only.
- **Never let an AI builder edit `Relay Brain`** (34,835-char Code node holding the whole
  routing engine). Assert its sha256 before and after any change to that workflow.

## Standing is set manually — Stripe is advisory only

`good_standing` is set by hand and manual wins. Stripe `past_due` alone caught **zero** of
four known delinquents: two had no Stripe subscription at all, one appeared only as failed
*charges* in a *second* Stripe account under business names.

Check **charges AND invoices AND subscriptions**, across **both** Stripe accounts, matching
on email or `stripe_customer_id` — never on name. `fleet-standing-stripe-sync` is
REPORT-ONLY and must never auto-write standing; its most valuable output is the list of
delinquent customers it could *not* attribute to any fleet box.

`stripe_customer_id` is pipe-delimited: one person can hold **seven** Stripe customer
records under different business names. Split on `|` and compare per-token — comparing
the whole joined string against a single id matches nothing.
