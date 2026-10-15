#!/usr/bin/env python3
"""W1-card-questions-U1: PURPOSE, its one follow-up, and the AGNES question.

Prove for BUILD-PLAN.md section W1-card-questions-U1:

* every purpose gets the right follow-up and the lengths that use really offers;
* "all recommended" (and "yes") never answers PERMISSION;
* replaying the same replies twice gives the same question list;
* a remembered "no" hides AGNES, a remembered "yes" still asks;
* Agnes Yes turns VIDEO MODEL into the backup wording (same options, same prices);
* ``--run-dir`` writes control/method.json and the receipt's agnes block;
* studio-json carries ``shows_when`` and an example on every screen.

Nothing here calls a provider: the card builds text and reads one local guide.

Run: python3 -m pytest -q S75/scripts/core/choice_card/intake_card/test_purpose_agnes.py
"""
import json
import os
import sys
import types

try:                                # the empty-home CI smoke run has no pytest
    import pytest
except ModuleNotFoundError:
    # CI runs every test_*.py under scripts/core with bare python3 and a fresh
    # empty HOME, so a module-level `import pytest` is a red build there; that
    # run only imports this module and never calls the test functions, while a
    # real pytest run always has pytest importable.
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

TYPED = "Sweet Details Cookie-Decorating Class"


def _reply(q):
    """One reply the card accepts for this question, in ask order."""
    if q["id"] == "permission":
        return "1"                      # the yes that lets the order continue
    if q["id"] == "spend":
        return "$25"
    if q.get("free_text"):
        return TYPED
    return "recommended"


def _plan(purpose=None, where=None, client_dir=None, overrides=None):
    """Play a whole card the way ``conversation`` plays it, and return the
    FINAL question list with the replies that reached it. Building the list
    first and the replies second is what makes the two agree: the AGNES screen
    only exists once a length has been answered, so the list is still growing
    while the early replies are being parsed."""
    answers, qs, replies = [], IC._shaped(IC.QUESTIONS, [], client_dir), []
    overrides = dict(overrides or {})
    while len(answers) < len(qs):
        q = qs[len(answers)]
        if q["id"] == "purpose" and purpose is not None:
            r = str(purpose)
        elif q["id"] == "where" and where is not None:
            r = str(where)
        else:
            r = overrides.get(q["id"], _reply(q))
        a = IC._parse(r, q)
        assert a and "error" not in a, (r, q["id"])
        answers.append(a)
        replies.append(r)
        qs = IC._shaped(IC.QUESTIONS, answers, client_dir)
    return qs, replies


def _ids(qs):
    return [q["id"] for q in qs]


def _labels(qs, qid):
    return [o[0] for o in next(q for q in qs if q["id"] == qid)["options"]]


def _answers_for(replies, client_dir=None):
    """The answers a replay of ``replies`` produces, from a cold start."""
    answers, qs = [], IC._shaped(IC.QUESTIONS, [], client_dir)
    for r in replies:
        a = IC._parse(r, qs[len(answers)])
        assert a and "error" not in a, (r, qs[len(answers)]["id"])
        answers.append(a)
        qs = IC._shaped(IC.QUESTIONS, answers, client_dir)
    return answers


def _fake_agnes(monkeypatch, remembered, calls):
    """``agnes_access`` is its own unit of this program; stand in for it."""
    mod = types.ModuleType("agnes_access")

    class _AG:
        remembered = staticmethod(lambda client_dir: remembered)
        remember = staticmethod(lambda client_dir, answer: calls.append((client_dir, answer)))

    mod.agnes_access = _AG
    monkeypatch.setitem(sys.modules, "agnes_access", mod)


# ---------------------------------------------------------------- the flow ----
def test_purpose_is_first_and_carries_its_own_wording():
    qs, _ = _plan()
    assert _ids(qs)[0] == "purpose"
    msg = IC.render_step(1, qs)
    assert msg.splitlines()[0] == "Question 1 of %d - PURPOSE" % len(qs)
    assert "What is this video for?" in msg
    assert "(RECOMMENDED)" in msg
    assert ("I recommend option 1 (Grow my business) because one production gives "
            "you the full package: your YouTube episode, two trailers for it, and "
            "two ready-to-run ad clips for Facebook, YouTube and TikTok.") in msg
    assert msg.endswith('Reply with a number, or say "recommended".')


def test_each_purpose_gets_the_right_follow_up_and_the_right_lengths():
    # choice 1: EPISODE LENGTH is the length question, in LENGTH's own slot
    camp, _ = _plan(purpose=1)
    ids = _ids(camp)
    assert ids[0] == "purpose"
    assert "episode_length" in ids and "length" not in ids
    assert ids.index("episode_length") == ids.index("models") + 1
    assert _labels(camp, "episode_length") == [
        "3 minutes", "5 minutes", "7 minutes", "10 minutes"]
    assert "shape" in ids

    # choice 2: PERMISSION sits right after PURPOSE, and no other screen
    test, _ = _plan(purpose=2)
    assert _ids(test)[:2] == ["purpose", "permission"]
    assert "episode_length" not in _ids(test)
    assert _labels(test, "length") == [
        "60 seconds", "90 seconds", "3 minutes + 60s and 90s clips"]
    assert "shape" in _ids(test)

    # choice 3: no follow-up at all
    lesson, _ = _plan(purpose=3)
    assert "permission" not in _ids(lesson)
    assert "where" not in _ids(lesson)
    assert _labels(lesson, "length") == [
        "60 seconds", "90 seconds", "3 minutes + 60s and 90s clips"]

    # choice 4: WHERE right after PURPOSE, then the platform's own lengths
    paid, _ = _plan(purpose=4, where=1)
    assert _ids(paid)[:2] == ["purpose", "where"]
    assert _labels(paid, "length") == ["30 seconds", "60 seconds", "90 seconds"]
    plen = next(q for q in paid if q["id"] == "length")
    assert plen["options"][plen["recommended"]][0] == "60 seconds"
    assert "shape" not in _ids(paid)          # 9:16 is pinned for an ad
    free, _ = _plan(purpose=4, where=4)
    assert _labels(free, "length") == ["60 seconds", "90 seconds"]
    assert "shape" not in _ids(free)


def test_the_permission_block_is_the_wording_in_the_method_doc():
    qs, _ = _plan(purpose=2)
    lines = IC.render_step(2, qs).splitlines()
    assert lines[0] == "Question 2 of %d - PERMISSION" % len(qs)
    assert lines[1] == "Do you have your client's permission to use their testimonial?"
    assert lines[2] == "1. Yes"
    assert lines[3] == "2. No - pause this order until I have it."
    assert lines[-1] == "Reply 1 or 2."
    assert not any(l.startswith("I recommend") or "RECOMMENDED" in l for l in lines), lines


# ------------------------------------------------------------ the refusals ----
def test_all_recommended_is_refused_at_permission():
    perm = _plan(purpose=2)[0][1]
    assert perm["id"] == "permission"
    assert perm["recommended"] is None
    for reply in ("recommended", "recommend", "rec", "yes", "y", "go"):
        assert IC._parse(reply, perm) is None, reply
    assert IC._parse("2", perm)["n"] == 2
    st = IC.conversation(["2", "recommended"], purpose_flow=True)
    assert len(st["answers"]) == 1, st["answers"]
    assert "did not catch" in st["message"]
    assert "PERMISSION" in st["message"]


# ---------------------------------------------------------------- replay ------
def test_replaying_the_same_replies_twice_gives_the_same_question_list():
    qs, replies = _plan(purpose=1)
    first, second = _answers_for(replies), _answers_for(replies)
    assert first == second
    assert _ids(IC._shaped(IC.QUESTIONS, first)) == _ids(qs)
    assert _ids(IC._shaped(IC.QUESTIONS, second)) == _ids(qs)
    # and the card itself says the same thing twice
    assert IC.conversation(replies, purpose_flow=True)["message"] == \
        IC.conversation(replies, purpose_flow=True)["message"]


# ---------------------------------------------------------------- AGNES -------
def test_remembered_no_hides_the_agnes_question(monkeypatch):
    _fake_agnes(monkeypatch, "no", [])
    qs, _ = _plan(purpose=1, client_dir="/client")
    assert "agnes" not in _ids(qs)


def test_remembered_yes_and_unknown_still_ask(monkeypatch):
    for value in ("yes", "unknown"):
        _fake_agnes(monkeypatch, value, [])
        qs, _ = _plan(purpose=1, client_dir="/client")
        assert "agnes" in _ids(qs), value
        assert _ids(qs).index("agnes") == _ids(qs).index("look") + 1, value


def test_a_missing_agnes_access_is_unknown_and_loud_never_a_crash(monkeypatch):
    import loud_failure as loud
    monkeypatch.setitem(sys.modules, "agnes_access", None)
    loud.reset()
    qs, _ = _plan(purpose=1, client_dir="/client")
    assert "agnes" in _ids(qs)                       # the question is asked
    assert any(e["code"] == "AGNES_ACCESS_UNAVAILABLE" for e in loud.entries())
    loud.reset()


def test_the_agnes_question_stops_past_five_minutes(monkeypatch):
    _fake_agnes(monkeypatch, "unknown", [])
    short, _ = _plan(purpose=1, client_dir="/client",
                     overrides={"episode_length": "2"})
    assert "agnes" in _ids(short)                    # 5 minutes is still Agnes
    long, _ = _plan(purpose=1, client_dir="/client",
                    overrides={"episode_length": "4"})
    assert "agnes" not in _ids(long)                 # 7 and 10 minutes are KIE-only
    assert _labels(long, "episode_length")[3] == "10 minutes"


def test_agnes_yes_turns_the_video_model_into_the_backup(monkeypatch):
    _fake_agnes(monkeypatch, "unknown", [])
    qs, yes_replies = _plan(purpose=1, client_dir="/client", overrides={"agnes": "1"})
    assert "agnes" in _ids(qs) and "model" in _ids(qs)
    yes = IC._shaped(IC.QUESTIONS, _answers_for(yes_replies, "/client"), "/client")
    model = next(q for q in yes if q["id"] == "model")
    plain = IC._model_question("3 minutes")
    assert model["options"] == plain["options"]      # same models, same prices
    assert model["values"] == plain["values"]
    assert model["ask"].startswith(
        "Which video model should make your shots if Agnes cannot? ")

    _, no_replies = _plan(purpose=1, client_dir="/client", overrides={"agnes": "2"})
    no = IC._shaped(IC.QUESTIONS, _answers_for(no_replies, "/client"), "/client")
    assert next(q for q in no if q["id"] == "model")["ask"].startswith(
        "Which video model should make your shots? Prices are")


# ------------------------------------------------------- the run records -----
def test_run_dir_writes_method_json_and_the_agnes_block(tmp_path, monkeypatch):
    _fake_agnes(monkeypatch, "unknown", [])
    run = str(tmp_path / "run")
    os.makedirs(run)
    _, replies = _plan(purpose=4, where=1)
    assert IC.main(["--step", "--purpose-flow", "--run-dir", run, "--format", "text"]
                   + [x for r in replies for x in ("--reply", r)]
                   + ["--reply", "yes"]) == 0

    with open(os.path.join(run, "control", "method.json"), encoding="utf-8") as fh:
        method = json.load(fh)
    assert method["purpose"] == "paid_ad"
    assert method["platform"] == "meta"
    assert method["output_types"] == ["STANDALONE_SALES_EDIT"]
    assert method["chosen_length_s"] == 60
    assert isinstance(method["runtime_targets"], dict) and method["runtime_targets"]
    assert method["gates"] == {g: "planned" for g in "ABCDEF"}
    assert method["testimonial_permission"] is None

    with open(os.path.join(run, "control", "card-receipt.json"), encoding="utf-8") as fh:
        receipt = json.load(fh)
    assert receipt["agnes"] == {"answer": "yes"}
    assert receipt["storyboard_approval"] is True    # merged in, never clobbered


def test_a_testimonial_run_records_its_permission_answer(tmp_path, monkeypatch):
    _fake_agnes(monkeypatch, "unknown", [])
    run = str(tmp_path / "run")
    os.makedirs(run)
    _, replies = _plan(purpose=2)
    assert IC.main(["--step", "--purpose-flow", "--run-dir", run, "--format", "text"]
                   + [x for r in replies for x in ("--reply", r)]
                   + ["--reply", "yes"]) == 0
    with open(os.path.join(run, "control", "method.json"), encoding="utf-8") as fh:
        method = json.load(fh)
    assert method["purpose"] == "testimonial"
    assert method["platform"] is None
    assert method["output_types"] == ["MASTER_EPISODE"]
    assert method["testimonial_permission"] == "yes"


def test_permission_not_yet_waits_and_writes_nothing(tmp_path, monkeypatch):
    _fake_agnes(monkeypatch, "unknown", [])
    run = str(tmp_path / "run")
    os.makedirs(run)
    _, replies = _plan(purpose=2, overrides={"permission": "2"})
    st = IC.conversation(replies + ["yes"], questions=IC.QUESTIONS, run_dir=run,
                         purpose_flow=True)
    assert st["outcome"] == "waiting"
    assert st["reason_code"] == "testimonial-permission-pending"
    assert st["done"] is False
    assert not os.path.exists(os.path.join(run, "control", "method.json"))
    assert not os.path.exists(os.path.join(run, "control", "card-receipt.json"))


def test_the_client_agnes_answer_is_remembered(monkeypatch):
    calls = []
    _fake_agnes(monkeypatch, "unknown", calls)
    _, replies = _plan(purpose=4, where=1, client_dir="/client")
    IC.conversation(replies + ["yes"], client_dir="/client", purpose_flow=True)
    assert calls == [("/client", "yes")]


# ----------------------------------------------------------- studio export ----
def test_studio_json_carries_shows_when_and_an_example_on_every_screen(capsys):
    assert IC.main(["--format", "studio-json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    screens = payload["questions"]
    by_id = {s["id"]: s for s in screens}
    for qid in ("purpose", "episode_length", "shape", "permission", "where", "agnes"):
        assert qid in by_id, qid
    for s in screens:                       # every screen, card and conditional
        assert s["shows_when"], s["id"]
        assert s["example"], s["id"]
        assert s["question"], s["id"]
    assert by_id["purpose"]["shows_when"] == {"purpose": [1, 2, 3, 4]}
    assert by_id["episode_length"]["shows_when"] == {"purpose": [1]}
    assert by_id["shape"]["shows_when"] == {"purpose": [1, 2, 3]}
    assert by_id["permission"]["shows_when"] == {"purpose": [2]}
    assert by_id["where"]["shows_when"] == {"purpose": [4]}
    assert by_id["length"]["shows_when"] == {"purpose": [2, 3, 4]}
    assert by_id["agnes"]["shows_when"]["agnes_remembered"] == ["unknown", "yes"]
    assert by_id["agnes"]["shows_when"]["length_s_max"] == 300


def test_a_screen_without_an_example_is_still_refused(tmp_path):
    guide = tmp_path / "GUIDE.md"
    guide.write_text("## STEP 1: One\n\nSome prose, no example.\n", encoding="utf-8")
    with pytest.raises(IC.StudioExportError) as exc:
        IC.studio_json(guide=str(guide), conditional=True)
    assert "STUDIO_JSON_FIELD_MISSING" in str(exc.value)
