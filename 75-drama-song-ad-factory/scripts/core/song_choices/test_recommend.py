#!/usr/bin/env python3
"""Method Step 14 (METHOD-INTEGRATION F9): the three-version message RECOMMENDS
the strongest compliant version with a concrete reason.

The recommendation is built from the take's own gate results, the client still
picks, and a run that carries no gate results -- or no ``control/method.json`` --
says nothing extra.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/song_choices/test_recommend.py
No ffmpeg, no provider, no spend: the takes are bytes on disk and the runner and
the send path are injected.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for sub in ("", "intake_preflight"):
    sys.path.insert(0, os.path.join(CORE, sub))
from song_choices import song_choices as SC            # noqa: E402
from song_dispatch import song_dispatch as _SD         # noqa: E402

REQUIRED = _SD.REQUIRED_TAKE_GATES


def _gate(v):
    return _SD._gate(v)


def _receipt(gates, required=None):
    """The production constituent receipt, built by the production builder."""
    req = list(required or REQUIRED)
    full = {k: _gate("PASS") for k in req}
    full.update(gates)
    rcpt = {"verdict": "PASS", "gates": full, "required_gates": req}
    return _SD.constituent_receipt({"audio_digest": "sha-of-the-take"}, rcpt, {})


def _result(n, extra=None, status="PASS", take=True, required=None):
    gates = dict(extra or {})
    return {"n": n,
            "variant": {"id": "variant-%d" % n, "label": "LABEL %d" % n,
                        "description": "description %d" % n},
            "status": status,
            "take": ({"audio_path": "/tmp/never-read.mp3", "duration_s": 88.0} if take else None),
            "receipt": _receipt(gates, required),
            "attempt": 1, "attempts": 1, "receipts": []}


def test_recommend_picks_the_version_with_the_most_pass_gates():
    res = [_result(1, {"song_contract": _gate("FLAG")}),
           _result(2),
           _result(3, {"hook": _gate("FAIL")})]
    got = SC.recommend(res)
    assert got["n"] == 2, got
    assert got["reason"] == "it passed %d of %d song checks, the hook lands" \
        % (len(REQUIRED), len(REQUIRED)), got


def test_tie_breaks_on_the_erm_and_hero_shift_gates_then_the_hook_then_the_number():
    # 1 and 2 tie on the PASS count; 2 carries the measured music turns.
    tied = [_result(1, {"first_sung": _gate("UNMEASURED"), "pace_change": _gate("UNMEASURED")}),
            _result(2, {"first_sung": _gate("PASS"), "pace_change": _gate("PASS")})]
    assert SC.recommend(tied)["n"] == 2
    # 3 and 4 tie on the turns too; 4 carries the earned hook.
    tied2 = [_result(3, {"first_sung": _gate("PASS"), "pace_change": _gate("PASS"),
                         "hook": _gate("UNMEASURED")}),
             _result(4, {"first_sung": _gate("PASS"), "pace_change": _gate("PASS"),
                         "hook": _gate("PASS")})]
    assert SC.recommend(tied2)["n"] == 4
    # A total tie always names the same version: the lowest number.
    flat = [_result(2), _result(1), _result(3)]
    assert SC.recommend(flat)["n"] == 1
    assert SC.recommend(list(reversed(flat)))["n"] == 1


def test_the_reason_is_one_plain_concrete_line_built_from_the_gates():
    got = SC.recommend([_result(1, {"rap_audio": _gate("FAIL")}),
                        _result(2, {"pace_change": _gate("PASS"), "first_sung": _gate("PASS")})])
    assert got["n"] == 2
    assert got["reason"] == ("it passed %d of %d song checks, the ERM / Hero Shift turn gates "
                             "pass, the hook lands" % (len(REQUIRED) + 2, len(REQUIRED) + 2)), got
    assert "\n" not in got["reason"] and got["reason"].strip() == got["reason"]


def test_no_gate_results_says_nothing_extra():
    assert SC.recommend([]) is None
    assert SC.recommend(None) is None
    no_receipt = [dict(_result(1), receipt=None), dict(_result(2), receipt={})]
    assert SC.recommend(no_receipt) is None
    offered = {str(i): {"label": "%d - LABEL %d - description %d" % (i, i, i),
                        "duration": "1:28"} for i in (1, 2, 3)}
    plain = SC.client_message(offered, [3])
    assert SC.client_message(offered, [3], recommend=None) == plain
    assert "recommend" not in plain.lower()


def test_a_version_delivery_would_not_offer_is_never_recommended():
    # Version 2 has the best raw gate set but a REQUIRED gate is flagged, so its
    # receipt is not accepted and delivery will not offer it.
    res = [_result(1, {"rap_audio": _gate("FAIL")}),
           _result(2, {"length": _gate("FLAG")}),
           _result(3, {"hook": _gate("UNMEASURED")})]
    assert not SC._accepted(res[1])[0]
    assert SC.recommend(res)["n"] == 1
    # A FAILED version is never recommended either.
    assert SC.recommend([_result(1, {"rap_audio": _gate("FAIL")}),
                         dict(_result(2), status="FAILED")])["n"] == 1


def _deliver(res, method, tmp):
    """deliver_choices with a fake runner: bytes on disk, no ffmpeg, no send."""
    run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
    os.makedirs(os.path.join(deliv, "SONG-CHOICES"), exist_ok=True)
    if method:
        os.makedirs(os.path.join(run, "control"), exist_ok=True)
        with open(os.path.join(run, "control", "method.json"), "w", encoding="utf-8") as f:
            json.dump({"purpose": "campaign", "gates": {"A": "planned"}}, f)
    for r in res:
        if not r.get("take"):
            continue
        src = os.path.join(tmp, "take-%d.mp3" % r["n"])
        with open(src, "wb") as f:
            f.write(b"ID3fake-mp3-bytes")
        r["take"]["audio_path"] = src

    def runner(argv):
        shutil.copy2(argv[3], argv[-1])

    msg = SC.deliver_choices(res, deliv, run, runner=runner)
    return msg, run


def test_the_message_recommends_only_on_a_method_run_and_never_auto_picks():
    res = [_result(1), _result(2, {"pace_change": _gate("PASS"), "first_sung": _gate("PASS")}),
           _result(3, {"rap_audio": _gate("FAIL"), "sung_of_voice": _gate("FLAG")})]
    with tempfile.TemporaryDirectory() as tmp:
        plain, run = _deliver([dict(r) for r in res], method=False, tmp=tmp)
        # byte for byte the message this module has always sent
        offered = json.load(open(os.path.join(run, "song-choices", "state.json")))["offered"]
        assert plain == SC.client_message(offered, [])
        assert "recommend" not in plain.lower()
        assert "Reply 1, 2 or 3 to pick your song." in plain
        assert not os.path.exists(SC.picked_song(run))          # nothing was picked for them
    with tempfile.TemporaryDirectory() as tmp:
        msg, run = _deliver([dict(r) for r in res], method=True, tmp=tmp)
        line = ("I recommend version 2 because it passed %d of %d song checks, the ERM / Hero Shift "
                "turn gates pass, the hook lands." % (len(REQUIRED) + 2, len(REQUIRED) + 2))
        assert line in msg, msg
        # the pick line is still there, still last, and nothing was picked for them
        assert msg.index(line) < msg.index("Reply 1, 2 or 3 to pick your song.")
        assert sorted(json.load(open(os.path.join(run, "song-choices", "state.json")))["offered"]) \
            == ["1", "2", "3"]
        assert not os.path.exists(SC.picked_song(run))


def test_a_failed_version_is_neither_offered_nor_recommended():
    best = _result(2, {"pace_change": _gate("PASS"), "first_sung": _gate("PASS")})
    res = [_result(1), dict(best, status="FAILED", take=None), _result(3)]
    with tempfile.TemporaryDirectory() as tmp:
        msg, run = _deliver(res, method=True, tmp=tmp)
        # Designed absence: a FAILED take with NO audio is not presented for
        # listening, so it never reaches the failure fork either -- the client
        # message names no failed version at all. The fork wording
        # ("did not pass all of my song checks") is only for a take the client
        # can actually hear.
        assert "Version 2 did not pass all of my song checks" not in msg
        assert SC.FAILURE_FORK not in msg
        assert "I recommend version 1 because" in msg
        assert "recommend version 2" not in msg
        assert "Reply 1 or 3 to pick your song." in msg
        assert sorted(json.load(open(os.path.join(run, "song-choices", "state.json")))["offered"]) \
            == ["1", "3"]
