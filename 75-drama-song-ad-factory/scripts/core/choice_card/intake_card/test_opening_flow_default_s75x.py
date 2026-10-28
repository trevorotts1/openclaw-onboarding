#!/usr/bin/env python3
"""S75X-W1-U1: the opening-coaching (purpose) flow is the default for a NEW run.

Proves:

* a NEW run folder opens on PURPOSE (one plain question per message);
* confirming a new run writes control/method.json;
* a RESUMED run keeps the card it was asked with -- the old list is asked again,
  control/method.json is never created, and its saved answers are not migrated;
* a run that recorded the purpose flow (control/method.json, or the studio order
  whose screens are that flow) is replayed through the same flow, never back
  through the old list;
* the caller can still force either list with purpose_flow=True / False;
* no client-facing question in any path carries method jargon (MOS, ERM, ...);
* supplied information is reused: a saved character replaces the typed
  description, and the brief's maximum is the BUDGET's first option.

Nothing here calls a provider and nothing outside the run folders it makes is
written.

Run: python3 -m pytest -q scripts/core/choice_card/intake_card/test_opening_flow_default_s75x.py
"""
import contextlib
import io
import json
import os
import sys

try:                                # the empty-home CI smoke run has no pytest
    import pytest
except ModuleNotFoundError:
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

TYPED = "Sweet Details Cookie-Decorating Class"


def _reply(q, purpose=1, where=None):
    if q["id"] == "purpose":
        return str(purpose)
    if q["id"] == "where" and where is not None:
        return str(where)
    if q["id"] == "permission":
        return "1"
    if q["id"] == "spend":
        return "$25"
    if q.get("free_text"):
        return TYPED
    return "recommended"


def _plan(purpose=1, where=None):
    """A whole purpose-flow card: the final question list and one reply each."""
    answers, qs, replies = [], IC._shaped(IC.QUESTIONS, []), []
    while len(answers) < len(qs):
        q = qs[len(answers)]
        r = _reply(q, purpose, where)
        a = IC._parse(r, q)
        assert a and "error" not in a, (r, q["id"])
        answers.append(a)
        replies.append(r)
        qs = IC._shaped(IC.QUESTIONS, answers)
    return qs, replies


def _flatten(replies):
    return [x for r in replies for x in ("--reply", r)]


def _first_line(msg):
    return msg.splitlines()[0]


# ---------------------------------------------------------------- new run -----
def test_a_new_run_opens_on_the_opening_flow_through_the_launcher(tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    assert IC.main(["--step", "--run-dir", str(run)]) == 0
    first = capsys.readouterr().out
    assert _first_line(first) == "Question 1 of %d - PURPOSE" % len(
        IC._shaped(IC.QUESTIONS, []))
    assert "What is this video for?" in first


def test_a_new_run_folder_is_where_the_flow_turns_on():
    # the API decides from the run folder: no folder = preview, old list.
    assert IC._run_history(None) is None
    assert "OFFER" in IC.conversation([])["message"]


def test_confirming_a_new_run_writes_the_method_record(tmp_path):
    qs, replies = _plan(purpose=1)
    run = tmp_path / "run"
    run.mkdir()
    args = ["--step", "--run-dir", str(run), "--format", "session-json"]

    def turn(extra=()):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = IC.main(args + list(extra))
        state = json.loads(output.getvalue())
        assert rc == 0, state
        return state

    method_path = run / "control" / "method.json"
    state = turn()                                 # present the first exact question
    assert state["question_id"] == "purpose"
    assert not method_path.exists()
    for reply in replies:
        state = turn(["--question-id", state["question_id"],
                      "--question-digest", state["question_digest"], "--reply", reply])
        assert not method_path.exists()             # intake preferences are not approval
    assert state["question_id"] == "recap" and state["done"] is False
    assert state["answered_count"] == state["total_count"] == len(qs)
    state = turn(["--question-id", state["question_id"],
                  "--question-digest", state["question_digest"], "--reply", "yes"])
    assert state["done"] is True
    with open(os.path.join(str(run), "control", "method.json"), encoding="utf-8") as fh:
        method = json.load(fh)
    assert method["purpose"] == "campaign"
    assert method["chosen_length_s"] == 180          # the 3-minute campaign episode


def test_the_flow_asks_one_question_per_message():
    qs, replies = _plan(purpose=1)
    answers = []
    for i, r in enumerate(replies):
        msg = IC.conversation(replies[:i], purpose_flow=True)["message"]
        assert msg.count("Question ") == 1, (i, msg)
        answers.append(r)
    assert len(answers) == len(qs)


# ------------------------------------------------------------- resumed run ----
def _old_run(tmp_path):
    """A run that already used the old card: its markers and saved answers."""
    run = tmp_path / "run"
    (run / "control").mkdir(parents=True)
    (run / "control" / "state.sqlite3").write_bytes(b"SQLite format 3\x00old")
    (run / "card-answers.json").write_text(json.dumps(
        {"schema_version": 2,
         "answers": [{"id": "offer", "n": 1, "text": "Old Offer", "value": "Old Offer"}]}),
        encoding="utf-8")
    (run / "control" / "card-receipt.json").write_text(json.dumps(
        {"storyboard_approval": True, "target": "555"}, indent=2, sort_keys=True),
        encoding="utf-8")
    return run


def test_a_resumed_run_is_asked_the_card_it_started_with(tmp_path):
    run = _old_run(tmp_path)
    assert IC._run_history(str(run)) is False
    first = IC.conversation([], run_dir=str(run))["message"]
    assert _first_line(first).endswith("- OFFER")
    assert "PURPOSE" not in first


def test_a_resumed_run_is_not_migrated_or_rewritten(tmp_path):
    run = _old_run(tmp_path)
    state_bytes = (run / "control" / "state.sqlite3").read_bytes()
    st = IC.conversation(IC.example_replies() + ["yes"], run_dir=str(run))
    assert st["done"] is True
    # no purpose record was invented for the old run
    assert not (run / "control" / "method.json").exists()
    # its answers keep the old question ids: nothing was re-shaped or migrated
    saved = json.loads((run / "card-answers.json").read_text(encoding="utf-8"))
    ids = [row["id"] for row in saved["answers"]]
    assert "purpose" not in ids
    assert ids == [q["id"] for q in IC.QUESTIONS]
    # the run's own state file and target were left alone
    assert (run / "control" / "state.sqlite3").read_bytes() == state_bytes
    receipt = json.loads((run / "control" / "card-receipt.json").read_text(encoding="utf-8"))
    assert receipt["target"] == "555"


def test_a_purpose_flow_run_keeps_its_flow_on_resume(tmp_path):
    run = tmp_path / "run"
    (run / "control").mkdir(parents=True)
    (run / "control" / "method.json").write_text('{"purpose": "campaign"}', encoding="utf-8")
    assert IC._run_history(str(run)) is True
    assert _first_line(IC.conversation([], run_dir=str(run))["message"]).endswith("- PURPOSE")


def test_a_studio_order_is_a_purpose_flow_run(tmp_path):
    run = tmp_path / "run"
    (run / "control").mkdir(parents=True)
    (run / "control" / "studio-order.json").write_text('{"order_id": "o1"}', encoding="utf-8")
    assert IC._run_history(str(run)) is True


def test_the_caller_can_still_force_either_list(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    assert "OFFER" in IC.conversation([], run_dir=str(run), purpose_flow=False)["message"]
    assert "PURPOSE" in IC.conversation([], run_dir=str(run), purpose_flow=True)["message"]
    assert "OFFER" in IC.conversation([], purpose_flow=False)["message"]
    assert "PURPOSE" in IC.conversation([], purpose_flow=True)["message"]


# ------------------------------------------------------------ plain words -----
def _client_text(q):
    """Every client-facing string a question can put in front of a client."""
    out = [q.get("label"), q.get("ask"), q.get("why"), q.get("reason"),
           q.get("closing"), q.get("preface"), q.get("rec_mark")]
    out += list(q.get("recap") or [])
    for opt, sentence in q.get("options") or ():
        out += [opt, sentence]
    return [x for x in out if isinstance(x, str)]


def test_no_method_jargon_in_any_client_facing_question():
    paths = [(1, None), (2, None), (3, None), (4, 1), (4, 2), (4, 3), (4, 4)]
    seen = 0
    for purpose, where in paths:
        qs, replies = _plan(purpose, where)
        for q in qs:
            for text in _client_text(q):
                assert IC.jargon_hits(text) == [], (q["id"], text)
            seen += 1
        # the whole recap is client-facing too
        answers = []
        for i, r in enumerate(replies):
            a = IC._parse(r, qs[i])
            assert a and "error" not in a
            answers.append(a)
        assert IC.jargon_hits(IC.render_recap(answers, qs)) == []
    assert seen > 0


def test_jargon_matching_is_whole_word():
    assert IC.jargon_hits("terms and conditions") == []
    assert IC.jargon_hits("MOS") == ["MOS"]
    assert IC.jargon_hits("the ERM apex") == ["ERM"]


# ------------------------------------------------------------ reuse ----------
def test_a_saved_character_replaces_the_typed_description(tmp_path):
    from character_library import character_library as CL
    client = tmp_path / "client"
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG-fake")
    CL.save_character(str(client), "Maya Lee", "Warm, 40s, silver braids", [str(img)])

    qs = IC._with_saved_character(str(client))
    shaped = IC._shaped(qs, [])
    ids = [q["id"] for q in shaped]
    assert "saved_character" in ids
    assert "character" not in ids           # the typed description is not asked again
    # and it answers like the other picks
    q = next(q for q in shaped if q["id"] == "saved_character")
    assert IC._parse("1", q)["n"] == 1


def test_the_brief_maximum_is_reused_not_reasked():
    q = IC.spend_question(18.5, 40, True)
    shaped = IC._shaped([x for x in IC.QUESTIONS if x["id"] != "spend"] + [q], [])
    spend = next(x for x in shaped if x["id"] == "spend")
    assert spend["options"][0][0] == "Your max: $40.00"
    assert spend["options"][0][1] == "from your brief"
    assert sum(1 for x in shaped if x["id"] == "spend") == 1   # never asked twice
