"""reaper.py - N-110: the tagged-browser reaper and the disk check (3D.8 B4/B5).

Every 5 minutes the reaper kills only browser processes that carry the
video-tool tag AND are either orphaned (their wrapper is gone) or older than
the render timeout. It deletes only tagged temp folders that belong to no
living render. It never touches an untagged browser, profile or folder: the
client's own browsers and downloads are never looked at. It logs silently and
never sends a client a message.

Severity (3J): a tagged browser left after its render is MEDIUM; a leak that
threatens the disk or memory (free disk under 10 percent, or memory pressure
above 85 percent with tagged browsers alive) is MAJOR and is fixed at once,
without stopping the run. The disk check runs at pre-flight and at delivery.

Stdlib only; process and folder lists are supplied by the caller.
"""
import os
import shutil

DEFAULT_TAG = "s75-video"
REAPER_INTERVAL_S = 300
DEFAULT_TIMEOUT_S = 600
MAJOR_FREE_FRACTION = 0.10
PRESSURE_HOLD = 0.85


def _browser_budget():
    import json
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        cand = os.path.join(d, "references", "time-budgets.json")
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as fh:
                    return json.load(fh).get("browser") or {}
            except (OSError, ValueError):
                return {}
        d = os.path.dirname(d)
    return {}


def is_tagged(cmdline, tag=None):
    tag = tag or _browser_budget().get("tag") or DEFAULT_TAG
    return bool(cmdline) and tag in str(cmdline)


def reap(processes, temp_dirs, *, now=None, tag=None, timeout_s=None,
         kill=None, remove=None):
    """Return the kill/delete actions; only tagged items are ever touched."""
    import time
    now = float(now if now is not None else time.time())
    browser = _browser_budget()
    tag = tag or browser.get("tag") or DEFAULT_TAG
    timeout_s = timeout_s or max((browser.get("timeouts_s") or {}).values()
                                 or [DEFAULT_TIMEOUT_S])
    actions, log = [], []
    for proc in processes or []:
        if not is_tagged(proc.get("cmdline"), tag):
            continue                                  # never an untagged browser
        started = proc.get("started_unix")
        too_old = isinstance(started, (int, float)) and now - started > timeout_s
        orphaned = proc.get("wrapper_alive") is False
        if not (too_old or orphaned):
            continue
        reason = "orphaned" if orphaned else "past the %ds timeout" % timeout_s
        actions.append({"action": "kill", "pid": proc.get("pid"),
                        "reason": reason, "severity": "MEDIUM"})
        log.append("killed tagged browser pid %s (%s)" % (proc.get("pid"), reason))
        if kill:
            kill(proc.get("pid"))
    for folder in temp_dirs or []:
        if not folder.get("tagged") or folder.get("live_render"):
            continue
        actions.append({"action": "delete", "path": folder.get("path"),
                        "severity": "MEDIUM"})
        log.append("deleted tagged temp folder %s" % folder.get("path"))
        if remove:
            remove(folder.get("path"))
    return {"actions": actions, "log": log, "interval_s": REAPER_INTERVAL_S,
            "tag": tag, "silent": True}


def disk_check(path, *, min_free_fraction=None, memory_pressure=None,
               tagged_alive=0):
    """Pre-flight and delivery disk check with its severity (3J item 18)."""
    try:
        usage = shutil.disk_usage(path)
        free_fraction = usage.free / usage.total if usage.total else 1.0
    except OSError as exc:
        return {"ok": False, "severity": "MAJOR", "detail": str(exc)[:200]}
    floor = MAJOR_FREE_FRACTION if min_free_fraction is None else min_free_fraction
    pressure = memory_pressure or 0
    if free_fraction < floor or (pressure > PRESSURE_HOLD and tagged_alive > 0):
        severity = "MAJOR"
    elif tagged_alive > 0:
        severity = "MEDIUM"
    else:
        severity = "OK"
    return {"ok": True, "free_fraction": round(free_fraction, 4),
            "free_bytes": usage.free, "tagged_alive": tagged_alive,
            "memory_pressure": pressure, "severity": severity,
            "leftovers_reported": tagged_alive > 0,
            "detail": "free disk %.1f%%" % (free_fraction * 100)}


def severity_of(action):
    """A leftover after its render is MEDIUM; a disk/memory threat is MAJOR."""
    return action.get("severity", "MEDIUM")
