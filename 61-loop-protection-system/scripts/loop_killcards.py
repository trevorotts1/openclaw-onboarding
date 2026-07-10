#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_killcards.py
# The responder's playbook (spec Section 4.2 + 6.3). Each Tier-1 fix class is a
# TESTED, REVERSIBLE, single-blast-radius kill card. The universal quarantine
# ladder (spec 4.1) is the order every fix follows:
#   1 silence the TIMER before the process   2 snapshot before any config touch
#   3 write as the box user, never root       4 restart via the sanctioned path
#   5 verify it STAYS fixed                    6 ledger + report
#
# DRY_RUN IS THE DEFAULT (spec 6.1): with armed=False every kill card PLANS and
# mutates NOTHING (D-DRYRUN proves the filesystem is byte-identical after a tick).
# Tier 2/3 NEVER auto-apply here - they return a prepared proposal for the operator
# / Rescue Rangers. The healer self-breaker is consulted before every apply: a
# target that has already been fixed >3x/24h, or whose last fix failed verify, is
# NOT auto-fixed again (the session-health.sh law).
#
# The mechanical actions are stdlib-only, deterministic, and operate on the paths
# they are handed (so drills exercise REAL mutations on SCRATCH fixtures). NO model
# call, NO network. Config-touching actions hard-refuse root.
# =============================================================================
"""loop_killcards.py - per-class kill cards for the Loop Protection System."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
import loop_breaker as BR  # noqa: E402


def fix_class_for(loop_class):
    """Resolve the fix-class entry (LF-*) whose loop_class field NAMES this loop class.
    Returns the entry dict or None (None => no Tier-1 auto-fix; propose/escalate)."""
    for fc in C.load_skill_config("fix-classes.json")["fix_classes"]:
        names = [n.strip() for n in str(fc.get("loop_class", "")).split("/")]
        if loop_class in names:
            return fc
    return None


def plan(finding, box="box", killcard_cmd=None):
    """Build the prepared kill card for a finding (pure). Returns a plan dict with the
    fix class, tier, the exact action, and the one-line revert. A fix that cannot be
    reverted in one line does not ship (spec 4.2)."""
    lc = finding.get("loop_class")
    fc = fix_class_for(lc)
    fid = finding.get("finding_id")
    revert = C.revert_command_for(fid if fid is not None else "<id>")
    if fc is None:
        return {"loop_class": lc, "fix_class": None, "tier": 3, "action": "propose-and-hold",
                "what": "no Tier-1 kill card for %s; escalate to Rescue Rangers" % lc,
                "revert_cmd": revert}
    return {"loop_class": lc, "fix_class": fc["id"], "tier": fc["tier"],
            "action": fc["title"], "what": fc["title"],
            "reversible_in": fc.get("reversible_in"),
            "revert_cmd": revert,
            "killcard_cmd": killcard_cmd or ("loop-companion.sh fix %s" % (fid if fid is not None else "<id>"))}


# --------------------------------------------------------------------------- #
# Mechanical actions (deterministic; operate on the paths handed to them).
# Each honors DRY_RUN (plan only) and returns a result dict.
# --------------------------------------------------------------------------- #
def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False


def lf1_archive_stale_lock(lock_path, dry_run=True):
    """LF-1: remove a stale lock ONLY after proving (by a REAL JSON parse) that its pid
    is dead. The session-health failure defines the safe version: never treat a JSON
    lock as a bare pid, and NEVER touch a live lock. Returns {applied, reason}."""
    p = Path(lock_path)
    if not p.is_file():
        return {"applied": False, "reason": "no lock file", "dry_run": dry_run}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        pid = data.get("pid") if isinstance(data, dict) else None
    except (ValueError, OSError):
        return {"applied": False, "reason": "lock not JSON-parseable; NOT touched (safe refusal)",
                "dry_run": dry_run}
    if _pid_alive(pid):
        return {"applied": False, "reason": "lock pid %s is ALIVE; never touch a live lock" % pid,
                "dry_run": dry_run}
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would archive dead-pid lock (pid %s)" % pid,
                "dry_run": True}
    archive = p.with_suffix(p.suffix + ".archived")
    shutil.move(str(p), str(archive))
    return {"applied": True, "reason": "archived dead-pid lock to %s" % archive,
            "dry_run": False, "revert": "mv %s %s" % (archive, p)}


def lf4_disable_cron(cron_file, cron_id, dry_run=True):
    """LF-4: disable a cron (enabled:false) - DISABLE, NEVER DELETE. Config-touching =>
    refuses root. Operates on a JSON file of {crons:[{id/name, enabled}]}. Reversible by
    setting enabled:true. Returns {applied, reason}."""
    C.refuse_root_for_config("disable-cron")
    p = Path(cron_file)
    data = json.loads(p.read_text(encoding="utf-8"))
    crons = data.get("crons", data if isinstance(data, list) else [])
    target = None
    for c in crons:
        if c.get("id") == cron_id or c.get("name") == cron_id:
            target = c
            break
    if target is None:
        return {"applied": False, "reason": "cron %s not found" % cron_id, "dry_run": dry_run}
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would set enabled=false on %s (never delete)"
                % cron_id, "dry_run": True}
    target["enabled"] = False
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"applied": True, "reason": "disabled cron %s (enabled=false; not deleted)" % cron_id,
            "dry_run": False,
            "revert": "set enabled=true on cron %s" % cron_id}


def lf2_rewind_offset(offset_file, dry_run=True):
    """LF-2: rewind a corrupted telegram getUpdates offset. When the stored
    lastUpdateId has advanced PAST the oldest pending update (a restart race, deaf
    inbound), rewind stored_offset to oldest_pending_update_id - 1 and record the new
    value. Reversible via the prior offset (snapshotted first). Operates on a JSON file
    {stored_offset, oldest_pending_update_id}. Returns {applied, reason, rewound_to}."""
    p = Path(offset_file)
    data = json.loads(p.read_text(encoding="utf-8"))
    stored = int(data.get("stored_offset", 0))
    oldest = int(data.get("oldest_pending_update_id", 0))
    if stored < oldest:
        return {"applied": False, "reason": "offset not advanced past pending; nothing to rewind",
                "dry_run": dry_run, "rewound_to": stored}
    target = oldest - 1
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would rewind %d -> %d + restart channel"
                % (stored, target), "dry_run": True, "rewound_to": target}
    prior = stored
    data["stored_offset"] = target
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"applied": True, "reason": "rewound offset %d -> %d (channel restart follows)"
            % (prior, target), "dry_run": False, "rewound_to": target,
            "revert": "restore stored_offset=%d" % prior}


def lf6_park_process(unit, ledger, dry_run=True):
    """LF-6: park a crash-looping process unit on a process-breaker trip. STOP + park
    (visible-red; never silently respawns). Reversible via unpark. Returns
    {applied, reason}."""
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would STOP + park unit '%s'" % unit,
                "dry_run": True}
    BR.trip(unit, "process", ledger, park=True)
    return {"applied": True, "reason": "parked unit '%s' (visible-red; no auto-respawn)" % unit,
            "dry_run": False, "revert": "loop-companion.sh unpark %s" % unit}


# --------------------------------------------------------------------------- #
# apply dispatch (honors DRY_RUN + the healer self-breaker)
# --------------------------------------------------------------------------- #
def apply(plan_dict, ledger, armed, executors, verify_failed_last=False):
    """Apply a prepared plan. Returns {status, detail, escalate}.
      status: 'planned' (DRY_RUN or tier>1), 'applied', 'refused', 'escalated'
    The healer self-breaker is consulted FIRST: a target fixed too often or whose last
    fix failed verify is NOT auto-fixed again - it escalates (spec 5.1)."""
    br = BR.load_breakers()
    unit = plan_dict.get("unit") or plan_dict.get("loop_class")
    tier = plan_dict.get("tier", 3)
    fc = plan_dict.get("fix_class")

    if tier != 1:
        return {"status": "planned", "detail": "tier %s -> proposal only (%s)"
                % (tier, "operator stamp" if tier == 2 else "propose-and-hold"),
                "escalate": tier == 3}

    tripped, why = BR.healer_breaker_trips(unit, ledger, br, verify_failed=verify_failed_last)
    if tripped:
        return {"status": "escalated", "detail": "healer breaker: %s" % why, "escalate": True}

    if not armed:
        # DRY_RUN observe-only: PLAN, mutate nothing.
        ex = executors.get(fc)
        detail = "DRY_RUN"
        if ex:
            r = ex(dry_run=True)
            detail = "DRY_RUN: %s" % r.get("reason", "")
        return {"status": "planned", "detail": detail, "escalate": False}

    ex = executors.get(fc)
    if ex is None:
        return {"status": "refused", "detail": "no executor wired for %s" % fc, "escalate": True}
    r = ex(dry_run=False)
    if r.get("applied"):
        return {"status": "applied", "detail": r.get("reason"), "escalate": False,
                "revert": r.get("revert")}
    return {"status": "refused", "detail": r.get("reason"), "escalate": False}


def self_test():
    import tempfile
    print("[loop_killcards] self-test: plan, LF-1 lock, LF-4 cron, DRY_RUN byte-identical, healer breaker")
    from loop_ledger import Ledger

    # plan resolves a Tier-1 fix class for a known loop class
    p = plan({"loop_class": "LP-B1", "finding_id": 7})
    assert p["fix_class"] == "LF-6" and p["tier"] == 1 and "unpark --finding 7" in p["revert_cmd"]
    p3 = plan({"loop_class": "LP-D1", "finding_id": 9})   # empty-prompt cron = propose-and-hold
    assert p3["fix_class"] is None and p3["tier"] == 3
    print("  plan case: PASS (LP-B1->LF-6 tier1; LP-D1->propose-and-hold tier3)")

    with tempfile.TemporaryDirectory() as td:
        # LF-1: a DEAD-pid JSON lock is archived; a LIVE-pid lock is refused; a
        # non-JSON lock is refused (never parsed as a bare pid).
        dead = Path(td) / "dead.lock"
        dead.write_text(json.dumps({"pid": 2147480000}), encoding="utf-8")  # impossible pid
        r = lf1_archive_stale_lock(dead, dry_run=False)
        assert r["applied"] and not dead.exists() and Path(str(dead) + ".archived").exists()
        live = Path(td) / "live.lock"
        live.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        r2 = lf1_archive_stale_lock(live, dry_run=False)
        assert not r2["applied"] and "ALIVE" in r2["reason"] and live.exists()
        bad = Path(td) / "bad.lock"
        bad.write_text("PID=1234 not json", encoding="utf-8")
        r3 = lf1_archive_stale_lock(bad, dry_run=False)
        assert not r3["applied"] and "not JSON" in r3["reason"] and bad.exists()
        print("  LF-1 case: PASS (dead archived; live refused; non-JSON refused)")

        # LF-4: DRY_RUN leaves the cron file BYTE-IDENTICAL; armed sets enabled=false.
        cron = Path(td) / "crons.json"
        cron.write_text(json.dumps({"crons": [{"id": "resume", "enabled": True}]}, indent=2),
                        encoding="utf-8")
        before = cron.read_bytes()
        d = lf4_disable_cron(cron, "resume", dry_run=True)
        assert not d["applied"] and cron.read_bytes() == before  # D-DRYRUN invariant
        a = lf4_disable_cron(cron, "resume", dry_run=False)
        assert a["applied"] and json.loads(cron.read_text())["crons"][0]["enabled"] is False
        print("  LF-4 case: PASS (DRY_RUN byte-identical; armed disables, never deletes)")

        # LF-2: a corrupted (advanced-past-pending) offset rewinds to oldest-1.
        off = Path(td) / "offset.json"
        off.write_text(json.dumps({"stored_offset": 100450, "oldest_pending_update_id": 100400}),
                       encoding="utf-8")
        ob = off.read_bytes()
        assert lf2_rewind_offset(off, dry_run=True)["rewound_to"] == 100399 and off.read_bytes() == ob
        r2 = lf2_rewind_offset(off, dry_run=False)
        assert r2["applied"] and json.loads(off.read_text())["stored_offset"] == 100399
        print("  LF-2 case: PASS (DRY_RUN byte-identical; armed rewinds to oldest-1)")

        led = Ledger(Path(td) / "loop-protection")
        # DRY_RUN apply mutates nothing and reports planned
        execs = {"LF-4": lambda dry_run: lf4_disable_cron(cron, "resume", dry_run=dry_run)}
        planned = apply({"loop_class": "LP-A4", "fix_class": "LF-4", "tier": 1, "unit": "resume"},
                        led, armed=False, executors=execs)
        assert planned["status"] == "planned" and "DRY_RUN" in planned["detail"]
        # healer breaker: after 3 recorded fixes on a unit, apply escalates instead
        for _ in range(3):
            led.record_fix(None, "LF-6", unit="cc-app", what="park", dry_run=False)
        esc = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "cc-app"},
                    led, armed=True, executors={"LF-6": lambda dry_run: {"applied": True}})
        assert esc["status"] == "escalated" and esc["escalate"] is True
        # verify-failed-last also short-circuits to escalate (never a 2nd auto-attempt)
        esc2 = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "fresh"},
                     led, armed=True, executors={"LF-6": lambda dry_run: {"applied": True}},
                     verify_failed_last=True)
        assert esc2["status"] == "escalated"
        led.close()
        print("  apply case: PASS (DRY_RUN plans; healer breaker escalates >3/24h & verify-fail)")

    print("[loop_killcards] self-test: PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Loop Protection kill cards.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
