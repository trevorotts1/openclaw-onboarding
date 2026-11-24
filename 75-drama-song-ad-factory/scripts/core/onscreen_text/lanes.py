#!/usr/bin/env python3
"""lanes.py: lane-aware OCR verdicts for the text sweep (F-OCR-1, OCR half).

The old sweep returned one verdict per path with no lane distinction, and
that produced 13 false-CLEAN rows: landed ``clips/`` takes called CLEAN while
their v7 fix-lane takes were lettered, and the worst miss ``clips/T28.mp4``
CLEAN with 0 tokens beside fix takes reading 13 and 11 tokens. Six more were
false-LETTERS on superseded lanes. The verdict is therefore keyed by LANE:

  * ``landed``     the path that will actually play (under ``clips/``)
  * ``fix-lane``   a repair lane (``motion-fix/``, ``lipsync-fix/``, ``*-fix``)
  * ``superseded`` a lane the run retired
  * ``unknown``    no lane marker: never used to claim anything

Rules (binding):
  1. The sweep is control-gated: a known-dirty frame must read LETTERS and a
     known-clean frame must read CLEAN, and the report carries
     ``discriminates: true``. Otherwise the whole sweep is UNCALIBRATED.
  2. ``tokens_seen`` is disclosed beside every CLEAN. A CLEAN with no token
     count is UNCALIBRATED.
  3. A landed CLEAN beside any lettered non-landed lane is UNCALIBRATED: the
     T28-class miss, where a fix lane proves letters the landed path missed.
  4. A swap claim ("this take replaces that one, and the take is letter
     clean") needs an OCR-CLEAN row on the LANDED path. A landed LETTERS row
     refuses the claim outright (a clean fix lane can never carry it).

This module owns the sweep procedure only; the pixel reader (L01) is held,
and frame_text.py's reader bar is another unit's file (noted to its owner).
stdlib only, no spend, no reader of its own.
"""
from __future__ import annotations

TOOL_NAME = "ocr_lanes"
TOOL_VERSION = "1.0.0"

LANE_LANDED = "landed"
LANE_FIX = "fix-lane"
LANE_SUPERSEDED = "superseded"
LANE_UNKNOWN = "unknown"
LANES = (LANE_LANDED, LANE_FIX, LANE_SUPERSEDED, LANE_UNKNOWN)

VERDICT_CLEAN = "CLEAN"
VERDICT_LETTERS = "LETTERS"
VERDICTS = (VERDICT_CLEAN, VERDICT_LETTERS)

UNCALIBRATED = "UNCALIBRATED"
LETTER_GATE_UNAVAILABLE = "LETTER_GATE_UNAVAILABLE"
SWAP_CLAIM_REFUSED = "SWAP_CLAIM_REFUSED"
LANDED_PATH_LETTERED = "LANDED_PATH_LETTERED"
TOKENS_NOT_DISCLOSED = "TOKENS_NOT_DISCLOSED"

_FIX_MARKERS = ("motion-fix", "lipsync-fix", "lip-fix", "-fix/", "/fix/",
                "fix-lane", "redo")


def classify(path):
    """The lane a path belongs to, from its own segments only."""
    if not isinstance(path, str) or not path.strip():
        return LANE_UNKNOWN
    p = path.replace("\\", "/").lower()
    if "superseded" in p or "/old/" in p:
        return LANE_SUPERSEDED
    if any(marker in p for marker in _FIX_MARKERS):
        return LANE_FIX
    if p.startswith("clips/") or "/clips/" in p:
        return LANE_LANDED
    return LANE_UNKNOWN


def _tokens(row):
    value = row.get("tokens_seen")
    return value if isinstance(value, int) and value >= 0 else None


def _norm_verdict(row):
    return str(row.get("verdict", "")).strip().upper()


def control_ok(control):
    """The control pair must tell a dirty frame from a clean one."""
    if not isinstance(control, dict):
        return False
    dirty = str(control.get("dirty", "")).strip().upper()
    clean = str(control.get("clean", "")).strip().upper()
    return (bool(control.get("discriminates")) and dirty == VERDICT_LETTERS
            and clean == VERDICT_CLEAN)


def sweep_verdict(rows, control=None):
    """Key every row by lane and decide whether the sweep can be trusted.

    Returns ``{"calibrated", "discriminates", "findings", "rows", "lanes"}``.
    A row keeps ``lane``, ``verdict``, ``tokens_seen`` and gains ``trusted``;
    nothing here writes a claim -- ``claim_letter_clean`` does that.
    """
    findings = []
    trusted = control_ok(control)
    if not trusted:
        findings.append({"code": LETTER_GATE_UNAVAILABLE,
                         "detail": "controls did not tell dirty from clean"})
    out = []
    for row in rows or []:
        lane = row.get("lane") or classify(row.get("path"))
        verdict = _norm_verdict(row)
        tokens = _tokens(row)
        r = dict(row)
        r.update({"lane": lane if lane in LANES else LANE_UNKNOWN,
                  "verdict": verdict, "tokens_seen": tokens})
        if verdict == VERDICT_CLEAN and tokens is None:
            r["trusted"] = False
            findings.append({"code": TOKENS_NOT_DISCLOSED,
                             "path": r.get("path"),
                             "detail": "a CLEAN row must carry tokens_seen"})
        else:
            r["trusted"] = trusted
        out.append(r)
    landed_clean = [r for r in out
                    if r["lane"] == LANE_LANDED and r["verdict"] == VERDICT_CLEAN]
    lettered_other = [r for r in out
                      if r["lane"] != LANE_LANDED and r["verdict"] == VERDICT_LETTERS]
    if landed_clean and lettered_other:
        findings.append({"code": UNCALIBRATED,
                         "detail": ("landed path reads CLEAN while %d "
                                    "non-landed lane(s) read LETTERS"
                                    % len(lettered_other)),
                         "paths": [r.get("path") for r in lettered_other]})
        for r in landed_clean:
            # The T28 class: a landed CLEAN whose fix lanes read LETTERS is
            # not a clean landed path. It says UNCALIBRATED, not CLEAN, so no
            # reader downstream can quote it as a pass.
            r["trusted"] = False
            r["verdict"] = UNCALIBRATED
    lanes = {}
    for r in out:
        lanes.setdefault(r["lane"], []).append(r.get("path"))
    calibrated = trusted and not any(f["code"] == UNCALIBRATED for f in findings)
    return {"calibrated": calibrated, "discriminates": bool(trusted),
            "findings": findings, "rows": out, "lanes": lanes}


def claim_letter_clean(rows, path, control=None):
    """Can this path carry a letter-clean claim? Landed CLEAN only.

    Returns ``{allowed, code, detail, row}``. A landed LETTERS row refuses
    with LANDED_PATH_LETTERED even when a fix lane is clean; a clean fix-lane
    row refuses with SWAP_CLAIM_REFUSED, because the claim belongs to the path
    that plays.
    """
    sweep = sweep_verdict(rows, control=control)
    target = None
    for r in sweep["rows"]:
        if r.get("path") == path:
            target = r
            break
    if target is None:
        return {"allowed": False, "code": SWAP_CLAIM_REFUSED,
                "detail": "no sweep row for the claimed path", "row": None}
    lane = target["lane"]
    if lane == LANE_LANDED and target["verdict"] == VERDICT_LETTERS:
        return {"allowed": False, "code": LANDED_PATH_LETTERED,
                "detail": "the landed path is lettered; a clean fix lane "
                          "cannot replace the claim", "row": target}
    if lane != LANE_LANDED:
        return {"allowed": False, "code": SWAP_CLAIM_REFUSED,
                "detail": "a claim needs the landed path, not a %s lane" % lane,
                "row": target}
    if not sweep["calibrated"]:
        return {"allowed": False, "code": UNCALIBRATED,
                "detail": "the sweep did not pass its controls",
                "row": target}
    if target["verdict"] != VERDICT_CLEAN:
        return {"allowed": False, "code": SWAP_CLAIM_REFUSED,
                "detail": "the landed path is not OCR-clean", "row": target}
    return {"allowed": True, "code": None, "detail": "", "row": target,
            "tokens_seen": target["tokens_seen"]}


if __name__ == "__main__":
    # F-OCR-1's two named cases, plus the control gate.
    ctl = {"dirty": "LETTERS", "clean": "CLEAN", "discriminates": True}

    # Case 1: the worst miss. `clips/T28.mp4` read CLEAN while both T28 fix
    # takes read LETTERS -> the landed CLEAN is UNCALIBRATED, never a claim.
    t28 = [
        {"path": "clips/T28.mp4", "verdict": "CLEAN", "tokens_seen": 0},
        {"path": "lipsync-fix/T28-a.mp4", "verdict": "LETTERS", "tokens_seen": 13},
        {"path": "lipsync-fix/T28-b.mp4", "verdict": "LETTERS", "tokens_seen": 11},
    ]
    out = sweep_verdict(t28, ctl)
    assert out["calibrated"] is False
    assert [f["code"] for f in out["findings"]] == [UNCALIBRATED]
    assert [r["trusted"] for r in out["rows"]] == [False, True, True]
    assert claim_letter_clean(out["rows"], "clips/T28.mp4", ctl)["allowed"] \
        is False

    # Case 2: the T09 swap. The landed path is LETTERS, so a clean fix lane
    # cannot carry the claim.
    t09 = [
        {"path": "clips/T09.mp4", "verdict": "LETTERS", "tokens_seen": 7},
        {"path": "lipsync-fix/T09.mp4", "verdict": "CLEAN", "tokens_seen": 0},
    ]
    out = sweep_verdict(t09, ctl)
    landed = claim_letter_clean(out["rows"], "clips/T09.mp4", ctl)
    assert landed["allowed"] is False and landed["code"] == LANDED_PATH_LETTERED
    swap = claim_letter_clean(out["rows"], "lipsync-fix/T09.mp4", ctl)
    assert swap["allowed"] is False and swap["code"] == SWAP_CLAIM_REFUSED

    # The control gate and the token disclosure.
    assert sweep_verdict(t28, None)["calibrated"] is False
    assert sweep_verdict(t28, None)["findings"][0]["code"] == \
        LETTER_GATE_UNAVAILABLE
    assert sweep_verdict([{"path": "clips/T01.mp4", "verdict": "CLEAN"}],
                         ctl)["findings"][0]["code"] == TOKENS_NOT_DISCLOSED

    # Lanes.
    assert classify("clips/T04.mp4") == LANE_LANDED
    assert classify("motion-fix/kling/T04.mp4") == LANE_FIX
    assert classify("superseded/T04.mp4") == LANE_SUPERSEDED
    print("lanes: control PASS")
