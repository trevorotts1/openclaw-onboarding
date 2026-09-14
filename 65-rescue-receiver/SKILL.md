---
name: rescue-receiver
description: >
  Fleet escalation plumbing: pulls Rescue Rangers coaching tickets from the n8n
  rr_outbox (RR-07 receiver gateway) and hands each to the local agent as an
  isolated per-ticket session via the client's own `openclaw agent` turn, then
  acks delivered/failed against the HONESTY CONTRACT. Client-silent operator
  tooling — never announces itself to the client, never touches client models
  or credentials.
metadata:
  version: "v23.4.5"
  priority: HIGH
---

# Rescue Receiver (Skill 65)

## What this is

The box-side half of the Rescue Rangers coaching loop. When the fleet's n8n
Relay Brain mints a ticket and the RR-07 receiver gateway queues a coaching
instruction for THIS box in `rr_outbox`, this skill's `rescue-poll.sh`
(registered as a `kind:command` cron, every 2 minutes) claims it, runs the
pre-proven local delivery command, and acks the verdict.

## The HONESTY CONTRACT

- `delivered` ONLY when the delivery command exited 0 AND a non-empty reply was
  extracted.
- everything else acks `failed`. Ambiguous is never fixed.
- receiver v1.3.0: an exit-0 non-empty reply whose text matches
  escalation/deferral language ("could not", "unable to", "human intervention",
  "I don't have", "needs human", "failed to") acks `failed` with
  fail_reason `escalation_language` and a `reply_excerpt` of the text — a
  turn that says it failed is a failure, never a delivery.
- a box that stays silent leaves its ticket non-terminal — the fleet SLA sweep
  re-pages it. Silence is never success.

## Wiring

- `wire.sh` — idempotent; registers the */2-minute cron ONLY when the box is
  enrolled (RR_RECEIVER_URL + RR_BOX_TOKEN + RR_BOX_SLUG present in the secrets
  env). Safe to re-run on every roll.
- RR-028: it RECONCILES rather than assumes. The cron is read back from
  `openclaw cron list --json` AND from the gateway's stored
  `cron_jobs.job_json` (the only view that shows a DISABLED job); duplicates
  are collapsed, and command / schedule / enabled / delivery flags are compared
  and repaired (`cron edit` in place, else replace) with a FRESH readback after
  every write. A write that does not read back is never reported as success.
  A row the readback cannot corroborate, or whose `enabled` bit no view reports,
  is REFUSED rather than repaired (see the store/unobservable rules below).
  Reconciliation reads NO software version, so it is not gated by a
  `.wired-<version>` sentinel and gives the same verdict across a version
  change. `wire.sh`'s exit code is the INSTALLER's claim (files installed) — it
  is never "receiver ready".
- RR-028 re-review (23.4.2, tightened by final review 23.4.3) — the gateway STORE
  may VETO, never LICENSE. The store is a file the descriptor resolved
  (`ocd_state_db` accepts any readable candidate sqlite with >=1 table), so "a
  store resolved" is not "this store reflects the gateway". An ADD therefore
  requires the CLI's OWN listing to have been asked for a full-status flag
  (`--all` / `--include-disabled` / `--show-disabled`, advertised by that CLI)
  and to have reported nothing; and a REMOVAL additionally requires the
  gateway's own listing to show the row, the row to have been OBSERVED with
  `enabled=true`, and never to have been seen DISABLED. A job the
  operator switched off is never deleted, exactly as it is never re-enabled —
  and a row whose `enabled` bit NO view reports is never edited, replaced or
  removed either: the reconciler refuses (`enabled_unobservable`, rc 8, nothing
  mutated, nothing claimed), because "we could not see it" must never authorise
  destroying it. The store is compared against the CLI's listing for the managed
  name: agreement corroborates; a contradiction
  (`cron_source_disagreement`) refuses, and a store row the CLI's listing does
  not show is reported `unconfirmed` (`store_row_omitted_by_cli`) — never
  `corroborated` — and licenses nothing either. A CLI that could not ANSWER is
  not a view that answered "none": a gateway the box cannot reach (measured: the
  CLI prints `Gateway not reachable at ws://… (ECONNREFUSED)` to stderr and exits
  0) is reported `cli_unreachable` and nothing is compared at all — an empty
  listing from a failed command is never turned into a two-view contradiction
  against the store. The legacy-name cleanup that
  runs before reconciliation is a removal too and goes through the same guard.
- Requires `65-rescue-receiver/rescue-poll.sh` and
  `65-rescue-receiver/rr-readiness.sh` to exist under the box's skills dir; the
  skill dir ships via the normal update-skills roll.
- Requires `shared-utils/rr-readiness.sh` (RR-028): the readiness engine —
  explicit states UNENROLLED / ENROLLED_PENDING / SCHEDULED / VERIFIED with an
  explicit reason each, keyed by a desired-config digest (name, schedule,
  command, enabled, delivery, slug, URL and a SALTED token commitment).
- Requires `shared-utils/oc-env-descriptor.sh` (RR-029): the ONE host/container
  descriptor. The runtime the cron is scheduled in is derived from it, and a
  readiness receipt only verifies the runtime it was taken in.
- Requires `shared-utils/rescue-env.sh` (RR-027): the shared dotenv parser +
  child-env scrub. Enrollment values are PARSED (never sourced as shell, never
  exported), and every child of the poll runs with rescue credential aliases
  removed from its environment while necessary authorized model/tool
  credentials pass through untouched. Malformed store lines fail VISIBLY
  (file + line named on stderr, values never printed) instead of a silent
  half-config.

## Readiness (RR-028)

```sh
bash <ocroot>/skills/65-rescue-receiver/rr-readiness.sh            # report (read-only)
bash <ocroot>/skills/65-rescue-receiver/rr-readiness.sh --json     # one JSON object
bash <ocroot>/skills/65-rescue-receiver/rr-readiness.sh --reconcile
bash <ocroot>/skills/65-rescue-receiver/rr-readiness.sh --probe    # safe test claim
```

| state | meaning |
|---|---|
| `UNENROLLED` | slug/token/URL absent, or the store is unreadable/malformed — the reason names the missing NAME(s) |
| `ENROLLED_PENDING` | enrolled, but scheduling is unproven: cron absent/duplicated/mismatched/disabled, readback unreadable, or a runtime requirement (parser / curl / base64 / openclaw / node) unresolved |
| `SCHEDULED` | exactly one cron read back with the desired digest, enabled and silent — no verified receipt yet |
| `VERIFIED` | the above, plus a receipt from a safe test claim taken in the intended runtime |

What `VERIFIED` means, honestly: the receipt is a plain local FILE recording
that a safe test claim was answered in this runtime. Nothing authenticates it —
there is no signature, no HMAC and no signing key on the box — so a hand-written
receipt carrying the printed digest, runtime id and claim fields is
indistinguishable from one the engine wrote. `VERIFIED` is a local liveness
attestation, not a tamper-proof one.

Exit codes: `0` VERIFIED, `1` SCHEDULED, `2` ENROLLED_PENDING, `3` UNENROLLED,
`78` no openclaw root. The safe test claim is a capacity-0 `dry_run` claim that
starts no agent turn and acks nothing; if the receiver hands it an instruction
it is REFUSED and no receipt is written (the box stays `SCHEDULED`). The bearer
token rides a 0600 `curl -H @file` header inside a 0700 private temp dir —
never argv, never a log. Exit code of `wire.sh` = files installed; readiness is
a separate claim that only `--probe` can raise to `VERIFIED`.

## What the agent needs to know

- Rescue Rangers is the fleet escalation team. The box's OWN env/secrets are
  knowledge sources: `RESCUE_RANGERS_WEBHOOK_URL` (POST-only; GET 404/302 is
  NORMAL), `RESCUE_RANGERS_HELP_CHAT_ID` (deprecated), the `X-Rescue-Secret`
  (verify by sha256 only, never print).
- Self-verify connectivity headless BEFORE claiming you cannot do something:
  `curl -sI <dashboard-url>` for the CF Access 302 chain, and a webhook
  `__AUTHTEST__` POST expecting `{"status":"test_suppressed"}`.
- NEVER tell a client "I don't have your credentials" without first reading
  env, secrets and config and proving absence.
