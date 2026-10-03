#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_watchdog.py
# The per-box watchdog tick (spec Section 6.1). ONE tick, default every 15 min,
# jittered, host-level, OUTSIDE every OpenClaw session (the Box B law): it must
# survive the very wedges it treats (it does not depend on the gateway, the cron
# engine, or the agent loop - LP-B5 kills all three).
#
# ONE TICK:
#   collect evidence (D1-D4 inputs) ->
#   run detectors D1-D4 ->
#   read NEW Skill 60 ledger events (read-only; best-effort; 60's ledger keeps its
#      single writer, we write only OUR own) ->
#   for each finding: record -> route by fix tier (6.3) -> DRY_RUN plans / armed
#      Tier-1 applies -> verify -> ledger -> alert/escalate per Section 7
#
# DETERMINISTIC PYTHON, ZERO MODEL CALLS, no long-lived daemon, tick CPU < 5s.
# DRY_RUN (armed=false) is the DEFAULT for the first 7 days (observe-only burn-in).
# tick() takes an INJECTED evidence dict so the whole pipeline is testable offline;
# collect_evidence() is the best-effort box-reading layer (never fatal on a probe
# miss: a probe failure is DATA, never a crash - loop-detector.sh's exit-0-always
# law). The collectors read the box's OWN local streams. The D2 token field is
# CONFIRMED from the OpenClaw trajectory-writer source (`usage.total`, emitted by
# getUsageTotals; the file:line proof lives on _usage_total below); the other field
# names (session triggers, cron last-run markers, handoff keys) are plausible
# OpenClaw v2026.x schema candidates, read DEFENSIVELY (multi-candidate, fail-soft)
# and to be CONFIRMED on the operator canary's real streams during burn-in:
#   D1  collect_units()    pm2 jlist (filtered to name/status/pid/restarts ONLY)
#   D2  collect_windows()  trajectory `model.completed` cumulative usage -> hourly
#                          paid/local token windows + human-initiated-session counts
#   D3  collect_runs()     offset-tracked NEW-bytes trajectory slice ->
#                          (outcome class + tool sequence + target) signatures,
#                          for SUCCESSFUL turns ("OK") as well as failures
#   D4  collect_crons()    `openclaw cron list --json` + observed-fire counting;
#       collect_wedge()    demand-without-progress ticks + orphan :port listener
#                          vs the declared supervisor in the restart-handoff file
#   D7  collect_cross_run_sends()  offset-tracked NEW-bytes slice of every recent
#                          AGENT SESSION transcript (agents/*/sessions/*.jsonl -
#                          NOT the *.trajectory.jsonl stream D1-D4 read); every
#                          inbound cross-agent delivery the gateway makes is
#                          stamped there as message.provenance (2026-08-04 proof).
#                          The raw message body is hashed and discarded inside
#                          this one collector - it never reaches a detector, a
#                          finding, or the ledger.
# The env seam LOOP_NO_PROBES=1 disables every subprocess probe (hermetic tests).
# =============================================================================
"""loop_watchdog.py - the per-box Loop Protection watchdog tick."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_backoff as BO  # noqa: E402
import loop_common as C  # noqa: E402
import loop_detectors as D  # noqa: E402
import loop_killcards as KC  # noqa: E402
import loop_escalate as ESC  # noqa: E402
from loop_ledger import Ledger, now_utc, openclaw_root  # noqa: E402


def _feed_findings(evidence, thresholds):
    """Findings about the WATCHDOG'S OWN instruments (never about the box):
      blind collector      P2 "watchdog blind: <collector>" - a feed that came back
                           EMPTY while sessions are demonstrably active. An empty
                           instrument is a broken check, not a healthy box.
      subscription burn    D2 WARN (at most) for Ollama-Cloud-style usage-window burn:
                           it never counts as paid and never goes silent as local.
    Neither escalates to Rescue Rangers (`escalate` False): an instrument fault is
    the operator's to read in the ledger/alert, and the escalation intake is a
    shared, globally rate-limited channel."""
    out = []
    for name in evidence.get("blind") or []:
        f = D._finding("LP-WD1", "P2", "collector:%s" % name,
                       "watchdog blind: %s returned zero rows while sessions are active "
                       "- an empty instrument is a broken check, not a healthy box" % name,
                       "FEED", tier=3)
        f["escalate"] = False
        out.append(f)
    t = thresholds["d2_token_burn_rate"]
    for w in evidence.get("windows") or []:
        if int(w.get("initiated_sessions", 0) or 0) != 0:
            continue
        sub = int(w.get("subscription_tokens", 0) or 0)
        streak = int(w.get("idle_consecutive", 1) or 1)
        if sub > t["warn_tokens_per_hour"] or (sub > 0 and streak >= t["idle_paid_windows_to_p1"]):
            f = D._finding("LP-A2", "WARN", "%s usage-window" % w.get("label", "window"),
                           "idle-window usage-window burn %d tok/hr (subscription tier, never "
                           "priced; it eats the plan's usage window and ends in HTTP 402/429)"
                           % sub, "D2", tier=2)
            f["escalate"] = False
            out.append(f)
    return out


def run_detectors(evidence, thresholds, signatures):
    """Run D1-D7 over injected/collected evidence. Returns a flat findings list."""
    findings = []
    findings += D.d1_restart_velocity(evidence.get("units", []), thresholds,
                                      warn_streaks=evidence.get("warn_streaks", {}))
    findings += D.d2_token_burn_rate(evidence.get("windows", []), thresholds, signatures)
    findings += D.d3_identical_signature(evidence.get("runs", []), thresholds)
    findings += D.d4_timer_refire(evidence.get("crons", []), evidence.get("wedge", {}), thresholds)
    findings += D.d5_transcript_poison(evidence.get("sessions", []), thresholds)
    findings += D.d6_futile_retry_burst(evidence.get("bursts", []), thresholds,
                                        signatures)
    findings += D.d7_cross_run_resend(evidence.get("sends", []), thresholds)
    findings += _feed_findings(evidence, thresholds)
    return findings


def _dedup_ok(led, finding, window_hours):
    """One alert per (class, box/unit) per window. Records the digest when clear."""
    key = finding.get("dedup_key") or ("%s|%s" % (finding["loop_class"], finding.get("unit")))
    if led.recent_digest(key, window_hours):
        return False
    led.record_digest("alert", key, payload=finding.get("severity"))
    return True



# --------------------------------------------------------------------------- #
# THE ESCALATION GATE (RR-ESC-GATE-20260826)
# --------------------------------------------------------------------------- #
# The Rescue Rangers escalation path had NO dedup and NO backoff - while the
# operator ALERT sitting directly below it in _handle_finding had both. Measured
# on ONE live box: a single dedup_key produced 992 escalations, and the findings
# table held 4,084 rows across 12 distinct dedup_keys. The mechanism is not
# exotic. RR-SENDER-FIX-20260826 correctly leaves a finding OPEN when the intake
# never admits its escalation, so the byte-identical escalation is rebuilt and
# re-posted on the NEXT 15-minute tick, and the next, forever. The intake's rate
# limit is GLOBAL (12/60s) across the whole fleet, so one box's runaway key
# sheds OTHER clients' live escalations; one box held 5 spill files carrying the
# same finding.
#
# Two independent controls now stand in front of ESC.send(), BOTH keyed on the
# finding's OWN dedup_key:
#
#   DEDUP    one escalation per key per window, and the digest is written ONLY
#            after the intake ADMITS the payload. A refusal must NEVER write a
#            digest: an attempt that silences its own retry is silent loss,
#            which is strictly worse than the noise this fixes.
#   BACKOFF  a refusal (HTTP 429, HTTP 502, read timeout) advances that key
#            through the EXISTING loop_backoff module and the backoff_state
#            table - 2h/4h/8h/16h/24h(cap), jittered. A refusal therefore can
#            never produce an immediate identical retry. An ADMITTED delivery
#            CLEARS the key's backoff: an admission is loop_backoff's "real
#            artifact of progress", so the next refusal restarts the ladder at
#            2h instead of resuming at the cap.
#
# BOTH are PER KEY. A genuinely NEW problem carries a NEW dedup_key and
# escalates IMMEDIATELY, on the same tick, even while another key sits in a 24h
# backoff. Nothing here is global, per-box or per-class, precisely so that
# turning a noisy system into a SILENT one is structurally impossible - that
# failure would be far worse than the one being repaired.
#
# The digest key is NAMESPACED. Ledger.recent_digest() matches on dedup_key
# ALONE and ignores `kind`, so an un-namespaced escalation digest would silence
# the operator alert for the same finding, and vice versa: two channels, one
# mute button. loop_killcards' resend cooldown namespaces for the same reason.
# The ledger-only park outcome SKS-002's kill cards report (BR.STATE_PARKED_FLAG). Read
# by VALUE so this file works on a branch that has not merged that constant yet.
PARKED_FLAG_STATE = "parked-flag"
ESCALATION_DIGEST_KIND = "escalation"
ESCALATION_DIGEST_PREFIX = "escalation|"
ESCALATION_BACKOFF_PREFIX = "escalate:"

# Fallback window when config/thresholds.json carries no
# alert.escalation.dedup_window_hours.
#
# 12h, DELIBERATELY NOT the 6h alert window. An operator alert is a local note
# in this box's own ledger; an escalation is a POST to a globally rate-limited
# shared intake that pages a human rescue team, so it must be strictly quieter
# than the alert, never merely as quiet. 12h means the rescue team sees each
# DISTINCT unresolved problem at most once per work shift - twice a day: often
# enough that an unresolved problem cannot go dark, rare enough that a problem
# already in someone's hands cannot page them again. Against the measured
# incident: that one key persisted ~10.3 days (992 ticks x 15 min); at 12h it
# posts 21 times instead of 992, and the whole box's 12 keys post at most 24
# times a day against a measured ~1,150. It also sits BELOW the 24h backoff cap,
# so the two controls compose instead of one making the other unreachable.
DEFAULT_ESCALATION_DEDUP_WINDOW_HOURS = 12


def _escalation_key(finding):
    """The identity of the PROBLEM, not of the attempt. Same derivation as
    _dedup_ok's, so the alert channel and the escalation channel cannot disagree
    about what "the same problem" means. Every detector finding already carries a
    dedup_key (loop_detectors._finding always sets one); the fallback is kept
    because _handle_finding also accepts injected findings."""
    return finding.get("dedup_key") or (
        "%s|%s" % (finding["loop_class"], finding.get("unit")))


def _escalation_window_hours(thresholds):
    """alert.escalation.dedup_window_hours, else the module default.

    A configured 0 means "no escalation dedup" and is HONOURED rather than
    replaced by the default. `value or default` swallowing an explicit zero is
    fault 5 of 0.6.2, where setting a rate limiter to 0 returned the DEFAULT
    rate - the one thing an operator reaches for under pressure did the
    opposite. Presence, never truthiness."""
    cfg = (thresholds.get("alert") or {}).get("escalation") or {}
    raw = cfg.get("dedup_window_hours")
    if raw is None:
        return float(DEFAULT_ESCALATION_DEDUP_WINDOW_HOURS)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_ESCALATION_DEDUP_WINDOW_HOURS)


def _escalation_gate(led, finding, thresholds, now=None):
    """May THIS finding post to Rescue Rangers on THIS tick?

    READ-ONLY, unlike _dedup_ok which records its digest as it checks. The
    escalation digest is written only once the intake has ADMITTED the payload
    (see _escalation_admitted), because a digest stamped at attempt time would
    suppress the retry of an escalation that was never delivered.

    Returns {ok, reason, key, window_hours, attempt, next_at}; `reason` is
    'clear', 'backoff' or 'dedup'. Backoff is tested FIRST: a key in backoff is
    the pathological case - the intake actively refused it - and naming that is
    more use to an operator than naming the dedup that would also have held it.
    """
    key = _escalation_key(finding)
    now = now or datetime.now(timezone.utc)
    window = _escalation_window_hours(thresholds)
    bo = led.get_backoff(ESCALATION_BACKOFF_PREFIX + key) or {}
    attempt = int(bo.get("attempt") or 0)
    next_at = bo.get("next_at")
    # C.parse_iso8601 always returns an AWARE UTC datetime or None, so `nxt > now`
    # can never raise a naive/aware TypeError. An unreadable next_at yields None
    # and the gate opens: this path fails OPEN, toward delivering. That direction
    # is deliberate - the worse failure of the two is silence, so a corrupt
    # backoff row must cost an extra post, never a lost escalation.
    nxt = C.parse_iso8601(next_at) if next_at else None
    out = {"key": key, "window_hours": window, "attempt": attempt,
           "next_at": next_at}
    if nxt is not None and nxt > now:
        out.update(ok=False, reason="backoff")
        return out
    # window 0 disables the dedup outright. The explicit guard is not redundant:
    # recent_digest()'s cutoff at window 0 is `now`, and a digest stamped in the
    # SAME second satisfies `ts >= cutoff`, so a 0 window would still suppress
    # once. 0 must mean zero.
    if window > 0 and led.recent_digest(ESCALATION_DIGEST_PREFIX + key, window):
        out.update(ok=False, reason="dedup")
        return out
    out.update(ok=True, reason="clear")
    return out


def _escalation_admitted(led, key):
    """The intake ADMITTED this escalation. Stamp the dedup digest (this is the
    ONLY place it is written) and clear the key's backoff ladder."""
    led.record_digest(ESCALATION_DIGEST_KIND, ESCALATION_DIGEST_PREFIX + key,
                      payload="admitted")
    BO.clear(ESCALATION_BACKOFF_PREFIX + key, led)


def _escalation_refused(led, key, thresholds):
    """The intake did NOT admit it. NO digest is written - that would silence the
    retry of an escalation nobody received. The key's backoff advances one rung
    instead (2h/4h/8h/16h/24h cap, jittered so 35 boxes sharing a */15 cron do
    not re-post in the same instant). Returns loop_backoff's dict
    {job, attempt, interval_seconds, next_at, escalate}."""
    return BO.register_failure(ESCALATION_BACKOFF_PREFIX + key, thresholds, led)


def tick(evidence, led, armed=None, escalate_transport=None, box="box"):
    """One deterministic tick over INJECTED evidence. Returns a summary dict:
      {armed, findings, applied, planned, escalated, escalation_unsent,
       escalation_suppressed, escalation_suppressed_by, escalation_channel_degraded,
       alerts, errors, drain}
    Zero model calls. With armed False (DRY_RUN) NOTHING is mutated outside OUR ledger
    (findings are still recorded - observing is the whole point of burn-in).

    ONE BAD FINDING NEVER KILLS THE TICK. Each finding is handled inside its own
    failure boundary: an exception out of the plan/apply/escalate path is counted in
    `errors`, written to stderr, and the tick CONTINUES to the next finding. This is
    not defensive garnish - an uncaught OSError from a kill card's filesystem write
    used to abort the whole tick, dropping every finding queued behind it and, in a
    scheduled job, dying silently run after run. A watchdog that dies quietly is
    worse than no watchdog, because the box now looks watched."""
    thresholds = C.load_skill_config("thresholds.json")
    signatures = C.load_signatures()
    if armed is None:
        armed = led.is_armed()
    window_hours = thresholds["alert"]["dedup_window_hours"]

    summary = {"armed": armed, "findings": 0, "applied": 0, "planned": 0,
               "escalated": 0, "escalation_unsent": 0,
               # RR-ESC-GATE-20260826. `escalated` counts ADMITTED deliveries,
               # `escalation_unsent` counts attempts the intake refused, and
               # `escalation_suppressed` counts attempts the gate never made -
               # three distinct outcomes that used to be one number.
               "escalation_suppressed": 0, "escalation_suppressed_by": {},
               "escalation_channel_degraded": 0,
               "alerts": 0, "errors": 0,
               "by_class": {}}

    findings = run_detectors(evidence, thresholds, signatures)
    # UNDETERMINED is its own answer: every source this run could not read is named
    # here, so a quiet tick is never mistaken for a healthy one.
    summary["undetermined"] = list(evidence.get("undetermined") or [])
    summary["scheduler_managed"] = list(evidence.get("scheduler_managed") or [])
    for f in findings:
        try:
            _handle_finding(f, led, thresholds, armed, box, escalate_transport,
                            window_hours, summary)
        except Exception as exc:  # noqa: BLE001 - containment is the point
            summary["errors"] += 1
            sys.stderr.write(
                "ERROR [loop_watchdog]: finding %s/%s failed to process (%s: %s); "
                "CONTINUING to the next finding - one bad unit never kills the tick\n"
                % (f.get("loop_class"), f.get("unit"), type(exc).__name__, exc))

    # Drain the UNSENT spill queue REPAIRS.md always claimed was retried.
    #
    # DISARMED BY DEFAULT. Absent env = OFF; re-arming is a deliberate explicit
    # act. This gate is the safety, not the rate cap in loop_escalate.py: a
    # numeric default cannot protect anything here, because update-skills.sh
    # delivers the skill with `cp -Rp` and OVERWRITES this file on every box, so
    # a roll would wipe a box-local disarm and re-arm all 35 boxes at once. The
    # repo ships the SAME gate the live fleet carries so a roll PRESERVES the
    # disarm. Do not rename the env var or the marker without changing both.
    #
    # WHY: this module's limiter is PER BOX; the intake limit is GLOBAL (12/60s).
    # 35 polite boxes still compose to ~70 posts per tick window. Run autonomously
    # on 2026-08-26 it delivered 10,595 escalations, drove the shared intake to
    # HTTP 429, and degraded execution from 29.8s to 229s - timing out REAL client
    # escalations against the 120s client timeout.
    #
    # Runs LAST, and only when delivering for real: an injected transport means
    # --no-send or a self-test, and a stub returning True would archive the whole
    # backlog without posting anything.
    if escalate_transport is None and os.environ.get("RESCUE_RANGERS_DRAIN_ENABLE", "") == "1":
        try:
            summary["drain"] = ESC.drain()
        except Exception as exc:  # noqa: BLE001 - a drain never kills the tick
            summary["drain"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        # Recorded either way, so a tick log PROVES the state instead of implying
        # it by silence - the same reason a failed escalation is no longer logged
        # as "escalated".
        summary["drain"] = {"skipped": "DISARMED RR-DRAIN-DISARMED-20260826",
                            "rearm": "RESCUE_RANGERS_DRAIN_ENABLE=1"}

    # ---- LIVENESS: the one fact nothing recorded (v0.6.5) -------------------
    # "When did the watchdog last RUN" had NO direct signal. The fleet inferred it
    # from MAX(findings.tick_ts), which is not liveness at all - it measures
    # whether a box HAS a loop condition. On 2026-08-26 that proxy produced a
    # false "6 boxes unwatched" report; one of those boxes had ticked 13 minutes
    # earlier and simply had nothing to find. THE HEALTHY BOX IS EXACTLY THE BOX
    # THAT METRIC CALLS DEAD, which is the worst possible direction for the error
    # to run. The only other instruments were loop.db's file mtime and the cron
    # engine's own lastRunAtMs - neither of which is inside the ledger, so neither
    # survives a box you can only reach through this skill.
    #
    # WRITTEN ON EVERY TICK, FINDINGS OR NONE. The zero-findings tick is the whole
    # point: it is the case the broken metric gets wrong. record_finding writes a row
    # only when a detector fires, so a box whose conditions CLEARED writes nothing and
    # its newest finding freezes at the last real problem - while the tick keeps
    # running perfectly every 15 minutes. The inference ran the wrong way round: a
    # quiet ledger is the watchdog reporting all-clear, and the sweep read it as a
    # casualty.
    #
    # THE OLD SIGNAL WAS RECOVERABLE ONLY BY ACCIDENT. The ledger file's mtime did
    # advance every tick - but only because collect_crons() calls
    # set_meta("d4_cron_fires") unconditionally. That is a side effect of an
    # unrelated detector, not a promise. Anyone who moved that call, or made it
    # conditional, would have silently removed the fleet's only honest heartbeat
    # without touching anything named like one. This key is the promise, stated on
    # purpose.
    #
    # WHAT IT PROVES, AND WHAT IT DOES NOT. It proves a tick RAN and reached the end.
    # It does NOT prove a RECURRING CRON is scheduled: install.sh's one-shot
    # post-install tick stamps it too, which is exactly why last_tick_mode records
    # "dry-run" for that tick. Cron existence is a SEPARATE fact, checked separately
    # by loop_cron.py. Read both, or you have only swapped one comfortable inference
    # for another.
    #
    # LAST, and outside the per-finding boundary: the stamp means "this tick ran to
    # completion", so a tick that died mid-way must NOT leave a fresh one. A failed
    # write is REPORTED and COUNTED, never swallowed - a liveness key that silently
    # stops updating is the same lie wearing a new hat.
    try:
        led.set_meta("last_tick_ts", now_utc())
        led.set_meta("last_tick_findings", summary["findings"])
        led.set_meta("last_tick_errors", summary["errors"])
        led.set_meta("last_tick_armed", "true" if armed else "false")
        led.set_meta("last_tick_undetermined", len(summary["undetermined"]))
    except Exception as exc:  # noqa: BLE001 - reported, never silent
        summary["errors"] += 1
        sys.stderr.write(
            "ERROR [loop_watchdog]: the tick completed but last_tick_ts could NOT be "
            "written (%s: %s). This box will read as UNWATCHED until it can be.\n"
            % (type(exc).__name__, exc))
    return summary


def _handle_finding(f, led, thresholds, armed, box, escalate_transport,
                    window_hours, summary):
    """Record, route, apply/plan, escalate and alert ONE finding. Mutates `summary`.
    Raising is contained by tick()'s per-finding boundary."""
    fid = led.record_finding(f["loop_class"], f["severity"], unit=f.get("unit"),
                             evidence_path=f.get("evidence_path"),
                             detail=f.get("detail"), tier=f.get("tier"),
                             dedup_key=f.get("dedup_key"))
    f["finding_id"] = fid
    summary["findings"] += 1
    summary["by_class"][f["loop_class"]] = summary["by_class"].get(f["loop_class"], 0) + 1

    kc = KC.plan({"loop_class": f["loop_class"], "finding_id": fid}, box=box)
    kc["unit"] = f.get("unit")
    # Route by tier. Tier-1 auto-applies ONLY when armed; else it plans. Tier 2/3
    # never auto-apply. The ONE safe in-tick mechanical act is parking a crash-
    # looping PROCESS unit via the process breaker (LF-6: STOP + park, visible-red,
    # never respawns) - it touches NO client config. Only a CONFIRMED loop (a P1 D1
    # finding, which is exactly a process-breaker trip: >=10/tick or >=40/day) parks
    # in-tick; a WARN plans only. Every config-touching kill card (LF-1/2/4/5/7)
    # stays plan-only in the unattended tick and is applied SOLELY by an explicit
    # operator `fix`, so the tick never touches client config unattended. DRY_RUN =>
    # LF-6 plans (mutates nothing - the D-DRYRUN invariant); armed => LF-6 trips the
    # process breaker + parks the unit. Escalation stays an ADD-ON (the P1 operator
    # alert below, plus Tier-3 / healer-breaker escalation) - never a substitute for
    # the park (the old empty-executors bug ESCALATED instead of parking).
    in_tick_executors = {}
    if f.get("severity") == "P1" and kc.get("fix_class") == "LF-6" and f.get("unit"):
        _park_unit = f["unit"]
        in_tick_executors["LF-6"] = (
            lambda dry_run, _u=_park_unit: KC.lf6_park_process(_u, led, dry_run=dry_run))
    # LF-10 (D5): the second config-FREE in-tick act - archive a loop-poisoned
    # session transcript so the next turn starts clean. It touches ONE file, is
    # reverted by moving it back, and REFUSES a transcript that is still live,
    # so an unattended tick can never roll the conversation someone is in.
    if f.get("severity") == "P1" and kc.get("fix_class") == "LF-10" \
            and f.get("evidence_path"):
        _sess = f["evidence_path"]
        _idle = thresholds["d5_transcript_poison"]["roll_min_idle_minutes"]
        in_tick_executors["LF-10"] = (
            lambda dry_run, _p=_sess, _m=_idle: KC.lf10_archive_and_roll_session(
                _p, dry_run=dry_run, min_idle_minutes=_m))
    # LF-12 is the D7 sibling of LF-6: config-free (touches no client config,
    # only calls the native sessions.abort RPC on the one named source
    # session, then parks it), so it too applies for real in-tick on an
    # armed box rather than waiting for an explicit operator `fix`.
    if f.get("severity") == "P1" and kc.get("fix_class") == "LF-12" and f.get("unit"):
        _abort_unit = f["unit"]
        in_tick_executors["LF-12"] = (
            lambda dry_run, _u=_abort_unit: KC.lf12_abort_cross_run_resend(_u, led, dry_run=dry_run))
    result = KC.apply(kc, led, armed=armed, executors=in_tick_executors,
                      verify_failed_last=False)
    # Fix 4: a finding is `fixed` ONLY when something was really stopped/aborted. A
    # ledger-only park (`parked-flag`: a flag in OUR ledger, nothing stopped) is
    # recorded as exactly that and the finding STAYS OPEN - marking it fixed is how a
    # crash-looping process kept crashing while its alert went quiet.
    flag_only = result.get("state") == PARKED_FLAG_STATE
    if flag_only:
        summary["planned"] += 1
        summary["parked_flag"] = summary.get("parked_flag", 0) + 1
        led.record_fix(fid, kc.get("fix_class"), unit=f.get("unit"),
                       what=result.get("detail"), verify_outcome=PARKED_FLAG_STATE,
                       revert_cmd=kc.get("revert_cmd"), dry_run=False)
    elif result["status"] == "applied":
        summary["applied"] += 1
        led.record_fix(fid, kc.get("fix_class"), unit=f.get("unit"),
                       what=result.get("detail"), verify_outcome="applied",
                       revert_cmd=kc.get("revert_cmd"), dry_run=False)
        led.set_finding_state(fid, "fixed")
    else:
        summary["planned"] += 1

    # Escalate Tier-3 and any healer-breaker escalation via Rescue Rangers -
    # THROUGH the per-key gate (RR-ESC-GATE-20260826). Nothing else in this
    # function changed: the gate decides only WHETHER this key may post now.
    if result.get("escalate") and f.get("escalate") is not False:
        gate = _escalation_gate(led, f, thresholds)
        if not gate["ok"]:
            # SUPPRESSED. No payload is built, ESC.send is never reached, and
            # therefore no spill file is written - 5 identical spills for one
            # finding on one box is what the ungated path cost. The finding is
            # left OPEN and is NOT marked 'escalated': RR-SENDER-FIX-20260826's
            # rule holds unchanged, only an ADMITTED escalation is an
            # escalation, and a suppressed one was never even attempted. The
            # first eligible tick after the window or the backoff expires
            # escalates it.
            summary["escalation_suppressed"] += 1
            summary["escalation_suppressed_by"][gate["reason"]] = \
                summary["escalation_suppressed_by"].get(gate["reason"], 0) + 1
            sys.stderr.write(
                "INFO [loop_watchdog]: escalation for finding %s SUPPRESSED "
                "(%s; key=%s window=%sh attempt=%s next_at=%s); finding left "
                "OPEN, not escalated\n"
                % (fid, gate["reason"], gate["key"], gate["window_hours"],
                   gate["attempt"], gate["next_at"]))
        else:
            payload = ESC.build_payload(
                box=box, loop_class=f["loop_class"], finding=f.get("detail"),
                evidence_path=f.get("evidence_path"),
                proposed_fix=kc.get("what"), why=result.get("detail"),
                action_needed="operator decision / approve fix",
                finding_id=fid, killcard_cmd=kc.get("killcard_cmd"),
                revert_cmd=kc.get("revert_cmd"))
            res = ESC.send(payload, transport=escalate_transport)
            if res.get("sent"):
                _escalation_admitted(led, gate["key"])
                led.set_finding_state(fid, "escalated")
                summary["escalated"] += 1
            else:
                # An escalation the intake never admitted is NOT escalated.
                # Marking it so is how fleet-wide loss stayed invisible: the
                # finding was closed in the ledger, the payload sat in UNSENT,
                # and nobody was ever told. Left OPEN so a LATER tick
                # re-escalates it - later, never immediately: the identical
                # payload now backs off 2h/4h/8h/16h/24h(cap) on this key.
                summary["escalation_unsent"] += 1
                bo = _escalation_refused(led, gate["key"], thresholds)
                sys.stderr.write(
                    "ERROR [loop_watchdog]: escalation for finding %s NOT "
                    "admitted (%s); payload spilled to %s; left open; key=%s "
                    "backs off to %s (attempt %d)\n"
                    % (fid, res.get("error"), res.get("unsent_path"),
                       gate["key"], bo["next_at"], bo["attempt"]))
                if bo.get("escalate"):
                    # loop_backoff's retry breaker trips after K consecutive
                    # failures and normally means "hand it up to Rescue
                    # Rangers" - which is the very channel that is failing. It
                    # is RECORDED and logged, never converted into another post
                    # to the thing that just refused K times in a row.
                    summary["escalation_channel_degraded"] += 1
                    sys.stderr.write(
                        "ERROR [loop_watchdog]: Rescue Rangers refused key=%s "
                        "%d consecutive times - the ESCALATION CHANNEL itself "
                        "is degraded on this box. Not re-escalated (that is "
                        "the same channel). Operator action required.\n"
                        % (gate["key"], bo["attempt"]))

    # operator alert (deduped). P1 bypasses batching but not dedup.
    if f["severity"] in ("P1", "P2") and _dedup_ok(led, f, window_hours):
        summary["alerts"] += 1


# --------------------------------------------------------------------------- #
# collect_*() - the best-effort box-reading layer (never fatal)
# ---------------------------------------------------------------------------
# THE STUB THAT MISSED THE STAR INCIDENT LIVED HERE: collect_evidence() used to
# return {"windows": [], "runs": [], "crons": [], "wedge": {}} - so even a fully
# armed watchdog handed D2/D3/D4 EMPTY evidence on a real box (fix design
# 2026-07-13 SS4, finding 2: "the single most important repo finding"). Every
# collector below reads a REAL local stream and fails SOFT: a missing/unreadable
# source contributes no findings (never a crash, never a guess). The D2 token
# field is source-confirmed (see _usage_total); every other field name is read
# through a multi-candidate, fail-soft accessor so a schema-name miss degrades to
# "no finding", never a wrong one. No secret VALUE is ever read, stored, or
# printed - these streams carry counts, ids, model ids, tool NAMES, and
# timestamps only, and the pm2 path stays behind filter_pm2_record.
# --------------------------------------------------------------------------- #
_PROBES_OFF_ENV = "LOOP_NO_PROBES"  # =1 disables every subprocess probe (tests)

# session.started `data.trigger` values that count as HUMAN-initiated. Only 'user'
# is a human; cron/heartbeat/memory stay idle-classified. Plausible OpenClaw
# session.started trigger values - CONFIRM on the operator canary during burn-in.
_HUMAN_TRIGGERS = ("user",)

# candidate last-run marker fields on a cron job's `state` block, tried in order
# (plausible primary: lastRunAtMs; the rest are defensive candidates). CONFIRM the
# real marker on the operator canary during burn-in.
_CRON_LAST_RUN_FIELDS = ("lastRunAtMs", "lastRunAt", "lastFireAtMs", "lastRun")


def _probes_off():
    return os.environ.get(_PROBES_OFF_ENV, "") == "1"


# =========================================================================== #
# FEED LAYER (Fix 1) - supported, content-free, READ-ONLY CLI feeds.
#
# OpenClaw v2026.7.2-beta.1 moved conversations and trajectory events into a
# per-agent SQLite database. The session/trajectory FILES the old collectors
# globbed are never written any more (measured on the operator box: 0 session or
# trajectory files in 40 days, a 622 MB database written today), so every
# file-fed detector returned an empty result - and an empty result reads as
# "healthy". The replacement reads exactly two supported commands and NEVER opens
# the SQLite file (the live database is write-ahead-log mode with compressed rows;
# the docs say to use the supported accessors):
#
#   openclaw sessions --all-agents --active 1440 --json     D2 token deltas
#   openclaw audit --kind <agent_run|tool_action> --after <iso8601> --json
#                                                            D3 / D4 wedge / D5 / D6
#
# Audit records are `redaction: metadata_only`: ids, status, sequence, timestamps,
# tool NAMES. Nothing in either feed carries message content, tool arguments or tool
# results, and every record is reduced to a small whitelist of fields the moment it
# is read, so an extra field a future OpenClaw adds can never reach a finding, the
# ledger or stdout.
#
# EVERY feed fails SOFT and says so: a miss yields no rows PLUS a named UNDETERMINED
# note (never a silent zero). Silence from a broken instrument is the failure this
# whole rebuild exists to remove; see the blind-collector control below.
# =========================================================================== #
AUDIT_OFFSET_PREFIX = "loop-audit:"  # ledger offsets key: loop-audit:<kind>

_FEEDS_DEFAULTS = {"sessions_active_minutes": 1440, "blind_control_active_minutes": 60,
                   "audit_lookback_minutes": 60, "audit_first_sight_minutes": 20,
                   "audit_page_limit": 500,
                   "audit_max_pages": 4, "cli_timeout_seconds": 20}


def _feed_cfg(thresholds=None):
    """config/thresholds.json `feeds` block over the defaults above. A missing or
    malformed block degrades to the defaults, never to a crash."""
    cfg = dict(_FEEDS_DEFAULTS)
    try:
        raw = (thresholds or C.load_skill_config("thresholds.json")).get("feeds")
    except Exception:  # noqa: BLE001 - config trouble must never kill the tick
        raw = None
    if isinstance(raw, dict):
        for k in cfg:
            v = raw.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                cfg[k] = int(v)
    return cfg


def _openclaw_bin():
    from shutil import which
    return os.environ.get("OPENCLAW_BIN") or which("openclaw")


def _loads_lenient(out):
    """json.loads, tolerating banner/log lines ahead of the JSON document. None on a
    miss. A CLI may print a one-line notice before the payload; the document itself
    is still the first '{' or '['."""
    try:
        return json.loads(out)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(out):
        if ch in "{[":
            try:
                obj, _ = dec.raw_decode(out[i:])
                return obj
            except ValueError:
                continue
    return None


def _openclaw_json(args, timeout=20):
    """Run `openclaw <args>` and parse its JSON. Returns (data, status); status is
    'ok' or a short reason (probes-off, no-binary, timeout, exec-error, exit:<rc>,
    cli-error:<type>, bad-json). Only the status reason is ever surfaced - never the
    CLI's own text. Read-only commands only; the caller picks the argv."""
    if _probes_off():
        return None, "probes-off"
    binpath = _openclaw_bin()
    if not binpath:
        return None, "no-binary"
    try:
        proc = subprocess.run([binpath] + list(args), capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (OSError, subprocess.SubprocessError):
        return None, "exec-error"
    out = (proc.stdout or "").strip()
    data = _loads_lenient(out) if out else None
    if isinstance(data, dict) and data.get("ok") is False:
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        return None, "cli-error:%s" % str(err.get("type") or "unknown")[:40]
    if proc.returncode != 0:
        return None, "exit:%d" % proc.returncode
    if data is None:
        return None, "bad-json"
    return data, "ok"


def _ts_any(v):
    """Epoch seconds, epoch milliseconds, numeric string or ISO-8601 -> aware UTC
    datetime, else None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    if isinstance(v, (int, float)):
        if v <= 0:
            return None
        sec = v / 1000.0 if v > 1e11 else float(v)
        try:
            return datetime.fromtimestamp(sec, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return _parse_ts(v)


def _meta_json(led, key):
    """A JSON dict out of ledger meta; {} on a missing/corrupt/non-dict value."""
    if led is None:
        return {}
    try:
        got = json.loads(led.get_meta(key, "{}") or "{}")
    except (ValueError, TypeError):
        return {}
    return got if isinstance(got, dict) else {}


# ---- tier resolution (config/signatures.json paid_tier_markers.tiers) -------- #
def _resolve_tier(model_id, sig):
    """'metered' | 'subscription_capped' | 'local' | 'unclassified'.

    Binds to the three-tier STRUCTURE in signatures.json (paid_tier_markers.tiers),
    first match wins, DATA ONLY - no network call, no runtime lookup. It matches the
    PROVIDER SEGMENT, never a substring ("ollama/<model>:cloud" must not read as
    metered just because the model name contains a metered vendor's name).

    'unclassified' is UNDETERMINED: the caller fires nothing on it. That includes
    a signatures.json that carries no `tiers` block at all (the pre-tier shape) -
    this reader will not guess which of the old flat markers meant what."""
    try:
        pt = (sig or {}).get("paid_tier_markers") or {}
        tiers = pt.get("tiers")
        if not isinstance(tiers, dict) or not isinstance(model_id, str) \
                or not model_id.strip():
            return "unclassified"
        norm = pt.get("normalize") or {}
        s = model_id.strip()
        if norm.get("lowercase", True):
            s = s.lower()
        if norm.get("strip_leading_slashes", True):
            s = s.lstrip("/")
        if norm.get("strip_one_trailing_parenthesized_qualifier", True):
            s = re.sub(r"\([^()]*\)$", "", s)
        routed = False
        rp = norm.get("router_prefix") or ""
        if rp and s.startswith(rp.lower()):
            s, routed = s[len(rp):], True
        met = tiers.get("metered") or {}
        sub = tiers.get("subscription_capped") or {}
        loc = tiers.get("local") or {}
        if met.get("include_anthropic_family") and any(
                s.startswith(str(p).lower())
                for p in (sig.get("anthropic_family_deny_prefixes") or [])):
            return "metered"
        provider = s.split("/", 1)[0] if "/" in s else ""
        name = s.rsplit("/", 1)[-1]
        if provider in (loc.get("providers") or []):
            return "local"
        if provider in (met.get("providers") or []) or any(
                provider.startswith(str(p)) for p in (met.get("provider_prefixes") or [])):
            return "metered"
        if (provider in (sub.get("providers") or [])
                or (routed and provider in (sub.get("providers_when_router_prefixed") or []))
                or any(name.endswith(str(x)) for x in (sub.get("name_suffixes") or []))):
            return "subscription_capped"
        if not routed and provider in (loc.get("providers_when_not_router_prefixed") or []):
            return "local"
    except Exception:  # noqa: BLE001 - a malformed tier block is UNDETERMINED, not a crash
        return "unclassified"
    return "unclassified"


def _provider_model_id(row):
    """`modelProvider` + '/' + `model` as ONE id - the join the tier resolver was
    written against (signatures.json paid_tier_markers._source, D2 EXPECTATION)."""
    prov = str(row.get("modelProvider") or "").strip()
    model = str(row.get("model") or "").strip()
    return "%s/%s" % (prov, model) if (prov and model) else (model or prov)


# ---- D2: sessions feed ------------------------------------------------------- #
def fetch_sessions(minutes, runner=None, cfg=None):
    """`openclaw sessions --all-agents --active <minutes> --json` ->
    {rows|None, status, partial}. `partial` is True when the CLI says hasMore: the
    rows we hold are NOT the whole picture and the caller must say so."""
    cfg = cfg or _feed_cfg()
    runner = runner or _openclaw_json
    data, status = runner(["sessions", "--all-agents", "--active", str(int(minutes)),
                           "--json"], timeout=cfg["cli_timeout_seconds"])
    if status != "ok":
        return {"rows": None, "status": status, "partial": False}
    rows = data.get("sessions") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return {"rows": None, "status": "bad-shape", "partial": False}
    partial = bool(isinstance(data, dict) and data.get("hasMore") is True)
    return {"rows": rows, "status": "ok", "partial": partial}


def _session_row(r):
    """A raw `sessions --json` row -> the content-free whitelist, or None."""
    if not isinstance(r, dict) or not isinstance(r.get("key"), str) or not r["key"]:
        return None
    total = _coerce_nonneg_int(r.get("totalTokens"))
    if total is None:
        parts = [p for p in (_coerce_nonneg_int(r.get("inputTokens")),
                             _coerce_nonneg_int(r.get("outputTokens"))) if p is not None]
        total = sum(parts) if parts else None
    return {"key": r["key"], "total": total, "model_id": _provider_model_id(r),
            "updated": _ts_any(r.get("updatedAt")),
            "interaction": _ts_any(r.get("lastInteractionAt"))}


def active_session_count(rows, minutes, now=None):
    """How many session rows were updated inside the last `minutes`."""
    now = now or datetime.now(timezone.utc)
    cut = now - timedelta(minutes=minutes)
    n = 0
    for r in rows or []:
        s = _session_row(r)
        if s and s["updated"] is not None and s["updated"] >= cut:
            n += 1
    return n


def collect_session_windows(rows, led=None, now=None, signatures=None, notes=None,
                            stats=None):
    """D2 evidence: hourly token windows for the trailing 24h, oldest first, from the
    `sessions` feed.

    DELTA, NEVER LIFETIME. `totalTokens` is a session's lifetime count, so each run
    charges only the difference from the value stored in ledger meta
    (d2_session_tokens) - the same rule D1 uses for restart counts. FIRST SIGHT OF A
    SESSION CHARGES 0 and a counter that goes BACKWARDS (a reset or compaction)
    re-baselines to 0: reading a long-lived session's whole history as one tick of
    burn is an instant false P1.

    IDLE IS DECIDED PER SESSION. A session is idle when its `lastInteractionAt` (the
    last REAL user/channel interaction; cron, heartbeat and exec events do not move
    it) is older than the current hour. A session with NO `lastInteractionAt` has
    never had a recorded human interaction, so it is idle too - treating it as
    undetermined would blind exactly the cron/heartbeat sessions the furnace burns
    through. Only an idle session's burn is charged; a working session's burn is not.

    THE TIER IS READ FROM DATA. The model id resolves through signatures.json
    paid_tier_markers.tiers: metered -> paid_tokens (P1 path), subscription_capped
    (Ollama Cloud) -> subscription_tokens (WARN at most, usage-window burn, never
    priced), local -> local_tokens (never flagged). An unknown tier - including a
    signatures.json with no tier block - is UNDETERMINED and fires nothing.

    With led=None (the read-only audit path) nothing is persisted, every delta is 0,
    and only the human-interaction counts are real."""
    now = now or datetime.now(timezone.utc)
    sig = signatures if signatures is not None else C.load_signatures()
    hour = now.replace(minute=0, second=0, microsecond=0)
    first_hour = hour - timedelta(hours=23)
    zero = {"paid": 0, "sub": 0, "local": 0, "undet": 0, "initiated": 0, "sessions": 0}
    hist = _meta_json(led, "d2_hourly")
    base = _meta_json(led, "d2_session_tokens")
    newbase = {}
    cur = dict(zero)
    cur.update({k: int(v) for k, v in (hist.get(hour.isoformat()) or {}).items()
                if k in zero and isinstance(v, (int, float))})
    cur_in = 0  # humans seen THIS run; recomputed each run, so it is not summed twice
    unrated = 0
    burned = 0
    for raw in rows or []:
        s = _session_row(raw)
        if s is None or s["total"] is None:
            continue
        prev = base.get(s["key"])
        try:
            prev = int(prev) if prev is not None else None
        except (TypeError, ValueError):
            prev = None
        delta = max(0, s["total"] - prev) if prev is not None and s["total"] >= prev else 0
        newbase[s["key"]] = s["total"]
        human = s["interaction"] is not None and s["interaction"] >= hour
        if human:
            cur_in += 1
        if delta <= 0:
            continue
        cur["sessions"] += 1
        burned += 1
        if human:
            continue  # working burn, not idle burn
        tier = _resolve_tier(s["model_id"], sig)
        if tier == "metered":
            cur["paid"] += delta
        elif tier == "subscription_capped":
            cur["sub"] += delta
        elif tier == "local":
            cur["local"] += delta
        else:
            cur["undet"] += delta
            unrated += 1
    cur["initiated"] = max(cur["initiated"], cur_in)
    if stats is not None:
        stats["burned_sessions"] = burned
    if notes is not None and unrated:
        notes.append("D2: %d session(s) burned tokens on a model whose tier is not "
                     "classifiable - UNDETERMINED, nothing fired on them" % unrated)
    hist[hour.isoformat()] = cur
    keep = {}
    for k, v in hist.items():
        dt = _parse_ts(k)
        if dt is not None and dt >= first_hour and isinstance(v, dict):
            keep[k] = v
    if led is not None:
        led.set_meta("d2_session_tokens", json.dumps(newbase, sort_keys=True))
        led.set_meta("d2_hourly", json.dumps(keep, sort_keys=True))
    out = []
    streak = 0
    h = first_hour
    while h <= hour:
        b = keep.get(h.isoformat(), zero)
        idle = int(b.get("initiated", 0)) == 0
        streak = streak + 1 if idle else 0
        nxt = h + timedelta(hours=1)
        out.append({"label": "%s-%sZ" % (h.strftime("%Y-%m-%d %H:00"), nxt.strftime("%H:00")),
                    "paid_tokens": int(b.get("paid", 0)),
                    "subscription_tokens": int(b.get("sub", 0)),
                    "local_tokens": int(b.get("local", 0)),
                    "undetermined_tokens": int(b.get("undet", 0)),
                    "initiated_sessions": int(b.get("initiated", 0)),
                    "idle_consecutive": streak if idle else 0,
                    "completions": int(b.get("sessions", 0))})
        h = nxt
    return out


# ---- D3 / D4 wedge / D5 / D6: audit feed ------------------------------------ #
def _seq(e):
    v = e.get("sequence") if isinstance(e, dict) else None
    return int(v) if isinstance(v, int) and not isinstance(v, bool) else None


def fetch_audit(kind, led=None, now=None, runner=None, cfg=None):
    """`openclaw audit --kind <kind> --after <iso8601> --json`, paged by nextCursor.

    Returns {events, raw_count, status, partial, cursor}:
      events     NEW records only (sequence above the stored cursor), oldest first
      raw_count  every record the lookback window returned, new or already seen -
                 the blind-collector control reads THIS, because "no NEW events"
                 is normal and "no events at all while sessions are active" is not
      partial    the page budget ran out before the stored cursor was reached, so
                 older new records exist that this run could not see (UNDETERMINED)
      cursor     the highest sequence now consumed

    THE CURSOR is persisted in the ledger offsets table under `loop-audit:<kind>`
    as the highest `sequence` consumed (records come back newest first, so the
    CLI's own page cursor is only meaningful WITHIN one run). A sequence that goes
    BACKWARDS (the state database was rebuilt) rewinds to 0 instead of silently
    discarding every record as already seen."""
    cfg = cfg or _feed_cfg()
    runner = runner or _openclaw_json
    now = now or datetime.now(timezone.utc)
    key = AUDIT_OFFSET_PREFIX + kind
    stored = led.get_offset(key) if led is not None else 0
    after = (now - timedelta(minutes=cfg["audit_lookback_minutes"])) \
        .replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    allrows = []
    raw = 0
    cursor = None
    status = "ok"
    partial = False
    for page in range(cfg["audit_max_pages"]):
        args = ["audit", "--kind", kind, "--after", after, "--limit",
                str(cfg["audit_page_limit"]), "--json"]
        if cursor is not None:
            args += ["--cursor", str(cursor)]
        data, st = runner(args, timeout=cfg["cli_timeout_seconds"])
        if st != "ok":
            status = st
            break
        evs = data.get("events") if isinstance(data, dict) else None
        if not isinstance(evs, list):
            status = "bad-shape"
            break
        raw += len(evs)
        allrows += [e for e in evs if isinstance(e, dict) and _seq(e) is not None]
        reached_old = any((_seq(e) or 0) <= stored for e in evs if isinstance(e, dict))
        nxt = data.get("nextCursor") if isinstance(data, dict) else None
        if not nxt or reached_old:
            break
        cursor = nxt
        if page == cfg["audit_max_pages"] - 1:
            partial = True
    newest = max((_seq(e) for e in allrows), default=0)
    if allrows and newest < stored:
        stored = 0  # sequence went backwards: rebuilt database - rewind, never discard
    # FIRST SIGHT (no stored cursor, a real ledger): consume only the last few minutes.
    # An hour of history handed to D3 in one slice reads a healthy 5-minute heartbeat as
    # twelve identical runs - an instant false P1 on the first tick of every box.
    first_cut = None
    if led is not None and stored == 0:
        first_cut = now - timedelta(minutes=cfg["audit_first_sight_minutes"])
    fresh = {}
    for e in allrows:
        if _seq(e) <= stored:
            continue
        if first_cut is not None:
            at = _ts_any(e.get("occurredAt"))
            if at is None or at < first_cut:
                continue
        fresh[_seq(e)] = e
    events = [fresh[k] for k in sorted(fresh)]
    out_cursor = max(newest, stored)
    if status == "ok" and led is not None and allrows:
        led.set_offset(key, out_cursor)
    return {"events": events, "raw_count": raw, "status": status, "partial": partial,
            "cursor": out_cursor}


_AUDIT_STATUS_CLASS = {"succeeded": "OK", "failed": "Failed", "cancelled": "Cancelled",
                       "timed_out": "TimedOut", "blocked": "Blocked", "unknown": "Unknown"}


def _unit_of(e):
    return "session:%s" % (e.get("sessionKey") or e.get("sessionId") or e.get("agentId")
                           or "unknown")


def audit_evidence(run_events, tool_events, thresholds=None):
    """Reduce audit records to detector evidence. COUNTS, STATUSES AND TOOL NAMES
    ONLY - the records carry nothing else, and only whitelisted fields are read.

      runs      D3  one entry per FINISHED run: (status class + the run's tool-name
                    sequence + session), ordered per session so a streak of the same
                    run status in one session is contiguous
      sessions  D5  `tool_action status=blocked` bursts per runId
      bursts    D6  FAILING-BURST face only: `failed` tool actions per (session, tool)
                    inside a 60-second window. The auth-marker face needs the tool's
                    RESULT TEXT, which audit does not carry - the loop-brake plugin
                    covers it, so failclosed is always 0 here.
      stats     D4  agent.run.started vs agent.run.finished counts in the slice
    """
    th = thresholds or C.load_skill_config("thresholds.json")
    d5 = th["d5_transcript_poison"]
    window = float(th["d6_futile_retry_burst"]["window_seconds"])
    gap = int(d5["gap_records"])
    trail_n = int(d5["window_records"])

    starts = sum(1 for e in run_events if e.get("action") == "agent.run.started")
    finished = [e for e in run_events if e.get("action") == "agent.run.finished"]
    fin_tools = [e for e in tool_events if e.get("action") == "tool.action.finished"]
    fin_tools.sort(key=lambda e: _seq(e) or 0)

    by_run = {}
    for e in fin_tools:
        by_run.setdefault(str(e.get("runId") or ""), []).append(e)

    runs = []
    for e in finished:
        st = str(e.get("status") or "unknown")
        seq_names = [str(t.get("toolName")) for t in by_run.get(str(e.get("runId") or ""), [])
                     if t.get("toolName")][:50]
        runs.append({"unit": _unit_of(e), "error_class": _AUDIT_STATUS_CLASS.get(st, "Unknown"),
                     "tool_sequence": seq_names,
                     "target": str(e.get("sessionKey") or e.get("sessionId") or "unknown"),
                     "_seq": _seq(e) or 0})
    runs.sort(key=lambda r: (r["unit"], r["_seq"]))
    for r in runs:
        r.pop("_seq", None)

    sessions = []
    for rid, evs in by_run.items():
        blocked = bursts_n = 0
        cur = since = 0
        bursts = []
        tools = set()
        trail = []
        for t in evs:
            is_b = str(t.get("status")) == "blocked"
            if is_b:
                blocked += 1
                tools.add(str(t.get("toolName") or "<tool>"))
                if cur and since > gap:
                    bursts.append(cur)
                    cur = 0
                cur += 1
                since = 0
            else:
                since += 1
            trail.append(1 if is_b else 0)
            if len(trail) > trail_n:
                trail.pop(0)
        if cur:
            bursts.append(cur)
        if blocked <= 0:
            continue
        ratio = sum(trail) / float(max(len(trail), trail_n)) if trail else 0.0
        sessions.append({"unit": "run:%s" % rid, "path": None, "bytes": 0,
                         "tail_records": len(evs), "blocked_records": blocked,
                         "max_burst": max(bursts) if bursts else 0,
                         "trailing_ratio": round(ratio, 4), "blocked_tools": sorted(tools),
                         "checkpoint_rows": 0, "poisoned_checkpoints": 0,
                         "idle_minutes": None,
                         "session_key": str(evs[0].get("sessionKey") or "")})

    per = {}
    for e in fin_tools:
        name = e.get("toolName")
        at = e.get("occurredAt")
        if not isinstance(name, str) or not name or isinstance(at, bool) \
                or not isinstance(at, (int, float)):
            continue
        per.setdefault((_unit_of(e), name), []).append(
            (at / 1000.0, str(e.get("status")) == "failed"))
    bursts_out = []
    for (unit, name), seq in sorted(per.items()):
        seq.sort()
        best = None
        i = 0
        for j in range(len(seq)):
            while seq[j][0] - seq[i][0] > window:
                i += 1
            calls = j - i + 1
            if best is None or calls > best[0]:
                best = (calls, sum(1 for k in range(i, j + 1) if seq[k][1]),
                        seq[j][0] - seq[i][0])
        if not best or best[1] <= 0:
            continue  # nothing futile in the heaviest window: no measurement at all
        bursts_out.append({"unit": unit, "path": None, "tool": name, "calls": best[0],
                           "errors": best[1], "failclosed": 0,
                           "span_seconds": round(best[2], 1)})
    return {"runs": runs, "sessions": sessions, "bursts": bursts_out,
            "stats": {"starts": starts, "completions": len(finished)}}


# ---- blind-collector control ------------------------------------------------- #
def blind_collectors(sessions_info, run_info, active_now):
    """Names of collectors that returned ZERO rows while the box is demonstrably
    active. THE KNOWN-GOOD CONTROL RULE: an empty instrument is a broken check, not
    a healthy box, so each feed is cross-checked against the OTHER. A feed that
    FAILED is UNDETERMINED - never blind and never healthy.

      audit:agent_run  the lookback window holds NO agent_run record although the
                       sessions feed shows sessions updated inside the last hour
                       (`active_now`; every run emits one record)
      sessions         the --active 1440 list is EMPTY although the audit feed saw
                       agent runs inside the lookback window"""
    blind = []
    sess_ok = bool(sessions_info) and sessions_info.get("status") == "ok"
    run_ok = bool(run_info) and run_info.get("status") == "ok"
    if run_ok and sess_ok and int(run_info.get("raw_count", 0)) == 0 and (active_now or 0) > 0:
        blind.append("audit:agent_run")
    if run_ok and sess_ok and not sessions_info.get("rows") \
            and int(run_info.get("raw_count", 0)) > 0:
        blind.append("sessions")
    return blind


def feed_health_check(runner=None, now=None, cfg=None):
    """The read-only live feed-health control (verify.sh --live, `feed-health` CLI).

    Runs `openclaw sessions --all-agents --active 60 --json` as the CONTROL and the
    agent_run audit feed as the instrument. Returns {verdict, blind, undetermined,
    active_60, agent_run_events}. verdict: 'healthy' | 'idle' | 'blind' |
    'undetermined'. Nothing is persisted; no ledger is opened."""
    cfg = cfg or _feed_cfg()
    ctl = fetch_sessions(cfg["blind_control_active_minutes"], runner, cfg)
    run = fetch_audit("agent_run", led=None, now=now, runner=runner, cfg=cfg)
    und = []
    if ctl["status"] != "ok":
        und.append("sessions control: %s" % ctl["status"])
    if run["status"] != "ok":
        und.append("audit agent_run: %s" % run["status"])
    active = len(ctl["rows"]) if ctl["rows"] is not None else None
    info = {"verdict": None, "blind": [], "undetermined": und,
            "active_60": active, "agent_run_events": run["raw_count"]}
    if ctl["status"] == "ok" and run["status"] == "ok":
        if active and run["raw_count"] == 0:
            info["blind"] = ["audit:agent_run"]
            info["verdict"] = "blind"
        else:
            info["verdict"] = "healthy" if active else "idle"
    else:
        info["verdict"] = "undetermined"
    return info


# ---- D1: restart sources (environment-free) ---------------------------------- #
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _run_text(argv, timeout=10, env=None):
    """(stdout|None, status). The argv is chosen by the caller and is always a fixed,
    format-limited or table form: never a command that dumps an environment."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              check=False, env=env)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (OSError, subprocess.SubprocessError):
        return None, "exec-error"
    if proc.returncode != 0:
        return None, "exit:%d" % proc.returncode
    return proc.stdout or "", "ok"


def _pm2_list_text():
    """`pm2 list` TABLE form -> text, or None. NEVER `pm2 jlist` and never
    `pm2 describe`: their output carries every process's environment."""
    if _probes_off():
        return None, "probes-off"
    from shutil import which
    binpath = os.environ.get("LOOP_PM2_BIN") or which("pm2")
    if not binpath:
        return None, "no-binary"
    env = dict(os.environ, COLUMNS="400", NO_COLOR="1", FORCE_COLOR="0")
    return _run_text([binpath, "list"], timeout=10, env=env)


_PM2_RESTART_HEADS = ("↺", "restarts", "restart")


def _parse_pm2_table(text):
    """Parse the `pm2 list` app table BY HEADER NAME -> [{name, pid, status,
    restart_time}], or None when no table with the required columns is found.

    None means UNDETERMINED. An unparseable table is NEVER read as "zero restarts":
    the caller leaves its baseline alone and says so. A name that pm2 truncated
    (trailing ellipsis) is skipped rather than guessed. The module table (header
    `module`, not `name`) is ignored."""
    if not isinstance(text, str) or not text.strip():
        return None
    text = _ANSI_RE.sub("", text)
    idx = None
    recs = []
    found = False
    for line in text.splitlines():
        if "│" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("│").split("│")]
        low = [c.lower() for c in cells]
        if low and low[0] == "id":
            idx = None
            rcol = next((i for i, c in enumerate(low) if c in _PM2_RESTART_HEADS), None)
            if "name" in low and "pid" in low and "status" in low and rcol is not None:
                idx = {"n": low.index("name"), "p": low.index("pid"),
                       "s": low.index("status"), "r": rcol, "w": len(cells)}
                found = True
            continue
        if idx is None or len(cells) != idx["w"]:
            continue
        name = cells[idx["n"]]
        if not name or name.endswith("…"):
            continue
        rs = cells[idx["r"]]
        pid = cells[idx["p"]]
        recs.append({"name": name, "status": cells[idx["s"]],
                     "pid": int(pid) if pid.isdigit() and int(pid) > 0 else None,
                     "restart_time": int(rs) if rs.isdigit() else 0})
    return recs if found else None


def _launchctl_list_text():
    """`launchctl list` TABLE form (PID, Status, Label) -> text. NEVER
    `launchctl print`: it dumps a service's environment."""
    if _probes_off():
        return None, "probes-off"
    from shutil import which
    binpath = os.environ.get("LOOP_LAUNCHCTL_BIN") or which("launchctl")
    if not binpath:
        return None, "no-binary"
    return _run_text([binpath, "list"], timeout=10)


def _parse_launchctl_table(text, prefix="ai.openclaw."):
    """{label: pid|None} for every label starting with `prefix`; None (UNDETERMINED)
    when the header is not exactly PID / Status / Label. A '-' PID is a loaded job
    that is not running right now."""
    if not isinstance(text, str):
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or [t.lower() for t in lines[0].split()] != ["pid", "status", "label"]:
        return None
    out = {}
    for ln in lines[1:]:
        parts = ln.split(None, 2)
        if len(parts) != 3 or not parts[2].startswith(prefix):
            continue
        pid = parts[0]
        out[parts[2].strip()] = int(pid) if pid.isdigit() else None
    return out


def _docker_restart_recs():
    """VPS host: restart counts for the OpenClaw containers, FORMAT-LIMITED only:
    `docker ps --format '{{.Names}}'` then `docker inspect -f '{{.Name}}
    {{.RestartCount}}' <ctr>...`. Never a full `docker inspect`, which carries each
    container's environment. Returns (recs|None, status)."""
    if _probes_off():
        return None, "probes-off"
    from shutil import which
    binpath = os.environ.get("LOOP_DOCKER_BIN") or which("docker")
    if not binpath:
        return None, "no-binary"
    out, st = _run_text([binpath, "ps", "--format", "{{.Names}}"], timeout=10)
    if out is None:
        return None, st
    flt = (os.environ.get("LOOP_DOCKER_NAME_FILTER") or "openclaw").lower()
    names = [n.strip() for n in out.splitlines() if flt in n.lower()]
    if not names:
        return [], "ok"
    out, st = _run_text([binpath, "inspect", "-f", "{{.Name}} {{.RestartCount}}"] + names,
                        timeout=10)
    if out is None:
        return None, st
    recs = []
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[1].isdigit():
            recs.append({"name": "docker:%s" % parts[0].lstrip("/"),
                         "restart_time": int(parts[1]), "status": "running"})
    return recs, "ok"


def _platform():
    return os.environ.get("LOOP_PLATFORM") or sys.platform


def _in_container():
    return os.path.exists("/.dockerenv")


def collect_units(led=None, recs=None, pm2_text=C.MISSING, launchctl_text=C.MISSING,
                  docker_recs=C.MISSING, notes=None, now=None):
    """D1 evidence: process restarts per unit per tick from ENVIRONMENT-FREE sources.

      pm2 apps     `pm2 list` TABLE form (never jlist/describe), parsed by header
      Mac gateway  `launchctl list` TABLE form, every `ai.openclaw.*` label: a pid
                   change between two observations is one restart
      VPS host     `docker inspect -f '{{.Name}} {{.RestartCount}}'` (format-limited)

    Every source is reduced to name/status/pid/restarts by the time it leaves its
    parser, and pm2 records still go through loop_common.filter_pm2_record, the
    single choke point.

    `delta` is restarts SINCE THE LAST TICK, baselined per unit in ledger meta.
    FIRST SIGHT OF A UNIT IS ALWAYS delta=0: pm2 and docker report LIFETIME counts,
    so treating one as a per-tick delta made the first tick on a real box read a
    long-lived unit's whole history as one storm - an instant false P1 and, on an
    armed box, an instant false park. A counter that goes BACKWARDS re-baselines to
    0. An UNPARSEABLE table is UNDETERMINED: it is noted, the baseline is left
    exactly as it was, and it is never read as zero restarts.

    The gateway findings are ALERT-ONLY: nothing here, and nothing the tick does
    with these units, stops or kills the gateway."""
    notes = notes if notes is not None else []
    now = now or datetime.now(timezone.utc)
    if recs is not None:  # injected pm2 records = a hermetic call: no live side probes
        launchctl_text = None if launchctl_text is C.MISSING else launchctl_text
        docker_recs = None if docker_recs is C.MISSING else docker_recs
    seen = _meta_json(led, "d1_restart_baseline")
    baseline = dict(seen)
    units = []

    def _ingest(recs_in, own):
        """Fold one source's records in; `own(name)` says which baseline keys the
        source owns so an UNREADABLE source cannot prune another source's entries."""
        for k in [k for k in baseline if own(k)]:
            baseline.pop(k)
        for rec in recs_in:
            f = C.filter_pm2_record(rec)
            name = f.get("name")
            if not name:
                continue
            total = int(f.get("restarts", 0) or 0)
            prev = seen.get(name)
            try:
                prev = int(prev) if prev is not None else None
            except (TypeError, ValueError):
                prev = None
            f["delta"] = max(0, total - prev) if prev is not None and total >= prev else 0
            baseline[name] = total
            units.append(f)

    # ---- pm2 -----------------------------------------------------------------
    if recs is not None:
        _ingest(recs if isinstance(recs, list) else [], lambda k: not k.startswith("docker:"))
    else:
        if pm2_text is C.MISSING:
            pm2_text, st = _pm2_list_text()
            if pm2_text is None and st not in ("probes-off", "no-binary"):
                notes.append("D1: `pm2 list` failed (%s) - restart velocity for pm2 units "
                             "is UNDETERMINED this run" % st)
        parsed = _parse_pm2_table(pm2_text) if pm2_text is not None else None
        if pm2_text is not None and parsed is None:
            notes.append("D1: `pm2 list` table could not be parsed by header (name, pid, "
                         "restarts, status) - UNDETERMINED, NOT read as zero restarts; "
                         "baseline left untouched")
        elif parsed is not None:
            _ingest(parsed, lambda k: not k.startswith("docker:"))

    # ---- docker (VPS host) ---------------------------------------------------
    if docker_recs is C.MISSING:
        docker_recs = None
        if _platform() != "darwin" and not _in_container():
            docker_recs, st = _docker_restart_recs()
            if docker_recs is None and st not in ("probes-off", "no-binary"):
                notes.append("D1: docker restart counts unreadable (%s) - UNDETERMINED" % st)
        elif _in_container():
            notes.append("D1: inside a container - no host supervisor/docker view; docker "
                         "restart velocity UNDETERMINED")
    if docker_recs is not None:
        _ingest(docker_recs, lambda k: k.startswith("docker:"))

    # ---- launchd (Mac gateway) -----------------------------------------------
    if launchctl_text is C.MISSING:
        launchctl_text = None
        if _platform() == "darwin":
            launchctl_text, st = _launchctl_list_text()
            if launchctl_text is None and st not in ("probes-off", "no-binary"):
                notes.append("D1: `launchctl list` failed (%s) - gateway restart velocity "
                             "UNDETERMINED" % st)
    if launchctl_text is not None:
        table = _parse_launchctl_table(launchctl_text)
        if table is None:
            notes.append("D1: `launchctl list` table header is not PID/Status/Label - "
                         "gateway restart velocity UNDETERMINED (NOT zero)")
        else:
            prev_pids = _meta_json(led, "d1_launchd_pids")
            changes = _meta_json(led, "d1_launchd_changes")
            cutoff = (now - timedelta(hours=24)).isoformat()
            new_pids = {}
            for label, pid in sorted(table.items()):
                prev = prev_pids.get(label, C.MISSING)
                new_pids[label] = pid
                # ONE restart = a live pid replaced by a DIFFERENT live pid. A job going
                # to or coming from '-' is a StartInterval job idling or a stop, not a
                # restart - counting those would turn every interval job into a storm.
                moved = isinstance(prev, int) and isinstance(pid, int) and pid != prev
                hist = [t for t in changes.get(label, []) if isinstance(t, str) and t >= cutoff]
                if moved:
                    hist.append(now.replace(microsecond=0).isoformat())
                changes[label] = hist
                units.append({"name": label, "status": "running" if pid else "stopped",
                              "pid": pid, "restarts": len(hist), "delta": 1 if moved else 0,
                              "day_restarts": len(hist),
                              "is_watchdog": "watchdog" in label})
            if led is not None:
                led.set_meta("d1_launchd_pids", json.dumps(new_pids, sort_keys=True))
                led.set_meta("d1_launchd_changes", json.dumps(changes, sort_keys=True))
    if led is not None:
        led.set_meta("d1_restart_baseline", json.dumps(baseline, sort_keys=True))
    return units


def _parse_ts(s):
    """ISO-8601 -> aware UTC datetime, or None. Naive stamps are treated as UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# LEGACY FILE COLLECTORS (pre-v2026.7.2-beta.1 layout) - NOT WIRED INTO THE TICK.
# collect_evidence() no longer calls anything below this banner up to the D7
# section: OpenClaw stopped writing these files, so they return [] on a current
# box (that silent emptiness is exactly what Fix 1 removed). They are kept, not
# deleted, because the LF-10 transcript-roll drills and the self-test still prove
# the D5/D7 detector arithmetic over archived transcripts.
# ponytail: delete this block when LF-10's file roll is retired (SKS-008 makes it
# a prepared proposal); no live path depends on it.
# --------------------------------------------------------------------------- #
def _legacy_file_evidence(led=None):
    """The OLD file-fed D2/D3 evidence (trajectory stream). Drills only."""
    rows, _stats = _read_new_trajectory_rows(led)
    return {"windows": collect_windows(), "runs": collect_runs(rows)}


def _traj_files(max_files=24, max_age_hours=26.0):
    """Newest trajectory files (by mtime, bounded) under <openclaw_root>/agents/
    */sessions/*.trajectory.jsonl - the same ground-truth stream Skill 60's S2
    tails. Bounded so the tick stays CPU-cheap on boxes with thousands of old
    session files. [] when the stream does not exist (probe miss = data)."""
    try:
        files = glob.glob(str(openclaw_root() / "agents" / "*" / "sessions"
                              / "*.trajectory.jsonl"))
    except OSError:
        return []
    import time
    now = time.time()
    scored = []
    for f in files:
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        if now - mt <= max_age_hours * 3600.0:
            scored.append((mt, f))
    scored.sort(reverse=True)
    return [f for _, f in scored[:max_files]]


def _iter_jsonl_tail(path, max_bytes):
    """Parsed JSON rows from the last max_bytes of a JSONL file (bounded tail
    PEEK - advances no offset). A truncated first line is dropped; a bad line is
    skipped, never fatal."""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # drop the (possibly partial) first line
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


# The trajectory `data.usage` object is the NORMALIZED usage shape OpenClaw's own
# trajectory writer emits - {input, output, cacheRead, cacheWrite, [reasoningTokens],
# total} - so the run-aggregate field is `total` (NOT `total_tokens`, which is a raw
# provider/OpenAI-compat alias the writer consumes but never emits into the stream).
# CONFIRMED from OpenClaw 2026.6.11 source, read-only, no live box touched:
#   writer  dist/selection-CVIPXpKT.js:14200  recordEvent("model.completed", {usage:
#           attemptUsage ...})  and  :14217  recordEvent("trace.artifacts", {usage:
#           attemptUsage ...})   [attemptUsage = getUsageTotals(), :13848]
#   shape   dist/selection-CVIPXpKT.js:4328-4339  getUsageTotals() ->
#           total = usageTotals.total || derivedTotal   (derivedTotal =
#           input+output+cacheRead+cacheWrite)
#   norm    dist/usage-C67Kbb7n.js:44-64  normalizeUsage() emits the SAME shape and
#           ACCEPTS raw aliases (total/totalTokens/total_tokens, input/inputTokens/
#           input_tokens, ...) -> always normalized to `.total`
#   codex   dist/run-attempt-CJMFmJj8.js:5276 normalizeCodexTokenUsage -> normalizeUsage
#           (identical `.total` shape); recorded :7268
# `usage.total` is therefore the real field; the remaining scalar candidates are
# DEFENSIVE (an un-normalized row from an older/newer schema, or a codex assistant
# snapshot carrying `totalTokens`), and the component sum is the last-resort fallback
# (== getUsageTotals' own derivedTotal) so a schema drift that drops `total` but keeps
# the buckets still charges non-zero instead of going silently blind (the Star-furnace
# failure mode). This also resolves Skill 60's _CONTEXT_TOKEN_FIELDS OPEN QUESTION for
# the token field. Re-confirm on the operator canary's real trajectory during burn-in
# before arming (the collect_windows burn-in exit gate).
_USAGE_TOTAL_FIELDS = ("total", "totalTokens", "total_tokens")  # confirmed first
_USAGE_COMPONENT_FIELDS = ("input", "output", "cacheRead", "cacheWrite")  # derivedTotal


def _coerce_nonneg_int(value):
    """A finite, non-negative real -> int; a bool, None, or anything else -> None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def _usage_total(data):
    """Total tokens off a trajectory event's `data.usage`, or None. Multi-candidate
    and FAIL-SOFT (a missing/odd shape -> None, never a guess, never a crash),
    mirroring Skill 60's _extract_context_tokens posture so the two skills agree on
    ONE defensive reader. Tries the CONFIRMED aggregate `usage.total` first, then the
    defensive raw-schema aliases `totalTokens`/`total_tokens`, then the summed
    component buckets (input+output+cacheRead+cacheWrite) - see the candidate-order
    comment above for the OpenClaw-source proof."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return None
    for fld in _USAGE_TOTAL_FIELDS:
        v = _coerce_nonneg_int(usage.get(fld))
        if v is not None:
            return v
    parts = [p for p in (_coerce_nonneg_int(usage.get(f))
                         for f in _USAGE_COMPONENT_FIELDS) if p is not None]
    return sum(parts) if parts else None


def _paid_event(row, sig):
    """Paid-tier classification of one trajectory event via signatures data
    (provider slug + model-id markers; e.g. a :cloud suffix)."""
    mid = "%s/%s" % (row.get("provider") or "", row.get("modelId") or "")
    return C.model_id_flags(mid, sig)["paid"]


def collect_windows(now=None, max_files=24, max_bytes=750_000):
    """D2 evidence: hourly token windows for the trailing 24h, oldest first, from
    the trajectory stream. Token source is `model.completed` data.usage (read via
    _usage_total, whose aggregate `usage.total` is source-confirmed - see there),
    which is CUMULATIVE PER RUN: OpenClaw's writer accumulates usage across a run
    (getUsageTotals is a run-scoped accumulator), so successive completions in one
    run carry rising totals and each completion contributes its DELTA - this is
    what makes a burn visible MID-RUN, while the looping run is still alive (the
    Star furnace burned ~466 completions inside ONE run; a run-end-only source
    sees nothing until it is over). `trace.artifacts` run totals back-fill only
    runs whose completions carried no usage (older schema). initiated_sessions
    counts `session.started` rows with a HUMAN trigger ('user'), so cron/
    heartbeat activity stays idle-classified, per the D2 contract. Extra key
    `completions` (per-window completion count) is carried for the D5
    completion-rate detector to consume when it lands (fix design SS4) - D2
    ignores it. Returns [] when no trajectory stream exists.

    BURN-IN EXIT GATE: before any `arm`, confirm collect_windows() yields non-zero
    `paid_tokens` on the operator canary's real trajectory. A silently-zero feed
    (a token-field-name drift the multi-candidate reader did not cover) would make
    D2 blind again - exactly the Star furnace blind spot - so a live non-zero
    reading is the arming precondition."""
    files = _traj_files(max_files=max_files)
    if not files:
        return []
    now = now or datetime.now(timezone.utc)
    first_hour = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    sig = C.load_signatures()
    zero = {"paid": 0, "local": 0, "initiated": 0, "completions": 0}
    buckets = {}
    prev_total = {}      # runId -> last cumulative usage.total seen
    counted_runs = set()  # runIds with >=1 usage-bearing completion
    artifact_rows = []   # (hour, paid?, total, runId) fallback candidates
    for f in files:
        for row in _iter_jsonl_tail(f, max_bytes):
            rtype = row.get("type")
            if rtype not in ("session.started", "model.completed", "trace.artifacts"):
                continue
            ts = _parse_ts(row.get("ts"))
            if ts is None or ts < first_hour:
                continue
            hour = ts.replace(minute=0, second=0, microsecond=0)
            b = buckets.setdefault(hour, dict(zero))
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            if rtype == "session.started":
                if str(data.get("trigger") or "") in _HUMAN_TRIGGERS:
                    b["initiated"] += 1
            elif rtype == "model.completed":
                b["completions"] += 1
                total = _usage_total(data)
                if total is not None:
                    rid = row.get("runId") or f
                    prev = prev_total.get(rid)
                    # cumulative-per-run: charge the delta; a decrease = a fresh
                    # accumulation baseline (compaction/branch), charge the new total
                    delta = total - prev if (prev is not None and total >= prev) else total
                    prev_total[rid] = total
                    counted_runs.add(rid)
                    b["paid" if _paid_event(row, sig) else "local"] += max(0, delta)
            else:  # trace.artifacts
                total = _usage_total(data)
                if total:
                    artifact_rows.append((hour, _paid_event(row, sig), total,
                                          row.get("runId") or f))
    for hour, paid, total, rid in artifact_rows:
        if rid in counted_runs:
            continue  # already charged via its completions - never double-count
        b = buckets.setdefault(hour, dict(zero))
        b["paid" if paid else "local"] += total
    out = []
    idle_streak = 0
    hour = first_hour
    while hour <= now:
        b = buckets.get(hour, zero)
        idle = b["initiated"] == 0
        idle_streak = idle_streak + 1 if idle else 0
        nxt = hour + timedelta(hours=1)
        out.append({"label": "%s-%sZ" % (hour.strftime("%Y-%m-%d %H:00"),
                                         nxt.strftime("%H:00")),
                    "paid_tokens": b["paid"], "local_tokens": b["local"],
                    "initiated_sessions": b["initiated"],
                    "idle_consecutive": idle_streak if idle else 0,
                    "completions": b["completions"]})
        hour = nxt
    return out


def _read_new_trajectory_rows(led=None, max_files=40, max_bytes=2_000_000):
    """The NEW-bytes-since-last-tick trajectory slice (the D3 slice pattern;
    ledger offsets under 'loop-traj:<path>'). Returns (rows, stats) where stats
    counts demand ('starts': prompt.submitted/session.started) vs progress
    ('completions': model.completed/trace.artifacts/session.ended) for the D4
    wedge probe. Offsets only ever land on line boundaries. With led=None (the
    read-only audit path) this PEEKS at the bounded tail and advances NOTHING.
    First sight of a large file starts near its tail - history is Skill 60's
    job, the watchdog's job is the last slice."""
    rows = []
    stats = {"starts": 0, "completions": 0}
    for f in _traj_files(max_files=max_files, max_age_hours=48.0):
        key = "loop-traj:%s" % f
        try:
            size = os.path.getsize(f)
        except OSError:
            continue
        fresh_cut = False
        off = led.get_offset(key) if led is not None else 0
        if off > size:
            off = 0  # rotated/truncated: start over
        if off == 0 and size > max_bytes:
            off = size - max_bytes  # not a line boundary: drop the first line below
            fresh_cut = True
        try:
            with open(f, "rb") as fh:
                fh.seek(off)
                chunk = fh.read(max_bytes)
        except OSError:
            continue
        end = chunk.rfind(b"\n")
        if end < 0:
            continue  # no complete line yet; do not advance, wait for more bytes
        lines = chunk[:end].split(b"\n")
        if fresh_cut and lines:
            lines = lines[1:]  # partial first line from a mid-file cut
        new_off = off + end + 1
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            rtype = row.get("type")
            if rtype in ("prompt.submitted", "session.started"):
                stats["starts"] += 1
            elif rtype in ("model.completed", "trace.artifacts", "session.ended"):
                stats["completions"] += 1
            row["_file"] = f
            rows.append(row)
        if led is not None:
            led.set_offset(key, new_off)
    return rows, stats


def _outcome_class_of(data):
    """The outcome class of one finished run, for the D3 signature. SUCCESSFUL
    runs return "OK" - repeated identical successful turns are a loop face too
    (the Star correction wave was 'successful' sends end to end; D3 hashing
    failures only is exactly why it stayed silent). No message content and no
    secret enters the class: structural flags and enum values only."""
    if not isinstance(data, dict):
        return "OK"
    if data.get("timedOutDuringCompaction"):
        return "CompactionTimeout"
    if data.get("timedOut"):
        return "TimedOut"
    if data.get("idleTimedOut"):
        return "IdleTimeout"
    if data.get("aborted") or data.get("externalAbort"):
        return "Aborted"
    status = str(data.get("finalStatus") or data.get("status") or "").lower()
    if status in ("", "success", "ok", "completed"):
        return "OK"
    src = data.get("promptErrorSource")
    return "Error:%s" % src if src else "Error"


def collect_runs(rows):
    """D3 evidence from the new-bytes slice: one entry per finished run, BOTH
    failures and successes. Source of truth is `trace.artifacts` (per-run
    summary: outcome flags + ordered tool NAMES in data.toolMetas); a run that
    ended without artifacts but with an erroring `session.ended` is synthesized
    from that. Entries are ordered per unit (unit-contiguous, then time) so
    interleaved sessions never break a same-unit streak - D3 counts CONSECUTIVE
    identical signatures. Tool NAMES only; arguments/content never collected."""
    runs = []
    ended = {}
    have_artifacts = set()
    for row in rows:
        rtype = row.get("type")
        if rtype not in ("trace.artifacts", "session.ended"):
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        unit = "session:%s" % (row.get("sessionKey") or row.get("sessionId") or "unknown")
        target = str(row.get("sessionKey") or row.get("sessionId") or "unknown")
        if rtype == "trace.artifacts":
            metas = data.get("toolMetas") if isinstance(data.get("toolMetas"), list) else []
            seq = [str(m.get("toolName")) for m in metas
                   if isinstance(m, dict) and m.get("toolName")]
            runs.append({"unit": unit, "error_class": _outcome_class_of(data),
                         "tool_sequence": seq, "target": target,
                         "_ts": str(row.get("ts") or ""), "_seq": row.get("seq") or 0})
            have_artifacts.add(row.get("runId"))
        else:
            ended[row.get("runId")] = (unit, target, data, str(row.get("ts") or ""),
                                       row.get("seq") or 0)
    for rid, (unit, target, data, ts, seq_no) in ended.items():
        if rid in have_artifacts:
            continue
        klass = _outcome_class_of(data)
        if klass == "OK":
            continue  # a clean end with no artifacts row carries no signature
        runs.append({"unit": unit, "error_class": klass, "tool_sequence": [],
                     "target": target, "_ts": ts, "_seq": seq_no})
    runs.sort(key=lambda r: (r["unit"], r["_ts"], r["_seq"]))
    for r in runs:
        r.pop("_ts", None)
        r.pop("_seq", None)
    return runs


def _cron_list_via_cli(timeout=15, runner=None):
    """`openclaw cron list --json` -> (jobs, has_more, status).

    `cron list --json` returns `limit: 200, hasMore` and has NO --limit/--offset
    flag, so a box with more than 200 jobs hands back a PARTIAL list. `has_more` is
    surfaced so the caller can say so (D4 is UNDETERMINED for the unseen jobs)
    instead of silently watching a fraction of the box. Read-only. The
    {jobs:[...]} / [...] shapes are both accepted."""
    runner = runner or _openclaw_json
    data, st = runner(["cron", "list", "--json"], timeout=timeout)
    if st != "ok":
        return [], False, st
    jobs = data.get("jobs") if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        return [], False, "bad-shape"
    return jobs, bool(isinstance(data, dict) and data.get("hasMore") is True), "ok"


def _cron_jobs_via_cli(timeout=15):
    """Back-compat wrapper: the jobs list only. [] on ANY miss - a probe miss is
    DATA. Use _cron_list_via_cli to also learn `hasMore`."""
    return _cron_list_via_cli(timeout)[0]


_SCHEDULER_FAILED_STATUSES = ("error", "errored", "failed", "failure", "timeout", "timed_out")


def _scheduler_managed(job):
    """Why OpenClaw's OWN scheduler is already handling this job's failures, or None.

    October's cron engine backs recurring failures off (30s, 60s, 5m, 15m, 60m) and
    AUTO-DISABLES a job after 10 consecutive failures, recording `state.autoDisabled`
    and `state.consecutiveErrors` (+ `lastRunStatus`). A job in either condition is
    the SCHEDULER's to handle: this skill records it as EVIDENCE only and never
    raises or escalates on it (LP-A4's 're-firing a terminally failing job' case)."""
    st = job.get("state") if isinstance(job.get("state"), dict) else {}
    if st.get("autoDisabled") or job.get("autoDisabled"):
        return "auto-disabled by the scheduler"
    errs = st.get("consecutiveErrors", job.get("consecutiveErrors"))
    last = str(st.get("lastRunStatus", job.get("lastRunStatus")) or "").lower()
    if isinstance(errs, int) and not isinstance(errs, bool) and errs >= 1 \
            and last in _SCHEDULER_FAILED_STATUSES:
        return "backing off after %d consecutive error(s)" % errs
    return None


def collect_crons(led=None, jobs=None, now=None, has_more=False, notes=None,
                  managed=None, runner=None):
    """D4 cron evidence: {name, declared_schedule, actual_fires_per_day, announce}
    per enabled recurring job. Fire counting is OBSERVED, not guessed: each tick
    the job's last-run marker (state.lastRunAtMs) is compared with the previous
    tick's (persisted in ledger meta 'd4_cron_fires', trailing 24h) and each
    transition counts one fire - a strict LOWER BOUND at the 15-minute cadence
    (max ~96 observations/day), which still catches any @daily job firing every
    few minutes. Until a fire has been observed actual_fires_per_day is None and
    D4's over-fire branch stays silent (never a false P1 on first tick). With
    led=None nothing is persisted. `jobs` is injectable for offline tests.

    SCHEDULER-AWARE (Fix 11): a job the scheduler has auto-disabled or is backing
    off is reported with actual_fires_per_day=None - D4's over-fire branch needs a
    number, so it stays silent - plus a `scheduler_managed` reason; the job is
    appended to `managed` (evidence only) and never becomes a finding.

    PARTIAL LIST (Fix 11): when the CLI says `hasMore`, only the first page of
    jobs was seen. That is recorded in `notes` as UNDETERMINED for the unseen
    jobs - never read as 'the rest are fine'."""
    notes = notes if notes is not None else []
    managed = managed if managed is not None else []
    if jobs is None:
        if runner is None and _probes_off():
            return []
        jobs, has_more, st = _cron_list_via_cli(runner=runner)
        if st != "ok":
            notes.append("D4: `openclaw cron list --json` unreadable (%s) - cron over-fire "
                         "check UNDETERMINED this run" % st)
    if has_more:
        notes.append("D4: `cron list --json` reported hasMore - jobs beyond the first page "
                     "were NOT seen; over-fire check is UNDETERMINED for them (never "
                     "silently partial)")
    if not jobs:
        return []
    now = now or datetime.now(timezone.utc)
    hist = {}
    if led is not None:
        try:
            hist = json.loads(led.get_meta("d4_cron_fires", "{}") or "{}")
        except (ValueError, TypeError):
            hist = {}
        if not isinstance(hist, dict):
            hist = {}
    cutoff = (now - timedelta(hours=24)).isoformat()
    out = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        sm = _scheduler_managed(j)
        if sm and sm.startswith("auto-disabled"):
            managed.append({"name": str(j.get("name") or j.get("id") or "<cron>"),
                            "reason": sm})
            continue  # auto-disabled: nothing is firing - the scheduler already stopped it
        if j.get("enabled") is False:
            continue
        sched = j.get("schedule") if isinstance(j.get("schedule"), dict) else {}
        kind = str(sched.get("kind") or "")
        if kind == "at":
            continue  # one-shot: no cadence to over-fire
        declared = sched.get("expr")
        if not declared and isinstance(sched.get("everyMs"), (int, float)):
            declared = "%ds" % max(1, int(sched["everyMs"] / 1000))
        name = str(j.get("name") or j.get("id") or "<cron>")
        key = str(j.get("id") or name)
        state = j.get("state") if isinstance(j.get("state"), dict) else {}
        marker = None
        for fld in _CRON_LAST_RUN_FIELDS:
            if state.get(fld) is not None:
                marker = str(state[fld])
                break
        rec = hist.get(key) if isinstance(hist.get(key), dict) else {}
        fires = [t for t in rec.get("fires", []) if isinstance(t, str) and t >= cutoff]
        if marker is not None and rec.get("marker") is not None \
                and marker != rec.get("marker"):
            fires.append(now.replace(microsecond=0).isoformat())
        hist[key] = {"marker": marker if marker is not None else rec.get("marker"),
                     "fires": fires}
        delivery = j.get("delivery") if isinstance(j.get("delivery"), dict) else {}
        entry = {"name": name, "declared_schedule": declared,
                 "actual_fires_per_day": len(fires) if fires else None,
                 "announce": delivery.get("mode") == "announce"}
        if sm:
            entry["actual_fires_per_day"] = None  # D4 over-fire stays silent
            entry["scheduler_managed"] = sm
            managed.append({"name": name, "reason": sm})
        out.append(entry)
    if led is not None:
        led.set_meta("d4_cron_fires", json.dumps(hist, sort_keys=True))
    return out


def _proc_up(pattern):
    """pgrep-based process presence: 'up' / 'down' / 'unknown' (a probe we cannot
    run is 'unknown', never a guessed 'down' - Skill 60's conservative probe law)."""
    if _probes_off():
        return "unknown"
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True,
                           text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return "up"
        if r.returncode == 1:
            return "down"
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _listener_pid_on(port):
    """First pid LISTENing on TCP :port via `lsof -t`, or None on any miss."""
    if _probes_off():
        return None
    try:
        r = subprocess.run(["lsof", "-nP", "-t", "-iTCP:%d" % int(port),
                            "-sTCP:LISTEN"], capture_output=True, text=True,
                           timeout=10)
        pids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        return pids[0] if pids else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _pid_alive(pid):
    """True when `pid` is a live process. Signal 0 only: nothing is sent."""
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, not ours
    except (OSError, ValueError, TypeError):
        return False


_GATEWAY_LAUNCHD_LABEL = "ai.openclaw.gateway"
_GATEWAY_SYSTEMD_UNIT = "openclaw-gateway.service"


def _supervisor_pid(listener_note=None):
    """(pid|None, why) - the pid the GATEWAY'S OWN SUPERVISOR says it is running,
    gathered ENVIRONMENT-FREE. `why` names the source or the reason it is unreadable.

      Mac            `launchctl list` TABLE (PID, Status, Label), label
                     `ai.openclaw.gateway`. NEVER `launchctl print` (it dumps the
                     service environment).
      Linux systemd  `systemctl --user show -p MainPID <unit>` (a single property).
      inside docker  no host-supervisor view exists: UNDETERMINED.

    None is UNDETERMINED - the caller raises NOTHING on it. A launchd label that is
    loaded but has no live pid ('-') is also None: there is no live supervisor pid
    to compare against."""
    if _probes_off():
        return None, "probes-off"
    plat = _platform()
    if plat == "darwin":
        out, st = _launchctl_list_text()
        if out is None:
            return None, "launchctl list %s" % st
        table = _parse_launchctl_table(out)
        if table is None:
            return None, "launchctl list header is not PID/Status/Label"
        if _GATEWAY_LAUNCHD_LABEL not in table:
            return None, "label %s not loaded" % _GATEWAY_LAUNCHD_LABEL
        pid = table[_GATEWAY_LAUNCHD_LABEL]
        return (pid, "launchd") if pid else (None, "label loaded, no live pid")
    if _in_container():
        return None, "inside a container: no host supervisor view"
    from shutil import which
    sc = os.environ.get("LOOP_SYSTEMCTL_BIN") or which("systemctl")
    if not sc:
        return None, "no supervisor binary (systemctl) on this host"
    unit = os.environ.get("LOOP_GATEWAY_SYSTEMD_UNIT") or _GATEWAY_SYSTEMD_UNIT
    out, st = _run_text([sc, "--user", "show", "-p", "MainPID", unit], timeout=10)
    if out is None:
        return None, "systemctl show %s" % st
    m = re.search(r"^MainPID=(\d+)\s*$", out, re.M)
    if not m or int(m.group(1)) <= 0:
        return None, "systemd reports no MainPID"
    return int(m.group(1)), "systemd"


def collect_wedge(led=None, slice_stats=None, gateway_up=None,
                  supervisor_pid=C.MISSING, listener_pid=C.MISSING, notes=None,
                  pid_alive=None):
    """D4 wedge evidence. Two probes, both fail-soft:

    (1) hung-but-alive: the no-progress counter increments ONLY when the slice
        shows DEMAND (agent.run.started) with ZERO completions (agent.run.finished)
        while the gateway process is up; any completion (or a down gateway) resets
        it; a fully idle box HOLDS it - idleness is never a wedge (no false P1
        every quiet night). Persisted in ledger meta 'd4_no_progress_ticks'; with
        led=None nothing is persisted.
    (2) orphan listener: the :18789 listener pid compared with the pid the
        gateway's SUPERVISOR reports (launchd / systemd), never with a handoff
        file. Reported ONLY when BOTH pids are known, they DIFFER, and the
        supervisor pid is ALIVE. Anything unreadable is UNDETERMINED and raises
        nothing.

        The legacy gateway-supervisor-restart-handoff.json is IGNORED (never read,
        never deleted). October keeps the handoff in SQLite, so a leftover July file
        carried a pid of a long-dead process; comparing it with the live listener
        raised a false top-priority LP-B3 every 15 minutes - and the prepared fix
        for LP-B3 (kill the listener) would have killed the healthy gateway itself.
        Kill-list semantics stay D4's: the finding names only the listener, and the
        supervisor's own pid can never be the one named.

    `gateway_up`/`supervisor_pid`/`listener_pid` are injectable for offline tests."""
    notes = notes if notes is not None else []
    pid_alive = pid_alive or _pid_alive
    th = C.load_skill_config("thresholds.json")["d4_timer_refire"]
    wedge = {}
    st = slice_stats or {}
    if gateway_up is None:
        gateway_up = _proc_up("openclaw")
    ticks = 0
    if led is not None:
        try:
            ticks = int(led.get_meta("d4_no_progress_ticks", "0") or 0)
        except (TypeError, ValueError):
            ticks = 0
    if int(st.get("completions", 0) or 0) > 0 or gateway_up == "down":
        ticks = 0
    elif int(st.get("starts", 0) or 0) > 0 and gateway_up == "up":
        ticks += 1
    # else: no demand observed - hold the counter (an idle box is not a wedge)
    if led is not None:
        led.set_meta("d4_no_progress_ticks", ticks)
    if ticks:
        wedge["gateway_healthy_no_progress_ticks"] = ticks

    if supervisor_pid is C.MISSING:
        supervisor_pid, why = _supervisor_pid()
    else:
        why = "injected"
    if listener_pid is C.MISSING:
        listener_pid = _listener_pid_on(th["gateway_port"])
    try:
        sup = int(supervisor_pid) if supervisor_pid is not None else None
        lp = int(listener_pid) if listener_pid is not None else None
    except (TypeError, ValueError):
        sup = lp = None
    if sup is None:
        if why not in ("probes-off",):
            notes.append("D4: gateway supervisor pid unreadable (%s) - orphan-listener "
                         "check UNDETERMINED, nothing raised" % why)
    elif lp and lp != sup and pid_alive(sup):
        wedge["orphan_listener_pid"] = lp
        wedge["supervisor_pid"] = sup
    return wedge


def _session_files(max_files=40, root=None):
    """Live session TRANSCRIPTS (not trajectories) under <openclaw_root>/agents/
    */sessions/*.jsonl, newest first, bounded. The transcript is the file the model
    re-reads as its own history, which is why D5 measures THIS and not the
    trajectory (the trajectory is telemetry the model never sees). [] on any miss.

    TWO exclusions, and the second one is load-bearing:
      *.trajectory.jsonl   telemetry, not history - never D5's subject.
      *<ARCHIVE_MARKER>*   a transcript LF-10 has ALREADY rolled. An archive keeps
                           the wreckage verbatim and keeps the original mtime, so it
                           re-measures as poisoned AND idle on the very next tick.
                           Left in scope it is re-archived every tick forever - each
                           roll appending another marker to the name until the
                           component passes 255 bytes and the move raises
                           ENAMETOOLONG, killing the scheduled job (reproduced: 7
                           rolls, crash on the 8th). The healer self-breaker cannot
                           catch it either, because the unit name is derived from
                           the FILENAME and so changes on every roll. An archive is
                           finished work: out of scope, permanently. D-POISON-REROLL
                           is the drill that holds this line."""
    try:
        files = glob.glob(str((root or openclaw_root()) / "agents" / "*" / "sessions"
                              / "*.jsonl"))
    except OSError:
        return []
    import time
    scored = []
    for f in files:
        if f.endswith(".trajectory.jsonl"):
            continue
        if KC.ARCHIVE_MARKER in os.path.basename(f):
            continue  # already rolled: finished work, never re-rolled
        try:
            scored.append((os.path.getmtime(f), f))
        except OSError:
            continue
    scored.sort(reverse=True)
    now = time.time()
    return [(f, (now - mt) / 60.0) for mt, f in scored[:max_files]]


def _blocked_tool_of(row):
    """The blocked tool NAME when `row` is a runtime tool-loop refusal, else None.
    STRUCTURAL match on two enum fields (details.status=='blocked' and
    details.deniedReason=='tool-loop') - never on the human-readable `reason`, so
    it survives wording changes and carries no message content into a finding."""
    if row.get("type") != "message":
        return None
    m = row.get("message")
    if not isinstance(m, dict) or m.get("role") != "toolResult":
        return None
    d = m.get("details")
    if not isinstance(d, dict):
        return None
    if str(d.get("status")) == "blocked" and str(d.get("deniedReason")) == "tool-loop":
        return str(m.get("toolName") or "<tool>")
    return None


def collect_sessions(files=None, thresholds=None, signatures=None):
    """D5 evidence: one measurement per session transcript, from a BOUNDED TAIL.

    The tail is the right window on purpose. D5's alarming faces both live at the
    end of a transcript - the current burst, and the trailing-window share - and a
    tail keeps the tick CPU-cheap on a box holding thousands of sessions. It also
    covered every poisoned compaction checkpoint in the archived incident (the
    deepest sat 1,617,348 bytes from the end, inside the 2,000,000-byte bound).

    Returns [] when no transcript stream exists (a probe miss is DATA). No message
    content is retained: counts, enum values, and tool NAMES only."""
    t = (thresholds or C.load_skill_config("thresholds.json"))["d5_transcript_poison"]
    sig = signatures if signatures is not None else C.load_signatures()
    blk = sig.get("tool_loop_block") if isinstance(sig, dict) else {}
    marker = (blk or {}).get("checkpoint_text_marker") or ""
    if files is None:
        files = _session_files(max_files=int(t["max_session_files"]))
    window = int(t["window_records"])
    gap = int(t["gap_records"])
    out = []
    for entry in files:
        path, idle_minutes = entry if isinstance(entry, (tuple, list)) else (entry, None)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        blocked = 0
        tools = set()
        bursts = []
        cur = 0
        since = 0
        trail = []
        records = 0
        cp_rows = 0
        cp_poisoned = 0
        for row in _iter_jsonl_tail(path, int(t["tail_bytes"])):
            if not isinstance(row, dict):
                continue
            if row.get("type") == "compaction":
                summary = row.get("summary")
                if isinstance(summary, str):
                    cp_rows += 1
                    if marker and marker in summary:
                        cp_poisoned += 1
                continue
            if row.get("type") != "message":
                continue
            records += 1
            tool = _blocked_tool_of(row)
            if tool is not None:
                blocked += 1
                tools.add(tool)
                if cur and since > gap:
                    bursts.append(cur)
                    cur = 0
                cur += 1
                since = 0
            else:
                since += 1
            trail.append(1 if tool is not None else 0)
            if len(trail) > window:
                trail.pop(0)
        if cur:
            bursts.append(cur)
        # Denominator FLOORS at the window size so a 4-record transcript with 3
        # blocks cannot report a 75% share. Short transcripts are caught by the
        # ignition face (max_burst), never by an inflated ratio.
        ratio = sum(trail) / float(max(len(trail), window)) if trail else 0.0
        out.append({"unit": "session:%s" % os.path.basename(path),
                    "path": path, "bytes": size, "tail_records": records,
                    "blocked_records": blocked, "max_burst": max(bursts) if bursts else 0,
                    "trailing_ratio": round(ratio, 4),
                    "blocked_tools": sorted(tools),
                    "checkpoint_rows": cp_rows, "poisoned_checkpoints": cp_poisoned,
                    "idle_minutes": idle_minutes})
    return out


def _tool_result_of(row):
    """(toolName, ts, is_error, payload_text) for a tool-result record, else None.

    `payload_text` is handed back ONLY so the caller can COUNT fail-closed markers
    in it. It is never stored, never returned in a burst measurement, and never
    reaches a finding - see collect_bursts()."""
    if row.get("type") != "message":
        return None
    m = row.get("message")
    if not isinstance(m, dict) or m.get("role") != "toolResult":
        return None
    name = m.get("toolName")
    if not isinstance(name, str) or not name:
        return None
    ts = _parse_ts(m.get("timestamp")) or _parse_ts(row.get("timestamp")) \
        or _parse_ts(row.get("ts"))
    err = m.get("isError") is True
    d = m.get("details")
    if not err and isinstance(d, dict):
        err = str(d.get("status") or "").lower() in ("error", "failed", "blocked", "denied")
    content = m.get("content")
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                for k in ("text", "output", "content"):
                    v = b.get(k)
                    if isinstance(v, str):
                        parts.append(v)
        text = "\n".join(parts)
    elif isinstance(content, dict):
        for k in ("text", "output"):
            v = content.get(k)
            if isinstance(v, str):
                text = v
                break
    return (name, ts, err, text)


_ERROR_SHAPE_CACHE = {}


def _error_shape_res(patterns):
    """Compile the pinned error_shape_patterns ONCE per distinct pattern set.

    The set comes from signatures.json (DATA, not code) but is compiled here and
    memoised at module level, so a 15-minute tick scanning thousands of results
    pays the compile cost once rather than per record. A pattern that fails to
    compile is SKIPPED, never raised: a typo in pinned config must not be able to
    take the watchdog down - a slightly weaker detector is recoverable, a dead
    watchdog on a looping box is not."""
    key = tuple(patterns)
    got = _ERROR_SHAPE_CACHE.get(key)
    if got is None:
        got = []
        for p in key:
            try:
                got.append(re.compile(p, re.IGNORECASE | re.MULTILINE))
            except re.error:
                continue
        _ERROR_SHAPE_CACHE[key] = got
    return got


def collect_bursts(files=None, thresholds=None, signatures=None):
    """D6 evidence: per (transcript, tool), the heaviest sliding window of calls.

    Reads the SAME bounded transcript tails D5 already reads, so D6 adds a pass
    over data the tick is holding anyway rather than a new probe surface.

    For each tool name it slides a `window_seconds` window over that tool's call
    timestamps and keeps the window with the most calls, recording alongside it how
    many of those calls FAILED at the tool layer and how many carried a FAIL-CLOSED
    dependency marker in their result payload.

    ⛔ ONLY COUNTS LEAVE THIS FUNCTION. Tool arguments are never read at all - that
    is the whole design, since arguments are exactly what a rewording agent varies
    to defeat every other guard. The result payload is scanned for marker presence
    and then DISCARDED: no matched text, no surrounding payload, no value of any
    kind enters a burst measurement, so a finding cannot leak a secret that
    happened to sit next to an auth error.

    v0.6.4 - FAIL-CLOSED IS NOW A TWO-LAYER TEST, because a bare marker match was
    scoring an agent that merely READ a document about authorization as an agent
    being REFUSED (benign `ls`/`find`/`cat` over one playbook directory escalated
    on a live box):
      L1  a tool in `result_scan_exempt_tools` is skipped for marker scanning,
          because its result IS retrieved content by construction. It still counts
          toward calls and errors, so read-tool bursts are fully preserved.
      L2  everything else needs marker AND (tool-layer failure OR a structural
          `error_shape_patterns` match) - a JSON error key, an HTTP 4xx status
          line, a CLI failure prefix. Prose cannot forge any of those.
    Both layers use ONLY the tool NAME and the RESULT text, both already in scope.
    CLASSIFYING BY COMMAND LINE IS FORBIDDEN HERE and always will be - reading the
    arguments to decide whether a `cat` is benign would break the law three
    paragraphs up, which is the one guarantee this function actually sells.
    Threshold behaviour is UNCHANGED: this is per-call precision, not a new
    trigger. See signatures.json for the measured evidence and the known residual.

    Records with no parseable timestamp are counted toward the tool's total but
    cannot be placed in a window; a transcript where NO record has a timestamp
    therefore yields no burst rather than a false one. A probe miss is DATA."""
    th = thresholds or C.load_skill_config("thresholds.json")
    t = th["d6_futile_retry_burst"]
    d5t = th["d5_transcript_poison"]
    sig = signatures if signatures is not None else C.load_signatures()
    fcm = sig.get("fail_closed_markers") if isinstance(sig, dict) else {}
    markers = [str(x).lower() for x in ((fcm or {}).get("markers") or [])]
    # v0.6.4 two-layer fail-closed classification (see signatures.json for the
    # measured evidence behind both layers).
    exempt = {str(x) for x in ((fcm or {}).get("result_scan_exempt_tools") or [])}
    shapes = _error_shape_res((fcm or {}).get("error_shape_patterns") or [])
    if files is None:
        files = _session_files(max_files=int(d5t["max_session_files"]))
    window = float(t["window_seconds"])
    out = []
    for entry in files:
        path = entry[0] if isinstance(entry, (tuple, list)) else entry
        per = {}
        for row in _iter_jsonl_tail(path, int(d5t["tail_bytes"])):
            if not isinstance(row, dict):
                continue
            hit = _tool_result_of(row)
            if hit is None:
                continue
            name, ts, err, text = hit
            if ts is None:
                continue
            low = text.lower() if text else ""
            if name in exempt:
                # L1. This tool's result IS retrieved CONTENT (file bytes, a stored
                # memory, a tool catalog entry), so a marker in it describes the
                # DOCUMENT, not this call's outcome. Exempt from marker scanning
                # ONLY - the call still lands in `per` below and still counts
                # toward calls and errors, so D6 bursts on read tools are intact.
                failclosed = False
            else:
                # L2. A marker proves the WORD is present; it never proved THIS
                # call was refused. Require the result to have failed at the tool
                # layer, or to be shaped like an error at all. Prose cannot forge
                # a quoted JSON key, an HTTP status line, or a CLI failure prefix,
                # which is exactly what separates a playbook that DISCUSSES
                # authorization from an API that REFUSED one.
                markers_hit = bool(low) and any(mk in low for mk in markers)
                failclosed = bool(markers_hit and
                                  (err or any(r.search(text) for r in shapes)))
            per.setdefault(name, []).append((ts.timestamp(), err, failclosed))
        for name, seq in per.items():
            seq.sort()
            best = None
            i = 0
            for j in range(len(seq)):
                while seq[j][0] - seq[i][0] > window:
                    i += 1
                calls = j - i + 1
                if best is None or calls > best[0]:
                    errs = 0
                    fcs = 0
                    for k in range(i, j + 1):
                        if seq[k][1]:
                            errs += 1
                        if seq[k][2]:
                            fcs += 1
                    best = (calls, errs, fcs, seq[j][0] - seq[i][0])
            if not best:
                continue
            # Nothing futile in the heaviest window -> contribute no measurement at
            # all. The detector's SILENCE RULE would drop it anyway; dropping it
            # here keeps the evidence dict small on a busy box.
            if best[1] <= 0 and best[2] <= 0:
                continue
            out.append({"unit": "session:%s" % os.path.basename(path),
                        "path": path, "tool": name, "calls": best[0],
                        "errors": best[1], "failclosed": best[2],
                        "span_seconds": round(best[3], 1)})
    return out


# --------------------------------------------------------------------------- #
# D7 - cross-run resend (provenance-stamped): the 2026-08-04 incident feed.
# Reads AGENT SESSION transcripts (agents/*/sessions/*.jsonl), a DIFFERENT
# stream from the *.trajectory.jsonl event log D1-D4 read - every inbound
# cross-agent delivery the gateway makes is stamped THERE as
# message.provenance, regardless of what the sending side logged (a resend is a
# brand-new top-level run at the sender, so nothing the sender wrote survives
# the resend boundary; only the RECEIVING side's transcript does).
# --------------------------------------------------------------------------- #
def _session_jsonl_files(max_files=40, max_age_hours=2.0):
    """Newest AGENT session transcripts under <openclaw_root>/agents/*/sessions/
    *.jsonl - explicitly EXCLUDING *.trajectory.jsonl (a `*.jsonl` glob also
    matches that suffix), bounded by recent mtime so D7 stays cheap enough for a
    60s cadence even though it currently rides the same 15-minute tick as D1-D4
    (no separate cron/pulse-lane is added by this change - see CHANGELOG.md).
    [] when the stream does not exist (a probe miss is data, never a crash)."""
    try:
        files = glob.glob(str(openclaw_root() / "agents" / "*" / "sessions" / "*.jsonl"))
    except OSError:
        return []
    files = [f for f in files if not f.endswith(".trajectory.jsonl")]
    import time
    now = time.time()
    scored = []
    for f in files:
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        if now - mt <= max_age_hours * 3600.0:
            scored.append((mt, f))
    scored.sort(reverse=True)
    return [f for _, f in scored[:max_files]]


def _read_new_session_rows(led=None, max_files=40, max_bytes=1_000_000):
    """The NEW-bytes-since-last-tick slice of every recent session transcript -
    D7's evidence source. A SEPARATE offset namespace ('loop-sess:<path>') from
    D3's ('loop-traj:<path>'), so the two streams never share or clobber a
    cursor even when a future schema places both under the same directory. Same
    line-boundary-safe, rotation-safe, bounded-tail-on-first-sight shape as
    _read_new_trajectory_rows. With led=None (the read-only audit path) this
    PEEKS the bounded tail and advances nothing."""
    rows = []
    for f in _session_jsonl_files(max_files=max_files):
        key = "loop-sess:%s" % f
        try:
            size = os.path.getsize(f)
        except OSError:
            continue
        fresh_cut = False
        off = led.get_offset(key) if led is not None else 0
        if off > size:
            off = 0  # rotated/truncated: start over
        if off == 0 and size > max_bytes:
            off = size - max_bytes  # not a line boundary: drop the first line below
            fresh_cut = True
        try:
            with open(f, "rb") as fh:
                fh.seek(off)
                chunk = fh.read(max_bytes)
        except OSError:
            continue
        end = chunk.rfind(b"\n")
        if end < 0:
            continue  # no complete line yet; do not advance, wait for more bytes
        lines = chunk[:end].split(b"\n")
        if fresh_cut and lines:
            lines = lines[1:]  # partial first line from a mid-file cut
        new_off = off + end + 1
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            row["_file"] = f
            rows.append(row)
        if led is not None:
            led.set_offset(key, new_off)
    return rows


# Candidate paths to the fields D7 reads off one session-transcript row.
# CONFIRMED live-box row shape (OpenClaw 2026.7.1-2, verified 2026-08-04 -
# real captured sample, not a guess):
#   row keys:     {type, id, parentId, timestamp, message}
#   message keys: {role, content, timestamp, provenance}
#   message.provenance = {kind:"inter_session", sourceSessionKey:"...",
#                          sourceTool:"sessions_send", [sourceChannel:"..."]}
#   message.role == "user" on a qualifying inbound row
# The CONFIRMED path is listed FIRST in every tuple below; the remaining
# candidates are defensive fallbacks for a differently-enveloped row, same
# posture as every other plausible-schema constant in this file
# (_CRON_LAST_RUN_FIELDS, _USAGE_TOTAL_FIELDS) - never a requirement.
#
# `sourceChannel` is OPTIONAL on the confirmed shape (present on one live
# sample, absent on another) and is DELIBERATELY never read or required below
# - its absence must never cause a miss.
#
# There is no confirmed per-run identifier field on this row shape (no
# `runId`); the row's own `id` (confirmed present on every row) is used
# instead - each inbound provenance-stamped delivery is exactly one row, so
# its own id already uniquely identifies that one resend instance, which is
# exactly what D7's "distinct run ids in the window" count needs.
# `runId`/`run_id` are tried first only in case a future or differently-
# enveloped row attaches one directly.
#
# The confirmed top-level row shape carries no `sessionKey`/`sessionId`
# either; TARGET falls through to the transcript's own file path (below),
# which already uniquely identifies the RECEIVING agent+session.
_PROVENANCE_PATHS = ("message.provenance", "provenance", "data.provenance")
_PAYLOAD_PATHS = ("message.content", "message.body", "message.text",
                  "content", "body", "text",
                  "data.content", "data.body", "data.text")
_SESSION_TARGET_FIELDS = ("sessionKey", "sessionId")
_TIMESTAMP_PATHS = ("timestamp", "ts", "message.timestamp")
_RUN_ID_PATHS = ("runId", "run_id", "id")
_ROLE_PATHS = ("message.role", "role")


def _first_present(row, dotted_paths):
    """The first non-missing, non-None value among `dotted_paths` on `row` (dot-
    path lookup via loop_common.dotpath_get). None when every candidate misses -
    never a crash, never a guess."""
    for path in dotted_paths:
        v = C.dotpath_get(row, path)
        if v is not C.MISSING and v is not None:
            return v
    return None


def collect_cross_run_sends(led=None):
    """D7 evidence: one entry per inbound provenance-stamped cross-agent message
    seen in the new-bytes-since-last-tick slice of every recent session
    transcript - {source, target, hash, run_id, ts}. Only rows whose provenance
    carries sourceTool == 'sessions_send' count (kind, when present, must be
    'inter_session' - any other kind is a different delivery path and is
    skipped, never guessed at); a role that is present and NOT 'user' is also
    skipped (the confirmed shape's qualifying rows are role='user' - an
    additional, non-fatal tightening: a MISSING role never excludes a row).
    The payload is hashed via C.cross_run_payload_hash and the raw text is
    NEVER assigned anywhere but the argument to that one call - it is not
    placed in the returned dict, not logged, and never reaches the ledger or
    a finding detail (a session transcript can carry a live client credential
    pasted mid-conversation - SKILL.md doctrine 3)."""
    rows = _read_new_session_rows(led)
    out = []
    for row in rows:
        prov = _first_present(row, _PROVENANCE_PATHS)
        if not isinstance(prov, dict):
            continue
        if str(prov.get("sourceTool") or "") != "sessions_send":
            continue
        kind = prov.get("kind")
        if kind is not None and str(kind) != "inter_session":
            continue
        role = _first_present(row, _ROLE_PATHS)
        if role is not None and str(role) != "user":
            continue
        source = prov.get("sourceSessionKey") or prov.get("sourceSession") \
            or prov.get("source")
        if not source:
            continue
        target = _first_present(row, _SESSION_TARGET_FIELDS) or row.get("_file")
        payload = _first_present(row, _PAYLOAD_PATHS)
        if payload is None:
            continue
        out.append({"source": str(source), "target": str(target),
                    "hash": C.cross_run_payload_hash(source, target, payload),
                    "run_id": str(_first_present(row, _RUN_ID_PATHS) or ""),
                    "ts": str(_first_present(row, _TIMESTAMP_PATHS) or "")})
    return out


def collect_evidence(led=None, runner=None, now=None):
    """Assemble the evidence dict from the box, best-effort. Detectors run over
    whatever is available; a missing source contributes no findings, never an
    error - but it is NEVER silent about it: every miss is named in
    evidence["undetermined"], and a collector that came back EMPTY while the box
    was demonstrably active is named in evidence["blind"] and becomes a P2
    finding ("watchdog blind: <collector>").

    Sources (Fix 1 - the October rebuild):
      D1  collect_units()               `pm2 list` table, `launchctl list` table,
                                        `docker inspect -f` (all environment-free)
      D2  collect_session_windows()     `openclaw sessions --all-agents --active 1440
                                        --json` token DELTAS
      D3  audit_evidence() runs         `openclaw audit --kind agent_run` finished
                                        runs + their tool sequences
      D4  collect_crons() / collect_wedge()   `openclaw cron list --json`; the
                                        supervisor pid (launchd/systemd), not a file
      D5  audit_evidence() sessions     `tool_action status=blocked` bursts per runId
      D6  audit_evidence() bursts       failed tool actions per (session, tool) in
                                        60-second windows (FAILING-BURST face only)
      D7  collect_cross_run_sends()     UNDETERMINED here: no content-free October
                                        source carries message provenance. The
                                        loop-brake plugin covers it in real time.

    With a Ledger (the tick path) the audit cursors persist under
    `loop-audit:<kind>` in the offsets table and the D1/D2/D4 baselines persist in
    meta. With led=None (the read-only audit path): nothing is persisted and no
    cursor advances. `runner(args, timeout=...)` is the injectable seam for the two
    openclaw feeds, so every drill runs offline over fixtures."""
    cfg = _feed_cfg()
    now = now or datetime.now(timezone.utc)
    notes = []
    managed = []

    sess = fetch_sessions(cfg["sessions_active_minutes"], runner, cfg)
    run_f = fetch_audit("agent_run", led, now, runner, cfg)
    tool_f = fetch_audit("tool_action", led, now, runner, cfg)
    for label, fx in (("sessions", sess), ("audit agent_run", run_f),
                      ("audit tool_action", tool_f)):
        if fx["status"] not in ("ok", "probes-off"):
            notes.append("feed `%s` unreadable (%s) - the detectors it feeds are "
                         "UNDETERMINED this run, NOT healthy" % (label, fx["status"]))
        if fx.get("partial"):
            notes.append("feed `%s` has more pages than the per-run budget - older new "
                         "records were NOT seen (UNDETERMINED for them)" % label)
    if sess["status"] == "ok" and sess["partial"]:
        notes.append("feed `sessions` reported hasMore - sessions beyond the first page "
                     "were NOT seen (UNDETERMINED for them)")

    active_now = active_session_count(sess["rows"], cfg["blind_control_active_minutes"], now) \
        if sess["rows"] is not None else None
    blind = blind_collectors(sess, run_f, active_now)

    sess_stats = {}
    windows = collect_session_windows(sess["rows"], led, now, notes=notes,
                                      stats=sess_stats) if sess["rows"] is not None else []
    audit = audit_evidence(run_f["events"], tool_f["events"])
    crons = collect_crons(led, notes=notes, managed=managed, runner=runner)
    wedge = collect_wedge(led, audit["stats"], notes=notes)
    notes.append("D7: no content-free October source carries inter-session provenance - "
                 "UNDETERMINED (the loop-brake plugin is the real-time cover)")
    return {"units": collect_units(led, notes=notes, now=now),
            "windows": windows,
            "runs": audit["runs"],
            "crons": crons,
            "wedge": wedge,
            "sessions": audit["sessions"],
            "bursts": audit["bursts"],
            "sends": [],
            "blind": blind,
            "undetermined": notes,
            "scheduler_managed": managed}


def self_test():
    import tempfile
    print("[loop_watchdog] self-test: DRY_RUN records+plans-nothing, armed-parks, "
          "escalate offline, escalation gate (dedup + refusal backoff)")

    storm = {"units": [{"name": "cc-app", "delta": 12, "day_restarts": 900}],
             "windows": [], "runs": [], "crons": [], "wedge": {}}

    def dead_tx(url, body):
        raise OSError("offline self-test: no network")

    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
        led = Ledger()
        # DRY_RUN (armed False): the storm is a P1 finding, RECORDED, but nothing applied.
        s = tick(storm, led, armed=False, escalate_transport=dead_tx, box="box-example")
        assert s["findings"] == 1 and s["applied"] == 0 and s["planned"] == 1
        assert s["by_class"].get("LP-B1") == 1
        assert len(led.open_findings("LP-B1")) == 1
        assert led.list_fixes() == []  # DRY_RUN mutated nothing
        print("  DRY_RUN case: PASS (P1 recorded; zero fixes applied; observe-only)")

        # A working box produces zero findings (no noise).
        s2 = tick({"units": [{"name": "gw", "delta": 0}]}, led, armed=False, box="box-example")
        assert s2["findings"] == 0 and s2["alerts"] == 0
        print("  quiet case: PASS (no findings, no alerts on a healthy box)")

        # ---- LIVENESS, PROVED ON THE CASE THE OLD METRIC GETS WRONG --------
        # The tick above found NOTHING. That is precisely the box a
        # MAX(findings.tick_ts) proxy declares unwatched. Both halves are
        # asserted: last_tick_ts advanced, AND the old proxy did not - so this
        # case fails the moment someone moves the stamp inside the findings path.
        live_before = led.get_meta("last_tick_ts")
        assert live_before, "a completed tick did not write last_tick_ts"
        assert led.get_meta("last_tick_findings") == "0", led.get_meta("last_tick_findings")
        max_finding_ts = led.conn.execute(
            "SELECT MAX(tick_ts) AS m FROM findings").fetchone()["m"]
        # Second-precision timestamps cannot prove "advanced" inside one second, so
        # the stamp is backdated to 2000 first: EVERY tick must overwrite it, not
        # just the first one that happened to find the key missing.
        led.set_meta("last_tick_ts", "2000-01-01T00:00:00+00:00")
        s2b = tick({"units": [{"name": "gw", "delta": 0}]}, led, armed=False, box="box-example")
        assert s2b["findings"] == 0
        assert led.get_meta("last_tick_ts") != "2000-01-01T00:00:00+00:00", \
            "a zero-findings tick did not REWRITE last_tick_ts"
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(led.get_meta("last_tick_ts"))).total_seconds()
        assert 0 <= age < 120, "last_tick_ts is not fresh (age=%ss)" % age
        max_finding_ts2 = led.conn.execute(
            "SELECT MAX(tick_ts) AS m FROM findings").fetchone()["m"]
        assert max_finding_ts2 == max_finding_ts, \
            "the control moved: this fixture no longer isolates liveness from findings"
        assert led.get_meta("last_tick_mode") in (None, "live", "dry-run")
        print("  liveness case: PASS (a tick that finds NOTHING still stamps "
              "last_tick_ts=%s findings=0, while MAX(findings.tick_ts) stays "
              "frozen at %r - the exact split that produced the false "
              "'6 boxes unwatched' report)"
              % (led.get_meta("last_tick_ts"), max_finding_ts))

        # Tier-3 class escalates offline (UNSENT fallback), never tight-loops.
        empty = {"units": [], "crons": [{"name": "noop", "declared_schedule": "@daily",
                 "actual_fires_per_day": 300}], "windows": [], "runs": [], "wedge": {}}
        s3 = tick(empty, led, armed=True, escalate_transport=dead_tx, box="box-example")
        assert s3["findings"] >= 1
        print("  escalate case: PASS (offline escalation via UNSENT fallback, no crash)")

        # THE DRAIN ENABLE GATE. This is the path every box takes on every tick,
        # and getting it wrong once already saturated the shared intake, so it is
        # asserted, not assumed. ESC.drain is replaced by a recorder: if the gate
        # leaks, the recorder fires and the assertion names it - no network is
        # involved either way. Evidence is quiet, so no finding escalates and the
        # real ESC.send is never reached even with escalate_transport=None.
        _quiet = {"units": [{"name": "gw", "delta": 0}], "windows": [], "runs": [],
                  "crons": [], "wedge": {}}
        _drain_calls = []
        _real_drain = ESC.drain
        ESC.drain = lambda *a, **k: (_drain_calls.append(1) or {"posted": 0})
        try:
            # (a) env ABSENT -> DISARMED. The default state of every box.
            os.environ.pop("RESCUE_RANGERS_DRAIN_ENABLE", None)
            sg = tick(_quiet, led, armed=False, escalate_transport=None, box="box-example")
            assert not _drain_calls, "DISARMED tick still ran the drain"
            assert sg["drain"]["skipped"] == "DISARMED RR-DRAIN-DISARMED-20260826", sg["drain"]
            assert sg["drain"]["rearm"] == "RESCUE_RANGERS_DRAIN_ENABLE=1", sg["drain"]

            # (b) a value that is not exactly "1" is NOT an enable
            for _almost in ("0", "true", "yes", "", "1 ", "ENABLE"):
                os.environ["RESCUE_RANGERS_DRAIN_ENABLE"] = _almost
                tick(_quiet, led, armed=False, escalate_transport=None, box="box-example")
                assert not _drain_calls, "%r was treated as an enable" % _almost

            # (c) an injected transport NEVER drains, even when armed
            os.environ["RESCUE_RANGERS_DRAIN_ENABLE"] = "1"
            tick(_quiet, led, armed=False, escalate_transport=dead_tx, box="box-example")
            assert not _drain_calls, "an injected transport drained"

            # (d) explicit enable + real delivery path -> the drain DOES run,
            #     because a safety that can never be lifted is not a safety.
            sg2 = tick(_quiet, led, armed=False, escalate_transport=None, box="box-example")
            assert _drain_calls == [1], "explicit enable did not run the drain"
            assert sg2["drain"] == {"posted": 0}, sg2["drain"]
        finally:
            ESC.drain = _real_drain
            os.environ.pop("RESCUE_RANGERS_DRAIN_ENABLE", None)
        print("  drain-gate case: PASS (absent env DISARMS and is recorded in the tick; "
              "near-miss values are not enables; injected transport never drains; "
              "an explicit =1 re-arms)")

        led.close()
        os.environ.pop("LOOP_STATE_DIR", None)

    # ---- THE ESCALATION GATE (RR-ESC-GATE-20260826) --------------------------
    # This path runs on every tick of every box. Ungated it produced 992
    # escalations from ONE dedup_key on a live box, against an intake whose rate
    # limit is GLOBAL across the fleet - so one box's runaway key sheds OTHER
    # clients' live escalations. Asserted in BOTH directions: the repeat must be
    # HELD, and a NEW key must be delivered on the very tick the old one is
    # still held. Proving only the holding direction is how a noisy system gets
    # quietly turned into a silent one, which is the worse failure by far.
    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
        led = Ledger()
        _b = {"units": [], "windows": [], "runs": [], "wedge": {}}
        _cron = lambda n: {"name": n, "declared_schedule": "@daily",
                           "actual_fires_per_day": 300}
        _hits = []

        def _tx_ok(url, body):
            _hits.append(json.loads(body.decode("utf-8"))["machine"]["finding_id"])
            return True

        def _tx_refuse(url, body):
            _hits.append("refused")
            raise RuntimeError("intake HTTP 429 (self-test): refused")

        e1 = tick(dict(_b, crons=[_cron("esc-1")]), led, armed=True,
                  escalate_transport=_tx_ok, box="box-example")
        assert e1["escalated"] == 1 and e1["escalation_suppressed"] == 0, e1
        # the SAME key on the next tick is held, and never reaches the transport
        e2 = tick(dict(_b, crons=[_cron("esc-1")]), led, armed=True,
                  escalate_transport=_tx_ok, box="box-example")
        assert e2["escalated"] == 0 and e2["escalation_unsent"] == 0, e2
        assert e2["escalation_suppressed"] == 1, e2
        assert e2["escalation_suppressed_by"] == {"dedup": 1}, e2
        assert len(_hits) == 1, "a deduped key reached the transport"
        # a NEW key is delivered on the SAME tick the old one stays held
        e3 = tick(dict(_b, crons=[_cron("esc-1"), _cron("esc-2")]), led, armed=True,
                  escalate_transport=_tx_ok, box="box-example")
        assert e3["escalated"] == 1 and e3["escalation_suppressed"] == 1, e3
        assert len(_hits) == 2, "a NEW dedup_key was suppressed - that is silent loss"
        # a REFUSAL backs the key off instead of re-posting it next tick, and
        # writes NO digest: an attempt that silences its own retry is silent loss.
        e4 = tick(dict(_b, crons=[_cron("esc-3")]), led, armed=True,
                  escalate_transport=_tx_refuse, box="box-example")
        assert e4["escalation_unsent"] == 1 and e4["escalated"] == 0, e4
        _bo = led.get_backoff(ESCALATION_BACKOFF_PREFIX + "LP-A4|esc-3")
        assert _bo and _bo["attempt"] == 1 and _bo["next_at"], _bo
        assert led.recent_digest(ESCALATION_DIGEST_PREFIX + "LP-A4|esc-3", 24) is None
        # and the refused finding is left OPEN, never marked escalated
        _open = {r["dedup_key"] for r in led.open_findings()}
        assert "LP-A4|esc-3" in _open, _open
        led.close()
        os.environ.pop("LOOP_STATE_DIR", None)
    print("  escalation-gate case: PASS (a repeat is HELD and never reaches the "
          "transport; a NEW dedup_key is delivered on that same tick; a refusal "
          "backs off, writes no digest, and leaves the finding open)")

    # ---- the collect layer: a synthetic loop trajectory yields REAL evidence --
    # Regression case for the Star incident: the old collect_evidence() STUB
    # returned {"windows": [], "runs": [], "crons": [], "wedge": {}} so D2/D3/D4
    # analyzed NOTHING even fully armed. This proves a loop on disk becomes
    # findings, hermetically (LOOP_NO_PROBES=1: zero subprocess, zero network).
    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
        os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
        os.environ[_PROBES_OFF_ENV] = "1"
        sess_dir = Path(td) / "openclaw" / "agents" / "main" / "sessions"
        sess_dir.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        t0 = (now - timedelta(minutes=90)).replace(microsecond=0)
        rows = [{"type": "session.started", "ts": t0.isoformat(), "sessionId": "s1",
                 "sessionKey": "agent:main:main", "runId": "r0",
                 "modelId": "z-ai/glm-5.3", "provider": "openrouter",
                 "data": {"trigger": "cron"}}]
        for i in range(12):  # 12 identical SUCCESSFUL runs, 300k paid tokens each
            common = {"ts": (t0 + timedelta(minutes=2 * i)).isoformat(),
                      "sessionId": "s1", "sessionKey": "agent:main:main",
                      "runId": "r%d" % (i + 1), "seq": i,
                      "modelId": "z-ai/glm-5.3", "provider": "openrouter"}
            rows.append(dict(common, type="model.completed",
                             data={"usage": {"input": 250000, "output": 50000,
                                             "total": 300000}}))
            rows.append(dict(common, type="trace.artifacts",
                             data={"finalStatus": "success",
                                   "usage": {"total": 300000},
                                   "toolMetas": [{"toolName": "exec"},
                                                 {"toolName": "message"}]}))
        (sess_dir / "s1.trajectory.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        led = Ledger()
        ev = _legacy_file_evidence(led)  # the LEGACY file reader, kept for these drills
        assert ev["windows"], "collect_windows EMPTY over a real trajectory stream"
        assert any(w["paid_tokens"] > 0 for w in ev["windows"])  # D2 sees usage now
        assert all(w["initiated_sessions"] == 0 for w in ev["windows"])  # cron != human
        okr = [r for r in ev["runs"] if r["error_class"] == "OK"]
        assert len(okr) >= 12 and okr[0]["tool_sequence"] == ["exec", "message"]
        thr = C.load_skill_config("thresholds.json")
        fnd = run_detectors(ev, thr, C.load_signatures())
        assert any(f["loop_class"] == "LP-A2" and f["severity"] == "P1"
                   for f in fnd), "D2 must flag the idle paid burn"
        assert any(f["detector"] == "D3" and f["severity"] == "P1"
                   for f in fnd), "D3 must flag the repeated identical SUCCESSFUL turn"
        ev2 = _legacy_file_evidence(led)
        assert ev2["runs"] == []  # the slice was offset-consumed
        print("  legacy-file collect case: PASS (the preserved file reader still feeds the "
              "D2/D3 arithmetic: synthetic loop -> windows/runs; D2+D3 fire; slice "
              "offset-consumed). NOT wired into the tick any more.")

        # _usage_total multi-candidate hardening (0.3.1): the source-confirmed
        # `usage.total` first, then defensive aliases, then the component-sum
        # fallback (== the writer's own derivedTotal), and fail-soft everywhere.
        assert _usage_total({"usage": {"total": 300000}}) == 300000        # confirmed
        assert _usage_total({"usage": {"totalTokens": 300000}}) == 300000  # camel alias
        assert _usage_total({"usage": {"total_tokens": 500000}}) == 500000  # raw alias
        assert _usage_total({"usage": {"input": 250000, "output": 50000,
                                       "cacheRead": 0}}) == 300000          # derivedTotal
        assert _usage_total({"usage": {}}) is None and _usage_total({}) is None
        assert _usage_total({"usage": {"total": True}}) is None  # a bool is never a count
        print("  usage-field case: PASS (multi-candidate total -> totalTokens -> "
              "total_tokens -> component-sum; fail-soft; source-confirmed usage.total)")

        # within-run cumulative DELTA end to end (the synthetic-loop case above uses
        # a DISTINCT runId per completion, so this is the ONLY proof of the delta
        # path): ONE runId whose cumulative usage rises 100k -> 800k, carried as
        # component buckets only, is charged as the 800k telescoping delta - never
        # the 3.6M naive sum - which also exercises the derivedTotal fallback.
        _saved_root = os.environ.get("LOOP_OPENCLAW_ROOT")
        with tempfile.TemporaryDirectory() as td2:
            os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td2, "openclaw")
            sdir = Path(td2) / "openclaw" / "agents" / "main" / "sessions"
            sdir.mkdir(parents=True)
            base = (datetime.now(timezone.utc) - timedelta(minutes=60)).replace(microsecond=0)
            drows = [{"type": "model.completed",
                      "ts": (base + timedelta(minutes=i + 1)).isoformat(),
                      "sessionKey": "agent:main:main", "runId": "rDELTA", "seq": i,
                      "modelId": "z-ai/glm-5.3", "provider": "openrouter",
                      "data": {"usage": {"input": 100000 * (i + 1)}}} for i in range(8)]
            (sdir / "sD.trajectory.jsonl").write_text(
                "\n".join(json.dumps(r) for r in drows) + "\n", encoding="utf-8")
            charged = sum(w["paid_tokens"] for w in collect_windows())
        if _saved_root is not None:
            os.environ["LOOP_OPENCLAW_ROOT"] = _saved_root
        assert charged == 800000, "within-run delta must charge 800k, got %d" % charged
        print("  within-run-delta case: PASS (single-run 100k->800k charges the 800k "
              "delta, not the 3.6M naive sum)")

        # crons: observed-fire counting via last-run marker transitions
        jobs_fx = [{"id": "j1", "name": "resume", "enabled": True,
                    "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                    "state": {"lastRunAtMs": 1000}, "delivery": {"mode": "none"}}]
        c1 = collect_crons(led, jobs=jobs_fx)
        assert c1[0]["declared_schedule"] == "0 9 * * *"
        assert c1[0]["actual_fires_per_day"] is None  # first sight: never a guess
        jobs_fx[0]["state"]["lastRunAtMs"] = 2000
        c2 = collect_crons(led, jobs=jobs_fx)
        jobs_fx[0]["state"]["lastRunAtMs"] = 3000
        c3 = collect_crons(led, jobs=jobs_fx)
        assert c2[0]["actual_fires_per_day"] == 1 and c3[0]["actual_fires_per_day"] == 2
        print("  collect-crons case: PASS (marker transitions counted, persisted, "
              "first-sight None)")

        # wedge: demand-without-progress counts; progress resets; idle holds.
        w1 = collect_wedge(led, {"starts": 2, "completions": 0}, gateway_up="up",
                           supervisor_pid=None)
        collect_wedge(led, {"starts": 1, "completions": 0}, gateway_up="up",
                      supervisor_pid=None)
        w3 = collect_wedge(led, {"starts": 3, "completions": 0}, gateway_up="up",
                           supervisor_pid=None)
        assert w1["gateway_healthy_no_progress_ticks"] == 1
        assert w3["gateway_healthy_no_progress_ticks"] == 3  # D4 P1 threshold
        wr = collect_wedge(led, {"starts": 0, "completions": 4}, gateway_up="up",
                           supervisor_pid=None)
        assert "gateway_healthy_no_progress_ticks" not in wr  # progress resets
        # ORPHAN LISTENER (Fix 2): the listener pid is compared with the pid the
        # SUPERVISOR reports - never with a handoff file. Three cases, all offline.
        _alive = lambda pid: pid in (222, 111)
        n_eq = []
        w_eq = collect_wedge(led, {}, gateway_up="up", supervisor_pid=111,
                             listener_pid=111, notes=n_eq, pid_alive=_alive)
        assert "orphan_listener_pid" not in w_eq and not n_eq   # equal: silent
        w_df = collect_wedge(led, {}, gateway_up="up", supervisor_pid=222,
                             listener_pid=111, pid_alive=_alive)
        assert w_df["orphan_listener_pid"] == 111 and w_df["supervisor_pid"] == 222
        n_un = []
        w_un = collect_wedge(led, {}, gateway_up="up", supervisor_pid=None,
                             listener_pid=111, notes=n_un, pid_alive=_alive)
        assert "orphan_listener_pid" not in w_un                  # unreadable: silent...
        assert n_un and "UNDETERMINED" in n_un[0]                 # ...but NAMED, never zero
        w_dead = collect_wedge(led, {}, gateway_up="up", supervisor_pid=999,
                               listener_pid=111, pid_alive=_alive)
        assert "orphan_listener_pid" not in w_dead  # a dead supervisor pid is no evidence
        print("  collect-wedge case: PASS (demand-gated counter; reset on progress; orphan "
              "= listener != LIVE supervisor pid only; equal silent; unreadable silent "
              "AND named UNDETERMINED; dead supervisor pid silent)")

        # D7 collect case: a provenance-stamped AGENT SESSION transcript (a
        # SEPARATE file in the SAME sessions dir - never the *.trajectory.jsonl
        # stream above), shaped EXACTLY like the CONFIRMED live-box row (OpenClaw
        # 2026.7.1-2, verified 2026-08-04): top-level {type, id, parentId,
        # timestamp, message}; message {role, content, timestamp, provenance} -
        # carrying 3 resends of the SAME inter-session message
        # (message.provenance.sourceTool == 'sessions_send', role='user') ~34s
        # apart (the incident's own cadence fingerprint; timestamps use the
        # CONFIRMED `timestamp` field, never the old guessed `ts`; run identity
        # comes from the row's own `id` - there is no `runId` on the real
        # shape). ONE resend row carries `sourceChannel` (optional, per the
        # live sample), the other two omit it entirely - both must match
        # (absence must never cause a miss). An assistant REPLY row (no
        # provenance at all) and a role='assistant' row that carries
        # provenance anyway (a malformed-shape probe) must both be excluded.
        # The raw payload text must NEVER survive into the evidence dict, the
        # ledger, or a finding detail (only its hash may).
        base = t0 + timedelta(hours=1)
        raw_payload = "please pick up ticket 4471 and reply when the queue clears"

        def _resend_row(row_id, parent_id, dt, with_channel):
            stamp = (base + timedelta(seconds=dt)).isoformat()
            prov = {"kind": "inter_session", "sourceSessionKey": "agent:orch:main",
                    "sourceTool": "sessions_send"}
            if with_channel:
                prov["sourceChannel"] = "telegram"
            return {"type": "message", "id": row_id, "parentId": parent_id,
                    "timestamp": stamp,
                    "message": {"role": "user", "content": raw_payload,
                               "timestamp": stamp, "provenance": prov}}

        resend_rows = [
            _resend_row("msg-r0", None, 0, with_channel=True),
            _resend_row("msg-r1", "msg-r0", 34, with_channel=False),
            _resend_row("msg-r2", "msg-r1", 68, with_channel=False),
            {"type": "message", "id": "msg-r2-reply", "parentId": "msg-r2",
             "timestamp": (base + timedelta(seconds=69)).isoformat(),
             "message": {"role": "assistant", "content": "on it",
                        "timestamp": (base + timedelta(seconds=69)).isoformat()}},
            {"type": "message", "id": "msg-bad-role", "parentId": None,
             "timestamp": (base + timedelta(seconds=200)).isoformat(),
             "message": {"role": "assistant", "content": raw_payload,
                        "timestamp": (base + timedelta(seconds=200)).isoformat(),
                        "provenance": {"kind": "inter_session",
                                      "sourceSessionKey": "agent:orch:main",
                                      "sourceTool": "sessions_send"}}},
        ]
        (sess_dir / "dept-target.jsonl").write_text(
            "\n".join(json.dumps(r) for r in resend_rows) + "\n", encoding="utf-8")
        sends = collect_cross_run_sends(led)
        assert len(sends) == 3, "expected exactly 3 - the reply and bad-role rows must be excluded"
        assert all(s["source"] == "agent:orch:main" for s in sends)
        assert {s["run_id"] for s in sends} == {"msg-r0", "msg-r1", "msg-r2"}, \
            "run identity must come from the row's own id (no runId on the confirmed shape)"
        assert not any(raw_payload in json.dumps(s) for s in sends), \
            "the raw message body must NEVER survive into D7 evidence"
        f7 = run_detectors({"sends": sends}, C.load_skill_config("thresholds.json"),
                           C.load_signatures())
        assert any(x["severity"] == "P1" and x["loop_class"] == "LP-A10" for x in f7)
        assert not any(raw_payload in json.dumps(x) for x in f7)
        sends2 = collect_cross_run_sends(led)
        assert sends2 == []  # the slice was offset-consumed
        print("  D7 collect case: PASS (3 confirmed-shape resends -> real evidence "
              "-> P1 LP-A10; sourceChannel present-or-absent both match; reply + "
              "bad-role rows excluded; raw payload never in evidence or a "
              "finding; slice offset-consumed)")

        led.close()
        for k in ("LOOP_STATE_DIR", "LOOP_OPENCLAW_ROOT", _PROBES_OFF_ENV):
            os.environ.pop(k, None)

    # ---- D5 collect_sessions: the STOCK reader, both directions ---------------
    # The point of D5 is that a paused loop leaves a transcript that is still
    # poisoned, so this must fire on wreckage that is no longer moving AND stay
    # silent on a LARGER clean transcript. Both fixtures are synthetic.
    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
        os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
        os.environ[_PROBES_OFF_ENV] = "1"
        sdir = Path(td) / "openclaw" / "agents" / "main" / "sessions"
        sdir.mkdir(parents=True)
        import shutil as _sh
        for name in ("loop-blocked-session.jsonl", "healthy-session.jsonl"):
            _sh.copy2(str(fixtures / name), str(sdir / name))
        thr = C.load_skill_config("thresholds.json")
        sess = collect_sessions()
        by = {os.path.basename(s["path"]): s for s in sess}
        bad = by["loop-blocked-session.jsonl"]
        good = by["healthy-session.jsonl"]
        assert bad["blocked_records"] == 60 and bad["max_burst"] == 60
        assert bad["poisoned_checkpoints"] == 1 and bad["blocked_tools"] == ["read"]
        # THE CONTROL: bigger file, more records, more checkpoints, ZERO blocks.
        assert good["blocked_records"] == 0 and good["max_burst"] == 0
        assert good["poisoned_checkpoints"] == 0
        assert good["bytes"] > bad["bytes"] and good["tail_records"] > bad["tail_records"]
        f5 = D.d5_transcript_poison(sess, thr)
        assert len(f5) == 1, "D5 must flag exactly ONE transcript, got %d" % len(f5)
        assert f5[0]["severity"] == "P1" and f5[0]["loop_class"] == "LP-A8"
        assert "loop-blocked-session.jsonl" in f5[0]["evidence_path"]
        print("  D5 collect case: PASS (poisoned transcript=P1 LP-A8 incl. the "
              "checkpoint carrier; LARGER clean transcript SILENT)")

        # SKS-008: with the shipped config LF-10 is Tier 2 (sessions.reset proposal), so
        # an ARMED tick must only PREPARE it and never move a transcript file.
        led = Ledger()
        _t0 = __import__("time").time() - 3600
        for _n in ("loop-blocked-session.jsonl", "healthy-session.jsonl"):
            os.utime(str(sdir / _n), (_t0, _t0))
        s_t2 = tick({"units": [], "windows": [], "runs": [], "crons": [], "wedge": {},
                     "sessions": collect_sessions()}, led, armed=True, box="box-example")
        led.close()
        assert s_t2["applied"] == 0 and s_t2["planned"] >= 1, s_t2
        assert (sdir / "loop-blocked-session.jsonl").is_file()
        print("  LF-10 tier-2 case: PASS (armed tick PREPARES sessions.reset, moves no file)")
        # The cases below keep covering the retained legacy file-move executor and the
        # D5 re-roll/containment guards, pinned to a TEST-LOCAL Tier-1 view of LF-10.
        _orig_fcf = KC.fix_class_for

        def _lf10_tier1_for_legacy_tests(loop_class):
            fc = _orig_fcf(loop_class)
            return dict(fc, tier=1) if fc and fc.get("id") == "LF-10" else fc
        KC.fix_class_for = _lf10_tier1_for_legacy_tests

        # An ARMED tick archives the poisoned transcript (move, never delete) and
        # leaves the clean one untouched; DRY_RUN mutates nothing.
        led = Ledger()
        ev_dry = {"units": [], "windows": [], "runs": [], "crons": [], "wedge": {},
                  "sessions": collect_sessions()}
        tick(ev_dry, led, armed=False, box="box-example")
        assert (sdir / "loop-blocked-session.jsonl").is_file()  # DRY_RUN: untouched
        # age both transcripts past the live-session guard, then arm
        import time as _t
        past = _t.time() - 3600
        for name in ("loop-blocked-session.jsonl", "healthy-session.jsonl"):
            os.utime(str(sdir / name), (past, past))
        ev = {"units": [], "windows": [], "runs": [], "crons": [], "wedge": {},
              "sessions": collect_sessions()}
        s5 = tick(ev, led, armed=True, box="box-example")
        assert s5["applied"] == 1, "armed tick must archive exactly one transcript"
        assert not (sdir / "loop-blocked-session.jsonl").exists()
        arch = list(sdir.glob("loop-blocked-session.loop-archive-*.jsonl"))
        assert len(arch) == 1 and arch[0].stat().st_size > 0  # MOVED, not deleted
        assert (sdir / "healthy-session.jsonl").is_file()      # control untouched
        led.close()
        print("  D5 roll case: PASS (DRY_RUN untouched; armed MOVES the poisoned "
              "transcript to an archive, never deletes; clean transcript untouched)")

        # The live-session guard: a transcript still being written is REFUSED.
        # NOTE: copy2 preserves the SOURCE mtime, which would make this fixture
        # look stale as soon as the repo checkout aged past roll_min_idle_minutes -
        # a time-dependent test that passes on a fresh clone and fails later. Stamp
        # the mtime to NOW so "live" means live at RUN time, always.
        _sh.copy2(str(fixtures / "loop-blocked-session.jsonl"),
                  str(sdir / "live-session.jsonl"))
        os.utime(str(sdir / "live-session.jsonl"), None)
        led = Ledger()
        ev_live = {"units": [], "windows": [], "runs": [], "crons": [], "wedge": {},
                   "sessions": [s for s in collect_sessions()
                                if s["path"].endswith("live-session.jsonl")]}
        s6 = tick(ev_live, led, armed=True, box="box-example")
        assert s6["findings"] == 1 and s6["applied"] == 0
        assert (sdir / "live-session.jsonl").is_file()
        led.close()
        print("  D5 live-guard case: PASS (a transcript still being written is "
              "REFUSED even when armed; the P1 still lands)")

        # D5 RE-ROLL guard: the archive LF-10 just wrote must leave D5's scope for
        # good. It is a *.jsonl in the same directory, shutil.move preserved its
        # mtime, and its bytes are the same wreckage - so left in scope it re-measured
        # as poisoned AND idle every tick and got archived again, growing the filename
        # by one marker per tick until the move raised ENAMETOOLONG and killed the
        # tick outright (measured: crash on the 8th roll). The healer self-breaker
        # could not catch it: D5's unit is derived from the FILENAME, which changed on
        # every roll. Repeated ticks must now archive EXACTLY once and go silent.
        led = Ledger()
        rolls = 0
        found = 0
        for _ in range(10):
            older = _t.time() - 3600
            for _f in sdir.iterdir():
                os.utime(str(_f), (older, older))
            s_rr = tick({"units": [], "windows": [], "runs": [], "crons": [],
                         "wedge": {}, "sessions": collect_sessions()},
                        led, armed=True, box="box-example")
            rolls += s_rr["applied"]
            found += s_rr["findings"]
        led.close()
        rolled = sorted(p.name for p in sdir.iterdir() if KC.ARCHIVE_MARKER in p.name)
        assert rolls == 1, "10 ticks must roll ONE transcript once, applied %d" % rolls
        # FINDINGS is the assertion that catches the collector regression alone: with
        # the archive back in scope the kill card's own guard still refuses the second
        # roll (applied stays 1 and the defect hides), but a re-measured archive raises
        # a fresh P1 every single tick.
        assert found == 1, "a rolled archive must never be re-found, got %d" % found
        assert all(n.count(KC.ARCHIVE_MARKER) == 1 for n in rolled), rolled
        assert all(len(p.name.encode("utf-8")) <= 255 for p in sdir.iterdir())
        print("  D5 re-roll case: PASS (10 armed ticks archive the poisoned transcript "
              "EXACTLY once, one finding total; an archive leaves D5 scope for good)")

        # TICK CONTAINMENT: one bad finding must never kill the tick. Injected at the
        # kill-card seam, with the RAISING transcript first, so a tick that aborts on
        # it can never reach the one behind it. An uncaught OSError here used to abort
        # the whole tick - in a scheduled job, a watchdog dying silently every run.
        for _f in sdir.iterdir():
            _f.unlink()
        for name in ("boom-session.jsonl", "good-session.jsonl"):
            _sh.copy2(str(fixtures / "loop-blocked-session.jsonl"), str(sdir / name))
            os.utime(str(sdir / name), (_t.time() - 3600,) * 2)
        _real_lf10 = KC.lf10_archive_and_roll_session

        def _selective(session_path, *a, **k):
            if "boom-session" in str(session_path):
                raise OSError(63, "File name too long (injected)")
            return _real_lf10(session_path, *a, **k)
        KC.lf10_archive_and_roll_session = _selective
        try:
            led = Ledger()
            ordered = sorted(collect_sessions(),
                             key=lambda m: 0 if "boom-session" in m["path"] else 1)
            sc = tick({"units": [], "windows": [], "runs": [], "crons": [],
                       "wedge": {}, "sessions": ordered}, led, armed=True,
                      box="box-example")
            led.close()
        finally:
            KC.lf10_archive_and_roll_session = _real_lf10
        assert "boom-session" in ordered[0]["path"]
        assert sc["findings"] == 2 and sc["errors"] == 1 and sc["applied"] == 1
        assert (sdir / "boom-session.jsonl").is_file()      # left exactly as found
        assert not (sdir / "good-session.jsonl").exists()   # the one behind it ran
        print("  tick-containment case: PASS (an exception escaping a kill card is "
              "counted in errors and the tick still processes the finding behind it)")
        KC.fix_class_for = _orig_fcf   # end of the legacy Tier-1 pin

        # D1 restart BASELINE: pm2 reports a unit's LIFETIME restart count, so the
        # first sight of any long-lived unit must read as delta 0, never as a storm.
        # Without this, the first tick on a real box invents a P1 for every unit
        # that has ever restarted - and on an armed box, parks it.
        led = Ledger()
        jl = [{"name": "long-lived", "pid": 1, "pm2_env": {"status": "online",
                                                           "restart_time": 28}}]
        u1 = collect_units(led, recs=jl)
        assert u1[0]["delta"] == 0, "first sight must be 0, got %s" % u1[0]["delta"]
        assert not D.d1_restart_velocity(u1, thr)      # and therefore SILENT
        jl[0]["pm2_env"]["restart_time"] = 40          # +12 since last tick
        u2 = collect_units(led, recs=jl)
        assert u2[0]["delta"] == 12
        assert any(x["severity"] == "P1" for x in D.d1_restart_velocity(u2, thr))
        jl[0]["pm2_env"]["restart_time"] = 2           # counter reset -> re-baseline
        assert collect_units(led, recs=jl)[0]["delta"] == 0
        led.close()
        print("  D1 baseline case: PASS (first sight=0 not a false storm; real "
              "delta=12 still P1; a reset counter re-baselines instead of spiking)")
        for k in ("LOOP_STATE_DIR", "LOOP_OPENCLAW_ROOT", _PROBES_OFF_ENV):
            os.environ.pop(k, None)

    # ---- D6 FAIL-CLOSED DISCRIMINATION (v0.6.4) ----------------------------
    # A bare marker match scored an agent that READ a document mentioning
    # authorization as an agent that was REFUSED. Benign ls/find/cat over one
    # playbook directory holding 5 marker-bearing files escalated on a live box.
    # Asserted in BOTH directions on the SAME tool name, because the only thing
    # easier than shipping a false positive is "fixing" it into a false negative.
    print("[loop_watchdog] self-test: D6 fail-closed discrimination (v0.6.4)")
    sig = C.load_signatures()
    thr6 = C.load_skill_config("thresholds.json")

    def _burst_fixture(td, tool, texts, name="s.jsonl"):
        """Write N marker-bearing results 10s apart, PLUS one genuinely errored
        result with benign text. The error record keeps the measurement alive past
        collect_bursts' silence rule, so `calls` and `errors` can be asserted even
        when failclosed is correctly 0 - that is how "still counted" is PROVEN
        rather than assumed."""
        p = os.path.join(td, name)
        base = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
        with open(p, "w", encoding="utf-8") as fh:
            for i, t in enumerate(list(texts) + ["ordinary output, nothing notable"]):
                fh.write(json.dumps({
                    "type": "message",
                    "message": {"role": "toolResult", "toolName": tool,
                                "timestamp": (base + timedelta(seconds=10 * i)).isoformat(),
                                "isError": i == len(texts),
                                "details": {"status": "completed"},
                                "content": t}}) + "\n")
        return p

    def _measure(path):
        out = collect_bursts(files=[path], thresholds=thr6, signatures=sig)
        assert len(out) == 1, out
        return out[0]

    def _old_rule_fcs(texts):
        """The PRE-0.6.4 rule, replayed on the same fixture text. Its answer is
        what makes each fixture a DISCRIMINATOR rather than a fixture that would
        pass either way - if this ever equals the new answer, the test proves
        nothing and must be rewritten."""
        mk = [str(x).lower() for x in sig["fail_closed_markers"]["markers"]]
        return sum(1 for t in texts if any(m in t.lower() for m in mk))

    with tempfile.TemporaryDirectory() as td:
        # 1. THE REPRO. Shell tool, exit 0, payload is playbook PROSE that DISCUSSES
        #    authorization. Note the third paragraph carries the bare word "error"
        #    in prose on purpose: the rejected proximity-window design would have
        #    scored it fail-closed, so this fixture is also that design's headstone.
        prose = [
            "Step 4. If the portal returns unauthorized, the agent should stop and "
            "hand the account back to the operator rather than retrying.",
            "Access tiers: a buyer record is forbidden to junior staff and visible "
            "to the listing owner only. Escalate exceptions to the broker.",
            "Troubleshooting. A common error: unauthorized access to the vault "
            "usually means the seat was never provisioned. Authentication failed "
            "messages in the console are expected during onboarding.",
        ]
        b1 = _measure(_burst_fixture(td, "exec", prose, "repro.jsonl"))
        assert b1["failclosed"] == 0, b1
        assert b1["calls"] == 4 and b1["errors"] == 1, b1
        assert _old_rule_fcs(prose) == 3, "fixture 1 no longer discriminates"
        print("  repro case: PASS (3 shell reads of marker-bearing PROSE in 60s -> "
              "failclosed=0 where the old rule gave 3; calls=4/errors=1 still "
              "counted; the 'common error:' paragraph proves the rejected "
              "proximity window would have failed here)")

        # 2. GENUINE REFUSAL, same tool, same exit-0 status. This is the direction
        #    that guards against over-pruning: the whole point of D6 is the call
        #    that SUCCEEDS while the dependency behind it refuses.
        refusal = ['{"error":{"type":"authentication_error","message":'
                   '"invalid_api_key: the supplied key is not valid"}}'] * 3
        b2 = _measure(_burst_fixture(td, "exec", refusal, "refusal.jsonl"))
        assert b2["failclosed"] == 3, b2
        assert b2["calls"] == 4 and b2["errors"] == 1, b2
        assert _old_rule_fcs(refusal) == 3
        print("  genuine-refusal case: PASS (same tool, same exit-0 status, "
              "structured auth error -> failclosed=3 KEPT; L2 prunes prose "
              "without pruning real refusals)")

        # 3. READ-TOOL EXEMPTION, proven INDEPENDENT of L2: the payload is verbatim
        #    raw error JSON, which satisfies L2 outright. Only the tool-name
        #    exemption can bring this to zero.
        exempt_tool = sig["fail_closed_markers"]["result_scan_exempt_tools"][0]
        raw_err = ['{"error":{"code":403,"reason":"forbidden","message":'
                   '"unauthorized"}}'] * 3
        b3 = _measure(_burst_fixture(td, exempt_tool, raw_err, "readtool.jsonl"))
        assert b3["failclosed"] == 0, b3
        assert b3["calls"] == 4 and b3["errors"] == 1, b3
        assert _old_rule_fcs(raw_err) == 3
        # Same bytes through a NON-exempt tool must still fire - otherwise the
        # exemption is not what zeroed it and this case proves nothing.
        b3b = _measure(_burst_fixture(td, "exec", raw_err, "readtool_ctl.jsonl"))
        assert b3b["failclosed"] == 3, b3b
        print("  read-exemption case: PASS (tool %r carrying verbatim error JSON "
              "-> failclosed=0 while the IDENTICAL payload through `exec` still "
              "gives 3, so L1 is doing the work, not L2; calls/errors preserved)"
              % exempt_tool)

    print("[loop_watchdog] self-test: PASS")
    return 0


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection per-box watchdog tick.")
    ap.add_argument("cmd", nargs="?", default="tick", choices=["tick", "feed-health"])
    ap.add_argument("--no-send", action="store_true",
                    help="do not deliver alerts/escalations (still records findings)")
    # --no-send suppresses DELIVERY only; it does NOT make a tick observe-only. On an
    # ARMED box a --no-send tick still applies Tier-1 fixes for real. --dry-run is the
    # flag that forces armed=False regardless of ledger state, for a caller that must
    # be sure it mutates nothing outside our own ledger (install.sh's post-install
    # tick, which used to claim DRY_RUN while running armed on an armed box).
    ap.add_argument("--dry-run", action="store_true",
                    help="force observe-only (armed=false) whatever the ledger says: "
                         "record findings, plan fixes, apply NOTHING")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd == "feed-health":
        # READ-ONLY live control for verify.sh --live: opens NO ledger, advances NO
        # cursor, writes nothing. Exit 0 = healthy or genuinely idle, 4 = a collector
        # is BLIND, 3 = UNDETERMINED (a feed could not be read - never folded into 0).
        info = feed_health_check()
        print(json.dumps(info, sort_keys=True))
        return {"healthy": 0, "idle": 0, "blind": 4}.get(info["verdict"], 3)
    led = Ledger()
    try:
        box = led.get_meta("box", "box")
        evidence = collect_evidence(led)
        tx = (lambda url, body: True) if a.no_send else None
        summary = tick(evidence, led, armed=False if a.dry_run else None,
                       escalate_transport=tx, box=box)
        # Beside last_tick_ts, not inside it: freshness is the question, but an
        # operator reading a fresh stamp deserves to know whether it came from the
        # scheduled watchdog or from install.sh's forced observe-only tick.
        try:
            led.set_meta("last_tick_mode", "dry-run" if a.dry_run else "live")
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("ERROR [loop_watchdog]: could not write last_tick_mode "
                             "(%s: %s)\n" % (type(exc).__name__, exc))
        print(json.dumps(summary, sort_keys=True))
        return 0
    finally:
        led.close()


if __name__ == "__main__":
    sys.exit(_cli())
