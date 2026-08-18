#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_detectors.py
# The FOUR loop-specific detectors D1-D4 (spec Section 3). These are the
# detectors absent from Skill 60's S1-S10 catalog; they are proposed for
# registration as Skill 60 signals S11-S14 (Open Decision T2) so the fleet keeps
# ONE signal vocabulary.
#
#   D1  restart velocity          pm2 restarts / launchctl runs / docker RestartCount
#   D2  token-burn rate           trajectory usage lines, paid vs local, idle-correlated
#   D3  repeated-identical-signature  rolling hash over (err class + tool seq + target)
#   D4  timer re-fire storm / wedge   cron over-fire, hung-but-alive, orphan :18789
#
# EACH detector is a PURE function over PARSED evidence (dicts/lists), so it is
# fully testable against fixtures with NO box access, NO subprocess, NO network,
# NO model call. A separate `collect_*` layer (thin, best-effort) gathers the
# evidence on a real box and hands parsed structures to these functions.
#
# DOCTRINE: zero model calls; deterministic; process-manager evidence is already
# filtered to name/status/pid/restarts by loop_common.filter_pm2_record BEFORE it
# reaches D1 (never an env dump); a secret VALUE never enters a finding detail
# (D2/D3 carry counts, key paths, and CLASS only).
# =============================================================================
"""loop_detectors.py - deterministic D1-D4 loop detectors for the Loop Protection System."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402

# Severity constants (mirror the ledger vocabulary).
P1, P2, WARN = "P1", "P2", "WARN"


def _finding(loop_class, severity, unit, detail, detector, tier=None,
             evidence_path=None, dedup_key=None):
    return {"loop_class": loop_class, "severity": severity, "unit": unit,
            "detail": detail, "detector": detector, "tier": tier,
            "evidence_path": evidence_path,
            "dedup_key": dedup_key or "%s|%s" % (loop_class, unit or "-")}


# --------------------------------------------------------------------------- #
# D1 - restart velocity
# --------------------------------------------------------------------------- #
def d1_restart_velocity(units, thresholds, warn_streaks=None):
    """`units` = list of {name, status, pid, restarts, delta} dicts (ALREADY filtered
    to name/status/pid/restarts by loop_common.filter_pm2_record; `delta` = restarts
    since last tick, and `day_restarts` optional). `warn_streaks` = {unit: consecutive
    WARN ticks so far}. Returns findings. Maps to LP-B1/LP-B2 and feeds the process
    breaker (Section 5.1)."""
    t = thresholds["d1_restart_velocity"]
    warn_streaks = warn_streaks or {}
    out = []
    for u in units:
        name = u.get("name") or "<unnamed>"
        delta = int(u.get("delta", 0) or 0)
        day = int(u.get("day_restarts", delta) or 0)
        loop_class = "LP-B2" if u.get("is_watchdog") else "LP-B1"
        if delta >= t["p1_per_tick"] or day >= t["p1_per_day"]:
            out.append(_finding(loop_class, P1, name,
                       "restart velocity %d/tick (day %d) >= P1 (%d/tick or %d/day)"
                       % (delta, day, t["p1_per_tick"], t["p1_per_day"]),
                       "D1", tier=1))
        elif delta >= t["warn_per_tick"]:
            streak = warn_streaks.get(name, 0) + 1
            if streak >= t["warn_consecutive_ticks_to_p1"]:
                out.append(_finding(loop_class, P1, name,
                           "restart velocity at WARN for %d consecutive ticks (>= %d) -> P1"
                           % (streak, t["warn_consecutive_ticks_to_p1"]), "D1", tier=1))
            else:
                out.append(_finding(loop_class, WARN, name,
                           "restart velocity %d/tick >= WARN (%d); streak %d"
                           % (delta, t["warn_per_tick"], streak), "D1", tier=1))
    return out


# --------------------------------------------------------------------------- #
# D2 - token-burn rate
# --------------------------------------------------------------------------- #
def d2_token_burn_rate(windows, thresholds, signatures=None):
    """`windows` = list of {label, paid_tokens, local_tokens, initiated_sessions,
    idle_consecutive} for the last N idle windows. A window is IDLE when
    initiated_sessions == 0. Returns findings (LP-A2/A6/A7). Paid tokens burned in an
    idle window is the dollar class. No secret enters the detail; only token counts."""
    t = thresholds["d2_token_burn_rate"]
    sig = signatures if signatures is not None else C.load_signatures()  # noqa: F841
    out = []
    for w in windows:
        label = w.get("label", "window")
        paid = int(w.get("paid_tokens", 0) or 0)
        idle = int(w.get("initiated_sessions", 0) or 0) == 0
        if not idle:
            continue
        idle_streak = int(w.get("idle_consecutive", 1) or 1)
        per_hour = paid  # windows are 1h by config (idle_window_minutes=60)
        if per_hour > t["p1_tokens_per_hour"]:
            out.append(_finding("LP-A2", P1, label,
                       "idle-window paid burn %d tok/hr > P1 (%d) with zero initiated sessions"
                       % (per_hour, t["p1_tokens_per_hour"]), "D2", tier=2))
        elif per_hour > t["warn_tokens_per_hour"]:
            out.append(_finding("LP-A2", WARN, label,
                       "idle-window paid burn %d tok/hr > WARN (%d)"
                       % (per_hour, t["warn_tokens_per_hour"]), "D2", tier=2))
        elif paid > 0 and idle_streak >= t["idle_paid_windows_to_p1"]:
            out.append(_finding("LP-A2", P1, label,
                       "ANY paid turn in %d consecutive idle windows -> P1 idle-burn"
                       % idle_streak, "D2", tier=2))
    return out


# --------------------------------------------------------------------------- #
# D3 - repeated-identical-signature
# --------------------------------------------------------------------------- #
def d3_identical_signature(runs, thresholds):
    """`runs` = ordered list of {unit, error_class, tool_sequence, target} for the
    session/cron runs seen in the new-bytes-since-last-tick slice (offset-tracked).
    A run of >=warn_repeat consecutive identical signatures = WARN; >=p1_repeat = P1
    'loop confirmed' (LP-A1/A3/A4, LP-D2). The content-based generalization of
    loop-detector.sh's progress test.

    Signatures cover BOTH outcomes: error_class is a failure class OR "OK" for a
    SUCCESSFUL turn - repeated identical successful turns are a loop face too (the
    Star correction wave was 'successful' turns end to end; failure-only hashing is
    exactly why D3 stayed silent). Successful repeats use the HIGHER
    p1_repeat_success ceiling (default 2x p1_repeat) and never WARN, so legitimate
    cadences (a heartbeat succeeding once per tick slice) stay silent."""
    t = thresholds["d3_identical_signature"]
    p1_success = int(t.get("p1_repeat_success", 2 * int(t["p1_repeat"])))
    out = []
    # group consecutive-identical by (unit, signature_hash)
    prev_key = None
    streak = 0
    emitted = set()
    for r in runs:
        h = C.signature_hash(r.get("error_class"), r.get("tool_sequence"), r.get("target"))
        unit = r.get("unit") or "<unit>"
        key = (unit, h)
        if key == prev_key:
            streak += 1
        else:
            prev_key = key
            streak = 1
        loop_class = r.get("loop_class", "LP-A4")
        ok_run = str(r.get("error_class") or "").upper() == "OK"
        p1_at = p1_success if ok_run else t["p1_repeat"]
        outcome = "successful-turn" if ok_run else "failure"
        if streak >= p1_at and key not in emitted:
            out.append(_finding(loop_class, P1, unit,
                       "identical %s signature %s repeated %d times consecutively (>= %d) -> loop confirmed"
                       % (outcome, h, streak, p1_at), "D3", tier=r.get("tier", 2)))
            emitted.add(key)
        elif (not ok_run) and streak == t["warn_repeat"] and key not in emitted:
            out.append(_finding(loop_class, WARN, unit,
                       "identical failure signature %s repeated %d times (>= %d)"
                       % (h, streak, t["warn_repeat"]), "D3", tier=r.get("tier", 2)))
    return out


# --------------------------------------------------------------------------- #
# D4 - timer re-fire storm / wedge probe
# --------------------------------------------------------------------------- #
def d4_timer_refire(crons, wedge, thresholds):
    """`crons` = list of {name, declared_schedule, actual_fires_per_day}. `wedge` =
    {gateway_healthy_no_progress_ticks, orphan_listener_pid, supervisor_pid,
    handoff_age_hours}. Returns findings (LP-A4/B3/B5, LP-C1/C2). A cron firing > 2x
    its declared cadence, a healthy-probe-but-no-progress wedge, and an orphan
    listener on :18789 are each P1."""
    t = thresholds["d4_timer_refire"]
    out = []
    for c in crons:
        name = c.get("name") or "<cron>"
        declared = C.fires_per_day_bound(c.get("declared_schedule"))
        actual = c.get("actual_fires_per_day")
        if declared and actual and actual > declared * t["cron_overfire_multiple"]:
            out.append(_finding("LP-C2" if c.get("announce") else "LP-A4", P1, name,
                       "cron fired %.0f/day vs declared bound %.0f/day (> %dx)"
                       % (actual, declared, t["cron_overfire_multiple"]), "D4", tier=1))
    wedge = wedge or {}
    if int(wedge.get("gateway_healthy_no_progress_ticks", 0) or 0) >= t["wedge_no_progress_ticks"]:
        out.append(_finding("LP-B5", P1, "gateway",
                   "gateway health 200 but zero turn progress for %d ticks (hung-but-alive wedge)"
                   % wedge["gateway_healthy_no_progress_ticks"], "D4", tier=1))
    orphan = wedge.get("orphan_listener_pid")
    supervisor = wedge.get("supervisor_pid")
    if orphan and orphan != supervisor:
        age = wedge.get("handoff_age_hours")
        detail = ("orphan listener pid %s on :%d NOT owned by the declared supervisor pid %s"
                  % (orphan, t["gateway_port"], supervisor))
        if age is not None and age >= t["handoff_file_age_hours"]:
            detail += " + stale handoff marker (%.1fh >= %dh)" % (age, t["handoff_file_age_hours"])
        out.append(_finding("LP-B3", P1, "gateway:%d" % t["gateway_port"], detail, "D4", tier=1))
    return out


# --------------------------------------------------------------------------- #
# D5 - self-blocking flush run / transcript poison
# --------------------------------------------------------------------------- #
def d5_transcript_poison(sessions, thresholds):
    """D1-D4 all measure FLOW - events per tick. They answer "is a loop running
    RIGHT NOW?" and go quiet the moment it pauses. D5 measures a STOCK: how much
    of a transcript is ALREADY loop wreckage. That distinction is the whole point
    of this detector. A flow detector reports all-clear on a paused loop while the
    transcript stays poisoned and every future turn on it starts degraded, so the
    fault outlives every fix aimed at the environment.

    `sessions` = list of per-transcript measurements (pure data; the collector does
    the reading):
      {unit, path, bytes, tail_records, blocked_records, max_burst, trailing_ratio,
       blocked_tools, checkpoint_rows, poisoned_checkpoints, idle_minutes}
    A "block" is ONE runtime tool-loop refusal, matched STRUCTURALLY on
    details.status=='blocked' + details.deniedReason=='tool-loop' (never on prose).

    Two faces, in the order they matter:
      IGNITION (primary)  max_burst - consecutive blocks inside one run. This is
                          the early, high-precision signal: it fires seconds into a
                          burst, long before the transcript is measurably poisoned.
      AFTERMATH (secondary) trailing_ratio + poisoned_checkpoints - the stock that
                          persists after the burst ends and that a roll must clear.

    THE SILENCE RULE (what makes this a detector and not an alarm bell): a
    transcript with ZERO blocks yields ZERO findings no matter how large it is.
    Size NEVER fires on its own - it only annotates a finding and can raise a WARN
    to P1. The control archive is 17,160,766 bytes (8x the flush re-arm floor) with
    zero blocks and must stay perfectly silent."""
    t = thresholds["d5_transcript_poison"]
    out = []
    for s in sessions:
        blocked = int(s.get("blocked_records", 0) or 0)
        if blocked <= 0:
            continue  # THE SILENCE RULE - no loop evidence, no finding, any size
        unit = s.get("unit") or "session:<unknown>"
        burst = int(s.get("max_burst", 0) or 0)
        ratio = float(s.get("trailing_ratio", 0.0) or 0.0)
        cps = int(s.get("poisoned_checkpoints", 0) or 0)
        size = int(s.get("bytes", 0) or 0)
        window = int(t["window_records"])
        rearm = size >= int(t["rearm_risk_bytes"])

        reasons = []
        severity = None
        if burst >= t["p1_blocks_per_burst"]:
            severity = P1
            reasons.append("IGNITION: %d consecutive runtime tool-loop blocks in one "
                           "burst (>= %d)" % (burst, t["p1_blocks_per_burst"]))
        if ratio >= t["p1_trailing_ratio"]:
            severity = P1
            reasons.append("AFTERMATH: %.0f%% of the trailing %d records are blocks "
                           "(>= %.0f%%)" % (ratio * 100, window,
                                            float(t["p1_trailing_ratio"]) * 100))
        if cps >= t["p1_poisoned_checkpoints"]:
            severity = P1
            reasons.append("SECOND CARRIER: %d compaction checkpoint summary(s) "
                           "captured loop text verbatim - these are re-injected on "
                           "resume and SURVIVE a transcript roll (needs LF-11)" % cps)
        if severity is None:
            if burst >= t["warn_blocks_per_burst"] or ratio >= t["warn_trailing_ratio"]:
                severity = WARN
                reasons.append("%d blocks, longest burst %d, trailing-%d share %.0f%%"
                               % (blocked, burst, window, ratio * 100))
            else:
                continue
        # Size is a MODIFIER, never a trigger: past the memoryFlush re-arm floor
        # every compaction re-arms a forced flush, so a poisoned transcript that is
        # ALSO oversized will keep re-igniting. That escalates a WARN; it never
        # creates a finding on its own.
        if rearm:
            reasons.append("transcript %d bytes is past the flush re-arm floor (%d) - "
                           "every compaction re-arms a forced flush"
                           % (size, int(t["rearm_risk_bytes"])))
            if severity == WARN:
                severity = P1
        tools = s.get("blocked_tools") or []
        if tools:
            reasons.append("blocked tool(s): %s" % ",".join(sorted(str(x) for x in tools)))
        idle = s.get("idle_minutes")
        if idle is not None:
            reasons.append("transcript idle %.0fm (auto-roll needs >= %dm)"
                           % (float(idle), int(t["roll_min_idle_minutes"])))
        out.append(_finding("LP-A8", severity, unit, "; ".join(reasons), "D5",
                            tier=1, evidence_path=s.get("path")))
    return out


# --------------------------------------------------------------------------- #
# D6 - futile retry burst (SEMANTIC repetition; argument-blind)
# --------------------------------------------------------------------------- #
def d6_futile_retry_burst(bursts, thresholds, signatures=None):
    """The blind spot every OTHER loop guard on this fleet shares: they all key on
    the ARGUMENTS.

      - The OpenClaw runtime's own identical-call guard keys on (toolName, argsHash).
      - This repo's always-armed runaway patch keys on (toolName, argsHash,
        resultHash) - STRICTER still, so it is blind in exactly the same way.
      - D3 above hashes (outcome class + tool sequence + TARGET).

    An agent that REWORDS a failing intent therefore defeats all three at once. The
    incident this detector comes from: an agent hit a fail-closed API, then made
    thirteen tool calls in forty-nine seconds - every one a differently-worded
    attempt at the same intent. Every call carried distinct arguments, so every
    args-keyed guard stayed silent and the run was only stopped by the human
    watching it narrate the hunt.

    D6 never looks at arguments. It asks the only question that survives rewording:
    *is this tool being called over and over while producing no progress?*

    `bursts` = list of per (transcript, tool) measurements, already reduced by the
    collector to counts inside one sliding window (pure data, no content):
      {unit, path, tool, calls, errors, failclosed, span_seconds}
        calls       tool calls to THIS tool inside the window
        errors      how many returned a tool-layer error/blocked result
        failclosed  how many returned a FAIL-CLOSED DEPENDENCY marker
                    (auth-class refusal: unauthorized / forbidden / invalid key /
                    authentication failed) counted from the result payload
    Only counts ever reach this function - never arguments, never result text.

    TWO FACES, and the second is the one that matters:

      FAILING BURST (secondary). Many calls to one tool in the window, most of them
        failing at the TOOL layer. Sound, but it only sees failures the runtime
        already labels as failures.

      FAIL-CLOSED DEPENDENCY (primary). The call SUCCEEDS and the dependency
        refuses inside the payload - `exec` running a curl that returns
        {"error":"Unauthorized"} exits 0 and is recorded `status: completed`. The
        tool layer sees nothing wrong at all, which is precisely why every existing
        guard missed the incident. Retrying an auth-class refusal cannot succeed by
        being reworded, so attempt number three is already a loop. This face is the
        detector encoding of the doctrine rule: STOP AFTER <= 2 ATTEMPTS.

    THE SILENCE RULE (inherited from D5, and load-bearing here): a burst with zero
    errors AND zero fail-closed markers yields ZERO findings no matter how many
    calls it contains. Volume alone is NEVER a loop. This is not caution - it is
    measured: the real local corpus (998 transcripts, 12,465 tool results) contains
    a perfectly healthy burst of 460 `exec` calls in 48.2 seconds with 2 errors.
    Any count-only detector - the obvious design, and the one this deliberately
    rejects - would fire on that and on ~100 other healthy bursts. Futility, not
    volume, is the signal."""
    t = thresholds["d6_futile_retry_burst"]
    sig = signatures if signatures is not None else C.load_signatures()  # noqa: F841
    out = []
    for b in bursts:
        calls = int(b.get("calls", 0) or 0)
        errors = int(b.get("errors", 0) or 0)
        failclosed = int(b.get("failclosed", 0) or 0)
        # THE SILENCE RULE - no evidence of futility, no finding, at ANY volume.
        if errors <= 0 and failclosed <= 0:
            continue
        tool = b.get("tool") or "<tool>"
        unit = b.get("unit") or "session:<unknown>"
        span = float(b.get("span_seconds", 0.0) or 0.0)
        window = int(t["window_seconds"])
        ratio = (float(errors) / calls) if calls else 0.0

        reasons = []
        severity = None

        # ---- FAIL-CLOSED DEPENDENCY (primary) --------------------------------
        if failclosed >= t["p1_failclosed_calls"]:
            severity = P1
            reasons.append(
                "FAIL-CLOSED DEPENDENCY: %d calls to `%s` in %.0fs returned an "
                "auth-class refusal (>= %d) - retrying a fail-closed dependency "
                "cannot succeed by rewording the request"
                % (failclosed, tool, span, t["p1_failclosed_calls"]))
        elif failclosed >= t["warn_failclosed_calls"]:
            severity = WARN
            reasons.append(
                "FAIL-CLOSED DEPENDENCY: %d calls to `%s` in %.0fs returned an "
                "auth-class refusal - doctrine allows <= %d attempts before "
                "stopping and reporting what is blocked"
                % (failclosed, tool, span, t["doctrine_max_attempts"]))

        # ---- FAILING BURST (secondary) ---------------------------------------
        if calls >= t["p1_burst_calls"] and ratio >= t["p1_error_ratio"]:
            severity = P1
            reasons.append(
                "FAILING BURST: %d/%d calls to `%s` failed inside a %ds window "
                "(%.0f%% >= %.0f%%)"
                % (errors, calls, tool, window, ratio * 100,
                   float(t["p1_error_ratio"]) * 100))
        elif (severity is None and calls >= t["min_burst_calls"]
              and ratio >= t["warn_error_ratio"]):
            severity = WARN
            reasons.append(
                "FAILING BURST: %d/%d calls to `%s` failed inside a %ds window "
                "(%.0f%% >= %.0f%%)"
                % (errors, calls, tool, window, ratio * 100,
                   float(t["warn_error_ratio"]) * 100))

        if severity is None:
            continue

        # Arguments are NEVER inspected, so say so in the finding: this is the one
        # detector whose verdict survives an agent rewording its way around every
        # args-keyed guard on the box.
        reasons.append("argument-blind: %d distinct-argument calls would defeat "
                       "every (toolName,argsHash) guard" % calls)
        out.append(_finding("LP-A9", severity, unit, "; ".join(reasons), "D6",
                            tier=2, evidence_path=b.get("path"),
                            dedup_key="LP-A9|%s|%s" % (unit, tool)))
    return out


# --------------------------------------------------------------------------- #
# self-test (deterministic, no box access, no network, no model)
# --------------------------------------------------------------------------- #
def self_test():
    print("[loop_detectors] self-test: D1 restart, D2 idle-burn, D3 signature, D4 wedge/orphan")
    th = C.load_skill_config("thresholds.json")

    # D1: Box A-class storm (56,050) trips P1 in ONE tick; a quiet unit stays silent.
    units = [
        {"name": "cc-app", "status": "online", "pid": 42, "restarts": 56050, "delta": 12,
         "day_restarts": 900},
        {"name": "gateway", "status": "online", "pid": 7, "restarts": 0, "delta": 0},
    ]
    f1 = d1_restart_velocity(units, th)
    assert any(x["severity"] == P1 and x["unit"] == "cc-app" and x["loop_class"] == "LP-B1"
               for x in f1)
    assert not any(x["unit"] == "gateway" for x in f1)
    # WARN escalates to P1 after N consecutive ticks
    warnu = [{"name": "flappy", "delta": 4}]
    f1b = d1_restart_velocity(warnu, th, warn_streaks={"flappy": 3})
    assert f1b and f1b[0]["severity"] == P1
    print("  D1 case: PASS (storm=P1, quiet=silent, WARN streak escalates)")

    # D2: idle window with a heavy paid burn = P1; a working (non-idle) window silent.
    windows = [
        {"label": "02:00-03:00", "paid_tokens": 500000, "initiated_sessions": 0, "idle_consecutive": 1},
        {"label": "09:00-10:00", "paid_tokens": 500000, "initiated_sessions": 3, "idle_consecutive": 0},
        {"label": "03:00-04:00", "paid_tokens": 100, "initiated_sessions": 0, "idle_consecutive": 4},
    ]
    f2 = d2_token_burn_rate(windows, th)
    assert any(x["severity"] == P1 and x["unit"] == "02:00-03:00" for x in f2)
    assert not any(x["unit"] == "09:00-10:00" for x in f2)  # not idle
    assert any(x["unit"] == "03:00-04:00" and x["severity"] == P1 for x in f2)  # any-paid streak
    print("  D2 case: PASS (idle heavy=P1, working=silent, any-paid-4-windows=P1)")

    # D3: 5 identical compaction failures = P1 loop confirmed; a differing run breaks it.
    runs = [{"unit": "session:main", "error_class": "ContextTooLarge",
             "tool_sequence": [], "target": "session:main", "loop_class": "LP-A1"}
            for _ in range(5)]
    f3 = d3_identical_signature(runs, th)
    assert any(x["severity"] == P1 and x["loop_class"] == "LP-A1" for x in f3)
    mixed = runs[:2] + [{"unit": "session:main", "error_class": "Other",
                         "tool_sequence": [], "target": "x"}] + runs[:2]
    f3b = d3_identical_signature(mixed, th)
    assert not any(x["severity"] == P1 for x in f3b)  # streak never reaches 5
    print("  D3 case: PASS (5 identical=P1; a break resets the streak)")

    # D3 success face: repeated identical SUCCESSFUL turns are a loop too, at the
    # HIGHER ceiling (p1_repeat_success), and never WARN below it - a heartbeat
    # succeeding once per slice stays silent forever.
    ok_runs = [{"unit": "session:main", "error_class": "OK",
                "tool_sequence": ["exec", "message"], "target": "session:main"}
               for _ in range(12)]
    f3c = d3_identical_signature(ok_runs, th)
    assert any(x["severity"] == P1 and "successful-turn" in x["detail"] for x in f3c)
    f3d = d3_identical_signature(ok_runs[:9], th)
    assert not f3d  # 9 < p1_repeat_success(10) and successes never WARN
    print("  D3 success case: PASS (12 identical OK=P1 at the success ceiling; 9=silent)")

    # D4: cron over-fire, wedge, orphan listener each = P1.
    crons = [{"name": "resume", "declared_schedule": "@daily", "actual_fires_per_day": 96},
             {"name": "healthy", "declared_schedule": "*/15 * * * *", "actual_fires_per_day": 96}]
    wedge = {"gateway_healthy_no_progress_ticks": 3, "orphan_listener_pid": 111,
             "supervisor_pid": 222, "handoff_age_hours": 30}
    f4 = d4_timer_refire(crons, wedge, th)
    classes = {x["loop_class"] for x in f4}
    assert "LP-A4" in classes and "LP-B5" in classes and "LP-B3" in classes
    assert not any(x["unit"] == "healthy" for x in f4)  # firing at its declared rate
    print("  D4 case: PASS (over-fire + wedge + orphan each P1; healthy cron silent)")

    # D5: the STOCK detector. Values below are the MEASURED shape of one archived
    # operator-box incident vs its healthy control, not invented numbers.
    poisoned = [{"unit": "session:example-poisoned", "bytes": 4607807,
                 "tail_records": 3393, "blocked_records": 1135, "max_burst": 275,
                 "trailing_ratio": 0.50, "blocked_tools": ["read", "tool_call"],
                 "checkpoint_rows": 16, "poisoned_checkpoints": 7,
                 "idle_minutes": 240.0}]
    f5 = d5_transcript_poison(poisoned, th)
    assert len(f5) == 1 and f5[0]["severity"] == P1 and f5[0]["loop_class"] == "LP-A8"
    assert "IGNITION" in f5[0]["detail"] and "SECOND CARRIER" in f5[0]["detail"]

    # THE CONTROL, and the whole reason this is a detector: a transcript 3.7x LARGER
    # than the poisoned one, 8x past the flush re-arm floor, with many checkpoints -
    # but ZERO blocks. It must be perfectly silent. A detector that fires on
    # everything is not a detector.
    healthy = [{"unit": "session:example-healthy", "bytes": 17160766,
                "tail_records": 8042, "blocked_records": 0, "max_burst": 0,
                "trailing_ratio": 0.0, "blocked_tools": [],
                "checkpoint_rows": 14, "poisoned_checkpoints": 0,
                "idle_minutes": 99999.0}]
    assert d5_transcript_poison(healthy, th) == []

    # The smallest burst measured in the incident (8) still trips P1 - that is the
    # threshold's whole job: catch 11/11 historical bursts, ~6.5% into the median
    # one, instead of waiting for the transcript to be measurably poisoned.
    smallest = [dict(poisoned[0], blocked_records=8, max_burst=8, trailing_ratio=0.04,
                     poisoned_checkpoints=0, bytes=100000)]
    f5c = d5_transcript_poison(smallest, th)
    assert f5c and f5c[0]["severity"] == P1 and "IGNITION" in f5c[0]["detail"]

    # A brief 3-block stutter on a SMALL transcript is a WARN, not a P1...
    stutter = [dict(poisoned[0], blocked_records=3, max_burst=3, trailing_ratio=0.015,
                    poisoned_checkpoints=0, bytes=100000)]
    f5d = d5_transcript_poison(stutter, th)
    assert f5d and f5d[0]["severity"] == WARN
    # ...but the SAME stutter past the flush re-arm floor is a P1, because every
    # compaction there re-arms a forced flush and it will keep re-igniting.
    f5e = d5_transcript_poison([dict(stutter[0], bytes=3000000)], th)
    assert f5e and f5e[0]["severity"] == P1 and "re-arm floor" in f5e[0]["detail"]

    # A 1-2 block blip below the WARN floor stays silent (no noise on a healthy box).
    assert d5_transcript_poison(
        [dict(poisoned[0], blocked_records=2, max_burst=2, trailing_ratio=0.01,
              poisoned_checkpoints=0, bytes=100000)], th) == []
    print("  D5 case: PASS (poisoned=P1 ignition+carrier; 17MB clean control SILENT; "
          "smallest-observed burst 8=P1; stutter=WARN, oversized stutter=P1; blip silent)")

    # D6: SEMANTIC repetition. The incident shape - 13 tool calls in 49s, every
    # one a differently-worded attempt at the same intent, against a fail-closed
    # API. Every call carried DISTINCT arguments, so the runtime's
    # (toolName,argsHash) guard and this repo's stricter
    # (toolName,argsHash,resultHash) runaway patch both stayed silent all day.
    incident = [{"unit": "session:example-incident", "tool": "exec", "calls": 13,
                 "errors": 0, "failclosed": 6, "span_seconds": 49.0,
                 "path": "/example/incident.jsonl"}]
    f6 = d6_futile_retry_burst(incident, th)
    assert len(f6) == 1 and f6[0]["severity"] == P1 and f6[0]["loop_class"] == "LP-A9"
    assert "FAIL-CLOSED DEPENDENCY" in f6[0]["detail"]
    # NOTE the errors=0 above: those 13 exec calls SUCCEEDED at the tool layer
    # (a curl against a fail-closed API exits 0, recorded status=completed). Any
    # detector keyed on tool-layer failure is blind to this entire class.

    # THE CONTROL, and the reason this detector counts futility instead of volume:
    # a REAL measured burst from the operator box's own corpus - 460 exec calls in
    # 48.2 seconds, 35x the incident's call count - with no failures and no
    # fail-closed refusals. It must be PERFECTLY SILENT. A count-only detector
    # (the obvious design) fires here, and on ~100 more healthy bursts in the same
    # corpus, which is precisely why count-only was rejected.
    healthy_burst = [{"unit": "session:example-healthy", "tool": "exec", "calls": 460,
                      "errors": 0, "failclosed": 0, "span_seconds": 48.2}]
    assert d6_futile_retry_burst(healthy_burst, th) == []
    # Even a big burst with a FEW incidental errors stays below the ratio floor.
    assert d6_futile_retry_burst(
        [dict(healthy_burst[0], errors=2)], th) == []

    # The doctrine boundary: 2 attempts against a fail-closed dependency is
    # allowed (that IS the rule), the 3rd is a WARN, the 5th a P1.
    assert d6_futile_retry_burst(
        [{"unit": "s", "tool": "exec", "calls": 2, "errors": 0, "failclosed": 2,
          "span_seconds": 5.0}], th) == []
    f6b = d6_futile_retry_burst(
        [{"unit": "s", "tool": "exec", "calls": 3, "errors": 0, "failclosed": 3,
          "span_seconds": 8.0}], th)
    assert f6b and f6b[0]["severity"] == WARN

    # FAILING-BURST face: the measured 36-call/36-error read burst from the real
    # corpus is a P1; the measured 24-call/18-error exec burst is a WARN.
    f6c = d6_futile_retry_burst(
        [{"unit": "s", "tool": "read", "calls": 36, "errors": 36, "failclosed": 0,
          "span_seconds": 60.0}], th)
    assert f6c and f6c[0]["severity"] == P1 and "FAILING BURST" in f6c[0]["detail"]
    f6d = d6_futile_retry_burst(
        [{"unit": "s", "tool": "exec", "calls": 24, "errors": 18, "failclosed": 0,
          "span_seconds": 59.4}], th)
    assert f6d and f6d[0]["severity"] == WARN
    print("  D6 case: PASS (13-call reworded hunt=P1 though every call SUCCEEDED; "
          "real 460-call healthy burst SILENT; 2 attempts allowed, 3rd=WARN; "
          "36/36 failing burst=P1)")

    print("[loop_detectors] self-test: PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Loop Protection detectors D1-D4.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
