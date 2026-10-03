#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_breaker.py
# Circuit breakers - the headline protection (spec Section 5.1).
# -----------------------------------------------------------------------------
# A breaker = (unit, window, max-events, trip-action). Five breakers ship:
#   process  D1 restart velocity   -> `pm2 stop <unit>` on an ARMED run (pm2 units only);
#                                     the OpenClaw gateway itself is ALERT-ONLY, never stopped
#   turn     D2 paid-token burn    -> heartbeat allowlist enforce + park cron (never model)
#   retry    D3 identical-signature -> park resumable + escalate (doctrine step 4)
#   cron     D4 re-fire storm      -> disable cron (not delete)
#   healer   the watchdog's OWN fixes -> stop fixing that target, escalate (session-health law)
#
# Every ceiling is a SAFETY CAP under Skill 60 Signal S4: a raise without an operator
# stamp is a P1 (spec 5.1).
#
# WHAT "PARK" MEANS (SKS-002 / Fix 4 - this file used to overclaim): `trip(park=True)`
# and `park()` write ONE ledger flag (breaker_state.parked=1) that the status screens
# show visible-red. That flag stops NOTHING on the box. A unit is only really stopped by
# `stop_and_park()`, which runs `pm2 stop <unit>` and records the state `stopped`; when no
# real stop exists the recorded state is `parked-flag` and the finding is NEVER `fixed`.
# `unpark_unit()` is the matching revert (`pm2 start <unit>` for a `stopped` unit).
#
# State lives in the ledger (breaker_state / fix_actions). Deterministic, stdlib
# only, NO model call, NO network.
# =============================================================================
"""loop_breaker.py - circuit breakers for the Loop Protection System."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
from loop_ledger import Ledger  # noqa: E402

# Exit contract mirrors the ledger CLI: 0 OK, 2 usage, 3 not-found / predicate false.
EX_OK, EX_USAGE, EX_FALSE = 0, 2, 3


def load_breakers():
    return C.load_skill_config("breakers.json")["breakers"]


def process_breaker_trips(unit, delta_restarts, day_restarts, breakers):
    """True when the process breaker should trip for `unit`."""
    b = breakers["process"]
    return (delta_restarts >= b["max_events_per_window"]
            or day_restarts >= b["max_events_per_day"])


def retry_breaker_trips(consecutive_identical, breakers):
    b = breakers["retry"]
    return consecutive_identical >= b["max_consecutive"]


def cron_breaker_trips(actual_per_day, declared_per_day, breakers):
    b = breakers["cron"]
    if not declared_per_day:
        return False
    declared_per_day = max(declared_per_day, 1.0)  # same 1/day floor as D4: weekly@1 is normal
    return actual_per_day > declared_per_day * b["overfire_multiple_of_declared"]


def resend_breaker_trips(distinct_run_count, breakers):
    """True when the resend breaker should trip: >= N DISTINCT run ids carrying
    the SAME normalized cross-run payload for the SAME (source,target) pair
    inside the rolling window (LP-A10, the 2026-08-04 cross-run resend
    incident). Mirrors D7's own p1_repeat threshold from thresholds.json as an
    INDEPENDENT ceiling copy in breakers.json - the same S4 cap-raise-without-
    stamp pattern every other breaker predicate here follows."""
    b = breakers["resend"]
    return distinct_run_count >= b["max_events_per_window"]


def healer_breaker_trips(unit, ledger, breakers, verify_failed=False):
    """The healer's self-breaker: > N fixes on the SAME target / 24h OR any fix-verify
    failure = STOP fixing that target (spec 5.1). Returns (tripped, reason)."""
    b = breakers["healer"]
    if verify_failed and b.get("trip_on_any_verify_failure", True):
        return True, "a fix-verify failed once on '%s' (healer breaker: never a second auto-attempt)" % unit
    n = ledger.fixes_for_target_since(unit, 24)
    if n >= b["max_fixes_per_target_per_day"]:
        return True, ("%d fixes on '%s' in 24h >= %d (healer-loop suspected)"
                      % (n, unit, b["max_fixes_per_target_per_day"]))
    return False, ""


def trip(unit, breaker_name, ledger, park=True):
    """Record a breaker trip in the ledger. `park=True` ALSO sets the ledger's parked flag.
    That flag is a visible-red STATUS MARKER ONLY: nothing outside the status screens reads
    it and it stops no process and pauses no session. Use `stop_and_park()` for a real stop."""
    return ledger.upsert_breaker(unit, breaker_name, tripped=1,
                                 parked=1 if park else 0)


def park(unit, ledger):
    """Operator `park`: set the ledger parked-flag only (stops nothing)."""
    return ledger.upsert_breaker(unit, "manual", parked=1, tripped=0)


# --------------------------------------------------------------------------- #
# REAL stop / start of a pm2 unit (SKS-002 / Fix 4).
#   * pm2 units only. The OpenClaw gateway is NEVER stopped here: October's built-in
#     crash-loop breaker already suppresses channel auto-start after 3 unclean boots in 5
#     minutes (OpenClaw docs/gateway/restart-recovery.md), so the gateway case is ALERT-ONLY.
#   * `pm2 stop <name>` / `pm2 start <name>` print a process table and NO environment; their
#     output is discarded, only the exit code is read. Argv list, never a shell.
#   * Seam: $LOOP_PM2_BIN names the pm2 binary (a hermetic test points it at a stub). With
#     LOOP_NO_PROBES=1 and no $LOOP_PM2_BIN there is NO pm2 at all, so a drill that forgot to
#     inject a stub can never stop a real process.
# --------------------------------------------------------------------------- #
STOPPED_META_PREFIX = "real-stop|"   # ledger meta: this skill really stopped <unit> via pm2
STATE_STOPPED = "stopped"
STATE_PARKED_FLAG = "parked-flag"    # ledger flag only; NOTHING stopped; never `fixed`

# pm2 unit names this skill will pass to pm2: a conservative charset that cannot be an
# option (no leading '-'); `all` (pm2's every-process selector) is refused separately.
_PM2_UNIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]*$")
_GATEWAY_UNIT_RE = re.compile(r"^(gateway(:\d+)?|openclaw[-_]?gateway|ai\.openclaw\..+)$", re.I)


def is_gateway_unit(unit):
    """True for the OpenClaw gateway under any name this skill sees (`gateway`,
    `gateway:18789`, `openclaw-gateway`, the launchd label `ai.openclaw.*`)."""
    return bool(_GATEWAY_UNIT_RE.match(str(unit or "").strip()))


def _pm2_bin():
    env = os.environ.get("LOOP_PM2_BIN", "").strip()
    if env:
        return env
    if os.environ.get("LOOP_NO_PROBES", "") == "1":
        return None
    return shutil.which("pm2")


def _pm2_run(verb, unit, timeout=30):
    """`pm2 <verb> <unit>` (verb is stop|start). Returns {ok, reason}; never raises; the
    command's output is discarded (rc only)."""
    unit = str(unit or "").strip()
    if verb not in ("stop", "start") or not _PM2_UNIT_RE.match(unit) or unit.lower() == "all":
        return {"ok": False, "reason": "refused to pass unit name %r to pm2" % unit}
    binpath = _pm2_bin()
    if not binpath:
        return {"ok": False, "reason": "no pm2 binary available (LOOP_NO_PROBES=1 or pm2 not installed)"}
    try:
        proc = subprocess.run([binpath, verb, unit], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": "pm2 %s could not run (%s)" % (verb, type(exc).__name__)}
    if proc.returncode != 0:
        return {"ok": False, "reason": "pm2 %s %s exited %d (unit not found or not stoppable)"
                % (verb, unit, proc.returncode)}
    return {"ok": True, "reason": "pm2 %s %s exited 0" % (verb, unit)}


def pm2_stop(unit):
    return _pm2_run("stop", unit)


def pm2_start(unit):
    return _pm2_run("start", unit)


def stop_and_park(unit, ledger, stop_fn=None):
    """The ONLY thing here that really stops a unit. Returns {state, stopped, reason}.
      gateway unit      -> state `parked-flag`, ALERT-ONLY, nothing is run
      pm2 stop rc == 0  -> state `stopped`; ledger remembers it so `unpark_unit` can start it
      anything else     -> state `parked-flag`: a ledger flag, NOTHING stopped
    Never raises (a stop_fn that throws is a failed stop, not a crash)."""
    if is_gateway_unit(unit):
        trip(unit, "process", ledger, park=True)
        return {"state": STATE_PARKED_FLAG, "stopped": False,
                "reason": "ALERT-ONLY: '%s' is the OpenClaw gateway and is never stopped by this "
                          "skill (OpenClaw's built-in crash-loop breaker suppresses channel "
                          "auto-start after 3 unclean boots in 5 minutes). Recorded "
                          "state=parked-flag: a ledger flag only, NOTHING was stopped, the "
                          "finding stays open" % unit}
    try:
        r = (stop_fn or pm2_stop)(unit)
    except Exception as exc:  # noqa: BLE001 - a stop miss is data, never a crash
        r = {"ok": False, "reason": "stop raised %s" % type(exc).__name__}
    trip(unit, "process", ledger, park=True)
    if isinstance(r, dict) and r.get("ok"):
        ledger.set_meta(STOPPED_META_PREFIX + str(unit), "pm2")
        return {"state": STATE_STOPPED, "stopped": True,
                "reason": "ran `pm2 stop %s` (REAL stop). Recorded state=stopped; "
                          "`unpark` runs `pm2 start %s`" % (unit, unit)}
    why = (r or {}).get("reason", "stop failed") if isinstance(r, dict) else "stop failed"
    return {"state": STATE_PARKED_FLAG, "stopped": False,
            "reason": "no real stop available for '%s' (%s). Recorded state=parked-flag: a "
                      "ledger flag only, NOTHING was stopped, the finding stays open"
                      % (unit, why)}


def unpark(unit, ledger):
    """Clear the parked/tripped LEDGER state on EVERY breaker row for a unit. Ledger only;
    `unpark_unit` is the operator revert that also restarts a unit this skill stopped."""
    cleared = 0
    for row in ledger.parked_units():
        if row["unit"] == unit:
            ledger.upsert_breaker(unit, row["breaker"], parked=0, tripped=0, event_count=0)
            cleared += 1
    # also clear a tripped-but-unparked row
    for row in ledger.tripped_breakers():
        if row["unit"] == unit:
            ledger.upsert_breaker(unit, row["breaker"], parked=0, tripped=0)
            cleared += 1
    return cleared


def unpark_unit(unit, ledger, start_fn=None):
    """Operator revert. If this skill really stopped `unit` (meta set by stop_and_park) run
    `pm2 start <unit>` FIRST; when that fails nothing is cleared (the unit stays visible-red
    and the revert can be retried). Returns {ok, cleared, restarted, reason}."""
    key = STOPPED_META_PREFIX + str(unit)
    restarted = False
    if ledger.get_meta(key):
        try:
            r = (start_fn or pm2_start)(unit)
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "reason": "start raised %s" % type(exc).__name__}
        if not (isinstance(r, dict) and r.get("ok")):
            why = r.get("reason", "start failed") if isinstance(r, dict) else "start failed"
            return {"ok": False, "cleared": 0, "restarted": False,
                    "reason": "`pm2 start %s` failed (%s); unit left parked, retry unpark" % (unit, why)}
        ledger.set_meta(key, "")
        restarted = True
    return {"ok": True, "cleared": unpark(unit, ledger), "restarted": restarted,
            "reason": "ran `pm2 start %s`" % unit if restarted else "ledger flag cleared (nothing was stopped)"}


def cap_raise_without_stamp(current_ceiling, shipped_ceiling):
    """A Loop Protection ceiling loosened beyond its shipped default WITHOUT an
    operator stamp is itself a P1 (spec 5.1/5.2: the system watches the watcher).
    Returns True when current > shipped (a raise)."""
    try:
        return float(current_ceiling) > float(shipped_ceiling)
    except (TypeError, ValueError):
        return False


def _selftest_stub_bin(path, log, stdout=""):
    """Test seam: an executable stub that APPENDS its argv to `log`, prints `stdout`, and exits
    with the integer in `log`+'.rc' (default 0). Lets a hermetic test prove EXACTLY which
    external commands a code path runs, without ever touching a real pm2/openclaw."""
    body = '#!/bin/sh\necho "$@" >> "%s"\n' % log
    if stdout:
        body += "echo '%s'\n" % stdout
    body += '[ -f "%s.rc" ] && exit "$(cat "%s.rc")"\nexit 0\n' % (log, log)
    Path(path).write_text(body, encoding="utf-8")
    os.chmod(path, 0o755)


def _selftest_calls(log):
    """argv lines a stub recorded, [] when it was never run."""
    try:
        return [ln for ln in Path(log).read_text(encoding="utf-8").splitlines() if ln]
    except OSError:
        return []


def self_test():
    # Hermetic: no pm2 may ever be reachable except an injected stub, whatever the caller's env.
    saved = {k: os.environ.get(k) for k in ("LOOP_NO_PROBES", "LOOP_PM2_BIN")}
    os.environ["LOOP_NO_PROBES"] = "1"
    os.environ.pop("LOOP_PM2_BIN", None)
    try:
        return _self_test_body()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _self_test_body():
    import tempfile
    print("[loop_breaker] self-test: process/retry/cron/healer trips, park/unpark, real stop, cap-raise")
    br = load_breakers()

    assert process_breaker_trips("cc-app", 12, 900, br) is True   # 12/tick >= 10
    assert process_breaker_trips("cc-app", 3, 40, br) is True      # 40/day >= 40
    assert process_breaker_trips("cc-app", 2, 5, br) is False
    print("  process case: PASS (trips at 10/tick or 40/day)")

    assert retry_breaker_trips(5, br) is True and retry_breaker_trips(4, br) is False
    assert cron_breaker_trips(96, 1, br) is True   # 96/day vs @daily bound 1, > 2x
    assert cron_breaker_trips(2, 96, br) is False  # firing at declared rate
    # the 1/day floor (same bug as D4): weekly bound 0.14/day, ONE fire is normal, 3 is not
    assert cron_breaker_trips(1, 86400.0 / 604800, br) is False
    assert cron_breaker_trips(3, 86400.0 / 604800, br) is True
    print("  retry+cron case: PASS (weekly@1 silent, weekly@3 trips)")

    assert resend_breaker_trips(3, br) is True and resend_breaker_trips(2, br) is False
    print("  resend case: PASS (trips at >=3 identical cross-run resends in the window)")

    with tempfile.TemporaryDirectory() as td:
        led = Ledger(Path(td) / "loop-protection")
        # healer: a single verify failure trips immediately
        t1, why1 = healer_breaker_trips("cc-app", led, br, verify_failed=True)
        assert t1 and "verify" in why1
        # healer: 3 fixes on the same target in 24h trips
        for _ in range(3):
            led.record_fix(None, "LF-6", unit="cc-app", what="park", dry_run=False)
        t2, why2 = healer_breaker_trips("cc-app", led, br)
        assert t2 and "healer-loop suspected" in why2
        t3, _ = healer_breaker_trips("fresh-unit", led, br)
        assert t3 is False
        print("  healer case: PASS (verify-fail OR >3 fixes/24h trips; fresh unit safe)")

        trip("cc-app", "process", led, park=True)
        assert any(r["unit"] == "cc-app" for r in led.parked_units())
        n = unpark("cc-app", led)
        assert n >= 1 and not any(r["unit"] == "cc-app" for r in led.parked_units())
        print("  park/unpark case: PASS (trip parks; unpark clears)")
        led.close()

        # ---- REAL stop (SKS-002 / Fix 4): stub pm2 records every call ----------------
        log = str(Path(td) / "pm2.log")
        stub = str(Path(td) / "pm2")
        _selftest_stub_bin(stub, log)
        os.environ["LOOP_PM2_BIN"] = stub
        led = Ledger(Path(td) / "loop-protection-real")
        try:
            # (a) a pm2 unit is REALLY stopped: exactly one `stop`, state=stopped
            r = stop_and_park("cc-app", led, stop_fn=None)
            assert r["state"] == STATE_STOPPED and r["stopped"] is True, r
            assert _selftest_calls(log) == ["stop cc-app"], _selftest_calls(log)
            assert any(x["unit"] == "cc-app" for x in led.parked_units())
            # (b) the revert runs `pm2 start` exactly once and clears the ledger
            u = unpark_unit("cc-app", led)
            assert u["ok"] and u["restarted"] is True, u
            assert _selftest_calls(log) == ["stop cc-app", "start cc-app"], _selftest_calls(log)
            assert not any(x["unit"] == "cc-app" for x in led.parked_units())
            # (c) a second unpark does NOT start again (nothing of ours is stopped)
            u2 = unpark_unit("cc-app", led)
            assert u2["ok"] and u2["restarted"] is False
            assert _selftest_calls(log) == ["stop cc-app", "start cc-app"]
            # (d) pm2 exits non-zero => NOT stopped, state=parked-flag (never `stopped`)
            Path(log + ".rc").write_text("1", encoding="utf-8")
            r = stop_and_park("ghost", led)
            assert r["state"] == STATE_PARKED_FLAG and r["stopped"] is False, r
            assert "NOTHING was stopped" in r["reason"] and "stays open" in r["reason"]
            assert led.get_meta(STOPPED_META_PREFIX + "ghost") in (None, "")
            # a failed stop leaves no `pm2 start` for the revert to run
            before = len(_selftest_calls(log))
            assert unpark_unit("ghost", led)["restarted"] is False
            assert len(_selftest_calls(log)) == before
            Path(log + ".rc").unlink()
            # (e) the OpenClaw gateway is ALERT-ONLY under every name: pm2 is never run
            before = len(_selftest_calls(log))
            for gw in ("gateway", "gateway:18789", "openclaw-gateway", "ai.openclaw.gateway"):
                assert is_gateway_unit(gw)
                g = stop_and_park(gw, led)
                assert g["state"] == STATE_PARKED_FLAG and g["stopped"] is False
                assert "ALERT-ONLY" in g["reason"]
            assert len(_selftest_calls(log)) == before, "the gateway must never reach pm2"
            assert not is_gateway_unit("cc-app") and not is_gateway_unit("gateway-proxy-app")
            # (f) hostile / option-shaped names never reach pm2
            before = len(_selftest_calls(log))
            for bad in ("all", "ALL", "--help", "-x", "a b", "a;b", "", "$(id)"):
                assert stop_and_park(bad, led)["stopped"] is False, bad
            assert len(_selftest_calls(log)) == before, "a bad unit name reached pm2"
            # (f2) SECRET LEAK: pm2's own output (a process table / env) is DISCARDED, only the
            #      exit code is read. A tracer a stub prints on stdout must reach neither the
            #      result, the ledger meta, nor this process's stdout/stderr.
            tracer = "TRACERENVSECRETsk11deadbeef"
            tstub, tlog = str(Path(td) / "pm2-tracer"), str(Path(td) / "pm2-tracer.log")
            _selftest_stub_bin(tstub, tlog, stdout=tracer)
            os.environ["LOOP_PM2_BIN"] = tstub
            import contextlib, io
            buf_o, buf_e = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_o), contextlib.redirect_stderr(buf_e):
                tr = stop_and_park("tracer-app", led)
                tu = unpark_unit("tracer-app", led)
            blob = json.dumps([tr, tu]) + buf_o.getvalue() + buf_e.getvalue() + \
                json.dumps([dict(m) for m in led.conn.execute("SELECT * FROM meta").fetchall()])
            assert tr["stopped"] and tu["restarted"], (tr, tu)
            assert _selftest_calls(tlog) == ["stop tracer-app", "start tracer-app"]
            assert tracer not in blob, "pm2 output leaked into the result/ledger/stdout"
            os.environ["LOOP_PM2_BIN"] = stub
            # (g) a stop_fn that throws is a failed stop, never a crash
            def _boom(unit):
                raise RuntimeError("boom")
            assert stop_and_park("boom-app", led, stop_fn=_boom)["state"] == STATE_PARKED_FLAG
            # (h) unpark start FAILS => unit stays parked and the revert can be retried
            stop_and_park("retry-app", led)
            Path(log + ".rc").write_text("1", encoding="utf-8")
            f = unpark_unit("retry-app", led)
            assert f["ok"] is False and any(x["unit"] == "retry-app" for x in led.parked_units())
            Path(log + ".rc").unlink()
            assert unpark_unit("retry-app", led)["restarted"] is True
            # (i) no pm2 reachable at all (probes off, no seam) => parked-flag, no crash
            os.environ.pop("LOOP_PM2_BIN")
            before = len(_selftest_calls(log))
            n = stop_and_park("nopm2", led)
            assert n["state"] == STATE_PARKED_FLAG and len(_selftest_calls(log)) == before
        finally:
            os.environ.pop("LOOP_PM2_BIN", None)
            led.close()
        print("  real-stop case: PASS (pm2 stop once; revert pm2 start once; failed stop => "
              "parked-flag; gateway alert-only; hostile names refused; no pm2 => parked-flag)")

    assert cap_raise_without_stamp(20, 10) is True     # loosened ceiling
    assert cap_raise_without_stamp(10, 10) is False
    print("  cap-raise case: PASS (a loosened ceiling without a stamp = P1 signal)")

    print("[loop_breaker] self-test: PASS")
    return 0


# --------------------------------------------------------------------------- #
# CLI (operator park / unpark - the one-line revert the whole skill stands on).
# Exit contract mirrors the ledger: 0 OK, 2 usage, 3 not-found/false.
# --------------------------------------------------------------------------- #
def _resolve_unit(ledger, unit, finding_id):
    """Resolve the target unit: an explicit <unit> wins; otherwise look the finding
    up in the ledger and take ITS unit. This is the finding->unit lookup the operator
    revert (`unpark --finding <id>`) needs and previously lacked. Returns (unit, err)."""
    if unit:
        return unit, None
    if finding_id is not None:
        f = ledger.get_finding(finding_id)
        if not f:
            return None, "finding %s not found in the ledger" % finding_id
        if not f.get("unit"):
            return None, "finding %s carries no unit to act on" % finding_id
        return f["unit"], None
    return None, "a <unit> or --finding <id> is required"


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection circuit breakers.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the deterministic self-test and exit")
    ap.add_argument("--state-dir",
                    help="override the ledger state dir (default $LOOP_STATE_DIR)")
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (
            ("park", "set the ledger parked-flag on a unit (visible-red status marker; stops NOTHING)"),
            ("unpark", "clear park+trip on a unit; `pm2 start`s it first if this skill stopped it")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("unit", nargs="?", help="the unit name")
        sp.add_argument("--finding", type=int,
                        help="resolve the unit from a ledger finding id")
    sub.add_parser("status", help="list parked units + tripped breakers (read-only)")

    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.cmd:
        ap.print_help()
        return EX_OK

    state_dir = Path(a.state_dir) if getattr(a, "state_dir", None) else None
    ledger = Ledger(state_dir)
    try:
        if a.cmd == "status":
            print(json.dumps({"parked_units": [r["unit"] for r in ledger.parked_units()],
                              "tripped_breakers": [[r["unit"], r["breaker"]]
                                                   for r in ledger.tripped_breakers()]},
                             sort_keys=True))
            return EX_OK
        unit, err = _resolve_unit(ledger, getattr(a, "unit", None),
                                  getattr(a, "finding", None))
        if err:
            sys.stderr.write("REFUSED [loop_breaker]: %s\n" % err)
            return EX_FALSE if a.finding is not None else EX_USAGE
        if a.cmd == "park":
            park(unit, ledger)
            print(json.dumps({"ok": True, "action": "park", "unit": unit,
                              "state": STATE_PARKED_FLAG, "stopped": False,
                              "note": "ledger flag only; nothing was stopped",
                              "revert": "loop-companion.sh unpark %s" % unit},
                             sort_keys=True))
            return EX_OK
        # unpark: the operator revert. `pm2 start`s a unit this skill really stopped, clears
        # every parked/tripped row, and (when driven by --finding) marks the finding resolved.
        res = unpark_unit(unit, ledger)
        if not res["ok"]:
            sys.stderr.write("REFUSED [loop_breaker]: %s\n" % res["reason"])
            print(json.dumps({"ok": False, "action": "unpark", "unit": unit,
                              "reason": res["reason"]}, sort_keys=True))
            return EX_FALSE
        if a.finding is not None:
            ledger.set_finding_state(a.finding, "resolved")
        print(json.dumps({"ok": True, "action": "unpark", "unit": unit,
                          "cleared": res["cleared"], "restarted": res["restarted"]},
                         sort_keys=True))
        return EX_OK
    finally:
        ledger.close()


if __name__ == "__main__":
    sys.exit(_cli())
