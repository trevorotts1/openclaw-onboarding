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


def scenario(core, muts=frozenset()):
    # selftest runs every mutation in this one process; drop the product
    # modules first so no patch from an earlier mutation leaks into the next.
    for name in [n for n in list(sys.modules)
                 if n.split(".")[0] in ("sung_hook", "master_length",
                                        "final_assembler", "suno_recipe",
                                        "intake_preflight")]:
        del sys.modules[name]
    SH = H.load_pkg(core, "sung_hook.sung_hook")
    HP = H.load_pkg(core, "sung_hook.hook_placement")
    ML = H.load_pkg(core, "master_length.master_length")
    ASM = H.load_pkg(core, "final_assembler.assembler")
    MP = H.load_pkg(core, "final_assembler.master_provenance")
    DR = H.load_pkg(core, "suno_recipe.duration_registry")
    P = H.load_pkg(core, "intake_preflight.preflight")

    # Deliberate PRODUCT defects: each one damages a rule the row measures, so
    # the assertion has to read the product to notice. None of them edits a
    # fixture the assertion compares against.
    if "sheet_count_rule_always_accepts" in muts:
        SH.check_sheet_count = lambda *a, **kw: []
    if "buildup_rule_always_accepts" in muts:
        HP.check_buildup = lambda *a, **kw: []
    if "labels_trusted_as_measured" in muts:
        real_measure = SH.measure
        SH.measure = lambda hook, words, segs, target: real_measure(
            hook, words, [dict(s, source="measured") for s in (segs or [])],
            target)
    if "overshoot_becomes_failure" in muts:
        real_judge = ML.judge_duration

        def failing_overshoot(actual_s, target_s, short="band",
                              label_target_s=None):
            out = real_judge(actual_s, target_s, short=short,
                             label_target_s=label_target_s)
            if (isinstance(actual_s, (int, float))
                    and isinstance(target_s, (int, float))
                    and actual_s > target_s):
                return dict(out, verdict="FAIL", outcome="rejected")
            return out

        ML.judge_duration = failing_overshoot
    if "plan_keeps_full_length" in muts:
        ML.master_max_s = lambda chosen_length_s: chosen_length_s
    if "unmeasured_master_accepted" in muts:
        real_check = ML.check_master

        def accepts_unmeasured(chosen_length_s, measured_s):
            if measured_s is None:
                return {"outcome": "ok", "reason_code": "MASTER_LENGTH_OK",
                        "master_max_s": chosen_length_s, "measured_s": None,
                        "detail": "accepted"}
            return real_check(chosen_length_s, measured_s)

        ML.check_master = accepts_unmeasured
    if "provenance_ignores_bytes" in muts:
        real_prov = MP.check_master_provenance

        def ignores_bytes(*a, **kw):
            out = dict(real_prov(*a, **kw))
            out["pass"] = True
            out["reason_code"] = "OK"
            return out

        MP.check_master_provenance = ignores_bytes
    if "profile_not_offered" in muts:
        DR.profiles_for = lambda seconds: ()
    if "probe_returns_zero" in muts:
        ASM.probe_duration = lambda path: 0.0
    if "sheet_check_rejects_valid" in muts:
        SH.check_sheet_count = (
            lambda sheet, hook, delivered: ["defect: the valid sheet is refused"])
    if "sheet_check_accepts_hook_first" in muts:
        SH.check_sheet_count = lambda sheet, hook, delivered: []
    if "buildup_rule_never_rejects" in muts:
        HP.check_buildup = lambda sheet, style, delivered: []
    if "hook_positions_zero" in muts:
        HP.hook_positions = lambda sheet, style: [0.0]
    if "measure_counts_labels" in muts:
        real_measure = SH.measure
        SH.measure = lambda hook, words, segments, target: real_measure(
            hook, words,
            [dict(s, source="measured") for s in (segments or [])], target)
    if "measure_wrong_count" in muts:
        real_measure = SH.measure

        def wrong_count(hook, words, segments, target):
            out = dict(real_measure(hook, words, segments, target))
            out["measured"] = int(out.get("measured") or 0) + 1
            return out

        SH.measure = wrong_count
    if "one_short_fails" in muts:
        SH.judge = lambda hook, target, times, reason=None: {
            "verdict": "FAIL", "action": "regenerate"}
    if "overshoot_warning_dropped" in muts:
        real_judge = ML.judge_duration

        def silent(*a, **kw):
            out = dict(real_judge(*a, **kw))
            out["warning"] = None
            return out

        ML.judge_duration = silent
    if "band_too_short_passes" in muts:
        real_judge = ML.judge_duration

        def loose(*a, **kw):
            out = dict(real_judge(*a, **kw))
            if (a[2] if len(a) > 2 else kw.get("short")) == "band":
                out["verdict"] = "PASS"
            return out

        ML.judge_duration = loose
    if "plan_not_two_early" in muts:
        real_plan = ML.plan

        def no_margin(chosen):
            out = dict(real_plan(chosen))
            out["master_max_s"] = chosen
            out["song_target_s"] = chosen
            out["shot_plan_end_s"] = chosen
            return out

        ML.plan = no_margin
    if "master_short_rejected" in muts:
        real_check = ML.check_master

        def strict(chosen, measured):
            out = dict(real_check(chosen, measured))
            if measured is not None and measured <= chosen - 2:
                out["outcome"] = "rejected"
                out["reason_code"] = "MASTER_LENGTH_SHORT"
            return out

        ML.check_master = strict
    if "overshoot_master_silent" in muts:
        ML.check_master = lambda chosen, measured: {
            "outcome": "ok", "reason_code": "MASTER_LENGTH_OK"}
    if "unmeasured_accepted" in muts:
        real_check = ML.check_master

        def accepts_none(chosen, measured):
            if measured is None:
                return {"outcome": "ok", "reason_code": "MASTER_LENGTH_OK"}
            return dict(real_check(chosen, measured))

        ML.check_master = accepts_none
    if "probe_lies" in muts:
        ASM.probe_duration = lambda path, ffprobe=None: 60.0
    if "probe_appends_bytes" in muts:
        real_probe = ASM.probe_duration

        def appending_probe(path, *a, **kw):
            with open(path, "ab") as fh:
                fh.write(b"\x00" * 16)
            return real_probe(path, *a, **kw)

        ASM.probe_duration = appending_probe
    if "provenance_rejects" in muts:
        MP.check_master_provenance = lambda take_dir, take: {
            "pass": False, "reason_code": "MASTER_HASH_MISMATCH"}
    if "provenance_accepts" in muts:
        MP.check_master_provenance = lambda take_dir, take: {
            "pass": True, "reason_code": "OK"}
    if "registry_wrong_seconds" in muts:
        real_row = DR.profile_row

        def wrong_row(name):
            out = dict(real_row(name))
            out["seconds"] = 90
            return out

        DR.profile_row = wrong_row
    if "preflight_drops_120" in muts:
        P.DEFAULT_PROFILES = tuple(
            n for n in P.DEFAULT_PROFILES if not n.endswith("-120s"))

    c = H.Checks(ROW, TITLE)
    print("A07 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

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

    return c

# --------------------------------------------------------------------------
# selftest — deliberate product defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "sheet_count_rule_always_accepts": [
        "a07:hook-first-sheet-rejected",
    ],
    "buildup_rule_always_accepts": [
        "a07:buildup-rule-rejects-hook-first",
    ],
    "labels_trusted_as_measured": [
        "a07:label-only-segments-never-count",
    ],
    "overshoot_becomes_failure": [
        "a07:62s-passes-with-named-warning",
        "a07:severe-overshoot-also-never-stops",
        "a07:master-overshoot-named-on-receipt",
        "a07:measured-62s-passes-as-named-warning",
        "a07:over-profile-master-named-never-silent",
    ],
    "plan_keeps_full_length": [
        "a07:master-planned-two-seconds-early",
        "a07:two-minute-plan-ends-two-seconds-early",
    ],
    "unmeasured_master_accepted": [
        "a07:unmeasured-duration-never-passes",
    ],
    "provenance_ignores_bytes": [
        "a07:altered-take-refused-not-delivered",
    ],
    "profile_not_offered": [
        "a07:two-minute-profile-offered-to-preflight",
    ],
    "probe_returns_zero": [
        "a07:62s-take-measured-by-ffprobe",
        "a07:measured-62s-passes-as-named-warning",
        "a07:two-minute-master-within-profile",
    ],
    "sheet_check_rejects_valid": [
        "a07:opening-sheet-places-hook-after-build-up",
    ],
    "sheet_check_accepts_hook_first": [
        "a07:hook-first-sheet-rejected",
    ],
    "buildup_rule_never_rejects": [
        "a07:buildup-rule-rejects-hook-first",
    ],
    "hook_positions_zero": [
        "a07:first-hook-at-or-after-plan-floor",
    ],
    "measure_counts_labels": [
        "a07:label-only-segments-never-count",
    ],
    "measure_wrong_count": [
        "a07:measured-hook-count-and-times",
    ],
    "one_short_fails": [
        "a07:one-short-is-flag-not-fail",
    ],
    "overshoot_warning_dropped": [
        "a07:62s-passes-with-named-warning",
        "a07:severe-overshoot-also-never-stops",
        "a07:measured-62s-passes-as-named-warning",
    ],
    "band_too_short_passes": [
        "a07:short-side-keeps-5-10-band",
    ],
    "plan_not_two_early": [
        "a07:master-planned-two-seconds-early",
        "a07:two-minute-plan-ends-two-seconds-early",
    ],
    "master_short_rejected": [
        "a07:master-at-limit-accepted",
        "a07:two-minute-master-within-profile",
    ],
    "overshoot_master_silent": [
        "a07:master-overshoot-named-on-receipt",
        "a07:over-profile-master-named-never-silent",
    ],
    "unmeasured_accepted": [
        "a07:unmeasured-duration-never-passes",
    ],
    "probe_lies": [
        "a07:62s-take-measured-by-ffprobe",
    ],
    "probe_appends_bytes": [
        "a07:62s-take-bytes-unchanged",
    ],
    "provenance_rejects": [
        "a07:62s-take-preserved-untouched",
    ],
    "provenance_accepts": [
        "a07:altered-take-refused-not-delivered",
    ],
    "registry_wrong_seconds": [
        "a07:two-minute-profile-id-resolves-to-120s",
        "a07:receipt-records-duration-profile",
    ],
    "preflight_drops_120": [
        "a07:two-minute-profile-offered-to-preflight",
        "a07:receipt-records-duration-profile",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all %d defects" % len(MUTATIONS)
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest_mode = bool(argv) and argv[0] == "selftest"
    args = H.add_args(
        description="a07 selftest" if selftest_mode else __doc__
    ).parse_args(argv[1:] if selftest_mode else argv)
    core = H.resolve_core(args)
    if not H.have_tools("ffmpeg", "ffprobe"):
        print("TOOLING: ffmpeg/ffprobe are required to measure a real 62 s take "
              "and a real two-minute master")
        return 2
    if selftest_mode:
        return selftest(core)
    return scenario(core).finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
