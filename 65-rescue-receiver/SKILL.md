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
  version: "v22.0.59"
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
  enrolled (RR_RECEIVER_URL + RR_BOX_TOKEN present in the secrets env). Safe to
  re-run on every roll.
- Requires `65-rescue-receiver/rescue-poll.sh` to exist under the box's skills
  dir; the skill dir ships via the normal update-skills roll.

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
