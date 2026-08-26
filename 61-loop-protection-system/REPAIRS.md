# REPAIRS - Loop Protection System troubleshooting tree

Read top to bottom; the first matching branch is your fix. Everything here is
operator-facing and deterministic.

## 0. The healer itself is looping (read this FIRST)

The session-health.sh incident is the reason this branch leads. If the watchdog is
applying the same fix to the same target again and again:

- The **healer breaker** should already have stopped it: > 3 fixes on one target in
  24h, OR any fix whose verify failed once, trips it and the watchdog STOPS fixing
  that target and escalates. Confirm with `loop-companion.sh status` (look for the
  target under tripped breakers / open findings marked escalated).
- If the healer breaker did NOT stop it, that is a P0 defect in this skill. Disarm
  the box immediately (`loop-companion.sh disarm` -> back to DRY_RUN observe-only),
  then escalate to Rescue Rangers with the ledger. A broken healer is worse than no
  healer.

## 1. python3 or sqlite3 missing

`preflight.sh` exits 3. Install python3 (stdlib sqlite3 ships with it). The watchdog
needs nothing else - no node, no build step, no key.

## 2. "REFUSED: running as root"

A config-touching path refuses root (a root-owned openclaw.json is the LP-B5 freeze).
On VPS run every command inside `docker exec -u node <container> ...`. The
`LOOP_ALLOW_ROOT=1` seam exists ONLY for the CI/self-test sandbox, never production.

## 3. The tick reports findings but nothing is fixed

Expected during the 7-day burn-in: `armed=false` means DRY_RUN observe-only - it
RECORDS and PLANS but mutates nothing. Arm Tier-1 with `loop-companion.sh arm` after
the burn-in. Tier-2/3 never auto-apply regardless.

## 4. A unit is parked and will not come back

By design: a tripped process breaker parks the unit visible-red so it cannot silently
respawn into the same crash. Fix the boot cause (stale build / missing env / root-owned
files / port conflict), THEN `loop-companion.sh unpark <unit>` and watch the stability
window (pid stable at t+15/35/65s).

## 5. An escalation did not reach Rescue Rangers

**First check whether it was SUPPRESSED rather than lost.** Since 0.6.3 every
escalation passes a per-key gate (RR-ESC-GATE-20260826). The tick's stderr names it:

    INFO [loop_watchdog]: escalation for finding <id> SUPPRESSED (dedup|backoff; key=... window=12.0h attempt=N next_at=...); finding left OPEN, not escalated

- `dedup` - this exact `dedup_key` was already ADMITTED inside
  `alert.escalation.dedup_window_hours` (12h). Working as designed; the finding stays
  `open` and re-escalates after the window.
- `backoff` - the intake REFUSED this key and it is waiting until `next_at`
  (2h/4h/8h/16h/24h cap, jittered). Read the matching `ERROR` line above it for the
  refusal reason, and the spill file's `_unsent_reason`.

Suppression is **per `dedup_key`**, so a different problem still escalates immediately.
If a NEW problem was suppressed, that is a P0 defect in this skill - not a tuning
question. `escalation_suppressed_by` in the tick summary breaks the count down by
reason, and `escalate:<dedup_key>` rows in the ledger's `backoff_state` table show
every key currently backed off (the ledger DB is `<state>/loop.db`; this one-liner is
paste-tested and needs only python3, which preflight already requires):

    cd ~/.openclaw/skills/61-loop-protection-system/scripts && python3 -c "import sys;sys.path.insert(0,'.');from loop_ledger import Ledger;l=Ledger();print('\n'.join('%s attempt=%s next_at=%s'%(r['job'],r['attempt'],r['next_at']) for r in l.conn.execute(\"SELECT job,attempt,next_at FROM backoff_state WHERE job LIKE 'escalate:%' ORDER BY next_at\")) or 'no escalation backoffs');l.close()"

Escalations go ONLY via the n8n webhook `$RESCUE_RANGERS_WEBHOOK_URL`
(`openclaw message send` to the group is silently dropped - bots cannot read other
bots). If the webhook was down, OR the intake REFUSED the payload, it is written to
`<state>/escalations/UNSENT-esc-*.json` with the reason in `_unsent_reason`.

Spills are replayed by `loop_escalate.py --drain`, which is **DISARMED BY DEFAULT and
operator-run**. The watchdog's automatic drain is behind an explicit enable gate:

    RESCUE_RANGERS_DRAIN_ENABLE=1        # absent env = DISARMED

With the env absent the tick records
`{"skipped": "DISARMED RR-DRAIN-DISARMED-20260826", "rearm": "RESCUE_RANGERS_DRAIN_ENABLE=1"}`,
so a tick log PROVES the state either way instead of implying it by silence.

There are TWO INDEPENDENT LOCKS, and an automatic drain requires BOTH to be released:

    RESCUE_RANGERS_DRAIN_ENABLE=1        # 1. the gate: is drain() CALLED at all
    RESCUE_RANGERS_DRAIN_PER_TICK=2      # 2. the cap: default 0, so a call no-ops

Setting only the first changes nothing - the call is made and returns immediately with
`"stopped": "drain disabled: per-tick cap is 0 ..."`. That is deliberate: every
single-layer protection in this incident failed somewhere. `2` is the recommended rate.
An explicit `RESCUE_RANGERS_DRAIN_PER_TICK=0` is honoured as a real kill and no longer
falls back to the default.

Drain a backlog deliberately with `loop_escalate.py --drain --limit N` (add `--dry-run`
to see what would be replayed without posting). NOTE: a direct `--drain` run bypasses
the enable gate entirely - that is correct and intended for operator-run drains, but it
means a direct call posting is NOT evidence that the automatic drain is armed. To check
whether a box drains by itself, read the gate in `loop_watchdog.py`, or look for the
DISARMED marker in a tick summary.

WHY IT IS OFF (2026-08-26): the limiter in the script is PER BOX, but the intake limit
is GLOBAL - "more than 12 escalations/60s" for the whole fleet. 35 boxes each behaving
politely at 2/tick still compose to ~70 posts per tick window against a ceiling of 12.
Run autonomously fleet-wide it delivered 10,595 stranded escalations and saturated the
shared intake: HTTP 429, and execution duration degraded from a 29.8s baseline to
229s/221s/187s/183s. Since the client timeout is 120s, REAL client escalations then
timed out. Draining a backlog must never starve live traffic. Turning it on fleet-wide
requires GLOBAL sequencing across boxes, or a per-box limit enforced at the intake.

The gate lives in `loop_watchdog.py` rather than in a numeric default because
`update-skills.sh` delivers this skill with `cp -Rp` and OVERWRITES that file on every
box. A box-local disarm would be wiped by the next roll, re-arming the whole fleet at
once. The repo ships the same gate the live boxes carry, so a roll PRESERVES the
disarmed state.

When enabled, the drain is deliberately slow: spills are deduped by problem identity,
at most N DISTINCT problems are re-posted per tick, spaced after a per-box jitter, and
it stops the moment one post fails. A file is cleared only on confirmed admission and
is MOVED to `<state>/escalations/drained/`, never deleted.

To work a backlog down safely, run it from ONE box at a time with a small `--limit` and
watch intake latency between runs.

Check both dirs; read `_unsent_reason` first - it names the fault. Confirm
`$RESCUE_RANGERS_WEBHOOK_URL` is set and reachable, and that
`$RESCUE_RANGERS_WEBHOOK_SECRET` is present (the intake 403s without the header).
`--drain --dry-run` reports what WOULD be replayed and posts nothing.

NOTE (2026-08-26): before this date the line above claimed spills were "retried next
tick". Nothing ever read the directory back - no replay code existed - so every spilled
escalation was lost. If a box has a large backlog under `escalations/`, that is the
cause, and the drain will work through it a few problems per tick.

## 6. False positives above the floor

Target is <= 2 per box per month after burn-in. If higher: the fix is DATA, not code -
tune the relevant threshold in `config/thresholds.json` (it rides the repo + rollout,
never a box-local edit), reproduce the false positive as a fixture, and route through
the Healer so the signature is corrected once, fleet-wide.

## 7. The watchdog cron is missing, duplicated, or the tick never fires

**Ask the box, do not guess.** Two commands answer it, and both give a NAMED negative
rather than a bare "no":

    bash verify.sh --live                              # both facts at once
    python3 scripts/loop_cron.py status --json         # how many loop-tick jobs exist
    python3 scripts/loop_ledger.py liveness            # when a tick last COMPLETED

Exit 0 = proven; 4 = wrong (the count or the age is named); **5 = UNDETERMINED**, which
means the gateway could not be read or `openclaw` could not be resolved — not that the
box is unwatched. If `loop_cron.py` reports it probed a list of paths and found nothing,
the binary is almost certainly there and off `PATH`: a bare ssh to a Mac gets
`/usr/bin:/bin:/usr/sbin:/sbin`, while openclaw lives in `/opt/homebrew/bin` (Apple
Silicon), `/usr/local/bin` (Intel) or `~/.local/bin`. Point `LOOP_OPENCLAW_BIN` at it
and re-run.

**DUPLICATES (v0.6.5).** Until 0.6.5 `install.sh` called `openclaw cron add`
unconditionally and the CLI has no upsert, so every re-run added another job — 25 of 34
boxes carried 2-12 of them, all enabled, all `*/15`, the watchdog firing 2-12x per
window. Re-running the installer now COLLAPSES them to one:

    bash loop-companion.sh install --role client --box <box>

It keeps the oldest ENABLED job (longest run history), fixes its schedule in place if it
is not `*/15 * * * *`, and removes the rest by id, printing every removal. It does NOT
rename it (hostnames flap `Mac.lan` -> `Mac`; renaming a working job every flap is churn)
and it does NOT re-enable a DISABLED registration — that is somebody's decision, so the
installer reports it and exits 5 instead. Re-enable deliberately:
`openclaw cron list --all` to find the id, then `openclaw cron enable <id>`. It only ever removes a job
that is BOTH named `loop-tick-*` AND recognisably ours; anything else is reported and
left alone for you. `LOOP_CRON_NO_PRUNE=1` reports instead of removing.

**A TICK THAT NEVER FIRES.** `liveness` reads ledger meta `last_tick_ts`, stamped by
every completed tick including one that finds nothing. Do **not** substitute
`MAX(findings.tick_ts)` — that measures whether the box HAS a loop, so a healthy box
reads as a dead watchdog; it produced a false "6 boxes unwatched" report on 2026-08-26,
one of which had ticked 13 minutes earlier. A ledger with no stamp at all is a watchdog
older than v0.6.5, not a dead one — check the cron job before concluding anything.

`loop-companion.sh install` re-registers the host-level `*/15` tick (`--no-deliver`,
operator-only, OUTSIDE any OpenClaw session). Because the watchdog must survive the
very wedges it treats (LP-B5 freezes the cron engine), on Mac prefer a host crontab /
launchd agent under the login user; on VPS a host-side cron that enters via
`docker exec -u node`, plus an in-container fallback timer.

## 8. Loop protection stopped working right after an `openclaw update`

Expected, and it is not this skill's watchdog that broke. `openclaw update` reinstalls
node_modules, which silently reverts the **dist patch** that makes a runaway tool loop
actually ABORT, and it can regenerate the gateway service-env file (dropping the Telegram
spooled-handler turn timeout, after which any turn over 5 minutes is killed and its text
nulled). Nothing warns you; loop protection simply stops aborting.

Run the restore-verify script — read-only, safe any time:

```bash
bash 61-loop-protection-system/scripts/openclaw-loop-protection-restore.sh
```

It checks all nine pieces of the stack and prints a per-item OK / DRIFT / FAIL. Exit 0 =
clean, 3 = drift found, 4 = hard fail, 2 = usage/prerequisite. Then repair what is
repairable:

```bash
bash 61-loop-protection-system/scripts/openclaw-loop-protection-restore.sh --apply
```

Notes that matter:
- It **never restarts the gateway.** A dist or service-env change does not take effect
  until you restart it yourself, when the box is idle. The script says so and stops.
- It is **fail-loud**: if a dist anchor is neither found nor already-applied, upstream
  changed — it reports `UPSTREAM_CHANGED`, refuses to patch, and exits 4. Re-derive the
  patch against that build rather than forcing it.
- It **never prints a secret.** The service-env file and openclaw.json are compared by
  key name and boolean/numeric value only; there is no flag that disables redaction.
- Some items are deliberately NOT auto-fixed because they are the operator's call —
  notably a `tools.allow` list on the main agent that omits `write` (the shape that
  caused the two-week outage: the flush prompt orders a write the agent has no tool for,
  so the turn loops). It reports and tells you what to add.

## 9. Reading Skill 60's ledger fails

Non-fatal by design: Loop Protection consumes Skill 60's events read-only and
best-effort. A missing Skill 60 ledger contributes no cross-signal but never crashes
the tick (a probe failure is data, never a crash).
