#!/usr/bin/env python3
"""FU-STYLE-QUESTIONS: music and video style questions explain each choice,
and the video question carries sample-video links from style_samples.json.

Run: python3 core/choice_card/intake_card/test_style_questions.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import intake_card as IC  # noqa: E402

MUSIC = next(q for q in IC.QUESTIONS if q["id"] == "music")
LOOK = next(q for q in IC.QUESTIONS if q["id"] == "look")
IDS = ["lifelike-3d", "2d-hand-painted", "sketch-to-life", "canvas-to-life", "canvas-to-3d"]
MAX_WORDS = 12     # words in an option's explanation line
MAX_ASK = 70       # characters in a question's ask line


def _samples():
    with open(os.path.join(HERE, "style_samples.json"), encoding="utf-8") as f:
        return json.load(f)


def test_every_option_has_a_short_explanation():
    for q in (MUSIC, LOOK):
        assert len(q["ask"]) <= MAX_ASK, q["ask"]
        for opt, sentence in q["options"]:
            assert sentence and len(sentence.split()) <= MAX_WORDS, (opt, sentence)
            assert len(sentence.split()) >= 4, (opt, sentence)       # says something


def test_option_order_labels_and_recommended_unchanged():
    assert [o for o, _ in MUSIC["options"]] == ["Soul Ballad", "R&B Flow", "Soul Rise"]
    assert [o for o, _ in LOOK["options"]] == [
        "Lifelike 3D", "2D Hand-Painted", "Sketch to Life (Hybrid)",
        "Canvas to Life", "Canvas to 3D"]
    assert MUSIC["recommended"] == 0 and LOOK["recommended"] == 0
    from choice_card.looks import looks as L
    assert list(L.LOOK_ORDER) == IDS            # ids and order untouched


def test_sample_table_is_well_formed():
    table = _samples()
    assert set(table) == set(IDS)
    for k, url in table.items():
        assert url is None or re.fullmatch(r"https://[^\s/]+/\S+\.mp4", url), (k, url)


def test_links_show_under_their_option_and_missing_link_shows_nothing():
    text = IC.render_step(IC.QUESTIONS.index(LOOK) + 1)
    lines = text.split("\n")
    table = _samples()
    for n, i in enumerate(IDS, 1):
        at = next(j for j, l in enumerate(lines) if l.startswith("%d. " % n))
        nxt = lines[at + 1]
        if table[i]:
            assert nxt == "   Watch: " + table[i]
        else:
            assert not nxt.startswith("   Watch")
    assert text.count("Watch: https://") == sum(1 for v in table.values() if v)
    assert "Watch: None" not in text and "Watch: null" not in text


def test_exact_sample_links():
    B = "https://assets.cdn.filesafe.space/Mct54Bwi1KlNouGXQcDX/media/"
    t = _samples()
    assert t["sketch-to-life"] == B + "923bbada-b8c2-4901-a736-8835a85605b3.mp4"
    assert t["canvas-to-3d"] == B + "9eb9ea93-2cf8-4246-935f-739d2eb576cf.mp4"
    assert t["lifelike-3d"] == B + "ceccdb53-1db7-4513-b7d5-f8da7a9cdd65.mp4"
    assert t["2d-hand-painted"] == B + "79707c0f-e255-4f3f-955a-9fed2e8e9915.mp4"
    assert t["canvas-to-life"] is None


def test_recap_reads_plainly():
    n = len(IC.QUESTIONS)
    st = IC.conversation(["1"] * 5 + ["$25"] + ["1"] * (n - 6))
    assert "Music Style: Soul Ballad" in st["message"]
    assert "Video Style: Lifelike 3D" in st["message"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    raise SystemExit(1 if fails else 0)
