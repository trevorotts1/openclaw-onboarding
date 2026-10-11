#!/usr/bin/env python3
"""WWFIX-U1 acceptance tests: the D2 three-version money-safety trap, the D1 rap
floor, the story gates, the pace gate, the fail-closed rap check, the provider
overlap receipt and the words-versus-music label.

Every threshold these tests pin is a NEW ACCEPTANCE RULE added by WWFIX-U1, not
a measured limit of an earlier run.

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
                        "So I count what I make and not what they take today,"]},
             {"tag": "Outro", "delivery": "spoken",
              "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
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


def test_d2_cmd_generate_reports_one_dispatch_or_three():
    """The canonical entry point: `--unit-id` -> dispatched 1, no flag -> 3, and
    the umbrella receipt distinguishes 3 THREADS from 3 visible agent units."""
    for flag, want in (("WW-001", 1), ("", 3)):
        with tempfile.TemporaryDirectory() as tmp:
            a = argparse.Namespace(run_dir=tmp, request=_spec_file(tmp), ledger="",
                                   run_id="R", variant="", unit_id=flag)
            calls, gen = _counting_generate()
            out = SC.cmd_generate(a, generate=gen, measure=lambda t: {},
                                  save=lambda v, t, r: None, plan=_plan())
            check(out["dispatched"] == want,
                  "D2: cmd_generate --unit-id %r dispatches %d" % (flag or "none", want))
            if want == 3:
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
