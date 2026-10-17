#!/usr/bin/env python3
"""Browser session registry and hygiene accounting (fix plan Item 33).

One contract, from Amendment 5's Browser Engine Contract and Item 33:
every browser session a run opens is registered at open time by the
launching wrapper (the swarm runner, or a Skill 6 adapter), never from a
working agent's memory, in the run's append-only registry:

    <run_dir>/private/browser-sessions.jsonl

Append-only on purpose: a runner that dies mid-write can lose at most its
last line, and the fold below treats the registry as the evidence it is.

Events:
  opened  {session_name, run_id, stage, engine, binding, unit,
           client_slug, headed, opened_at, owner_pid, live_marker,
           teardown_cmd, via}
  closed  {session_name, closed_by: "normal" | "reaped", closed_at, via,
           detail}

`unit` is the controlled unit the engine actually isolates (Amendment 5B:
a CLI engine isolates a named session; the OpenClaw Chrome extension,
DRAFT-PENDING-LANDING per draft PR #1990, isolates controlled tabs or
windows in the operator's Chrome). Adapters record the unit their engine
truly isolates, so counts stay honest per engine; the extension-accurate
unit mapping is restated when Skill 6's change lands (Amendment 5B,
point 3), and until then the OpenClaw binding records unit "session" and
this file makes no stronger claim.

Accounting (per stage, folded from the registry after a reaper sweep):
  sessions_opened   distinct sessions opened for the stage
  sessions_closed   distinct sessions closed with closed_by "normal"
  orphans_found     sessions the sweep had to deal with:
                    orphans_reaped + unaccounted
  orphans_reaped    distinct sessions closed with closed_by "reaped"
  unaccounted       sessions still open after the sweep (the sweep could
                    not prove them closed); the gate refuses the stage's
                    close while this is above zero, naming them
  headed_launches   opened events with headed true (a contract
                    violation unless an owner override is on record)

Liveness probe for a still-open session, in order: a recorded
live_marker file exists (alive) or not (gone); else a recorded owner_pid
answers os.kill(pid, 0) (alive), is gone (gone), or cannot be probed
(unknown). Reaping a live session tries, in order: the recorded
teardown_cmd (exit 0 = success), then SIGTERM to the recorded owner_pid.
A session counts as reaped only when the probe afterwards says it is
gone, or the teardown command exited 0 and no marker contradicts it. A
session that cannot be reaped stays open in the fold and is therefore
unaccounted: the accounting never upgrades hope into a close.

CLI (for adapters and tests; the gate imports this module instead):
  register-open  <run_dir> --name N --stage S --engine E --binding B
                 [--unit U] [--client-slug C] [--run-id R] [--headed]
                 [--owner-pid P] [--live-marker PATH] [--teardown-cmd CMD]
  register-close <run_dir> --name N [--closed-by normal|reaped]
  reap           <run_dir> --stage S        (sweep + receipt + JSON out)
  receipt        <run_dir> --stage S        (receipt only, no sweep)
  rollup         <run_dir>                  (run-level REPORT.json shape)
"""
import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_REL = Path("private") / "browser-sessions.jsonl"
RECEIPT_NAME = "browser-hygiene.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def registry_path(run_dir):
    return Path(run_dir) / REGISTRY_REL


# ---------------------------------------------------------------------------
# Registry writes (append-only)

def _append(run_dir, record):
    path = registry_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def register_open(run_dir, *, session_name, stage, engine, binding,
                  unit="session", client_slug="", run_id="", headed=False,
                  owner_pid=None, live_marker=None, teardown_cmd=None,
                  via="wrapper"):
    """Record a session opening. Called by the launching wrapper at
    launch time (Item 33 HOW 1: registration is the wrapper's job)."""
    _append(run_dir, {
        "event": "opened",
        "session_name": session_name,
        "run_id": run_id,
        "stage": stage,
        "engine": engine,
        "binding": binding,
        "unit": unit,
        "client_slug": client_slug,
        "headed": bool(headed),
        "opened_at": now_iso(),
        "owner_pid": owner_pid,
        "live_marker": str(live_marker) if live_marker else None,
        "teardown_cmd": teardown_cmd,
        "via": via,
    })
    return session_name


def register_close(run_dir, session_name, *, closed_by="normal", via="wrapper",
                   detail=""):
    """Record a session closing. closed_by is "normal" when the owner
    tore the session down through the contract's teardown operation, or
    "reaped" when the reaper sweep closed the books on it."""
    if closed_by not in ("normal", "reaped"):
        raise ValueError(f"closed_by must be 'normal' or 'reaped', got {closed_by!r}")
    _append(run_dir, {
        "event": "closed",
        "session_name": session_name,
        "closed_by": closed_by,
        "closed_at": now_iso(),
        "via": via,
        "detail": detail,
    })


# ---------------------------------------------------------------------------
# Fold

def load_events(run_dir):
    path = registry_path(run_dir)
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue  # a torn last line after a hard kill loses only itself
        if isinstance(rec, dict) and rec.get("session_name"):
            events.append(rec)
    return events


def fold_sessions(run_dir):
    """Fold the registry into one record per session name.

    A record's status is "open" until a closed event lands; the last
    event wins for close fields, the opened event supplies the rest."""
    sessions = {}
    for rec in load_events(run_dir):
        name = rec["session_name"]
        cur = sessions.setdefault(name, {"session_name": name, "status": "open",
                                         "closed_by": None})
        if rec.get("event") == "opened":
            for key in ("run_id", "stage", "engine", "binding", "unit",
                        "client_slug", "headed", "opened_at", "owner_pid",
                        "live_marker", "teardown_cmd", "via"):
                cur[key] = rec.get(key)
            cur["opened"] = True
        elif rec.get("event") == "closed":
            cur["status"] = "closed"
            cur["closed_by"] = rec.get("closed_by")
            cur["closed_at"] = rec.get("closed_at")
            cur["close_via"] = rec.get("via")
            cur["close_detail"] = rec.get("detail", "")
    return sessions


def stage_has_sessions(run_dir, stage):
    return any(s.get("stage") == stage for s in fold_sessions(run_dir).values())


# ---------------------------------------------------------------------------
# Probe and reap

def probe_alive(record):
    """True: provably still alive. False: provably gone. None: unknown."""
    marker = record.get("live_marker")
    if marker:
        return Path(marker).exists()
    pid = record.get("owner_pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, owned by someone else
        except OSError:
            return None
        # kill(pid, 0) also succeeds for a zombie, but a zombie
        # executes nothing and holds no browser: where /proc exposes
        # the state, a zombie is gone, not alive.
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            if stat.rsplit(")", 1)[-1].split()[0] == "Z":
                return False
        except Exception:
            pass
        return True
    return None


def _attempt_teardown(record):
    """Try to close a live session. Returns True only on proven success:
    the teardown command exited 0 with no contradicting probe, or the
    owner process took SIGTERM and is gone."""
    cmd = record.get("teardown_cmd")
    if cmd:
        try:
            proc = subprocess.run(shlex.split(cmd), capture_output=True,
                                  text=True, timeout=60)
        except Exception:
            return False
        if proc.returncode != 0:
            return False
        return probe_alive(record) is not True
    pid = record.get("owner_pid")
    if isinstance(pid, int) and pid > 0 and probe_alive(record) is True:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
        for _ in range(20):
            if probe_alive(record) is False:
                return True
            time.sleep(0.05)
        return probe_alive(record) is False
    return False


def reap_stage(run_dir, stage, *, via="gate-reaper"):
    """The reaper sweep for one stage (Item 33 HOW 3). Every session of
    the stage still open in the fold is an orphan: verify it gone and
    record it reaped, try to tear down a live one and record it reaped,
    or leave it open, which makes it unaccounted by definition.

    Returns the sweep outcome dict; the receipt writer turns it into the
    stage's browser-hygiene.json."""
    sessions = fold_sessions(run_dir)
    outcome = {"reaped": [], "unaccounted": []}
    for name in sorted(sessions):
        rec = sessions[name]
        if rec.get("stage") != stage or rec.get("status") != "open":
            continue
        alive = probe_alive(rec)
        if alive is False:
            register_close(run_dir, name, closed_by="reaped", via=via,
                           detail="sweep: session provably gone; books closed")
            outcome["reaped"].append(name)
        elif _attempt_teardown(rec):
            register_close(run_dir, name, closed_by="reaped", via=via,
                           detail="sweep: teardown performed by the reaper")
            outcome["reaped"].append(name)
        else:
            outcome["unaccounted"].append(name)
    return outcome


# ---------------------------------------------------------------------------
# Receipts and roll-up

def _headed_override(run_dir, stage):
    """An owner override for headed launches, recorded ahead of the gate
    (Item 33 HOW 4: the override lives in the receipt). Two carriers, in
    order: an owner_override_headed object already present in the
    stage's hygiene receipt (written by the executor with the owner's
    instruction), or intake.json's browser_headed_override for the
    stage. Anything else is not an override."""
    receipt_path = Path(run_dir) / stage / RECEIPT_NAME
    if receipt_path.exists():
        try:
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
            override = data.get("owner_override_headed")
            if isinstance(override, dict) and override.get("reason"):
                return override
        except Exception:
            pass
    intake = Path(run_dir) / "intake.json"
    if intake.exists():
        try:
            data = json.loads(intake.read_text(encoding="utf-8"))
            override = (data.get("browser_headed_override") or {}).get(stage)
            if isinstance(override, dict) and override.get("reason"):
                return override
        except Exception:
            pass
    return None


def stage_counts(run_dir, stage):
    """Folded per-stage accounting. orphans_found is defined from the
    fold (reaped + still-open-after-a-sweep), so a receipt written after
    a sweep and a receipt re-read later agree."""
    sessions = fold_sessions(run_dir)
    mine = [s for s in sessions.values() if s.get("stage") == stage]
    opened = len(mine)
    closed_normal = sum(1 for s in mine if s.get("closed_by") == "normal")
    reaped = sum(1 for s in mine if s.get("closed_by") == "reaped")
    still_open = [s for s in mine if s.get("status") == "open"]
    return {
        "sessions_opened": opened,
        "sessions_closed": closed_normal,
        "orphans_found": reaped + len(still_open),
        "orphans_reaped": reaped,
        "unaccounted": len(still_open),
        "headed_launches": sum(1 for s in mine if s.get("headed")),
        "_sessions": mine,
    }


def write_stage_receipt(run_dir, stage):
    """Write <stage>/browser-hygiene.json from the folded registry and
    return the receipt dict (plan Item 33 HOW 4 field names)."""
    counts = stage_counts(run_dir, stage)
    override = _headed_override(run_dir, stage)
    sessions_list = []
    for s in sorted(counts["_sessions"], key=lambda r: r["session_name"]):
        sessions_list.append({
            "name": s["session_name"],
            "engine": s.get("engine"),
            "binding": s.get("binding"),
            "unit": s.get("unit"),
            "closed_by": s.get("closed_by"),  # null while unaccounted
        })
    receipt = {
        "stage": stage,
        "sessions_opened": counts["sessions_opened"],
        "sessions_closed": counts["sessions_closed"],
        "orphans_found": counts["orphans_found"],
        "orphans_reaped": counts["orphans_reaped"],
        "unaccounted": counts["unaccounted"],
        "headed_launches": counts["headed_launches"],
        "owner_override_headed": override,
        "sessions": sessions_list,
        "updated_at": now_iso(),
    }
    path = Path(run_dir) / stage / RECEIPT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def sweep_and_receipt(run_dir, stage):
    """Gate entry point: reaper sweep, then the receipt, then the
    verdict fields the gate enforces."""
    outcome = reap_stage(run_dir, stage)
    receipt = write_stage_receipt(run_dir, stage)
    receipt["_unaccounted_names"] = outcome["unaccounted"]
    return receipt


def run_rollup(run_dir, stage_order):
    """Run-level roll-up in S6's frozen REPORT.json hygiene shape
    (references/report-json.schema.json): exactly the fields status,
    opened, closed, orphans_found, reaped, unaccounted,
    headed_launches. Summed from the per-stage browser-hygiene.json
    receipts on disk; status is "recorded" only when at least one stage
    receipt exists, otherwise "not_recorded" with null counts (a run
    with no browser accounting must not claim recorded zeros)."""
    totals = {"opened": 0, "closed": 0, "orphans_found": 0, "reaped": 0,
              "unaccounted": 0, "headed_launches": 0}
    found = False
    for stage in stage_order:
        path = Path(run_dir) / stage / RECEIPT_NAME
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        found = True
        totals["opened"] += int(data.get("sessions_opened") or 0)
        totals["closed"] += int(data.get("sessions_closed") or 0)
        totals["orphans_found"] += int(data.get("orphans_found") or 0)
        totals["reaped"] += int(data.get("orphans_reaped") or 0)
        totals["unaccounted"] += int(data.get("unaccounted") or 0)
        totals["headed_launches"] += int(data.get("headed_launches") or 0)
    if not found:
        return {"status": "not_recorded", "opened": None, "closed": None,
                "orphans_found": None, "reaped": None, "unaccounted": None,
                "headed_launches": None}
    return {"status": "recorded", **totals}


# ---------------------------------------------------------------------------
# CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="Browser session registry (Item 33)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("register-open")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--name", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--engine", required=True)
    p.add_argument("--binding", required=True)
    p.add_argument("--unit", default="session")
    p.add_argument("--client-slug", default="")
    p.add_argument("--run-id", default="")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--owner-pid", type=int)
    p.add_argument("--live-marker")
    p.add_argument("--teardown-cmd")
    p.add_argument("--via", default="wrapper")
    p = sub.add_parser("register-close")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--name", required=True)
    p.add_argument("--closed-by", default="normal", choices=["normal", "reaped"])
    p.add_argument("--via", default="wrapper")
    p = sub.add_parser("reap")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--stage", required=True)
    p = sub.add_parser("receipt")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--stage", required=True)
    p = sub.add_parser("rollup")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--stages", required=True,
                   help="comma-separated stage order")
    args = ap.parse_args(argv)
    if args.cmd == "register-open":
        register_open(args.run_dir, session_name=args.name, stage=args.stage,
                      engine=args.engine, binding=args.binding, unit=args.unit,
                      client_slug=args.client_slug, run_id=args.run_id,
                      headed=args.headed, owner_pid=args.owner_pid,
                      live_marker=args.live_marker,
                      teardown_cmd=args.teardown_cmd, via=args.via)
        print(f"registered open: {args.name}")
        return 0
    if args.cmd == "register-close":
        register_close(args.run_dir, args.name, closed_by=args.closed_by,
                       via=args.via)
        print(f"registered close: {args.name}")
        return 0
    if args.cmd == "reap":
        receipt = sweep_and_receipt(args.run_dir, args.stage)
        print(json.dumps(receipt, indent=2))
        return 0
    if args.cmd == "receipt":
        receipt = write_stage_receipt(args.run_dir, args.stage)
        print(json.dumps(receipt, indent=2))
        return 0
    if args.cmd == "rollup":
        print(json.dumps(run_rollup(args.run_dir,
                                    args.stages.split(",")), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
