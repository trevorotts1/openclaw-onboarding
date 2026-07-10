# How to use the Loop Protection System (Skill 61) - operator guide

Plain language for the operator. This system is silent toward clients by
construction; everything below happens on your side.

## What it does for you

Every client box is full of timers - heartbeats, crons, supervisors, retry loops,
channel pollers. When one of them fires an action whose failure does not stop the
timer, the box enters a loop: it burns the client's tokens around the clock, or it
restarts thousands of times, silently, for weeks. This skill is the reflex that
catches that in one 15-minute tick and either fixes it (deterministic, proven,
reversible fixes only) or hands you a one-tap proposal - never bothering the client.

## First run on a box (canary first, then hold)

1. Install (idempotent, refuses root; on VPS wrap in `docker exec -u node`):

       bash 61-loop-protection-system/loop-companion.sh install --role operator --box <name>

   The box is left in **DRY_RUN observe-only** (`armed=false`) - the 7-day burn-in.
   During burn-in it RECORDS every finding but changes nothing.

2. Watch what it would have done:

       bash 61-loop-protection-system/loop-companion.sh audit --local
       bash 61-loop-protection-system/loop-companion.sh status

3. After 7 clean days, arm Tier-1 auto-fix on that box:

       bash 61-loop-protection-system/loop-companion.sh arm

   Tier-2 (heartbeat re-tier, compaction correction, announce-cron conversion) stays
   a proposal everywhere until you stamp it per box. Tier-3 always asks.

## Day to day

- The 15-minute cron ticks on its own. You hear from it only on a CHANGE (a new P1,
  a fix applied, a proposal to approve). Silence means healthy.
- A confirmed loop on an armed box is fixed and reported. An ambiguous one, or a
  Tier-2/3, arrives as a proposal or a Rescue Rangers escalation with the exact
  prepared command and its one-line revert.
- To approve a prepared Tier-2 fix: `loop-companion.sh approve <finding-id>`.
- To stop the world on a unit: `loop-companion.sh park <unit>`; to release it after
  you have fixed the boot cause: `loop-companion.sh unpark <unit>`.

## What it will never do

- Call a model (it is deterministic Python; it cannot itself become a furnace).
- Touch a client's chosen model (sovereignty is absolute - it parks timers, not
  models).
- Delete a cron or a unit (disable/park only).
- Send anything to a client surface.
- Print a secret value (process-manager output is filtered to name/status/pid/restarts).
- Auto-retry a fix whose verify failed once (the healer self-breaker stops it).

## When you suspect the watchdog itself is misbehaving

Run `loop-companion.sh troubleshoot` and see `REPAIRS.md` - including the
"the healer itself is looping" branch (the session-health lesson, encoded).
