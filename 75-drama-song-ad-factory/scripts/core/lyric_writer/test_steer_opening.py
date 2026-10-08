#!/usr/bin/env python3
"""H6: the lyric-sheet builder steers toward first real singing at 15%.
Run: python3 core/lyric_writer/test_steer_opening.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import lyric_writer as LW  # noqa: E402

def test_steer_opening():
    # 60 s sheet that talks for 30 s before any singing: pull the hook 21 s earlier.
    r = LW.steer_opening([{"delivery": "spoken", "seconds": 30.0},
                          {"delivery": "sung", "seconds": 30.0}], 60)
    assert r["action"] == "shorten_opener" and r["move_by_s"] == -21.0, r
    assert r["check"]["verdict"] == "FAIL" and r["plan_target_s"] == 9.0, r
    # Short opener then a sung hook at 8 s: keep.
    r = LW.steer_opening([{"delivery": "spoken", "seconds": 8.0},
                          {"delivery": "sung", "seconds": 52.0}], 60)
    assert r["action"] == "keep" and r["check"]["verdict"] == "PASS", r
    # Opens sung with no opener: lengthen it to the target.
    r = LW.steer_opening([{"delivery": "sung", "seconds": 60.0}], 60)
    assert r["action"] == "lengthen_opener" and r["move_by_s"] == 9.0, r
    # All spoken: add a sung hook.
    assert LW.steer_opening([{"delivery": "spoken", "seconds": 60.0}])["action"] == "add_sung_hook"


if __name__ == "__main__":
    test_steer_opening()
    print("ok: steer_opening")
