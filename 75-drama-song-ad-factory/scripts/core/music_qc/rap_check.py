#!/usr/bin/env python3
"""rap_check: the rap-versus-sung gate. FAIL-CLOSED, no invented threshold.

The analysis lane measured `controls.rap_control` as UNMEASURED with the
reason recorded: "no independently labelled rap audio control available;
non-sung != rap". The existing detector (song_contract) is sung / not-sung
only. Non-sung alone must NEVER earn a rap PASS.

So this module does NOT prescribe a cadence number and does NOT ship an
automatic rap classifier. It requires a LABELLED fixture set -- a POSITIVE
real rap control plus a sung negative and a spoken-over-beat negative -- and
returns UNMEASURED until that fixture exists. UNMEASURED blocks a take PASS
(QC 17.8: no evidence supplied; cannot pass). Nothing here is calibrated.

Fixture: point ``SONG_RAP_CONTROL`` at a JSON file
{"rap": <path>, "sung": <path>, "spoken_over_beat": <path>} of local audio
clips. Absent or incomplete -> UNMEASURED, never a pass.
"""
from __future__ import annotations

import json
import os

TOOL_NAME = "rap_check"
TOOL_VERSION = "1.0.0"

CONTROL_ENV = "SONG_RAP_CONTROL"
REQUIRED = ("rap", "sung", "spoken_over_beat")


class RapControlError(ValueError):
    """A malformed control fixture: loud, never a silent pass."""


def control_paths(env=None):
    """The labelled fixture paths, or {} when unavailable (fail closed)."""
    p = (env if env is not None else os.environ).get(CONTROL_ENV)
    if not p or not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(rows, dict):
        return {}
    for k in REQUIRED:
        v = rows.get(k)
        if not v or not os.path.isfile(str(v)):
            return {}
    return {k: str(rows[k]) for k in REQUIRED}


def control_ready(env=None):
    """True only when all three labelled controls are present on disk."""
    return len(control_paths(env)) == len(REQUIRED)


def classify(segments, env=None):
    """The rap gate for one take. ``segments`` = the detector's measured
    segments. Returns {verdict, reason, rap_seconds, controls}:
      * no labelled control      -> UNMEASURED (never PASS)
      * control present          -> the labelled control decides; until a
        classifier is calibrated against one this stays UNMEASURED too.
    """
    ctrl = control_paths(env)
    rap_s = sum(float(s.get("end", 0)) - float(s.get("start", 0))
                for s in (segments or [])
                if isinstance(s, dict) and s.get("delivery") == "rap")
    if not ctrl:
        return {"verdict": "UNMEASURED", "rap_seconds": rap_s, "controls": [],
                "reason": "no labelled rap control (rap >= sung >= spoken-over-beat); "
                          "non-sung is not rap, so this cannot pass"}
    return {"verdict": "UNMEASURED", "rap_seconds": rap_s, "controls": sorted(ctrl),
            "reason": "labelled controls present but no calibrated rap classifier "
                      "ships yet; UNMEASURED blocks PASS (QC 17.8)"}


def gate(segments, env=None):
    """Alias used by the take judge."""
    return classify(segments, env=env)
