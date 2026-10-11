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
Extended by the WW-PREVENT-RECURRENCE wave (Unit U1, package arc-revision-battery):
WW-10 (three DISTINCT initial identities, integer microseconds, 0.999 s FAILS),
WW-03 (the performed-beat manifest and the creative fingerprint, from ONE source),
WW-11 (parity release check, judge-path gate-removal and delivery-boundary tests)
and WW-19 (the import audit of the six referenced module paths). The WW-wave
thresholds are NEW ACCEPTANCE RULES under the same rule stated above.

ONE battery: this file. No second framework, no second suite.

Run: python3 core/music_qc/test_wwfix_u1.py
"""
import argparse
import datetime
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL_ROOT = os.path.dirname(os.path.dirname(CORE))
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
UNDETERMINED = []


def check(cond, label):
    if cond:
        print("ok   %s" % label)
    else:
        print("FAIL %s" % label)
        FAILURES.append(label)


def undetermined(label, why):
    """A dependency owned by a sibling work package that has not landed yet is
    UNDETERMINED -- never a pass."""
    print("UNDETERMINED %s: %s" % (label, why))
    UNDETERMINED.append("%s (%s)" % (label, why))


def gate(cond, label, why):
    """Guard: a missing (not-yet-published) dependency is UNDETERMINED, never a
    pass; a present-but-wrong dependency is a real FAIL."""
    if cond:
        return True
    undetermined(label, why)
    return False


def _load_path(rel):
    """Load a module from a file path so the battery never depends on a package
    __init__ that lands with another work package."""
    p = os.path.join(CORE, rel)
    if not os.path.exists(p):
        return None
    mod = "dsaf_" + rel.replace("/", "_").replace(".", "_")
    try:
        spec = importlib.util.spec_from_file_location(mod, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except Exception:
        return None


try:
    import song_dispatch as SD                      # noqa: E402
except Exception:
    SD = None
SA = _load_path("story_arc/story_arc.py")


CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
#: The R&B Flow sheet on the 88-SECOND CARD (WW-01 made the rap floor PER
#: VERSE: 2 verses, each 8.8 s / 22 words at D = 88 => 40 rap words = 16.0 s at
#: 2.5 wps). Below 88 s the same shape cannot hold BOTH the per-verse rap floor
#: AND the style's sung-share target at once -- at 58 s the sung share the style
#: plans (72.9% of voice) and the per-verse floor pull in opposite directions
#: and no 58 s sheet satisfies both, which is exactly the defect the 58 s
#: fixtures hit. At 88 s the budget clears both: 78 sung + 40 rap + 3 spoken,
#: the shipped 88-second golden (suno-90s-rnb-flow.json) passes every gate the
#: same way. The spoken [Outro] is dropped for the rap variant -- the intro +
#: CTA shape is exercised by every non-rap sheet -- and the hook block is
#: declared FOUR times (the 88 s plan fits four hook blocks; three is refused).
SHEET_RNB = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["And I rise above the pa-a-ain,", "Through the dark I walk alo-o-one,"]},
             {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["One seed of truth made me stro-o-ong,", "I hold the light I found,",
                        "I walk out free,", "I rise a-a-above,", "I am more than this,",
                        "I am he-e-ere,", "I am not lost,", "I am still standing ta-a-all,"]},
             {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
             {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
             {"tag": "Hook 4", "delivery": "sung", "lines": HOOK},
             {"tag": "Verse", "delivery": "rap",
              "lines": ["Backup shoes, backup jacket, but no backup plan,",
                        "So I count what I make and not what they take today,"]},
             {"tag": "Verse", "delivery": "rap",
              "lines": ["Every door they closed I opened with my own two hands,",
                        "And I keep walking toward the morning light now,"]}]
HOOK_PLAN = {"true_at_beat": "the_world"}
SPOKEN_RANGE = (15, 20)


def _reqs():
    return SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88, hook_plan=HOOK_PLAN)


def _plan():
    return {"delivered_s": 88, "style_id": "rnb-flow",
            "sheet_text": R.render_lyrics(SHEET_RNB, "rnb-flow"), "hook_plan": HOOK_PLAN}


def _spec_file(tmp):
    path = os.path.join(tmp, "req.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"style_id": "rnb-flow", "client_text": CLIENT, "title": "T",
                   "length_s": 88, "hook_plan": HOOK_PLAN,
                   "input": {"lyrics": R.render_lyrics(SHEET_RNB, "rnb-flow"),
                             "style_id": "rnb-flow", "duration": 88, "vocal_gender": "f"}}, f)
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

def _receipts(base, seconds, attempt_ids=("a1", "a2", "a3"), initial=True, variants=None):
    # WW-10: the gate needs three DISTINCT (variant, attempt, task) identities, so
    # the default variant is per-attempt. ``variants`` lets a caller pin its own.
    t0 = base
    out = []
    for i, aid in enumerate(attempt_ids):
        v = variants[i] if variants and i < len(variants) else "variant-%s" % aid
        out.append(OV.make_receipt(v, {"k": i}, "logical", aid, "task-%s" % aid,
                                   t0, t0 + datetime.timedelta(seconds=seconds),
                                   initial=initial))
    return out


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
    # WW-10 adaptation: the gate now reads the labelled provider clock
    # (``accepted_submit_at``) and validates the receipt digest, so a naive-clock
    # probe must strip BOTH provider stamps and the digest.
    naive = [dict(r, submitted_at=r["submitted_at"].replace("Z", ""),
                  accepted_submit_at=r["accepted_submit_at"].replace("Z", ""),
                  terminal_at=r["terminal_at"].replace("Z", ""), receipt_sha256=None)
             for r in _receipts(base, 5.0)]
    check(OV.overlap_gate(naive)["verdict"] == "UNAVAILABLE",
          "D2: an unlabelled/naive clock is not admissible evidence")
    local = [dict(r, timestamp_source="local", receipt_sha256=None)
             for r in _receipts(base, 5.0)]
    check(OV.overlap_gate(local)["verdict"] == "UNAVAILABLE",
          "D2: a receipt labelled with a LOCAL clock is not admissible evidence")
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
    out = SCT.check_sheet(R.render_lyrics(thin, "rnb-flow"), "rnb-flow", 88)
    check(out["verdict"] == "FAIL"
          and any(r.startswith("RAP_PLANNED_ZERO_WORDS") for r in out["reasons"]),
          "D1: an R&B Flow sheet with no rap lines is refused (%r)" % (out["reasons"][:1],))
    check(out["totals"]["rap_floor_words"] == 22 and out["totals"]["rap_floor_s"] == 8.8,
          "D1: the refusal names the 88 s floor (22 rap words / 8.8 s)")
    ok = SCT.check_sheet(R.render_lyrics(SHEET_RNB, "rnb-flow"), "rnb-flow", 88)
    check(ok["verdict"] == "PASS" and ok["totals"]["rap_words"] >= 22,
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


# ---- WW-23: BOTH musical transitions ---------------------------------------
#
# WW-23 extends the EXISTING D3 pace gate (music_qc/pace_change) -- it is not a
# sixth audio gate. Two approved semantic anchors (the drop and the return) and
# TWO DISTINCT seam timestamps are mandatory BEFORE generation; the exports are
# judged by D3 alone. Every threshold is PROPOSED (acceptance-profile.json
# ww_wave.pace_change), never a measured limit and never a number Trevor set.

#: the WW-23 module helper the song_contract package __init__ does not re-export
_SCM = getattr(SCT, "song_contract", SCT)

def _ww23_order(**over):
    o = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove",
         "boundary_s": 20.0, "return_boundary_s": 60.0}
    o.update(over)
    return o

def _ww23_request(order):
    """The REAL assembled provider request for rnb-flow at 88 s, carrying the
    order's pace clause in input.style and the internal _pace_plan metadata."""
    return SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88,
                             hook_plan=HOOK_PLAN, pace_plan=order)[0][1]

def _ww23_take():
    return {"segments": [{"delivery": "sung", "start": 0.0, "end": 30.0, "source": "measured"}],
            "aligned_words": [], "duration_s": 88.0, "detector": "singing_detector 2",
            "music_under_speech_ratio": 1.0, "tail_rms_dbfs": -20.0, "first_sung_s": 5.0}

def test_ww23_the_exact_payload_carries_both_directions_and_no_internal_metadata():
    """The exact SERIALIZED payload carries both approved directions, and the
    internal _pace_plan judging metadata is not a provider instruction."""
    if not gate(SD is not None, "WW-23 payload", "song_dispatch/song_choices absent"):
        return
    order = _ww23_order()
    req = _ww23_request(order)
    payload = json.dumps(req, sort_keys=True)
    check(("half-time drop, thin drums" in payload and "turn and rise back to the groove" in payload),
          "WW-23: the exact serialized payload carries BOTH pace changes")
    check(_SCM.check_pace_style(req["input"]["style"], order) == [],
          "WW-23: the final style carries both directions (known-good control)")
    check(PC.pace_provider_leak(req) is True and "_pace_plan" in payload,
          "WW-23: the internal _pace_plan IS on the raw request until run_takes strips it")
    check(PC.pace_provider_leak({"input": {"style": "clean"}}) is False,
          "WW-23: a clean provider payload carries no _pace_plan metadata")

def test_ww23_pre_generation_gate_blocks_missing_seam_reused_boundary_and_one_direction():
    """BEFORE generation. Removing the gate invocation in song_dispatch.run_takes
    makes every one of these negatives stop refusing, so the wiring is real."""
    if not gate(SD is not None and hasattr(SD, "run_takes"), "WW-23 pre-gen gate",
                "song_dispatch.run_takes absent"):
        return
    plan = dict(_plan())

    def _gen(calls):
        def gen(rq):
            calls.append(rq)
            return [dict(_ww23_take()), dict(_ww23_take())]
        return gen

    # KNOWN-GOOD CONTROL first: a complete two-seam order reaches generation.
    calls = []
    order_ok = _ww23_order()
    out = SD.run_takes(_ww23_request(order_ok), dict(plan, pace_change=order_ok),
                       _gen(calls), lambda t: {}, lambda t, r: None,
                       CLIENT, " ".join(HOOK), cap_cents=6)
    check(len(calls) == 1, "WW-23: a complete two-seam order reaches generation")
    check(calls and not PC.pace_provider_leak(calls[0]),
          "WW-23: the request the provider receives carries NO _pace_plan metadata")

    # MISSING SEAM blocks before any generation
    calls = []
    miss = _ww23_order(return_boundary_s=None)
    try:
        SD.run_takes(_ww23_request(miss), dict(plan, pace_change=miss),
                     _gen(calls), lambda t: {}, lambda t, r: None,
                     CLIENT, " ".join(HOOK), cap_cents=6)
        check(False, "WW-23: a missing seam was accepted")
    except SD.DispatchError as e:
        check("PACE_SEAM_MISSING" in str(e) and calls == [],
              "WW-23: a MISSING seam blocks before any generation (%s)" % (str(e)[:70],))

    # REUSED BOUNDARY blocks
    calls = []
    reuse = _ww23_order(return_boundary_s=20.0)
    try:
        SD.run_takes(_ww23_request(reuse), dict(plan, pace_change=reuse),
                     _gen(calls), lambda t: {}, lambda t, r: None,
                     CLIENT, " ".join(HOOK), cap_cents=6)
        check(False, "WW-23: a reused boundary was accepted")
    except SD.DispatchError as e:
        check("PACE_SEAM_REUSED_BOUNDARY" in str(e) and calls == [],
              "WW-23: a REUSED boundary blocks before any generation (%s)" % (str(e)[:70],))

    # ONE DIRECTION in the final style blocks (the return clause stripped)
    calls = []
    order_ok = _ww23_order()
    req = _ww23_request(order_ok)
    half = dict(req, input=dict(req["input"],
                                style=req["input"]["style"].replace(order_ok["return"], "the outro")))
    try:
        SD.run_takes(half, dict(plan, pace_change=order_ok),
                     _gen(calls), lambda t: {}, lambda t, r: None,
                     CLIENT, " ".join(HOOK), cap_cents=6)
        check(False, "WW-23: a one-direction final style was accepted")
    except SD.DispatchError as e:
        check("PACE_DIRECTION_MISSING" in str(e) and calls == [],
              "WW-23: a final style carrying only ONE transition blocks (%s)" % (str(e)[:70],))

    # check_pace_plan / pace_seams are the unit-level guards the gate calls
    check(PC.check_pace_plan(order_ok) == [],
          "WW-23: check_pace_plan passes a complete order")
    check(any("PACE_SEAM_MISSING" in r for r in PC.check_pace_plan(miss)),
          "WW-23: check_pace_plan names the missing seam")
    check(PC.pace_seams(reuse)["reused"] is True and PC.pace_seams(order_ok)["distinct"] is True,
          "WW-23: pace_seams reads a reused boundary vs two distinct seams")

def test_ww23_return_energy_is_symmetric_and_a_24db_overshoot_blocks():
    """PROPOSED D3: solution onset return 80-120% AND the ABSOLUTE energy
    difference within 3 dB. A 24 dB overshoot is FAIL, not a return."""
    before = {"onset_rate_per_s": 4.0, "rms_dbfs": -14.0}
    problem = {"onset_rate_per_s": 2.0, "rms_dbfs": -18.0}
    good = PC.confirm_pace_change(before, problem, {"onset_rate_per_s": 4.1, "rms_dbfs": -14.5})
    check(good["verdict"] == "PASS", "WW-23: a real return within 3 dB PASSES")
    over = PC.confirm_pace_change(before, problem, {"onset_rate_per_s": 4.1, "rms_dbfs": 10.0})
    check(over["verdict"] == "FAIL" and "energy_return" in over["failed"]
          and over["return_energy_gap_db"] == 24.0,
          "WW-23: a 24 dB return OVERSHOOT blocks (symmetric bound)")
    under = PC.confirm_pace_change(before, problem, {"onset_rate_per_s": 4.1, "rms_dbfs": -38.0})
    check(under["verdict"] == "FAIL" and "energy_return" in under["failed"],
          "WW-23: a 24 dB return UNDERSHOOT blocks the same way (symmetric)")
    check(good["floor"]["return_energy_is_symmetric"] is True,
          "WW-23: the gate reports its return-energy bound as symmetric")

def test_ww23_flat_and_octave_flip_controls_cannot_pass():
    """A flat arrangement (no onset/energy movement) and an octave-aliased bpm
    pair (the same beat) can never register as a gear change."""
    flat = {"onset_rate_per_s": 4.0, "rms_dbfs": -14.0}
    out = PC.confirm_pace_change(flat, dict(flat), dict(flat), bpm_before=42.857, bpm_after=42.857)
    check(out["verdict"] == "FAIL" and "onset_reduction" in out["failed"]
          and "energy_drop" in out["failed"],
          "WW-23: a FLAT arrangement cannot pass the ordered gear change")
    alias = PC.confirm_pace_change(flat, dict(flat), dict(flat), bpm_before=85.2, bpm_after=181.5)
    check(alias["verdict"] == "FAIL" and alias["octave_fold"]["same_beat"] is True
          and alias["bpm_grants_pass"] is False,
          "WW-23: an OCTAVE-FLIP bpm alias with no onset/energy movement cannot pass")

def test_ww23_d3_judges_both_seams_on_the_exports():
    """D3 alone performs both musical checks on the exports: each approved seam
    gets its own smooth-transition review, and the SECOND (return) seam can fail
    on its own."""
    # envelope: the drop seam at 2.0 s is smooth; the return seam at 4.0 s is a cut
    env = [1.0] * 60
    env[40] = 100.0                                  # a flux spike AT the return seam
    before = {"onset_rate_per_s": 4.0, "rms_dbfs": -14.0}
    problem = {"onset_rate_per_s": 2.0, "rms_dbfs": -18.0}
    after = {"onset_rate_per_s": 4.1, "rms_dbfs": -14.5}
    both = PC.confirm_pace_change(before, problem, after, boundary_s=2.0,
                                  return_boundary_s=4.0, envelope=env, hop_s=0.1)
    check(both["checks"].get("smooth_transition") is True
          and both["checks"].get("smooth_transition_return") is False,
          "WW-23: D3 judges BOTH seams independently (drop smooth, return a cut)")
    check(both["verdict"] == "FAIL" and "smooth_transition_return" in both["failed"],
          "WW-23: a hard RETURN seam blocks the exported take on its own")
    # the plan carries both seams into the D3 judge through judge_plan_pace
    order = {"reason": "the bridge lifts", "boundary_s": 2.0, "return_boundary_s": 4.0}
    jp = PC.judge_plan_pace({"pace_change": order}, before, problem, after,
                            envelope=env, hop_s=0.1)
    check(jp["applicable"] is True
          and jp["checks"].get("smooth_transition_return") is False
          and "smooth_transition_return" in jp["failed"],
          "WW-23: judge_plan_pace routes the SECOND seam into D3")
    # NOT a sixth audio gate: the pace checks stay inside the one pace_change gate
    check("pace_change" in SD.GATES
          and not [g for g in SD.GATES if "pace" in g and g != "pace_change"],
          "WW-23: no sixth audio gate -- both pace checks live in the D3 gate")

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

# ---- WW-10: three DISTINCT identities, integer microseconds ---------------

def test_ww10_three_distinct_identities_are_required():
    """WW-10: the gate needs EXACTLY three DISTINCT (variant, attempt, task)
    identities. Two receipts sharing a task id, a repeated variant, or a repeated
    attempt FAIL -- they never PASS."""
    if not gate(OV is not None, "WW-10 distinctness", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    good = OV.overlap_gate(_receipts(base, 5.0))
    check(good["verdict"] == "PASS" and len(good["distinct_identities"]) == 3,
          "WW-10: three distinct task ids PASS (%r)" % (good["distinct_identities"],))
    dup_task = [dict(r) for r in _receipts(base, 5.0)]
    dup_task[1]["task_id"] = dup_task[0]["task_id"]
    g = OV.overlap_gate(dup_task)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_IDENTITY_DUPLICATE",
          "WW-10: two receipts sharing a task id FAIL (%r)" % (g["verdict"],))
    same_identity = [dict(r) for r in _receipts(base, 5.0)]
    same_identity[2].update(attempt_id=same_identity[0]["attempt_id"],
                            task_id=same_identity[0]["task_id"],
                            variant_id=same_identity[0]["variant_id"])
    check(OV.overlap_gate(same_identity)["verdict"] == "FAIL",
          "WW-10: a repeated (variant, attempt, task) identity FAILS")
    no_var = [dict(r) for r in _receipts(base, 5.0)]
    no_var[1]["variant_id"] = None
    check(OV.overlap_gate(no_var)["verdict"] == "UNAVAILABLE",
          "WW-10: an identity with no variant id is UNAVAILABLE, never a pass")


def test_ww10_microseconds_no_rounding_and_0999_fails():
    """WW-10: the comparison is INTEGER MICROSECONDS with no rounding. 999,999 us
    FAILS; 1,000,000 us PASSes -- 0.999999 s can never become 1.0."""
    if not gate(OV is not None, "WW-10 microseconds", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    just_below = OV.overlap_gate(_receipts(base, 0.999999))
    check(just_below["verdict"] == "FAIL" and just_below["overlap_us"] == 999999,
          "WW-10: 999,999 us FAILS with no rounding (%r us)" % (just_below["overlap_us"],))
    at_floor = OV.overlap_gate(_receipts(base, 1.0))
    check(at_floor["verdict"] == "PASS" and at_floor["overlap_us"] == 1000000,
          "WW-10: exactly 1,000,000 us PASSes")
    check(OV.MIN_OVERLAP_US == 1_000_000 and at_floor["microseconds_compared_without_rounding"],
          "WW-10: the floor is declared in microseconds and the comparison states so")


def test_ww10_malformed_reversed_duplicated_digest_all_fail():
    """WW-10: MISSING lifecycle evidence is UNAVAILABLE; MALFORMED, REVERSED,
    DUPLICATED and DIGEST-MISMATCHED evidence is FAIL."""
    if not gate(OV is not None, "WW-10 malformed", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    reversed_r = [dict(r, receipt_sha256=None) for r in _receipts(base, 5.0)]
    reversed_r[0]["terminal_at"] = "2025-12-31T00:00:00.000Z"     # before its submit
    g = OV.overlap_gate(reversed_r)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_EVIDENCE_REVERSED",
          "WW-10: a reversed timestamp FAILS (%r)" % (g["reason_code"],))
    malformed = [dict(r, receipt_sha256=None) for r in _receipts(base, 5.0)]
    malformed[0]["terminal_at"] = "not-a-timestamp"
    g = OV.overlap_gate(malformed)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_EVIDENCE_MALFORMED",
          "WW-10: a malformed timestamp FAILS (%r)" % (g["reason_code"],))
    tampered = [dict(r) for r in _receipts(base, 5.0)]
    tampered[1]["terminal_at"] = "2026-01-01T00:00:05.500Z"       # edited after the digest
    g = OV.overlap_gate(tampered)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_DIGEST_MISMATCH",
          "WW-10: a digest-mismatched receipt FAILS (%r)" % (g["reason_code"],))
    four = OV.overlap_gate(_receipts(base, 5.0, attempt_ids=("a1", "a2", "a3", "a4")))
    check(four["verdict"] == "FAIL", "WW-10: four initial rows FAIL")
    missing = [dict(r, receipt_sha256=None) for r in _receipts(base, 5.0)]
    missing[2]["terminal_at"] = None
    check(OV.overlap_gate(missing)["verdict"] == "UNAVAILABLE",
          "WW-10: a missing terminal stamp is UNAVAILABLE, never a pass")


def test_ww10_scope_is_honest_concurrency_evidence():
    """WW-10: the fix is scoped as a CONCURRENCY-EVIDENCE fix and carries no
    automatic paid redo."""
    if not gate(OV is not None, "WW-10 scope", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    g = OV.overlap_gate(_receipts(base, 5.0))
    check(g.get("scope") == "CONCURRENCY_EVIDENCE" and g.get("paid_redo") is False
          and g.get("preserve_paid_tracks") is True,
          "WW-10: scope is CONCURRENCY_EVIDENCE, no paid redo, paid tracks preserved")

# ---- WW-03 / WW-15: the performed-beat manifest and the fingerprint --------

def _manifest_source(lines_by_beat, delivery="sung", devices=None):
    return {b: {"lines": lines_by_beat.get(b, []), "delivery": delivery,
                "devices": (devices or {}).get(b, [])} for b in SA.BEATS}


def _aligned(text, start=0.0, step=0.3):
    out = []
    for i, w in enumerate(str(text).split()):
        out.append({"word": w, "startS": start + i * step, "endS": start + i * step + 0.2})
    return out


def test_ww03_manifest_covers_all_twelve_beats_from_one_source():
    """WW-03: ONE source -> the performed-beat manifest for ALL TWELVE canonical
    beats; the fingerprint covers lines, delivery, beat map, hook and pace."""
    if not gate(SA is not None, "WW-03 manifest", "story_arc.py not present"):
        return
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    man = SA.build_manifest(_manifest_source(lines))
    check(man["beat_count"] == 12 and len(man["beats"]) == 12
          and man["present_count"] == 12 and not man["missing"],
          "WW-03: the manifest covers all twelve canonical beats from ONE source")
    fp = SA.creative_fingerprint(man)
    check(fp["components"] == ["lines", "delivery", "beat_map", "hook", "pace"]
          and isinstance(fp["sha256"], str) and len(fp["sha256"]) == 64,
          "WW-03: the fingerprint covers lines, delivery, beat map, hook and pace")
    src2 = dict(_manifest_source(lines))
    src2[SA.BEATS[3]] = {"lines": ["a different wound line"], "delivery": "sung"}
    check(SA.build_manifest(src2)["fingerprint"] != man["fingerprint"],
          "WW-03: editing ONE line changes the fingerprint")


def test_ww03_metadata_only_twelve_identifiers_do_not_pass():
    """A metadata-only twelve-identifier list (ids but no heard lines) must NOT
    pass -- it is MANIFEST_METADATA_ONLY, never a pass."""
    if not gate(SA is not None, "WW-03 metadata-only", "story_arc.py not present"):
        return
    ids_only = {b: {"line_ids": ["id-%s" % b]} for b in SA.BEATS}
    man = SA.build_manifest(ids_only)
    binding = SA.bind_revision("rev-3", man)
    g = SA.check_performed_manifest(man, binding, _aligned("anything at all"))
    check(g["verdict"] == "FAIL"
          and any(x == "MANIFEST_METADATA_ONLY" for x in g["failed"]),
          "WW-03: a metadata-only twelve-identifier list is refused (%r)" % (g["failed"],))


def test_ww03_the_shipped_take_is_refused_on_missing_devices():
    """The stored take carries only ONE of the seven approved devices, so six
    required devices are missing and the performed gate refuses it."""
    if not gate(SA is not None, "WW-03 devices", "story_arc.py not present"):
        return
    seven = ["The book showed me the way", "The mirror named the pattern",
             "The mentor held the light", "The wound had a name",
             "The climb was mine", "The doubt was loud", "The call came at dawn"]
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    lines[SA.BEATS[0]] = ["The book showed me the way"]
    man = SA.build_manifest(_manifest_source(lines))
    binding = SA.bind_revision("rev-3", man)
    heard = (_aligned(" ".join(" ".join(lines[b]) for b in SA.BEATS))
             + _aligned("stray filler", start=400.0))
    g = SA.check_performed_manifest(man, binding, heard, required_devices=seven)
    check(g["verdict"] == "FAIL"
          and sum(1 for x in g["failed"] if x.startswith("DEVICE_MISSING")) == 6,
          "WW-03: the shipped take with 1 of 7 devices is refused (%d missing)"
          % sum(1 for x in g["failed"] if x.startswith("DEVICE_MISSING")))


def test_ww03_reorder_and_fingerprint_mismatch_fail():
    """WW-03: a reordered line FAILS, and a take whose stored fingerprint does not
    match the approved sheet is refused -- never retroactively re-bound."""
    if not gate(SA is not None, "WW-03 reorder/fingerprint", "story_arc.py not present"):
        return
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    man = SA.build_manifest(_manifest_source(lines))
    binding = SA.bind_revision("rev-3", man)
    in_order = _aligned(" ".join(" ".join(lines[b]) for b in SA.BEATS))
    ok = SA.check_performed_manifest(man, binding, in_order)
    check(ok["verdict"] == "PASS" and ok["reason_code"] == "PERFORMED_STORY_COVERED",
          "WW-03: all twelve lines heard in order PASS with a matching fingerprint")
    swapped = list(SA.BEATS)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    reordered = _aligned(" ".join(" ".join(lines[b]) for b in swapped))
    bad = SA.check_performed_manifest(man, binding, reordered)
    check(bad["verdict"] == "FAIL", "WW-03: a line reordered FAILS")
    edited = SA.build_manifest(_manifest_source(dict(lines, **{SA.BEATS[0]: ["a new opener"]})))
    mismatch = SA.check_performed_manifest(man, SA.bind_revision("rev-4", edited), in_order)
    check(mismatch["verdict"] == "FAIL" and "FINGERPRINT_MISMATCH" in mismatch["failed"],
          "WW-03: a take whose fingerprint does not match the approved sheet is refused")
    stale = SA.assert_take_bound({"fingerprint": "deadbeef"}, man)
    check(stale["verdict"] == "FAIL" and stale["reason_code"] == "FINGERPRINT_MISMATCH",
          "WW-15: an existing take is NEVER retroactively bound to an edited sheet")
    check(SA.assert_take_bound({"fingerprint": man["fingerprint"]}, man)["verdict"] == "PASS",
          "WW-15: a take matching the approved revision PASSes")


def test_ww03_counts_are_named_and_distinct_never_relabelled():
    """WW-03: the fifteen-stage source method, the eight coarse timing stages and
    the twelve canonical beats are preserved through explicit NAMED mappings and
    never by relabelling one count as another."""
    if not gate(SA is not None, "WW-03 stage mapping", "story_arc.py not present"):
        return
    rep = SA.stage_mapping_report()
    check(rep["source_method_stage_count"] == 15 and rep["timing_stage_count"] == 8
          and rep["canonical_beat_count"] == 12,
          "WW-03: 15 source-method stages, 8 timing stages, 12 canonical beats")
    check(rep["counts_are_distinct"] and rep["mapped_by_name_not_by_count"],
          "WW-03: the three counts are distinct and mapped BY NAME")
    check(all(b in rep["beat_to_timing"] and rep["beat_to_timing"][b] in rep["timing_stages"]
              for b in rep["canonical_beats"]),
          "WW-03: every canonical beat names a real coarse timing stage")


def test_ww03_pace_component_is_one_source():
    """The fingerprint's pace component is defined once, in music_qc/pace_change."""
    if not gate(PC is not None and hasattr(PC, "pace_fingerprint_component"),
                "WW-03 pace component", "music_qc/pace_change.py not present"):
        return
    a = PC.pace_fingerprint_component({"reason": "the bridge lifts", "boundary_s": 40.0})
    b = PC.pace_fingerprint_component({"boundary_s": 40.0, "reason": "the bridge lifts"})
    check(a and a == b, "WW-03: the pace component is stable under key order")
    check(PC.pace_fingerprint_component(None) == ""
          and PC.canonical_pace({"pace_change": {"boundary_s": 1.0}})["drop"]
          == PC.PACE_CUE_DROP,
          "WW-03: no ordered change -> empty component; the cue names half-time")

def test_ww03_beat_missing_is_named_per_absent_beat():
    """ORCH-DEFECTS-0710 (a)/(b): a manifest with ELEVEN of the twelve required
    beats present and heard IN ORDER must FAIL, and the failed list must carry ONE
    BEAT_MISSING entry NAMING the single absent beat. A summary count can never
    stand in for a named missing beat."""
    if not gate(SA is not None, "WW-03 beat-missing", "story_arc.py not present"):
        return
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    absent = SA.BEATS[7]
    partial = {b: v for b, v in lines.items() if b != absent}
    man = SA.build_manifest(_manifest_source(partial))
    check(man["present_count"] == 11 and man["missing"] == [absent],
          "WW-03: eleven of twelve beats are present; %s is the one absent beat" % absent)
    heard = _aligned(" ".join(" ".join(lines[b]) for b in SA.BEATS if b != absent))
    binding = SA.bind_revision("rev-5", man)
    g = SA.check_performed_manifest(man, binding, heard)
    check(g["verdict"] == "FAIL",
          "WW-03: eleven of twelve required beats heard in order is a FAIL (%r)"
          % (g["verdict"],))
    check("BEAT_MISSING:%s" % absent in g["failed"],
          "WW-03: the absent beat is NAMED as BEAT_MISSING:%s (%r)" % (absent, g["failed"]))
    check(sum(1 for x in g["failed"] if x.startswith("BEAT_MISSING:")) == 1,
          "WW-03: exactly ONE named missing beat, no summary count (%r)" % (g["failed"],))

# ---- WW-11: judge-path gate-removal and delivery-boundary tests ------------

def _inspect_source(fn):
    try:
        import inspect
        return inspect.getsource(fn)
    except Exception:
        return ""


def _story_gate_wired():
    if SD is None or not hasattr(SD, "judge_take"):
        return False, "song_dispatch.judge_take is not present"
    if "check_returned_story" not in _inspect_source(SD.judge_take):
        return False, "check_returned_story is not yet called from judge_take (WW-08 lands with its own package)"
    return True, ""


def test_ww11_judge_path_gate_removal_breaks_the_suite():
    """WW-08/WW-11: deleting the story-gate invocation from judge_take must break
    the suite. Until the wiring lands this is UNDETERMINED -- never a pass."""
    wired, why = _story_gate_wired()
    if not gate(wired, "WW-11 gate-removal", why):
        return
    import song_contract as _SCTmod
    take = {"segments": [{"delivery": "sung", "start": 0.0, "end": 30.0, "source": "measured"}],
            "aligned_words": [], "duration_s": 58.0, "first_sung_s": 30.0}
    plan = {"delivered_s": 58, "style_id": "rnb-flow", "sheet_text": "", "hook_plan": {}}
    original = getattr(_SCTmod, "check_returned_story", None)
    try:
        _SCTmod.check_returned_story = lambda *a, **k: {"verdict": "PASS", "reasons": []}
        kept = SD.judge_take(take, plan, "", "", None, "rnb-flow", "")
    finally:
        if original is not None:
            _SCTmod.check_returned_story = original
    check("story_coverage" in (kept.get("gates") or {})
          or "story_coverage" in (kept.get("flagged") or [])
          or "story_coverage" in (kept.get("failed") or []),
          "WW-11: the story gate is in the take judge's gate set (removal would drop it)")


def test_ww11_delivery_boundary_refuses_a_non_pass_take():
    """WW-18/WW-11: the delivery path must refuse a take whose required gates did
    not all PASS. Until the delivery-level block lands this is UNDETERMINED."""
    if not gate(SC is not None and hasattr(SC, "deliver_choices"),
                "WW-11 delivery boundary", "song_choices.deliver_choices is not present"):
        return
    src = _inspect_source(SC.deliver_choices) + _inspect_source(getattr(SC, "record_pick", lambda: None))
    if "gates" not in src and "verdict" not in src.replace("FAILED", ""):
        undetermined("WW-11 delivery boundary",
                     "the delivery path does not yet consult the required gate set (WW-18 lands with its own package)")
        return
    bad = {"status": "FLAG", "variant": {"id": "v1"}, "take": {"path": "/tmp/x.mp3"},
           "receipts": [], "gates": {"story": {"verdict": "UNMEASURED"}}}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            SC.deliver_choices([bad], tmp, os.path.join(tmp, "d"), send=lambda *a: None)
        except Exception as e:
            check(True, "WW-11: a take with an unmeasured required gate is refused (%s)"
                  % type(e).__name__)
        else:
            check(False, "WW-11: the delivery path offered a take with an unmeasured gate")


# ---- WW-11: the release-level parity check --------------------------------

def _tree_hash(root):
    lines = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            with open(p, "rb") as f:
                lines.append("%s  %s" % (hashlib.sha256(f.read()).hexdigest(), rel))
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest(), sorted(lines)


def parity_check(canonical_core, twin_core, pinned_revision=None, twin_revision=None):
    """The release-level parity check (WW-11): the same shared core scope must be
    byte-identical between the two copies. A missing canonical source -- a missing
    twin, or a twin that has not recorded the revision it mirrored -- is
    UNDETERMINED, never a release PASS."""
    if not canonical_core or not os.path.isdir(canonical_core):
        return {"status": "UNDETERMINED", "detail": "canonical core absent",
                "canonical": canonical_core}
    if not twin_core or not os.path.isdir(twin_core):
        return {"status": "UNDETERMINED", "detail": "twin core absent", "twin": twin_core}
    if pinned_revision is None or twin_revision is None:
        return {"status": "UNDETERMINED",
                "detail": "the twin has not recorded the revision it mirrored"}
    if str(pinned_revision) != str(twin_revision):
        return {"status": "UNDETERMINED",
                "detail": "the twin pinned a different revision (%s != %s)"
                          % (twin_revision, pinned_revision)}
    ch, cl = _tree_hash(canonical_core)
    th, tl = _tree_hash(twin_core)
    cset = {ln.split("  ", 1)[1] for ln in cl}
    tset = {ln.split("  ", 1)[1] for ln in tl}
    if cset != tset:
        return {"status": "FAIL", "detail": "shared core scope differs",
                "only_canonical": sorted(cset - tset), "only_twin": sorted(tset - cset),
                "canonical_hash": ch, "twin_hash": th}
    if ch != th:
        return {"status": "FAIL", "detail": "shared core bytes differ",
                "canonical_hash": ch, "twin_hash": th}
    return {"status": "PASS", "detail": "shared core is byte-identical",
            "canonical_hash": ch, "twin_hash": th}


def test_ww11_release_parity_is_undetermined_when_a_source_is_missing():
    """WW-11: a missing canonical source (or twin), or a twin that has not
    recorded the revision it mirrored, is UNDETERMINED -- NEVER a release PASS.
    The check bites when the pins agree and the bytes differ."""
    twin = os.environ.get("DSAF_TWIN_CORE") or os.path.expanduser(
        "~/.claude/skills/drama-song-ad-factory/scripts/core")
    res = parity_check(CORE, twin, os.environ.get("DSAF_PINNED_REVISION"),
                       os.environ.get("DSAF_TWIN_PINNED_REVISION"))
    if res["status"] != "PASS":
        undetermined("WW-11 parity", "%s -- UNDETERMINED, not a release pass" % res["detail"])
    else:
        check(True, "WW-11: the shared core scope is byte-identical between the two copies")
    # deterministic controls: missing source -> UNDETERMINED; pinned + differing -> FAIL
    missing = parity_check(os.path.join(CORE, "no-such-dir"), twin, "R", "R")
    check(missing["status"] == "UNDETERMINED",
          "WW-11: a missing canonical source is UNDETERMINED, never a release PASS")
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = (os.path.join(tmp, n) for n in ("a", "b", "c"))
        for d in (a, b, c):
            os.makedirs(d)
        for d in (a, b):
            with open(os.path.join(d, "x.py"), "w", encoding="utf-8") as f:
                f.write("x = 1\n")
        with open(os.path.join(c, "x.py"), "w", encoding="utf-8") as f:
            f.write("x = 2\n")
        check(parity_check(a, b, "R", "R")["status"] == "PASS",
              "WW-11: byte-identical copies at the SAME pinned revision PASS")
        check(parity_check(a, c, "R", "R")["status"] == "FAIL",
              "WW-11: differing bytes at the same pinned revision FAIL")
        check(parity_check(a, b, "R", "R2")["status"] == "UNDETERMINED",
              "WW-11: a twin pinned to a different revision is UNDETERMINED")


# ---- WW-19: the import audit of the six referenced module paths ------------

SIX_MODULE_PATHS = [
    "scripts/core/music_qc/rap_check.py",
    "scripts/core/music_qc/pace_change.py",
    "scripts/core/music_qc/test_wwfix_u1.py",
    "scripts/core/story_coverage/story_coverage.py",
    "scripts/core/story_coverage/__init__.py",
    "scripts/core/song_choices/overlap.py",
]
OWNED_HERE = {
    "scripts/core/music_qc/pace_change.py",
    "scripts/core/music_qc/test_wwfix_u1.py",
    "scripts/core/song_choices/overlap.py",
}
#: Built by the OTHER concurrent packages of THIS SAME unit; absent here means
#: NOT-YET-PUBLISHED (UNDETERMINED), not ABSENT.
NOT_YET_PUBLISHED = {
    "scripts/core/music_qc/rap_check.py",
    "scripts/core/story_coverage/story_coverage.py",
    "scripts/core/story_coverage/__init__.py",
}


def import_audit(core_dir, not_yet_published=None):
    """WW-19: audit the six referenced module paths. PRESENT / NOT-YET-PUBLISHED
    (UNDETERMINED) / ABSENT (a failure). Absent is distinguished from
    not-yet-published, and neither is ever reported as PASS."""
    nyp = NOT_YET_PUBLISHED if not_yet_published is None else not_yet_published
    rows = []
    for rel in SIX_MODULE_PATHS:
        rel_from_core = rel[len("scripts/core/"):]
        if os.path.exists(os.path.join(core_dir, rel_from_core)):
            state = "PRESENT"
        elif rel in nyp:
            state = "NOT_YET_PUBLISHED"
        else:
            state = "ABSENT"
        rows.append({"path": rel, "state": state})
    counts = {s: sum(1 for r in rows if r["state"] == s)
              for s in ("PRESENT", "NOT_YET_PUBLISHED", "ABSENT")}
    return {"rows": rows, "counts": counts,
            "verdict": "FAIL" if counts["ABSENT"] else "DETERMINED"}


def test_ww19_import_audit_reports_absent_vs_not_yet_published():
    audit = import_audit(CORE)
    print("   WW-19 import audit on this tree: %r" % (audit["counts"],))
    check(audit["counts"]["ABSENT"] == 0,
          "WW-19: no referenced module is ABSENT on this tree (%r)" % (audit["counts"],))
    check(audit["counts"]["PRESENT"] >= 3,
          "WW-19: this package's three owned modules are PRESENT (%r)" % (audit["counts"],))
    # WW-19 fail-closed control, re-based at build time. Pull request 1844 asserted
    # "with no not-yet-published allowance the audit FAILS closed" against ITS base,
    # where three of the six referenced modules did not exist yet. WWFIXPIN-U1 has
    # since landed music_qc/rap_check.py, story_coverage/story_coverage.py and
    # story_coverage/__init__.py on main, so this tree can no longer observe ABSENT
    # with the real core -- the premise, not the rule, changed. The control runs the
    # audit over an EMPTY core dir instead, which exercises the same fail-closed rule
    # deterministically: with no allowance all six are ABSENT and the audit FAILS,
    # and the not-yet-published allowance excuses exactly its own three.
    with tempfile.TemporaryDirectory() as tmp:
        strict = import_audit(tmp, not_yet_published=set())
        check(strict["verdict"] == "FAIL"
              and strict["counts"]["ABSENT"] == len(SIX_MODULE_PATHS),
              "WW-19: with no not-yet-published allowance the audit FAILS closed (%r)"
              % (strict["counts"],))
        excused = import_audit(tmp, not_yet_published=NOT_YET_PUBLISHED)
        check(excused["verdict"] == "FAIL"
              and excused["counts"]["NOT_YET_PUBLISHED"] == len(NOT_YET_PUBLISHED)
              and excused["counts"]["ABSENT"] == len(SIX_MODULE_PATHS) - len(NOT_YET_PUBLISHED),
              "WW-19: the not-yet-published allowance excuses exactly its own three (%r)"
              % (excused["counts"],))


# ---- WW-20: the version is read live, never from a PR body -----------------

def version_check(skill_root, live_version):
    """WW-20: the written version must be strictly ABOVE the version read live
    from main at build time. No live value read -> UNDETERMINED."""
    path = os.path.join(skill_root, "skill-version.txt")
    try:
        with open(path, encoding="utf-8") as f:
            written = f.read().strip()
    except OSError:
        return {"status": "UNDETERMINED", "detail": "skill-version.txt not found"}
    if not live_version:
        return {"status": "UNDETERMINED", "detail": "no live version read at build time",
                "written": written}

    def _parts(v):
        return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())

    return {"status": "PASS" if _parts(written) > _parts(live_version) else "FAIL",
            "written": written, "live": live_version}


def test_ww20_version_is_read_live_and_strictly_above():
    live = os.environ.get("DSAF_LIVE_SKILL_VERSION")
    res = version_check(SKILL_ROOT, live)
    if res["status"] == "UNDETERMINED":
        undetermined("WW-20 live version",
                     "%s -- set DSAF_LIVE_SKILL_VERSION to prove the bump" % res["detail"])
        return
    check(res["status"] == "PASS",
          "WW-20: %s is strictly above the live %s" % (res["written"], res["live"]))


# <<< WWB-U22 BLOCK START -- WW-22: Ordered approved-story-line matching >>>
# WW-22 (WW-22 "Ordered approved-story-line matching", WW-ROUND3-FIX-PLAN.md):
# normalize the approved words, RETAIN REPEATS and require ORDERED matching
# rather than set membership; carry the EXACT approved opening line into the
# request/evidence context. The delivered ONSET on an exported take stays audio
# gate D2's measurement -- nothing in this block claims a measured onset.
#
# No numeric threshold is introduced here: the only number used is
# story_coverage.PLOT_LINE_MIN_WORDS (4), which the base already pins and this
# unit does not move. PROPOSED-and-unchanged, never attributed to Trevor.

#: The WW-22 fixture, verbatim from the plan's gate: an approved opening line of
#: four real words and the four observed shapes the matcher must sort.
WW22_APPROVED = ["i", "cooked", "for", "two"]

#: A production-shaped sheet whose opening PLOT line IS that approved line.
WW22_SHEET = "\n".join([
    "[Verse 1 (rap): rhythmic rap on the beat, tight metered flow, clear diction]",
    "I cooked for two",
])


def _ww22_rows(words, start=4.0, step=0.4):
    return [{"word": w, "startS": start + i * step, "endS": start + i * step + 0.3}
            for i, w in enumerate(words)]


def test_ww22_ordered_match_accepts_the_approved_line_in_order():
    """KNOWN-GOOD CONTROL FIRST: the approved words, in order, match."""
    m = SV.ordered_match(WW22_APPROVED, "I cooked for two")
    check(m["matched"] is True and m["coverage"] == 1.0 and m["approved_n"] == 4,
          "WW-22: 'I cooked for two' matches the approved line IN ORDER (%.2f)"
          % m["coverage"])
    check(m["refusal"] == "" and m["ordered"] is True and m["repeats_kept"] is True,
          "WW-22: an in-order match refuses nothing and reports the ordered rule")
    # the same line read from the sheet, through the production reader
    check(SV.plot_lines_from_sheet(WW22_SHEET) == [WW22_APPROVED],
          "WW-22: the sheet's approved opening line reads back as the exact "
          "ordered words %r" % (WW22_APPROVED,))


def test_ww22_ordered_match_rejects_four_filler_tokens_and_reversed_words():
    """The plan's gate: four `I` tokens and reversed words are REFUSED.

    The multiset count this unit replaces is computed alongside, so the test
    shows the defect it closes rather than asserting an unprovable claim."""
    four = SV.ordered_match(WW22_APPROVED, ["i", "i", "i", "i"])
    check(four["matched"] is False and four["covered"] == 1,
          "WW-22: four `I` tokens do NOT match the approved line (covered %d/4)"
          % four["covered"])
    rev = SV.ordered_match(WW22_APPROVED, ["two", "for", "cooked", "i"])
    check(rev["matched"] is False and rev["covered"] == 1,
          "WW-22: reversed words do NOT match the approved line (covered %d/4) "
          "-- a Counter pool scored this 4/4" % rev["covered"])
    from collections import Counter
    pool = Counter(["two", "for", "cooked", "i"])
    old = sum(1 for w in WW22_APPROVED if pool[w] > 0)
    check(old == 4 and rev["covered"] == 1,
          "WW-22: the replaced multiset scored the reversed words %d/4 while the "
          "ordered matcher scores %d/4" % (old, rev["covered"]))


def test_ww22_vocables_never_match_an_approved_line():
    """A vocalise is not a story word, so it never covers an approved word."""
    m = SV.ordered_match(WW22_APPROVED, ["oo-o-o-o-o-oh", "la", "na", "mmm"])
    check(m["matched"] is False and m["covered"] == 0,
          "WW-22: vocables cover no approved word (covered %d/4)" % m["covered"])
    check(SV.words_of("Oo-o-o-o-o-oh, la-na") == ["la-na"] or
          SV.words_of("Oo-o-o-o-o-oh,") == [],
          "WW-22: the vocalise reader drops the vocable and keeps a real word")
    # the approved side refuses a SET: a vocabulary has no order to match against
    s = SV.ordered_match({"i", "cooked", "for", "two"}, "I cooked for two")
    check(s["matched"] is False and s["approved_n"] == 0,
          "WW-22: a set is REFUSED as the approved side (no invented order)")


def test_ww22_up_newline_token_remains_lexical():
    """The plan's gate: `up\\n\\n` remains lexical. Preserved, not newly won."""
    check(SV.is_lexical("up\n\n") is True,
          "WW-22: the token 'up\\n\\n' is still lexical (is_lexical)")
    check(SV._norm("up\n\n") == "up",
          "WW-22: its normalized form after the header/whitespace strip is 'up'")
    check(SV.words_of("up\n\n") == ["up"],
          "WW-22: words_of('up\\n\\n') is ['up'] -- the trailing break does not "
          "erase the token")
    check(SV.is_lexical(SV._tok({"word": "[Verse 1 (rap): tight]\\nI "}) ) is False
          and SV.words_of("I ") == ["i"],
          "WW-22: a lexical token AFTER a section header is preserved ('I ')")
    check(SV.is_lexical("Oo-oh,") is False,
          "WW-22: a punctuation-bearing vocalise is STILL not lexical")


def test_ww22_text_coverage_matches_in_order_not_by_pool():
    """The pre-generation text floor compares IN ORDER (WW-22).

    Base pins kept: 98/100 passes the 0.98 floor and 97/100 fails."""
    ok = SV.text_coverage_gate(["word"] * 100, ["word"] * 98)
    check(ok["verdict"] == "PASS" and ok["text_coverage"] == 0.98
          and ok["covered_n"] == 98 and ok["ordered"] is True
          and ok["matched_in_order"] is False,
          "WW-22: 98/100 still PASSES the 0.98 floor -- a floor, not a full "
          "match -- and is measured IN ORDER (covered %d/100)"
          % ok.get("covered_n", -1))
    check(SV.text_coverage_gate(["word"] * 100, ["word"] * 97)["verdict"] == "FAIL",
          "WW-22: 97/100 still FAILS the 0.98 floor")
    good = SV.text_coverage_gate(WW22_APPROVED, "I cooked for two")
    check(good["verdict"] == "PASS" and good["text_coverage"] == 1.0,
          "WW-22: the approved line present in order covers 100%% of the text")
    rev = SV.text_coverage_gate(WW22_APPROVED, "two for cooked i")
    check(rev["verdict"] == "FAIL" and rev["covered_n"] == 1,
          "WW-22: REVERSED words are refused by the text floor (covered %d/4)"
          % rev["covered_n"])
    four = SV.text_coverage_gate(WW22_APPROVED, ["i", "i", "i", "i"])
    check(four["verdict"] == "FAIL",
          "WW-22: four repeated filler tokens are refused by the text floor")
    voc = SV.text_coverage_gate(WW22_APPROVED, ["oo-o-o-o-o-oh"] * 8)
    check(voc["verdict"] == "FAIL",
          "WW-22: a wall of vocables is refused by the text floor")
    check(SV.text_coverage_gate({"i", "cooked"}, "i cooked")["reason_code"]
          == "NO_APPROVED_TEXT",
          "WW-22: a set on the approved side is UNAVAILABLE, never a pass")


def test_ww22_exact_approved_opening_line_reaches_the_request_evidence_context():
    """The exact approved opening line is CARRIED, through the production path.

    The sheet text below is the SAME value song_dispatch.validate_request hands
    to song_contract.check_sheet at its `_SC.check_sheet(_lyrics_of(req), ...)`
    call site, so the carried line is the value the production path records
    before any spend."""
    from song_dispatch import song_dispatch as SD
    reqs = SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88, hook_plan=HOOK_PLAN)
    req = reqs[0][1]                           # [(variant, request)] x3
    sheet = SD._lyrics_of(req)                 # the production call site's argument
    SD.validate_request(req, style_id="rnb-flow", delivered_s=88)   # must not raise
    out = SCT.check_sheet(sheet, "rnb-flow", 88)
    want = SV.plot_lines_from_sheet(sheet)
    check(want and out["approved_opening"]["line"] == want[0],
          "WW-22: check_sheet carries the EXACT approved opening line %r"
          % (out["approved_opening"]["line"][:4],))
    check(out["approved_opening"]["ordered"] is True
          and out["approved_opening"]["repeats_kept"] is True
          and out["approved_opening"]["ordered_match"]["matched"] is True,
          "WW-22: the carried line is ordered, repeats kept, and matched IN ORDER "
          "against the sheet's own delivered words")
    check(out["approved_opening"]["line"] ==
          SV.approved_opening_line(sheet)["line"],
          "WW-22: the same exact line is returned by the public accessor")
    check(out["approved_opening"]["ordered_match"]["refusal"] == "",
          "WW-22: the carried match refuses nothing on a real sheet")


def test_ww22_production_story_gate_carries_and_enforces_the_ordered_line():
    """The ordered matcher is REACHABLE from the production judge path.

    song_dispatch.judge_take -> song_contract.check_returned_story ->
    story_coverage.judge_returned_take -> story_start_gate -> ordered_run_match.
    The known-good control runs first, then the two refusals."""
    good = SCT.check_returned_story(
        {"aligned_words": _ww22_rows(["i", "cooked", "for", "two"])},
        "rnb-flow", 88.0, WW22_SHEET, {"delivered_s": 88.0})
    gs = good["story_coverage"]["gates"]["story_start"]
    check(gs["verdict"] == "PASS" and gs["first_plot_line_s"] == 4.0
          and gs["failed"] == [],
          "WW-22 control: the approved line in order at 4.0 s PASSES story_start")
    check(gs["approved_opening_line"] == WW22_APPROVED
          and good["story_coverage"]["approved_opening_line"] == WW22_APPROVED,
          "WW-22: the exact approved opening line rides the production gate's "
          "context %r" % (gs["approved_opening_line"],))
    check(gs["delivered_onset_owner"] == "D2"
          and good["story_coverage"]["delivered_onset_owner"] == "D2",
          "WW-22: no onset is claimed here -- the delivered onset is D2's")
    four = SCT.check_returned_story(
        {"aligned_words": _ww22_rows(["i", "i", "i", "i"])},
        "rnb-flow", 88.0, WW22_SHEET, {"delivered_s": 88.0})
    gf = four["story_coverage"]["gates"]["story_start"]
    check(gf["verdict"] == "FAIL" and "NO_PLOT_LINE_SUNG" in gf["failed"],
          "WW-22: four `I` tokens are REFUSED by the production story gate (%r)"
          % (gf["failed"],))
    rev = SCT.check_returned_story(
        {"aligned_words": _ww22_rows(["two", "for", "cooked", "i"])},
        "rnb-flow", 88.0, WW22_SHEET, {"delivered_s": 88.0})
    gr = rev["story_coverage"]["gates"]["story_start"]
    check(gr["verdict"] == "FAIL" and "NO_PLOT_LINE_SUNG" in gr["failed"],
          "WW-22: reversed words are REFUSED by the production story gate (%r)"
          % (gr["failed"],))
    voc = SCT.check_returned_story(
        {"aligned_words": _ww22_rows(["oo-oh"] * 8)},
        "rnb-flow", 88.0, WW22_SHEET, {"delivered_s": 88.0})
    gv = voc["story_coverage"]["gates"]["story_start"]
    check(gv["verdict"] == "FAIL" and "NO_PLOT_LINE_SUNG" in gv["failed"],
          "WW-22: vocables alone are REFUSED by the production story gate (%r)"
          % (gv["failed"],))
    check(gr["approved_opening_line"] == WW22_APPROVED,
          "WW-22: the refusal still names the exact approved line it matched "
          "against")
    tc = SCT.check_returned_story(
        {"aligned_words": _ww22_rows(["i", "cooked", "for", "two"])},
        "rnb-flow", 88.0, WW22_SHEET, {"delivered_s": 88.0})
    check("text_coverage" in tc["story_coverage"]["gates"]
          and "story_start" in tc["story_coverage"]["gates"],
          "WW-22: both ordered guards are members of the production gate set")
    check(SCT.check_returned_story(
        {"aligned_words": _ww22_rows(["i", "cooked", "for", "two"])},
        "rnb-flow", 88.0, WW22_SHEET, {"delivered_s": 88.0})
        ["story_coverage"]["gates"]["text_coverage"]["verdict"] == "UNAVAILABLE",
        "WW-22: with no observed text the text floor is UNAVAILABLE (fail-closed), "
        "never a silent pass -- check_returned_story does not carry observed text")
    # judge_returned_take is the evaluator check_returned_story delegates to;
    # driven directly here so the ordered refusal is exercised on real inputs.
    jt = SV.judge_returned_take(
        {"aligned_words": _ww22_rows(["i", "cooked", "for", "two"]),
         "approved_words": "I cooked for two", "observed_words": "two for cooked i"},
        {"delivered_s": 88.0}, WW22_SHEET, 88.0)
    g = jt["gates"]["text_coverage"]
    check(g["verdict"] == "FAIL" and g["matched_in_order"] is False
          and g["covered_n"] == 1,
          "WW-22: the ordered text floor REFUSES reversed observed text "
          "(covered %d of %d)" % (g.get("covered_n", -1), g.get("approved_n", -1)))
    jt_ok = SV.judge_returned_take(
        {"aligned_words": _ww22_rows(["i", "cooked", "for", "two"]),
         "approved_words": "I cooked for two", "observed_words": "I cooked for two"},
        {"delivered_s": 88.0}, WW22_SHEET, 88.0)
    gok = jt_ok["gates"]["text_coverage"]
    check(gok["verdict"] == "PASS" and gok["matched_in_order"] is True,
          "WW-22 control: the same observed text IN ORDER passes the text floor")


def test_ww22_ordered_run_match_is_the_shared_primitive():
    """One ordered matcher: `first_plot_line_s` reads through `ordered_run_match`."""
    toks = ["i", "cooked", "for", "two"]
    check(SV.ordered_run_match([WW22_APPROVED], toks, min_words=4) == 0,
          "WW-22: ordered_run_match finds the run at index 0 for the ordered line")
    check(SV.ordered_run_match([WW22_APPROVED], ["two", "for", "cooked", "i"],
                               min_words=4) is None,
          "WW-22: ordered_run_match finds NO run for reversed words")
    check(SV.ordered_run_match([WW22_APPROVED], ["i", "i", "i", "i"],
                               min_words=4) is None,
          "WW-22: ordered_run_match finds NO run for four filler tokens")
    check(SV.ordered_run_match([WW22_APPROVED], ["x", "i", "cooked", "for", "two"],
                               min_words=4) == 1,
          "WW-22: the run is located at its true offset (index 1)")
    check(SV.ordered_run_match([WW22_APPROVED], ["i", "cooked", "for"],
                               min_words=4) is None,
          "WW-22: a 3-word run cannot satisfy the 4-word line floor")
    rows = _ww22_rows(["x", "i", "cooked", "for", "two"])
    check(SV.first_plot_line_s(rows, [WW22_APPROVED]) == 4.4,
          "WW-22: first_plot_line_s maps the shared matcher's index to seconds "
          "(4.4 s)")

# <<< WWB-U22 BLOCK END >>>
# ==== WW-24: measured-only evidence provenance (WWB-U24) ====================
#
# WW-24 validates the INPUTS the five delivered-audio results (D1..D5) are built
# from: PLANNED or STRETCHED timestamps never become returned-audio
# measurements. It measures no audio and claims no audio-quality outcome, so it
# adds NO sixth audio gate. One delimited block; functions prefixed test_ww24_.
# Every numeric threshold here is a NEW ACCEPTANCE RULE, not a measured limit.

import timing_guard as TG                        # noqa: E402  (WW-24 boundary)
import spoken_share.spoken_share as SS          # noqa: E402  (WW-24 runtime helper)

WW24_DIGEST = "a" * 64


def _ww24_segments(D):
    return [{"delivery": "sung", "start": 0.0, "end": D, "source": "measured"}]


def _ww24_good(D=40.0, digest=WW24_DIGEST, **over):
    ev = {"schema": "blackceo.measured-evidence/v1", "source": "measured",
          "export_digest": digest, "actual_duration_s": D,
          "detector": "singing_detector", "detector_version": "2.0.0",
          "stem_id": "stem-1", "alignment": {"words": []},
          "segments": _ww24_segments(D),
          "trusted_context": {"source": "pipeline", "tool": "singing_detector",
                              "tool_version": "2.0.0",
                              "measured_at": "2026-10-11T00:00:00Z"}}
    ev.update(over)
    return ev


def _ww24_with_evidence(binding, ev):
    """The five carried results, each bound to the take, each carrying ``ev``."""
    out = _ww21_results(binding)
    for rec in out.values():
        rec["evidence"] = dict(ev)
    return out


def test_ww24_a_known_good_control_passes():
    """POSITIVE CONTROL, before any negative: a complete measured-evidence
    record is admitted, and the production boundary advances it at zero spend."""
    good = _ww24_good()
    rcpt = TG.check_measured_evidence(good)
    print("  WW-24 known-good control: verdict=%r reason=%r" % (rcpt["verdict"], rcpt["reason_code"]))
    check(rcpt["verdict"] == "PASS" and rcpt["blocked"] is False and rcpt["purchases"] == 0,
          "WW-24: the known-good measured-evidence control PASSES")
    with tempfile.TemporaryDirectory() as tmp:
        b = _ww21_binding(tmp)
        ev = _ww24_good(digest=b["export_digest"])
        out = SD.accept_audio_results(_ww24_with_evidence(b, ev), b)
        print("  WW-24 production boundary on the control: verdict=%r blocked_by=%r"
              % (out["verdict"], out["blocked_by"][:1]))
        check(out["verdict"] == "PASS" and out["purchases"] == 0,
              "WW-24: the production boundary advances the known-good evidence")


def test_ww24_b_no_sixth_audio_gate_is_added():
    """WW-24 measures no audio. The five delivered-audio gate names, and the
    boundary's own claim, are unchanged."""
    check(SD.AUDIO_RESULTS == ("D1", "D2", "D3", "D4", "D5") and SD._MIN_AUDIO_RESULTS == 5,
          "WW-24: the five delivered-audio results are unchanged (no sixth gate)")
    check(TG.check_measured_evidence(_ww24_good())["measures_no_audio"] is True,
          "WW-24: the provenance boundary declares it measures no audio")


def test_ww24_c_zero_gap_stretched_plan_blocks():
    """A PLAN stretched to fill [0, D] with zero gaps is still a plan."""
    ev = _ww24_good()
    ev["source"] = "stretched"
    for s in ev["segments"]:
        s["source"] = "stretched"
    reasons = TG.measured_evidence_reasons(ev)
    print("  WW-24 zero-gap stretched plan -> %s" % (reasons[:1],))
    check(reasons and reasons[0].startswith("PLANNED_TIMESTAMPS"),
          "WW-24: a zero-gap stretched plan BLOCKS (PLANNED_TIMESTAMPS)")


def test_ww24_d_duplicate_runtime_blocks():
    """A doubled timeline (measured + annotations over the same audio) is refused."""
    ev = _ww24_good()
    ev["segments"] = [{"delivery": "sung", "start": 0.0, "end": 40.0, "source": "measured"},
                      {"delivery": "sung", "start": 0.0, "end": 40.0, "source": "measured"}]
    reasons = TG.measured_evidence_reasons(ev)
    print("  WW-24 duplicate runtime -> %s" % (reasons[:1],))
    check(reasons and reasons[0].startswith("DUPLICATE_RUNTIME"),
          "WW-24: a duplicate runtime BLOCKS (DUPLICATE_RUNTIME)")
    ev2 = _ww24_good()
    ev2["segments"] = []
    ev2["segment_seconds_total"] = 80.0
    r2 = TG.measured_evidence_reasons(ev2)
    check(r2 and any(x.startswith("DUPLICATE_RUNTIME") for x in r2),
          "WW-24: segment seconds above the measured runtime BLOCK (DUPLICATE_RUNTIME)")


def test_ww24_e_wrong_audio_blocks():
    """The evidence digest must match the take being advanced."""
    with tempfile.TemporaryDirectory() as tmp:
        b = _ww21_binding(tmp)
        ev = _ww24_good(digest="b" * 64)
        reasons = TG.measured_evidence_reasons(ev, binding=b)
        print("  WW-24 wrong audio -> %s" % (reasons[:1],))
        check(any(x.startswith("WRONG_AUDIO") for x in reasons),
              "WW-24: evidence measured against another export BLOCKS (WRONG_AUDIO)")
        out = SD.accept_audio_results(_ww24_with_evidence(b, ev), b)
        check(out["verdict"] != "PASS" and out["purchases"] == 0,
              "WW-24: the production boundary BLOCKS a wrong-audio receipt")


def test_ww24_f_fabricated_receipt_blocks():
    """A HAND-SET source="measured" label is not provenance."""
    for label, ev in (
            ("hand-set source only", {"source": "measured"}),
            ("source + digest, no artifacts", {"source": "measured",
                                               "export_digest": WW24_DIGEST,
                                               "actual_duration_s": 40.0}),
            ("source + artifacts, no trusted context",
             dict(_ww24_good(), trusted_context=None)),
            ("source + context with a manual label",
             _ww24_good(trusted_context={"source": "manual", "tool": "x",
                                         "tool_version": "1", "measured_at": "now"})),
            ("a bare string standing in for the record", "measured")):
        rcpt = TG.check_measured_evidence(ev) if isinstance(ev, dict) else \
            {"verdict": "FAIL", "reasons": TG.measured_evidence_reasons(ev)}
        print("  WW-24 fabricated receipt [%s] -> %s" % (label, (rcpt["reasons"] or ["<none>"])[0]))
        check(rcpt["verdict"] != "PASS",
              "WW-24: a fabricated receipt BLOCKS [%s]" % label)


def test_ww24_g_boundary_is_wired_and_load_bearing():
    """THE DEAD-GUARD PROOF. Drive the REAL production writer and boundary with a
    fabricated receipt, print the value at the call site, then REMOVE the gate
    invocation and show the same fixture flips to PASS."""
    fabricated = {"source": "measured", "actual_duration_s": 40.0}
    with tempfile.TemporaryDirectory() as tmp:
        run = os.path.join(tmp, "run")
        b = _ww21_binding(tmp)
        rec = SD.record_acceptance(run, "polished-modern", b,
                                   _ww24_with_evidence(b, fabricated))
        print("  WW-24 production writer record_acceptance -> verdict=%r reason=%s"
              % (rec["verdict"], (rec["blocked_by"] or ["<none>"])[0]))
        check(rec["verdict"] != "PASS" and rec["purchases"] == 0,
              "WW-24: record_acceptance BLOCKS a fabricated provenance receipt")
        check(SD.acceptance_from_run(run)["allowed"] is False,
              "WW-24: a run whose acceptance record carries fabricated evidence BLOCKS")
        # remove the gate invocation: swap the validator for a permissive stub
        saved = SD._TG.measured_evidence_reasons
        SD._TG.measured_evidence_reasons = lambda *a, **k: []
        try:
            out = SD.accept_audio_results(_ww24_with_evidence(b, fabricated), b)
            print("  WW-24 gate invocation REMOVED -> verdict=%r" % out["verdict"])
            check(out["verdict"] == "PASS",
                  "WW-24: removing the gate invocation lets the fabricated receipt PASS "
                  "(the guard is load-bearing, not dead)")
        finally:
            SD._TG.measured_evidence_reasons = saved
        back = SD.accept_audio_results(_ww24_with_evidence(b, fabricated), b)
        check(back["verdict"] != "PASS",
              "WW-24: with the gate restored the fabricated receipt BLOCKS again")


def test_ww24_h_script_report_separates_figures():
    """The script report carries the lexical estimate, the music-only allowance
    and the runtime under SEPARATE labels; an inflated 'seconds of words' label
    is refused. Reached through the production judge seam."""
    rep = SV.script_report(50.416, 8.0)
    print("  WW-24 script report -> %r" % (rep["reason_code"],))
    check(rep["verdict"] == "PASS" and rep["lexical_estimate_s"] == 50.416
          and rep["music_only_allowance_s"] == 8.0 and rep["runtime_s"] == 58.416,
          "WW-24: lexical estimate, music-only allowance and runtime are separate")
    inflated = SV.script_report(50.416, 8.0, inflated_seconds_of_words=58.416)
    print("  WW-24 inflated label -> %r" % (inflated["reason_code"],))
    check(inflated["verdict"] == "FAIL"
          and inflated["reason_code"] == "INFLATED_SECONDS_OF_WORDS",
          "WW-24: the inflated 'seconds of words' label is REFUSED")
    # the production seam (song_contract -> judge_returned_take) writes it
    plan = {"delivered_s": 58, "words": {"total": 120}, "intro_outro_s": 8.0,
            "beats_u16": len(LF.STORY_ARC_U16)}
    out = SV.judge_returned_take({"aligned_words": [], "duration_s": 58}, plan, "", 58)
    report = out.get("script_report")
    print("  WW-24 judge_returned_take report keys -> %r"
          % (sorted(report or {})[:6],))
    check(isinstance(report, dict) and "lexical_estimate_s" in report
          and "music_only_allowance_s" in report and "runtime_s" in report,
          "WW-24: the production judge seam emits the separate script report")


def test_ww24_i_word_annotations_never_add_runtime():
    """Word annotations (source="aligned"/"annotation") are timing evidence over
    the returned audio; they never ADD physical runtime. The WW-04 one-timeline
    repair refuses a doubled denominator."""
    D = 40.0
    segs = [{"delivery": "sung", "start": 0.0, "end": 20.0, "source": "measured"},
            {"delivery": "spoken", "start": 20.0, "end": 40.0, "source": "measured"}]
    check(SS.measured_runtime_s(segs, D) == D,
          "WW-24: the measured duration IS the physical runtime, never the sum")
    doubled = segs + [{"delivery": "sung", "start": 0.0, "end": 40.0, "source": "aligned"}]
    try:
        SS.measured_runtime_s(doubled, D)
        check(False, "WW-24: a doubled (measured + annotations) runtime was accepted")
    except SS.SpokenShareError as e:
        print("  WW-24 doubled runtime refused -> %s" % e.code)
        check(e.code == "TIMELINE_NOT_DISJOINT",
              "WW-24: word annotations over the same audio BLOCK (doubled runtime)")
    try:
        SS.measured_runtime_s(segs, None)
        check(False, "WW-24: a plan with no measured duration was accepted as runtime")
    except SS.SpokenShareError as e:
        check(e.code == "MISSING_ACTUAL_DURATION",
              "WW-24: no measured duration BLOCKS (a plan is not physical runtime)")
# ==== WW-25: copy-first archive (WWC-U25) ===================================
#
# WW-25 copy-first archive. The EXISTING shipping writer is
# song_choices.deliver_choices (the production publish step reached through
# fan_in and the factory's music stage): it ffmpeg-copies the approved takes
# into <delivery>/SONG-CHOICES/ and rewrites README.txt and state.json, so a
# re-run REPLACES those outputs. There is NO pre-existing archive helper in
# skill 75 (resolved from disk: zero ``archive`` symbols anywhere under
# 75-drama-song-ad-factory/scripts/, and no such module in this repo's git
# history for skill 75) -- so the copy-first archive lives ON that shipping
# writer, never in a new parallel module. The historical defective
# qualification/.../WW-011-lane/build_restart2.py archive_replaced()
# (os.remove on an existing archive then shutil.move) is EVIDENCE of the defect,
# never the shipping destination. One delimited block; functions prefixed
# test_ww25_. PROPOSED: the archive basename ``published`` and the -2/-3
# collision bump are NEW ACCEPTANCE RULES added by WW-25, not a measured limit
# and never a number Trevor set.
#
# Deleted-original recovery remains UNVERIFIED: this unit proves COPY-FIRST
# preservation of originals and prior archives, never that a deleted original
# can be recreated.

WW25_RECEIPT = {"schema": "ww.constituent-evidence/1", "accepted": True}

def _ww25_name(r):
    """The published file name deliver_choices builds for a result (the same
    _safe(label) rule the shipping writer uses)."""
    return SC._safe("%d - %s (%s)" % (r["n"], r["variant"]["label"],
                                      r["variant"]["description"])) + ".mp3"

def _ww25_results(tmp):
    out = []
    for i, v in enumerate(("polished-modern", "warm-live-band", "cinematic-strings"), 1):
        p = os.path.join(tmp, "takes", "%s.mp3" % v)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(("approved take bytes for %s" % v).encode("utf-8"))
        out.append({"n": i, "variant": {"id": v, "label": v.upper(), "description": "d"},
                    "status": "PASS", "attempt": 1, "attempts": 1, "receipts": [],
                    "receipt": dict(WW25_RECEIPT),
                    "take": {"audio_path": p, "duration_s": 58.0}})
    return out

def _ww25_runner():
    """A fake ffmpeg: copy the -i source to the destination the argv names, the
    way the real publish writes the titled file."""
    def run(argv):
        src = argv[argv.index("-i") + 1]
        dst = argv[-1]
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as f:
            data = f.read()
        with open(dst, "wb") as f:
            f.write(data)
    return run

def test_ww25_known_good_control_copies_verifies_then_publishes():
    """POSITIVE CONTROL, before any negative. The shipping writer publishes the
    three versions AND makes a fresh archive whose every copied hash equals its
    source; the originals are copied, never deleted or moved."""
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        res = _ww25_results(tmp)
        SC.deliver_choices(res, deliv, run, runner=_ww25_runner(), target="1",
                           send=lambda *a: None)
        folder = os.path.join(deliv, "SONG-CHOICES")
        published = sorted(f for f in os.listdir(folder) if f.endswith(".mp3"))
        check(published == sorted(_ww25_name(r) for r in res),
              "WW-25: the known-good control publishes the three version files")
        root = os.path.join(run, "song-choices", SC.ARCHIVE_DIRNAME)
        dirs = sorted(os.listdir(root))
        check(dirs == ["published"],
              "WW-25: the copy-first archive is exactly one new folder (%r)" % (dirs,))
        receipt = json.load(open(os.path.join(root, "published", "archive-receipt.json"),
                                 encoding="utf-8"))
        check(receipt["complete"] is True and len(receipt["files"]) == 3,
              "WW-25: the archive receipt is complete for every copied file")
        by_name = {_ww25_name(r): r["take"]["audio_path"] for r in res}
        for row in receipt["files"]:
            src = by_name.get(row["name"])
            check(src is not None and row["sha256"] == SC._sha256_file(src),
                  "WW-25: the copied hash matches its source for %s" % row["name"])
        check(all(os.path.isfile(r["take"]["audio_path"]) for r in res),
              "WW-25: the originals were COPIED, never deleted or moved")
        print("  WW-25 known-good control: archive=%s files=%d"
              % (dirs[0], len(receipt["files"])))

def test_ww25_copy_failure_publishes_nothing_and_preserves_both_sides():
    """A copy fault through the REAL delivery path refuses BEFORE publish: no
    version file, every original hash unchanged, the prior archive unchanged."""
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        res = _ww25_results(tmp)
        before = {r["take"]["audio_path"]: SC._sha256_file(r["take"]["audio_path"]) for r in res}
        prior = os.path.join(run, "song-choices", SC.ARCHIVE_DIRNAME, "published")
        os.makedirs(prior, exist_ok=True)
        old = os.path.join(prior, "old.mp3")
        with open(old, "wb") as f:
            f.write(b"a prior archive that must never be touched")
        prior_sha = SC._sha256_file(old)
        orig = SC.shutil.copy2
        def _boom(src, dst, *a, **k):
            raise OSError("disk full (injected copy fault)")
        SC.shutil.copy2 = _boom
        try:
            SC.deliver_choices(res, deliv, run, runner=_ww25_runner(), target="1",
                               send=lambda *a: None)
        except SC.ChoiceError as e:
            print("  WW-25 copy failure refused: %s" % e)
            check("copy failed" in str(e) and "nothing was published" in str(e),
                  "WW-25: the copy fault refuses with the intended reason")
        else:
            check(False, "WW-25: a copy fault did not refuse the publish")
        finally:
            SC.shutil.copy2 = orig
        check(not os.path.isdir(os.path.join(deliv, "SONG-CHOICES")),
              "WW-25: a copy fault publishes no version file")
        check(before == {p: SC._sha256_file(p) for p in before},
              "WW-25: every original hash is unchanged after a copy fault")
        check(SC._sha256_file(old) == prior_sha,
              "WW-25: the prior archive is byte-unchanged after a copy fault")

def test_ww25_missing_source_refuses_before_publish():
    """A vanished original refuses through the real path (the plan's copy
    failure): nothing is published and the surviving originals are intact."""
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        res = _ww25_results(tmp)
        os.remove(res[1]["take"]["audio_path"])
        keep = [r["take"]["audio_path"] for r in (res[0], res[2])]
        before = {p: SC._sha256_file(p) for p in keep}
        try:
            SC.deliver_choices(res, deliv, run, runner=_ww25_runner(), target="1",
                               send=lambda *a: None)
        except SC.ChoiceError as e:
            print("  WW-25 missing source refused: %s" % e)
            check("source missing" in str(e), "WW-25: a missing source refuses before publish")
        else:
            check(False, "WW-25: a missing source did not refuse")
        check(not os.path.isdir(os.path.join(deliv, "SONG-CHOICES")),
              "WW-25: a missing source publishes no version file")
        check(before == {p: SC._sha256_file(p) for p in before},
              "WW-25: the surviving originals are unchanged")

def test_ww25_noncolliding_dir_bumps_on_collision():
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "published")
        os.makedirs(base)
        check(SC._noncolliding_dir(base) == base + "-2",
              "WW-25: a folder collision bumps the archive name")
        os.makedirs(base + "-2")
        check(SC._noncolliding_dir(base) == base + "-3",
              "WW-25: a second collision bumps again")

def test_ww25_collision_and_rerun_never_overwrite_a_prior_archive():
    """A re-run makes a NEW noncolliding archive; an earlier archive is never
    overwritten to make the re-run succeed."""
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        res = _ww25_results(tmp)
        SC.deliver_choices(res, deliv, run, runner=_ww25_runner(), target="1",
                           send=lambda *a: None)
        root = os.path.join(run, "song-choices", SC.ARCHIVE_DIRNAME)
        first = os.path.join(root, "published", "archive-receipt.json")
        first_sha = SC._sha256_file(first)
        SC.deliver_choices(res, deliv, run, runner=_ww25_runner(), target="1",
                           send=lambda *a: None)
        dirs = sorted(os.listdir(root))
        check(dirs == ["published", "published-2"],
              "WW-25: a re-run makes a NEW noncolliding archive (%r)" % (dirs,))
        check(SC._sha256_file(first) == first_sha,
              "WW-25: the prior archive is byte-unchanged after a re-run")
        print("  WW-25 re-run archives: %r" % (dirs,))

def test_ww25_the_archive_guard_is_reachable_from_the_delivery_path():
    """The guard is the CALL inside deliver_choices, not a hand-built helper.
    Show deliver_choices calls it with the REAL take sources (printed), then
    that removing the call publishes with no archive -- the guard is load-bearing."""
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        res = _ww25_results(tmp)
        seen = {}
        orig = SC.archive_before_publish
        def _rec(rd, items, **kw):
            seen["items"] = list(items)
            return orig(rd, items, **kw)
        SC.archive_before_publish = _rec
        try:
            SC.deliver_choices(res, deliv, run, runner=_ww25_runner(), target="1",
                               send=lambda *a: None)
        finally:
            SC.archive_before_publish = orig
        got = sorted(s["source"] for s in seen.get("items", []))
        want = sorted(r["take"]["audio_path"] for r in res)
        print("  WW-25 call site sources: %r" % (got,))
        check(got == want,
              "WW-25: deliver_choices calls the archive with the REAL take sources")
        with tempfile.TemporaryDirectory() as tmp2:
            run2, deliv2 = os.path.join(tmp2, "run"), os.path.join(tmp2, "D")
            res2 = _ww25_results(tmp2)
            SC.archive_before_publish = lambda *a, **k: None      # MUTATION: remove the guard
            try:
                SC.deliver_choices(res2, deliv2, run2, runner=_ww25_runner(), target="1",
                                   send=lambda *a: None)
            finally:
                SC.archive_before_publish = orig
            check(not os.path.isdir(os.path.join(run2, "song-choices", SC.ARCHIVE_DIRNAME)),
                  "WW-25: with the guard call removed no archive is made (the guard is load-bearing)")

def test_ww25_no_parallel_archive_module_was_created():
    """WW-25 fixes the EXISTING shipping writer; it never invents a second
    module. Fail if any *archive*.py file appears under the core tree."""
    hits = []
    for root, _dirs, files in os.walk(CORE):
        if "__pycache__" in root:
            continue
        hits += [os.path.join(root, f) for f in files
                 if f.lower().endswith(".py") and "archive" in f.lower()]
    check(hits == [], "WW-25: no parallel archive module was created (%r)" % (hits,))
    check(hasattr(SC, "archive_before_publish") and hasattr(SC, "deliver_choices"),
          "WW-25: the archive lives ON the existing shipping writer")

def test_ww25_deleted_original_recovery_is_unverified():
    undetermined("WW-25 deleted-original recovery",
                 "WW-25 proves COPY-FIRST preservation (originals copied, never deleted; "
                 "prior archives never overwritten); it does NOT prove a deleted original "
                 "can be recovered. Reported UNVERIFIED, never a pass.")

# =====================================================================
# WWC-U26 (WW-26) -- three COMPLETE briefs, including the upbeat option.
# Replaces the shared request plus a short appended ``clause`` with three
# independently authored complete briefs, and gates the EXACT serialized
# request["input"]["style"] before any generation. ONE delimited block.
# =====================================================================

_W26_CAP = getattr(R, "suno_recipe", R).SUNO_STYLE_FIELD_MAX

def _w26_reqs():
    return SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88, hook_plan=HOOK_PLAN)

def _w26_shared_core_rows(base_brief):
    """Three rows that are the DEFECT this unit replaces: one shared core and a
    short appended suffix per variant. Complete brief fields everywhere except
    the trailing arrangement, so only the identifiers differ. ``base_brief`` is
    passed in so this helper never re-enters the patched production path."""
    base = dict(base_brief)
    rows = []
    for vid in ("a", "b", "c"):
        brief = dict(base, arrangement="variant %s arrangement line here" % vid)
        rows.append({"id": vid, "label": vid.upper(), "genre": "rnb-flow",
                     "role": "polished", "upbeat": vid == "b", "brief": brief})
    return rows

def test_ww26_three_complete_briefs_in_the_serialized_payload():
    """A positive control first: the production path yields three DISTINCT
    styles, each carrying all ten directions, exactly ONE upbeat, no genre
    substitution, under the cap -- and no shared-core-plus-suffix shape."""
    rows = _w26_reqs()
    check(len(rows) == 3, "WW-26: three variant requests are built")
    word = getattr(R, "suno_recipe", R).vocal_gender_word("f")
    styles, up = [], 0
    for v, rq in rows:
        style = rq["input"]["style"]
        styles.append(style)
        for f in SC._BRIEF_FIELDS:
            need = str(v["brief"][f]).replace("{gender}", word)
            check(need in style, "WW-26: %s style carries the %s direction"
                  % (v["id"], SC._DIRECTION_LABEL[f]))
        check(v["genre"] == "rnb-flow", "WW-26: %s keeps the chosen genre (no substitution)" % v["id"])
        if v.get("upbeat"):
            up += 1
        check(len(style) <= _W26_CAP, "WW-26: %s style is under the %d-char cap" % (v["id"], _W26_CAP))
    check(up == 1, "WW-26: exactly ONE variant is the explicit upbeat role")
    check(len(set(styles)) == 3, "WW-26: the three serialized styles are DISTINCT")
    print("  WW-26 common prefix of the three real styles: %d chars (a shared core would be hundreds)"
          % SC._common_prefix_len(styles))
    check(SC._common_prefix_len(styles) < SC.SHARED_CORE_PREFIX_MIN,
          "WW-26: the real briefs carry no shared core (common prefix %d < %d)"
          % (SC._common_prefix_len(styles), SC.SHARED_CORE_PREFIX_MIN))

def test_ww26_require_three_checks_treatments_not_identifiers():
    """_require_three must check COMPLETE treatments, not identifiers only."""
    rows = _w26_reqs()
    check(SC._require_three(rows, key=lambda r: r[0]["id"]) is rows,
          "WW-26 control: three complete briefs pass _require_three")
    import copy
    thin = copy.deepcopy(rows)
    thin[1][0]["brief"]["scene_words"] = ""
    try:
        SC._require_three(thin, key=lambda r: r[0]["id"])
    except SC.ChoiceError as e:
        check("MISSING_DIRECTION" in str(e) and "immediate scene words" in str(e),
              "WW-26: an incomplete treatment is refused (got %s)" % str(e)[:70])
    else:
        check(False, "WW-26: _require_three accepted an incomplete treatment")
    no_up = copy.deepcopy(rows)
    for v, _ in no_up:
        v["upbeat"] = False
    try:
        SC._require_three(no_up, key=lambda r: r[0]["id"])
    except SC.ChoiceError as e:
        check("upbeat" in str(e), "WW-26: no upbeat role is refused")
    else:
        check(False, "WW-26: _require_three accepted zero upbeat roles")

def test_ww26_serialized_payload_refuses_missing_shared_and_overflow():
    """The gate reads the EXACT serialized input.style after every transform."""
    rows = _w26_reqs()
    check(SC._check_three_briefs(rows, "f") is rows,
          "WW-26 control: the real serialized payloads pass the gate")
    import copy
    dropped = copy.deepcopy(rows)
    f = SC._BRIEF_FIELDS[0]
    need = dropped[0][0]["brief"][f]
    dropped[0][1]["input"]["style"] = dropped[0][1]["input"]["style"].replace(need + " ", "")
    try:
        SC._check_three_briefs(dropped, "f")
    except SC.ChoiceError as e:
        check("MISSING_DIRECTION" in str(e), "WW-26: a dropped direction refuses (%s)" % str(e)[:60])
    else:
        check(False, "WW-26: the gate accepted a style missing its groove direction")
    for f, label in (("vocals", "cast/vocals"), ("hook", "rap-vs-sung hook"),
                     ("problem_shift", "problem shift"), ("solution_shift", "solution shift")):
        hole = copy.deepcopy(rows)
        need = str(hole[2][0]["brief"][f]).replace("{gender}", "female")
        hole[2][1]["input"]["style"] = hole[2][1]["input"]["style"].replace(need + " ", "")
        try:
            SC._check_three_briefs(hole, "f")
        except SC.ChoiceError as e:
            check("MISSING_DIRECTION" in str(e) and label in str(e),
                  "WW-26: a dropped %s direction refuses on the serialized payload" % label)
        else:
            check(False, "WW-26: the gate accepted a style missing the %s direction" % label)
    no_up = copy.deepcopy(rows)
    for v, _ in no_up:
        v["upbeat"] = False
    try:
        SC._check_three_briefs(no_up, "f")
    except SC.ChoiceError as e:
        check("UPBEAT_DIRECTION" in str(e), "WW-26: a payload set with no upbeat role refuses")
    else:
        check(False, "WW-26: the gate accepted a payload set with no upbeat direction")
    # shared core plus suffix: three near-identical serialized styles
    core = "shared core text " * 20
    shared = [({"id": vid, "genre": "rnb-flow", "upbeat": vid == "b",
                "brief": {k: "same %s here" % k for k in SC._BRIEF_FIELDS}},
               {"input": {"style": core + "suffix %s" % vid}}) for vid in ("a", "b", "c")]
    try:
        SC._check_three_briefs(shared, "f")
    except SC.ChoiceError as e:
        check("SHARED_CORE_PLUS_SUFFIX" in str(e),
              "WW-26: a shared-core-plus-suffix payload refuses (%s)" % str(e)[:60])
    else:
        check(False, "WW-26: the gate accepted a shared core plus a short suffix")
    # final overflow on the serialized style
    big = copy.deepcopy(rows)
    big[0][1]["input"]["style"] = big[0][1]["input"]["style"] + (" x" * 300)
    try:
        SC._check_three_briefs(big, "f")
    except SC.ChoiceError as e:
        check("STYLE_TOO_LONG" in str(e), "WW-26: a final over-cap style refuses (%s)" % str(e)[:60])
    else:
        check(False, "WW-26: the gate accepted an over-cap serialized style")

def test_ww26_shared_core_guard_is_reachable_from_the_production_path():
    """WIRING PROOF. The refusal must come from the REAL gate on the REAL
    build_requests path: with a shared-core table, build_requests refuses; with
    the gate call removed, the same build_requests no longer refuses."""
    import copy
    base_brief = copy.deepcopy(_w26_reqs()[0][0]["brief"])
    real_variants, real_gate = SC.variants_for, SC._check_three_briefs
    try:
        SC.variants_for = lambda style_id: _w26_shared_core_rows(base_brief)
        try:
            SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88, hook_plan=HOOK_PLAN)
        except SC.ChoiceError as e:
            check("SHARED_CORE_PLUS_SUFFIX" in str(e),
                  "WW-26: build_requests refuses a shared core plus suffix (%s)" % str(e)[:70])
        else:
            check(False, "WW-26: build_requests accepted a shared-core table")
        # guard-removal: stub the gate and the SAME call no longer refuses
        SC._check_three_briefs = lambda rows, vocal_gender="f": rows
        built = SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88, hook_plan=HOOK_PLAN)
        check(len(built) == 3,
              "WW-26 gate-removal: with _check_three_briefs stubbed the same call builds (the guard is load-bearing)")
    finally:
        SC.variants_for, SC._check_three_briefs = real_variants, real_gate

def test_ww26_pace_clause_stays_last_under_the_cap_on_all_three():
    """WW-07 boundary kept: the approved pace clause is LAST within the cap on
    ALL THREE variants, after the ending clause and the variant's own arrangement."""
    pace = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove"}
    rows = SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88,
                            hook_plan=HOOK_PLAN, pace_plan=pace)
    ending = getattr(R, "suno_recipe", R)._EQ.STYLE_ENDING
    drop = pace["drop"]
    for v, rq in rows:
        style = rq["input"]["style"]
        check(style.index(ending) < style.index(drop) < style.index(pace["return"]),
              "WW-26: %s APPROVED pace clause is last, after the ending" % v["id"])
        check(style.index(v["clause"].rstrip(".")) < style.index(drop),
              "WW-26: %s own arrangement clause sits before the approved pace clause" % v["id"])
        check(style.rstrip().rstrip(".").endswith(pace["return"].rstrip(".")),
              "WW-26: %s serialized style ENDS with the return" % v["id"])
        check(len(style) <= _W26_CAP,
              "WW-26: %s style stays under the cap with the pace clause (%d)" % (v["id"], len(style)))

# <<< WWC-U27 BLOCK START -- WW-27: Ensemble character bible and distinct voices >>>
#
# WW-27 (2026-10-11): the CAST DECISION precedes drafting; multiple characters
# are the DEFAULT and the count follows the conflict. Every character carries a
# full treatment and a Suno voice of register / timbre / articulation /
# delivery / emotional progression / version treatment. A villain or foil
# SPEAKS and receives a consequential reply. The sheet's speakers must be
# DECLARED, the FINAL style may not command one voice for an ensemble, and the
# take stays ONE full-song track. Audio gate D5 alone confirms the delivered
# voices -- this block measures no audio and adds NO sixth audio gate.
#
# Every numeric threshold here is a NEW ACCEPTANCE RULE, not a measured limit
# and never a number Trevor set.

import math                                     # noqa: E402  (WW-27 timbre fixtures)

try:
    import music_director as MD                  # noqa: E402  (WW-27 production seam)
except Exception:                                # pragma: no cover
    MD = None

_R27 = getattr(R, "suno_recipe", R)         # noqa: E402  (WW-27: the bare recipe module)
from character_bible import character_bible as CB          # noqa: E402  (WW-27 cast model)
from qc_voice_match import line_voice_fit as LVF           # noqa: E402  (WW-27 identity, D5 input)
from lyric_writer import lyric_writer as LW                # noqa: E402  (WW-27 drafting seam)

WW27_SV_MARA = {"register": "warm alto", "timbre": "bright and open",
                "articulation": "clear clipped consonants", "delivery": "belted and forward",
                "emotional_progression": "guarded to soaring",
                "version_treatment": "lead take, doubled on the hook"}
WW27_SV_JONAS = {"register": "low bass-baritone", "timbre": "gravel and edge",
                 "articulation": "hard clipped consonants", "delivery": "metered and cold",
                 "emotional_progression": "cold to breaking",
                 "version_treatment": "lead take, dry and close"}
WW27_SV_FOIL = {"register": "mid tenor", "timbre": "reedy and thin",
                "articulation": "soft consonants", "delivery": "plain and plainspoken",
                "emotional_progression": "nervous to certain",
                "version_treatment": "answering take, slightly behind the beat"}


def _ww27_char(name, role, gender, sv, **over):
    rec = {"name": name, "role": role, "want": "to be free of the door",
           "wound": "a door closed on them young",
           "relationships": "the other characters in this scene",
           "consequential_action": "walks out and burns the list",
           "voice": "speaks plain and low", "voice_direction": dict(sv),
           "gender": gender}
    rec.update(over)
    return rec


def _ww27_cast(**over):
    """The KNOWN-GOOD ensemble: a protagonist, a speaking villain and a foil."""
    c = {"cast_mode": "ensemble",
         "characters": [_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
                        _ww27_char("Jonas", "villain", "male", WW27_SV_JONAS),
                        _ww27_char("Tobin", "foil", "male", WW27_SV_FOIL)]}
    c.update(over)
    return c


WW27_HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
WW27_HOOK_PLAN = {"true_at_beat": "the_world"}


def _ww27_sheet(opponent="Jonas", reply="Mara"):
    """The R&B Flow 88 s sheet with its voiced sections TAGGED to the cast.

    Same words and same shape as the fixture the rest of this battery proves at
    88 s, so it clears the sung-share, per-verse rap and hook floors while the
    traded reply (the villain's rap verse, then the protagonist's) is really in
    the script."""
    return [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
            {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
            {"tag": "Verse Mara", "delivery": "sung",
             "lines": ["And I rise above the pa-a-ain,",
                       "Through the dark I walk alo-o-one,"]},
            {"tag": "Hook 1", "delivery": "sung", "lines": WW27_HOOK},
            {"tag": "Verse Mara", "delivery": "sung",
             "lines": ["One seed of truth made me stro-o-ong,", "I hold the light I found,",
                       "I walk out free,", "I rise a-a-above,", "I am more than this,",
                       "I am he-e-ere,", "I am not lost,", "I am still standing ta-a-all,"]},
            {"tag": "Hook 2", "delivery": "sung", "lines": WW27_HOOK},
            {"tag": "Hook 3", "delivery": "sung", "lines": WW27_HOOK},
            {"tag": "Hook 4", "delivery": "sung", "lines": WW27_HOOK},
            {"tag": "Rap Verse %s" % opponent, "delivery": "rap",
             "lines": ["Backup shoes, backup jacket, but no backup plan,",
                       "So I count what I make and not what they take today,"]},
            {"tag": "Rap Verse %s" % reply, "delivery": "rap",
             "lines": ["Every door they closed I opened with my own two hands,",
                       "And I keep walking toward the morning light now,"]}]


def _ww27_reqs(cast=None, sheet=None, **kw):
    """The LIVE production build: song_choices.build_requests -> the real
    suno_recipe.createTask builder, one request per arrangement variant."""
    if cast is None:
        cast = _ww27_cast()
    return SC.build_requests("rnb-flow", sheet if sheet is not None else _ww27_sheet(),
                             CLIENT, "T", 88, hook_plan=WW27_HOOK_PLAN, cast=cast, **kw)


def _ww27_stub_cast_module(reasons=()):
    """A stand-in for character_bible.character_bible whose gate never refuses --
    how a test removes the real gate call without editing production code."""
    class _S(object):
        @staticmethod
        def check_cast(*a, **k):
            return {"reasons": list(reasons), "verdict": "FAIL" if reasons else "PASS"}
    return _S


def _ww27_sine(f, secs=0.4, amp=0.5, rate=16000):
    n = int(rate * secs)
    return {"samples": [amp * math.sin(2.0 * math.pi * f * i / rate) for i in range(n)],
            "sample_rate": rate}


def _ww27_rich(f, overtones=((2.0, 0.6),), secs=0.4, amp=0.5, rate=16000):
    """One voice: a fundamental plus its overtones -- its TIMBRE, at any pitch."""
    n = int(rate * secs)
    out = []
    for i in range(n):
        x = math.sin(2.0 * math.pi * f * i / rate)
        for mult, level in overtones:
            x += level * math.sin(2.0 * math.pi * mult * f * i / rate)
        out.append(amp * x)
    return {"samples": out, "sample_rate": rate}


def test_ww27_a_known_good_ensemble_control_passes():
    """POSITIVE CONTROL, first. The cast decision defaults to an ensemble, the
    complete cast passes, and the LIVE production builder accepts it at zero
    spend while still refusing every one of the negatives below."""
    d = CB.cast_decision({"characters": [_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA)]})
    print("  WW-27 cast decision -> mode=%r default=%r min=%d"
          % (d["mode"], d["default"], d["min_characters"]))
    check(d["mode"] == "ensemble" and d["default"] is True and d["min_characters"] == 2,
          "WW-27: multiple characters are the DEFAULT; the count follows the conflict")
    rc = CB.check_cast(_ww27_cast(), sheet_text=R.render_lyrics(_ww27_sheet(), "rnb-flow"),
                       style_text="warm ensemble r&b, both voices in call and response")
    print("  WW-27 known-good cast -> verdict=%r code=%r traded=%r"
          % (rc["verdict"], rc["reason_code"], rc["traded_replies"]))
    check(rc["verdict"] == "PASS" and rc["purchases"] == 0 and rc["measures_no_audio"] is True,
          "WW-27: the complete ensemble cast PASSES with zero purchases")
    check(rc["contrast"] == 3 and rc["characters_n"] == 3,
          "WW-27: three contrasting vocal directions are recorded (%d)" % rc["contrast"])
    check(bool(rc["traded_replies"]) and rc["traded_replies"]["opponent"].lower() == "jonas"
          and rc["traded_replies"]["reply"].lower() == "mara",
          "WW-27: the villain speaks and the protagonist answers it (traded replies)")
    reqs = _ww27_reqs()
    check(len(reqs) == 3 and all(r[1]["input"]["lyrics"] for r in reqs),
          "WW-27: the live production builder builds all three variants with the cast")


def test_ww27_b_no_sixth_audio_gate_is_added():
    """WW-27 measures no audio and claims no audio-quality outcome: the five
    delivered-audio gate names are unchanged and the cast receipt says so."""
    if not gate(SD is not None, "WW-27 no-sixth-gate", "song_dispatch absent"):
        return
    check(SD.AUDIO_RESULTS == ("D1", "D2", "D3", "D4", "D5") and SD._MIN_AUDIO_RESULTS == 5,
          "WW-27: the five delivered-audio results are unchanged (no sixth gate)")
    check(CB.check_cast(_ww27_cast())["measures_no_audio"] is True,
          "WW-27: the cast gate declares it measures no audio")
    check(not [g for g in SD.GATES if "cast" in g or "ensemble" in g or "speaker" in g],
          "WW-27: no cast/ensemble/speaker gate was added to the delivered-audio set")


def test_ww27_c_the_cast_decision_precedes_drafting():
    """The cast decision runs BEFORE the lines are judged: lyric_writer refuses a
    declared-but-broken cast with the fields named, and never reports coverage
    for lines it never reached."""
    good = LW.validate_lyrics(
        [{"line_id": "v1", "text": "I walk out free"}, {"line_id": "v2", "text": "I hold the light"}],
        _ww27_cast())
    print("  WW-27 lyric verdict with a complete cast -> %r cast=%r"
          % (good["outcome"], (good.get("cast_decision") or {}).get("reason_code")))
    check(good["cast_decision"] is not None
          and good["cast_decision"]["reason_code"] == "ENSEMBLE_CAST_OK",
          "WW-27: a complete cast is decided FIRST and rides every lyric verdict")
    broken = LW.validate_lyrics(
        [{"line_id": "v1", "text": "I walk out free"}],
        {"cast_mode": "ensemble",
         "characters": [{"name": "Mara", "role": "protagonist"}]})
    first = broken["errors"][0] if broken["errors"] else {}
    print("  WW-27 lyric verdict with a broken cast -> %r %r"
          % (broken["outcome"], first.get("error")))
    details = " ".join(e.get("detail", "") for e in broken["errors"])
    check(broken["outcome"] == "rejected"
          and broken["reason_code"] in (CB.CODE_CAST_NOT_ENSEMBLE, CB.CODE_CAST_INCOMPLETE)
          and broken["coverage"]["covered"] == 0,
          "WW-27: drafting is REFUSED before a line is judged (%r)" % (broken["reason_code"],))
    check(CB.CODE_CAST_INCOMPLETE in details and "want" in details and "voice" in details,
          "WW-27: the refusal names the missing treatment fields")
    plain = LW.validate_lyrics([{"line_id": "v1", "text": "I walk out free"}], {"product_name": ""})
    check(plain.get("cast_decision") is None and plain["outcome"] == "ok",
          "WW-27: a brief that declares no cast is judged exactly as before")
    legacy = LW.validate_lyrics(
        [{"line_id": "v1", "text": "I walk out free"}],
        {"characters": ["Mara"], "packet_lines": ["I walk out free"]})
    check(legacy.get("cast_decision") is None and legacy["outcome"] == "ok",
          "WW-27: a H7-style brief whose `characters` are names only is judged as before "
          "(the gate fires on a WW-27 cast declaration, never on that list)")


def test_ww27_d_incomplete_and_single_character_casts_refuse():
    """Every cast-record refusal, each named: the ensemble floor, an incomplete
    treatment, an incomplete Suno voice, an unknown role and a shared voice."""
    one = {"characters": [_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA)]}
    check(CB.cast_reasons(one)[0].startswith(CB.CODE_CAST_NOT_ENSEMBLE),
          "WW-27: one character under the ensemble default refuses (CAST_NOT_ENSEMBLE)")
    thin = {"characters": [_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA, voice=None),
                           _ww27_char("Jonas", "villain", "male", WW27_SV_JONAS)]}
    check(any(r.startswith(CB.CODE_CAST_INCOMPLETE) and "voice" in r
              for r in CB.cast_reasons(thin)),
          "WW-27: a character missing its treatment refuses (CAST_INCOMPLETE)")
    novoice = {"characters": [_ww27_char("Mara", "protagonist", "female",
                                         {"register": "alto"}),
                              _ww27_char("Jonas", "villain", "male", WW27_SV_JONAS)]}
    r = CB.cast_reasons(novoice)
    print("  WW-27 thin Suno voice -> %r" % (r[0][:80],))
    check(any(x.startswith(CB.CODE_CAST_VOICE_INCOMPLETE)
              and "timbre" in x and "version_treatment" in x for x in r),
          "WW-27: an incomplete Suno voice names register/timbre/articulation/delivery/"
          "emotional_progression/version_treatment")
    unknown = {"characters": [_ww27_char("Mara", "hero", "female", WW27_SV_MARA),
                              _ww27_char("Jonas", "villain", "male", WW27_SV_JONAS)]}
    check(any(x.startswith(CB.CODE_CAST_ROLE_UNKNOWN) for x in CB.cast_reasons(unknown)),
          "WW-27: a role outside CAST_ROLES refuses (CAST_ROLE_UNKNOWN)")
    twin = {"characters": [_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
                           _ww27_char("Jonas", "villain", "male", WW27_SV_MARA)]}
    check(any(x.startswith(CB.CODE_CAST_VOICES_IDENTICAL)
              for x in CB.cast_reasons(twin, sheet_text=R.render_lyrics(_ww27_sheet(), "rnb-flow"))),
          "WW-27: two characters sharing ONE Suno voice direction refuse "
          "(CAST_VOICES_IDENTICAL -- no contrasting vocal directions)")


def test_ww27_e_undeclared_speaker_is_refused_reachable_from_check_sheet():
    """A bracket naming a character the cast does not hold is refused, and the
    refusal is REACHABLE from the production sheet contract."""
    sheet = R.render_lyrics(_ww27_sheet(), "rnb-flow")
    kade = sheet.replace("Jonas", "Kade")
    reasons = CB.cast_reasons(_ww27_cast(), sheet_text=kade)
    print("  WW-27 undeclared speaker -> %r" % (reasons[-1][:90],))
    check(any(x.startswith(CB.CODE_SPEAKER_UNDECLARED) and "kade" in x for x in reasons),
          "WW-27: an undeclared speaker in the script is REFUSED (SPEAKER_UNDECLARED)")
    out = SCT.check_sheet(sheet, "rnb-flow", 88, "ensemble r&b, both voices", cast=_ww27_cast())
    print("  WW-27 check_sheet cast receipt -> %r speakers=%r"
          % (out["cast"]["reason_code"], out["cast"]["speakers"]))
    check(out["cast"] is not None and out["cast"]["verdict"] == "PASS",
          "WW-27: the known-good cast is carried on check_sheet's own context")
    bad = SCT.check_sheet(kade, "rnb-flow", 88, "ensemble r&b", cast=_ww27_cast())
    check(bad["verdict"] == "FAIL"
          and any(CB.CODE_SPEAKER_UNDECLARED in r for r in bad["reasons"]),
          "WW-27: check_sheet REFUSES the undeclared speaker (the gate is reachable)")
    off = SCT.check_sheet(kade, "rnb-flow", 88, "ensemble r&b")
    check(off["cast"] is None and not any(CB.CODE_SPEAKER_UNDECLARED in r for r in off["reasons"]),
          "WW-27: with no cast declared the legacy sheet check is unchanged")


def test_ww27_f_villain_speaks_and_receives_a_consequential_reply():
    """The villain/foil rules: one must SPEAK and be ANSWERED; a NON-PERSON
    antagonist is permitted, but only with a speaking foil."""
    sheet = R.render_lyrics(_ww27_sheet(), "rnb-flow")
    check(bool(CB.traded_replies(CB.speaker_turns(sheet), ["Jonas"])),
          "WW-27 control: the script really trades a reply from the villain")
    silent = _ww27_cast(characters=[_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
                                    _ww27_char("Jonas", "villain", "male", WW27_SV_JONAS)])
    s2 = R.render_lyrics(_ww27_sheet(opponent="Mara", reply="Mara"), "rnb-flow")
    reasons = CB.cast_reasons(silent, sheet_text=s2)
    print("  WW-27 silent villain -> %r" % (reasons[0][:90],))
    check(any(x.startswith(CB.CODE_CAST_OPPONENT_SILENT) for x in reasons),
          "WW-27: a villain who never speaks is REFUSED (CAST_OPPONENT_SILENT)")
    no_reply = R.render_lyrics(_ww27_sheet(opponent="Jonas", reply="Jonas"), "rnb-flow")
    r2 = CB.cast_reasons(_ww27_cast(), sheet_text=no_reply)
    print("  WW-27 unanswered villain -> %r" % (r2[0][:100],))
    check(any(x.startswith(CB.CODE_CAST_NO_CONSEQUENTIAL_REPLY) for x in r2),
          "WW-27: a villain nobody answers is REFUSED (CAST_NO_CONSEQUENTIAL_REPLY)")
    nonperson = _ww27_cast(characters=[
        _ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
        _ww27_char("The Flood", "antagonist", None, WW27_SV_JONAS, person=False)])
    r3 = CB.cast_reasons(nonperson, sheet_text=sheet)
    print("  WW-27 non-person antagonist, no foil -> %r" % (r3[0][:90],))
    check(any(x.startswith(CB.CODE_CAST_NO_OPPOSING_VOICE) for x in r3),
          "WW-27: a NON-PERSON antagonist with no speaking foil is REFUSED")
    withfoil = _ww27_cast(characters=[
        _ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
        _ww27_char("The Flood", "antagonist", None, WW27_SV_JONAS, person=False),
        _ww27_char("Jonas", "villain", "male", WW27_SV_FOIL)])
    ok = CB.check_cast(withfoil, sheet_text=sheet)
    print("  WW-27 non-person antagonist WITH a speaking foil -> %r" % (ok["reason_code"],))
    check(ok["verdict"] == "PASS",
          "WW-27: a non-person antagonist IS permitted with a speaking foil")
    check(any(x.startswith(CB.CODE_CAST_NO_OPPOSING_VOICE)
              for x in CB.cast_reasons({"characters": [
                  _ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
                  _ww27_char("Tobin", "support", "male", WW27_SV_FOIL)]},
                  sheet_text=sheet)),
          "WW-27: an ensemble with NO villain or foil at all is REFUSED")


def test_ww27_g_the_final_serialized_payload_refuses_a_single_voice_ensemble_style():
    """The FIXED value the guard tests is read at the REAL call site: the FINAL
    ``request["input"]["style"]`` the provider would receive. An ensemble style
    commanding one voice refuses; removing the gate call stops the refusal."""
    req = _ww27_reqs()[0][1]
    style_ok = req["input"]["style"]
    print("  WW-27 final payload style tail -> %r" % (style_ok[-70:],))
    single = style_ok.rstrip() + " A single female voice."
    print("  WW-27 single-voice value the guard tests -> %r" % (single[-40:],))
    try:
        R.guard_request(single, req["input"]["lyrics"], "rnb-flow", CLIENT, 88,
                        hook_plan=WW27_HOOK_PLAN, cast=_ww27_cast())
        check(False, "WW-27: an ensemble style commanding a single voice was accepted")
    except R.RecipeError as e:
        print("  WW-27 style refusal -> %s" % (str(e)[:110],))
        check(CB.CODE_ENSEMBLE_SINGLE_VOICE_STYLE in str(e),
              "WW-27: the FINAL serialized style refuses (ENSEMBLE_SINGLE_VOICE_STYLE)")
    saved = _SCM._cast_model
    _SCM._cast_model = _ww27_stub_cast_module()
    try:
        R.guard_request(single, req["input"]["lyrics"], "rnb-flow", CLIENT, 88,
                        hook_plan=WW27_HOOK_PLAN, cast=_ww27_cast())
        leaked = ""
    except R.RecipeError as e:
        leaked = str(e)
    finally:
        _SCM._cast_model = saved
    print("  WW-27 gate removed from check_sheet -> %r" % (leaked[:80],))
    check(CB.CODE_ENSEMBLE_SINGLE_VOICE_STYLE not in leaked,
          "WW-27: removing the gate call removes the refusal (the guard is load-bearing)")
    back = SCT.check_sheet(req["input"]["lyrics"], "rnb-flow", 88, single, cast=_ww27_cast())
    check(back["verdict"] == "FAIL"
          and any(CB.CODE_ENSEMBLE_SINGLE_VOICE_STYLE in r for r in back["reasons"]),
          "WW-27: with the gate restored the single-voice style refuses again")


def test_ww27_h_the_exact_payload_carries_the_cast_and_the_traded_reply():
    """The exact serialized payload carries the developed cast: every voiced
    section names its character AND its delivery, so the traded reply is read
    from the payload's OWN lyrics -- and no provider field was invented."""
    req = _ww27_reqs()[0][1]
    payload = json.dumps(req, sort_keys=True)
    lyrics = req["input"]["lyrics"]
    turns = CB.speaker_turns(lyrics)
    trade = CB.traded_replies(turns, ["Jonas"])
    print("  WW-27 payload speakers -> %r traded=%r" % ([t["speaker"] for t in turns], trade))
    check(sorted({t["speaker"] for t in turns}) == ["jonas", "mara"],
          "WW-27: the serialized payload's lyrics name BOTH cast characters")
    check(bool(trade) and trade["opponent_lines"] > 0 and trade["reply_lines"] > 0,
          "WW-27: the traded reply is read from the payload's own lyric turns")
    check("[Rap Verse Jonas (rap): rhythmic rap" in lyrics
          and "[Verse Mara (sung):" in lyrics,
          "WW-27: each character's vocal direction rides its own payload tag")
    check("_cast" not in req
          and sorted(req) == ["_hook_plan", "_style_id", "callBackUrl", "endpoint",
                              "input", "model"],
          "WW-27: no provider field was invented -- the cast rides the script, not a new key")
    check("_cast" not in payload,
          "WW-27: the serialized payload carries no internal cast key")


def test_ww27_i_same_pitch_different_timbre_is_two_voices_and_a_pitch_shift_is_one():
    """D5's input, BEYOND PITCH. Fixture 1: the SAME pitch with different timbre
    is TWO identities. Fixture 2: a DIFFERENT pitch with the same timbre is ONE
    performer pitch-shifted, and is NOT a second voice."""
    a = LVF.identity_of(_ww27_sine(200.0))
    b = LVF.identity_of(_ww27_rich(200.0))
    c = LVF.identity_of(_ww27_rich(150.0))
    d = LVF.identity_of(_ww27_rich(300.0))
    print("  WW-27 same pitch/different timbre -> hz=%r/%r timbre=%r/%r"
          % (a["median_hz"], b["median_hz"], a["timbre"], b["timbre"]))
    check(a["median_hz"] == b["median_hz"] and LVF.distinct_identity(a, b),
          "WW-27: SAME PITCH with different timbre is TWO audible identities")
    print("  WW-27 different pitch/same identity -> hz=%r/%r sep=%r"
          % (c["median_hz"], d["median_hz"], LVF.timbre_separation(c, d)))
    check(c["median_hz"] != d["median_hz"] and not LVF.distinct_identity(c, d),
          "WW-27: a DIFFERENT PITCH with the same timbre is ONE identity, not two voices")
    check(LVF.timbre_separation(b, c) is not None and not LVF.distinct_identity(b, c),
          "WW-27: the same voice at another pitch reads the SAME profile (pitch-invariant)")
    rec = LVF.identity_receipt(
        [{"line_id": "l1", "onscreen": "Mara"}, {"line_id": "l2", "onscreen": "Jonas"}],
        {"mara": {"gender": "female"}, "jonas": {"gender": "male"}},
        {"l1": _ww27_rich(150.0), "l2": _ww27_rich(300.0)})
    print("  WW-27 identity receipt (pitch shift) -> %r %r"
          % (rec["outcome"], rec["reason_code"]))
    check(rec["outcome"] == "rejected" and rec["reason_code"] == LVF.CODE_SAME_IDENTITY_PITCH_SHIFT,
          "WW-27: two characters one pitch-shift apart are REFUSED as ONE identity")
    ok = LVF.identity_receipt(
        [{"line_id": "l1", "onscreen": "Mara"}, {"line_id": "l2", "onscreen": "Jonas"}],
        {"mara": {"gender": "female"}, "jonas": {"gender": "male"}},
        {"l1": _ww27_sine(200.0), "l2": _ww27_rich(200.0)})
    check(ok["outcome"] == "ok" and ok["identity_count"] == 2
          and ok["pitch_alone_is_not_identity"] is True,
          "WW-27: same pitch with different timbre PASSES the identity gate")


def test_ww27_j_one_full_song_track_and_no_stitched_voice_pack():
    """The take stays ONE full-song track: a stitched voice pack refuses."""
    rec = LVF.identity_receipt(
        [{"line_id": "l1", "onscreen": "Mara"}, {"line_id": "l2", "onscreen": "Jonas"}],
        {}, {"l1": _ww27_sine(200.0), "l2": _ww27_rich(200.0)}, tracks=2)
    print("  WW-27 stitched track count -> %r %r" % (rec["outcome"], rec["reason_code"]))
    check(rec["outcome"] == "rejected" and rec["reason_code"] == LVF.CODE_VOICE_PACK_STITCHED,
          "WW-27: a two-track take is REFUSED (VOICE_PACK_STITCHED)")
    sheet = R.render_lyrics(_ww27_sheet(), "rnb-flow")
    check(any(x.startswith(CB.CODE_VOICE_PACK_STITCHED)
              for x in CB.cast_reasons(_ww27_cast(), sheet_text=sheet, take={"tracks": 3})),
          "WW-27: the cast gate refuses a stitched pack on the take too")
    check(CB.check_cast(_ww27_cast(), sheet_text=sheet, take={"tracks": 1})["verdict"] == "PASS",
          "WW-27 control: one full-song track PASSES")


def test_ww27_k_the_cast_gate_is_reachable_from_the_live_builder_and_load_bearing():
    """The gate is REACHABLE from the live production builder, and removing its
    call stops the refusal. No cast passed -> the builder is unchanged."""
    good = _ww27_reqs()
    check(len(good) == 3, "WW-27 control: the live builder accepts the good cast (3 variants)")
    broken = {"characters": [_ww27_char("Mara", "protagonist", "female", WW27_SV_MARA)]}
    try:
        _ww27_reqs(cast=broken)
        check(False, "WW-27: the live builder accepted a single-character cast")
    except R.RecipeError as e:
        print("  WW-27 live builder refusal -> %s" % (str(e)[:100],))
        check(e.code == "CAST_REJECTED" and CB.CODE_CAST_NOT_ENSEMBLE in str(e),
              "WW-27: the LIVE builder refuses a broken cast before any request exists")
    saved = _R27._cast_model
    _R27._cast_model = _ww27_stub_cast_module()
    try:
        _ww27_reqs(cast=broken)
        leaked = True
    except Exception:
        leaked = False
    finally:
        _R27._cast_model = saved
    check(leaked, "WW-27: removing the builder's gate call lets the broken cast through "
                  "(the guard is load-bearing, not dead)")
    plain = SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 88, hook_plan=HOOK_PLAN)
    check(len(plain) == 3 and plain[0][1]["input"]["style"],
          "WW-27: with no cast passed the live builder is unchanged")


def test_ww27_l_base_boundaries_stay_intact():
    """WW-21's boundary, parse_lyrics' cue, the pace text LAST within the cap on
    all three variants, and the createTask contract's LEGACY_FLAT_CONTRACT."""
    if not gate(SD is not None, "WW-27 base boundaries", "song_dispatch absent"):
        return
    empty = SD._finish({})
    check(empty["verdict"] != "PASS" and empty["blocked_by"],
          "WW-27: WW-21's _finish({}) still BLOCKS an empty gate set")
    sheet_text = ("[Verse Mara (sung): smooth r&b melody, clear diction]\nI rise\n\n[End]\n")
    parsed = R.parse_lyrics(sheet_text)
    check(parsed and parsed[0].get("cue") == "smooth r&b melody, clear diction",
          "WW-27: parse_lyrics still stores the bracket cue under \"cue\"")
    order = {"drop": "half-time drop, thin drums",
             "return": "turn and rise back to the groove",
             "boundary_s": 20.0, "return_boundary_s": 60.0}
    _sr = getattr(R, "suno_recipe", R)
    pace = _sr.pace_clause(order)
    for variant, req in _ww27_reqs(pace_plan=order):
        style = req["input"]["style"]
        check(style.rstrip().endswith(pace.rstrip()) and len(style) <= _sr.SUNO_STYLE_FIELD_MAX,
              "WW-27: the pace text stays LAST within the %d-char cap (variant %s)"
              % (_sr.SUNO_STYLE_FIELD_MAX, variant["id"]))
    flat = {"endpoint": R.KIE_LEGACY_GENERATE_ENDPOINT, "prompt": "x", "style": "y"}
    errs = R.check_envelope(flat)
    check(errs and errs[0].startswith("LEGACY_FLAT_CONTRACT"),
          "WW-27: the retired flat payload is still REFUSED (LEGACY_FLAT_CONTRACT)")


def test_ww27_n_every_sheet_side_cast_refusal_reaches_check_sheet():
    """Every sheet/style-level cast refusal is REACHABLE from the production
    sheet contract, not only from a hand-built receipt."""
    good_sheet = R.render_lyrics(_ww27_sheet(), "rnb-flow")
    cases = [
        (CB.CODE_SPEAKER_UNDECLARED,
         _ww27_cast(), good_sheet.replace("Jonas", "Kade"), "ensemble r&b"),
        (CB.CODE_ENSEMBLE_SINGLE_VOICE_STYLE, _ww27_cast(), good_sheet,
         "ensemble r&b. A single female voice."),
        (CB.CODE_CAST_OPPONENT_SILENT, _ww27_cast(),
         R.render_lyrics(_ww27_sheet(opponent="Mara", reply="Mara"), "rnb-flow"),
         "ensemble r&b"),
        (CB.CODE_CAST_NO_CONSEQUENTIAL_REPLY, _ww27_cast(),
         R.render_lyrics(_ww27_sheet(opponent="Jonas", reply="Jonas"), "rnb-flow"),
         "ensemble r&b"),
        (CB.CODE_CAST_VOICES_IDENTICAL,
         {"cast_mode": "ensemble", "characters": [
             _ww27_char("Mara", "protagonist", "female", WW27_SV_MARA),
             _ww27_char("Jonas", "villain", "male", WW27_SV_MARA)]},
         good_sheet, "ensemble r&b"),
        (CB.CODE_CAST_INCOMPLETE,
         {"cast_mode": "ensemble", "characters": [
             _ww27_char("Mara", "protagonist", "female", WW27_SV_MARA, want=None),
             _ww27_char("Jonas", "villain", "male", WW27_SV_JONAS)]},
         good_sheet, "ensemble r&b"),
    ]
    for code, cast, sheet, style in cases:
        out = SCT.check_sheet(sheet, "rnb-flow", 88, style, cast=cast)
        hit = [r for r in out["reasons"] if r.startswith(code)]
        print("  WW-27 check_sheet reachability %-30s -> %s" % (code, bool(hit)))
        check(out["verdict"] == "FAIL" and bool(hit),
              "WW-27: %s is REACHABLE through song_contract.check_sheet" % code)


def test_ww27_m_the_production_director_seam_enforces_the_cast():
    """The other production builder (music_director.build_generate_request) runs
    the same gate, BEFORE anything is built and again on the final payload."""
    if not gate(MD is not None and hasattr(MD, "build_generate_request"), "WW-27 director seam",
                "music_director absent"):
        return
    sheet = _ww27_sheet()
    lyrics = R.render_lyrics(sheet, "rnb-flow")
    style = _R27.style_text("rnb-flow", sheet, "f")

    def build(**kw):
        return MD.build_generate_request(lyrics, style, "T", style_id="rnb-flow",
                                         client_text=CLIENT, length_s=88,
                                         hook_plan=WW27_HOOK_PLAN, **kw)

    try:
        req = build(cast=_ww27_cast())
        print("  WW-27 director payload -> style %d chars, rap tags %d"
              % (len(req["input"]["style"]), req["input"]["lyrics"].count("(rap)")))
        check(req["input"]["lyrics"].count("(rap)") == 2 and req["input"]["style"],
              "WW-27: the director builds the payload with the cast's script")
    except (ValueError, R.RecipeError) as e:
        check(False, "WW-27: the director refused the known-good cast (%s)" % (str(e)[:90],))
    try:
        build(cast={"characters": [{"name": "Mara", "role": "protagonist"}]})
        check(False, "WW-27: the director accepted a broken cast")
    except (ValueError, R.RecipeError) as e:
        print("  WW-27 director refusal -> %s" % (str(e)[:100],))
        check(CB.CODE_CAST_INCOMPLETE in str(e) or CB.CODE_CAST_NOT_ENSEMBLE in str(e),
              "WW-27: the director refuses the broken cast BEFORE any payload")
    try:
        check(bool(build()["input"]["lyrics"]),
              "WW-27: with no cast the director is unchanged")
    except (ValueError, R.RecipeError) as e:
        check(False, "WW-27: the director refused with no cast passed (%s)" % (str(e)[:90],))

# <<< WWC-U27 BLOCK END >>>
# =====================================================================
# WW-28 -- Causal plot and earned hook.
#
# New PROPOSED acceptance rules. The causal chain, the fiction/testimonial
# split, the reconstruction from the EXACT lyrics, the hook line vs the
# refrain and the closing commercial call are judged BEFORE budgeting, from
# the exact approved script -- no delivered-audio craft gate is added (D1-D5
# stay the only audio gates). Every guard below is fired through a
# production function (story_arc.validate_story, script_approval.check_
# script_approval, song_choices.build_requests) on a value the production
# path produces, never on a hand-built dictionary the run never constructs.
# =====================================================================

#: WW-28: load the gate module by PATH, so the battery never depends on a
#: package __init__ that exports a subset (SELF_APPROVAL is read off the module).
SAP = _load_path("script_approval/script_approval.py")

#: the exact approved lyrics: section tags, a cost line, an exchanged
#: reply, an earned hook and a closing that carries the commercial call.
WW28_LYRICS = """[Intro (spoken): no melody, cold open]
She watched the shop sign come down.

[Verse (sung): the wound]
I lost the door I painted years ago.

[Verse (rap): the turn]
Sam: did you ever count what they took?
Maya: every night, and then I built again.

[Hook (sung): the payoff]
I am not small

[Outro (spoken): no melody, book your assessment call]
Book your assessment call and start today.
"""

WW28_CAUSAL = {
    "scene": "the shop on Mercer street",
    "inciting_event": "the sign comes down",
    "opposing_action": "the landlord takes the door",
    "escalation": "she loses the second space too",
    "cost": "she lost the door she painted herself",
    "choice": "she rebuilds from the ledger",
    "product_mechanism": "the book walks her through the six steps",
    "consequence": "she opens the third space",
    "commercial_action": "Book your assessment call",
    "lyrics": WW28_LYRICS,
}


def _ww28_story(**over):
    """A complete causal story record, exactly as the production path reads
    creative/story.json. ``over`` overrides; ``causal_over`` patches the block."""
    causal_over = over.pop("causal_over", {})
    story = {"story_id": "ww28-causal-01", "beats": list(SA.BEATS), "product_reveal": 8,
             "hook": {"line": "I am not small", "refrain": "not small",
                      "declared_occurrences": 1},
             "scenes": [{"kind": "fiction", "text": "the sign comes down",
                         "cause": "the landlord calls the loan",
                         "effect": "she rebuilds from the ledger"}]}
    causal = dict(WW28_CAUSAL)
    causal.update(causal_over)
    story["causal"] = causal
    story.update(over)
    return story


def _ww28_causal_reason(story):
    r = SA.check_causal_story(story)
    return r["reason_code"], r["errors"][0]["detail"] if r["errors"] else ""


def test_ww28_causal_control_passes_then_every_field_is_required():
    """Known-good control FIRST, then each of the nine causal fields removed in
    turn must refuse with causal-incomplete, BEFORE budgeting."""
    if not gate(SA is not None, "WW-28 causal control", "story_arc did not load"):
        return
    good = SA.validate_story(_ww28_story())
    print("  WW-28 control: validate_story -> %r / %r" % (good["outcome"], good["reason_code"]))
    check(good["outcome"] == "ok", "WW-28: the complete causal story passes validate_story")
    assert SA.CAUSAL_FIELDS == ("scene", "inciting_event", "opposing_action", "escalation",
                                "cost", "choice", "product_mechanism", "consequence",
                                "commercial_action")
    for field in SA.CAUSAL_FIELDS:
        s = _ww28_story(causal_over={field: ""})
        rc, detail = _ww28_causal_reason(s)
        check(rc == "causal-incomplete" and field in detail,
              "WW-28: missing %s is refused (%s)" % (field, rc))
        r = SA.validate_story(s)
        check(r["outcome"] == "rejected" and r["reason_code"] == "causal-incomplete",
              "WW-28: validate_story refuses the story missing %s before budgeting" % field)


def test_ww28_fiction_is_separated_from_testimonial_fact():
    """A scene must declare fiction or testimonial; an undeclared kind is
    refused. A declared testimonial scene alongside fiction is allowed."""
    if not gate(SA is not None, "WW-28 fiction/testimonial", "story_arc did not load"):
        return
    s = _ww28_story(scenes=[{"text": "the shop", "cause": "a", "effect": "b"}])
    rc, _ = _ww28_causal_reason(s)
    check(rc == "scene-kind-undeclared", "WW-28: an undeclared scene kind is refused (%s)" % rc)
    s = _ww28_story(scenes=[{"kind": "FICTION", "text": "the shop", "cause": "a", "effect": "b"},
                            {"kind": "testimonial", "text": "the real second space",
                             "cause": "c", "effect": "d"}])
    check(SA.check_causal_story(s)["outcome"] == "ok",
          "WW-28: fiction and testimonial facts are judged together, each named")


def test_ww28_mood_board_and_causal_contradiction_are_refused():
    """A flat list of scenes with no causal link is a mood board, not a plot;
    and a closing that does not carry the declared commercial action is a
    causal contradiction between the story and the payload."""
    if not gate(SA is not None, "WW-28 mood board", "story_arc did not load"):
        return
    s = _ww28_story(scenes=[{"kind": "fiction", "text": "the shop"},
                            {"kind": "fiction", "text": "the door"}])
    rc, _ = _ww28_causal_reason(s)
    check(rc == "mood-board-plot", "WW-28: a mood-board plot is refused (%s)" % rc)
    s = _ww28_story(causal_over={"commercial_action": "Order your starter kit"})
    rc, detail = _ww28_causal_reason(s)
    check(rc == "causal-contradiction",
          "WW-28: a closing that lacks the declared action is refused (%s)" % rc)
    good = _ww28_story()
    check(SA.check_causal_story(good)["outcome"] == "ok",
          "WW-28: the matching closing is a positive control for the contradiction rule")


def test_ww28_maker_self_approval_is_refused_at_the_music_gate():
    """script_approval.check_script_approval -- called on the run_takes path
    before any generation -- refuses an approval the maker gave their own
    script, and accepts an independent one."""
    if not gate(SAP is not None, "WW-28 maker self-approval",
                "script_approval did not import"):
        return
    lyrics = "I am not small"
    sha = SAP.lyrics_sha(lyrics)
    self_approved = {"required": True, "status": "approved", "lyrics_sha": sha,
                     "maker": "Agnes", "approved_by": "agnes"}
    independent = dict(self_approved, approved_by="the client")
    legacy = {"required": True, "status": "approved", "lyrics_sha": sha}
    print("  WW-28 self-approval record: maker=%r approved_by=%r"
          % (self_approved["maker"], self_approved["approved_by"]))
    refusal = SAP.check_script_approval(self_approved, lyrics)
    check(bool(refusal) and refusal["reason_code"] == SAP.SELF_APPROVAL,
          "WW-28: maker self-approval is refused (%s)" % (refusal or {}).get("reason_code"))
    check(SAP.check_script_approval(independent, lyrics) is None,
          "WW-28: an independent approval passes (control)")
    check(SAP.check_script_approval(legacy, lyrics) is None,
          "WW-28: a record naming no maker keeps today's behaviour")
    # reachability: the music gate itself consults this function.
    if SD is not None and hasattr(SD, "run_takes"):
        check("check_script_approval" in _inspect_source(SD.run_takes),
              "WW-28: song_dispatch.run_takes consults check_script_approval (reachable)")


def test_ww28_hook_line_is_defined_before_counting_and_companions_cannot_double_it():
    """The EXACT hook line is counted, never the refrain or a companion line:
    two declared occurrences can never be reported as four."""
    if not gate(SA is not None, "WW-28 hook", "story_arc did not load"):
        return
    hook = {"line": "I am not small", "refrain": "not small", "declared_occurrences": 2}
    sub = ("[Hook (sung)]\nI am not small\nI am not small, I am strong\n\n"
           "[Hook (sung)]\nI am not small\nI am not small, I am strong\n\n[End]")
    counts = SA.count_hook_occurrences(sub, hook)
    print("  WW-28 hook counts: %r" % (counts,))
    check(counts["counted_exact"] == 2 and counts["counted_with_companions"] == 4,
          "WW-28: the exact hook line counts 2, companion lines would make 4")
    out = SA.check_hook_declaration(sub, hook)
    check(out["outcome"] == "rejected" and out["reason_code"] == "hook-companion-substitution",
          "WW-28: companion-line substitution is refused (%s)" % out["reason_code"])
    ok = ("[Hook (sung)]\nI am not small\n\n[Hook (sung)]\nI am not small\n\n[End]")
    check(SA.check_hook_declaration(ok, hook)["outcome"] == "ok",
          "WW-28: two real hook occurrences pass (control)")
    check(SA.check_hook_declaration(ok, {"refrain": "not small"})["reason_code"]
          == "hook-line-undefined",
          "WW-28: no exact hook line is refused before any counting")


def test_ww28_payload_closing_carries_the_approved_call_on_the_production_path():
    """song_choices.build_requests -- the production builder -- refuses a closing
    that promises but asks for nothing, and accepts one that carries the call."""
    if not gate(SC is not None and R is not None, "WW-28 payload closing",
                "song_choices/suno_recipe did not import"):
        return
    outro = {"tag": "Outro", "delivery": "spoken",
             "cue": "no melody, book your assessment call",
             "lines": ["Your life will change."]}
    sheet = list(SHEET_RNB) + [outro]
    print("  WW-28 closing cue: %r" % outro["cue"])
    try:
        SC.build_requests("rnb-flow", sheet, CLIENT, "T", 88, hook_plan=HOOK_PLAN)
    except Exception as e:
        check("summary-only-promise" in str(e),
              "WW-28: the production builder refuses the summary-only closing (%s)" % str(e)[:70])
    else:
        check(False, "WW-28: the production builder accepted a summary-only closing")
    other = dict(outro, lines=["Book your assessment call today."])
    try:
        SC.build_requests("rnb-flow", list(SHEET_RNB) + [other], CLIENT, "T", 88, hook_plan=HOOK_PLAN)
        check(True, "WW-28: the production builder accepts a closing that carries the call")
    except Exception as e:
        check(False, "WW-28: a real closing call was refused (%s)" % str(e)[:90])
    # a plain sheet (no call-tagged closing) is untouched
    plain = SA.check_payload_closing("[Verse]\nhi\n\n[End]")
    check(plain["outcome"] == "skipped",
          "WW-28: a sheet with no call-tagged closing stands aside (%s)" % plain["reason_code"])


def test_ww28_reconstruction_is_from_exact_lyrics_not_a_scene_summary():
    """An independent non-maker reconstructs the causal story from the EXACT
    lyrics; a scene summary is refused. Marked DEPENDS-ON-WW-27 for the full
    ensemble-cast leg -- the base speaker structures are used here."""
    if not gate(SA is not None, "WW-28 reconstruction", "story_arc did not load"):
        return
    rec = SA.reconstruct_causal_story(WW28_LYRICS, hook_line="I am not small")
    print("  WW-28 reconstruction: %r stakes=%r replies=%r earned=%r cast=%r"
          % (rec["reason_code"], rec["stakes"], rec["exchanged_replies"], rec["earned_hook"],
             rec["cast_model"]))
    check(rec["determined"] and rec["stakes"] and rec["exchanged_replies"] and rec["earned_hook"],
          "WW-28: the causal story reconstructs from the exact lyrics")
    summary = "A woman runs a shop. Things get hard. Then everything changes."
    bad = SA.reconstruct_causal_story(summary)
    check(not bad["determined"] and bad["reason_code"] == "SCENE_SUMMARY_NOT_LYRICS",
          "WW-28: a scene summary is refused, not reconstructed (%s)" % bad["reason_code"])
    no_stakes = "[Verse (sung)]\nla la\n\n[Hook (sung)]\nI am not small\n\n[End]"
    r = SA.reconstruct_causal_story(no_stakes, hook_line="I am not small")
    check(not r["determined"] and "stakes" in r["detail"],
          "WW-28: lyrics with no stakes cannot be reconstructed")


def test_ww28_mappings_are_preserved_twelve_eight_fifteen():
    """The explicit mappings survive: twelve canonical beats, eight timing
    stages, fifteen source-method stages, each mapped by name."""
    if not gate(SA is not None, "WW-28 mappings", "story_arc did not load"):
        return
    report = SA.assert_mappings_intact()
    print("  WW-28 mappings: %r" % (report["counts"],))
    check(report["canonical_beat_count"] == 12 and len(report["canonical_beats"]) == 12,
          "WW-28: twelve canonical beats preserved")
    check(report["timing_stage_count"] == 8 and len(report["timing_stages"]) == 8,
          "WW-28: eight timing stages preserved")
    check(report["source_method_stage_count"] == 15, "WW-28: fifteen source-method stages preserved")
    check(report["counts_are_distinct"] and report["mapped_by_name_not_by_count"],
          "WW-28: the three counts stay distinct and mapped by name")


def test_ww28_guards_are_reachable_and_no_sixth_audio_gate_is_added():
    """The causal gate is INVOKED by validate_story of the production path:
    removing the invocation lets a bad story through. And the story gate adds
    no audio gate -- D1-D5 remain the only delivered-audio gates."""
    if not gate(SA is not None, "WW-28 reachability", "story_arc did not load"):
        return
    src = _inspect_source(SA.validate_story)
    check("check_causal_story" in src,
          "WW-28: validate_story (the function script_approval.stage calls) invokes the causal gate")
    bad = _ww28_story(causal_over={"cost": ""})
    check(SA.validate_story(bad)["outcome"] == "rejected",
          "WW-28: with the gate in place the bad story is refused (pre-mutation)")
    original = SA.check_causal_story
    try:
        SA.check_causal_story = lambda *a, **k: {"errors": [], "outcome": "ok"}
        after = SA.validate_story(bad)["outcome"]
    finally:
        SA.check_causal_story = original
    check(after == "ok",
          "WW-28: removing the causal-gate invocation lets the bad story through (gate is load-bearing)")
    check(SA.validate_story(bad)["outcome"] == "rejected",
          "WW-28: the gate is restored after the mutation proof")
    check(hasattr(SD, "AUDIO_RESULTS") and SD.AUDIO_RESULTS == ("D1", "D2", "D3", "D4", "D5"),
          "WW-28: no sixth audio gate -- the five delivered-audio results are unchanged")
    check("WW28" not in _inspect_source(getattr(SD, "judge_take", lambda: None)),
          "WW-28: the delivered-audio judge carries no WW-28 craft gate")


# =====================================================================
# WWC-U4 (integrator) -- finishes WW-28's DEPENDS-ON-WW-27 clause.
#
# WW-28's non-maker reconstruction judged its 'exchanged replies' leg only
# against the base's speaker-prefix / quoted-reply structures and reported
# cast_model="base-structures"; the full cast-model version was reported
# DEPENDS-ON-WW-27 and NOT claimed met. WW-27's ensemble character bible now
# sits BELOW this unit, so the leg is finished on THAT model: when the story
# declares a cast, a villain or foil must SPEAK and receive a consequential
# reply from another declared character (character_bible.traded_replies over
# speaker_turns), and the receipt says cast_model="ww27-ensemble-cast".
# Known-good control first, then negatives; the gate-removal mutation proves
# the cast model -- not a hand-built dictionary -- is load-bearing. No new
# audio gate: D1-D5 are untouched. One delimited block; tests test_wwcu4_*.
# =====================================================================

#: WW-27's ensemble cast record (the shape character_bible.resolve_cast reads).
def _wwcu4_cast():
    return {"cast_mode": "ensemble", "characters": [
        {"name": "Mara", "role": "protagonist", "want": "her shop back",
         "wound": "she lost the door she painted",
         "relationships": "Jonas holds the lease",
         "consequential_action": "she rebuilds from the ledger",
         "voice": "warm alto",
         "voice_direction": {"register": "alto", "timbre": "warm",
                             "articulation": "clear", "delivery": "restrained",
                             "emotional_progression": "wound to resolve",
                             "version_treatment": "one take"}},
        {"name": "Jonas", "role": "villain", "want": "the lease back",
         "wound": "he was outbid once", "relationships": "Mara's landlord",
         "consequential_action": "he takes the door",
         "voice": "dry baritone",
         "voice_direction": {"register": "baritone", "timbre": "dry",
                             "articulation": "clipped", "delivery": "cold",
                             "emotional_progression": "flat menace",
                             "version_treatment": "one take"}}]}

#: exact lyrics whose exchanged reply is a NAMED-CHARACTER turn (WW-27's
#: bracket grammar), with a cost line, an earned hook and the closing call.
WWCU4_LYRICS_REPLIED = """[Intro (spoken): no melody, cold open]
She watched the shop sign come down.
I lost the door I painted years ago.

[Jonas (male): the opposing voice]
You will never open that door again.

[Mara (female): the reply]
I rebuilt from the ledger and I open it today.

[Hook (sung): the payoff]
I am not small

[Outro (spoken): no melody, book your assessment call]
Book your assessment call and start today.
"""

#: the same shape with the villain LEFT UNANSWERED (no reply turn at all).
WWCU4_LYRICS_SILENT = """[Intro (spoken): no melody, cold open]
I lost the door I painted years ago.

[Jonas (male): the opposing voice]
You will never open that door again.

[Hook (sung): the payoff]
I am not small

[Outro (spoken): no melody, book your assessment call]
Book your assessment call and start today.
"""

def test_wwcu4_control_the_base_leg_still_reconstructs_without_a_cast():
    if not gate(SA is not None, "WWC-U4 control", "story_arc did not load"):
        return
    rec = SA.reconstruct_causal_story(WW28_LYRICS)
    print("  WWC-U4 control: base-structures -> determined=%r cast_model=%r"
          % (rec["determined"], rec["cast_model"]))
    check(rec["determined"] is True and rec["cast_model"] == "base-structures",
          "WWC-U4: with no cast the base speaker-prefix leg still reconstructs (unchanged)")

def test_wwcu4_cast_model_judges_the_exchanged_replies_leg():
    if not gate(SA is not None and CB is not None, "WWC-U4 cast leg",
                "story_arc or character_bible did not load"):
        return
    rec = SA.reconstruct_causal_story(WWCU4_LYRICS_REPLIED, cast=_wwcu4_cast())
    print("  WWC-U4 cast leg: determined=%r cast_model=%r traded=%r"
          % (rec["determined"], rec["cast_model"], rec.get("traded_reply")))
    check(rec["determined"] is True and rec["cast_model"] == "ww27-ensemble-cast",
          "WWC-U4: a declared cast judges the exchanged-replies leg on WW-27's model")
    check((rec.get("traded_reply") or {}).get("opponent") == "jonas",
          "WWC-U4: the villain's spoken turn is answered by another declared character")
    base = SA.reconstruct_causal_story(WWCU4_LYRICS_REPLIED)
    print("  WWC-U4 same lyrics, no cast -> %s: %s" % (base["reason_code"], base["detail"]))
    check(base["determined"] is False and base["reason_code"] == "CAUSAL_CHAIN_INCOMPLETE"
          and "exchanged replies" in base["detail"],
          "WWC-U4: the SAME lyrics fail the base leg -- the cast model is the difference")

def test_wwcu4_cast_model_refuses_an_unanswered_opponent():
    if not gate(SA is not None and CB is not None, "WWC-U4 silent opponent",
                "story_arc or character_bible did not load"):
        return
    rec = SA.reconstruct_causal_story(WWCU4_LYRICS_SILENT, cast=_wwcu4_cast())
    print("  WWC-U4 silent opponent -> %s: %s" % (rec["reason_code"], rec["detail"]))
    check(rec["determined"] is False and rec["reason_code"] == "CAUSAL_CHAIN_INCOMPLETE"
          and "exchanged replies" in rec["detail"],
          "WWC-U4: a villain who speaks but is never answered is refused (WW-27 traded replies)")

def test_wwcu4_cast_model_reaches_the_production_gate():
    if not gate(SA is not None and CB is not None, "WWC-U4 production gate",
                "story_arc or character_bible did not load"):
        return
    good = SA.validate_story(_ww28_story(causal_over={"lyrics": WWCU4_LYRICS_REPLIED,
                                                      "cast": _wwcu4_cast()}))
    print("  WWC-U4 production gate (cast declared) -> %r / %r"
          % (good["outcome"], good["reason_code"]))
    check(good["outcome"] == "ok",
          "WWC-U4: the production causal gate passes the cast-answered story")
    bad = SA.validate_story(_ww28_story(causal_over={"lyrics": WWCU4_LYRICS_SILENT,
                                                     "cast": _wwcu4_cast()}))
    print("  WWC-U4 production gate (opponent unanswered) -> %r / %r"
          % (bad["outcome"], bad["reason_code"]))
    check(bad["outcome"] == "rejected" and bad["reason_code"] == "CAUSAL_CHAIN_INCOMPLETE",
          "WWC-U4: the production causal gate refuses the unanswered opponent")

def test_wwcu4_the_cast_model_call_is_load_bearing():
    if not gate(SA is not None and CB is not None, "WWC-U4 mutation",
                "story_arc or character_bible did not load"):
        return
    saved = SA._cast_model
    try:
        SA._cast_model = lambda: None
        gone = SA.reconstruct_causal_story(WWCU4_LYRICS_REPLIED, cast=_wwcu4_cast())
        print("  WWC-U4 with _cast_model stubbed -> %s: %s"
              % (gone["reason_code"], gone["detail"]))
        check(gone["determined"] is False and gone["reason_code"] == "CAUSAL_CHAIN_INCOMPLETE",
              "WWC-U4: with the cast model removed the same story is refused again")
    finally:
        SA._cast_model = saved
    back = SA.reconstruct_causal_story(WWCU4_LYRICS_REPLIED, cast=_wwcu4_cast())
    check(back["determined"] is True,
          "WWC-U4: restoring the cast model accepts it again (load-bearing, not dead)")

# =====================================================================
# WW-29: reconciled template data and recipe (WW29-U2)
#
# The model block (references/prompt-templates/models/suno-v6.json) no longer
# mandates a long wordless opening or an early hook, and the vocalise is
# OPTIONAL; the R&B Flow rap/sung direction is one decision in the data and in
# the recipe; the required directions and `negative_tags` reach the EXACT final
# `request["input"]` on every entry path; and an over-cap final style REFUSES
# with a named reason, deleting no clause.
#
# Every threshold pinned below is a rule this unit states, not a measured limit
# of an earlier run. Entry paths exercised: suno_recipe.build_request,
# music_director.build_generate_request and song_choices.build_requests (the
# three-complete-briefs path through suno_recipe.brief_style_text).
# =====================================================================

import copy                                                    # noqa: E402
import io                                                      # noqa: E402
import os                                                      # noqa: E402

import ending_qc as _EQ29                                      # noqa: E402
import music_director as _MD29                                 # noqa: E402
import prompt_limits as _PL29                                  # noqa: E402
from sung_hook import hook_placement as _HP29                  # noqa: E402
from words_fit import words_fit as _WF29                       # noqa: E402

#: The bare recipe module: is_rap_style/check_opening_vocalise_cue/
#: _fewer_words_budget live outside the package re-export list.
_R29 = getattr(R, "suno_recipe", R)
_M29 = getattr(LF, "length_formula", LF)
_SKILL29 = os.path.dirname(os.path.dirname(CORE))              # .../75-drama-song-ad-factory
WW29_LENGTH_S = 88

#: R&B Flow on the 88 s card WITHOUT its [Vocalise] section: the shipped sheet
#: with one wordless line removed, so it still clears the per-verse rap floor.
SHEET_NO_VOCALISE = [s for s in SHEET_RNB
                     if not str(s["tag"]).lower().startswith("vocalise")]
#: The same sheet with a DECLARED long opening cue (the WW-16 defect, verbatim).
SHEET_LONG_VOCALISE = [
    dict(s, cue="two very long held notes") if str(s["tag"]).lower().startswith("vocalise")
    else s for s in SHEET_RNB]
#: The retired rule's own shape: the hook is the very first section.
SHEET_HOOK_FIRST = ([{"tag": "Hook", "delivery": "sung", "lines": list(HOOK)}]
                    + SHEET_RNB[1:])

def _ww29_build(sheet=None, **kw):
    """ENTRY PATH 1: the recipe's own createTask builder."""
    return R.build_request("rnb-flow", SHEET_RNB if sheet is None else sheet,
                           CLIENT, "T", WW29_LENGTH_S, hook_plan=HOOK_PLAN, **kw)

def _ww29_director(sheet=None):
    """ENTRY PATH 2: the director seam that builds the same envelope."""
    sh = SHEET_RNB if sheet is None else sheet
    return _MD29.build_generate_request(
        R.render_lyrics(sh, "rnb-flow"), R.style_text("rnb-flow", sh, "f"), "T",
        style_id="rnb-flow", client_text=CLIENT, length_s=WW29_LENGTH_S,
        hook_plan=HOOK_PLAN)

def _ww29_choices(sheet=None):
    """ENTRY PATH 3: the three independently authored complete briefs."""
    return SC.build_requests("rnb-flow", SHEET_RNB if sheet is None else sheet,
                             CLIENT, "T", WW29_LENGTH_S, hook_plan=HOOK_PLAN)

def _ww29_final_inputs(sheet=None):
    rows = [("build_request", _ww29_build(sheet)),
            ("director", _ww29_director(sheet))]
    rows += [("choices/%s" % v["id"], req) for v, req in _ww29_choices(sheet)]
    return [(name, req["input"]) for name, req in rows]

def _ww29_why(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception as e:                                     # noqa: BLE001
        return str(e)
    return ""

def test_ww29_a_required_directions_and_transmitted_negatives_on_every_path():
    """The EXACT serialized input of every entry path carries every required
    direction and the style's own `negative_tags`, not a trimmed one."""
    need = set(R.REQUIRED_MUSIC_DIRECTIONS)
    data_neg = R.negative_tags("rnb-flow")
    print("  WW-29 rnb-flow negative_tags -> %r" % (data_neg,))
    for name, inp in _ww29_final_inputs():
        print("  WW-29 %s input keys -> %r" % (name, sorted(inp)))
        check(need <= set(inp),
              "WW-29: %s input carries every required direction" % name)
        check(isinstance(inp.get("negative_tags"), str) and inp["negative_tags"].strip(),
              "WW-29: %s transmits a non-empty negative_tags" % name)
        check(inp["negative_tags"] == data_neg,
              "WW-29: %s negative_tags is the data's own string, untouched" % name)
        check(R.check_negatives(inp["negative_tags"], "rnb-flow") == [],
              "WW-29: %s keeps every required negative clause" % name)
        check(R.check_style_text(inp["style"]) == [],
              "WW-29: %s final style passes the style rules" % name)

def test_ww29_b_the_vocalise_is_optional_and_the_ceiling_still_refuses_a_long_cue():
    """CONTROL first: the shipped sheet (which HAS a vocalise) builds. Then the
    same sheet with no [Vocalise] builds on every entry path -- the base refused
    it with "no sung vocalise lead-in". The WW-16 ceiling still refuses a
    DECLARED long/held cue, and removing that one call drops the refusal."""
    control = _ww29_build()
    check("[Vocalise" in control["input"]["lyrics"],
          "WW-29 control: the shipped sheet still renders its optional vocalise")
    errs = R.check_lyric_sheet(SHEET_NO_VOCALISE, CLIENT, WW29_LENGTH_S, style_id="rnb-flow")
    print("  WW-29 no-vocalise sheet errors -> %r" % (errs,))
    check(not any("vocalise" in e.lower() for e in errs),
          "WW-29: a sheet carrying no vocalise is not refused for that")
    for name, inp in _ww29_final_inputs(SHEET_NO_VOCALISE):
        check("[Vocalise" not in inp["lyrics"],
              "WW-29: %s builds a payload with no vocalise section" % name)
    # the ceiling guard the unit KEEPS, on the producing path
    why = _ww29_why(_ww29_build, SHEET_LONG_VOCALISE)
    print("  WW-29 declared long opening cue -> %r" % (why[:110],))
    check("3.0 s ceiling" in why,
          "WW-29: a DECLARED long opening vocalise cue is still refused by the ceiling")
    saved = _R29.check_opening_vocalise_cue
    try:
        _R29.check_opening_vocalise_cue = lambda cue: None
        gone = _ww29_why(_ww29_build, SHEET_LONG_VOCALISE)
    finally:
        _R29.check_opening_vocalise_cue = saved
    print("  WW-29 with the ceiling call removed -> %r" % (gone[:80],))
    check("3.0 s ceiling" not in gone,
          "WW-29: removing the ceiling call removes the refusal (load-bearing, not dead)")
    check("3.0 s ceiling" in _ww29_why(_ww29_build, SHEET_LONG_VOCALISE),
          "WW-29: restoring the ceiling call refuses it again")

def test_ww29_c_no_stale_early_hook_rule_and_the_payoff_doctrine_refuses():
    """The retired rule is gone from the DATA and from the CODE (read on disk),
    and what refuses a hook-first sheet is the current payoff doctrine."""
    data = io.open(os.path.join(_SKILL29, "references", "prompt-templates", "models",
                               "suno-v6.json"), encoding="utf-8").read()
    src = io.open(os.path.join(_SKILL29, "scripts", "core", "suno_recipe",
                               "suno_recipe.py"), encoding="utf-8").read()
    check("first by 15% of runtime" not in data,
          "WW-29: the data no longer mandates the first hook at 15% of runtime")
    check("two very long held notes" not in data and "OPTIONAL" in data,
          "WW-29: the data says the vocalise is OPTIONAL, not two long held notes")
    check("a vocalise comes first" not in src and "no sung vocalise lead-in" not in src,
          "WW-29: the retired vocalise/early-hook reasons are gone from the recipe")
    why = "; ".join(R.check_lyric_sheet(SHEET_HOOK_FIRST, CLIENT, style_id="rnb-flow"))
    print("  WW-29 hook-first sheet -> %r" % (why[:130],))
    check("may not open" in why and "payoff" in why,
          "WW-29: a hook-first sheet is refused by the payoff doctrine")
    check("vocalise comes first" not in why,
          "WW-29: the refusal no longer cites the retired vocalise rule")
    check(_HP29.check_buildup(SHEET_HOOK_FIRST, "rnb-flow", WW29_LENGTH_S),
          "WW-29: hook_placement.check_buildup holds the same rule on the same sheet")

def test_ww29_d_required_clauses_survive_the_cap_and_an_overflow_refuses():
    """The required clauses (delivery map, band wording, one clean ending, the
    hook-order clause, the approved pace clause) are ON the exact final style,
    and an over-cap final style REFUSES without deleting one."""
    pace = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove"}
    req = _ww29_build(pace_plan=pace)
    style, inp = req["input"]["style"], req["input"]
    for clause, label in ((_EQ29.STYLE_ENDING, "clean ending"),
                          (_HP29.PROMPT_CLAUSE, "hook-order"),
                          ("RAPS the lines tagged Rap", "rap delivery map"),
                          ("SINGS the lines tagged Sung", "sung delivery map")):
        check(clause in style, "WW-29: the final style still carries the %s clause" % label)
    check(style.rstrip().endswith(_R29.pace_clause(pace).rstrip()),
          "WW-29: the approved pace clause is still LAST in the final style")
    check(len(style) <= _R29.SUNO_STYLE_FIELD_MAX,
          "WW-29: the final style is inside the cap (%d chars)" % len(style))
    # the cap refuses rather than trimming the negative clause
    over = dict(inp, negative_tags="x, " * 400)
    why = _ww29_why(_PL29.check_request, "suno-generate", {"input": over})
    print("  WW-29 over-cap negative clause -> %r" % (why[:110],))
    check("negative_tags" in why,
          "WW-29: an over-cap negative clause is REFUSED with the field named, never trimmed")
    # the OVERFLOW on the real three-briefs path: the production builder refuses
    real = SC.variants_for
    try:
        rows = copy.deepcopy(real("rnb-flow"))
        for v in rows:
            v["brief"]["arrangement"] = "x" * 400
        SC.variants_for = lambda style_id: rows
        why = _ww29_why(SC.build_requests, "rnb-flow", SHEET_RNB, CLIENT, "T",
                        WW29_LENGTH_S, hook_plan=HOOK_PLAN)
    finally:
        SC.variants_for = real
    print("  WW-29 over-cap final style -> %r" % (why[:150],))
    check("STYLE_TOO_LONG" in why and "NO clause is deleted" in why
          and "delivery map" in why,
          "WW-29: an over-cap final style REFUSES and deletes no clause")
    check(len(_ww29_choices()[0][1]["input"]["style"]) <= _R29.SUNO_STYLE_FIELD_MAX,
          "WW-29: with the variant brief restored the same path builds inside the cap")

def test_ww29_e_rnb_flow_rap_and_sung_direction_is_one_decision():
    """The rap fact reads the STYLE'S OWN DATA, so the label and the id judge
    the same style the same way; the final style directs both deliveries."""
    rap_neg = "rap, choir, reverb, echo"
    id_errs = R.check_negatives(rap_neg, "rnb-flow")
    label_errs = R.check_negatives(rap_neg, "R&B Flow")
    print("  WW-29 id/label rap-negative errors -> %r / %r" % (id_errs, label_errs))
    check(id_errs == label_errs and id_errs,
          "WW-29: the label and the id give the SAME rap-negatives verdict (the base gave [] for the label)")
    check(_R29.is_rap_style("rnb-flow") and _R29.is_rap_style("R&B Flow"),
          "WW-29: is_rap_style reads the data, so both spellings answer rap")
    for other in ("soul-ballad", "soul-rise", "velvet_voiceover", "brand-new-style", None, ""):
        check(_R29.is_rap_style(other) is False,
              "WW-29: is_rap_style(%r) is False (fail closed)" % (other,))
    check(R.negative_tags("R&B Flow") == R.negative_tags("rnb-flow"),
          "WW-29: the fallback negatives agree for the label and the id")
    style = _ww29_build()["input"]["style"]
    check("RAPS the lines tagged Rap" in style and "SINGS the lines tagged Sung" in style,
          "WW-29: the final R&B Flow style directs rhythmic rap verses AND the sung hook")
    data = io.open(os.path.join(_SKILL29, "references", "prompt-templates", "models",
                               "suno-v6.json"), encoding="utf-8").read()
    check("speech-rhythm rap" in data and "fully sung melodic r&b hook" in data,
          "WW-29: the data states the same rap-versus-sung direction once")
    saved = _R29.is_rap_style
    try:
        _R29.is_rap_style = lambda style_id: style_id in _R29.RAP_STYLE_IDS
        leaked = R.check_negatives(rap_neg, "R&B Flow")
    finally:
        _R29.is_rap_style = saved
    print("  WW-29 with the hard-coded id list only -> %r" % (leaked,))
    check(leaked == [],
          "WW-29: the old hard-coded list silently drops the guard for the label (load-bearing)")

def test_ww29_f_the_fewer_words_budget_agrees_with_the_length_plan():
    """OPTION (ii). An R&B Flow card's "fewer words" budget IS the length plan's
    own total (rap words at the rap rate, the per-verse floor reserved); a style
    that delivers no rap keeps the base arithmetic unchanged."""
    L, io_s = 90, _WF29.INTRO_OUTRO_S
    rates = _WF29.rates_for("rnb-flow")
    target = _WF29.style_sung_target_pct("rnb-flow", L)
    budget = _WF29._fewer_words_budget(L, target, rates, io_s, style="rnb-flow")
    plan = _M29.plan(L, style_id="rnb-flow")
    print("  WW-29 R&B Flow L=%g target=%r budget=%r plan total=%r"
          % (L, target, budget, plan["words"]["total"]))
    check(budget == float(plan["words"]["total"]),
          "WW-29: the reconciled budget EQUALS length_formula.plan on the same card")
    check(_WF29._fewer_words_budget(L, target, rates, io_s, style="R&B Flow") == budget,
          "WW-29: the label and the id give the same budget")
    floor_words = _M29.rap_verse_min_words("rnb-flow") * _M29.MIN_RAP_VERSES
    check(plan["words"]["rap"] >= floor_words,
          "WW-29: the plan the budget reads reserves the two-verse rap floor (%d words)"
          % floor_words)
    # the base shape ignored rap: prove the OLD number is no longer offered
    old = ((L - io_s) * target / 100.0 * rates["sung"]
           + (L - io_s) * (1 - target / 100.0) * rates["spoken"])
    check(old != budget,
          "WW-29: the old rap-blind arithmetic (%r) is replaced by the plan's number" % old)
    # a non-rap style is byte-identical to the base
    for style in ("soul-ballad", "Soul Rise", None):
        r = _WF29.DEFAULT_SUNG_TARGET_PCT if style is None else _WF29.style_sung_target_pct(style, L)
        rates_s = _WF29.rates_for(style)
        got = _WF29._fewer_words_budget(L, r, rates_s, io_s, style=style)
        # the BASE expression, char for char, so "unchanged" is exact, not near
        vb = L - io_s
        f = max(0.0, min(1.0, r / 100.0))
        want = vb * f * rates_s["sung"] + vb * (1.0 - f) * rates_s["spoken"]
        check(got == want,
              "WW-29: %r keeps the base budget arithmetic unchanged (%r == %r)"
              % (style, got, want))
    # the number the OPTION SHOWS is the number the GATE enforces
    pf = _WF29.preflight(L, 200, 30, style="rnb-flow")
    shown = (pf.get("options") or {}).get("fewer_words") or {}
    print("  WW-29 fewer_words option -> %r" % (shown,))
    check(pf["outcome"] == "waiting" and shown.get("max_total_words") == float(plan["words"]["total"]),
          "WW-29: the option offers the plan's budget, not the rap-blind one")
    over = [dict(s) for s in SHEET_RNB]
    over[4]["lines"] = list(over[4]["lines"]) + ["filler words here now %d" % i for i in range(20)]
    gate_errs = R.check_lyric_sheet(over, CLIENT, WW29_LENGTH_S, style_id="rnb-flow")
    print("  WW-29 over-budget sheet -> %r" % (gate_errs,))
    check(any("budget" in e for e in gate_errs),
          "WW-29: the recipe's own word gate refuses over the plan's budget")

def test_ww29_g_a_card_that_cannot_hold_the_two_verse_rap_floor_is_still_refused():
    """CONTROL first: the shipped R&B Flow sheet builds. Then a sheet whose two
    rap verses sit under the per-verse floor is refused on the production path
    with the floor named -- the budget work lowers no rap floor."""
    check(_ww29_director()["input"]["lyrics"],
          "WW-29 control: the shipped two-verse R&B Flow sheet still builds")
    thin = []
    for s in SHEET_NO_VOCALISE:
        if s["delivery"] == "rap" and len([x for x in thin if x["delivery"] == "rap"]) == 0:
            thin.append(dict(s, lines=["too short a verse here"]))
        elif s["delivery"] == "rap":
            thin.append(dict(s, lines=["and one more short line"]))
        else:
            thin.append(dict(s))
    print("  WW-29 thin sheet rap words -> %r" % (R.sheet_words(thin, "rap"),))
    why = _ww29_why(_ww29_director, thin)
    print("  WW-29 thin rap sheet -> %r" % (why[:150],))
    check("RAP_VERSE_BELOW_FLOOR" in why and "floor 20 words / 8.0 s" in why,
          "WW-29: a card that cannot hold the two-verse rap floor is REFUSED, floor named")
    check(_M29.rap_verse_min_words("rnb-flow") == 20 and _M29.MIN_RAP_VERSES == 2,
          "WW-29: the per-verse floor the refusal names is the unchanged 20 words x 2 verses")
    check(_M29.rap_floor_s(88) == 8.8 and _M29.RAP_FLOOR_SHARE == 0.10,
          "WW-29: the total rap floor is unchanged (max(8.0 s, 10% of D))")
# <<< WW29-U2 BLOCK END >>>


# =====================================================================
# WW29-U3 (Builder c: music director) -- WW-29 on the music director.
#
# WW-29 removes the mandatory wordless held-note opening and the stale
# hook-in-the-first-fifteen-percent rule, keeps the hook a MEASURED payoff
# (``true_at_beat``), makes the opening vocalise OPTIONAL, and requires the
# cast, pace/shift, hook, ending and negative clauses to survive into the
# EXACT serialized ``request["input"]`` with an overflow REFUSING rather than
# dropping a clause.
#
# The rule enforcement for the vocalise and the cue lives in the recipe/data
# (``scripts/core/suno_recipe/suno_recipe.py`` + ``references/prompt-templates``,
# builder b) and the doctrine text in the docs (builder a). THIS builder owns
# ``scripts/core/music_director/__init__.py`` and proves the DIRECTOR:
#   (a) adds no vocalise / early-hook direction of its own;
#   (b) carries every required direction and its own clauses to the EXACT
#       payload from every entry path (the R&B Flow rap card and a non-rap
#       soul card, built the same way);
#   (c) refuses an over-cap final payload through the LOAD-BEARING cap gate
#       without truncating anything (the gate is removed and shown to matter).
# =====================================================================

#: A non-rap soul card that clears the recipe at its delivered length (58 s).
SHEET_BAL = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
             {"tag": "Verse 1", "delivery": "sung",
              "lines": ["One seed of truth made me stro-o-ong,"]},
             {"tag": "Hook 1", "delivery": "sung", "lines": list(HOOK)},
             {"tag": "Hook 2", "delivery": "sung", "lines": list(HOOK)},
             {"tag": "Hook 3", "delivery": "sung", "lines": list(HOOK)},
             {"tag": "Outro", "delivery": "spoken",
              "lines": ["She Found Power in the Climb. Get the book. Link below."]}]

REQUIRED_DIRECTIONS = ("custom_mode", "instrumental", "title", "lyrics", "style",
                       "negative_tags", "duration")


def _ww29_u3_md():
    """The music director for this block, or None when it is not on the tree."""
    return _load_path("music_director/__init__.py")


def test_ww29_u3_exact_input_carries_every_required_direction():
    MD = _ww29_u3_md()
    if not gate(MD is not None and R is not None, "WW29-U3 directions",
                "music_director or suno_recipe did not load"):
        return
    out = R.prepare("rnb-flow", SHEET_RNB, CLIENT, 88, hook_plan=HOOK_PLAN)
    req = MD.build_generate_request(out["lyrics"], out["style"], "T",
                                    style_id="rnb-flow", client_text=CLIENT,
                                    length_s=88, true_at_beat="the_world")
    inp = req["input"]
    missing = [f for f in REQUIRED_DIRECTIONS if f not in inp]
    print("  WW29-U3 exact request['input'] keys: %s" % sorted(inp))
    check(not missing,
          "WW29-U3: the exact request['input'] carries every required direction (missing=%r)" % missing)
    check(bool(inp["negative_tags"]) and "rap" not in [t.strip() for t in inp["negative_tags"].split(",")],
          "WW29-U3: negative_tags is transmitted, and the R&B Flow negatives keep rap (no rap exclusion)")
    check("resolved ending" in inp["style"].lower(),
          "WW29-U3: the ending clause survives into the exact request['input']['style']")
    check("[End]" in inp["lyrics"] and ("[Outro" in inp["lyrics"] or "[Resolve" in inp["lyrics"]),
          "WW29-U3: the exact serialized lyrics still ask for a real ending ([Outro] + end tag)")
    check(inp["duration"] == 88,
          "WW29-U3: the delivered length reaches the exact input.duration (%r)" % inp["duration"])


def test_ww29_u3_director_adds_no_vocalise_or_early_hook_of_its_own():
    MD = _ww29_u3_md()
    if not gate(MD is not None and R is not None, "WW29-U3 no-vocalise",
                "music_director or suno_recipe did not load"):
        return
    # (1) deterministically: the text the director appends to a caller style is
    # the ending clause only -- no wordless-vocalise mandate, no early-hook rule.
    exotic = "warm analog strings, dry close vocal, slow tempo, female lead"
    req = MD.build_generate_request("la la", exotic, "T", style_id="velvet_voiceover")
    added = req["input"]["style"][len(exotic):].lower()
    print("  WW29-U3 text the director adds to a caller style: %r" % added)
    check("wordless" not in added and "vocalise" not in added and "vocalize" not in added,
          "WW29-U3: the director injects NO wordless-vocalise mandate of its own")
    check("15%" not in added and "fifteen" not in added and "percent" not in added,
          "WW29-U3: the director injects NO percent-of-runtime early-hook rule of its own")
    # (2) the removed mandate lives in the RECIPE, never the director: a sheet
    # with NO vocalise is judged by suno_recipe (after WW-29 it is accepted).
    novoc = [s for s in SHEET_RNB if not s["tag"].lower().startswith("vocalise")]
    try:
        R.prepare("rnb-flow", novoc, CLIENT, 88, hook_plan=HOOK_PLAN)
        check(True, "WW29-U3: the recipe accepts a sheet that opens WITHOUT a vocalise (lead-in is OPTIONAL)")
    except R.RecipeError as e:
        print("  WW29-U3 no-vocalise refusal (must be the recipe's): %s" % str(e)[:120])
        check("vocalise" in str(e).lower(),
              "WW29-U3: any vocalise requirement is the RECIPE's (suno_recipe), named in its refusal; the director adds none")


def test_ww29_u3_pace_shift_clause_is_last_and_single():
    MD = _ww29_u3_md()
    if not gate(MD is not None and R is not None, "WW29-U3 pace",
                "music_director or suno_recipe did not load"):
        return
    out = R.prepare("rnb-flow", SHEET_RNB, CLIENT, 88, hook_plan=HOOK_PLAN)
    pp = {"drop": "at the lowest point the groove drops to half-time with thin, sparse drums",
          "return": "then it turns and rises back to the full groove"}
    req = MD.build_generate_request(out["lyrics"], out["style"], "T",
                                    style_id="rnb-flow", client_text=CLIENT,
                                    length_s=88, true_at_beat="the_world", pace_plan=pp)
    st = req["input"]["style"]
    clause = getattr(R, "suno_recipe", R).pace_clause(pp).rstrip()
    check(st.rstrip().endswith(clause),
          "WW29-U3: the approved pace/shift clause is LAST in the exact request['input']['style']")
    check(st.count(clause) == 1,
          "WW29-U3: the shift clause appears exactly once (never duplicated, never dropped)")


def test_ww29_u3_over_cap_refuses_and_the_cap_gate_is_load_bearing():
    import prompt_limits as PL
    MD = _ww29_u3_md()
    if not gate(MD is not None and R is not None, "WW29-U3 cap",
                "music_director or suno_recipe did not load"):
        return
    out = R.prepare("soul-ballad", SHEET_BAL, CLIENT, 58, hook_plan=HOOK_PLAN)
    big_title = "T" * 81
    try:
        MD.build_generate_request(out["lyrics"], out["style"], big_title,
                                  style_id="soul-ballad", client_text=CLIENT,
                                  length_s=58, true_at_beat="the_world")
        check(False, "WW29-U3: an 81-char title must REFUSE (no silent truncation)")
    except PL.PromptLimitError as e:
        check(e.code == "PROMPT_OVER_CAP" and e.field == "title" and e.chars == 81 and e.cap == 80,
              "WW29-U3: the final cap gate refuses the over-cap title, naming field/chars/cap/PROMPT_OVER_CAP")
    # wiring: remove the DIRECTOR's real cap call; the over-cap payload must now build.
    orig = MD.prompt_limits.check_request
    MD.prompt_limits.check_request = lambda *a, **k: {"measured": []}
    try:
        loose = MD.build_generate_request(out["lyrics"], out["style"], big_title,
                                          style_id="soul-ballad", client_text=CLIENT,
                                          length_s=58, true_at_beat="the_world")
        check(loose["input"]["title"] == big_title,
              "WW29-U3: with the cap gate removed the over-cap title reaches the payload (the gate is load-bearing, not decorative)")
    finally:
        MD.prompt_limits.check_request = orig


def test_ww29_u3_a_non_rap_variant_carries_the_same_clauses():
    MD = _ww29_u3_md()
    if not gate(MD is not None and R is not None, "WW29-U3 soul variant",
                "music_director or suno_recipe did not load"):
        return
    out = R.prepare("soul-ballad", SHEET_BAL, CLIENT, 58, hook_plan=HOOK_PLAN)
    req = MD.build_generate_request(out["lyrics"], out["style"], "T",
                                    style_id="soul-ballad", client_text=CLIENT,
                                    length_s=58, true_at_beat="the_world")
    inp = req["input"]
    missing = [f for f in REQUIRED_DIRECTIONS if f not in inp]
    check(not missing and bool(inp["negative_tags"]) and "resolved ending" in inp["style"].lower(),
          "WW29-U3: a non-rap soul card carries the same required directions, negatives and ending clause (missing=%r)" % missing)

def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print("\n%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    if UNDETERMINED:
        print("\nPASS (%d UNDETERMINED -- NOT a release pass): %s"
              % (len(UNDETERMINED), "; ".join(UNDETERMINED)))
        return 0
    print("\nALL PASS")
    return 0


# ===========================================================================
# WW29-U1 (builder a: documents reconciliation) -- BEGIN delimited block.
# Asserts the reconciled WW-29 doctrine is present in the three documents and
# consistent with the style data. Known-good controls run before the negatives.
# ===========================================================================

def _ww29_u1_doc(rel):
    """Read one skill-75 document from the tree (empty string if absent)."""
    p = os.path.join(SKILL_ROOT, rel)
    if not os.path.exists(p):
        return ""
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def _ww29_u1_rule2_slice(text):
    """The recipe's rule 2 only: from '2. Sung lines are short' to the next
    numbered rule. Binds the assertion to rule 2 itself, never to a phrase
    that survives elsewhere in the document."""
    i = text.find("2. Sung lines are short")
    if i < 0:
        return ""
    j = text.find("\n3.", i)
    return text[i:(j if j > 0 else i + 600)]


def _ww29_u1_rule2_ok(text):
    """True when the rule-2 text states the wordless vocalise is OPTIONAL and
    never a forced lead-in -- and the retired mandatory wording ("after a
    wordless sung vocalise") is gone."""
    t = text.lower()
    return ("optional" in t and "never a forced" in t and "lead-in" in t
            and "mandatory" not in t
            and "after a wordless sung vocalise" not in t)


def test_ww29_u1_vocalise_is_optional_not_a_forced_lead_in():
    good = ("2. Sung lines are short, rhymed. A wordless vocalise is OPTIONAL, "
            "never a forced\n   lead-in: one short note or none.")
    check(_ww29_u1_rule2_ok(good),
          "WW29-U1 control: the reconciled rule 2 wording passes the checker")
    bad = ("2. Sung lines are short, rhymed, with hyphen-held vowels, "
           "after a wordless sung vocalise.")
    check(not _ww29_u1_rule2_ok(bad),
          "WW29-U1 control: the retired mandatory-vocalise wording is rejected")
    skill = _ww29_u1_doc("SKILL.md")
    rule2 = _ww29_u1_rule2_slice(skill)
    check(bool(rule2),
          "WW29-U1: SKILL.md has the numbered recipe rule 2")
    check(_ww29_u1_rule2_ok(rule2),
          "WW29-U1: SKILL.md recipe rule 2 makes the vocalise optional, never a forced lead-in")
    check("after a wordless sung vocalise" not in skill.lower(),
          "WW29-U1: SKILL.md no longer mandates 'after a wordless sung vocalise' anywhere")
    check("suno_parts" not in skill,
          "WW29-U1: SKILL.md names no non-existent prompt_templates.suno_parts")
    check("suno_recipe.style_text" in skill,
          "WW29-U1: SKILL.md names the real style-text builder suno_recipe.style_text")


def test_ww29_u1_three_docs_carry_the_reconciled_direction():
    docs = {"SKILL.md": _ww29_u1_doc("SKILL.md"),
            "INSTRUCTIONS.md": _ww29_u1_doc("INSTRUCTIONS.md"),
            "references/stage-runbook.md": _ww29_u1_doc("references/stage-runbook.md")}
    for name, text in docs.items():
        low = text.lower()
        check("five gates" in low,
              "WW29-U1: %s states the five-gate delivered-audio boundary" % name)
        check("optional" in low and "never a forced" in low,
              "WW29-U1: %s states the vocalise is optional, never a forced opening" % name)
        check("r&b flow" in low and "rap verses" in low and "sung" in low,
              "WW29-U1: %s states the R&B Flow rap-versus-sung direction" % name)
        check("negative_tags" in low,
              "WW29-U1: %s carries the negative_tags transmission clause" % name)


def test_ww29_u1_rnb_flow_data_matches_the_documented_direction():
    rel = os.path.join("references", "prompt-templates", "music", "rnb-flow.json")
    p = os.path.join(SKILL_ROOT, rel)
    check(os.path.exists(p), "WW29-U1: the R&B Flow style data file exists")
    if not os.path.exists(p):
        return
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    check(data.get("rap_allowed") is True,
          "WW29-U1: the R&B Flow data allows rap")
    check("rap" in (data.get("deliveries") or []),
          "WW29-U1: the R&B Flow data lists rap as a delivery")
    body = " ".join(data.get("style_parts") or []).lower()
    check("rap" in body and "sung" in body,
          "WW29-U1: the R&B Flow data contrasts rap verses with a sung hook")


def test_ww29_u1_runbook_single_dispatch_is_the_one_song_case():
    rb = _ww29_u1_doc("references/stage-runbook.md")
    check("one-song case" in rb,
          "WW29-U1: the runbook's single kie_dispatch row is the one-song case")
    check("song_choices" in rb,
          "WW29-U1: the runbook points the multi-version path at song_choices")

# ===========================================================================
# WW29-U1 -- END delimited block.
# ===========================================================================


if __name__ == "__main__":
    raise SystemExit(main())
