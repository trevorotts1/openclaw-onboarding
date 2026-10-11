#!/usr/bin/env python3
"""U1 (WW-08, WW-18, WW-07, WW-16, WW-09, WW-14) negative controls.

Run: python3 core/song_dispatch/test_song_dispatch_ww_u1.py

Every test drives the REAL judge / choices / delivery paths (never a helper in
isolation), with a fake transport and zero provider calls. Each new rule has a
NEGATIVE CONTROL -- the input that passes today but must now be refused.
"""
import inspect
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))
sys.path.insert(0, os.path.join(CORE, "intake_preflight"))

import length_formula as LF                       # noqa: E402
from song_dispatch import song_dispatch as SD     # noqa: E402  (the module, not the package)
from song_choices import song_choices as SC       # noqa: E402
from suno_recipe import suno_recipe as R          # noqa: E402
import factory as F                                # noqa: E402  intake_preflight

CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
SCRIPT = "One closed door. She Found Power in the Climb. Get the book. Link below."
HOOKTXT = " ".join(HOOK)


def _req():
    return R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)


def _plan(**kw):
    req = _req()
    return dict(LF.plan(60, (15, 20)), sheet_text=req["input"]["lyrics"], style_id="soul-ballad",
                hook_plan=HOOK_PLAN, **kw)


def _suno_words(lyrics):
    out = []
    for block in lyrics.split("\n\n"):
        head, *lines = block.split("\n")
        toks = " ".join(lines).split() or [""]
        out += [{"word": (head + "\n" + t + " ") if k == 0 else t + " "} for k, t in enumerate(toks)]
    return out


def _good_take(**over):
    words = [dict(w, startS=3 + i * 1.0, endS=3.5 + i * 1.0)
             for i, w in enumerate(_suno_words(_req()["input"]["lyrics"]))]
    take = {"segments": [{"delivery": "spoken", "start": 0, "end": 2, "source": "measured"},
                         {"delivery": "sung", "start": 2.5, "end": 45, "source": "measured"},
                         {"delivery": "spoken", "start": 45, "end": 54, "source": "measured"}],
            "aligned_words": words, "detector": "singing_detector 2.0.0", "duration_s": 57.5,
            "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0, "first_sung_s": 2.5}
    take.update(over)
    return take


def _judge(take, plan=None, style_id="soul-ballad", sheet_text=None):
    plan = plan if plan is not None else _plan()
    return SD.judge_take(take, plan, SCRIPT, HOOKTXT, (15, 20), style_id,
                         sheet_text if sheet_text is not None else plan["sheet_text"])


# ---- WW-08: every required gate runs; the vocabulary is TOTAL ---------------

def test_ww08_the_story_gate_is_called_from_the_take_judge():
    """WW-08 item 1 + the wiring control: judge_take must CALL
    check_returned_story. Removing the invocation must break this."""
    inner = inspect.getsource(SD._judge_take_inner)
    story = inspect.getsource(SD._story_gate)
    assert "_story_gate(" in inner, "judge_take no longer runs the story gate (WW-08)"
    assert "check_returned_story" in story, \
        "the story gate no longer calls check_returned_story (WW-08)"


def test_ww08_a_declared_story_revision_with_a_late_plot_line_fails():
    """The stored take's shape: the plot line is late, so the story gate FAILs
    and the take is never delivered (this passed the old 15%-of-D rule)."""
    plan = _plan(story_revision="rev-1")
    take = _good_take(aligned_words=[dict(w, startS=30 + i, endS=30.5 + i)
                                     for i, w in enumerate(_suno_words(_req()["input"]["lyrics"]))])
    rc = _judge(take, plan)
    assert rc["gates"]["story"]["verdict"] == "FAIL", rc["gates"]["story"]
    assert rc["verdict"] != "PASS"
    assert not SD.take_accepted(rc)[0]


def test_ww08_empty_gate_set_never_passes():
    rc = SD._finish({})
    assert rc["verdict"] == "FAIL" and rc["gates"] == {}


def test_ww08_every_non_pass_verdict_blocks_once_it_is_required():
    """FAIL, FLAG, UNMEASURED, UNAVAILABLE and UNKNOWN all block when the gate
    is required; a raised exception and a missing gate block too."""
    base = _plan().get("words")
    for verdict in ("FAIL", "FLAG", "UNMEASURED", "UNAVAILABLE", "UNKNOWN"):
        rc = SD._finish({"detector": {"verdict": verdict, "detail": "injected"},
                         "clean_ending": {"verdict": "PASS"}},
                        required=("detector", "clean_ending"))
        assert rc["verdict"] != "PASS", verdict
        ok, _why = SD.take_accepted(rc)
        assert not ok, verdict
        assert base is not None
    # a MISSING required gate
    rc = SD._finish({"detector": {"verdict": "PASS"}}, required=("detector", "clean_ending"))
    assert rc["gates"]["clean_ending"]["verdict"] == "UNMEASURED"
    assert not SD.take_accepted(rc)[0]
    # a gate that is not even a mapping (an exception record)
    rc = SD._finish({"detector": "boom"}, required=("detector",))
    assert not SD.take_accepted(rc)[0]


def test_ww08_a_gate_that_raises_blocks_the_judge():
    """An exception anywhere inside the take judge keeps the take off PASS."""
    def _boom(*a, **kw):
        raise RuntimeError("transport exploded")
    old = SD._judge_take_inner
    SD._judge_take_inner = _boom
    try:
        rc = _judge(_good_take())
    finally:
        SD._judge_take_inner = old
    assert rc["verdict"] != "PASS" and not SD.take_accepted(rc)[0]

    class _Boom:
        def gate(self, *a, **kw):
            raise RuntimeError("transport exploded")
    old_g = SD._RC.gate
    SD._RC.gate = _Boom().gate
    try:
        # a rap-delivering style runs the rap gate; it raises here
        rc = _judge(_good_take(), _plan(), style_id="rnb-flow")
    finally:
        SD._RC.gate = old_g
    assert rc["verdict"] != "PASS" and not SD.take_accepted(rc)[0]


def test_ww08_a_constituent_receipt_is_recorded_and_checked():
    rc = _judge(_good_take())
    rec = SD.constituent_receipt(_good_take(), rc, _plan())
    assert rec["schema"] == SD._QC.CONSTITUENT_SCHEMA
    assert rec["checker"] == "song_dispatch" and rec["accepted"] is True
    assert SD.constituent_ok(rec)[0]
    # a blocked receipt never counts, and neither does a missing one
    bad = SD._finish({"detector": {"verdict": "FAIL"}}, required=("detector",))
    rec2 = SD.constituent_receipt(_good_take(), bad, _plan())
    assert rec2["accepted"] is False and not SD.constituent_ok(rec2)[0]
    assert not SD.constituent_ok(None)[0]


# ---- WW-18: the block reaches the DELIVERY boundary ------------------------

def _mp3(path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=1", path], check=True, capture_output=True)


def _result(n, variant_id, take, accepted):
    rc = _judge(take)
    return {"n": n, "variant": {"id": variant_id, "label": variant_id.upper(),
                                "description": "d"},
            "status": rc["verdict"], "take": take,
            "receipt": SD.constituent_receipt(take, rc, _plan()) if accepted
            else SD.constituent_receipt(take, SD._finish({"detector": {"verdict": "FAIL"}},
                                                         required=("detector",)), _plan()),
            "receipts": [rc]}


def _three(tmp, bad_required_gate=False):
    rows = []
    for i, vid in enumerate(("polished-modern", "warm-live-band", "cinematic-strings")):
        p = os.path.join(tmp, "%s.mp3" % vid)
        _mp3(p)
        take = _good_take(audio_path=p)
        if bad_required_gate and i == 0:
            take["clean_ending"] = None            # a required gate FAILs on take 1
        rows.append(_result(i + 1, vid, take, accepted=not (bad_required_gate and i == 0)))
    return rows


def test_ww18_deliver_choices_refuses_a_take_whose_required_gate_failed():
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        results = _three(tmp, bad_required_gate=True)
        SC.deliver_choices(results, deliv, run)
        offered = json.load(open(os.path.join(run, "song-choices", "state.json")))["offered"]
        assert "1" not in offered, "the take whose required gate failed was offered"
        assert "2" in offered and "3" in offered


def test_ww18_record_pick_refuses_a_blocked_receipt():
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        results = _three(tmp)
        SC.deliver_choices(results, deliv, run)
        state = json.load(open(os.path.join(run, "song-choices", "state.json")))
        state["offered"]["1"]["receipt"] = SD.constituent_receipt(
            _good_take(), SD._finish({"detector": {"verdict": "UNMEASURED"}},
                                     required=("detector",)), _plan())
        SC._write(run, "state.json", state)
        try:
            SC.record_pick(run, "1")
        except SC.ChoiceError:
            pass
        else:
            raise AssertionError("a blocked constituent receipt was picked")
        assert SC.record_pick(run, "2").startswith("2")


def test_ww18_an_all_pass_take_is_offered_and_the_gate_holds_later_spend():
    with tempfile.TemporaryDirectory() as tmp:
        run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
        SC.deliver_choices(_three(tmp), deliv, run)
        assert SC.constituent_hold(run) is None
        # a blocked offered receipt closes the gate at the next paid stage
        state = json.load(open(os.path.join(run, "song-choices", "state.json")))
        state["offered"]["1"]["receipt"] = {"schema": SD._QC.CONSTITUENT_SCHEMA,
                                            "accepted": False, "blocked": ["x"]}
        SC._write(run, "state.json", state)
        assert SC.constituent_hold(run)["reason_code"] == "SONG_CONSTITUENT_EVIDENCE_MISSING"
        assert SC.dispatch_refusal(False, run) is not None
        assert SC.dispatch_refusal(True, run) is None       # the song stage itself may run


# ---- WW-07: the pace direction reaches the FINAL provider style ------------

def test_ww07_the_payload_carries_the_drop_and_return_after_the_ending():
    pace = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove"}
    req = R.build_request("rnb-flow", SHEET[:1] + SHEET[1:], CLIENT, "T", 58,
                          hook_plan=HOOK_PLAN, delivered_s=58, pace_plan=pace)
    style = req["input"]["style"]
    assert "half-time" in style and "thin" in style and "rise back" in style
    # AFTER the ending and the hook-placement order clause
    assert style.index("half-time") > style.index(R._EQ.STYLE_ENDING)
    assert style.index("half-time") > style.index(R._HP.PROMPT_CLAUSE)
    assert len(style) <= R.SUNO_STYLE_FIELD_MAX
    # the internal pace metadata never reaches the payload
    assert "_pace_plan" not in req and "_hook_plan" not in req


def test_ww07_the_assembled_variant_styles_all_carry_the_pace_clause_last():
    """WW-07: what SHIPS is the assembled three-variant provider style, so the
    drop and the return are asserted on ``request["input"]["style"]`` from
    song_choices.build_requests -- never on the recipe's style_text alone. On
    every variant the pace clause must come AFTER the ending clause and AFTER
    that variant's own ARRANGEMENT clause."""
    pace = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove"}
    reqs = SC.build_requests("soul-ballad", SHEET, CLIENT, "T", 58,
                            hook_plan=HOOK_PLAN, pace_plan=pace)
    assert len(reqs) == 3 and len({v["id"] for v, _ in reqs}) == 3
    for v, rq in reqs:
        style = rq["input"]["style"]
        clause = v["clause"].rstrip(".")
        assert "half-time" in style and "rise back" in style, (v["id"], style)
        assert style.index("half-time") > style.index(R._EQ.STYLE_ENDING), v["id"]
        assert style.index(clause) < style.index("half-time"), (v["id"], style[-240:])
        assert style.index("half-time") < style.index("rise back"), (v["id"], style[-240:])
        # the return is the LAST clause of the assembled provider style
        assert style.rstrip().rstrip(".").endswith(pace["return"].rstrip(".")), \
            (v["id"], style[-240:])
        assert len(style) <= R.SUNO_STYLE_FIELD_MAX
        assert rq["_pace_plan"] == pace          # rides to the judge, never to KIE


def test_ww07_no_pace_plan_means_no_clause_and_an_over_cap_append_raises():
    plain = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)
    assert "half-time" not in plain["input"]["style"]
    assert "_pace_plan" not in plain
    # an over-cap append raises STYLE_TOO_LONG rather than truncating
    huge = {"drop": "x" * R.SUNO_STYLE_FIELD_MAX, "return": "y" * 200}
    try:
        R.style_text("soul-ballad", SHEET, "f", pace_plan=huge)
    except R.RecipeError as e:
        assert "STYLE_TOO_LONG" in str(e)
    else:
        raise AssertionError("an over-cap pace append was truncated, not refused")


def test_ww07_the_director_envelope_writes_the_same_clause_and_bundles_it():
    import music_director
    lyrics = R.render_lyrics(SHEET, "soul-ballad")
    style = R.style_text("soul-ballad", SHEET, "f")
    pace = {"drop": "half-time drop, thin drums", "return": "turn and rise back"}
    req = music_director.build_generate_request(lyrics, style, "T", style_id="soul-ballad",
                                                client_text=CLIENT, length_s=58,
                                                true_at_beat=HOOK_PLAN["true_at_beat"],
                                                hook_plan=HOOK_PLAN, pace_plan=pace)
    assert "half-time" in req["input"]["style"]
    assert req["_pace_plan"] == pace and "_pace_plan" not in req["input"]


# ---- WW-16: the opening vocalise cue is BOUNDED ----------------------------

def test_ww16_a_declared_long_opening_cue_is_refused_before_spend():
    bad = [dict(SHEET[0]), {"tag": "Vocalise", "delivery": "sung",
                            "cue": "wordless, full melodic voice, two very long held notes",
                            "lines": ["Oo-o-o-o-o-oh,"]}] + SHEET[2:]
    errs = R.check_lyric_sheet(bad, CLIENT, 58, None)
    assert any("opening vocalise cue" in e for e in errs), errs
    assert R.check_opening_vocalise_cue("two very long held notes") is not None
    assert R.check_opening_vocalise_cue("four held notes") is not None
    assert R.check_opening_vocalise_cue("one note, 6 seconds") is not None


def test_ww16_a_short_declared_lead_in_cue_passes():
    ok = [dict(SHEET[0]), {"tag": "Vocalise", "delivery": "sung",
                           "cue": "wordless, brief lead-in, one short note",
                           "lines": ["Oo-o-o-o-o-oh,"]}] + SHEET[2:]
    assert R.check_opening_vocalise_cue("wordless, brief lead-in") is None
    assert R.check_opening_vocalise_cue(None) is None and R.check_opening_vocalise_cue("") is None
    assert [e for e in R.check_lyric_sheet(ok, CLIENT, 58, None)
            if "opening vocalise" in e] == []


# ---- WW-09: the recorded answer keeps its provenance ----------------------

def test_ww09_explicit_answers_are_honoured_and_none_are_read_as_no():
    assert SC.classify_song_answer([{"id": "song", "n": 1}])[0] is True
    assert SC.classify_song_answer([{"id": "song", "n": 2}])[0] is False     # explicit No stays No
    # a MISSING answer is never read as No
    missing, prov, why = SC.classify_song_answer([{"id": "music", "n": 1}])
    assert missing is True and why and prov["unknown"] is True
    # a CORRUPT answer is never read as No
    assert SC.classify_song_answer([{"id": "song", "n": 9}])[0] is True
    # an AUTHOR-LESS delegated answer (another channel, no author) is unspecified
    delegated, _p, _w = SC.classify_song_answer([{"id": "song", "n": 2, "channel": "assistant"}])
    assert delegated is True


def test_ww09_provenance_is_recorded_in_the_run_state():
    with tempfile.TemporaryDirectory() as tmp:
        SC.record_card_answer(tmp, [{"id": "song", "n": 2, "who": "client", "at": "2026-10-11T00:00Z"}],
                              target="chat-1")
        st = json.load(open(os.path.join(tmp, "song-choices", "state.json")))
        assert st["required"] is False and st["provenance"]["who"] == "client"
        assert st["provenance"]["channel"] == "card"


def test_ww09_empty_production_defaults_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "req.json")
        req = _req()
        json.dump({"style_id": "soul-ballad", "client_text": CLIENT, "title": "T",
                   "length_s": 58, "hook_plan": HOOK_PLAN,
                   "input": {"lyrics": req["input"]["lyrics"], "duration": 58,
                             "vocal_gender": "f"}},
                  open(p, "w"))
        a = _NS(run_dir=tmp, request=p)
        for kw in ({}, {"measure": lambda t: {}}, {"save": lambda v, t, r: None}):
            try:
                SC.cmd_generate(a, **kw)
            except SC.ChoiceError as e:
                assert "REFUSED" in str(e)
            else:
                raise AssertionError("an empty production default was accepted: %r" % (kw,))


class _NS:
    def __init__(self, **kw):
        self.run_dir = kw["run_dir"]
        self.request = kw["request"]
        self.ledger = ""
        self.run_id = "R"
        self.variant = ""
        self.unit_id = ""


# ---- WW-14: the per-variant clause, worded as the contract words it --------

def test_ww14_the_per_variant_clause_is_present_and_the_counts_agree():
    src = open(os.path.join(HERE, "song_dispatch.py"), encoding="utf-8").read()
    assert "per variant; three variants run in parallel lanes" in src
    assert SC.PROVIDER_SLOTS == 3 and SC.RESERVE == 0
    assert len(SC.UNIT_IDS) == 3


def test_ww14_factory_next_routes_the_yes_answer_to_the_runner():
    with tempfile.TemporaryDirectory() as tmp:
        run = os.path.join(tmp, "run")
        os.makedirs(os.path.join(run, "control"))
        import sqlite3
        with sqlite3.connect(os.path.join(run, "control", "state.sqlite3")) as con:
            con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT)")
            for s in ("research", "creative-strategy", "script-lyrics", "music"):
                con.execute("INSERT INTO stages VALUES('R', ?, 'COMPLETE')", (s,))
        SC.init(run, True)
        sc = F._song_choices_next(run, orchestrated=False)
        assert sc is not None and "song_choices.py generate" in sc["command"]
        assert len(sc["units"]) == 3


def main():
    fails = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   %s" % name)
            except Exception as exc:               # noqa: BLE001
                fails.append("%s: %r" % (name, exc))
                print("FAIL %s: %r" % (name, exc))
    if fails:
        print("\n%d FAILED" % len(fails))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
