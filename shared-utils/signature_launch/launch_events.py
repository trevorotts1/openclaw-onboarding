#!/usr/bin/env python3
"""Launch event emitter: one run event per launch step, never a launch failure.

Skill 83 (dispatch / assemble / check) and Skill 49 (dispatch_launch) call
``emit(skill, launch_id, event)`` so a launch is visible in the Command Center.
Events use the frozen Skill 71 run-events contract plus the two launch fields
``skill`` and ``launch_id`` (CC: src/lib/launch-run-events.ts) and are POSTed to
the CC launch ingest (``/api/launch-runs/ingest``) with the per-client token.

NON-BLOCKING: ``emit`` never raises and never waits long. Any failure (no URL,
no token, refused connection, timeout, HTTP error, a bad event) appends the
event to a JSONL spool on disk instead; the next successful ``emit`` (or an
explicit ``drain``) replays it, oldest first. A CC outage never fails a launch.

Environment (names only; values are never printed or logged):
  LAUNCH_EVENTS_URL          full ingest URL; else COMMAND_CENTER_URL /
                             MISSION_CONTROL_URL + /api/launch-runs/ingest
  LAUNCH_EVENTS_TOKEN_FILE   file holding the per-client bearer token; else
                             SKILL71_RUNS_SHIP_TOKEN_FILE (the Skill 71 shipper's
                             token file, same ingest token store); else
                             CC_API_TOKEN / MC_API_TOKEN
  LAUNCH_EVENTS_SPOOL        spool directory (default
                             ~/.openclaw/data/signature-launch/events-spool)
  LAUNCH_EVENTS_TIMEOUT      per-request seconds (default 3)
  LAUNCH_EVENTS_HOST_SHAPE   fleet-mac | fleet-hostinger | fleet-contabo, only
                             stamped on run_initialized (default fleet-mac)

Pure stdlib.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
INGEST_PATH = "/api/launch-runs/ingest"
SPOOL_FILE = "launch-events.jsonl"
REJECTED_FILE = "launch-events.rejected.jsonl"
# One launch of one skill is one CC run: run_id is derived, so every event of a
# launch carries the same run_id without any shared state between processes.
_RUN_NS = uuid.UUID("6f0c1c1e-83a4-49b0-8f6e-7a1c0de5eed1")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log(msg):
    print("[launch_events] %s" % msg, file=sys.stderr, flush=True)


def _token(env):
    direct = (env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or "").strip()
    path = env.get("LAUNCH_EVENTS_TOKEN_FILE") or env.get("SKILL71_RUNS_SHIP_TOKEN_FILE")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return direct
    return direct


def _url(env):
    explicit = (env.get("LAUNCH_EVENTS_URL") or "").strip()
    if explicit:
        return explicit
    base = (env.get("COMMAND_CENTER_URL") or env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    return base + INGEST_PATH if base else ""


def _spool_dir(env):
    explicit = (env.get("LAUNCH_EVENTS_SPOOL") or "").strip()
    if explicit:
        return Path(explicit)
    return Path(env.get("HOME") or os.path.expanduser("~")) / ".openclaw" / "data" / \
        "signature-launch" / "events-spool"


def build_event(skill, launch_id, event, env=None):
    """Complete a caller's event into a contract-shaped launch run event.

    ``event`` is a dict with at least ``event_type``, or a plain stage name
    (shorthand for a passing ``stage_closed``). Caller fields always win.
    """
    env = os.environ if env is None else env
    if isinstance(event, str):
        event = {"event_type": "stage_closed", "stage": event}
    now = _now()
    out = dict(event)
    out["skill"] = int(skill)
    out["launch_id"] = str(launch_id)
    out.setdefault("event_id", str(uuid.uuid4()))
    out.setdefault("run_id", str(uuid.uuid5(_RUN_NS, "%s:%s" % (int(skill), launch_id))))
    out.setdefault("schema_version", SCHEMA_VERSION)
    out.setdefault("emitted_at", now)
    kind = out.get("event_type")
    if kind == "run_initialized":
        out.setdefault("host_shape", env.get("LAUNCH_EVENTS_HOST_SHAPE") or "fleet-mac")
    elif kind == "stage_closed":
        out.setdefault("receipt_status", "pass")
        out.setdefault("closed_at", now)
    elif kind == "stage_blocked":
        out.setdefault("failures", [])
        out.setdefault("blocked_at", now)
    elif kind == "item_closed":
        out.setdefault("closed_at", now)
    elif kind == "item_blocked":
        out.setdefault("failures", [])
        out.setdefault("blocked_at", now)
    return out


def _post(url, token, events, timeout):
    """POST one batch. Returns the HTTP status; raises only network errors."""
    req = urllib.request.Request(
        url, data=json.dumps({"events": events}).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _spool(spool, event, name=SPOOL_FILE):
    spool.mkdir(parents=True, exist_ok=True)
    with open(spool / name, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def drain(env=None, post=None):
    """Replay the spool, oldest first. Returns {"sent": n, "left": n}.

    Stops at the first transient failure (order is kept). A 422 is a permanent
    contract rejection: that line moves to the rejected file, never retried.
    Never raises.
    """
    env = os.environ if env is None else env
    sent = left = 0
    try:
        spool = _spool_dir(env)
        path = spool / SPOOL_FILE
        url = _url(env)
        if not url or not path.is_file():
            return {"sent": 0, "left": _count(path)}
        token, send = _token(env), post or _post
        try:
            timeout = float(env.get("LAUNCH_EVENTS_TIMEOUT") or 3)
        except ValueError:
            timeout = 3.0
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        kept = []
        for i, raw in enumerate(lines):
            try:
                status = send(url, token, [json.loads(raw)], timeout)
            except Exception:  # noqa: BLE001 - outage: keep this and the rest
                kept = lines[i:]
                break
            if 200 <= status < 300:
                sent += 1
            elif status == 422:
                _spool(spool, json.loads(raw), REJECTED_FILE)
            else:
                kept = lines[i:]
                break
        left = len(kept)
        tmp = path.with_suffix(".tmp")
        if kept:
            tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        else:
            path.unlink()
    except Exception as exc:  # noqa: BLE001 - the spool is never a gate
        _log("drain skipped (%s)" % type(exc).__name__)
    return {"sent": sent, "left": left}


def _count(path):
    try:
        return len([ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()])
    except OSError:
        return 0


def emit(skill, launch_id, event, env=None, post=None):
    """Send one launch event to the Command Center; spool it on any failure.

    Returns {"event_id", "sent": bool, "spooled": bool}. NEVER raises.
    """
    env = os.environ if env is None else env
    result = {"event_id": None, "sent": False, "spooled": False}
    try:
        body = build_event(skill, launch_id, event, env)
        result["event_id"] = body["event_id"]
        url = _url(env)
        try:
            timeout = float(env.get("LAUNCH_EVENTS_TIMEOUT") or 3)
        except ValueError:
            timeout = 3.0
        if url and _count(_spool_dir(env) / SPOOL_FILE):
            # A backlog exists: queue behind it so the CC sees events oldest first.
            _spool(_spool_dir(env), body)
            result["sent"] = drain(env, post)["left"] == 0
            result["spooled"] = not result["sent"]
            return result
        if url:
            try:
                status = (post or _post)(url, _token(env), [body], timeout)
                if 200 <= status < 300:
                    result["sent"] = True
                    return result
                if status == 422:  # contract rejection: retrying cannot help
                    _log("CC rejected event %s (HTTP 422); kept in rejected spool" % body["event_id"])
                    _spool(_spool_dir(env), body, REJECTED_FILE)
                    return result
                _log("CC ingest answered HTTP %s; spooling" % status)
            except Exception as exc:  # noqa: BLE001 - CC outage never fails a launch
                _log("CC ingest unreachable (%s); spooling" % type(exc).__name__)
        _spool(_spool_dir(env), body)
        result["spooled"] = True
    except Exception as exc:  # noqa: BLE001
        _log("emit skipped (%s: %s)" % (type(exc).__name__, exc))
    return result
