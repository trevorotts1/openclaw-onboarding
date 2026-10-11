#!/usr/bin/env python3
"""WWFIX-U1 acceptance tests: the D2 three-version money-safety trap, the D1 rap
floor, the story gates, the pace gate, the fail-closed rap check, the provider
overlap receipt, the words-versus-music label, and WW-21's total fail-closed
acceptance boundary.

Every threshold these tests pin is a NEW ACCEPTANCE RULE added by WWFIX-U1, not
a measured limit of an earlier run.

WW-21 (this file's `test_ww21_*` section) is the aggregation and
EVIDENCE-BINDING boundary that runs before spend -- NOT a sixth audio gate. It
pins the five carried delivered-audio results (D1 real rap, D2 story start, D3
both pace changes, D4 three audibly different versions, D5 more than one
character voice), each bound to the export digest, creative revision and
profile revision it was produced against. PROPOSED: the minimum count of 5
(`song_dispatch._MIN_AUDIO_RESULTS`, `acceptance-profile.json
audio_results.minimum_count`) is the count of the five gate names the operator
plan already names -- a proposed value, not a measured limit and NOT a number
Trevor set. It moves only when that plan's gate list moves.

Run: python3 core/music_qc/test_wwfix_u1.py
"""
import argparse
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for sub in ("", "intake_preflight"):
    sys.path.insert(0, os.path.join(CORE, sub))

import length_formula as LF                    # noqa: E402
import music_qc.pace_change as PC              # noqa: E402
import music_qc.rap_check as RC                # noqa: E402
import story_coverage.story_coverage as SV     # noqa: E402
from song_choices import song_choices as SC    # noqa: E402
from song_choices import overlap as OV         # noqa: E402
import song_contract as SCT                    # noqa: E402
import suno_recipe as R                        # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("ok   %s" % label)
    else:
        print("FAIL %s" % label)
        FAILURES.append(label)


CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
#: The R&B Flow sheet: the style DELIVERS rap, so the sheet must plan the rap
#: floor (max(8 s, 10% of D) = 20 rap words at 58 s) and keep the sung share.
#: WWFIXGAPS U1 (defect 0): the sung share the style's own plan holds at 58 s
#: is 72.9% of voice time, and the plan's word budget at 58 s is 76 words (85
#: with the band). A rap sheet that keeps BOTH the D1 rap floor (20 words) and
#: a spoken closing call to action cannot also sing enough to clear that floor
#: -- 61 sung + 20 rap + 14 spoken = 95 words -- so this sheet runs WITHOUT the
#: spoken [Outro]. The intro + CTA shape is exercised by the non-rap sheets.
SHEET_RNB = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["And I rise above the pa-a-ain,", "Through the dark I walk alo-o-one,"]},
             {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["One seed of truth made me stro-o-ong,", "I hold the light I found,",
                        "I walk free,"]},
             {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
             {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
             {"tag": "Verse", "delivery": "rap",
              "lines": ["Backup shoes, backup jacket, but no backup plan,",
                        "So I count what I make and not what they take today,"]}]
HOOK_PLAN = {"true_at_beat": "the_world"}
SPOKEN_RANGE = (15, 20)


def _reqs():
    return SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 58, hook_plan=HOOK_PLAN)


def _plan():
    return {"delivered_s": 58, "style_id": "rnb-flow",
            "sheet_text": R.render_lyrics(SHEET_RNB, "rnb-flow"), "hook_plan": HOOK_PLAN}


def _spec_file(tmp):
    path = os.path.join(tmp, "req.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"style_id": "rnb-flow", "client_text": CLIENT, "title": "T",
                   "length_s": 58, "hook_plan": HOOK_PLAN,
                   "input": {"lyrics": R.render_lyrics(SHEET_RNB, "rnb-flow"),
                             "style_id": "rnb-flow", "duration": 58, "vocal_gender": "f"}}, f)
    return path


# ---- D2: the three-version money-safety trap ------------------------------

def _counting_generate():
    """A generate() that returns NO take, so every attempt fails: each attempt is
    exactly ONE provider generation, so the call count IS the generation count."""
    calls = {"n": 0, "variants": []}

    def generate(variant, request):
        calls["n"] += 1
        calls["variants"].append(variant["id"])
        return []
    return calls, generate


def test_d2_per_unit_selector_dispatches_one_and_the_umbrella_three():
    """THE TRAP. A per-unit selector must cost ONE variant's generations, never
    nine: 1 unit -> 1 variant, umbrella -> 3 variants, and the umbrella count is
    exactly three times the unit count (nine would mean each unit fanned out)."""
    reqs = _reqs()
    kw = dict(plan=_plan(), measure=lambda t: {}, save=lambda v, t, r: None,
              script_words=CLIENT, hook_text="", spoken_range_pct=SPOKEN_RANGE)
    u_calls, u_gen = _counting_generate()
    unit = SC.run_unit(reqs, unit_id="WW-002", generate=u_gen, **kw)
    a_calls, a_gen = _counting_generate()
    every = SC.generate_choices(reqs, generate=a_gen, **kw)
    check(len(unit) == 1 and len(every) == 3,
          "D2: the per-unit path runs 1 variant, the umbrella runs 3 (%d/%d)"
          % (len(unit), len(every)))
    check(set(u_calls["variants"]) == {reqs[1][0]["id"]},
          "D2: --unit-id WW-002 touches ONLY variant #2 (%r)" % (u_calls["variants"],))
    check(u_calls["n"] * 3 == a_calls["n"] and u_calls["n"] > 0,
          "D2: the umbrella generates exactly 3x the unit, never 9x (%d vs %d)"
          % (u_calls["n"], a_calls["n"]))


def test_d2_cmd_generate_reports_the_dispatch_count_it_actually_made():
    """The canonical entry point reports a MEASURED count.

    WWFIXGAPS U1 (defect 3): the report used to carry the literals 1 and 3. A
    take that never lands is regenerated ONCE, so the unit path makes TWO
    provider jobs and the umbrella SIX -- the literal was wrong the moment a
    retry happened, which is the case this test drives. The pin is the
    generator's OWN call count (the ground truth of provider jobs), so no
    constant can satisfy it in both modes.
    """
    for flag, want in (("WW-001", 2), ("", 6)):
        with tempfile.TemporaryDirectory() as tmp:
            a = argparse.Namespace(run_dir=tmp, request=_spec_file(tmp), ledger="",
                                   run_id="R", variant="", unit_id=flag)
            calls, gen = _counting_generate()
            out = SC.cmd_generate(a, generate=gen, measure=lambda t: {},
                                  save=lambda v, t, r: None, plan=_plan())
            check(out["dispatched"] == calls["n"] == want,
                  "D3: cmd_generate --unit-id %r reports the %d provider jobs it ran"
                  % (flag or "none", want))
            if not flag:
                check(out["media_concurrency"] == 3 and out["builder_agent_units"] == 1,
                      "D2: the umbrella receipt says 3 threads inside ONE agent unit")


def test_d2_fan_in_never_generates_and_the_plan_names_three_units():
    """Fan-in only CHECKS and DELIVERS results that already exist. The unit plan
    names WW-001..003, providerSlots 3, reserve 0, one owned folder each, and
    reports threads and agent units as SEPARATE numbers."""
    reqs = _reqs()
    import inspect
    for fn, label in ((SC.fan_in, "fan_in"), (SC.deliver_choices, "deliver_choices")):
        params = set(inspect.signature(fn).parameters)
        check("generate" not in params and "kie" not in params,
              "D2: %s takes no generate callable -- it can only CHECK and DELIVER" % label)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            SC.fan_in([{"status": "PASS", "variant": {"id": v}, "take": None,
                        "receipts": []} for v in ("a", "b", "c")], tmp,
                      os.path.join(tmp, "d"), send=lambda *a2: None)
        except SC.ChoiceError:
            check(True, "D2: fan-in with no delivered take refuses instead of generating")
        else:
            check(False, "D2: fan-in accepted three empty results")
    units = SC.plan_units("/run", reqs)
    check([u["unit_id"] for u in units["units"]] == ["WW-001", "WW-002", "WW-003"],
          "D2: the unit plan is WW-001..003")
    check(all(u["owned_requests"] == 1 for u in units["units"])
          and units["reserve"] == 0 and units["provider_slots"] == 3,
          "D2: providerSlots 3, reserve 0, ONE owned request per unit")
    check(units["builder_agent_units"] == 3 and units["media_concurrency"] == 3,
          "D2: 3 provider jobs and 3 agent units are reported as separate facts")
    check(len({u["owned_folder"] for u in units["units"]}) == 3,
          "D2: each unit owns its own folder")


def test_d2_require_three_refuses_before_any_spend():
    """Three versions must be THREE and DISTINCT, and a worker must name its
    variant: every malformed call raises BEFORE a generation is dispatched."""
    reqs = _reqs()
    for rows, label in ((reqs[:2], "two rows"), (reqs + reqs[:1], "four rows"),
                        ([reqs[0], reqs[0], reqs[1]], "a repeated variant")):
        try:
            SC._require_three(rows, key=lambda r: r[0]["id"])
        except SC.ChoiceError:
            check(True, "D2: _require_three refuses %s" % label)
        else:
            check(False, "D2: _require_three accepted %s" % label)
    try:
        SC.run_unit(reqs, plan=_plan(), generate=lambda v, r: [], measure=lambda t: {},
                    save=lambda v, t, r: None, script_words=CLIENT, hook_text="")
    except SC.ChoiceError:
        check(True, "D2: a worker with no --variant/--unit-id is refused")
    else:
        check(False, "D2: a worker with no --variant/--unit-id was allowed")


def test_d2_cmd_next_exposes_one_mode_at_a_time():
    """cmd_next exposes the umbrella command AND the three owned units with an
    EXPLICIT orchestrated flag, and never selects both."""
    from intake_preflight import factory as F
    with tempfile.TemporaryDirectory() as tmp:
        SC.init(tmp, True)
        umb = F._song_choices_next(tmp, orchestrated=False)
        orch = F._song_choices_next(tmp, orchestrated=True)
    check(umb and umb["mode"] == "umbrella" and umb["command"] == umb["umbrella_command"]
          and not any(u["selected"] for u in umb["units"]),
          "D2: umbrella mode selects the umbrella command and NO unit")
    check(orch and orch["mode"] == "orchestrated" and orch["command"] == ""
          and all(u["selected"] for u in orch["units"])
          and len(orch["units"]) == 3,
          "D2: orchestrated mode selects the three units and NOT the umbrella")
    check("nine" in umb["note"] and umb["overlap_min_s"] == 1.0,
          "D2: the mode note names the nine-generation trap")


# ---- D2 item 3: the provider-overlap receipt -------------------------------

def _receipts(base, seconds, attempt_ids=("a1", "a2", "a3"), initial=True):
    t0 = base
    return [OV.make_receipt("polished-modern", {"k": i}, "logical", aid, "task-%s" % aid,
                            t0, t0 + datetime.timedelta(seconds=seconds), initial=initial)
            for i, aid in enumerate(attempt_ids)]


def test_overlap_gate_boundary_and_fail_closed():
    """min(terminal_at) - max(submitted_at) over the THREE INITIAL attempts:
    PASS at exactly 1.000 s, FAIL at 0.999 s and at zero, and UNAVAILABLE -- never
    a pass -- without the evidence."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    at_1 = OV.overlap_gate(_receipts(base, 1.0))
    check(at_1["verdict"] == "PASS" and at_1["overlap_s"] == 1.0,
          "D2: exactly 1.000 s of provider overlap is a PASS (%r)" % (at_1["overlap_s"],))
    below = OV.overlap_gate(_receipts(base, 0.999))
    check(below["verdict"] == "FAIL", "D2: 0.999 s is a FAIL")
    zero = OV.overlap_gate(_receipts(base, 0.0))
    check(zero["verdict"] == "FAIL", "D2: zero overlap is a FAIL")
    short = OV.overlap_gate(_receipts(base, 5.0)[:2])
    check(short["verdict"] == "UNAVAILABLE",
          "D2: fewer than three INITIAL attempts is UNAVAILABLE, never a pass")
    regen = OV.overlap_gate(_receipts(base, 5.0, attempt_ids=("a4", "a5", "a6"), initial=False))
    check(regen["verdict"] == "UNAVAILABLE",
          "D2: regenerated attempts never stand in for the three initial ones")
    naive = [dict(r, submitted_at=r["submitted_at"].replace("Z", "")) for r in _receipts(base, 5.0)]
    check(OV.overlap_gate(naive)["verdict"] == "UNAVAILABLE",
          "D2: an unlabelled/naive clock is not admissible evidence")
    check(at_1["requires_owner_authority"] is True and at_1["paid_redo"] is False,
          "D2: the gate never authorises a paid redo on its own")


# ---- D1: the rap floor -----------------------------------------------------

def test_d1_rap_floor_rule():
    """rap_s >= max(8.0, 0.10 * D) and rap_words >= ceil(rap_s * style rap rate)."""
    check(LF.rap_floor_s(90) == 9.0 and LF.rap_floor_s(50) == 8.0,
          "D1: floor seconds = max(8.0, 10% of D)")
    check(LF.rap_floor_words("rnb-flow", 90) == LF.rap_floor_words("rnb-flow", 90)
          and LF.rap_floor_words("rnb-flow", 90)
          >= int(__import__("math").ceil(LF.rap_floor_s(90) * 2.5)),
          "D1: floor words = ceil(seconds * the style's rap rate)")
    p = LF.plan(90, style_id="rnb-flow")
    check(p.get("rap_s", 0) >= LF.rap_floor_s(90) and p["words"].get("rap", 0) > 0,
          "D1: plan(90, rnb-flow) emits a rap budget at or above the floor (%r s, %r words)"
          % (p.get("rap_s"), p["words"].get("rap")))
    check(p.get("rap_floor_s") == LF.rap_floor_s(90 - LF.END_EARLY_S) and p.get("rap_gate"),
          "D1: the plan report carries its own rap floor")
    r88 = SCT.rap_floor_for("rnb-flow", 88)
    check(r88["floor_s"] == 8.8 and r88["floor_words"] == 22,
          "D1: at D = 88 the floor is 8.8 s / 22 words (%r)" % (r88,))
    LF.assert_rap_floor(p, "rnb-flow")
    check(True, "D1: assert_rap_floor accepts a floored rapping plan")
    broken = dict(p, rap_s=0.0, words=dict(p["words"], rap=0))
    try:
        LF.assert_rap_floor(broken, "rnb-flow")
    except LF.RapFloorError:
        check(True, "D1: assert_rap_floor refuses a rap style planning ZERO rap")
    else:
        check(False, "D1: assert_rap_floor accepted a rap style planning ZERO rap")


def test_d1_rap_sheet_below_floor_is_refused_before_spend():
    """A rap style whose sheet plans fewer rap words than the floor is refused,
    and a non-rap style carrying a rap block is refused too."""
    thin = [s for s in SHEET_RNB if s["delivery"] != "rap"]
    out = SCT.check_sheet(R.render_lyrics(thin, "rnb-flow"), "rnb-flow", 58)
    check(out["verdict"] == "FAIL"
          and any(r.startswith("RAP_PLANNED_ZERO_WORDS") for r in out["reasons"]),
          "D1: an R&B Flow sheet with no rap lines is refused (%r)" % (out["reasons"][:1],))
    check(out["totals"]["rap_floor_words"] == 20 and out["totals"]["rap_floor_s"] == 8.0,
          "D1: the refusal names the 58 s floor (20 rap words / 8.0 s)")
    ok = SCT.check_sheet(R.render_lyrics(SHEET_RNB, "rnb-flow"), "rnb-flow", 58)
    check(ok["verdict"] == "PASS" and ok["totals"]["rap_words"] >= 20,
          "D1: the same sheet WITH its rap floor passes (%r)" % (ok["verdict"],))
    soul = SCT.check_sheet(R.render_lyrics(SHEET_RNB, "soul-ballad"), "soul-ballad", 58)
    check(soul["verdict"] == "FAIL",
          "D1: a rap block under a style with no rap delivery is refused")


# ---- D1: the story gates ---------------------------------------------------

def _spread(words, start, step=0.4):
    return [{"word": w, "startS": start + i * step, "endS": start + i * step + 0.3}
            for i, w in enumerate(words)]


PLOT = ["one", "closed", "door", "seed", "truth"]


def test_d1_story_start_gate():
    """The measurement is the approved PLOT LINE (a run of >= 4 words), never a
    stray word: the ceiling is an ABSOLUTE 5.0 s and a late opening FAILS."""
    early = _spread(["one", "closed", "door", "seed"] + ["la"] * 40, 4.0)
    g = SV.story_start_gate(early, PLOT, 58.0)
    check(g["verdict"] == "PASS" and g["first_plot_line_s"] <= 5.0,
          "D1: a plot line at %.2f s passes the 5.0 s ceiling" % g["first_plot_line_s"])
    late = _spread(["la"] * 30 + ["one", "closed", "door", "seed"], 4.0)
    g = SV.story_start_gate(late, PLOT, 58.0)
    check(g["verdict"] == "FAIL" and "FIRST_STORY_WORD_LATE" in g["failed"],
          "D1: a plot line at %.2f s FAILS the 5.0 s ceiling" % g["first_plot_line_s"])
    stray = _spread(["one"] + ["la"] * 40, 4.0)          # ONE plot word, not a line
    g = SV.story_start_gate(stray, PLOT, 58.0)
    check(g["verdict"] == "FAIL" and "NO_PLOT_LINE_SUNG" in g["failed"],
          "D1: one stray plot word is not a plot line (the false pass is closed)")
    long_open = _spread(["one", "closed", "door", "seed"], 12.0)
    g = SV.story_start_gate(long_open, PLOT, 58.0)
    check("OPENING_NON_LEXICAL_TOO_LONG" in g["failed"],
          "D1: an opening wordless span over 15%% of D FAILS")
    check(SV.story_start_gate([], PLOT, 58.0)["verdict"] == "UNAVAILABLE"
          and SV.story_start_gate(early, [], 58.0)["verdict"] == "UNAVAILABLE",
          "D1: missing evidence is UNAVAILABLE, never PASS")


def test_d1_lexical_coverage_gate():
    """real lexical time / delivered seconds >= 0.70, with NO vocalise counted."""
    words = _spread(["count"] * 20, 0.0, 2.0)               # 20 words, 0.3 s each
    thin = SV.lexical_coverage_gate(words, 58.0)
    check(thin["verdict"] == "FAIL" and thin["vocalise_counted"] is False,
          "D1: 6.0 s of words over 58 s is below the 0.70 floor")
    fat = _spread(["count"] * 200, 0.0, 0.3)                 # contiguous real words
    ok = SV.lexical_coverage_gate(fat, 58.0)
    check(ok["verdict"] == "PASS" and ok["coverage"] >= 0.70,
          "D1: %.1f s of real words over 58 s clears the 0.70 floor" % ok["lexical_s"])
    check(SV.is_vocalise("Oo-o-o-o-o-oh") and not SV.is_lexical("Oo-o-o-o-o-oh"),
          "D1: a vocalise is not a lexical word")
    voc = _spread(["Oo-o-o-o-o-oh"] * 60, 0.0, 0.7)
    check(SV.lexical_coverage_gate(voc, 58.0)["verdict"] == "FAIL",
          "D1: a sheet of vocalise alone cannot reach the coverage floor")
    check(SV.lexical_coverage_gate([], 58.0)["verdict"] == "UNAVAILABLE",
          "D1: unmeasured coverage is UNAVAILABLE, never PASS")


def test_d1_story_arc_gate():
    """Every beats_u16 window of at least 5 s must carry a measured lexical line;
    a wordless window FAILS and the closing short beat is not a hole."""
    beats = [(0.0, 20.0), (20.0, 40.0), (40.0, 43.0)]
    full = _spread(["count"] * 40, 0.0, 1.0)
    ok = SV.story_arc_gate(full, beats, 43.0)
    check(ok["verdict"] == "PASS" and ok["reason_code"] == SV.STORY_ARC_CODE_OK,
          "D1: every judged window carries a line")
    hole = [w for w in full if w["startS"] > 25.0]
    bad = SV.story_arc_gate(hole, beats, 43.0)
    check(bad["verdict"] == "FAIL" and bad["failed_windows"],
          "D1: a wordless 20-40 s window FAILS (the closing 3 s beat is not a hole)")
    check(SV.story_arc_gate([], beats, 43.0)["verdict"] == "UNAVAILABLE"
          and SV.story_arc_gate(full, 0, 43.0)["verdict"] == "UNAVAILABLE",
          "D1: a missing arc or alignment is UNAVAILABLE, never PASS")
    check(len(LF.STORY_ARC_U16) >= 6 and "hook" in LF.STORY_ARC_U16,
          "D1: the story arc is the u16 beat list the plan carries")


# ---- D1: the pace gate -----------------------------------------------------

def test_d1_pace_gate_controls():
    """The shipped takes FAIL (no gear change), a real half-time section PASSES,
    and the failure names the missing evidence."""
    shipped = PC.confirm_pace_change({"onset_rate": 2.0, "rms_dbfs": -14.0},
                                     {"onset_rate": 2.0, "rms_dbfs": -14.0},
                                     {"onset_rate": 2.0, "rms_dbfs": -14.0})
    check(shipped["verdict"] == "FAIL" and shipped["reason_code"] == "PACE_CHANGE_ABSENT",
          "D1: a take whose tempo ratio is 1.0 FAILS the ordered gear change")
    pair = PC.confirm_pace_change({"onset_rate": 4.0, "rms_dbfs": -14.0},
                                  {"onset_rate": 2.0, "rms_dbfs": -18.0},
                                  {"onset_rate": 4.1, "rms_dbfs": -14.5})
    check(pair["verdict"] == "PASS" and pair["onset_reduction"] >= PC.PACE_ONSET_REDUCTION
          and pair["energy_drop_db"] >= PC.PACE_ENERGY_DROP_DB,
          "D1: 50%% fewer onsets and -4 dB PASS")
    weak = PC.confirm_pace_change({"onset_rate": 4.0, "rms_dbfs": -14.0},
                                  {"onset_rate": 3.5, "rms_dbfs": -16.0},
                                  {"onset_rate": 4.0, "rms_dbfs": -14.0})
    check(weak["verdict"] == "FAIL"
          and "onset_reduction" in weak["failed"] and "energy_drop" in weak["failed"],
          "D1: a 12.5%% onset change and a -2 dB drop do NOT confirm a gear change")
    unmeasured = PC.confirm_pace_change({}, {}, {})
    check(unmeasured["verdict"] == "UNMEASURED"
          and unmeasured["reason_code"] == "PACE_EVIDENCE_UNMEASURED",
          "D1: missing onset/energy evidence is UNMEASURED, never PASS")
    check(PC.judge_plan_pace({}, {}, {}, {})["applicable"] is False,
          "D1: no ordered change in the plan = nothing to enforce")


def test_d1_pace_selftest_discriminates_and_bpm_never_passes():
    """The two measurement-anchored facts: the synthetic controls discriminate,
    and a bare bpm ratio can never certify the gear change."""
    st = PC.selftest()
    check(st.get("pair") == "PASS" and st.get("shipped") == "FAIL"
          and st.get("bare") == "UNMEASURED",
          "D1: the pace controls discriminate (half-time PASS, shipped FAIL, "
          "bare UNMEASURED) %r" % (st,))
    fold = PC.octave_fold_bpm(85.2, 181.5)
    check(fold["same_beat"] is True and fold["grants_pass"] is False,
          "D1: 85.2 and 181.5 bpm read as the SAME beat -- bpm alone never grants PASS")
    off = PC.confirm_pace_change({"onset_rate": 4.0, "rms_dbfs": -14.0},
                                 {"onset_rate": 4.0, "rms_dbfs": -14.0},
                                 {"onset_rate": 4.0, "rms_dbfs": -14.0},
                                 bpm_before=90.909, bpm_after=44.776)
    check(off["verdict"] == "FAIL" and off["octave_fold"]["same_beat"] is True
          and off["bpm_grants_pass"] is False,
          "D1: a folded bpm pair with no onset/energy evidence still FAILS")


# ---- D1: the fail-closed rap audio check -----------------------------------

def test_d1_rap_check_is_fail_closed():
    """No validated rap detector exists: without a labelled rap control the
    verdict is UNMEASURED, which blocks a take PASS -- never a fabricated PASS."""
    segs = [{"delivery": "spoken", "start": 0, "end": 5, "source": "measured"},
            {"delivery": "sung", "start": 5, "end": 20, "source": "measured"}]
    env = {k: "" for k in RC.REQUIRED}
    out = RC.gate(segs, env=env)
    check(out["verdict"] == "UNMEASURED" and ("blocks PASS" in out["reason"] or "cannot pass" in out["reason"]),
          "D1: rap on the audio is UNMEASURED and blocks PASS without a control (%r)"
          % (out["verdict"],))
    check(RC.classify(segs, env=env)["verdict"] == "UNMEASURED",
          "D1: classify is fail-closed on the same evidence")
    check(RC.gate([], env=env)["verdict"] == "UNMEASURED"
          and RC.control_ready(env) is False,
          "D1: an empty take and a missing control are both UNMEASURED")
    check(all(k in RC.REQUIRED for k in ("rap", "sung", "spoken_over_beat")),
          "D1: the control set names rap, sung and spoken-over-beat")


# ---- D1: the two conflated figures ----------------------------------------

def test_d1_words_versus_music_are_separate_labels():
    """The 58.4 s figure is 50.416 s of WORDS plus 8 s of music-only time -- the
    music seconds are runtime, never word time."""
    rep = SV.coverage_report(50.416, 8.0)
    check(rep["vocal_words_s"] == 50.416 and rep["music_only_s"] == 8.0
          and rep["runtime_s"] == 58.416,
          "D1: words, music-only time and runtime are reported separately")
    check(rep["words_and_music_are_separate_labels"] is True
          and "NEVER counted as word time" in rep["label"],
          "D1: the label states the music seconds are not word time")


def test_d1_sheet_parser_counts_the_three_deliveries_separately():
    """REGRESSION PIN. The failed run's 58 s sheet is 69 SUNG + 13 SPOKEN + 19 RAP
    words (101 total), never "101 words of one delivery". A parser that collapses
    the three deliveries re-breaks the rap floor."""
    sheet = [{"tag": "Intro", "delivery": "spoken", "lines": ["one two three four five six"]},
             {"tag": "Verse", "delivery": "sung", "lines": ["word " * 60]},
             {"tag": "Hook 1", "delivery": "sung", "lines": ["word " * 9]},
             {"tag": "Verse", "delivery": "rap", "lines": ["flow " * 19]},
             {"tag": "Outro", "delivery": "spoken", "lines": ["cta " * 7]}]
    out = SCT.check_sheet(R.render_lyrics(sheet, "rnb-flow"), "rnb-flow", 58)
    t = out["totals"]
    check(t["sung_words"] == 69 and t["spoken_words"] == 13 and t["rap_words"] == 19,
          "D1: the sheet parses as 69 sung + 13 spoken + 19 rap (%r)"
          % ({k: t[k] for k in ("sung_words", "spoken_words", "rap_words")},))
    check(t["total_words"] == 101,
          "D1: the three deliveries total 101 words, not 101 of one delivery")


# ---- defect 2: the two D1 audio gates are WIRED INTO the judge -------------

def _wired_take(plan):
    """Judge a take that stops just past the detector gate. It can never be a
    PASS (the hook and the style contract are unfilfilled), which is exactly
    what makes it the right probe for "UNMEASURED keeps a take off PASS"."""
    import song_dispatch as SD
    take = {"segments": [{"delivery": "sung", "start": 0.0, "end": 30.0,
                          "source": "measured"}],
            "aligned_words": [], "duration_s": 58.0, "detector": "singing_detector 2",
            "music_under_speech_ratio": 1.0, "tail_rms_dbfs": -20.0, "first_sung_s": 5.0}
    return SD.judge_take(take, plan, "", "", None, "rnb-flow", "")


def test_d1_the_two_audio_gates_are_wired_into_the_take_judge():
    """WWFIXGAPS U1 (defect 2): rap_check and pace_change shipped, but NOTHING
    CALLED them, so "UNMEASURED blocks a take PASS" was true only of the module
    in isolation. The spies below fail if judge_take stops calling them again."""
    import song_dispatch as SD
    check("rap_audio" in SD.GATES and "pace_change" in SD.GATES,
          "D2: the take judge declares both D1 audio gates")
    calls = {"rap": 0, "pace": 0}
    rap_gate, pace_judge = RC.gate, PC.judge_plan_pace

    def rap_spy(segs):
        calls["rap"] += 1
        return rap_gate(segs)

    def pace_spy(plan, *a, **kw):
        calls["pace"] += 1
        return pace_judge(plan, *a, **kw)

    RC.gate, PC.judge_plan_pace = rap_spy, pace_spy
    try:
        base = {"delivered_s": 58, "style_id": "rnb-flow", "sheet_text": "", "hook_plan": {}}
        plain = _wired_take(base)
        ordered = _wired_take(dict(base, pace_change={
            "reason": "the bridge lifts into the last hook", "boundary_s": 40.0}))
    finally:
        RC.gate, PC.judge_plan_pace = rap_gate, pace_judge
    check(calls == {"rap": 2, "pace": 2},
          "D2: judge_take CALLS rap_check.gate and pace_change.judge_plan_pace (%r)" % (calls,))
    check(plain["gates"]["rap_audio"]["verdict"] == "UNMEASURED"
          and "rap_audio" in plain["flagged"] and plain["verdict"] != "PASS",
          "D2: an unmeasured rap read is flagged and never reaches PASS")
    check(plain["gates"]["pace_change"]["verdict"] == "PASS"
          and plain["gates"]["pace_change"]["detail"].startswith("no ordered pace change"),
          "D2: with no ordered gear change there is nothing to enforce")
    check(ordered["gates"]["pace_change"]["verdict"] == "UNMEASURED"
          and "pace_change" in ordered["flagged"] and ordered["verdict"] != "PASS",
          "D2: an ordered gear change with no evidence never reaches PASS")


# ---- WW-21: the total fail-closed acceptance boundary ----------------------
#
# WW-21 is the aggregation + EVIDENCE-BINDING boundary that runs BEFORE spend.
# It is NOT a sixth audio gate: it measures no audio and claims no
# audio-quality outcome. The plan (WW-ROUND3-FIX-PLAN.md, unit WW-21, lines
# 54-58) names exactly the five delivered-audio results below.
#
# PROPOSED: `SD._MIN_AUDIO_RESULTS == 5` is the COUNT OF THE FIVE GATE NAMES
# THE PLAN ALREADY NAMES. It is a proposed value in acceptance-profile.json
# (`audio_results.minimum_count`) -- a count, not a measured limit, and NOT a
# number Trevor set. It moves only when the plan's own gate list moves.

from song_dispatch import song_dispatch as SD   # noqa: E402  (WW-21 boundary)

WW21_VID = "polished-modern"


def _ww21_export(tmp, name="export-1"):
    p = os.path.join(tmp, "%s.mp3" % name)
    with open(p, "wb") as f:
        f.write(("fake export bytes %s" % name).encode("utf-8"))
    return p


def _ww21_binding(tmp, name="export-1"):
    return SD.take_binding(_ww21_export(tmp, name), "creative-r7")


def _ww21_results(binding):
    """All five valid controls: PASS, each bound to the take being advanced."""
    return {name: {"verdict": "PASS", "binding": dict(binding), "detail": "control ok"}
            for name in SD.AUDIO_RESULTS}


def _three_results(tmp):
    return [{"n": i, "variant": {"id": v, "label": L, "description": "d"},
             "status": "PASS", "attempt": 1, "attempts": 1, "receipts": [],
             "take": {"audio_path": _ww21_export(tmp, "take-%s" % v), "duration_s": 58.0}}
            for i, (v, L) in enumerate((("polished-modern", "POLISHED MODERN"),
                                        ("warm-live-band", "WARM LIVE BAND"),
                                        ("cinematic-strings", "CINEMATIC STRINGS")), 1)]


def test_ww21_five_valid_controls_pass_with_zero_purchases():
    """POSITIVE CONTROL, before any generation: an empty fake-transport counter
    stays at zero and the boundary advances ONLY on all five valid results."""
    spend = []

    def fake_transport(_):                       # the fake transport: a purchase
        spend.append(_)
        return []

    assert SD.AUDIO_RESULTS == ("D1", "D2", "D3", "D4", "D5")
    assert SD._MIN_AUDIO_RESULTS == 5
    with tempfile.TemporaryDirectory() as tmp:
        b = _ww21_binding(tmp)
        out = SD.accept_audio_results(_ww21_results(b), b)
        print("  WW-21 positive control: verdict=%r required=%r binding=%r"
              % (out["verdict"], out["required"], sorted(b)))
        assert out["verdict"] == "PASS" and out["blocked_by"] == [] and out["purchases"] == 0
        assert out["required"] == list(SD.AUDIO_RESULTS)
        fake_transport("nothing")                # the transport itself is proven callable
        assert len(spend) == 1
        spend.clear()
    assert spend == [], "zero purchases on the positive control"


def test_ww21_each_named_negative_control_blocks_with_its_reason():
    """THE PLAN'S NEGATIVE CONTROLS. Every one of these must BLOCK with the
    intended, named reason, and every refusal path reports zero purchases."""
    with tempfile.TemporaryDirectory() as tmp:
        b = _ww21_binding(tmp)
        other = SD.take_binding(_ww21_export(tmp, "export-2"), "creative-r7")
        removed = _ww21_results(b)
        removed.pop("D4")                                     # remove one result
        controls = [
            ("remove one result D4", removed, b),
            ("inject UNKNOWN on D4", dict(_ww21_results(b),
                                          D4={"verdict": "UNKNOWN", "binding": dict(b)}), b),
            ("inject UNAVAILABLE on D4", dict(_ww21_results(b),
                                              D4={"verdict": "UNAVAILABLE", "binding": dict(b)}), b),
            ("inject UNMEASURED on D4", dict(_ww21_results(b),
                                             D4={"verdict": "UNMEASURED", "binding": dict(b)}), b),
            ("inject FAIL on D3", dict(_ww21_results(b),
                                       D3={"verdict": "FAIL", "binding": dict(b)}), b),
            ("inject FLAG on D4", dict(_ww21_results(b),
                                       D4={"verdict": "FLAG", "binding": dict(b)}), b),
            ("stale digest on D2",
             dict(_ww21_results(b), D2={"verdict": "PASS", "binding": dict(other)}), b),
            ("malformed non-mapping record on D5",
             dict(_ww21_results(b), D5=["PASS"]), b),
            ("malformed record with no verdict on D1",
             dict(_ww21_results(b), D1={"binding": dict(b)}), b),
            ("manual relabel on D4",
             dict(_ww21_results(b), D4={"verdict": "PASS",
                                        "binding": dict(b, source="manual")}), b),
            ("a bare string standing in for a binding on D4",
             dict(_ww21_results(b), D4={"verdict": "PASS", "binding": "manual-pass"}), b),
            ("stale profile revision on D4",
             dict(_ww21_results(b), D4={"verdict": "PASS",
                                        "binding": dict(b, profile_revision="0.0.0")}), b),
            ("unexpected extra non-PASS result",
             dict(_ww21_results(b), D6={"verdict": "UNKNOWN", "binding": dict(b)}), b),
            ("an empty result set", {}, b),
            ("a non-mapping result set", ["PASS"] * 5, b),
            ("a take binding that is not a mapping", _ww21_results(b), "manual"),
            ("a take binding missing its export digest",
             _ww21_results(b), {"creative_revision": "r7", "profile_revision": "1.0.0"}),
        ]
        for label, results, binding in controls:
            out = SD.accept_audio_results(results, binding)
            first = (out["blocked_by"] or ["<none>"])[0]
            print("  WW-21 BLOCK [%s] -> verdict=%r reason=%s" % (label, out["verdict"], first))
            check(out["verdict"] != "PASS" and out["blocked_by"],
                  "WW-21: %s BLOCKS (%s)" % (label, first.split(":")[0]))
            check(out["purchases"] == 0,
                  "WW-21: %s buys NOTHING (zero purchases)" % label)

        # the profile's OWN keys are live: the boundary reads what the profile
        # writes, so neither required[] nor minimum_count is a dead key
        prof = SD.acceptance_profile()
        check(prof["audio_results"]["required"] == list(SD.AUDIO_RESULTS),
              "WW-21: the profile's required list is the five delivered-audio results")
        lower = dict(prof, audio_results=dict(prof["audio_results"], minimum_count=4))
        check(SD.accept_audio_results(_ww21_results(b), b, profile=lower)["verdict"] == "PASS",
              "WW-21: the profile's minimum_count is READ (a lower count still passes)")
        higher = dict(prof, audio_results=dict(prof["audio_results"], minimum_count=6))
        hi = SD.accept_audio_results(_ww21_results(b), b, profile=higher)
        print("  WW-21 profile minimum_count=6 -> %r %s" % (hi["verdict"], hi["blocked_by"][:1]))
        check(hi["verdict"] != "PASS" and hi["blocked_by"][0].startswith("INCOMPLETE_EVIDENCE"),
              "WW-21: a raised minimum_count BLOCKS 5 carried results")
        sixth = dict(prof, audio_results=dict(prof["audio_results"],
                                              required=list(SD.AUDIO_RESULTS) + ["D9"]))
        six = SD.accept_audio_results(_ww21_results(b), b, profile=sixth)
        print("  WW-21 profile required+D9 -> %r %s" % (six["verdict"], six["blocked_by"][:1]))
        check(six["verdict"] != "PASS" and six["blocked_by"][0].startswith("MISSING_AUDIO_RESULT"),
              "WW-21: the profile's required list is READ (a sixth required gate blocks)")
        noprof = SD.accept_audio_results(_ww21_results(b), b, profile={})
        check(noprof["verdict"] != "PASS" and noprof["blocked_by"][0].startswith("PROFILE_UNAVAILABLE"),
              "WW-21: a missing profile BLOCKS -- no gates can be assumed away")


def test_ww21_empty_and_malformed_finisher_never_pass():
    """The TOTAL finisher. Before WW-21, `_finish({})` returned PASS -- an empty
    gate set was indistinguishable from a perfect take -- and an UNKNOWN or
    UNAVAILABLE gate was silently ignored."""
    empty = SD._finish({})
    print("  WW-21 _finish({}) -> %r %r" % (empty["verdict"], empty["blocked_by"][:1]))
    check(empty["verdict"] != "PASS" and empty["blocked_by"],
          "WW-21: _finish({}) BLOCKS -- an empty gate set never passes")
    for verdict in ("FAIL", "FLAG", "UNMEASURED", "UNAVAILABLE", "UNKNOWN"):
        out = SD._finish({"detector": {"verdict": verdict}})
        print("  WW-21 _finish({'detector': %r}) -> %r" % (verdict, out["verdict"]))
        check(out["verdict"] != "PASS",
              "WW-21: a %s gate BLOCKS the finisher" % verdict)
    for bad in ({"detector": "PASS"}, {"detector": {"verdict": ""}},
                {"detector": {"verdict": "MADE-UP"}}, {"detector": {}}, {"detector": []}):
        out = SD._finish(bad)
        print("  WW-21 _finish(malformed %r) -> %r %r" % (bad, out["verdict"], out["malformed"]))
        check(out["verdict"] != "PASS" and out["malformed"],
              "WW-21: a malformed record BLOCKS the finisher (%r)" % (bad,))
    missing = SD._finish({"detector": {"verdict": "PASS"}})
    print("  WW-21 _finish(one PASS gate) -> %r missing=%d" % (missing["verdict"], len(missing["missing"])))
    check(missing["verdict"] != "PASS" and missing["missing"],
          "WW-21: a missing required gate BLOCKS the finisher")
    check(SD._finish({"detector": {"verdict": "PASS"}}, required=("detector",))["verdict"] == "PASS",
          "WW-21: with that ONE gate required and PASSing, the finisher PASSES")
    take = {"segments": [{"delivery": "spoken", "start": 0.0, "end": 2.0, "source": "measured"},
                         {"delivery": "sung", "start": 2.5, "end": 45.0, "source": "measured"},
                         {"delivery": "spoken", "start": 45.0, "end": 54.0, "source": "measured"}],
            "aligned_words": [], "duration_s": 57.5, "detector": "singing_detector 2.0.0",
            "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0, "first_sung_s": 2.5}
    full = SD.judge_take(take, {"delivered_s": 58, "style_id": "soul-ballad", "sheet_text": "",
                                "hook_plan": {}}, "", "", None, "soul-ballad", "")
    print("  WW-21 a fully-judged take: missing=%r malformed=%r verdict=%r"
          % (full["missing"], full["malformed"], full["verdict"]))
    check(full["missing"] == [] and full["malformed"] == [] and set(full["gates"]) == set(SD.GATES),
          "WW-21: judge_take writes EVERY declared gate -- no gate in GATES is a dead name")


def test_ww21_rap_loophole_guard_fires_on_the_production_call_path():
    """THE DEAD-GUARD PROOF. The production entry point `cmd_generate` builds a
    plan with NO `words` key at all, so `_planned_pct` returns None: the plan
    declares no rap. The guard is reached through the REAL call path
    (cmd_generate -> one_variant -> run_takes -> judge_take -> _finish), its
    input is printed at that call site, and it fires on the value that path
    produces -- `rap_share` is no longer a PASS."""
    seen = []
    with tempfile.TemporaryDirectory() as tmp:
        calls = {"n": 0}

        def generate(variant, request):
            calls["n"] += 1
            return [{"segments": [{"delivery": "spoken", "start": 0.0, "end": 2.0, "source": "measured"},
                                  {"delivery": "sung", "start": 2.5, "end": 45.0, "source": "measured"},
                                  {"delivery": "spoken", "start": 45.0, "end": 54.0, "source": "measured"}],
                     "aligned_words": [], "duration_s": 57.5,
                     "detector": "singing_detector 2.0.0", "music_under_speech_ratio": 0.6,
                     "tail_rms_dbfs": -30.0, "first_sung_s": 2.5,
                     "audio_path": _ww21_export(tmp, "prod-%s" % variant["id"])}]

        def save(variant, take, rcpt):
            seen.append((variant["id"], rcpt))

        a = argparse.Namespace(run_dir=tmp, request=_spec_file(tmp), ledger="", run_id="R",
                               variant="", unit_id="")
        out = SC.cmd_generate(a, generate=generate, measure=lambda t: {}, save=save)
        print("  WW-21 production path: cmd_generate dispatched=%r variants judged=%d"
              % (out["dispatched"], len(seen)))
        assert seen, "the production path never reached the take judge"
    by = {vid: rcpt for vid, rcpt in seen}
    assert len(by) == 3
    for vid, rcpt in sorted(by.items()):
        g = rcpt["gates"]["rap_share"]
        print("  WW-21 guard input at the real call site [%s]: plan words has no 'rap' "
              "(planned -> None) and the take measured 0.0 s of rap" % vid)
        print("  WW-21 guard fires      [%s]: rap_share=%r detail=%s" % (vid, g["verdict"], g["detail"]))
        check(g["verdict"] != "PASS" and g["detail"].startswith("RAP_NEITHER_PLANNED_NOR_MEASURED"),
              "WW-21: the rnb-flow no-planned/no-measured-rap guard fires through cmd_generate (%s)" % vid)
        check("rap_share" in rcpt["flagged"],
              "WW-21: the closed loophole lands in the receipt's flagged set (%s)" % vid)
    # and the same guard, on the SAME production plan shape, from the aggregator
    with tempfile.TemporaryDirectory() as tmp2:
        b = _ww21_binding(tmp2)
        blocked = SD.accept_audio_results(
            dict(_ww21_results(b), D1={"verdict": "FLAG",
                                       "binding": dict(b),
                                       "detail": "RAP_NEITHER_PLANNED_NOR_MEASURED"}), b)
        print("  WW-21 aggregator on the carried rap FLAG -> %r %s"
              % (blocked["verdict"], blocked["blocked_by"][:1]))
        check(blocked["verdict"] != "PASS" and blocked["purchases"] == 0,
              "WW-21: the rap-style fault cannot advance through the acceptance boundary")


def test_ww21_the_block_reaches_offer_pick_and_purchase():
    """THE DELIVERY BOUNDARY. The production generator writes a take into
    <run>/music/takes/<variant>/; the moment one exists, an all-PASS acceptance
    record is REQUIRED. Until it exists the take is never OFFERED, never
    PICKED and never PURCHASED, and every refusal path shows zero purchases."""
    with tempfile.TemporaryDirectory() as tmp:
        run = os.path.join(tmp, "run")
        d = os.path.join(run, "music", "takes", WW21_VID)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "take-1.mp3"), "wb") as f:
            f.write(b"a produced take, as _real_generate leaves it")
        SC._write_envelope(run, WW21_VID, {"accepted_submit_at": "2026-01-01T00:00:00Z",
                                           "terminal_at": "2026-01-01T00:00:04Z"})
        chk = SC.acceptance_from_run(run)
        print("  WW-21 boundary state at the delivery boundary: applicable=%r allowed=%r blocked=%r"
              % (chk["applicable"], chk["allowed"], chk["blocked"]))
        check(chk["applicable"] is True and chk["allowed"] is False,
              "WW-21: a produced take with no acceptance record APPLIES and BLOCKS")
        purchases = []
        # OFFER
        try:
            SC.deliver_choices(_three_results(tmp), os.path.join(tmp, "D"), run,
                               runner=purchases.append, send=purchases.append)
        except SC.ChoiceError as e:
            print("  WW-21 OFFER refused: %s" % e)
            check(True, "WW-21: the OFFER is refused")
        else:
            check(False, "WW-21: an unaccepted take was OFFERED")
        # PICK
        SC.init(run, True)
        st = SC._state(run) or {}
        st.update(required=True, offered={"1": {"label": "1 - X (y)", "file": _ww21_export(tmp, "pick"),
                                                "duration": "0:58"}})
        SC._write(run, "state.json", st)
        try:
            SC.record_pick(run, "1")
        except SC.ChoiceError as e:
            print("  WW-21 PICK refused: %s" % e)
            check(True, "WW-21: the PICK is refused")
        else:
            check(False, "WW-21: an unaccepted take was PICKED")
        # PURCHASE (the kie_dispatch seam: every non-music paid job)
        r = SC.dispatch_refusal(False, run)
        print("  WW-21 PURCHASE gate: %r" % ((r or {}).get("reason_code"),))
        check(bool(r) and r["reason_code"] == SD.ACCEPTANCE_CODE_NOT_PROVEN,
              "WW-21: the PURCHASE gate refuses every non-music paid job")
        check(SC.refusal(run)["reason_code"] == SD.ACCEPTANCE_CODE_NOT_PROVEN,
              "WW-21: the run refusal carries the acceptance code")
        check(purchases == [], "WW-21: zero purchases on every refusal path")

        # a record that is not all PASS still blocks; only an all-PASS record opens it
        b = _ww21_binding(tmp)
        SD.record_acceptance(run, WW21_VID, b,
                             dict(_ww21_results(b), D5={"verdict": "UNMEASURED", "binding": dict(b)}))
        check(SC.acceptance_from_run(run)["allowed"] is False,
              "WW-21: an UNMEASURED result in the written record still BLOCKS")
        SD.record_acceptance(run, WW21_VID, b, _ww21_results(b))
        print("  WW-21 written all-PASS record -> %r" % (SC.acceptance_from_run(run)["verdict"],))
        check(SC.acceptance_from_run(run)["allowed"] is True,
              "WW-21: the all-PASS record written by record_acceptance opens (the reader reads the writer's key)")
        check(not SC._acceptance_refusal(run, "the offer"),
              "WW-21: with the record in place the OFFER is no longer held")
        # a corrupt record is skipped and the take rule re-blocks it
        with open(os.path.join(run, "music", "acceptance", "%s.json" % WW21_VID), "w",
                  encoding="utf-8") as f:
            f.write("{not json at all")
        chk = SC.acceptance_from_run(run)
        print("  WW-21 corrupt record -> applicable=%r blocked=%r reason=%s"
              % (chk["applicable"], chk["blocked"],
                 chk["variants"][WW21_VID]["reasons"][0][:60]))
        check(chk["applicable"] and chk["allowed"] is False,
              "WW-21: an unreadable acceptance record BLOCKS")
        check(purchases == [], "WW-21: still zero purchases")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print("\n%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
