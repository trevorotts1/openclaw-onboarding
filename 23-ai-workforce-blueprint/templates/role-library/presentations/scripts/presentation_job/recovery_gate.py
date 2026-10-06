#!/usr/bin/env python3
"""PRES-019 -- the recovery-readiness health gate.

WHAT ANSWERS "IS RECOVERY READY?"
---------------------------------
Supervised recovery (supervisor.py restarts a dead worker behind an active
run) is safe to arm by default ONLY when the machine can actually execute a
restart and tell a human about it. Before PRES-019 nothing proved that at
install time: the watchdog installer shipped the supervisor report-only on
every box, forever, unless an operator hand-exported an env var -- and the
consumer read that env var with `${VAR:+--apply}`, so "0" armed it too. A
live flock proves process ownership, not useful work; detection without
recovery is not recovery.

This module is the ONE checker both the installer (lib-presentation-schedules.
sh's _pres_recovery_health_gate) and any operator can run. It answers the
question with exit code 0/1 and --json evidence, naming EVERY failed gate --
never a bare "not ready" -- so a box that cannot recover says exactly why
(spec: "proves recovery ready or exposes the exact failed gate").

THE GATES, in order. Each is a prerequisite of the restart path as it
actually exists:

  entry-script     presentation_job.py beside the scripts dir -- what
                   supervisor._restart spawns (`--resume --run-dir`).
  python3          on PATH -- the spawn is sys.executable under the entry
                   script's shebang; without python3 every restart is a
                   corpse that burns the restart budget.
  recovery-modules supervisor.py, auto_resume.py, lease.py in the package.
                   lease.py absence degrades loudly rather than fatally in
                   supervisor.py, but a restart that cannot take the run
                   lease races a live holder -- gate it.
  notify-transport PRESENTATION_NOTIFY_CMD resolvable: the process env, or
                   presentation-notify.py beside the scripts (what the
                   installer renders), or a box env store naming one
                   (env_store.resolve -- presence only, never a value).
                   Fail-closed, same rule as the watchdog's own FIX 22 gate
                   and the launcher's notify_gate: a restart nobody can be
                   told about must not fire. PRESENTATION_NOTIFY_FAIL_CLOSED=0
                   (the documented emergency rollback) is honoured -- the
                   gate then treats an unconfigured transport as a WARNING
                   that still fails the gate ONLY when the value is absent
                   everywhere AND fail-closed is on... no: the gate follows
                   the launcher's semantics exactly. FAIL_CLOSED=0 means the
                   launcher would warn-and-continue, so the transport gate
                   passes with a warning. Kill switches preserved.
  load-path        mac: launchctl on PATH (a rendered plist arms nothing
                   without it). vps: openclaw on PATH (the cron branch's
                   own prerequisite).

WHAT THIS IS NOT. It is not a bypass of anything: an explicit operator
decision (PRESENTATION_SUPERVISE_APPLY=true/false/1/0) outranks this gate in
the installer; kill switches (PRESENTATION_AUTO_RESUME=0,
PRESENTATION_NOTIFY_FAIL_CLOSED, supervisor ledger caps, auto_resume bounds)
live downstream and are untouched here. It never spawns an engine, never
writes anywhere, never reads a credential VALUE (presence only, through the
same env_store.resolve the entry points already trust).

CLI:
    python3 presentation_job/recovery_gate.py --scripts-dir DIR --platform mac|vps
        exit 0 = ready, exit 1 = not ready (failed gates on stderr), exit 2 = usage
    --json  adds a machine-readable verdict on stdout (exit code unchanged)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

GATE_ID = "PRES-019"

#: The package modules a restart needs. lease.py is included even though
#: supervisor.py degrades without it: the degrade is logged, but a restart
#: that cannot lease the run races a live holder -- the gate refuses.
REQUIRED_PACKAGE_MODULES = ("supervisor.py", "auto_resume.py", "lease.py")


def _no_transport(env: Dict[str, str], out: Dict[str, Any],
                  detail: str) -> Dict[str, Any]:
    """Every transport source answered nothing. PRESENTATION_NOTIFY_FAIL_
    CLOSED=0 (the documented emergency rollback, watchdog FIX 22) keeps the
    gate open with a warning -- warn-and-continue, exactly the semantics the
    launcher's notify_gate gives the same variable. Fail-closed (default)
    fails the gate with the detail named."""
    if str(env.get("PRESENTATION_NOTIFY_FAIL_CLOSED") or "1").strip() != "0":
        out["failed"] = True
        out["detail"] = detail
    else:
        out["warn"] = f"{detail}; PRESENTATION_NOTIFY_FAIL_CLOSED=0 -- warn-and-continue"
    return out


def _resolve_notify_transport(scripts_dir: Path,
                              environ: Optional[Dict[str, str]] = None
                              ) -> Dict[str, Any]:
    """Presence-only notify-transport verdict. Never reads a VALUE out.

    Order mirrors what the installer actually renders and what the watchdog
    loads at runtime:
      1. the process environment (what launchd/cron will pass through);
      2. presentation-notify.py beside the scripts (the installer's render
         target -- the watchdog treats a co-located transport as configured);
      3. a box env store (env_store.resolve -- the loader presentation-
         watchdog.sh evals at every tick). Presence only: a name that
         resolves non-blank in any candidate store counts, the VALUE never
         leaves this function.
    PRESENTATION_NOTIFY_FAIL_CLOSED=0 is the documented emergency rollback
    for exactly this gate (watchdog FIX 22): it does not make an unconfigured
    transport configured, but it DOES make the system warn-and-continue --
    so the gate reports the gate as failed=False with a warning, preserving
    the operator's kill switch instead of overriding it.
    """
    env = dict(os.environ if environ is None else environ)
    out: Dict[str, Any] = {"gate": "notify-transport", "failed": False,
                           "source": None, "warn": None}
    raw = str(env.get("PRESENTATION_NOTIFY_CMD") or "").strip()
    if raw:
        out["source"] = "process-env"
        return out
    if (scripts_dir / "presentation-notify.py").is_file():
        out["source"] = "beside-scripts"
        return out
    try:
        from .env_store import resolve as env_store_resolve
    except ImportError:  # direct-path invocation (the shell gate runs us by path)
        try:
            sys.path.insert(0, str(scripts_dir))
            from presentation_job.env_store import resolve as env_store_resolve  # type: ignore[no-redef]
        except ImportError:
            return _no_transport(env, out, "env_store unresolvable -- "
                                 "store-based transports could not be "
                                 "checked; process env and the co-located "
                                 "transport were")
    try:
        assignments, _report = env_store_resolve(environ=env)
    except Exception as exc:  # noqa: BLE001 -- a broken store must not kill the gate
        return _no_transport(env, out, f"env store resolution raised "
                             f"{type(exc).__name__}")
    if str(assignments.get("PRESENTATION_NOTIFY_CMD") or "").strip():
        out["source"] = "env-store"
        return out
    return _no_transport(env, out, "PRESENTATION_NOTIFY_CMD unset everywhere "
                         "(process env, co-located presentation-notify.py, "
                         "box env store) -- a restart nobody can be told "
                         "about must not fire (fail-closed, same rule as "
                         "the watchdog's FIX 22 gate)")


def run_gate(scripts_dir: Path, platform: str = "mac",
             environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The verdict. PURE-ish: reads only. Returns

        {"ready": bool, "checks": [{gate, failed, detail?, source?, warn?}...],
         "scripts_dir": str, "platform": str}

    Every failed check carries its own human detail. `ready` is False when
    ANY check failed -- a partial recovery readiness is not readiness, the
    same all-or-nothing the supervisor's budget needs to be meaningful.
    """
    checks: List[Dict[str, Any]] = []

    def _add(gate: str, failed: bool, **extra: Any) -> None:
        row: Dict[str, Any] = {"gate": gate, "failed": bool(failed)}
        row.update(extra)
        checks.append(row)

    entry = scripts_dir / "presentation_job.py"
    _add("entry-script", not entry.is_file(),
         detail=None if entry.is_file() else
         f"{entry} not found -- supervisor._restart has nothing to spawn")

    py = shutil.which("python3", path=None)
    if py is None and environ is not None:
        py = shutil.which("python3", path=environ.get("PATH", ""))
    else:
        py = shutil.which("python3")
    _add("python3", py is None,
         detail=None if py else
         "python3 not on PATH -- every restart would burn the restart budget "
         "on a corpse spawn")

    for mod in REQUIRED_PACKAGE_MODULES:
        path = scripts_dir / "presentation_job" / mod
        _add(f"recovery-module:{mod[:-3]}", not path.is_file(),
             detail=None if path.is_file() else
             f"{path} not found -- the recovery machinery is incomplete "
             f"(supervisor.py needs all of {', '.join(REQUIRED_PACKAGE_MODULES)})")

    checks.append(_resolve_notify_transport(scripts_dir, environ))

    if str(platform or "").strip().lower() == "vps":
        oc = shutil.which("openclaw")
        _add("openclaw", oc is None,
             detail=None if oc else
             "openclaw not on PATH -- the VPS cron branch needs it to register "
             "the watchdog cron")
    else:
        lc = shutil.which("launchctl")
        _add("launchctl", lc is None,
             detail=None if lc else
             "launchctl not on PATH -- a rendered plist arms nothing without it")

    ready = all(not c.get("failed") for c in checks)
    return {
        "gate_id": GATE_ID,
        "ready": ready,
        "checks": checks,
        "scripts_dir": str(scripts_dir),
        "platform": platform,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="presentation_job.recovery_gate",
        description=("PRES-019 recovery-readiness health gate. Exit 0 = "
                     "supervised recovery may be armed; exit 1 = not ready "
                     "(every failed gate is named on stderr); exit 2 = usage. "
                     "Read-only: spawns nothing, writes nothing, never reads "
                     "a credential value."))
    p.add_argument("--scripts-dir", required=True,
                   help="the presentations scripts directory holding "
                        "presentation_job/ and presentation_job.py")
    p.add_argument("--platform", default="mac", choices=["mac", "vps"],
                   help="mac checks launchctl, vps checks openclaw")
    p.add_argument("--json", action="store_true",
                   help="print the full verdict as JSON on stdout (exit code "
                        "still 0/1)")
    args = p.parse_args(argv)

    scripts_dir = Path(args.scripts_dir).expanduser()
    verdict = run_gate(scripts_dir, args.platform)
    if args.json:
        print(json.dumps(verdict, indent=2))
    for check in verdict["checks"]:
        if check.get("failed"):
            detail = check.get("detail") or check.get("warn") or "failed"
            print(f"{GATE_ID} GATE {check['gate']}: {detail}", file=sys.stderr)
        elif check.get("warn"):
            print(f"{GATE_ID} WARNING {check['gate']}: {check['warn']}",
                  file=sys.stderr)
    if not args.json:
        print(f"{GATE_ID}: recovery {'READY' if verdict['ready'] else 'NOT READY'} "
              f"({scripts_dir}, platform {args.platform})", file=sys.stderr)
    return 0 if verdict["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
