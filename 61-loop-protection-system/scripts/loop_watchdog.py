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
    # point: it is the case the broken metric gets wrong.
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
    if result["status"] == "applied":
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
    if result.get("escalate"):
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


def collect_units(led=None, recs=None):
    """Best-effort pm2 jlist -> filtered units (name/status/pid/restarts ONLY). Returns
    [] on any miss (no pm2, not JSON, no git). NEVER dumps env. A probe miss is DATA.

    `delta` is restarts SINCE THE LAST TICK, baselined per unit in ledger meta.
    FIRST SIGHT OF A UNIT IS ALWAYS delta=0. This is load-bearing, not a nicety: pm2
    reports a unit's LIFETIME restart count, so treating that as a per-tick delta
    made the very first tick on any real box read a long-lived unit's whole history
    as one storm - an instant false P1, and on an armed box an instant false park.
    A baseline that only ever measures the gap between two observations cannot do
    that. A counter that goes BACKWARDS (pm2 resurrected/reset) re-baselines to 0
    rather than reporting a negative or a bogus spike. `recs` is injectable so the
    baseline logic is testable without pm2."""
    if recs is None:
        if _probes_off():
            return []
        try:
            out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True,
                                 timeout=5)
            recs = json.loads(out.stdout or "[]")
        except Exception:  # noqa: BLE001 - probe failure is data, never a crash
            return []
    seen = {}
    if led is not None:
        try:
            seen = json.loads(led.get_meta("d1_restart_baseline", "{}") or "{}")
        except (ValueError, TypeError):
            seen = {}
        if not isinstance(seen, dict):
            seen = {}
    units = []
    baseline = {}
    for rec in recs if isinstance(recs, list) else []:
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
        # first sight -> 0; a backwards counter -> 0 (re-baseline, never a spike)
        f["delta"] = max(0, total - prev) if prev is not None and total >= prev else 0
        baseline[name] = total
        units.append(f)
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


def _cron_jobs_via_cli(timeout=15):
    """Best-effort `openclaw cron list --json` -> jobs list. [] on ANY miss (no
    binary, non-zero exit, bad JSON) - a probe miss is DATA. Read-only command;
    the {jobs:[...]} / [...] output shape is the documented `cron list --json`
    contract, parsed defensively (either shape accepted); CONFIRM on the operator
    canary during burn-in."""
    if _probes_off():
        return []
    from shutil import which
    binpath = os.environ.get("OPENCLAW_BIN") or which("openclaw")
    if not binpath:
        return []
    try:
        proc = subprocess.run([binpath, "cron", "list", "--json"],
                              capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else data
    return jobs if isinstance(jobs, list) else []


def collect_crons(led=None, jobs=None, now=None):
    """D4 cron evidence: {name, declared_schedule, actual_fires_per_day, announce}
    per enabled recurring job. Fire counting is OBSERVED, not guessed: each tick
    the job's last-run marker (state.lastRunAtMs) is compared with the previous
    tick's (persisted in ledger meta 'd4_cron_fires', trailing 24h) and each
    transition counts one fire - a strict LOWER BOUND at the 15-minute cadence
    (max ~96 observations/day), which still catches any @daily job firing every
    few minutes. Until a fire has been observed actual_fires_per_day is None and
    D4's over-fire branch stays silent (never a false P1 on first tick). With
    led=None nothing is persisted. `jobs` is injectable for offline tests."""
    if jobs is None:
        jobs = _cron_jobs_via_cli()
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
        if not isinstance(j, dict) or j.get("enabled") is False:
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
        out.append({"name": name, "declared_schedule": declared,
                    "actual_fires_per_day": len(fires) if fires else None,
                    "announce": delivery.get("mode") == "announce"})
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


def _read_handoff():
    """The gateway supervisor restart-handoff marker (<openclaw_root>/
    gateway-supervisor-restart-handoff.json; expected keys include pid, createdAt,
    expiresAt - plausible candidates, CONFIRM on the operator canary during
    burn-in). None when absent/unreadable. Structural fields only; each key read
    defensively so a name miss degrades to "no orphan finding", never a wrong one."""
    p = openclaw_root() / "gateway-supervisor-restart-handoff.json"
    try:
        if not p.is_file():
            return None
        h = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(h, dict):
            h["_mtime"] = p.stat().st_mtime
            return h
    except (OSError, ValueError):
        pass
    return None


def _handoff_epoch(value):
    """createdAt/expiresAt -> aware datetime; accepts ISO strings or epoch ms."""
    if isinstance(value, str):
        return _parse_ts(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def collect_wedge(led=None, slice_stats=None, gateway_up=None,
                  handoff=C.MISSING, listener_pid=C.MISSING):
    """D4 wedge evidence. Two probes, both fail-soft:

    (1) hung-but-alive: the no-progress counter increments ONLY when the slice
        shows DEMAND (prompt.submitted / session.started) with ZERO completions
        while the gateway process is up; any completion (or a down gateway)
        resets it; a fully idle box HOLDS it - idleness is never a wedge (no
        false P1 every quiet night). Persisted in ledger meta
        'd4_no_progress_ticks'; with led=None nothing is persisted.
    (2) orphan listener: reported ONLY on a definitive supervisor claim - a
        restart-handoff file that is EXPIRED or >=1h old (a fresh handoff is a
        restart in progress, not an orphan) whose pid differs from the live
        listener on the gateway port. Kill-list semantics stay D4's: the finding
        names only the orphan.

    `gateway_up`/`handoff`/`listener_pid` are injectable for offline tests."""
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

    h = _read_handoff() if handoff is C.MISSING else handoff
    if isinstance(h, dict) and h.get("pid"):
        now = datetime.now(timezone.utc)
        created = _handoff_epoch(h.get("createdAt"))
        if created is None and h.get("_mtime"):
            try:
                created = datetime.fromtimestamp(float(h["_mtime"]), timezone.utc)
            except (OverflowError, OSError, ValueError):
                created = None
        age_h = (now - created).total_seconds() / 3600.0 if created else None
        expires = _handoff_epoch(h.get("expiresAt"))
        stale = (expires is not None and expires < now) or \
                (age_h is not None and age_h >= 1.0)
        if stale:
            lp = _listener_pid_on(th["gateway_port"]) \
                if listener_pid is C.MISSING else listener_pid
            try:
                sup = int(h["pid"])
            except (TypeError, ValueError):
                sup = None
            if lp and sup and int(lp) != sup:
                wedge["orphan_listener_pid"] = int(lp)
                wedge["supervisor_pid"] = sup
                if age_h is not None:
                    wedge["handoff_age_hours"] = round(age_h, 1)
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


def collect_evidence(led=None):
    """Assemble the evidence dict from the box, best-effort. Detectors run over
    whatever is available; a missing source contributes no findings, never an
    error. With a Ledger (the tick path): the D3/D7 slices are offset-tracked
    (separate namespaces) and the D4 counters persist. With led=None (the
    read-only audit path): bounded tail PEEK, nothing persisted, no offset
    advanced.

    D5 (transcript poison) attaches via collect_sessions() and is the one collector
    here that reads a STOCK rather than a flow, so it deliberately does NOT use the
    offset/slice pattern: re-measuring the same tail every tick is the point - the
    poison persists until something clears it. D6 (semantic retry burst) attaches
    via collect_bursts() over those SAME bounded tails, so it costs one extra pass
    rather than a new probe surface. D7 (cross-run resend) attaches via
    collect_cross_run_sends(), which DOES use the offset/slice pattern (a separate
    'loop-sess:<path>' namespace from D3's) since it is a FLOW over the same session
    transcripts D5/D6 read, not a stock. A completion-rate detector remains unbuilt
    (windows already carry per-hour `completions` for it)."""
    rows, slice_stats = _read_new_trajectory_rows(led)
    return {"units": collect_units(led),
            "windows": collect_windows(),
            "runs": collect_runs(rows),
            "crons": collect_crons(led),
            "wedge": collect_wedge(led, slice_stats),
            "sessions": collect_sessions(),
            "bursts": collect_bursts(),
            "sends": collect_cross_run_sends(led)}


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
                 "modelId": "minimax-m3:cloud", "provider": "ollama",
                 "data": {"trigger": "cron"}}]
        for i in range(12):  # 12 identical SUCCESSFUL runs, 300k paid tokens each
            common = {"ts": (t0 + timedelta(minutes=2 * i)).isoformat(),
                      "sessionId": "s1", "sessionKey": "agent:main:main",
                      "runId": "r%d" % (i + 1), "seq": i,
                      "modelId": "minimax-m3:cloud", "provider": "ollama"}
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
        ev = collect_evidence(led)
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
        ev2 = collect_evidence(led)
        assert ev2["runs"] == []  # the slice was offset-consumed
        print("  collect case: PASS (stub replaced: synthetic loop -> real windows/"
              "runs; D2+D3 fire; slice offset-consumed)")

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
                      "modelId": "minimax-m3:cloud", "provider": "ollama",
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

        # wedge: demand-without-progress counts; progress resets; idle holds;
        # a stale handoff + foreign listener = orphan; a fresh handoff never is.
        w1 = collect_wedge(led, {"starts": 2, "completions": 0}, gateway_up="up",
                           handoff=None)
        collect_wedge(led, {"starts": 1, "completions": 0}, gateway_up="up",
                      handoff=None)
        w3 = collect_wedge(led, {"starts": 3, "completions": 0}, gateway_up="up",
                           handoff=None)
        assert w1["gateway_healthy_no_progress_ticks"] == 1
        assert w3["gateway_healthy_no_progress_ticks"] == 3  # D4 P1 threshold
        wr = collect_wedge(led, {"starts": 0, "completions": 4}, gateway_up="up",
                           handoff=None)
        assert "gateway_healthy_no_progress_ticks" not in wr  # progress resets
        stale_handoff = {"pid": 222,
                         "createdAt": (now - timedelta(hours=30)).isoformat()}
        wo = collect_wedge(led, {}, gateway_up="up", handoff=stale_handoff,
                           listener_pid=111)
        assert wo["orphan_listener_pid"] == 111 and wo["supervisor_pid"] == 222
        fresh_handoff = {"pid": 222, "createdAt": now.isoformat()}
        wf = collect_wedge(led, {}, gateway_up="up", handoff=fresh_handoff,
                           listener_pid=111)
        assert "orphan_listener_pid" not in wf  # mid-restart is not an orphan
        print("  collect-wedge case: PASS (demand-gated counter; reset on progress; "
              "stale-handoff orphan only)")

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
    ap.add_argument("cmd", nargs="?", default="tick", choices=["tick"])
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
