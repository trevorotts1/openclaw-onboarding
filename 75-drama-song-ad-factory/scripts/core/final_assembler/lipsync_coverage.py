#!/usr/bin/env python3
"""lipsync_coverage.py: enforce the lip-sync coverage rule in code (manual
02 Part E E6, Critical).

The documented rule (price-menu section 3, choice-card-spec 3.6) used to
live only in docs; the 2026-10-08 failed ad cut ~6 s of lip-sync out of a
2-minute ad and nobody failed it. This module is the code that enforces the
rule at the FINAL edit QC gate (17.5, qc_gate check "final_edit"):

  * DOUBLED (owner order 2026-10-08): more pieces, not longer ones. A 60 s
    ad carries 6-8 short lip-sync clips (4-6 s each, 30-40 s in total),
    scaled linearly with the ad length; the numbers live in
    core/lipsync_clips.py. The floor here is the clip count (never fewer
    than 3) and the minimum seconds (50% of runtime, 30 s at 60 s);
  * the upper 40 s (at 60 s) is planning guidance, not a gate: only the two
    documented failure codes exist, and neither fires on "too much"
    lip-sync. The 6 s per-clip cap and the cost cap are enforced where the
    clips are planned and dispatched (lipsync_clips).

Wiring: evaluate() -> to_qc_record() emits a qc-schema 1.0.0 record with
check="final_edit" for core/qc_gate.py, exactly like sibling checkers do
(17.6: the gate still requires an independent reviewer on top of this
record; this module is the threshold checker, not the review). Thresholds
come from core/acceptance-profile.json "lipsync" when present,
module constants otherwise (same fallback pattern as assembler/lane_size).

stdlib only, no network, no spend, fail-closed (bad input raises, never
passes silently).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOL_HERE = Path(__file__).resolve().parent
_CORE = _TOOL_HERE.parents[1]                          # .../core

if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
import spoken_share as _SS                 # the one band (H8)
import lipsync_clips as _LC                # the doubled-lip-sync numbers

TOOL_NAME = "lipsync_coverage"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"                               # final_assembler receipt
QC_SCHEMA_VERSION = "1.0.0"                            # core/qc_gate.py
CHECK = "final_edit"                                   # 17.5 final edit QC

# The two documented reason codes (and no others).
LINES_TOO_FEW = "LIPSYNC_LINES_TOO_FEW"
COVERAGE_SHORT = "LIPSYNC_COVERAGE_SHORT"

# Rule constants; acceptance-profile.json "lipsync" overrides when present.
MIN_LINES = _LC.MIN_CLIPS_FLOOR           # always at least 3 lines (floor)
SCALE_SHARE = _LC.TOTAL_PER_REF_S[0] / _LC.REF_LENGTH_S   # 0.5: 30 s per 60 s

EXIT = {"ok": 0, "error": 1, "rejected": 5}

_PROFILE_KEY = "lipsync"


class LipsyncCoverageError(Exception):
    """Structural problem (bad input, bad profile). Fail closed, never pass."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _numbers(profile=None):
    """Thresholds from the shipped acceptance profile, constants otherwise."""
    d = {"min_lines": MIN_LINES, "scale_share": SCALE_SHARE}
    if isinstance(profile, dict):
        block = profile.get(_PROFILE_KEY)
        if block is not None:
            if not isinstance(block, dict):
                raise LipsyncCoverageError(
                    "BAD_PROFILE", "%s must be an object" % _PROFILE_KEY)
            try:
                d["min_lines"] = int(block["min_lines"])
                d["scale_share"] = float(block["scale_share"])
            except (KeyError, TypeError, ValueError) as exc:
                raise LipsyncCoverageError(
                    "BAD_PROFILE", "%s thresholds unreadable: %s"
                    % (_PROFILE_KEY, exc)) from exc
    return d


def required_lines(ad_length_s, profile=None):
    """Minimum lip-sync clips for one ad length: 6 per 60 s, scaled, never
    below the profile floor (3)."""
    return max(_numbers(profile)["min_lines"],
               _LC.budget(float(ad_length_s))["min_clips"])


def load_profile(path=None):
    """Shipped acceptance-profile.json (or a caller-supplied dict)."""
    if isinstance(path, dict):
        return path
    with open(path or str(_CORE / "acceptance-profile.json"),
              encoding="utf-8") as f:
        return json.load(f)


def required_total_s(ad_length_s, profile=None):
    """The lip-sync duration floor for one ad length (seconds): 50% of
    runtime, so 30 s in a 60 s ad. Linear, monotone in ad length."""
    return _numbers(profile)["scale_share"] * float(ad_length_s)


def check_lipsync_coverage(ad_length_s, lipsync_lines_count, lipsync_total_s,
                           profile=None):
    """E6 rule check. Returns pass or the reason (never raises on values).

    ad_length_s         — final ad length in seconds
    lipsync_lines_count — number of distinct lip-sync LINES in the ad
    lipsync_total_s     — total lip-sync footage in seconds

    Returns {"pass": True} on a pass, else
    {"pass": False, "reason_code": <code or codes joined by "+">,
     "detail": <plain-English>, "evidence": {...numbers...}}.
    The only reason codes are LIPSYNC_LINES_TOO_FEW and
    LIPSYNC_COVERAGE_SHORT. Nonsensical input (negative line count or
    total, non-positive ad length, non-numeric values) raises
    LipsyncCoverageError — fail closed, never a silent pass.
    """
    for name, val in (("ad_length_s", ad_length_s),
                      ("lipsync_lines_count", lipsync_lines_count),
                      ("lipsync_total_s", lipsync_total_s)):
        if isinstance(val, bool) or not isinstance(val, (int, float)) \
                or val != val:                    # bool/ non-number/ NaN
            raise LipsyncCoverageError("BAD_INPUT", "%s must be a number"
                                       % name)
    if ad_length_s <= 0:
        raise LipsyncCoverageError("BAD_INPUT",
                                   "ad_length_s must be positive")
    if lipsync_lines_count < 0 or lipsync_total_s < 0:
        raise LipsyncCoverageError("BAD_INPUT",
                                   "line count and total must be >= 0")

    floor_s = required_total_s(ad_length_s, profile)
    codes = []
    need_lines = required_lines(ad_length_s, profile)
    if lipsync_lines_count < need_lines:
        codes.append(LINES_TOO_FEW)
    # H8: the seconds goal is judged by Trevor's band, as percent of the lip-sync
    # goal short of the goal: <=5% accept, 5-10% accept WITH A FLAG, >10% redo.
    band = _SS.judge_seconds(lipsync_total_s, floor_s, floor_s, only="short")
    flags = []
    if band["verdict"] == _SS.VERDICT_FAIL:
        codes.append(COVERAGE_SHORT)
    elif band["verdict"] == _SS.VERDICT_FLAG:
        flags.append("lip-sync %.2f s is %.1f%% short of the "
                     "%.2f s goal: accepted with a flag"
                     % (lipsync_total_s, band["gap_pts"], floor_s))
    if not codes:
        return {"pass": True, "flags": flags,
                "evidence": {"ad_length_s": ad_length_s,
                             "lipsync_lines_count": lipsync_lines_count,
                             "lipsync_total_s": lipsync_total_s,
                             "required_lines_min": need_lines,
                             "required_total_s": floor_s}}
    return {"pass": False,
            "reason_code": "+".join(sorted(codes)),
            "detail": ("lip-sync coverage %s: %d line(s) of %.2f s in a "
                       "%.1f s ad; the rule needs at least %d line(s) and "
                       "%.2f s of lip-sync"
                       % ("short" if COVERAGE_SHORT in codes else "thin",
                          lipsync_lines_count, lipsync_total_s,
                          ad_length_s, need_lines, floor_s)),
            "evidence": {"ad_length_s": ad_length_s,
                         "lipsync_lines_count": lipsync_lines_count,
                         "lipsync_total_s": lipsync_total_s,
                         "required_lines_min": need_lines,
                         "required_total_s": floor_s}}


def to_qc_record(result, run_id, stage, reviewer, check_id=None,
                 checker_version=None):
    """qc-schema 1.0.0 record (check=final_edit) for core/qc_gate.py.

    reviewer must carry identity/session/authority and differ from the
    maker of the master (17.6; qc_gate enforces independence — this
    record alone never advances a stage).
    """
    if not isinstance(result, dict) or "pass" not in result:
        raise LipsyncCoverageError("BAD_INPUT",
                                   "result must be a check result")
    if not all(isinstance(_norm(x), str) for x in (run_id, stage)) \
            or not _norm(run_id) or not _norm(stage):
        raise LipsyncCoverageError("BAD_INPUT", "run_id/stage required")
    if not isinstance(reviewer, dict):
        raise LipsyncCoverageError("BAD_INPUT", "reviewer must be an object")
    rev = {}
    for key in ("identity", "session", "authority"):
        v = _norm(reviewer.get(key))
        if v is None:
            raise LipsyncCoverageError("BAD_INPUT",
                                       "reviewer.%s is required" % key)
        rev[key] = v
    passed = bool(result["pass"])
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "check_id": check_id or "lipsync-coverage",
        "run_id": run_id,
        "stage": stage,
        "check": CHECK,
        "verdict": "PASS" if passed else "FAIL",
        "evidence": {
            "summary": ("lip-sync coverage %s: %d line(s), %.2f s of "
                        "%.1f s ad%s"
                        % ("pass" if passed else "FAIL",
                           result["evidence"]["lipsync_lines_count"],
                           result["evidence"]["lipsync_total_s"],
                           result["evidence"]["ad_length_s"],
                           "" if passed else
                           " [%s]" % result["reason_code"])),
            "refs": ["manual 02 Part E E6",
                     "references/choice-card-spec.md section 3.6"],
        },
        "reason_code": "LIPSYNC_COVERAGE_OK" if passed
                       else result["reason_code"],
        "checker_version": checker_version or TOOL_VERSION,
        "reviewer": rev,
    }


def _norm(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lipsync_coverage",
        description="E6 lip-sync coverage check (final edit QC)")
    p.add_argument("--ad-length", type=float, required=True,
                   help="final ad length in seconds")
    p.add_argument("--lines", type=int, required=True,
                   help="distinct lip-sync lines in the ad")
    p.add_argument("--total", type=float, required=True,
                   help="total lip-sync seconds in the ad")
    p.add_argument("--run", default="untitled")
    p.add_argument("--stage", default="final")
    args = p.parse_args(argv)
    try:
        res = check_lipsync_coverage(args.ad_length, args.lines, args.total)
    except LipsyncCoverageError as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                          "command": "check", "outcome": "error",
                          "reason_code": exc.code, "state_version": 0}))
        return EXIT["error"]
    rec = to_qc_record(res, args.run, args.stage,
                       {"identity": TOOL_NAME, "session": "cli",
                        "authority": "manual 02 Part E E6"})
    print(json.dumps({"schema_version": SCHEMA_VERSION,
                      "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                      "command": "check", "outcome":
                          "ok" if res["pass"] else "rejected",
                      "reason_code": "LIPSYNC_COVERAGE_OK"
                          if res["pass"] else res["reason_code"],
                      "next_action": "advance" if res["pass"] else
                          "rebuild the ad with more lip-sync footage",
                      "detail": res.get("detail"),
                      "qc_record": rec, "state_version": 0}, indent=2))
    return EXIT["ok"] if res["pass"] else EXIT["rejected"]


if __name__ == "__main__":
    sys.exit(main())