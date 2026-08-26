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

## First run on a box (operator box first, then hold)

The whole first-proof sequence — install Skill 60 + 61, verify, burn in, arm — is
wrapped in ONE idempotent operator script (run it on YOUR box only):

       bash scripts/loop-protection-first-proof.sh install     # 60 then 61, DRY_RUN, never arms
       bash scripts/loop-protection-first-proof.sh verify      # both failable drill batteries
       bash scripts/loop-protection-first-proof.sh status       # armed?, burn-in days, findings
       # ...let it observe for 7 days...
       bash scripts/loop-protection-first-proof.sh arm --yes    # arm Tier-1 (refused before 7 days)
       bash scripts/loop-protection-first-proof.sh disarm       # one-line revert
       bash scripts/loop-protection-first-proof.sh runbook      # the full runbook

(the previous script filename still resolves for one release — it is now a thin
compatibility shim in `scripts/` that execs the file above, unchanged, so any
existing invocation keeps working while you migrate to the path above)

The manual, per-skill equivalent is unchanged:

1. Install (idempotent, refuses root; on VPS wrap in `docker exec -u node`):

       bash 61-loop-protection-system/loop-companion.sh install --role operator --box <name>

   The box is left in **DRY_RUN observe-only** (`armed=false`) - the 7-day burn-in.
   During burn-in it RECORDS every finding but changes nothing.

   Since v0.6.5 the installer PROVES the cron job it registers: it lists first
   (`--all`, so a disabled job is not invisible), leaves **exactly one**
   `loop-tick-*` job however many times you run it, and **exits 5 without printing
   "Install OK"** if the watchdog is not scheduled. Confirm the box independently:

       bash 61-loop-protection-system/verify.sh --live

   Exit 0 = one cron job and a fresh completed tick; 4 = one of those is wrong and
   is named; 5 = UNDETERMINED (the gateway could not be read), which is never a pass.

2. Watch what it would have done:

       bash 61-loop-protection-system/loop-companion.sh audit --local
       bash 61-loop-protection-system/loop-companion.sh status

3. After 7 clean days, arm Tier-1 auto-fix on that box:

       bash 61-loop-protection-system/loop-companion.sh arm

   Tier-2 (heartbeat re-tier, compaction correction, announce-cron conversion) stays
   a proposal everywhere until you stamp it per box. Tier-3 always asks.

## Fleet rollout (AFTER the operator-box proof passes — operator-timed, ONE batch)

Skill 60 + 61 are WIRED into onboarding (`install.sh`) and the updater
(`update-skills.sh`) via the shared `scripts/activate-loop-protection.sh`, but
client-box activation is **HELD by default** — the wiring reads a fleet gate:

- `61-loop-protection-system/config/rollout.json` → `fleet_rollout_enabled` (default **false**), or
- env `OPENCLAW_LOOP_PROTECTION_ROLLOUT=1` (per-box / staged override).

While HELD, a fresh onboarding or an update runs the activation step and it prints
a HELD note and no-ops (no cron, no ledger). When you flip the gate to `true` in
ONE commit (the batch rollout), every onboarding + update thereafter installs the
60→61 watchdogs in **DRY_RUN observe-only** (never armed). Arming stays a separate,
per-box, post-burn-in operator action. Verify `RESCUE_RANGERS_WEBHOOK_URL` per box
during the roll (the 30-min unacked-P1 escalation path depends on it).

## Day to day

- The 15-minute cron ticks on its own. You hear from it only on a CHANGE (a new P1,
  a fix applied, a proposal to approve). Silence means healthy.
- A confirmed loop on an armed box is fixed and reported. An ambiguous one, or a
  Tier-2/3, arrives as a proposal or a Rescue Rangers escalation with the exact
  prepared command and its one-line revert.
- To approve a prepared Tier-2 fix: `loop-companion.sh approve <finding-id>`.
- To stop the world on a unit: `loop-companion.sh park <unit>`; to release it after
  you have fixed the boot cause: `loop-companion.sh unpark <unit>`.

## The one you have to recognise by hand: a poisoned transcript

**Symptom: the agent answers CORRECTLY but SLOWLY.** That is the whole tell, and it
is counter-intuitive enough to be worth memorising:

> **A broken agent gives wrong answers. A poisoned one gives right answers slowly.**

If replies are wrong, garbled, or missing, look at config, the model, or the
channel. If replies are *correct* but take minutes when they used to take seconds,
suspect this instead. What is happening is that a run got stuck against the
runtime's own "you already called that tool with identical arguments" guard and is
burning minutes going nowhere - and while it does, it **holds the conversation
lane**, so your messages queue behind it. The reply you eventually get is fine. It
just had to wait for a doomed run to die first.

**Emergency recovery, any time, no tooling required: start a fresh session with
`/new`.** That is the fastest fix and it is always safe. The old transcript is kept.

Why `/new` works: the transcript itself is the problem. A run that fills a session
with hundreds of identical refusals leaves that wreckage in the history the model
reads back as its own past, so every later turn on that session starts degraded -
even after whatever triggered it is long gone. This is the one failure mode in this
skill where fixing the *environment* does not help, because the fault is in the
*context*.

**What D5 does about it on an armed box:** it watches each transcript for those
refusal bursts and, when one is confirmed, **archives the transcript so the next
turn starts clean** - moved to a timestamped file beside it, never deleted, and
reverted by moving it back. It will **not** roll a session that is still being
written; a conversation in progress gets the alert and a prepared abort instead.

**One caveat, stated plainly:** compaction checkpoint summaries can capture the
loop verbatim, and those are re-injected when a session resumes, so they **survive**
the transcript roll. D5 detects and reports them, but pruning them is a Tier-2
prepared action (the live gateway rewrites the session store, so an in-place edit
without a restart gets clobbered). If you see `SECOND CARRIER` in a finding, the
roll alone has not fully cleared it.

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
