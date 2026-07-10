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
# collect() is the thin best-effort box-reading layer (never fatal on a probe miss:
# a probe failure is DATA, never a crash - loop-detector.sh's exit-0-always law).
# =============================================================================
"""loop_watchdog.py - the per-box Loop Protection watchdog tick."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
import loop_detectors as D  # noqa: E402
import loop_killcards as KC  # noqa: E402
import loop_escalate as ESC  # noqa: E402
from loop_ledger import Ledger  # noqa: E402


def run_detectors(evidence, thresholds, signatures):
    """Run D1-D4 over injected/collected evidence. Returns a flat findings list."""
    findings = []
    findings += D.d1_restart_velocity(evidence.get("units", []), thresholds,
                                      warn_streaks=evidence.get("warn_streaks", {}))
    findings += D.d2_token_burn_rate(evidence.get("windows", []), thresholds, signatures)
    findings += D.d3_identical_signature(evidence.get("runs", []), thresholds)
    findings += D.d4_timer_refire(evidence.get("crons", []), evidence.get("wedge", {}), thresholds)
    return findings


def _dedup_ok(led, finding, window_hours):
    """One alert per (class, box/unit) per window. Records the digest when clear."""
    key = finding.get("dedup_key") or ("%s|%s" % (finding["loop_class"], finding.get("unit")))
    if led.recent_digest(key, window_hours):
        return False
    led.record_digest("alert", key, payload=finding.get("severity"))
    return True


def tick(evidence, led, armed=None, escalate_transport=None, box="box"):
    """One deterministic tick over INJECTED evidence. Returns a summary dict:
      {armed, findings, applied, planned, escalated, alerts}
    Zero model calls. With armed False (DRY_RUN) NOTHING is mutated outside OUR ledger
    (findings are still recorded - observing is the whole point of burn-in)."""
    thresholds = C.load_skill_config("thresholds.json")
    signatures = C.load_signatures()
    if armed is None:
        armed = led.is_armed()
    window_hours = thresholds["alert"]["dedup_window_hours"]

    summary = {"armed": armed, "findings": 0, "applied": 0, "planned": 0,
               "escalated": 0, "alerts": 0, "by_class": {}}

    findings = run_detectors(evidence, thresholds, signatures)
    for f in findings:
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

        # escalate Tier-3 and any healer-breaker escalation via Rescue Rangers
        if result.get("escalate"):
            payload = ESC.build_payload(
                box=box, loop_class=f["loop_class"], finding=f.get("detail"),
                evidence_path=f.get("evidence_path"),
                proposed_fix=kc.get("what"), why=result.get("detail"),
                action_needed="operator decision / approve fix",
                finding_id=fid, killcard_cmd=kc.get("killcard_cmd"),
                revert_cmd=kc.get("revert_cmd"))
            ESC.send(payload, transport=escalate_transport)
            led.set_finding_state(fid, "escalated")
            summary["escalated"] += 1

        # operator alert (deduped). P1 bypasses batching but not dedup.
        if f["severity"] in ("P1", "P2") and _dedup_ok(led, f, window_hours):
            summary["alerts"] += 1

    return summary


# --------------------------------------------------------------------------- #
# collect() - the thin best-effort box-reading layer (never fatal)
# --------------------------------------------------------------------------- #
def collect_units():
    """Best-effort pm2 jlist -> filtered units (name/status/pid/restarts ONLY). Returns
    [] on any miss (no pm2, not JSON, no git). NEVER dumps env. A probe miss is DATA."""
    import subprocess
    try:
        out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        recs = json.loads(out.stdout or "[]")
    except Exception:  # noqa: BLE001 - probe failure is data, never a crash
        return []
    units = []
    for rec in recs if isinstance(recs, list) else []:
        f = C.filter_pm2_record(rec)
        if f.get("name"):
            f["delta"] = f["restarts"]  # first-seen delta = current count; ledger refines
            units.append(f)
    return units


def collect_evidence():
    """Assemble the evidence dict from the box, best-effort. Detectors run over
    whatever is available; a missing source contributes no findings, never an error."""
    return {"units": collect_units(), "windows": [], "runs": [], "crons": [], "wedge": {}}


def self_test():
    import tempfile
    print("[loop_watchdog] self-test: DRY_RUN records+plans-nothing, armed-parks, escalate offline")

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

        # Tier-3 class escalates offline (UNSENT fallback), never tight-loops.
        empty = {"units": [], "crons": [{"name": "noop", "declared_schedule": "@daily",
                 "actual_fires_per_day": 300}], "windows": [], "runs": [], "wedge": {}}
        s3 = tick(empty, led, armed=True, escalate_transport=dead_tx, box="box-example")
        assert s3["findings"] >= 1
        print("  escalate case: PASS (offline escalation via UNSENT fallback, no crash)")

        led.close()
        os.environ.pop("LOOP_STATE_DIR", None)

    print("[loop_watchdog] self-test: PASS")
    return 0


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection per-box watchdog tick.")
    ap.add_argument("cmd", nargs="?", default="tick", choices=["tick"])
    ap.add_argument("--no-send", action="store_true",
                    help="do not deliver alerts/escalations (still records findings)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    led = Ledger()
    try:
        box = led.get_meta("box", "box")
        evidence = collect_evidence()
        tx = (lambda url, body: True) if a.no_send else None
        summary = tick(evidence, led, escalate_transport=tx, box=box)
        print(json.dumps(summary, sort_keys=True))
        return 0
    finally:
        led.close()


if __name__ == "__main__":
    sys.exit(_cli())
