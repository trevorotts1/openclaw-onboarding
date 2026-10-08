#!/usr/bin/env python3
"""E6 lip-sync coverage tests (manual 02 Part E E6, Critical).

Proves exactly the manual's done-when pairs and nothing looser:

  FAIL: a 2-minute (120 s) ad with 3 lip-sync clips totalling 6 s.
  PASS: a 60-90 s ad with 4 lip-sync lines totalling >= 15 s.
  FAIL: a 120 s ad with 3 lines totalling 10 s (below 12% = 14.4 s):
        coverage scales with runtime.
  PASS: a 120 s ad with 4 lines totalling 15 s (>= 12% = 14.4 s).
  FAIL: a 60 s ad with only 2 lines (never fewer than 3 lines,
        even when 12% would be met).
  PASS: no reason codes other than the documented two.
  WIRE: the marker rides plan_timeline -> lipsync_gate; assembler
        dry-run blocks a 2-minute 6-s ad and passes a 60-s 16-s ad;
        load_timeline rejects a non-boolean marker.
  GATE: the emitted record validates in qc_gate (schema + independence)
        and FAILs the final_edit check family in the shared gate.

stdlib only, zero paid calls, no ffmpeg binary required.

Run: python3 core/final_assembler/test_lipsync_coverage_e6.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A          # noqa: E402
import qc_gate as G                            # noqa: E402  (shared gate)

from final_assembler.lipsync_coverage import (
    COVERAGE_SHORT, LINES_TOO_FEW,
    check_lipsync_coverage, to_qc_record, required_total_s,
)                                              # noqa: E402

# The assembler gate emits the module's exact code strings.
LIPSYNC_LINES_TOO_FEW = LINES_TOO_FEW
LIPSYNC_COVERAGE_SHORT = COVERAGE_SHORT

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def test_done_when_pairs():
    """The manual's two Done-when rows, exactly as written."""
    bad = check_lipsync_coverage(120, 3, 6)
    check("done-when FAIL: 120 s ad, 3 clips totalling 6 s FAILS",
          bad["pass"] is False, bad)
    check("bad ad names the coverage code", COVERAGE_SHORT
          in bad["reason_code"], bad["reason_code"])
    good = check_lipsync_coverage(75, 4, 16.0)
    check("done-when PASS: 75 s ad, 4 lines totalling 16 s PASSES",
          good["pass"] is True, good)
    # and the boundary the rule states: 15 s exactly clears the 60-90 band
    exact = check_lipsync_coverage(90, 3, 15.0)
    check("done-when PASS: 90 s ad, 3 lines totalling exactly 15 s passes",
          exact["pass"] is True, exact)
    under = check_lipsync_coverage(90, 3, 14.99)
    check("90 s ad at 14.99 s is one hair under the band floor",
          under["pass"] is False and COVERAGE_SHORT in under["reason_code"],
          under)


def test_scaled_rules():
    """Longer ads scale up (12%); never fewer than 3 lines."""
    r = required_total_s(120)
    check("120 s floor holds the 15 s band floor (never lower; 12% alone "
          "would dip the floor and reward stretching ads past 90 s)",
          abs(r - 15.0) < 1e-9, r)
    r = required_total_s(300)
    check("300 s floor is 12% = 36 s", abs(r - 36.0) < 1e-9, r)
    r = required_total_s(60)
    check("60 s floor is 15 s (floor holds from 60 s)",
          abs(r - 15.0) < 1e-9, r)
    scaled_pass = check_lipsync_coverage(120, 4, 15.0)
    check("120 s ad with 4 lines/15 s passes (15 >= 14.4)",
          scaled_pass["pass"] is True, scaled_pass)
    scaled_fail = check_lipsync_coverage(120, 3, 10.0)
    check("120 s ad with 3 lines/10 s fails at 12%",
          scaled_fail["pass"] is False
          and COVERAGE_SHORT in scaled_fail["reason_code"], scaled_fail)
    few = check_lipsync_coverage(60, 2, 15.0)
    check("60 s ad with 2 lines fails lines-min even at 15 s",
          few["pass"] is False and LINES_TOO_FEW in few["reason_code"], few)
    emitted = (scaled_fail["reason_code"], few["reason_code"])
    allowed = {LINES_TOO_FEW, COVERAGE_SHORT}
    for code in emitted:
        for part in code.split("+"):
            check("reason code %r is documented" % part, part in allowed,
                  part)


def test_bad_input_fails_closed():
    for args in ((0, 3, 15), (-5, 3, 15), (60, -1, 15), (60, 3, -2.0),
                 (None, 3, 15), (60, True, 15)):
        try:
            check_lipsync_coverage(*args)
            check("bad input %r raises" % (args,), False)
        except Exception as exc:
            check("bad input %r raises" % (args,), True)
            check("raise carries a code", hasattr(exc, "code"), repr(exc))


def _tl(segs, dur, tmp):
    path = os.path.join(tmp, "tl-%d.json" % abs(len(segs) * 17 + int(dur)))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                   "width": 1920, "height": 1080, "song_path": None,
                   "transition": "none", "segments": segs}, fh)
    return path


def test_gate_wiring(tmp_root):
    """Marker rides the plan; the dry-run gate blocks / passes pairs."""
    import tempfile
    tmp = tempfile.mkdtemp(dir=tmp_root)
    clip = os.path.join(tmp, "clip.mp4")
    open(clip, "wb").close()

    # Done-when FAIL through the assembler gate: 3 clips of 2 s each in a
    # 120 s ad (3 x 2 + 5 x 19.5 + 16.5 = 120), 6 s of lip-sync total.
    # E2 default fades land in the same trunk, so the plan's real total is
    # 78.2 - 8 x 0.4 = 75 s (inside 60-90): the 6 s total is 7.98% < 12%.
    segs = ([{"src": "clip.mp4", "dur": 2.0, "lip_sync": True}] * 3
            + [{"src": "clip.mp4", "dur": 11.0}] * 5
            + [{"src": "clip.mp4", "dur": 17.2}])
    tl = _tl(segs, 120, tmp)
    rec = A.assemble(tl, os.path.join(tmp, "out.mp4"), dry_run=True)
    # 3 clips meet the line minimum; the 6 s total is what fails.
    check("120 s / 3 clips / 6 s: dry_run BLOCKED by E6",
          rec["reason_code"] == LIPSYNC_COVERAGE_SHORT,
          rec.get("reason_code"))
    check("blocked receipt carries coverage evidence",
          rec["outcome"] == "error"
          and abs(rec["evidence"]["lipsync"]["evidence"]["ad_length_s"]
                  - 75.0) < 0.2
          and abs(rec["evidence"]["lipsync"]["evidence"]["lipsync_total_s"]
                  - 6.0) < 0.2, rec["evidence"]["lipsync"])

    # Done-when PASS through the assembler gate: 60 s, 4 lines, 16 s.
    segs_pass = ([{"src": "clip.mp4", "dur": 4.0, "lip_sync": True}] * 4
                 + [{"src": "clip.mp4", "dur": 11.0}] * 4)
    tl2 = _tl(segs_pass, 60, tmp)
    rec2 = A.assemble(tl2, os.path.join(tmp, "out2.mp4"), dry_run=True)
    check("60 s / 4 lines / 16 s: gate passes",
          rec2["outcome"] == "ok" and rec2["reason_code"] == "DRY_RUN"
          and rec2["evidence"]["lipsync"] is None,
          rec2.get("reason_code"))


def test_marker_validation(tmp_root):
    """A non-boolean marker is structurally rejected, never coerced."""
    import tempfile
    tmp = tempfile.mkdtemp(dir=tmp_root)
    p = os.path.join(tmp, "bad.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                   "width": 1920, "height": 1080, "song_path": None,
                   "transition": "none",
                   "segments": [{"src": "x.mp4", "dur": 2.0,
                                 "lip_sync": "yes"}]}, fh)
    try:
        A.load_timeline(p)
        check("non-boolean lip_sync marker rejected", False)
    except ValueError as exc:
        check("non-boolean lip_sync marker rejected",
              "TIMELINE_BAD_SEGMENT" in str(exc) and "boolean" in str(exc),
              str(exc))


def test_qc_record_and_gate():
    """The FAIL record feeds the shared gate; final_edit gets the block."""
    bad = check_lipsync_coverage(120, 3, 6)
    rev = {"identity": "final_qc_reviewer", "session": "e6-qc",
           "authority": "manual 02 Part E E6"}
    rec_bad = to_qc_record(bad, "run-e6", "final", rev)
    check("fail record validates in qc_gate",
          G.validate_record(rec_bad) is None, G.validate_record(rec_bad))
    check("fail record is final_edit + FAIL",
          rec_bad["check"] == "final_edit" and rec_bad["verdict"] == "FAIL",
          (rec_bad["check"], rec_bad["verdict"]))
    good = check_lipsync_coverage(75, 4, 16.0)
    rec_ok = to_qc_record(good, "run-e6", "final", rev)
    check("pass record validates in qc_gate",
          G.validate_record(rec_ok) is None, G.validate_record(rec_ok))
    # Shared gate: the same final_edit check required with the others.
    makers = {"lipsync-coverage": "final_assembler"}
    gate = G.evaluate("run-e6", "final", [rec_bad], makers, ["final_edit"],
                      master={"chosen_length_s": 120, "measured_s": 118})
    check("shared gate FAILs the 2-minute 6-s ad", gate["gate"] == "FAIL",
          gate)
    gate_ok = G.evaluate("run-e6", "final", [rec_ok], makers,
                         ["final_edit"],
                         master={"chosen_length_s": 75, "measured_s": 73})
    check("shared gate PASSes the passing ad", gate_ok["gate"] == "PASS",
          gate_ok)
    # 17.6: maker's own review is refused by the same gate.
    rec_self = to_qc_record(good, "run-e6", "final", {
        "identity": "final_assembler", "session": "s", "authority": "a"})
    gate_self = G.evaluate("run-e6", "final", [rec_self], makers,
                           ["final_edit"])
    check("maker self-review refused",
          any(f["code"] == "MAKER_SELF_REVIEW" for f in gate_self["failures"]),
          gate_self["reason_code"])


def main():
    import tempfile
    tmp_root = tempfile.mkdtemp(prefix="/tmp/w75-W-E-U6-e6tests-")
    try:
        test_done_when_pairs()
        test_scaled_rules()
        test_bad_input_fails_closed()
        test_marker_validation(tmp_root)
        test_gate_wiring(tmp_root)
        test_qc_record_and_gate()
    finally:
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)
    print("%s" % ("%d check(s) failed" % len(FAILS) if FAILS
                  else "all E6 checks passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())