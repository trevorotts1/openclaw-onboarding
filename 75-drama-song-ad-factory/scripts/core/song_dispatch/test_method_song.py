#!/usr/bin/env python3
"""BUILD-PLAN W1-method-song-U1 (SPEC C1/C3/C5, METHOD-INTEGRATION F3/F4).

For a METHOD run the first sung line lands at the ERM apex -- judged against
that apex, never against 15 percent of the runtime -- and a method run that
orders no pace change is refused at dispatch with PACE_TURNS_REQUIRED, or
recorded UNMEASURED at the judge when it is judged directly, which blocks.
Both pace turns are now a REQUIRED gate of every take on every run
(``_pace_required``), so an unmeasured turn never reaches PASS anywhere.

Inert until wired: a run that carries no method block keeps today's first-sung
rule and today's dispatch path.

Stdlib only, fakes only: no provider call, no spend, no media file.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/song_dispatch/test_method_song.py
"""
import os
import sys

try:
    import pytest
except ImportError:
    # CI also runs this file script-style (`python3 <file>`) under an empty
    # HOME with no third-party modules, where a module-level `import pytest`
    # is a red build. Only the later pytest step collects these tests, so the
    # real module is present exactly when it is needed.
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
import length_formula as LF        # noqa: E402
import song_dispatch as SD         # noqa: E402
import spoken_share as _SSPKG      # noqa: E402
import suno_recipe as R            # noqa: E402

#: spoken_share and song_dispatch are packages whose __init__ re-exports a fixed
#: list; the method rule and the private helpers are reached on the module
#: itself (the same shape song_dispatch uses for suno_recipe/song_contract).
SS = getattr(_SSPKG, "spoken_share", _SSPKG)
SDM = getattr(SD, "song_dispatch", SD)

CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb."]}]
LYRICS = R.render_lyrics(SHEET, "soul-ballad")
SCRIPT = "One closed door. She Found Power in the Climb."
HOOKTXT = " ".join(HOOK)
HOOK_PLAN = {"true_at_beat": "the_world"}
ERM_APEX_S = 15.0

#: the plan every test starts from: today's length plan plus its sheet/style
#: (the shape song_dispatch's judge has always been handed).
PLAN = dict(LF.plan(60, (15, 20)), sheet_text=LYRICS, style_id="soul-ballad",
            hook_plan=HOOK_PLAN)
#: the same plan carrying the run's method block (control/method.json)
METHOD = {"erm_apex_s": ERM_APEX_S, "profile": "story", "erm_window_s": [12, 18]}
METHOD_PLAN = dict(PLAN, method=dict(METHOD))


def take(first_sung_s=15.4, sung_starts=None):
    """A measured take. Only ``first_sung_s`` (and any word-level
    ``sung_starts`` the take carries) feeds the first-vocal rule."""
    out = {"segments": [{"delivery": "spoken", "start": 0.0, "end": 2.0, "source": "measured"},
                        {"delivery": "sung", "start": 15.0, "end": 45.0, "source": "measured"},
                        {"delivery": "spoken", "start": 45.0, "end": 54.0, "source": "measured"}],
           "aligned_words": [], "detector": "singing_detector 2.0.0", "duration_s": 57.5,
           "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0,
           "first_sung_s": first_sung_s}
    if sung_starts is not None:
        out["sung_starts"] = sung_starts
    return out


def judge(first_sung_s=15.4, plan=None, sung_starts=None):
    return SD.judge_take(take(first_sung_s, sung_starts),
                         PLAN if plan is None else plan, SCRIPT, HOOKTXT, (15, 20))


def _pace_order(**over):
    """A complete two-seam order (the shape pace_change.check_pace_plan wants)."""
    o = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove",
         "boundary_s": ERM_APEX_S, "return_boundary_s": 38.0}
    o.update(over)
    return {k: v for k, v in o.items() if v is not None}


# ---- the one copy of the rule (spoken_share.judge_first_vocal_at_erm) -----

def test_the_erm_rule_is_pass_inside_the_window_and_fail_on_both_sides():
    for first, verdict, direction in ((15.4, "PASS", None), (15.0, "PASS", None),
                                      (13.5, "PASS", None), (16.5, "PASS", None),
                                      (8.0, "FAIL", "early"), (13.4, "FAIL", "early"),
                                      (17.2, "FAIL", "late"), (30.0, "FAIL", "late")):
        r = SS.judge_first_vocal_at_erm(first, None, ERM_APEX_S)
        assert r["verdict"] == verdict, (first, r)
        assert r["direction"] == direction, (first, r)
        assert r["window_s"] == [13.5, 16.5], r
    assert SS.METHOD_FIRST_SUNG_TOL_S == 1.5


def test_an_earlier_sung_word_than_the_detector_figure_fails_the_early_bound():
    """The rule is on the FIRST sung word, so word-level evidence beats the
    detector's own first figure."""
    r = SS.judge_first_vocal_at_erm(15.4, [10.0, 15.4, 21.0], ERM_APEX_S)
    assert r["verdict"] == "FAIL" and r["direction"] == "early", r
    assert r["first_sung_start_s"] == 10.0, r


def test_no_apex_or_no_measured_word_is_unmeasured_never_pass():
    assert SS.judge_first_vocal_at_erm(15.4, None, None)["verdict"] == "UNMEASURED"
    assert SS.judge_first_vocal_at_erm(None, None, ERM_APEX_S)["verdict"] == "UNMEASURED"
    assert "UNMEASURED" in SS.judge_first_vocal_at_erm(15.4, None, None)["detail"]


# ---- first_sung at the ERM, on the take judge -----------------------------

def test_a_method_take_is_judged_against_the_erm_apex():
    r = judge(15.4, METHOD_PLAN)
    assert r["gates"]["first_sung"]["verdict"] == "PASS", r["gates"]["first_sung"]
    assert "ERM apex" in r["gates"]["first_sung"]["detail"], r["gates"]["first_sung"]
    assert "first_sung" not in r["failed"], r


def test_a_method_take_singing_before_the_erm_fails_early():
    r = judge(8.0, METHOD_PLAN)
    assert r["gates"]["first_sung"]["verdict"] == "FAIL", r["gates"]["first_sung"]
    assert "early" in r["gates"]["first_sung"]["detail"], r["gates"]["first_sung"]
    assert "first_sung" in r["failed"], r
    assert r["verdict"] == "FAIL", r


def test_a_method_take_singing_after_the_erm_window_fails_late():
    r = judge(17.2, METHOD_PLAN)
    assert r["gates"]["first_sung"]["verdict"] == "FAIL", r["gates"]["first_sung"]
    assert "late" in r["gates"]["first_sung"]["detail"], r["gates"]["first_sung"]
    assert "first_sung" in r["failed"], r
    assert r["verdict"] == "FAIL", r


def test_the_erm_apex_comes_from_the_run_s_pacing_profile_read_off_the_plan():
    """SPEC B4: ``feed`` compresses the ERM to 15 percent of the runtime,
    ``story`` uses the method window's midpoint; nothing here keeps a table."""
    feed = dict(PLAN, method={"profile": "feed"})
    assert judge(9.0, feed)["gates"]["first_sung"]["verdict"] == "PASS"
    assert judge(15.0, feed)["gates"]["first_sung"]["verdict"] == "FAIL"
    window = dict(PLAN, method={"erm_window_s": [12, 18]})
    assert judge(15.4, window)["gates"]["first_sung"]["verdict"] == "PASS"
    # an explicit apex always wins
    explicit = dict(PLAN, method={"erm_apex_s": 20.0, "profile": "feed"})
    assert judge(20.0, explicit)["gates"]["first_sung"]["verdict"] == "PASS"


def test_a_method_plan_that_names_no_erm_apex_blocks_the_take():
    r = judge(15.4, dict(PLAN, method={"profile": "story"}))
    assert r["gates"]["first_sung"]["verdict"] == "UNMEASURED", r["gates"]["first_sung"]
    assert "erm_apex_s" in r["gates"]["first_sung"]["detail"], r["gates"]["first_sung"]
    assert r["verdict"] != "PASS", r


def test_a_plan_without_a_method_block_keeps_todays_first_sung_rule():
    """The 15 percent of runtime target, judged late only -- unchanged."""
    assert judge(8.0)["gates"]["first_sung"]["verdict"] == "PASS"
    assert judge(9.0)["gates"]["first_sung"]["verdict"] == "PASS"
    # the 15.4 s take a method run would PASS is late under the old rule:
    # that is exactly the conflict C1 this unit resolves, and it stays as it
    # was for a run that carries no method block.
    for first in (15.4, 30.0):
        late = judge(first)
        assert late["gates"]["first_sung"]["verdict"] == "FAIL", first
        assert "first_sung" in late["failed"], first


# ---- both pace turns are mandatory on every run ---------------------------

def test_pace_is_required_on_every_run():
    assert SDM._pace_required({}, {}) is True
    assert SDM._pace_required(PLAN, take()) is True


def test_a_method_plan_with_no_pace_order_records_unmeasured_and_blocks():
    r = judge(15.4, METHOD_PLAN)
    g = r["gates"]["pace_change"]
    assert g["verdict"] == "UNMEASURED", g
    assert "PACE_TURNS_REQUIRED" in g["detail"], g
    assert "pace_change" in r["required_gates"], r["required_gates"]
    assert "pace_change" in r["flagged"] and "pace_change" not in r["failed"], r
    assert r["verdict"] != "PASS", r


def test_a_method_plan_with_an_order_is_measured_not_refused():
    r = judge(15.4, dict(METHOD_PLAN, pace_change=_pace_order()))
    g = r["gates"]["pace_change"]
    assert "PACE_TURNS_REQUIRED" not in g["detail"], g
    assert g["verdict"] in ("UNMEASURED", "FAIL", "PASS"), g     # no pace evidence on this fake take


def test_a_method_run_with_no_pace_order_is_refused_at_dispatch():
    """METHOD C5: the refusal is at dispatch, before any generation."""
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)
    with pytest.raises(SD.DispatchError) as exc:
        SD.run_takes(req, dict(METHOD_PLAN), lambda rq: [], lambda t: {}, lambda t, r: None,
                     SCRIPT, HOOKTXT, (15, 20), cap_cents=6)
    assert "PACE_TURNS_REQUIRED" in str(exc.value), str(exc.value)


def test_a_run_without_a_method_block_is_refused_at_dispatch_too():
    """BUILD-PLAN W1-method-song-U1 (Trevor 2026-10-13): the acceptance says
    `_pace_required` is True on EVERY run, so a run missing the pace order is
    refused at dispatch with PACE_TURNS_REQUIRED -- method AND non-method
    alike. The old non-method exception (dispatch on, gate only) is gone: the
    two turns are mandatory wherever the run sits. Unrelated method-only
    behaviour (the first-sung ERM rule, the blueprint anchor names) stays
    inert-until-wired and is untouched here."""
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)
    with pytest.raises(SD.DispatchError) as exc:
        SD.run_takes(req, dict(PLAN), lambda rq: [], lambda t: {}, lambda t, r: None,
                     SCRIPT, HOOKTXT, (15, 20), cap_cents=6)
    assert "PACE_TURNS_REQUIRED" in str(exc.value), str(exc.value)


def test_a_non_method_run_with_an_order_reaches_generation():
    """Known-good control for the refusal above: a run carrying no method
    block but a complete pace order dispatches, reaches generation, keeps its
    pace gate required, and the internal _pace_plan never reaches KIE."""
    order = _pace_order()
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN,
                          pace_plan=order)
    sent = []
    out = SD.run_takes(req, dict(PLAN, pace_change=order),
                       lambda rq: sent.append(rq) or [take(15.4), take(15.4)],
                       lambda t: {}, lambda t, r: None, SCRIPT, HOOKTXT, (15, 20), cap_cents=6)
    assert len(sent) == 1, sent
    assert "_pace_plan" not in sent[0] and "_pace_plan" not in sent[0]["input"], sent[0]
    assert out["spent_cents"] == 6, out
    gates = out["receipts"][0]["gates"]
    assert "pace_change" in gates, gates
    assert gates["pace_change"]["verdict"] != "PASS"      # no measured pace audio on this fake take


def test_a_non_method_plan_judged_directly_with_no_order_blocks_too():
    """The judge half of the same rule: no order at all may never be read as
    "nothing to enforce", because that verdict is a PASS."""
    r = judge(15.4, PLAN)
    g = r["gates"]["pace_change"]
    assert g["verdict"] == "UNMEASURED", g
    assert "PACE_TURNS_REQUIRED" in g["detail"], g
    assert "pace_change" in r["required_gates"], r["required_gates"]
    assert "pace_change" in r["flagged"] and "pace_change" not in r["failed"], r
    assert r["verdict"] != "PASS", r


def test_the_same_method_request_with_an_order_reaches_generation():
    """Known-good control: the refusal is about the missing order, nothing else."""
    order = _pace_order()
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=PLAN["hook_plan"],
                          pace_plan=order)
    sent = []
    out = SD.run_takes(req, dict(METHOD_PLAN, pace_change=order),
                       lambda rq: sent.append(rq) or [take(15.4), take(15.4)],
                       lambda t: {}, lambda t, r: None, SCRIPT, HOOKTXT, (15, 20), cap_cents=6)
    assert len(sent) == 1, sent
    assert "_pace_plan" not in sent[0] and "_pace_plan" not in sent[0]["input"], sent[0]
    assert out["spent_cents"] == 6, out
