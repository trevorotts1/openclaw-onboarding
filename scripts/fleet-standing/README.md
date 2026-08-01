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

## The Relay payload trap

An n8n `httpRequest` node **replaces** the current item's JSON with the response body — it
does not merge or append. The standing-check call sits ahead of `Relay Brain` in the
`Rescue Rangers Relay` workflow, and `Relay Brain` reads `$json.body` and contains **zero**
`$('…')` node references back to the original trigger. So once the gate's `httpRequest` ran,
`Relay Brain`'s only view of the item was the gate's own verdict object — `message` resolved
to empty, and `Relay Brain` silently posted nothing. No error, no stored execution, nothing
to alert on. **Every escalation, for all 38 boxes, paying clients included, went into the
void** until this was caught.

The fix is the `Restore Rescue Payload` Code node immediately after the gate call:
`return [$('Auth Check (soft)').first()];`. It discards the gate's response body and re-hands
`Relay Brain` the original trigger payload it actually expects. **Removing this node
re-breaks Rescue Rangers fleet-wide, silently, with no error and no execution log to catch
it** — before touching this workflow again, confirm `Restore Rescue Payload` (or an
equivalent full-payload restore) still sits between the gate call and `Relay Brain`.

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

The same class of bug applies to `set -u`: any *new* variable referenced inside the gate
block must be read as `${VAR:-}`, never bare `$VAR`. A bare reference to a variable that is
unset on some code path is not a warning under `set -euo pipefail` — it aborts the whole
update, on all 38 boxes, the instant that path is hit.

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

`norm()` — the normalizer used for every comparison above — denylists a fixed set of
placeholder tokens: `tbd, n/a, na, none, unknown, null, -, ?, tba, ''` (empty string). The
literal string `TBD` had been checked into the `aliases` column of 13 rows, one of them
delinquent. Because a match is exact-per-token (never substring) and "any matched row not
in good standing wins" is deliberate, a caller supplying that same literal — exactly the
kind of fill-in an LLM reaches for — would have matched all 13 rows at once and been
refused: **12 paying clients denied service over a shared placeholder value.** The denylist
is applied to *both* sides of the comparison — the caller's supplied identifiers and every
row-derived key — so a placeholder can never register as a match regardless of which side
it appears on. This must stay: rows will keep getting seeded with a placeholder before the
real alias is known, and that is normal, not a bug to "fix" by removing the denylist.

## n8n fires a node on the FIRST predecessor, not when all of them do

Seven parallel branches fed one input port of a Code node; the node ran the instant the
first branch completed and threw on branches that had not started yet. It would have
failed **silently every night** and no offline logic test would have caught it — only a
real execution did.

Fix: a `Merge` node (`n8n-nodes-base.merge`, typeVersion 3.2, `mode: append`,
`numberInputs: N`) as an explicit barrier, with all branches wired into it and its
single output feeding the consumer.

## The prune's date semantics

The weekly prune (`fleet-standing-prune.json`) deletes old `rescue_request_ledger` rows so
the table doesn't grow forever. `requested_at` is a `date` column, and n8n's data-table `lt`
filter compares only the calendar DAY — inclusively. A naive `now − 30d` cutoff therefore
also deletes rows dated exactly 29 days ago, one day earlier than anyone computing "30 days"
by hand would expect. The cutoff is deliberately `now − 31d`, truncated to midnight UTC —
erring toward retaining a row too long, never toward deleting one too early.

This node also has history worth remembering before touching it again: it was once named
`Dry Run Prune Rescue Request Ledger` while its `dryRun` parameter was `false` — so it was
never a dry run at all. It deleted rows for real, every week, unattended, under a name that
told anyone glancing at the workflow canvas the opposite. Read the actual `dryRun` value;
don't trust the label.

## Pieces

| Piece | Where |
|---|---|
| Update chokepoint | `update-skills.sh`, block `FLEET-STANDING-GATE-V1` |
| Tests (14 cases) | `tests/unit/fleet-standing-gate.test.sh` |
| Fleet seeding | `scripts/fleet-standing/propagate-fleet-standing-gate.sh` |
| n8n workflow backups | `scripts/fleet-standing/n8n-backups/` |
| Weekly cron message refresh | `update-skills.sh`, block `WEEKLY-CRON-MESSAGE-REFRESH-V1`; `tests/unit/weekly-cron-message-refresh.test.sh` (31 cases) |
| Operator control (flip / list / check standing) | `~/clawd/fleet-standing/standing.sh` — operator-local, not tracked in this repo |

All three update paths — the Sunday `openclaw cron`, the legacy silent shell cron, and the
operator's fleet-roll SSH push — execute `update-skills.sh`, so one early exit gates all of
them. That includes the Sunday flow's 2-hour no-reply auto-apply.

## Operator control: `standing.sh`

`~/clawd/fleet-standing/standing.sh` (operator-local, not tracked in this repo) flips,
lists, and checks rows in the `fleet_standing` data table directly, without opening the n8n
UI:

```
standing.sh off  <name-or-slug> [reason...]        # good_standing = false, fuzzy match
standing.sh on   <name-or-slug> [reason...]        # good_standing = true,  fuzzy match
standing.sh off  --slug <exact-slug> [reason...]   # exact box_slug match, unambiguous
standing.sh on   --slug <exact-slug> [reason...]
standing.sh off  --all  <name-or-slug> [reason...] # apply to EVERY row the needle matches
standing.sh on   --all  <name-or-slug> [reason...]
standing.sh list                                    # everyone NOT in good standing
standing.sh check <name-or-slug>                    # one client's current standing
standing.sh check --slug <exact-slug>
```

Default matching is fuzzy (case-insensitive substring), and an ambiguous needle **refuses**
— exit 1, printing every matched slug — rather than guessing. `--slug` forces an exact
`box_slug` match, the only way to target one row deterministically when a client holds two
boxes (a base box plus a `-macbookpro`/`-2026`-style variant): a plain fuzzy `off` on their
name would try to match — and with `--all`, flip — both rows, half-blocking someone who
should end up fully blocked or fully clear. `--all` exists for the opposite, equally real
case: intentionally applying one change to every row an ambiguous needle matches. Any other
misuse (bad mode, missing name) also exits 1 with usage; `-h`/`--help` exits 0.

Rows page through the n8n data-table API by an opaque `nextCursor`, not `offset`/`skip` —
`offset`/`skip` return HTTP 400 outright. `limit` is server-capped at 250 per page; loop on
`nextCursor` until it comes back null/absent. `fleet_standing` is 38 rows today (one page),
but the table is loaded through this pagination loop regardless, so growth past 250 rows
doesn't silently truncate results.

## The Sunday cron refresh

`update-skills.sh` used to register the `weekly-onboarding-update` cron only when it was
absent. Once a box had it, that box's stored cron message was frozen at whatever
`cron-prompt.txt` said the day it was provisioned — a later repo edit to `cron-prompt.txt`
(new rules, a fixed leak, anything) never reached a box that already had the cron. Only a
box whose cron was missing, or still carried old auto-announce wiring that forced a
delete-and-recreate, ever picked up the change.

`refresh_weekly_cron_message()` closes that gap: on every run it reads the job's currently
stored message via `openclaw cron get`, compares it to the freshly-fetched
`cron-prompt.txt`, and — only on a mismatch — patches the message in place with
`openclaw cron edit <id> --message` (`--system-event` for a systemEvent-kind job). `cron
edit` is a field-level PATCH, so schedule, timezone, `sessionTarget`, wake mode, timeout,
and delivery are untouched **by construction**, because they are never passed — not because
the function is careful to re-specify them correctly. Every failure path (CLI missing,
gateway unreachable, malformed JSON, `python3` absent, the edit itself rejected) logs a
SKIP/WARN and returns 0, leaving the OLD message in place rather than a blank or partial
one — this function can never be the reason an update aborts.

## Env vars (per box)

`FLEET_STANDING_GATE_URL`, `FLEET_STANDING_GATE_HEADER`, `FLEET_STANDING_GATE_SECRET`,
`FLEET_STANDING_BOX_SLUG` (per box — the join key).

Escape hatches: `FLEET_STANDING_GATE_BYPASS=1` (skip), `FLEET_STANDING_GATE_SHADOW=1`
(report only, never block).

## Security rules

- **Reference every n8n data table by ID, never by name**, in every workflow node and every
  script that touches `fleet_standing` or `rescue_request_ledger` (`standing.sh` uses
  `aoLFsegM1aDIrcDj`, not the name `fleet_standing`). A lookup by name follows whatever
  table currently holds that name — rename or recreate the table and the thing deciding who
  gets service silently starts reading from somewhere else, or nowhere, with no error.
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

  **What to hash.** Fetch the node object for `Relay Brain` from workflow `GdymshUbNb9eaOAC`
  (e.g. `n8n_get_workflow` with `mode: filtered`, `nodeNames: ["Relay Brain"]`) — a dict with
  exactly these keys: `id`, `name`, `parameters`, `position`, `type`, `typeVersion`. Hash the
  **whole sort-keyed node object with Python's default JSON separators** — not `jsCode` alone,
  and not the compact separator form:
  ```python
  hashlib.sha256(json.dumps(node, sort_keys=True).encode()).hexdigest()
  ```
  The current known-good value is `580566e019c7f0258191d57949ce0e7a6a1ac11082b7954e967f9387afe9b405`.
  Two wrong recipes produce *different, plausible-looking* digests — landing on either means
  you used the wrong recipe, not that you found a real edit:
  - hashing `jsCode` alone → `e0d5e52ab4a4eeb4c80ce2e21eb37ecc16409e392b353ae89baebcc2f214e38d`
  - sort-keyed node with compact `separators=(",", ":")` → `f1e9fd621ff59323db25abe5fc0d73e1971c0147c1fad79b3cc786d9f9b09990`

  Corroborating checks (verify these before trusting any digest): `jsCode` is 34,835 chars,
  and the node's key set is exactly `['id','name','parameters','position','type','typeVersion']`
  (sorted). Never paste the node's own contents (client names, aliases, roster) into this repo
  or any committed file while checking this — read it, hash it, discard it.

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
