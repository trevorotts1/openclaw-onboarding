#!/usr/bin/env python3
"""Part I unit I4: every master ends 2 seconds early.

Trevor (2026-10-08): a 60 second video that runs to 1:02 is unusable in
Stories, Reels or a Facebook ad, so the master we deliver for a chosen
length L is at most L-2 seconds (60->58, 30->28, 90->88, 120->118).

This is a HARD MAXIMUM, not a band. The song duration, the shot plan and the
end card are all planned to the same number. A shorter master is fine here
(the closeness band is a separate rule).

QC DURATION OVERSHOOT = FLAG, NOT STOP (order 2026-10-21). An overshoot no
longer forces a redo: up to OVERSHOOT_ALLOWANCE_S (10 s) past the maximum
passes and records the named warning QC_DURATION_OVERSHOOT; past the
allowance it also passes, and records QC_DURATION_OVERSHOOT_SEVERE with the
exact seconds over so the warning is louder. Whether a long master is redone
belongs to the client, never to this check. An undershoot is unchanged: the
master is "free" on the short side here (the song gate keeps its own band).
stdlib only, no spend.
"""
import json
import sys

END_EARLY_S = 2
_EPS = 1e-6  # float noise only; a real 1 frame overrun still fails

#: The one overshoot allowance in seconds (order 2026-10-21).
OVERSHOOT_ALLOWANCE_S = 10.0
#: Named warning codes for the receipt (loud_failure.warn at the emitting edge).
DURATION_OVERSHOOT = "QC_DURATION_OVERSHOOT"
DURATION_OVERSHOOT_SEVERE = "QC_DURATION_OVERSHOOT_SEVERE"


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


def judge_duration(actual_s, target_s, short="band", label_target_s=None):
    """The ONE QC duration rule (order 2026-10-21). Never stops on an overshoot.

    actual_s <= target_s is the clean side: ``short="band"`` keeps Trevor's
    5/10 band on the shortfall (<=5 points PASS, 5-10 FLAG as today, past 10
    FAIL as today); ``short="free"`` leaves the short side alone (the video
    master's rule today).

    An overshoot of at most OVERSHOOT_ALLOWANCE_S passes and carries the named
    warning QC_DURATION_OVERSHOOT; a bigger overshoot ALSO passes (no stop) and
    carries QC_DURATION_OVERSHOOT_SEVERE naming the exact seconds over. The
    redo decision belongs to the client, never to this check.

    Returns {outcome, verdict, reason_code, detail, warning, overshoot_s,
    gap_pts, target_s, actual_s}. ``label_target_s`` is what the plain-English
    detail names as the target (the video master reports the client's chosen
    length while the arithmetic runs against the end-early maximum).
    """
    if not _num(actual_s) or actual_s <= 0:
        return {"outcome": "rejected", "verdict": "FAIL",
                "reason_code": "DURATION_UNMEASURED",
                "detail": "duration could not be measured",
                "warning": None, "overshoot_s": None, "gap_pts": None,
                "target_s": target_s, "actual_s": actual_s}
    if not _num(target_s) or target_s <= 0:
        raise MasterLengthError("target must be a positive number, got %r"
                                % (target_s,))
    label = target_s if not _num(label_target_s) or label_target_s <= 0 \
        else label_target_s
    over = actual_s - target_s
    if over > _EPS:
        within = over <= OVERSHOOT_ALLOWANCE_S + _EPS
        code = DURATION_OVERSHOOT if within else DURATION_OVERSHOOT_SEVERE
        note = ("within the %g-second allowance" % OVERSHOOT_ALLOWANCE_S if within
                else "%gs over the %g-second allowance"
                % (round(over - OVERSHOOT_ALLOWANCE_S, 3),
                   OVERSHOOT_ALLOWANCE_S))
        detail = "%gs of %gs — %s" % (actual_s, label, note)
        return {"outcome": "ok", "verdict": "PASS",
                "reason_code": ("DURATION_OVERSHOOT_WITHIN"
                                if within else "DURATION_OVERSHOOT_OVER"),
                "detail": detail,
                "warning": {"code": code, "detail": detail},
                "overshoot_s": round(over, 3), "gap_pts": None,
                "target_s": target_s, "actual_s": actual_s}
    gap = round((target_s - actual_s) / float(target_s) * 100.0, 6)
    if short == "free":
        return {"outcome": "ok", "verdict": "PASS",
                "reason_code": "DURATION_WITHIN",
                "detail": "%gs of %gs — at or under the target"
                          % (actual_s, label),
                "warning": None, "overshoot_s": 0.0, "gap_pts": gap,
                "target_s": target_s, "actual_s": actual_s}
    verdict = "PASS" if gap <= 5 else ("FLAG" if gap <= 10 else "FAIL")
    return {"outcome": "ok" if verdict != "FAIL" else "rejected",
            "verdict": verdict,
            "reason_code": {"PASS": "DURATION_WITHIN",
                            "FLAG": "DURATION_SHORT_FLAG",
                            "FAIL": "DURATION_TOO_SHORT"}[verdict],
            "detail": "%gs of %gs — %.1f points short"
                      % (actual_s, label, gap),
            "warning": None, "overshoot_s": 0.0, "gap_pts": gap,
            "target_s": target_s, "actual_s": actual_s}


def check_master(chosen_length_s, measured_s):
    """At or under L-2 is clean; an overshoot is a FLAG (named warning, never a
    stop); an unmeasured master never passes."""
    m = master_max_s(chosen_length_s)
    if not _num(measured_s) or measured_s <= 0:
        return {"outcome": "rejected", "reason_code": "MASTER_LENGTH_UNMEASURED",
                "master_max_s": m, "measured_s": measured_s,
                "detail": "master length could not be measured"}
    v = judge_duration(measured_s, m, short="free",
                       label_target_s=chosen_length_s)
    if v["verdict"] != "PASS":
        return {"outcome": "rejected", "reason_code": "MASTER_TOO_SHORT",
                "master_max_s": m, "measured_s": measured_s,
                "detail": v["detail"]}
    if v["warning"]:
        return {"outcome": "ok", "reason_code": "MASTER_LENGTH_OVERSHOOT",
                "master_max_s": m, "measured_s": measured_s,
                "overshoot_s": v["overshoot_s"], "warning": v["warning"],
                "detail": v["detail"]}
    return {"outcome": "ok", "reason_code": "MASTER_LENGTH_OK",
            "master_max_s": m, "measured_s": measured_s,
            "detail": "master is %.2fs, within the %gs limit" % (measured_s, m)}


def to_qc_record(chosen_length_s, measured_s, reviewer, run_id,
                 stage="final_edit", check_id="i4-master-length"):
    """qc-schema 1.0.0 record (check=final_edit) for core/qc_gate.py.

    An overshoot is a PASS carrying its named warning: the stage advances and
    the receipt says why (the client decides whether to redo).
    """
    r = check_master(chosen_length_s, measured_s)
    rec = {"schema_version": "1.0.0", "check_id": check_id, "run_id": run_id,
           "stage": stage, "check": "final_edit",
           "verdict": "PASS" if r["outcome"] == "ok" else "FAIL",
           "evidence": {"summary": r["detail"], "refs": []},
           "reason_code": r["reason_code"], "checker_version": "1.0.0",
           "reviewer": reviewer}
    if r.get("warning"):
        rec["warnings"] = [dict(r["warning"])]
    return rec


if __name__ == "__main__":  # python3 master_length.py <chosen_s> <measured_s>
    print(json.dumps(check_master(float(sys.argv[1]), float(sys.argv[2]))))
