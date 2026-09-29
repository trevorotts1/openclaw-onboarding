#!/usr/bin/env python3
"""
p209-jev-live-decision-probe.py — read-only proof, per box, that the
installed `shared-utils/decision-engine.py` bridge is the JEV LIVE ROUTING
build (unit JGT101: intent + route on every --evaluate response) and reports
whether the box's decision-engine kill switch (spec C5) is on.

This is a PROVER, in the p107/p206/p207/p208/p304 family: it never mutates
anything, never touches the network, and never spawns anything other than
the bridge it is checking. It is meant to run against a box's INSTALLED
tree (default ~/.openclaw/skills), not this repo's own shared-utils/ — the
repo copy is only the release candidate; what matters after a fleet roll is
what actually landed on the box.

WHAT THIS PROVES
-----------------
1. `--capability` answers with a schemaVersion whose major is "1" (the wire
   CC's bridge.ts probe already requires).
2. `--evaluate` on three fixed, non-fixture messages returns the shape unit
   JGT101 added on top of the pre-existing bridge response:
     - 'What time is it in Tokyo?'                    -> intent answer_only,
       route.action 'answer'.
     - 'Draft a press release about the launch'       -> route.action
       'route', route.department 'communications', route.fallback False
       (the standard-floor department-naming-map ranking).
     - 'Zorblax the quintessential frobnicator'       -> route.action
       'route', route.department 'general-task', route.fallback True (the
       universal no-fit catch-all).
   Every response is also checked for `configRevision` echoed verbatim and
   for none of the FORBIDDEN_ASSIGNMENT_KEYS unit JGT101's contract bans
   (JEV recommends; Command Center is the only writer).
3. The box's configured decision-engine mode (spec C5: env
   OPENCLAW_DECISION_ENGINE_MODE, else the first word of
   $OC_CONFIG/decision-engine-mode.conf, else the release default `auto`) —
   resolved in the SAME order as scripts/decision-engine-mode.py, so this
   probe can never disagree with the box's own referee about what "the
   mode" is.

WHAT THIS DOES NOT CHECK (named honestly, not left implicit)
--------------------------------------------------------------
  - Command Center's consumption of the bridge is NOT exercised here: no
    routeTaskDecision hook, no /api/tasks/ingest raw door, no jevResponder
    wiring. That is unit JGT105's surface, in the `cc` repo, not this one.
  - The live task board is NOT checked: this probe never looks at
    mission-control.db, never creates or inspects a card. A PASS here means
    the bridge JEV would recommend from is live and correct in isolation,
    not that a real owner message actually lands where JEV said it would.

USAGE
  p209-jev-live-decision-probe.py [--skills-root DIR] [--oc-config DIR] [--json]

  --skills-root  DIR containing shared-utils/decision-engine.py
                 (default: ~/.openclaw/skills)
  --oc-config    DIR holding decision-engine-mode.conf
                 (default: $OC_CONFIG, else ~/.openclaw)
  --json         machine-readable report (expected vs actual per check, the
                 bridge path, and the mode source)

EXIT CODES
  0  PASS                 all checks passed and the mode is `auto`.
  0  PASS_KILL_SWITCH_OFF all checks passed but the mode is off/legacy/shadow
                          (JEV is correct on the box but Command Center will
                          not call it).
  1  FAIL                 the bridge is missing, an installed bridge answers
                          but predates JEV live routing (no intent/route on
                          --evaluate — "installed bridge predates JEV live
                          routing — roll the box"), or any check mismatched.
  2  usage error or a probe crash. This is NEVER reported as a box failure —
     a crash here is a fact about the probe, not about the box.
================================================================================
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The exact key list unit JGT101's bridge contract forbids anywhere in a
# --evaluate response (JEV recommends; Command Center is the only writer).
FORBIDDEN_ASSIGNMENT_KEYS = {
    "assigned_agent_id", "assignedAgentId", "assignment", "board",
    "task_card", "taskCard", "dispatch", "column",
    "status_transition", "statusTransition", "persona_pin", "personaPin",
}

VALID_MODES = {"auto", "shadow", "legacy", "off"}
BRIDGE_TIMEOUT_S = 15
REQUEST_SCHEMA_VERSION = "1.1.0"
CONFIG_REVISION = "p209-probe"

NOT_CHECKED = [
    "Command Center's consumption of the bridge (routeTaskDecision's "
    "department hook, the /api/tasks/ingest raw door, jevResponder wiring) "
    "-- unit JGT105, a different repo.",
    "the live task board -- this probe never reads mission-control.db and "
    "never creates a card.",
]


def _hostname() -> str:
    try:
        return socket.gethostname().split(".")[0]
    except OSError:
        return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_forbidden_keys(obj, path: str = ""):
    """Recursive walk; returns the dotted/bracketed paths of any forbidden
    assignment key found anywhere in the response (never a bare grep)."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if k in FORBIDDEN_ASSIGNMENT_KEYS:
                found.append(p)
            found.extend(_find_forbidden_keys(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_find_forbidden_keys(v, f"{path}[{i}]"))
    return found


# ---------------------------------------------------------------------------
# Mode resolution -- same order as scripts/decision-engine-mode.py:
#   1. $OPENCLAW_DECISION_ENGINE_MODE (env)
#   2. first line of $OC_CONFIG/decision-engine-mode.conf
#   3. release default 'auto'
# ---------------------------------------------------------------------------

def _resolve_mode(oc_config: Path):
    """(mode, source) -- source is 'env' | 'file' | 'default'."""
    env_raw = os.environ.get("OPENCLAW_DECISION_ENGINE_MODE")
    if env_raw is not None and env_raw.strip():
        return env_raw.strip(), "env"
    store = oc_config / "decision-engine-mode.conf"
    if store.is_file():
        try:
            raw = store.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        first = (raw.splitlines() or [""])[0].strip()
        return first, "file"
    return "auto", "default"


# ---------------------------------------------------------------------------
# Bridge invocation -- read-only: one subprocess per check, stdlib only.
# ---------------------------------------------------------------------------

def _run_bridge(python_exe, bridge_path, args, stdin_payload=None):
    """(rc, stdout, stderr, error_note). error_note is set only when the
    bridge could not be spawned or timed out (never a fact about the box's
    answer -- that is scored by the caller from rc/stdout)."""
    try:
        proc = subprocess.run(
            [python_exe, str(bridge_path), *args],
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=BRIDGE_TIMEOUT_S,
        )
        return proc.returncode, proc.stdout, proc.stderr, None
    except subprocess.TimeoutExpired:
        return None, "", "", f"timed out after {BRIDGE_TIMEOUT_S}s"
    except OSError as exc:
        return None, "", "", f"could not execute bridge: {type(exc).__name__}: {exc}"


def _check_capability(python_exe, bridge_path):
    check = {
        "name": "capability_schema_major_1",
        "expected": "schemaVersion major == '1'",
        "actual": None,
        "passed": False,
    }
    rc, out, err, error_note = _run_bridge(python_exe, bridge_path, ["--capability"])
    if error_note:
        check["actual"] = error_note
        return check
    if rc != 0:
        check["actual"] = f"exit {rc}: {(err or out).strip()}"
        return check
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        check["actual"] = f"non-JSON output: {out.strip()!r}"
        return check
    schema = data.get("schemaVersion") if isinstance(data, dict) else None
    major = str(schema).strip().split(".", 1)[0] if isinstance(schema, str) else None
    check["actual"] = {"schemaVersion": schema}
    check["passed"] = major == "1"
    return check


def _check_evaluate(python_exe, bridge_path, name, task_description, expect):
    """expect keys used: intent, route.action, route.department,
    route.fallback -- only the ones a given case cares about."""
    check = {
        "name": name,
        "expected": {**expect, "taskDescription": task_description},
        "actual": None,
        "passed": False,
        "predates": False,
    }
    task_id = f"p209-{name}"
    payload = json.dumps({
        "schemaVersion": REQUEST_SCHEMA_VERSION,
        "configRevision": CONFIG_REVISION,
        "taskId": task_id,
        "taskDescription": task_description,
    })
    rc, out, err, error_note = _run_bridge(
        python_exe, bridge_path, ["--evaluate"], stdin_payload=payload
    )
    if error_note:
        check["actual"] = error_note
        return check
    if rc != 0:
        check["actual"] = f"exit {rc}: {(err or out).strip()}"
        return check
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        check["actual"] = f"non-JSON output: {out.strip()!r}"
        return check
    if not isinstance(data, dict) or "intent" not in data or "route" not in data:
        check["actual"] = {
            "keys": sorted(data.keys()) if isinstance(data, dict) else type(data).__name__
        }
        check["predates"] = True
        return check

    route = data.get("route") or {}
    forbidden = _find_forbidden_keys(data)
    actual = {
        "intent": data.get("intent"),
        "route": route,
        "configRevision": data.get("configRevision"),
        "forbidden_keys_found": forbidden,
    }
    check["actual"] = actual

    ok = True
    if "intent" in expect and data.get("intent") != expect["intent"]:
        ok = False
    if "route.action" in expect and route.get("action") != expect["route.action"]:
        ok = False
    if "route.department" in expect and route.get("department") != expect["route.department"]:
        ok = False
    if "route.fallback" in expect and route.get("fallback") != expect["route.fallback"]:
        ok = False
    if data.get("configRevision") != CONFIG_REVISION:
        ok = False
    if forbidden:
        ok = False
    check["passed"] = ok
    return check


def _emit(verdict, as_json):
    if as_json:
        print(json.dumps(verdict, indent=2, default=str))
        return
    print(f"p209 JEV live-decision probe — box: {verdict.get('box')}  ({verdict.get('checked_at')})")
    print(f"  bridge: {verdict.get('bridge_path')}  present={verdict.get('bridge_present')}")
    print(f"  mode: {verdict.get('mode')!r}  (source: {verdict.get('mode_source')})")
    for c in verdict.get("checks", []):
        tag = "[OK]  " if c["passed"] else "[MISS]"
        print(f"  {tag} {c['name']}")
        print(f"         expected: {c['expected']!r}")
        print(f"         actual:   {c['actual']!r}")
    print(f"  VERDICT: {verdict.get('verdict')} — {verdict.get('note')}")
    print("  NOT CHECKED:")
    for line in verdict.get("not_checked", []):
        print(f"    - {line}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--skills-root", default=None,
        help="DIR containing shared-utils/decision-engine.py (default: ~/.openclaw/skills)",
    )
    ap.add_argument(
        "--oc-config", default=None,
        help="DIR holding decision-engine-mode.conf (default: $OC_CONFIG, else ~/.openclaw)",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)  # argparse itself exits 2 on a bad arg

    skills_root = (
        Path(args.skills_root).expanduser() if args.skills_root
        else (Path.home() / ".openclaw" / "skills")
    )
    oc_config = (
        Path(args.oc_config).expanduser() if args.oc_config
        else Path(os.environ.get("OC_CONFIG") or (Path.home() / ".openclaw")).expanduser()
    )
    bridge_path = skills_root / "shared-utils" / "decision-engine.py"

    mode, mode_source = _resolve_mode(oc_config)

    verdict = {
        "box": _hostname(),
        "checked_at": _now_iso(),
        "skills_root": str(skills_root),
        "oc_config": str(oc_config),
        "bridge_path": str(bridge_path),
        "bridge_present": bridge_path.is_file(),
        "mode": mode,
        "mode_source": mode_source,
        "checks": [],
        "predates": False,
        "verdict": None,
        "note": None,
        "not_checked": NOT_CHECKED,
    }

    if not bridge_path.is_file():
        verdict["verdict"] = "FAIL"
        verdict["note"] = (
            f"bridge not found at {bridge_path} -- shared-utils/decision-engine.py "
            "is not installed on this box"
        )
        _emit(verdict, args.json)
        return 1

    python_exe = sys.executable or "python3"
    checks = [
        _check_capability(python_exe, bridge_path),
        _check_evaluate(
            python_exe, bridge_path, "tokyo_answer_only",
            "What time is it in Tokyo?",
            {"intent": "answer_only", "route.action": "answer"},
        ),
        _check_evaluate(
            python_exe, bridge_path, "press_release_route_communications",
            "Draft a press release about the launch",
            {"route.action": "route", "route.department": "communications", "route.fallback": False},
        ),
        _check_evaluate(
            python_exe, bridge_path, "zorblax_general_task_fallback",
            "Zorblax the quintessential frobnicator",
            {"route.action": "route", "route.department": "general-task", "route.fallback": True},
        ),
    ]
    verdict["checks"] = checks

    predates = any(c.get("predates") for c in checks)
    all_passed = all(c["passed"] for c in checks)

    if predates:
        verdict["predates"] = True
        verdict["verdict"] = "FAIL"
        verdict["note"] = "installed bridge predates JEV live routing — roll the box"
        rc = 1
    elif not all_passed:
        failing = [c["name"] for c in checks if not c["passed"]]
        verdict["verdict"] = "FAIL"
        verdict["note"] = f"mismatch on: {', '.join(failing)}"
        rc = 1
    elif mode == "auto":
        verdict["verdict"] = "PASS"
        verdict["note"] = "all checks passed; kill switch mode is 'auto' (JEV is live)"
        rc = 0
    else:
        # off/legacy/shadow, or an unrecognized value -- never silently
        # widened to a full PASS; the bridge itself is correct, but Command
        # Center will not call it (spec C5), or is only shadow-logging it.
        verdict["verdict"] = "PASS_KILL_SWITCH_OFF"
        suffix = "" if mode in VALID_MODES else " (not a recognized mode value)"
        verdict["note"] = (
            f"all checks passed; kill switch mode is {mode!r}{suffix} -- "
            "Command Center will not call JEV in this mode"
        )
        rc = 0

    _emit(verdict, args.json)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- a probe crash is never a box FAIL
        print(
            json.dumps({"verdict": "ERROR", "note": f"probe crashed: {type(exc).__name__}: {exc}"}),
            file=sys.stderr,
        )
        sys.exit(2)
