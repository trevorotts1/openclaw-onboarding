#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_cadence.py
# SELF-UPDATE CADENCE - the watcher must be the MOST-audited thing (spec Section 8)
# -----------------------------------------------------------------------------
# D8 LOCKED: WEEKLY, PINNED. The system starts weekly and STAYS weekly; it must
# NOT auto-downshift to monthly. The recommender measures drift velocity and may
# surface a NOTE in the digest, but the standing cadence NEVER changes itself -
# with pinned=true a "monthly" recommendation is advisory text only, never applied.
# The ONLY path that changes the effective cadence is an explicit operator
# 'cadence set ...', which writes an approval into a STATE overlay (never mutating
# the shipped config/cadence.json, so a box-local change can never trip S9).
#
# STDLIB ONLY. DOCTRINE: the system never changes its own cadence, thresholds, or
# signatures silently - cadence changes follow the same propose-approve loop as
# everything else.
#
# EXIT CODES: 0 OK, 1 error, 2 usage.
# =============================================================================
"""ews_cadence.py - drift-velocity measurement + weekly-pinned cadence (Skill 60)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import default_state_dir, now_utc  # noqa: E402

EX_OK, EX_ERR, EX_USAGE = 0, 1, 2


def _overlay_path(state_dir=None):
    return (Path(state_dir) if state_dir else default_state_dir()) / "cadence-approval.json"


def load_cadence(state_dir=None) -> dict:
    """The effective cadence: the operator's STATE overlay if present, else the
    shipped config/cadence.json pin (weekly, D8)."""
    ov = _overlay_path(state_dir)
    if ov.is_file():
        try:
            return json.loads(ov.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return C.load_skill_config("cadence.json")


def _rule(cadence_cfg):
    return cadence_cfg.get("drift_velocity_rule", {})


def week_wants_weekly(week, rule) -> bool:
    """Does one week's velocity trip any weekly threshold?"""
    r = rule.get("recommend_weekly_when_any", {})
    if week.get("material_drift_events", 0) >= r.get("material_drift_events_per_fleet_week_gte", 3):
        return True
    if week.get("signature_misses", 0) >= r.get("signature_misses_gte", 1):
        return True
    if week.get("new_model_ids_observed", 0) >= r.get("new_model_ids_observed_gte", 5):
        return True
    return False


def recommendation_for(series, cadence_cfg):
    """Given a chronological list of per-week velocity dicts (oldest first), return
    a recommendation dict. Hysteresis: a switch is proposed only after N consecutive
    most-recent weeks agree. A P1 signature miss in the latest week short-circuits to
    'weekly' immediately. Because current.pinned is honored by the caller, this is
    ADVISORY - it never applies itself."""
    rule = _rule(cadence_cfg)
    hyst = rule.get("hysteresis_periods", 2)
    if not series:
        return {"recommendation": "hold", "reason": "no velocity data", "drivers": {}}

    latest = series[-1]
    if rule.get("p1_signature_miss_short_circuits", True) and latest.get("p1_signature_miss"):
        return {"recommendation": "weekly", "reason": "P1 signature miss - immediate refresh",
                "drivers": latest}

    wants = [week_wants_weekly(w, rule) for w in series]
    weeks_low = rule.get("recommend_monthly_when_all_below_for_weeks", 4)
    tail = wants[-hyst:] if hyst > 0 else wants
    if len(tail) >= hyst and all(tail):
        return {"recommendation": "weekly",
                "reason": "%d consecutive weeks above the drift floor" % hyst, "drivers": latest}
    if len(series) >= weeks_low and not any(wants[-weeks_low:]):
        return {"recommendation": "monthly",
                "reason": "all metrics below the floor for %d consecutive weeks" % weeks_low,
                "drivers": latest}
    return {"recommendation": "hold", "reason": "no consecutive agreement (hysteresis)", "drivers": latest}


def digest_line(series, state_dir=None):
    """The standing cadence line for the weekly operator digest."""
    cfg = load_cadence(state_dir)
    cur = cfg.get("current", {})
    rec = recommendation_for(series, cfg)
    applied = "advisory only (cadence is PINNED)" if cur.get("pinned") else "operator may apply"
    line = ("current cadence: %s%s, approved %s; recommendation: %s (%s); %s"
            % (cur.get("cadence", "weekly"),
               " [PINNED]" if cur.get("pinned") else "",
               cur.get("approved_at", "?"), rec["recommendation"], rec["reason"], applied))
    return {"line": line, "current": cur, "recommendation": rec}


def cmd_set(cadence, reason, operator, state_dir=None):
    """The ONLY path that changes the effective cadence - an explicit operator act.
    Writes a STATE overlay (never the shipped config), preserving history."""
    if cadence not in ("weekly", "monthly"):
        raise ValueError("cadence must be weekly or monthly")
    cur = load_cadence(state_dir)
    hist = cur.get("history", [])
    entry = {"cadence": cadence, "pinned": (cadence == "weekly"), "approved_by": operator,
             "approved_at": now_utc(), "reason": reason}
    hist.append(entry)
    overlay = {"version": 1,
               "current": {"cadence": cadence, "pinned": (cadence == "weekly"),
                           "approved_by": operator, "approved_at": now_utc(), "reason": reason},
               "recommender": cur.get("recommender", {"enabled": True, "may_change_current": False}),
               "drift_velocity_rule": cur.get("drift_velocity_rule",
                                              C.load_skill_config("cadence.json").get("drift_velocity_rule", {})),
               "history": hist[-50:]}
    ov = _overlay_path(state_dir)
    ov.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cadence.", suffix=".tmp", dir=str(ov.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(overlay, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, ov)
        os.chmod(ov, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return overlay["current"]


def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_cadence.py",
                                 description="Drift-velocity cadence recommender (weekly-pinned, D8).")
    ap.add_argument("--state-dir")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sub.add_parser("show")
    sp = sub.add_parser("recommend")
    sp.add_argument("--series", help="JSON list of per-week velocity dicts (or - for stdin)")
    sp = sub.add_parser("set")
    sp.add_argument("--cadence", required=True, choices=["weekly", "monthly"])
    sp.add_argument("--reason", required=True)
    sp.add_argument("--operator", default="operator")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    sd = Path(args.state_dir) if args.state_dir else None
    if args.cmd == "show":
        _emit(load_cadence(sd))
        return EX_OK
    if args.cmd == "recommend":
        raw = sys.stdin.read() if args.series in (None, "-") else args.series
        series = json.loads(raw) if raw else []
        _emit(digest_line(series, sd))
        return EX_OK
    if args.cmd == "set":
        _emit({"ok": True, "current": cmd_set(args.cadence, args.reason, args.operator, sd)})
        return EX_OK
    ap.error("a subcommand is required (or use --self-test)")


def self_test():
    import tempfile as _tf
    print("[ews_cadence] self-test: weekly PINNED, recommender advisory, hysteresis, operator set")
    cfg = C.load_skill_config("cadence.json")
    assert cfg["current"]["cadence"] == "weekly" and cfg["current"]["pinned"] is True
    print("  pin case: PASS (shipped default is weekly + pinned, D8)")

    # high velocity -> recommends weekly
    hi = [{"material_drift_events": 5, "signature_misses": 0, "new_model_ids_observed": 6}] * 3
    r_hi = recommendation_for(hi, cfg)
    assert r_hi["recommendation"] == "weekly"
    # sustained low -> recommends monthly (advisory only)
    lo = [{"material_drift_events": 0, "signature_misses": 0, "new_model_ids_observed": 0}] * 4
    r_lo = recommendation_for(lo, cfg)
    assert r_lo["recommendation"] == "monthly"
    print("  recommend case: PASS (high=weekly, sustained-low=monthly)")

    # hysteresis: a single low week after highs does NOT flip to monthly
    mixed = hi[:3] + lo[:1]
    r_mixed = recommendation_for(mixed, cfg)
    assert r_mixed["recommendation"] in ("hold", "weekly")
    assert r_mixed["recommendation"] != "monthly"
    print("  hysteresis case: PASS (one low week does not flip the recommendation)")

    # P1 signature miss short-circuits to weekly regardless
    miss = lo[:3] + [{"material_drift_events": 0, "signature_misses": 0,
                      "new_model_ids_observed": 0, "p1_signature_miss": True}]
    assert recommendation_for(miss, cfg)["recommendation"] == "weekly"
    print("  short-circuit case: PASS (P1 signature miss forces weekly)")

    # the DIGEST LINE for a monthly-recommending series still reports PINNED weekly,
    # and marks the recommendation advisory-only (the system never self-changes)
    dl = digest_line(lo)
    assert "PINNED" in dl["line"] and "advisory only" in dl["line"]
    assert dl["current"]["cadence"] == "weekly"
    assert dl["recommendation"]["recommendation"] == "monthly"  # surfaced, not applied
    print("  advisory case: PASS (monthly surfaced but cadence stays PINNED weekly, D8)")

    # explicit operator set writes a STATE overlay (never the shipped file)
    with _tf.TemporaryDirectory() as td:
        os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
        before = C.load_skill_config("cadence.json")["current"]["cadence"]
        cur = cmd_set("monthly", "operator explicitly chose monthly", "operator")
        assert cur["cadence"] == "monthly"
        # the shipped config is UNTOUCHED (no S9 drift)
        assert C.load_skill_config("cadence.json")["current"]["cadence"] == before == "weekly"
        # the effective (overlay) cadence is now monthly
        assert load_cadence()["current"]["cadence"] == "monthly"
        os.environ.pop("EWS_STATE_DIR", None)
    print("  operator-set case: PASS (overlay changes effective cadence; shipped file untouched)")

    print("[ews_cadence] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
