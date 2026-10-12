#!/usr/bin/env python3
"""U9: talk-to-a-person / send-a-question -- payload, validation, epic routing.

Checks, on the entrypoint and never on wording:

  (a) every routing fixture resolves its epic and target exactly as recorded
      (the KIND case is the negative control for the TOPIC cases);
  (b) the send is STUBBED: the recording sink is the only thing reached and a
      bomb patched onto the real transport proves it never runs;
  (c) the stub records EXACTLY what would have been sent (the openclaw argv) and
      `sent` is False;
  (d) an invalid payload is REFUSED with a named reason code, and the CLI exits
      non-zero with an empty stdout (nothing was sent);
  (e) a run_dir appends one JSON line per question, byte-identical to the record.

Run: python3 core/choice_card/intake_card/test_person_question_u9.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import person_question as PQ  # noqa: E402

SCRIPT = os.path.join(HERE, "person_question.py")
FIXTURES = os.path.join(HERE, "person_question_fixtures.json")
OPENCLAW = ["openclaw", "message", "send", "--channel", "telegram", "--target"]

def _fixtures():
    with open(FIXTURES, encoding="utf-8") as f:
        return json.load(f)

def _cli(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True)

def test_fixtures_route_exactly_as_recorded():
    cases = _fixtures()["valid"]
    assert len(cases) >= 6, cases
    for c in cases:
        payload = PQ.build(**c["input"])
        r = PQ.route(payload)
        for key, want in c["expected"].items():
            assert r[key] == want, (c["name"], key, r[key], want)

def test_kind_case_is_the_negative_control_for_the_topic_cases():
    """A topic keyword picks a topic epic; the SAME question with no keyword falls
    to the KIND epic. If topic routing were dropped, the topic cases collapse onto
    the kind/default epic and this split disappears."""
    topic = PQ.route(PQ.build("question", "Can I get a refund on the price?",
                              "a1b2c3d4e5f6"))
    assert topic["epic"] == "billing" and topic["routed_by"] == "topic", topic

def test_the_recording_sink_is_the_only_thing_reached():
    rec = PQ.deliver(PQ.build("question", "hi there", "a1b2c3d4e5f6"), run_dir=None)
    assert rec["stubbed"] is True
    assert rec["sent"] is False
    assert rec["argv"][:6] == OPENCLAW, rec["argv"][:6]

def test_the_real_transport_never_runs_even_when_the_stub_would_use_it():
    """Patch a bomb onto channel_send's default transport: if deliver ever let the
    sink default, this raises instead of silently returning a record."""
    CS = PQ._channel_send()
    original = CS._run_send

    def boom(argv):
        raise AssertionError("the real transport ran: %r" % (argv,))

    CS._run_send = boom
    try:
        rec = PQ.deliver(PQ.build("talk-to-a-person", "please call me back",
                                  "a1b2c3d4e5f6"))
        assert rec["sent"] is False and rec["stubbed"] is True
    finally:
        CS._run_send = original

def test_the_stub_records_the_exact_payload_that_would_be_sent():
    rec = PQ.deliver(PQ.build("talk-to-a-person", "  please call me back  ",
                              "a1b2c3d4e5f6", contact="ana@example.com"))
    assert rec["kind"] == "talk-to-a-person"
    assert rec["epic"] == "handoff" and rec["routed_by"] == "kind", rec
    assert rec["target"] == "inbox:handoff", rec["target"]
    assert rec["argv"][6] == "inbox:handoff"
    body = rec["argv"][8]
    assert body.startswith("TALK TO A PERSON - run a1b2c3d4e5f6"), body
    assert "Reply to: ana@example.com" in body
    assert body.endswith("\n\nplease call me back"), body   # text is stripped, kept plain

def test_target_resolves_from_the_epic_when_the_caller_names_none():
    rec = PQ.deliver(PQ.build("question", "Can I get a refund?", "a1b2c3d4e5f6"))
    assert rec["epic"] == "billing" and rec["target"] == "inbox:billing", rec

def test_invalid_fixtures_are_refused_with_a_named_reason_code():
    for c in _fixtures()["invalid"]:
        try:
            PQ.build(**c["input"])
        except PQ.QuestionError as e:
            assert e.reason_code == c["reason_code"], (c["name"], e.reason_code)
        else:
            raise AssertionError("an invalid payload was accepted: %s" % c["name"])

def test_text_too_long_is_refused():
    try:
        PQ.build("question", "x" * (PQ.MAX_TEXT + 1), "a1b2c3d4e5f6")
    except PQ.QuestionError as e:
        assert e.reason_code == "text-too-long", e.reason_code
    else:
        raise AssertionError("an over-long question was accepted")

def test_run_dir_appends_one_json_line_per_question():
    run_dir = tempfile.mkdtemp()
    rec = PQ.deliver(PQ.build("question", "one", "a1b2c3d4e5f6"), run_dir=run_dir)
    PQ.deliver(PQ.build("question", "two", "a1b2c3d4e5f6"), run_dir=run_dir)
    p = os.path.join(run_dir, "control", "person-question.jsonl")
    with open(p, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln]
    assert len(lines) == 2, lines
    assert json.loads(lines[0]) == rec            # byte-identical to the returned record
    assert all(json.loads(ln)["sent"] is False for ln in lines)

def test_cli_prints_one_record_and_exits_zero():
    p = _cli("ask", "--kind", "question", "--text", "Where is my video?",
             "--run-id", "a1b2c3d4e5f6", "--target", "555")
    assert p.returncode == 0, (p.returncode, p.stderr)
    rec = json.loads(p.stdout)
    assert rec["sent"] is False and rec["epic"] == "intake", rec

def test_cli_refuses_an_invalid_question_with_nothing_sent():
    p = _cli("ask", "--text", "   ", "--run-id", "a1b2c3d4e5f6")
    assert p.returncode == PQ.REFUSED_EXIT, (p.returncode, p.stderr)
    assert p.stdout.strip() == "", p.stdout        # nothing was sent
    assert "REFUSED empty-text" in p.stderr, p.stderr

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
