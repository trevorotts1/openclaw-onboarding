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

  SC-16 (real take, not a number)
    * a real 62 s encoded take is measured by the tree's own ffprobe read, its
      bytes are unchanged by that measurement, and the provenance check binds
      it to its receipt; altered bytes are refused MASTER_HASH_MISMATCH.

  SC-17 (two-minute profile)
    * the profile id resolves to 120 s in the one registry and is offered to
      preflight; the plan aims 118 s; a real 118 s master measures at or under
      the profile and an over-profile master is named on the receipt.
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
    ASM = H.load_pkg(core, "final_assembler.assembler")
    MP = H.load_pkg(core, "final_assembler.master_provenance")
    DR = H.load_pkg(core, "suno_recipe.duration_registry")
    P = H.load_pkg(core, "intake_preflight.preflight")
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

    # ---- SC-16: a real 62 s take, measured and preserved ------------------
    # The duration above is a number passed in. This block measures a real
    # encoded take with the tree's own ffprobe read and then proves the take
    # cannot be silently swapped: the provenance check binds the file's bytes to
    # its assembler receipt, and altered bytes are refused by name.
    if not H.have_tools("ffmpeg", "ffprobe"):
        print("TOOLING: ffmpeg/ffprobe are required to measure a real 62 s take "
              "and a real two-minute master")
        return 2
    with H.Scratch() as media_dir:
        take_dir = Path(media_dir) / "take"
        take = H.aac_take(take_dir / "take-62s.mp4", 62)
        sha_before = H.sha256_file(take)
        measured = ASM.probe_duration(take)
        c.check("a07:62s-take-measured-by-ffprobe",
                measured == 62.0,
                "ffprobe duration=%.3fs for a 62 s take" % measured)

        H.write_json(take + ".receipt.json",
                     {"outcome": "ok", "produced_by": MP.producer_stamp(),
                      "master_sha256": H.sha256_file(take)})
        kept = MP.check_master_provenance(str(take_dir), take)
        c.check("a07:62s-take-preserved-untouched",
                kept.get("pass") is True and kept.get("reason_code") == "OK",
                "reason=%s module=%s"
                % (kept.get("reason_code"),
                   (kept.get("evidence") or {}).get("module")))
        c.check("a07:62s-take-bytes-unchanged",
                H.sha256_file(take) == sha_before,
                "sha256 %s before, %s after the measurement"
                % (sha_before[:12], H.sha256_file(take)[:12]))

        with open(take, "ab") as fh:
            fh.write(b"\x00" * 4096)
        altered = MP.check_master_provenance(str(take_dir), take)
        c.check("a07:altered-take-refused-not-delivered",
                altered.get("pass") is False
                and altered.get("reason_code") == MP.MASTER_HASH_MISMATCH,
                "reason=%s after the take was altered"
                % (altered.get("reason_code"),))

        policy = ML.judge_duration(measured, 60, short="free")
        c.check("a07:measured-62s-passes-as-named-warning",
                policy.get("verdict") == "PASS"
                and (policy.get("warning") or {}).get("code")
                == ML.DURATION_OVERSHOOT,
                "verdict=%s warning=%s detail=%s"
                % (policy.get("verdict"),
                   (policy.get("warning") or {}).get("code"),
                   policy.get("detail")))

        # ---- SC-17: the two-minute profile --------------------------------
        row = DR.profile_row("drama-9x16-120s")
        c.check("a07:two-minute-profile-id-resolves-to-120s",
                row.get("name") == "drama-9x16-120s"
                and row.get("seconds") == 120
                and row.get("label") == "2 minutes"
                and row.get("shape") == "9x16",
                "profile=%s seconds=%s label=%s"
                % (row.get("name"), row.get("seconds"), row.get("label")))
        c.check("a07:two-minute-profile-offered-to-preflight",
                DR.profiles_for(120) == ("drama-9x16-120s", "drama-16x9-120s")
                and set(DR.profiles_for(120)) <= set(P.DEFAULT_PROFILES),
                "profiles_for_120=%s preflight_allows=%s"
                % (DR.profiles_for(120),
                   sorted(set(DR.profiles_for(120)) & set(P.DEFAULT_PROFILES))))

        plan120 = ML.plan(120)
        c.check("a07:two-minute-plan-ends-two-seconds-early",
                plan120.get("chosen_length_s") == 120
                and plan120.get("master_max_s") == 118
                and plan120.get("song_target_s") == 118
                and plan120.get("shot_plan_end_s") == 118
                and plan120.get("end_card_end_s") == 118,
                "plan=%s" % (plan120,))

        master = H.aac_take(take_dir / "master-120-profile.mp4", 118)
        m118 = ASM.probe_duration(master)
        c.check("a07:two-minute-master-within-profile",
                m118 <= 120.0
                and ML.check_master(120, m118).get("reason_code")
                == "MASTER_LENGTH_OK",
                "measured=%.3fs of the 120 s profile, reason=%s"
                % (m118, ML.check_master(120, m118).get("reason_code")))
        over_profile = ML.check_master(120, 124)
        c.check("a07:over-profile-master-named-never-silent",
                over_profile.get("reason_code") == "MASTER_LENGTH_OVERSHOOT"
                and (over_profile.get("warning") or {}).get("code")
                == ML.DURATION_OVERSHOOT,
                "measured=124s of the 120 s profile, reason=%s"
                % (over_profile.get("reason_code"),))

    return c.finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
