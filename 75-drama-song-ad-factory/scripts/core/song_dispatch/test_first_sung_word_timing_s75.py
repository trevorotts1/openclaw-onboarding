#!/usr/bin/env python3
"""Skill 75 U3 (defects D5, D6/A3, D10): the first sung WORD, not the symptom.

The take judge used to trust the singing detector's first figure alone, so a
line heard under the groove before the detector called it singing passed, and
a method run could be judged against a plan block that disagreed with the
run's own ``control/method.json``. This unit:

  * reads the first sung/rap word's start from the take's own word timings and
    records WHICH source produced the number, the detector staying the
    fallback;
  * reads a method run's apex from ``control/method.json`` at the judge seam,
    so a take singing at 0 s fails whatever the plan block says;
  * runs the pre-ERM sheet gate on the request path, before any spend;
  * publishes the ONE operator-decision order for measured FAILs.

Inert without a method record: a non-method run with no words is unchanged.
Stdlib only, fakes only: no provider call, no spend, no media file.

Run: cd scripts/core/song_dispatch && HOME=$(mktemp -d) python3 test_first_sung_word_timing_s75.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
import length_formula as LF        # noqa: E402
import song_dispatch as _PKG       # noqa: E402
import suno_recipe as R            # noqa: E402

#: the package re-exports a fixed list; the new helpers and the private
#: acceptance readers are reached on the module itself
SD = getattr(_PKG, "song_dispatch", _PKG)

D = 178
CLIENT = "I work too hard to not have nothing."
HOOK = ["I work too hard", "to not have nothing"]
VERSE = ["I work too hard to not have nothing,",
         "every closed door became a road I walked,",
         "and I am still here standing in the light."]
PRE = ["I am not the sum of the days I fell,"]
PRE2 = ["I am not the sum of the nights I quit,"]
SHEET = [{"tag": "Intro", "delivery": "spoken",
          "lines": ["Twelve words of spoken setup land here before the groove drops down."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung", "lines": VERSE},
         {"tag": "Pre-Chorus", "delivery": "sung", "lines": PRE}]
# 178 s needs the hook EIGHT times, and the hook must stay the UNIQUE
# most-repeated sung section: a tie lets the pre-chorus be read as "the hook"
# and the last-sung rule then refuses the sheet. The two pre-chorus variants
# alternate, so neither ever reaches eight.
for _i in range(1, 9):
    SHEET.append({"tag": "Hook %d" % _i, "delivery": "sung", "lines": HOOK})
    if _i < 8:
        SHEET.append({"tag": "Pre-Chorus", "delivery": "sung",
                      "lines": PRE if _i % 2 else PRE2})
SHEET.append({"tag": "Outro", "delivery": "spoken", "lines": [CLIENT]})
LYRICS = R.render_lyrics(SHEET, "soul-ballad")
SCRIPT = "Twelve words of spoken setup land here before the groove drops down. " + CLIENT
HOOKTXT = " ".join(HOOK)
HOOK_PLAN = {"true_at_beat": "the_world"}
METHOD = {"erm_apex_s": 32.5, "profile": "story", "erm_window_s": [25, 40]}

PLAN = dict(LF.plan(D, (15, 20)), sheet_text=LYRICS, style_id="soul-ballad",
            hook_plan=HOOK_PLAN)
METHOD_PLAN = dict(PLAN, method=dict(METHOD))

def words(text, start, step=0.4, key="start"):
    out = []
    for i, w in enumerate(text.split()):
        at = round(start + i * step, 3)
        out.append({"word": w, key: at, "end": round(at + step * 0.8, 3)})
    return out

def take(first_sung_s=32.0, aligned=None, duration_s=D):
    """A measured take. Only the first sung figure and the aligned words feed
    the first-vocal rule; the rest is the shape every gate reads."""
    out = {"segments": [{"delivery": "spoken", "start": 0.0, "end": 30.0, "source": "measured"},
                        {"delivery": "sung", "start": 31.0, "end": duration_s - 8.0,
                         "source": "measured"},
                        {"delivery": "spoken", "start": duration_s - 8.0, "end": duration_s,
                         "source": "measured"}],
           "aligned_words": aligned or [], "detector": "singing_detector 2.0.0",
           "duration_s": duration_s, "music_under_speech_ratio": 0.6,
           "tail_rms_dbfs": -30.0, "first_sung_s": first_sung_s}
    return out

def judge(t, plan=None):
    return SD.judge_take(t, PLAN if plan is None else plan, SCRIPT, HOOKTXT, (15, 20),
                         "soul-ballad", LYRICS)

def _pace_order(apex=32.5):
    return {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove",
            "boundary_s": apex, "return_boundary_s": 120.0}

# ---- first_sung comes from word timing, the detector is the fallback ------

def test_word_timing_puts_the_first_sung_line_at_the_apex():
    t = take(2.0, words("I work too hard to not have nothing so I keep showing up", 32.0))
    g = judge(t, METHOD_PLAN)["gates"]["first_sung"]
    assert g["verdict"] == "PASS", g
    assert g["measurement"]["source"] == "word_timing", g
    assert g["measurement"]["word_timing_first_sung_s"] == 32.0, g
    assert g["measurement"]["detector_first_sung_s"] == 2.0, g

def test_no_words_falls_back_to_the_detector_and_fails_early():
    g = judge(take(2.0), METHOD_PLAN)["gates"]["first_sung"]
    assert g["verdict"] == "FAIL" and "early" in g["detail"], g
    assert g["measurement"]["source"] == "singing_detector", g
    assert g["measurement"]["word_timing_first_sung_s"] is None, g

def test_a_line_sung_at_ten_seconds_against_the_apex_fails_early():
    t = take(10.0, words("I work too hard to not have nothing", 10.0))
    g = judge(t, METHOD_PLAN)["gates"]["first_sung"]
    assert g["verdict"] == "FAIL" and "early" in g["detail"], g
    assert g["measurement"]["source"] == "word_timing", g

def test_an_unmatched_word_stream_falls_back_to_the_detector():
    t = take(32.0, words("nothing of the sort is heard anywhere in this take", 5.0))
    g = judge(t, METHOD_PLAN)["gates"]["first_sung"]
    assert g["measurement"]["source"] == "singing_detector", g
    assert g["measurement"]["word_timing_first_sung_s"] is None, g
    assert g["verdict"] == "PASS", g

def test_start_and_startS_both_carry_the_timing():
    loud = [{"word": "I", "start": 32.0}, {"word": "work", "start": 32.4},
            {"word": "too", "start": 32.8}, {"word": "hard", "start": 33.2}]
    camel = [{"word": "I", "startS": 32.0}, {"word": "work", "startS": 32.4},
             {"word": "too", "startS": 32.8}, {"word": "hard", "startS": 33.2}]
    assert SD.first_sung_from_words(LYRICS, loud) == 32.0
    assert SD.first_sung_from_words(LYRICS, camel) == 32.0
    # the no-voice Vocalise section never becomes the anchor
    assert SD.first_sung_from_words(LYRICS, [{"word": "Oo-o-o-o-o-oh", "start": 1.0}]) is None

def test_nothing_to_read_is_none_never_a_number():
    assert SD.first_sung_from_words("", []) is None
    assert SD.first_sung_from_words(LYRICS, []) is None
    assert SD.first_sung_from_words("untagged words with no bracket", [{"word": "I"}]) is None

# ---- control/method.json is the apex the judge reads ---------------------

def test_run_method_targets_reads_the_record_and_reports_what_it_found():
    assert SD.run_method_targets(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        assert SD.run_method_targets(tmp) is None            # no record at all
        os.makedirs(os.path.join(tmp, "control"))
        p = os.path.join(tmp, "control", "method.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"purpose": "campaign", "runtime_targets": dict(METHOD)}, f)
        assert SD.run_method_targets(tmp) == METHOD
        with open(p, "w", encoding="utf-8") as f:
            f.write("{not json")
        assert SD.run_method_targets(tmp) == {"unreadable": "control/method.json"}
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"purpose": "campaign"}, f)
        assert SD.run_method_targets(tmp) == {"runtime_targets_missing": True}
        assert judge(take(32.0), dict(PLAN, method={"runtime_targets_missing": True}))[
            "gates"]["first_sung"]["verdict"] == "UNMEASURED"

def test_run_takes_judges_a_method_run_against_the_record_on_disk():
    order = _pace_order()
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", PLAN["delivered_s"],
                          hook_plan=HOOK_PLAN, pace_plan=order)
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "control"))
        with open(os.path.join(tmp, "control", "method.json"), "w", encoding="utf-8") as f:
            json.dump({"runtime_targets": dict(METHOD)}, f)
        sent = []
        good = take(0.0, words("I work too hard to not have nothing so I keep showing up", 32.0))
        out = SD.run_takes(req, dict(PLAN, pace_change=order),
                           lambda rq: sent.append(rq) or [good],
                           lambda t: {}, lambda t, r: None, SCRIPT, HOOKTXT, (15, 20),
                           cap_cents=6, run_dir=tmp)
        assert len(sent) == 1, sent
        g = out["receipts"][0]["gates"]["first_sung"]
        assert g["verdict"] == "PASS", g
        assert g["measurement"]["source"] == "word_timing", g
        # the SAME record refuses a take that sings at 0 s
        bad = take(0.0, words("I work too hard to not have nothing", 0.0))
        out2 = SD.run_takes(req, dict(PLAN, pace_change=order),
                            lambda rq: [bad], lambda t: {}, lambda t, r: None,
                            SCRIPT, HOOKTXT, (15, 20), cap_cents=6, run_dir=tmp)
        g2 = out2["receipts"][0]["gates"]["first_sung"]
        assert g2["verdict"] == "FAIL" and "early" in g2["detail"], g2

def test_a_non_method_run_with_no_words_is_unchanged():
    g = judge(take(2.0))["gates"]["first_sung"]
    assert g["measurement"]["source"] == "singing_detector", g
    assert g["measurement"]["word_timing_first_sung_s"] is None, g
    assert "ERM" not in g["detail"], g

# ---- the pre-ERM sheet gate runs on the REQUEST path ---------------------

def test_validate_request_runs_the_pre_erm_gate_for_a_method_order():
    order = _pace_order()
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", D, hook_plan=HOOK_PLAN,
                          pace_plan=order)
    short_intro = R.render_lyrics([{"tag": "Intro", "delivery": "spoken",
                                    "lines": ["One two three four five six seven eight "
                                              "nine ten eleven twelve."]}], "soul-ballad")
    req = dict(req, input=dict(req["input"], lyrics=short_intro))
    method_order = dict(order, method=dict(METHOD))
    plain = SD.validate_request(req, style_id="soul-ballad", client_text=CLIENT,
                                delivered_s=D, pace_plan=order, hook_plan=HOOK_PLAN)
    as_method = SD.validate_request(req, style_id="soul-ballad", client_text=CLIENT,
                                    delivered_s=D, pace_plan=method_order,
                                    hook_plan=HOOK_PLAN)
    if hasattr(R, "check_pre_erm_opening"):
        assert "PRE_ERM_SPOKEN_SHORT" in " ".join(as_method), as_method
    assert "PRE_ERM_SPOKEN_SHORT" not in " ".join(plain), plain

# ---- D10: the ONE published operator-decision order ----------------------

def _refusal_run(tmp):
    b = {"export_digest": os.urandom(32).hex(), "creative_revision": "u3-r1",
         "profile_revision": "1.0.0"}
    results = {g: {"verdict": "PASS", "binding": dict(b)}
               for g in ("D1", "D2", "D3", "D4")}
    results["D5"] = {"verdict": "FAIL", "binding": dict(b)}
    SD.record_acceptance(tmp, "v1", b, results)
    return tmp

def test_the_refusal_publishes_the_exact_operator_decision_sequence():
    with tempfile.TemporaryDirectory() as tmp:
        ref = SD.acceptance_refusal(_refusal_run(tmp), "delivery")
        assert ref is not None, "a measured FAIL must hold the boundary"
        assert SD.OPERATOR_DECISION_SEQUENCE in ref["next_action"], ref["next_action"]
        for step in ("record_acceptance", "sha256_evidence_records",
                     "measure_evidence_digest", "record_operator_decision",
                     "ACCEPTED_RISK", "gates_not_proven",
                     "music/acceptance/operator-decision.json", "--operator-decision"):
            assert step in SD.OPERATOR_DECISION_SEQUENCE, step
        assert "measured FAILs advance only through a recorded operator decision" \
            in ref["detail"], ref["detail"]

def test_a_manual_relabel_refusal_never_names_the_decision_path():
    with tempfile.TemporaryDirectory() as tmp:
        b = {"export_digest": os.urandom(32).hex(), "creative_revision": "u3-r1",
             "profile_revision": "1.0.0", "source": "manual"}
        SD.record_acceptance(tmp, "v1", b, {g: {"verdict": "PASS", "binding": dict(b)}
                                            for g in ("D1", "D2", "D3", "D4", "D5")})
        ref = SD.acceptance_refusal(tmp, "delivery")
        assert ref is not None, "a relabel never advances"
        assert "--operator-decision" not in ref["next_action"], ref["next_action"]

def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    fails = []
    for name, fn in tests:
        try:
            fn()
            print("PASS %s" % name)
        except Exception as exc:                      # noqa: BLE001 - report, do not stop
            fails.append(name)
            print("FAIL %s: %r" % (name, exc))
    print("\n%d/%d passed" % (len(tests) - len(fails), len(tests)))
    if fails:
        print("failed: %s" % ", ".join(fails))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
