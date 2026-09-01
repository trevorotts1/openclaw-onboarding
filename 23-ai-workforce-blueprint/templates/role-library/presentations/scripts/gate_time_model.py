#!/usr/bin/env python3
"""gate_time_model.py — adaptive VSL email/phone gate placement.

The VSL gate timestamp is NOT hardcoded to 8:00. It is adaptive
(DESIGN-OPUS S6.3): the gate sits between 3:00 and 8:00, biased toward
8:00, AFTER the FIRST BIG REVELATION of the deck's narrative arc.

Placement rule:
    gate_time = clamp(R + 20s, 180s, 480s)

where R is the first-big-revelation video timestamp, derived by mapping the
revelation slide to the video timeline via the webinar slide->time mapping
(webinar_timing.py: audio_start of the revelation slide).

Fail-closed defaults (S6.3):
    * R unknown (no slide->time mapping / no metadata):
        gate_time = min(0.9 * D, 480s), never below 180s, never above D - 10s.
        R-unknown is FLAGGED so QC sees the degradation, never silent.
    * D < 180s (video shorter than the floor): the gate is clamped to 180s but
        if the video cannot even reach 190s (180s gate + 10s tail) the gate
        would be unusable — we fail closed by pinning to 180s and FLAGGING.
    * D unknown: gate_time = 480s default and FLAGGED (fail-closed to 8:00).

Never out of band: the returned gate_time is ALWAYS inside [180, 480] and
ALWAYS <= max(D - 10, 0) when D is known. It never seeks the video outside the
3:00-8:00 window (that is the JS seek-scope's window too — see
vsl_gate_overlay.js).

stdlib-only. Zero Anthropic ids. Deterministic.

Usage:
    python3 gate_time_model.py --self-test
    python3 gate_time_model.py --duration 900 --revelation-time 400
    python3 gate_time_model.py --duration 900 --revelation-slide 12 \
        --slide-map '{"1":0,"12":402,"20":880}'
    python3 gate_time_model.py --duration 900                # R unknown -> fail closed
"""

from __future__ import annotations

import argparse
import json
import math
import sys

GATE_FLOOR_SEC = 180     # 3:00
GATE_CEIL_SEC = 480      # 8:00
REVELATION_LEAD_SEC = 20  # gate sits 20s after the revelation
MIN_TAIL_SEC = 10        # never place a gate within 10s of video end


class FlaggedGate(dict):
    """dict subclass carrying a human/machine-readable flag list."""

    def __init__(self, *args, flags=None, **kwargs):
        super().__init__(*args, **kwargs)
        self["flags"] = flags or []


def _flag(fg: FlaggedGate, msg: str) -> None:
    fg["flags"].append(msg)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_gate_time(
    duration_seconds: float | None,
    revelation_time_seconds: float | None = None,
    revelation_slide: int | None = None,
    slide_map: dict | None = None,
) -> FlaggedGate:
    """Compute gate_time = clamp(R + 20s, 180s, 480s), fail-closed.

    Args:
        duration_seconds: total video duration from ffprobe / Agnes
            metadata.seconds. May be None (unknown).
        revelation_time_seconds: optional direct R (first big revelation video
            timestamp). If omitted, resolved from revelation_slide + slide_map.
        revelation_slide: optional revelation slide number.
        slide_map: optional {slide_no: audio_start_sec} mapping (webinar_timing).

    Returns:
        FlaggedGate with keys:
            gate_time_seconds   int, always in [180, 480], <= D - 10 when D known
            revelation_time_seconds   float | None  (the resolved R)
            basis               "revelation+lead" | "duration-fallback" | "default-8min"
            flags               list[str]
    """
    fg = FlaggedGate()
    fg["flags"] = []

    # ---- resolve R ----------------------------------------------------------
    r = revelation_time_seconds
    r_basis = "direct"

    if r is None and revelation_slide is not None and slide_map:
        if str(revelation_slide) in slide_map:
            r = float(slide_map[str(revelation_slide)])
            r_basis = f"slide_map[{revelation_slide}]"
        else:
            r = None
            _flag(fg, f"revelation slide {revelation_slide} not in slide_map; R unknown")

    if r is not None and not (isinstance(r, (int, float)) and math.isfinite(r) and r >= 0):
        _flag(fg, f"invalid revelation_time {r!r}; R unknown")
        r = None

    fg["revelation_time_seconds"] = r
    fg["revelation_basis"] = r_basis

    # ---- duration sanity ----------------------------------------------------
    d = None
    if duration_seconds is not None:
        if isinstance(duration_seconds, (int, float)) and math.isfinite(duration_seconds) and duration_seconds > 0:
            d = float(duration_seconds)
        else:
            _flag(fg, f"invalid duration {duration_seconds!r}; D unknown")

    if d is not None and d < GATE_FLOOR_SEC:
        _flag(fg, f"D={d:.0f}s < floor {GATE_FLOOR_SEC}s; gate pinned to floor, video too short for a usable gate")

    # ---- candidate gate time -------------------------------------------------
    if r is not None:
        gate = r + REVELATION_LEAD_SEC
        fg["basis"] = "revelation+lead"
    elif d is not None:
        # R unknown -> fall back to min(0.9 * D, 480), never below 180 (S6.3)
        gate = min(0.9 * d, GATE_CEIL_SEC)
        fg["basis"] = "duration-fallback"
        _flag(fg, "R unknown; used min(0.9*D, 8:00) duration fallback (FLAGGED)")
    else:
        # D and R both unknown -> fail closed to 8:00 (S6.3)
        gate = float(GATE_CEIL_SEC)
        fg["basis"] = "default-8min"
        _flag(fg, "R and D unknown; defaulted to 8:00 (FLAGGED, fail-closed)")

    # ---- clamp into the legal window ----------------------------------------
    gate = clamp(gate, GATE_FLOOR_SEC, GATE_CEIL_SEC)

    # ---- never above D - 10s when D is known --------------------------------
    if d is not None:
        max_with_tail = max(d - MIN_TAIL_SEC, 0.0)
        if gate > max_with_tail:
            before = gate
            gate = max_with_tail
            _flag(fg, f"gate {before:.0f}s would sit within {MIN_TAIL_SEC}s of video end; clamped to D-{MIN_TAIL_SEC}s={max_with_tail:.0f}s")

    # ---- final invariant re-check (never out of band) ------------------------
    gate = clamp(gate, GATE_FLOOR_SEC, GATE_CEIL_SEC)
    if d is not None:
        gate = min(gate, max(d - MIN_TAIL_SEC, 0.0))

    # A gate that cannot be reached (D <= floor+tail) still lands on the floor.
    gate = clamp(gate, GATE_FLOOR_SEC, GATE_CEIL_SEC)

    fg["gate_time_seconds"] = int(round(gate))
    return fg


def _fmt_flag(f: str) -> str:
    return f"    FLAG: {f}"


def _print_result(fg: FlaggedGate) -> None:
    print(f"  gate_time_seconds      = {fg['gate_time_seconds']}")
    print(f"  revelation_time_seconds= {fg['revelation_time_seconds']}")
    print(f"  revelation_basis       = {fg['revelation_basis']}")
    print(f"  basis                  = {fg['basis']}")
    if fg["flags"]:
        for f in fg["flags"]:
            print(_fmt_flag(f))
    else:
        print("    (no flags — clean adaptive placement)")


def self_test() -> None:
    """Prove the three required cases + fail-closed behaviour."""
    print("== gate_time_model.py self-test ==")
    failures = []

    def check(label, fg, expected, expect_flags=False):
        got = fg["gate_time_seconds"]
        ok = got == expected and (bool(fg["flags"]) == expect_flags)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {got}s expected {expected}s"
              f" flags={bool(fg['flags'])}")
        if not ok:
            failures.append(label)

    # Required case 1: R=120s -> gate=180s (clamped low)
    check("R=120s (clamp low)", compute_gate_time(duration_seconds=900, revelation_time_seconds=120), 180)

    # Required case 2: R=400s -> gate=420s
    check("R=400s (in-band)", compute_gate_time(duration_seconds=900, revelation_time_seconds=400), 420)

    # Required case 3: R=470s -> gate=480s (clamped high)
    check("R=470s (clamp high)", compute_gate_time(duration_seconds=900, revelation_time_seconds=470), 480)

    # R unknown, D known -> min(0.9*D, 480), flagged
    fg = compute_gate_time(duration_seconds=900)
    check("R unknown, D=900s (fail-closed fallback)", fg, 480, expect_flags=True)

    # R unknown, D short (120s) -> floor 180s + flag (video too short)
    fg = compute_gate_time(duration_seconds=120)
    check("D=120s too short", fg, 180, expect_flags=True)

    # R unknown, D unknown -> default 8:00 + flag
    fg = compute_gate_time(duration_seconds=None)
    check("R and D unknown (default 8:00)", fg, 480, expect_flags=True)

    # Slide-map resolution: slide 12 -> audio_start 402 -> gate 422
    smap = {"1": 0, "12": 402, "20": 880}
    fg = compute_gate_time(duration_seconds=900, revelation_slide=12, slide_map=smap)
    ok = fg["gate_time_seconds"] == 422 and fg["revelation_basis"] == "slide_map[12]"
    print(f"  [{'PASS' if ok else 'FAIL'}] slide_map resolution: got {fg['gate_time_seconds']}s expected 422s")
    if not ok:
        failures.append("slide_map resolution")

    # D small: gate within D-10s tail rule (R=300, D=320 -> gate <= 310)
    fg = compute_gate_time(duration_seconds=320, revelation_time_seconds=300)
    ok = fg["gate_time_seconds"] == 310
    print(f"  [{'PASS' if ok else 'FAIL'}] D-tail rule (D=320, R=300): got {fg['gate_time_seconds']}s expected 310s")
    if not ok:
        failures.append("D-tail rule")

    if failures:
        print(f"\nSELF-TEST: {len(failures)} FAILURE(S): {failures}")
        sys.exit(1)
    print("\nSELF-TEST: ALL PASS")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Adaptive VSL gate placement: gate_time = clamp(R+20s, 180s, 480s).")
    parser.add_argument("--duration", type=float, default=None,
                        help="Video total duration in seconds (ffprobe / metadata.seconds).")
    parser.add_argument("--revelation-time", type=float, default=None,
                        help="First-big-revelation video timestamp R in seconds (direct).")
    parser.add_argument("--revelation-slide", type=int, default=None,
                        help="Revelation slide number (resolved via --slide-map).")
    parser.add_argument("--slide-map", type=str, default=None,
                        help='JSON object mapping slide number -> audio_start seconds.')
    parser.add_argument("--json", action="store_true",
                        help="Emit the result as JSON.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run the deterministic self-test and exit.")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    slide_map = None
    if args.slide_map:
        try:
            slide_map = json.loads(args.slide_map)
        except json.JSONDecodeError as e:
            print(f"error: --slide-map not valid JSON: {e}", file=sys.stderr)
            return 2

    fg = compute_gate_time(
        duration_seconds=args.duration,
        revelation_time_seconds=args.revelation_time,
        revelation_slide=args.revelation_slide,
        slide_map=slide_map,
    )

    if args.json:
        print(json.dumps(fg, sort_keys=True))
    else:
        _print_result(fg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
