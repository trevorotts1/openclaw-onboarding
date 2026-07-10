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

Escalations go ONLY via the n8n webhook `$RESCUE_RANGERS_WEBHOOK_URL`
(`openclaw message send` to the group is silently dropped - bots cannot read other
bots). If the webhook was down, the payload is written to
`<state>/escalations/UNSENT-esc-*.json` and retried next tick. Check that dir; confirm
`$RESCUE_RANGERS_WEBHOOK_URL` is set and reachable.

## 6. False positives above the floor

Target is <= 2 per box per month after burn-in. If higher: the fix is DATA, not code -
tune the relevant threshold in `config/thresholds.json` (it rides the repo + rollout,
never a box-local edit), reproduce the false positive as a fixture, and route through
the Healer so the signature is corrected once, fleet-wide.

## 7. The watchdog cron is missing or the tick never fires

`loop-companion.sh install` re-registers the host-level `*/15` tick (`--no-deliver`,
operator-only, OUTSIDE any OpenClaw session). Because the watchdog must survive the
very wedges it treats (LP-B5 freezes the cron engine), on Mac prefer a host crontab /
launchd agent under the login user; on VPS a host-side cron that enters via
`docker exec -u node`, plus an in-container fallback timer.

## 8. Reading Skill 60's ledger fails

Non-fatal by design: Loop Protection consumes Skill 60's events read-only and
best-effort. A missing Skill 60 ledger contributes no cross-signal but never crashes
the tick (a probe failure is data, never a crash).
