"""gates.py - N-86: the eight step gates of section 10C as code.

pre-flight and the look lock -> story -> reference -> picture (with the
side-by-side pass) -> approval -> spend guard -> take -> delivery. Only MAJOR
findings stop an item (section 3J); the approval gate carries the run owner's
"go ahead if every check passes" choice.

Stdlib only. State lives at control/step-gates.json inside the run folder.
"""
import json
import os
import time

SCHEMA = "blackceo.step-gates/v1"

#: The eight gates, in order, with the thing each stands in front of.
GATES = (
    ("preflight", "anything paid"),
    ("story", "every keyframe"),
    ("reference", "any keyframe that uses the sheets"),
    ("picture", "the video burst"),
    ("approval", "the video burst"),
    ("spend", "every burst"),
    ("take", "the timeline"),
    ("delivery", "anything sent to anyone"),
)

MAJOR = "MAJOR"


class GateRefused(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _path(run_dir):
    return os.path.join(os.path.abspath(run_dir), "control", "step-gates.json")


def _load(run_dir):
    try:
        with open(_path(run_dir), "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    doc.setdefault("schema", SCHEMA)
    doc.setdefault("gates", {})
    return doc


def _save(run_dir, doc):
    path = _path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def record(run_dir, gate, findings=None, passed=None, note=None, now=None):
    """Record one gate's result. Only a MAJOR finding closes a gate.

    ``findings`` is a list of {"level": "MAJOR"|"MEDIUM"|"MINOR", "code", ...}.
    ``passed`` forces the verdict (used by the run owner's approval and the
    spend guard); otherwise any MAJOR closes it.
    """
    if gate not in dict(GATES):
        raise GateRefused("GATE_UNKNOWN", "no gate named %r" % gate)
    findings = list(findings or [])
    majors = [f for f in findings if str(f.get("level", "")).upper() == MAJOR]
    verdict = bool(passed) if passed is not None else not majors
    doc = _load(run_dir)
    doc["gates"][gate] = {"open": verdict, "findings": findings,
                          "majors": [f.get("code") for f in majors],
                          "note": note, "at": time.time() if now is None else now}
    _save(run_dir, doc)
    return {"gate": gate, "open": verdict, "majors": [f.get("code") for f in majors]}


def approval_choice(run_dir, status, now=None):
    """Gate 5. ``go_ahead_if_pass`` skips the pause; anything else waits."""
    if status not in ("approved", "go_ahead_if_pass"):
        return record(run_dir, "approval", passed=False,
                      note="run owner has not chosen; the clock pauses", now=now)
    return record(run_dir, "approval", passed=True, note=status, now=now)


def is_open(run_dir, gate):
    doc = _load(run_dir)
    return bool((doc["gates"].get(gate) or {}).get("open"))


def require(run_dir, gate, next_gate=None):
    """Refuse to start the item a closed gate stands in front of."""
    if is_open(run_dir, gate):
        return True
    rec = _load(run_dir)["gates"].get(gate) or {}
    raise GateRefused("GATE_CLOSED",
                      "gate %r is closed%s: %s"
                      % (gate, " for %s" % next_gate if next_gate else "",
                         ", ".join(rec.get("majors") or []) or rec.get("note") or "not run"))


def gate_for_item(item):
    """Which gate stands in front of one production item (10C's list)."""
    item = str(item or "").lower()
    if item in ("keyframe", "keyframes", "storyboard"):
        return "story"
    if item in ("reference", "references", "character-sheet", "place-picture"):
        return "reference"
    if item in ("video-burst", "clip", "clips", "picture"):
        return "picture"
    if item in ("burst", "spend", "paid-job"):
        return "spend"
    if item in ("take", "timeline", "master"):
        return "take"
    if item in ("delivery", "message", "link"):
        return "delivery"
    if item in ("first-paid-job", "anything-paid"):
        return "preflight"
    return None
