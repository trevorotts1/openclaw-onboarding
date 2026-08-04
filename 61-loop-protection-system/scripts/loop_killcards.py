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
import subprocess
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


def _agent_id_from_session_key(session_key):
    """Best-effort agentId extraction from a session key of the CONFIRMED
    live-box shape 'agent:<agentId>:<channel>:<mode>:<kind>:<chatId>' (real
    sample: 'agent:dept-master-orchestrator:telegram:default:direct:
    8606145708'). Falls back to the full session key when the shape doesn't
    match (never a crash, never a guess beyond this one documented
    convention) - the gateway RPC's `agentId` param is best-effort exactly
    like the RPC call itself; a wrong agentId degrades to the RPC returning
    an error/no-op, never a crash, and the park below still applies either
    way."""
    parts = str(session_key).split(":")
    if len(parts) >= 2 and parts[0] == "agent":
        return parts[1]
    return str(session_key)


def _sessions_abort_via_gateway_rpc(session_key, timeout=10):
    """The native sessions.abort RPC, called via `openclaw gateway call
    sessions.abort --params '{"key":..., "agentId":...}'`.

    CONFIRMED on a live box (OpenClaw 2026.7.1-2, 2026-08-04): `openclaw
    sessions --help` lists ONLY cleanup / compact / export-trajectory / list -
    there is NO `sessions abort` CLI subcommand. The only real path is the
    generic gateway RPC caller (`openclaw gateway --help` -> `call  Call a
    Gateway method`). This exact form was independently exercised live and,
    against a session with no active run, returned
    {"ok":true,"abortedRunId":null,"status":"no-active-run"} - a documented
    SAFE no-op, so it is safe to call speculatively (the earlier
    `sessions abort` CLI form would have silently returned a non-zero exit on
    EVERY call - a defect that FAILED SOFT into never aborting anything while
    still reporting the fix as applied via the park; that is exactly the
    silent-no-op failure mode this skill exists to prevent, so the wrong
    command is corrected here, not left as a tolerated fallback).

    `LOOP_NO_PROBES=1` (the hermetic-test env seam every other subprocess
    probe in this skill honors) short-circuits to a no-op BEFORE any
    subprocess runs, so a caller that forgets to inject `abort_fn` still
    never touches a real gateway. On ANY OTHER miss (no binary, non-zero
    exit, bad JSON) returns {ok: False} - never a crash. The caller still
    parks the source unit regardless of this result: the park is what
    actually breaks the loop, and the RPC call is a best-effort courtesy."""
    if os.environ.get("LOOP_NO_PROBES", "") == "1":
        return {"ok": False}
    binpath = os.environ.get("OPENCLAW_BIN") or shutil.which("openclaw")
    if not binpath:
        return {"ok": False}
    params = json.dumps({"key": str(session_key),
                         "agentId": _agent_id_from_session_key(session_key)})
    try:
        proc = subprocess.run(
            [binpath, "gateway", "call", "sessions.abort", "--params", params],
            capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"ok": False}
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return {"ok": False}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"ok": False}


def _rpc_signals_success_or_noop(result):
    """True when the sessions.abort RPC result is either a real success
    (ok:true with an abortedRunId) or the documented SAFE no-op (ok:true,
    abortedRunId:null, status:'no-active-run' - verified live: a session with
    nothing to abort). BOTH are 'the RPC did its job'; NEITHER is a failure,
    and neither should ever read as one downstream (no retry storm, no
    false-failed-fix in the ledger) - only the healer breaker (>3 fixes on
    the same target/24h, or any fix whose verify failed once) governs whether
    LF-9 fires again, never this result. Checks `status` independently of
    `ok` (not just as a fallback) so a differently-shaped future response
    that carries `status:"no-active-run"` without an explicit `ok` still
    reads as the documented safe no-op, never a failure."""
    if not isinstance(result, dict):
        return False
    if str(result.get("status") or "") == "no-active-run":
        return True
    return bool(result.get("ok"))


def lf9_abort_cross_run_resend(source_session_key, ledger, dry_run=True, abort_fn=None):
    """LF-9: abort the resending SOURCE session's in-flight run via the native
    sessions.abort RPC (openclaw gateway call sessions.abort), breaking a
    confirmed cross-run resend loop (LP-A8) at its driver - the orchestrator
    that keeps firing a brand-new top-level run every time sessions_send's
    local 30s fallback timeout is misread as delivery failure. Calling
    sessions.abort with NO active run is a documented safe no-op
    ({ok:true, abortedRunId:null, status:"no-active-run"} - verified live),
    so this never errors on a source that has already moved on by the time
    the breaker trips; the PARK below is what actually stops the recurrence,
    regardless of the RPC outcome. NEVER pkill node, NEVER restart the
    gateway - this touches ONLY the one session named.

    A 600s action cooldown (config/thresholds.json d7_cross_run_resend
    .action_cooldown_seconds) bounds how often this may re-fire on the SAME
    source: a second call inside the window is REFUSED (never re-applied),
    recorded via the ledger's existing digest/dedup primitive (the same one
    tick()'s alert dedup uses) rather than a new mechanism. `abort_fn` is
    injectable (defaults to the gateway-RPC probe below) so tests never touch
    a real gateway. Returns {applied, reason}."""
    cooldown_key = "resend-cooldown|%s" % source_session_key
    cooldown_seconds = C.load_skill_config("thresholds.json")["d7_cross_run_resend"]["action_cooldown_seconds"]
    if dry_run:
        return {"applied": False,
                "reason": "DRY_RUN: would call sessions.abort on '%s' + park "
                          "(no-op-safe if nothing active)" % source_session_key,
                "dry_run": True}
    if ledger.recent_digest(cooldown_key, cooldown_seconds / 3600.0):
        return {"applied": False,
                "reason": "action cooldown active on '%s' (< %ds since the last "
                          "abort+park; never re-fire the breaker faster than the "
                          "proven-safe cadence)" % (source_session_key, cooldown_seconds),
                "dry_run": False}
    fn = abort_fn or _sessions_abort_via_gateway_rpc
    try:
        result = fn(source_session_key)
    except Exception as exc:  # noqa: BLE001 - an RPC miss is data, never a crash
        result = {"ok": False, "error": str(exc)}
    BR.trip(source_session_key, "resend", ledger, park=True)
    ledger.record_digest("resend-cooldown", cooldown_key, payload="applied")
    if isinstance(result, dict) and str(result.get("status") or "") == "no-active-run":
        rpc_detail = "no-active-run (documented safe no-op - nothing to abort)"
    elif _rpc_signals_success_or_noop(result):
        rpc_detail = "aborted runId=%s" % (result.get("abortedRunId") if isinstance(result, dict) else None)
    else:
        rpc_detail = "unreachable/unexpected response (safe either way - the park below is what actually breaks the loop)"
    return {"applied": True,
            "reason": "sessions.abort RPC on '%s' -> %s; source parked "
                      "(visible-red; no auto-respawn)" % (source_session_key, rpc_detail),
            "dry_run": False,
            "revert": "loop-companion.sh unpark %s" % source_session_key}


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


# --------------------------------------------------------------------------- #
# Operator-commanded execution of a prepared kill card by finding id (spec 9.1).
# An explicit `fix`/`approve` IS the operator's word for THIS finding, so the one
# config-FREE, deterministic act - the process-unit park (LF-6) - executes for real
# against the ledger. Every config-touching class (LF-1/2/4/5/7) and every Tier-2
# config-shape change is PREPARED here (exact command + one-line revert) and applied
# ON-BOX via the maintenance path, NEVER auto-applied off-box: an honest hand-off,
# not a stub that claims success.
# --------------------------------------------------------------------------- #
def run_fix(ledger, finding_id, box="box", approve=False):
    """Execute (LF-6) or prepare (everything else) the kill card for a finding.
    Returns (result_dict, exit_code) with the ledger exit contract (0/2/3)."""
    f = ledger.get_finding(finding_id)
    if not f:
        return {"ok": False, "reason": "finding %s not found in the ledger" % finding_id}, 3
    kc = plan({"loop_class": f.get("loop_class"), "finding_id": finding_id}, box=box)
    kc["unit"] = f.get("unit")
    fc = kc.get("fix_class")
    tier = kc.get("tier")
    if approve and tier != 2:
        return {"ok": False, "action": "reject",
                "reason": "approve is for a Tier-2 proposal; finding %s is tier %s"
                          % (finding_id, tier), "prepared": kc}, 2
    # config-FREE, deterministic act: park the crash-looping process unit (LF-6).
    if fc == "LF-6":
        unit = f.get("unit")
        if not unit:
            return {"ok": False, "reason": "finding %s carries no unit to park" % finding_id}, 2
        r = lf6_park_process(unit, ledger, dry_run=False)
        applied = bool(r.get("applied"))
        ledger.record_fix(finding_id, fc, unit=unit, what=kc.get("what"),
                          verify_outcome="applied" if applied else "refused",
                          revert_cmd=kc.get("revert_cmd"), dry_run=False)
        ledger.set_finding_state(finding_id, "fixed" if applied else "escalated")
        return {"ok": applied, "action": "fix", "fix_class": fc, "unit": unit,
                "applied": applied, "detail": r.get("reason"),
                "revert_cmd": kc.get("revert_cmd")}, 0
    # config-FREE, deterministic act: abort the resending session + park it
    # (LF-9, LP-A8's sessions.abort + park sibling of LF-6's process park).
    if fc == "LF-9":
        unit = f.get("unit")
        if not unit:
            return {"ok": False,
                    "reason": "finding %s carries no unit (source session) to abort" % finding_id}, 2
        r = lf9_abort_cross_run_resend(unit, ledger, dry_run=False)
        applied = bool(r.get("applied"))
        ledger.record_fix(finding_id, fc, unit=unit, what=kc.get("what"),
                          verify_outcome="applied" if applied else "refused",
                          revert_cmd=kc.get("revert_cmd"), dry_run=False)
        ledger.set_finding_state(finding_id, "fixed" if applied else "escalated")
        return {"ok": applied, "action": "fix", "fix_class": fc, "unit": unit,
                "applied": applied, "detail": r.get("reason"),
                "revert_cmd": kc.get("revert_cmd")}, 0
    # no Tier-1 kill card at all -> propose-and-hold (Rescue Rangers).
    if fc is None:
        return {"ok": False, "action": "hold", "fix_class": None, "tier": tier,
                "reason": "no Tier-1 kill card for %s; propose-and-hold -> escalate to "
                          "Rescue Rangers" % f.get("loop_class"),
                "prepared": kc, "revert_cmd": kc.get("revert_cmd")}, 0
    # config-touching Tier-1 / Tier-2: PREPARE the exact command + revert; apply ON-BOX.
    verb = "approved-tier2" if approve else "prepared"
    return {"ok": True, "action": verb, "fix_class": fc, "tier": tier, "unit": f.get("unit"),
            "reason": "%s: fix class %s touches box config; apply ON-BOX via the maintenance "
                      "path (docker exec -u node on VPS), never auto-applied off-box. The exact "
                      "command + one-line revert are prepared below." % (verb, fc),
            "prepared": kc, "revert_cmd": kc.get("revert_cmd")}, 0


def self_test():
    import tempfile
    print("[loop_killcards] self-test: plan, LF-1 lock, LF-4 cron, DRY_RUN byte-identical, healer breaker")
    from loop_ledger import Ledger

    # plan resolves a Tier-1 fix class for a known loop class
    p = plan({"loop_class": "LP-B1", "finding_id": 7})
    assert p["fix_class"] == "LF-6" and p["tier"] == 1 and "unpark --finding 7" in p["revert_cmd"]
    p3 = plan({"loop_class": "LP-D1", "finding_id": 9})   # empty-prompt cron = propose-and-hold
    assert p3["fix_class"] is None and p3["tier"] == 3
    p4 = plan({"loop_class": "LP-A8", "finding_id": 11})  # cross-run resend = LF-9 tier1
    assert p4["fix_class"] == "LF-9" and p4["tier"] == 1 and "unpark --finding 11" in p4["revert_cmd"]
    print("  plan case: PASS (LP-B1->LF-6 tier1; LP-D1->propose-and-hold tier3; LP-A8->LF-9 tier1)")

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

        # LF-9: abort-and-park the resending source session (LP-A8, the
        # 2026-08-04 cross-run resend incident). The RPC is INJECTED (abort_fn)
        # so this drill touches no real gateway; the EXACT response shape
        # verified live against a session with no active run -
        # {"ok":true,"abortedRunId":null,"status":"no-active-run"} - must be
        # treated as a SUCCESSFUL no-op, never a failed fix and never a
        # trigger to retry. DRY_RUN mutates nothing. A second call inside the
        # 600s action cooldown is REFUSED, never re-applied.
        led9 = Ledger(Path(td) / "loop-protection-lf9")

        def _fake_abort_noop(key):
            return {"ok": True, "abortedRunId": None, "status": "no-active-run"}

        planned9 = lf9_abort_cross_run_resend("agent:orch:main", led9, dry_run=True,
                                              abort_fn=_fake_abort_noop)
        assert not planned9["applied"] and "DRY_RUN" in planned9["reason"]
        r9 = lf9_abort_cross_run_resend("agent:orch:main", led9, dry_run=False,
                                        abort_fn=_fake_abort_noop)
        assert r9["applied"], "the documented no-active-run no-op must NOT read as a failed fix"
        assert "no-active-run" in r9["reason"] and "safe no-op" in r9["reason"]
        assert any(row["unit"] == "agent:orch:main" for row in led9.parked_units())
        r9b = lf9_abort_cross_run_resend("agent:orch:main", led9, dry_run=False,
                                         abort_fn=_fake_abort_noop)
        assert not r9b["applied"] and "cooldown" in r9b["reason"]
        led9.close()

        # A genuine abort (an active run really gets aborted) is ALSO applied,
        # with the runId surfaced in the detail - a different park unit avoids
        # the cooldown set above.
        led9b = Ledger(Path(td) / "loop-protection-lf9b")

        def _fake_abort_real(key):
            return {"ok": True, "abortedRunId": "run-xyz"}

        r9c = lf9_abort_cross_run_resend("agent:other-orch:main", led9b, dry_run=False,
                                         abort_fn=_fake_abort_real)
        assert r9c["applied"] and "run-xyz" in r9c["reason"]
        led9b.close()

        # An unreachable/failing RPC still applies (the park is what actually
        # breaks the loop; the RPC is a best-effort courtesy) but is labeled
        # distinctly, never claimed as a successful abort.
        led9c = Ledger(Path(td) / "loop-protection-lf9c")

        def _fake_abort_unreachable(key):
            return {"ok": False}

        r9d = lf9_abort_cross_run_resend("agent:third-orch:main", led9c, dry_run=False,
                                         abort_fn=_fake_abort_unreachable)
        assert r9d["applied"] and "unreachable" in r9d["reason"]
        led9c.close()

        assert _agent_id_from_session_key(
            "agent:dept-master-orchestrator:telegram:default:direct:8606145708") \
            == "dept-master-orchestrator"
        assert _agent_id_from_session_key("not-agent-shaped") == "not-agent-shaped"
        assert _rpc_signals_success_or_noop({"ok": True, "abortedRunId": "r1"})
        assert _rpc_signals_success_or_noop({"status": "no-active-run"})  # ok absent entirely
        assert not _rpc_signals_success_or_noop({"ok": False})
        assert not _rpc_signals_success_or_noop("not-a-dict")
        print("  LF-9 case: PASS (DRY_RUN plans; the verified no-active-run no-op reads "
              "as a SUCCESSFUL fix, never a failure; a real abort surfaces its runId; "
              "an unreachable RPC still parks but is labeled distinctly; cooldown "
              "refuses a second call; agentId extraction + response-shape predicate "
              "both correct)")

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

        # run_fix: `fix <id>` on an LP-B1 finding PARKS the unit for real (config-free
        # LF-6) and records a one-line revert; a config-touching class is PREPARED, not
        # applied; a Tier-3 class holds. This is the operator `fix`/`approve` path.
        led = Ledger(Path(td) / "loop-protection-fix")
        fid = led.record_finding("LP-B1", "P1", unit="cc-app", detail="storm", tier=1)
        res, rc = run_fix(led, fid)
        assert rc == 0 and res["ok"] and res["fix_class"] == "LF-6"
        assert any(r["unit"] == "cc-app" for r in led.parked_units())
        assert any(r["unit"] == "cc-app" and r["breaker"] == "process"
                   for r in led.tripped_breakers())
        assert "unpark --finding %d" % fid in res["revert_cmd"]
        assert led.get_finding(fid)["state"] == "fixed"
        cid = led.record_finding("LP-A4", "P1", unit="resume", detail="cron", tier=1)
        cres, crc = run_fix(led, cid)   # LF-4 is config-touching -> prepared, not applied
        assert crc == 0 and cres["action"] == "prepared" and cres["fix_class"] == "LF-4"
        hid = led.record_finding("LP-D1", "P2", unit="x", detail="hold", tier=3)
        hres, _ = run_fix(led, hid)     # no Tier-1 kill card -> hold
        assert hres["action"] == "hold" and hres["fix_class"] is None
        miss, mrc = run_fix(led, 999999)  # unknown finding -> not found (rc 3)
        assert mrc == 3 and miss["ok"] is False
        led.close()
        print("  run_fix case: PASS (LF-6 parks for real+revertible; config prepared; hold; not-found=3)")

    print("[loop_killcards] self-test: PASS")
    return 0


# --------------------------------------------------------------------------- #
# CLI: operator `fix` / `approve` / `plan` by finding id (routed via loop-companion.sh).
# --------------------------------------------------------------------------- #
def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection kill cards.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--state-dir",
                    help="override the ledger state dir (default $LOOP_STATE_DIR)")
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (
            ("fix", "operator-commanded execution of a prepared kill card by finding id"),
            ("approve", "approve a Tier-2 proposal by finding id (prepares the on-box command)"),
            ("plan", "print the prepared kill card for a finding id (read-only)")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("finding_id", type=int, help="the ledger finding id")

    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.cmd:
        ap.print_help()
        return 0

    from loop_ledger import Ledger  # local import keeps self-test path import-light
    state_dir = Path(a.state_dir) if getattr(a, "state_dir", None) else None
    ledger = Ledger(state_dir)
    try:
        box = ledger.get_meta("box", "box")
        if a.cmd == "plan":
            f = ledger.get_finding(a.finding_id)
            if not f:
                sys.stderr.write("REFUSED [loop_killcards]: finding %s not found\n" % a.finding_id)
                return 3
            kc = plan({"loop_class": f.get("loop_class"), "finding_id": a.finding_id}, box=box)
            kc["unit"] = f.get("unit")
            print(json.dumps(kc, sort_keys=True))
            return 0
        result, rc = run_fix(ledger, a.finding_id, box=box, approve=(a.cmd == "approve"))
        print(json.dumps(result, sort_keys=True))
        return rc
    finally:
        ledger.close()


if __name__ == "__main__":
    sys.exit(_cli())
