#!/usr/bin/env python3
"""native_rate.py: the native-rate duplicate gate before any spend (F-CG-2).

The 2.0 percent duplicate cap exists today only after the money is gone: the
assembler measures the rendered master (``fps_conform.assert_no_dupe_frames``)
and per-segment (``segment_dup_report``, where a deliberate ``hold`` is
reported but never failed). A dup-heavy take therefore reached assembly and
was paid for. This gate runs on the DOWNLOADED TAKE, at intake/pre-flight,
before any clip money is spent:

  * the model's native rate comes from the existing ``fps_conform.native_fps``
    (the one lookup the assembler already uses), so the gate and the
    assembler can never disagree about a model's rate;
  * ``fps_conform.measure_dup_pct`` supplies the real mpdecimate measurement;
  * over 2.0 percent at native rate refuses intake with
    ``NATIVE_DUP_TOO_HIGH``.

A plan segment marked ``hold`` is a deliberate still and is exempt in the
same way the assembler exempts it: reported, never failed. An unknown model
or a failed measurement is ``NATIVE_DUP_MEASURE_FAILED`` / ``NATIVE_RATE_UNKNOWN``
and never a pass.

The pre-flight caller lives in ``intake_preflight`` (another unit's file); it
calls ``intake_gate`` here. No spend, stdlib plus ffmpeg.
"""
from __future__ import annotations

import os
import sys

_core = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _core not in sys.path:
    sys.path.insert(0, _core)
from final_assembler import fps_conform  # noqa: E402

TOOL_NAME = "native_rate"
TOOL_VERSION = "1.0.0"

NATIVE_DUP_TOO_HIGH = "NATIVE_DUP_TOO_HIGH"
NATIVE_RATE_UNKNOWN = "NATIVE_RATE_UNKNOWN"
NATIVE_DUP_MEASURE_FAILED = "NATIVE_DUP_MEASURE_FAILED"


def native_rate_row(path, model, ffmpeg="ffmpeg", run=None, cap=None,
                    hold=False):
    """One intake row for a downloaded take.

    ``verdict`` PASS | FAIL | EXEMPT | UNAVAILABLE. ``hold`` marks a
    deliberate still: the number is reported, the row never fails (the same
    exemption the assembler's per-segment report gives).
    """
    cap = fps_conform.DUP_FRAMES_CAP if cap is None else float(cap)
    row = {"path": os.fspath(path) if path else path, "model": model,
           "cap": cap, "native_fps": None, "dup_pct": None,
           "hold": bool(hold), "verdict": "UNAVAILABLE", "reason_code": None}
    fps = fps_conform.native_fps(model)
    if fps is None:
        row["reason_code"] = NATIVE_RATE_UNKNOWN
        return row
    row["native_fps"] = fps
    try:
        pct = fps_conform.measure_dup_pct(path, ffmpeg=ffmpeg, run=run)
    except (OSError, RuntimeError) as exc:
        row["reason_code"] = NATIVE_DUP_MEASURE_FAILED
        row["detail"] = str(exc)
        return row
    row["dup_pct"] = float(pct)
    if hold:
        row["verdict"] = "EXEMPT"
        return row
    if row["dup_pct"] > cap:
        row["verdict"] = "FAIL"
        row["reason_code"] = NATIVE_DUP_TOO_HIGH
        return row
    row["verdict"] = "PASS"
    return row


def intake_gate(rows):
    """Refuse intake when any take is over the cap or unmeasured.

    Returns ``{"pass": bool, "findings": [{path, code, detail}], "rows": []}``.
    EXEMPT holds are carried in ``rows`` and never in ``findings``.
    """
    findings = []
    for r in rows or []:
        if r.get("verdict") in ("PASS", "EXEMPT"):
            continue
        code = r.get("reason_code") or NATIVE_RATE_UNKNOWN
        findings.append({"path": r.get("path"), "code": code,
                         "detail": ("dup %.2f%% > %.2f%% at %s fps"
                                    % (r.get("dup_pct"), r.get("cap"),
                                       r.get("native_fps"))
                                    if code == NATIVE_DUP_TOO_HIGH
                                    else code)})
    return {"pass": not findings, "findings": findings,
            "rows": list(rows or [])}


if __name__ == "__main__":
    # Control: a take over the cap refuses intake before spend; a hold is
    # reported and never fails; an unknown native rate is unavailable, never a
    # pass. fps_conform is stubbed so no video is needed.
    import types
    real = native_rate_module = None
    orig_nf, orig_mp = fps_conform.native_fps, fps_conform.measure_dup_pct
    orig_cap = getattr(fps_conform, "DUP_FRAMES_CAP", None)
    try:
        fps_conform.native_fps = lambda model: 24
        fps_conform.measure_dup_pct = lambda path, **kw: 3.5
        over = native_rate_row("take.mp4", "minimax-h3", cap=2.0)
        assert over["verdict"] == "FAIL"
        assert over["reason_code"] == NATIVE_DUP_TOO_HIGH
        held = native_rate_row("take.mp4", "minimax-h3", cap=2.0, hold=True)
        assert held["verdict"] == "EXEMPT"
        gate = intake_gate([over, held])
        assert not gate["pass"] and gate["findings"][0]["code"] == \
            NATIVE_DUP_TOO_HIGH
        fps_conform.measure_dup_pct = lambda path, **kw: 0.5
        assert native_rate_row("take.mp4", "minimax-h3", cap=2.0)["verdict"] \
            == "PASS"
        fps_conform.native_fps = lambda model: None
        unknown = native_rate_row("take.mp4", "mystery")
        assert unknown["verdict"] == "UNAVAILABLE" and \
            unknown["reason_code"] == NATIVE_RATE_UNKNOWN
        assert not intake_gate([unknown])["pass"]
    finally:
        fps_conform.native_fps = orig_nf
        fps_conform.measure_dup_pct = orig_mp
        if orig_cap is not None:
            fps_conform.DUP_FRAMES_CAP = orig_cap
    print("native_rate: control PASS")
