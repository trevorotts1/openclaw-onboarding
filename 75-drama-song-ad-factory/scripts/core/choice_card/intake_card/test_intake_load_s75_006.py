#!/usr/bin/env python3
"""S75-006: the intake asks only what the client can answer, in plain words.

Proves the acceptance cases of the unit that cut the card down:

(a) purpose 1, with this computer's AI setup already saved and no Agnes, asks
    exactly nine questions before the recap;
(b) no client-facing question carries vendor or method jargon;
(c) CHECKPOINTS option 2 records storyboard yes, song no, script no;
(d) "ok" on MUSIC STYLE is not an answer;
(e) the Studio export reads no per-machine state: an empty home folder and one
    holding a saved AI setup and a saved Agnes answer give the same bytes;
(f) every purpose stays inside the Studio service's twenty answers per order.

Nothing here calls a provider and nothing outside its temp folders is written.

Run: python3 scripts/core/choice_card/intake_card/test_intake_load_s75_006.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)
from choice_card.intake_card import intake_card as IC  # noqa: E402
from choice_card.intake_card import ai_models as AM  # noqa: E402

SCRIPT = os.path.join(HERE, "intake_card.py")


def _client_dir(agnes="no"):
    """A client data folder with this computer's AI setup already saved."""
    d = tempfile.mkdtemp(prefix="s75-006-client-")
    AM.remember_setup(d, AM.recommended())
    if agnes:
        with open(os.path.join(d, "agnes.json"), "w", encoding="utf-8") as f:
            json.dump({"subscriber": agnes}, f)
    return d


#: One reply per question the common campaign card asks, the OFFER reply
#: carrying the web address so the address screen is never asked.
CAMPAIGN = ["1", "My course, https://example.com/course", "Women 35-55",
            "Tasha, 40, locs", "5", "1", "1", "1", "$25"]


def _walk(replies, client_dir=None):
    """The rendered question IDs and the messages, one per reply."""
    st = IC.conversation([], client_dir=client_dir, purpose_flow=True)
    asked, messages = [], []
    for i in range(len(replies)):
        head = st["message"].splitlines()[0]
        messages.append(st["message"])
        if head.startswith("Question "):
            asked.append(head.split(" - ", 1)[1])
        st = IC.conversation(replies[:i + 1], client_dir=client_dir, purpose_flow=True)
    return asked, messages, st


def test_a_the_common_campaign_asks_nine_questions_before_the_recap():
    client = _client_dir()
    asked, _, st = _walk(CAMPAIGN, client)
    assert asked == ["PURPOSE", "OFFER", "AUDIENCE", "CHARACTER", "EPISODE LENGTH",
                     "MUSIC STYLE", "VIDEO STYLE", "CHECKPOINTS", "BUDGET"], asked
    assert len(asked) == 9
    assert st["message"].startswith("Here is what you picked:"), st["message"]
    # the address arrived inside the OFFER reply and is stored beside it
    ids = [a["id"] for a in st["answers"]]
    assert "link" in ids and "offer" in ids, ids
    assert IC.conversation(CAMPAIGN + ["yes"], client_dir=client,
                           purpose_flow=True)["done"] is True


def test_b_no_question_carries_vendor_or_method_jargon():
    texts = {}

    def collect(q):
        out = [q.get("why"), q.get("ask"), q.get("reason"), q.get("closing")]
        out += list(q.get("body") or [])
        out += list(q.get("recap") or [])
        for n, opt in enumerate(q.get("options") or (), 1):
            out.append(opt[0])
            # the VIDEO MODEL and AGNES screens name the products the client is
            # choosing between, so their option details are exempt by design
            if q["id"] not in ("model", "agnes"):
                out.append(opt[1])
        texts[q["id"]] = [t for t in out if isinstance(t, str)]

    for q in (list(IC.QUESTIONS) + IC._conditional_questions()
              + IC._gate_questions() + [IC._music_full_q()]):
        collect(q)
    bad = []
    for qid, rows in texts.items():
        for text in rows:
            hits = IC.jargon_hits(text)
            if hits:
                bad.append((qid, hits, text))
    assert not bad, bad
    # the two blocked families are both covered
    assert IC.jargon_hits("OpenRouter") == ["OpenRouter"]
    assert IC.jargon_hits("the beat sheet") == ["beat sheet"]


def test_c_checkpoints_option_two_records_storyboard_yes_song_no_script_no():
    client = _client_dir()
    replies = list(CAMPAIGN)
    replies[7] = "2"                                     # CHECKPOINTS is the 8th reply
    st = IC.conversation(replies, client_dir=client, purpose_flow=True)
    qs = IC._shaped(IC.QUESTIONS, st["answers"], client)
    rq, ra = IC._record_lists(st["answers"], qs, client, {})
    rows = dict(zip((q["id"] for q in rq), ra))
    assert rows["storyboard"]["n"] == 1, rows["storyboard"]
    assert rows["song"]["n"] == 2, rows["song"]
    assert rows["script"]["n"] == 2, rows["script"]
    # and every recorded pair keeps its own position
    assert len(rq) == len(ra), (len(rq), len(ra))


def test_d_ok_on_music_style_is_not_an_answer():
    music = next(q for q in IC.QUESTIONS if q["id"] == "music")
    assert IC._parse("ok", music) is None
    assert IC._parse("yes", music) is None
    assert IC._parse("recommended", music)["n"] == 1
    # and it never advances the flow
    st = IC.conversation(["1", "My course, example.com/course", "Women", "Tasha",
                          "5", "ok"], purpose_flow=True)
    assert [a["id"] for a in st["answers"]] == ["purpose", "offer", "audience",
                                                "character", "episode_length"]


def test_e_the_studio_export_reads_no_per_machine_state():
    empty = tempfile.mkdtemp(prefix="s75-006-home-empty-")
    saved = _client_dir(agnes="yes")
    env_empty = dict(os.environ, HOME=empty, XDG_CONFIG_HOME=os.path.join(empty, "cfg"))
    env_saved = dict(os.environ, HOME=saved, XDG_CONFIG_HOME=os.path.join(saved, "cfg"))
    one = subprocess.run([sys.executable, SCRIPT, "--format", "studio-json"],
                         capture_output=True, env=env_empty, check=True).stdout
    two = subprocess.run([sys.executable, SCRIPT, "--format", "studio-json"],
                         capture_output=True, env=env_saved, check=True).stdout
    assert one == two                       # byte for byte, no machine state read
    assert json.loads(one)["format"] == "studio-json"


def test_f_every_purpose_stays_inside_the_twenty_answer_limit():
    screens = IC.studio_json(conditional=True)["questions"]
    by_id = {s["id"]: s for s in screens}
    purposes = {1: "campaign", 2: "testimonial", 3: "lesson", 4: "social"}
    for purpose in purposes:
        on = [s for s in screens if purpose in (s.get("shows_when") or {})
              .get("purpose", [])]
        # no Agnes, no saved characters: the screens this purpose can show
        assert 0 < len(on) <= 20, (purpose, [s["id"] for s in on])
    # and the card itself, shaped for each purpose, keeps its screens inside it
    for purpose in purposes:
        answers = [{"id": "purpose", "n": purpose, "text": "", "value": None}]
        if purpose == 2:
            answers.append({"id": "permission", "n": 1, "text": "Yes", "value": None})
        if purpose == 4:
            answers.append({"id": "where", "n": 1, "text": "Meta", "value": None})
        qs = IC._shaped(IC.QUESTIONS, answers)
        assert len(qs) <= 20, (purpose, [q["id"] for q in qs])
    assert by_id["checkpoints"]["shows_when"] == {"purpose": [1, 2, 3, 4]}


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
