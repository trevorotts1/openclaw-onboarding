#!/usr/bin/env python3
"""U-GEN304: X05's uncalled save-only resume pair stays deleted, and a HELD
result still carries the retained charge plus the operator's resume inputs.

Pre-fix this test FAILS: ``save_only_plan`` and ``resume_save_only`` exist in
the module and no production recovery step calls either of them.

Run: python3 scripts/core/song_choices/test_song_choices_x05_recovery_deleted.py
"""
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from song_choices import song_choices as SC  # noqa: E402


def main():
    src = inspect.getsource(SC)
    for name in ("save_only_plan", "resume_save_only"):
        assert not hasattr(SC, name), (
            "%s is still defined: a resume nothing calls" % name)
        assert ("def %s(" % name) not in src, (
            "%s is still defined in the module source" % name)

    env = {"counts": {"generated": 1, "submitted": 1, "saved": 0, "delivered": 0},
           "reason_code": "KIE_SAVE_OUTPUT_EMPTY",
           "evidence": {"credits_consumed": 12.5, "actual_cost": 0.42}}
    hold = {"reason_code": "KIE_SAVE_OUTPUT_EMPTY", "detail": "zero-byte",
            "next_action": "", "task_id": "task-abc",
            "save_dir": "run/music", "info": None,
            "counts": env["counts"], "credits": 12.5, "actual_cost": 0.42}
    variant = {"id": "v1", "label": "A", "description": "d"}
    res = SC._held_result(1, variant, env, hold)

    assert res["status"] == "HELD", res["status"]
    assert res["resubmit"] is False, "a hold never invites a resubmit"
    assert res["hold"] is hold, "the retained task/charge block is the hold itself"
    assert res["hold"]["task_id"] == "task-abc"
    assert res["hold"]["credits"] == 12.5
    assert res["hold"]["actual_cost"] == 0.42
    assert res["recovery"] == {"command": "save", "task_id": "task-abc",
                               "save_dir": "run/music", "info": None}, res["recovery"]
    print("OK: save_only_plan/resume_save_only are gone; HELD keeps hold + recovery")


if __name__ == "__main__":
    main()
