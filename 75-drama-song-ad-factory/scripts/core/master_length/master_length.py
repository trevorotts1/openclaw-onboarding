#!/usr/bin/env python3
"""Part I unit I4: every master ends 2 seconds early.

Trevor (2026-10-08): a 60 second video that runs to 1:02 is unusable in
Stories, Reels or a Facebook ad, so the master we deliver for a chosen
length L is at most L-2 seconds (60->58, 30->28, 90->88, 120->118).

This is a HARD MAXIMUM, not a band. The song duration, the shot plan and the
end card are all planned to the same number, and QC fails any master longer
than it. A shorter master is fine here (the closeness band is a separate
rule). stdlib only, no spend.
"""
import json
import sys

END_EARLY_S = 2
_EPS = 1e-6  # float noise only; a real 1 frame overrun still fails


class MasterLengthError(ValueError):
    pass


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v \
        and v not in (float("inf"), float("-inf"))


def master_max_s(chosen_length_s):
    """The hard maximum master length for a chosen length."""
    if not _num(chosen_length_s) or chosen_length_s <= END_EARLY_S:
        raise MasterLengthError(
            "chosen length must be a number of seconds above %d, got %r"
            % (END_EARLY_S, chosen_length_s))
    return chosen_length_s - END_EARLY_S


def plan(chosen_length_s):
    """One number for the song, the shot plan and the end card to aim at."""
    m = master_max_s(chosen_length_s)
    return {"chosen_length_s": chosen_length_s, "master_max_s": m,
            "song_target_s": m, "shot_plan_end_s": m, "end_card_end_s": m}


def check_master(chosen_length_s, measured_s):
    """PASS when the measured master is at or under L-2, else FAIL."""
    m = master_max_s(chosen_length_s)
    if not _num(measured_s) or measured_s <= 0:
        return {"outcome": "rejected", "reason_code": "MASTER_LENGTH_UNMEASURED",
                "master_max_s": m, "measured_s": measured_s,
                "detail": "master length could not be measured"}
    if measured_s > m + _EPS:
        return {"outcome": "rejected", "reason_code": "MASTER_TOO_LONG",
                "master_max_s": m, "measured_s": measured_s,
                "detail": "master is %.2fs, the limit for a %gs video is %gs"
                          % (measured_s, chosen_length_s, m)}
    return {"outcome": "ok", "reason_code": "MASTER_LENGTH_OK",
            "master_max_s": m, "measured_s": measured_s,
            "detail": "master is %.2fs, within the %gs limit" % (measured_s, m)}


def to_qc_record(chosen_length_s, measured_s, reviewer, run_id,
                 stage="final_edit", check_id="i4-master-length"):
    """qc-schema 1.0.0 record (check=final_edit) for core/qc_gate.py."""
    r = check_master(chosen_length_s, measured_s)
    return {"schema_version": "1.0.0", "check_id": check_id, "run_id": run_id,
            "stage": stage, "check": "final_edit",
            "verdict": "PASS" if r["outcome"] == "ok" else "FAIL",
            "evidence": {"summary": r["detail"], "refs": []},
            "reason_code": r["reason_code"], "checker_version": "1.0.0",
            "reviewer": reviewer}


if __name__ == "__main__":  # python3 master_length.py <chosen_s> <measured_s>
    print(json.dumps(check_master(float(sys.argv[1]), float(sys.argv[2]))))
