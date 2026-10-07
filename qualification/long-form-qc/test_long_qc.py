#!/usr/bin/env python3
"""W4-01-U2 pack self-check. stdlib only, run: python3 test_long_qc.py

Two things are proven here:
  1. the aggregation and discovery rules cannot launder a defect into PASS
  2. the pack discriminates: run against the known-good 30s short-run
     control it must FAIL the 60-90s duration band, PASS receipts, and
     report UNAVAILABLE (never PASS) for the shot and variant arms whose
     inputs genuinely do not exist there.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import run_long_qc as q  # noqa: E402


def t_agg_cannot_launder():
    assert q.agg([]) == q.UNAVAILABLE
    assert q.agg([q.PASS, q.PASS]) == q.PASS
    assert q.agg([q.PASS, q.UNAVAILABLE]) == q.UNAVAILABLE
    assert q.agg([q.PASS, q.REVIEW]) == q.REVIEW
    assert q.agg([q.REVIEW, q.UNAVAILABLE]) == q.REVIEW
    assert q.agg([q.PASS, q.UNAVAILABLE, q.FAIL]) == q.FAIL
    assert q.agg([q.REVIEW, q.FAIL]) == q.FAIL
    assert q.agg(["NOPE"]) == q.UNAVAILABLE


def t_discovery_roles():
    disc = q.discover(BROOT / "qualification" / "short-run")
    assert disc["exists"], "short-run control package must exist"
    assert disc["campaign"] is not None, "campaign role must resolve"
    assert disc["manifest"] is not None, "manifest role must resolve"
    assert disc["shots"] is None, "short-run has no 14.2 shot plan"
    assert disc["timing"] is None, "short-run has no 12.4 timing map"
    lines, words, source, note = q.observation(disc)
    assert lines, "provider prompt observation must resolve on the control"
    assert source.startswith("provider-prompt:"), source
    assert words is None
    assert note


def t_band_is_real():
    lo, hi = q.DURATION_BAND_S
    assert lo == 60.0 and hi == 90.0
    assert not (lo <= 30.024 <= hi), "30s control must fall outside the band"
    assert lo <= 75.0 <= hi


def t_master_selection_prefers_assembled():
    clip = {"rel": "shots/video-shot-01.mp4", "duration_s": 21.0, "bytes": 9}
    final = {"rel": "final/final-9x16.mp4", "duration_s": 63.0, "bytes": 99}
    m, rule, seen, asm = q.pick_video_master([clip, final])
    assert m["rel"] == final["rel"] and asm, (m, asm)
    assert "assembled output" in rule, rule
    assert len(seen) == 2

    # only clips exist: the clip is reported, but never as an assembled one
    m, rule, seen, asm = q.pick_video_master([clip])
    assert m["rel"] == clip["rel"] and not asm, (m, asm)
    assert "no assembled output" in rule, rule

    # a bigger clip must not beat a smaller assembled deliverable
    big_clip = dict(clip, duration_s=80.0, bytes=10 ** 9)
    m, _, _, asm = q.pick_video_master([big_clip, final])
    assert m["rel"] == final["rel"] and asm, (m, asm)

    m, _, _, _ = q.pick_video_master([])
    assert m is None


def t_control_run_discriminates():
    with tempfile.TemporaryDirectory(prefix="w4-01-u2-selftest-") as tmp:
        r = subprocess.run(
            [sys.executable, str(HERE / "run_long_qc.py"),
             "--pkg", str(BROOT / "qualification" / "short-run"),
             "--out", tmp, "--run", "w3-04-short-run",
             "--label", "selftest-control"],
            capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        man = json.loads((Path(tmp) / "MANIFEST.json").read_text())
        arms = man["arms"]
        assert arms["01-package-inventory"] == "FAIL", arms
        assert arms["02-shot-continuity"] == "UNAVAILABLE", arms
        assert arms["03-timing-guard"] == "REVIEW", arms
        assert arms["04-music-qc"] == "FAIL", arms
        assert arms["05-delivery-variants"] == "UNAVAILABLE", arms
        # receipts: PASS, or FAIL whose only cause is OS metadata in the
        # reconciler's hardcoded short-run artifacts walk (asserted below)
        assert arms["06-receipts-reconciliation"] in ("PASS", "FAIL"), arms
        assert man["verdict"] != "PASS", "control must never read as PASS"

        inv = json.loads((Path(tmp) / "01-package-inventory.json").read_text())
        band = [c for c in inv["checks"] if c["id"] == "DURATION_BAND"]
        assert band and band[0]["status"] == "FAIL", band

        music = json.loads((Path(tmp) / "04-music-qc.json").read_text())
        diff = music["raw"]["lyric_diff"]
        assert diff["coverage"] == 1.0 and not diff["critical_missing"] \
            and not diff["adlib_words"], diff
        dur = [a for a in music["audit"] if a["id"] == "DURATION"]
        assert dur and dur[0]["status"] == "FAIL", dur

        rec = json.loads((Path(tmp) / "06-receipts-reconciliation.json").read_text())
        assert rec["totals"]["ceiling"] == 5000
        assert rec["totals"]["remaining_budget"] == 4992
        assert rec["independent_verdict"] == "PASS", rec.get("independent")
        assert rec["reconciler_verdict"] == rec["verdict"]
        if rec["verdict"] != "PASS":
            # the shared reconciler's R3 walk is hardcoded to
            # qualification/short-run/artifacts; the only way it may fail
            # here is an OS metadata file in that tree, never a receipt.
            ex = rec.get("explain") or {}
            assert ex.get("unclaimed_is_os_metadata_only"), ex
            assert ex.get("unclaimed_files"), ex

        tim = json.loads((Path(tmp) / "03-timing-guard.json").read_text())
        assert tim["raw"]["verdict"] == "REVIEW", tim["raw"]
        assert tim["raw"]["evidence"]["coverage"]["overall"] == 1.0


def t_missing_package_blocks():
    with tempfile.TemporaryDirectory(prefix="w4-01-u2-missing-") as tmp:
        pkg = Path(tmp) / "no-such-package"
        out = Path(tmp) / "out"
        r = subprocess.run(
            [sys.executable, str(HERE / "run_long_qc.py"),
             "--pkg", str(pkg), "--out", str(out),
             "--label", "selftest-missing"],
            capture_output=True, text=True, timeout=120)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        man = json.loads((out / "MANIFEST.json").read_text())
        assert man["status"] == "BLOCKED"
        assert man["verdict"] in ("FAIL", "UNAVAILABLE")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_")]
    failed = []
    for t in tests:
        try:
            t()
            print("PASS  %s" % t.__name__)
        except AssertionError as e:
            failed.append((t.__name__, e))
            print("FAIL  %s: %s" % (t.__name__, e))
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, e))
            print("ERROR %s: %s: %s" % (t.__name__, type(e).__name__, e))
    print("---")
    print("%d/%d passed" % (len(tests) - len(failed), len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
