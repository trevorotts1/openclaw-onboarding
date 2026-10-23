#!/usr/bin/env python3
"""a07_opening_sync_duration.py — acceptance row A07 (weight 8).

Condition (tests/w10-canary/receipt-mapping.json, row A07, verbatim):
    "opening sync + measurement + 62s + duration proofs (S75-W10-U1)"

Four nouns, four groups of assertions, all against the tree under test:

  opening sync
    * the sheet builder places the hook AFTER the build-up (a verse first),
      repeats it the length-derived number of times, and ends on a hook;
    * a hook-first sheet is REJECTED by the same checks (the rule discriminates,
      it is not a check that only ever passes);
    * the planned first hook lands at or after the plan's earliest hook second
      (opening sync is measured in seconds, not eyeballed).

  measurement
    * a hook counts only from detector-measured segments: label-only segments
      FAIL with action=regenerate (never counted from labels);
    * measured segments yield the measured count and its times, and the band
      accepts at target / flags one short.

  62s
    * a 62 s take against a 60 s target PASSES with the named warning
      QC_DURATION_OVERSHOOT (a flag, never a stop), and the severe band also
      passes with QC_DURATION_OVERSHOOT_SEVERE.

  duration
    * the master is planned to chosen-2 s (60 -> 58) and check_master accepts
      it; the video overshoot surfaces as MASTER_LENGTH_OVERSHOOT;
    * an unmeasured duration NEVER passes;
    * the short side keeps the 5/10 band.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "a07"
TITLE = "opening sync + measurement + 62s + duration"
STYLE = "rnb-flow"
DELIVERED = 58.0          # a 60 s video's delivered master length
HOOK = ["built it from nothing"]


def main(argv=None):
    args = H.add_args(description=__doc__).parse_args(argv)
    core = H.resolve_core(args)
    SH = H.load_pkg(core, "sung_hook.sung_hook")
    HP = H.load_pkg(core, "sung_hook.hook_placement")
    ML = H.load_pkg(core, "master_length.master_length")
    c = H.Checks(ROW, TITLE)
    print("A07 %s — tree %s" % (TITLE, core))

    # ---- opening sync ----------------------------------------------------
    verses = [{"tag": "Verse 1", "delivery": "sung",
               "lines": ["I built this from nothing"]}]
    sheet = SH.build_lyric_sheet(verses, HOOK, DELIVERED)
    c.check("a07:opening-sheet-places-hook-after-build-up",
            SH.check_sheet_count(sheet, HOOK, DELIVERED) == []
            and HP.check_buildup(sheet, STYLE, DELIVERED) == [],
            "sections=%s" % [s["tag"] for s in sheet])

    hook_first = [
        {"tag": "Hook", "delivery": "sung", "lines": list(HOOK)},
        {"tag": "Verse 1", "delivery": "sung", "lines": ["I built this"]},
    ]
    errs = SH.check_sheet_count(hook_first, HOOK, DELIVERED)
    c.check("a07:hook-first-sheet-rejected",
            bool(errs) and any("never the opener" in e for e in errs),
            "; ".join(errs)[:200])
    c.check("a07:buildup-rule-rejects-hook-first",
            HP.check_buildup(hook_first, STYLE, DELIVERED) != [],
            HP.check_buildup(hook_first, STYLE, DELIVERED))

    positions = HP.hook_positions(sheet, STYLE)
    first_s = round(positions[0] * DELIVERED, 1) if positions else None
    floor_s = HP.min_first_hook_s(STYLE, DELIVERED)
    c.check("a07:first-hook-at-or-after-plan-floor",
            bool(positions) and first_s is not None and first_s >= floor_s,
            "first_hook=%ss floor=%ss" % (first_s, floor_s))

    # ---- measurement -----------------------------------------------------
    words, t = [], 1.0
    for _ in range(3):
        for w in HOOK[0].split():
            words.append({"word": w, "start": t, "end": t + 0.3})
            t += 0.4
    measured_segs = [{"delivery": "sung", "start": 0.0, "end": 60.0,
                      "source": "measured"}]
    label_segs = [{"delivery": "sung", "start": 0.0, "end": 60.0}]
    target = SH.hook_count(DELIVERED)

    label_res = SH.measure(HOOK[0], words, label_segs, target)
    c.check("a07:label-only-segments-never-count",
            label_res.get("verdict") == "FAIL"
            and label_res.get("action") == "regenerate"
            and label_res.get("measured") == 0,
            "verdict=%s measured=%s reason=%s"
            % (label_res.get("verdict"), label_res.get("measured"),
               str(label_res.get("reason"))[:120]))

    meas = SH.measure(HOOK[0], words, measured_segs, target)
    c.check("a07:measured-hook-count-and-times",
            meas.get("measured") == target == 3
            and len(meas.get("times_s") or []) == 3
            and meas.get("verdict") == "PASS"
            and meas.get("action") == "accept",
            "measured=%s/%s times=%s"
            % (meas.get("measured"), target, meas.get("times_s")))

    short = SH.judge(HOOK[0], target, [1.0, 2.0])
    c.check("a07:one-short-is-flag-not-fail",
            short.get("verdict") == "FLAG"
            and short.get("action") == "accept-with-flag",
            "verdict=%s action=%s" % (short.get("verdict"), short.get("action")))

    # ---- 62 s ------------------------------------------------------------
    over = ML.judge_duration(62, 60, short="free")
    c.check("a07:62s-passes-with-named-warning",
            over.get("verdict") == "PASS"
            and (over.get("warning") or {}).get("code") == ML.DURATION_OVERSHOOT
            and "62s of 60s" in str(over.get("detail")),
            "reason=%s detail=%s"
            % (over.get("reason_code"), over.get("detail")))

    severe = ML.judge_duration(75, 60, short="free")
    c.check("a07:severe-overshoot-also-never-stops",
            severe.get("verdict") == "PASS"
            and (severe.get("warning") or {}).get("code")
            == ML.DURATION_OVERSHOOT_SEVERE,
            "code=%s" % (severe.get("warning") or {}).get("code"))

    # ---- duration --------------------------------------------------------
    plan = ML.plan(60)
    c.check("a07:master-planned-two-seconds-early",
            plan.get("master_max_s") == 58
            and plan.get("song_target_s") == 58
            and plan.get("shot_plan_end_s") == 58,
            "plan=%s" % plan)

    at_max = ML.check_master(60, 58)
    c.check("a07:master-at-limit-accepted",
            at_max.get("outcome") == "ok"
            and at_max.get("reason_code") == "MASTER_LENGTH_OK",
            "reason=%s" % at_max.get("reason_code"))

    over_master = ML.check_master(60, 62)
    c.check("a07:master-overshoot-named-on-receipt",
            over_master.get("outcome") == "ok"
            and over_master.get("reason_code") == "MASTER_LENGTH_OVERSHOOT"
            and (over_master.get("warning") or {}).get("code")
            == ML.DURATION_OVERSHOOT,
            "reason=%s" % over_master.get("reason_code"))

    unmeasured = ML.check_master(60, None)
    c.check("a07:unmeasured-duration-never-passes",
            unmeasured.get("outcome") == "rejected"
            and unmeasured.get("reason_code") == "MASTER_LENGTH_UNMEASURED",
            "reason=%s" % unmeasured.get("reason_code"))

    band = ML.judge_duration(56, 58, short="band")
    too_short = ML.judge_duration(45, 58, short="band")
    c.check("a07:short-side-keeps-5-10-band",
            band.get("verdict") == "PASS"
            and too_short.get("verdict") == "FAIL",
            "56s=%s 45s=%s" % (band.get("verdict"), too_short.get("verdict")))

    # ---- duration profile on the receipt (SC-17) -------------------------
    # The run's receipt must name the duration profile it ran under, and that
    # name must resolve to the chosen length in the ONE registry -- a bare echo
    # of the request would pass the first half only.
    PF = H.load_pkg(core, "intake_preflight.preflight")
    DR = H.load_pkg(core, "suno_recipe.duration_registry")
    prof = "drama-9x16-120s"
    res = PF.check({"profile": prof, "mode": "diagnostic",
                    "capabilities": {"generating": False}})
    got = ((res or {}).get("checks") or {}).get("duration_profile")
    c.check("a07:receipt-records-duration-profile",
            isinstance(got, str) and got == prof
            and DR.profile_row(got)["seconds"] == 120,
            "receipt duration_profile=%r" % (got,))

    return c.finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
