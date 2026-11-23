"""markers.py - N-51: a step is finished when it writes a completion marker
holding its output's fingerprint. The next step waits on the marker, never on
a timer; an overdue marker restarts that one step (section 10E loop).

Stdlib only. Markers live at control/markers/<step>.json.
"""
import hashlib
import json
import os
import time

SCHEMA = "blackceo.completion-marker/v1"


def _marker_path(run_dir, step):
    return os.path.join(os.path.abspath(run_dir), "control", "markers",
                        "%s.json" % step)


def fingerprint(path):
    """SHA-256 of a file's bytes, or None when it cannot be read."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def write_marker(run_dir, step, output_path, deadline_minutes=None, now=None):
    """Write the marker atomically. No output file, no marker."""
    out = os.path.abspath(os.fspath(output_path))
    fp = fingerprint(out)
    if fp is None:
        return {"ok": False, "code": "MARKER_OUTPUT_MISSING",
                "detail": "output is missing or unreadable: %s" % output_path}
    rec = {"schema": SCHEMA, "step": step, "output": out, "fingerprint": fp,
           "bytes": os.path.getsize(out),
           "completed_at": time.time() if now is None else now,
           "deadline_minutes": deadline_minutes}
    path = _marker_path(run_dir, step)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return {"ok": True, "marker": rec, "code": None}


def read_marker(run_dir, step):
    try:
        with open(_marker_path(run_dir, step), "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def is_complete(run_dir, step):
    """Present AND its output still has the fingerprinted bytes (a stale or
    replaced output is not complete)."""
    rec = read_marker(run_dir, step)
    if not rec:
        return False
    return fingerprint(rec.get("output", "")) == rec.get("fingerprint")


def is_overdue(run_dir, step, started_at, deadline_minutes, now=None):
    """True when the step has no valid marker and its deadline has passed."""
    if is_complete(run_dir, step):
        return False
    now = time.time() if now is None else now
    if started_at is None:
        return False
    return (now - started_at) > (float(deadline_minutes or 0) * 60.0)


def next_ready(run_dir, previous_step):
    """The next step may start only on the previous marker -- never on a timer."""
    ready = is_complete(run_dir, previous_step)
    return {"ready": ready,
            "detail": None if ready else
            "waiting on the completion marker of %r (no timer decides a step)"
            % previous_step}


def restart_step(run_dir, step):
    """Overdue markers restart THAT ONE STEP. The marker is cleared; nothing
    else in the run is touched."""
    try:
        os.remove(_marker_path(run_dir, step))
        return {"restarted": True, "step": step}
    except FileNotFoundError:
        return {"restarted": False, "step": step, "detail": "no marker to clear"}
