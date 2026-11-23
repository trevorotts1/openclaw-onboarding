#!/usr/bin/env python3
"""G-FACE-02 proof: a 212 by 377 lip-source still is refused at intake.

`python3 -B scripts/core/intake_preflight/test_source_stills.py`
Plain asserts, no framework; exits 0 only when every proof holds.
"""
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import source_stills as S  # noqa: E402


def _png(width, height):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    from logo_check import PNG_SIG
    return (PNG_SIG + struct.pack(">I4s", 13, b"IHDR") + ihdr
            + b"\x00\x00\x00\x00" + struct.pack(">I4s", 0, b"IEND")
            + b"\x00\x00\x00\x00")


def main():
    with tempfile.TemporaryDirectory() as td:
        small = os.path.join(td, "t02.png")
        with open(small, "wb") as fh:
            fh.write(_png(212, 377))
        got = S.check_lip_source_still(small)
        assert not got["ok"] and got["code"] == "LIPSYNC_STILL_TOO_SMALL", got
        assert got["width"] == 212 and got["height"] == 377, got
        assert "re-render" in got["next_action"], got
        print("ok 1 - 212x377 lip-source still refused before any paid job")

        big = os.path.join(td, "ok.png")
        with open(big, "wb") as fh:
            fh.write(_png(720, 1280))
        assert S.check_lip_source_still(big)["ok"], S.check_lip_source_still(big)
        print("ok 2 - 720x1280 lip-source still accepted")

        # a storyboard check names every offender at once
        board = {"shots": [
            {"id": "s1", "kind": "lip", "lip_source_still": os.path.basename(small)},
            {"id": "s2", "kind": "story", "still": os.path.basename(small)},
        ]}
        res = S.check_storyboard_stills(board, run_dir=td)
        assert not res["ok"] and [f["shot_id"] for f in res["failures"]] == ["s1"], res
        print("ok 3 - storyboard check refuses only the lip shot, names it")
    print("3 proofs held")


if __name__ == "__main__":
    main()
