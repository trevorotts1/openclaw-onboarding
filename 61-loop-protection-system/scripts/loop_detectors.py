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

    print("[loop_detectors] self-test: PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Loop Protection detectors D1-D4.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
