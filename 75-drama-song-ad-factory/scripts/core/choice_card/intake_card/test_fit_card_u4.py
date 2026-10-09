#!/usr/bin/env python3
"""FU-U4 (plan unit U4): client lines are a contract; the STOP card lists only
real options.

  (a) a concept-mode sheet with L003 missing is refused naming L003, and a
      concept-mode brief with no packet_lines is refused outright;
  (b) the One-Check fixture at 150 s gives exit 2 with one row per style;
  (c) a card option id not in the registries raises;
  (d) the notices list includes HONK, CRUNCH, DING and the echo voice.

Run: python3 core/choice_card/intake_card/test_fit_card_u4.py
stdlib only, no network, no spend.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)

import music_director                                   # noqa: E402
import protected_names as PN                            # noqa: E402
from choice_card.intake_card import intake_card as IC   # noqa: E402
from intake_preflight import intake as INT              # noqa: E402
from lyric_writer import lyric_writer as LW             # noqa: E402
from music_styles import music_styles as MS             # noqa: E402

FIXTURE = os.path.join(CORE, "suno_recipe", "fixtures", "one-check-lyrics.txt")
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def one_check_packet():
    """The client's spoken and rap lines of the One-Check sheet as LINES.json rows."""
    packet, delivery = [], None
    for raw in open(FIXTURE, encoding="utf-8").read().splitlines():
        m = re.match(r"\[[^\]]*\((sung|spoken|rap)\)", raw)
        if m:
            delivery = m.group(1)
        elif raw.strip() and not raw.startswith("[") and delivery in ("spoken", "rap"):
            packet.append({"id": "L%03d" % (len(packet) + 1), "speaker": "x",
                           "text": raw.strip(), "scene": 1})
    return packet


def raises(fn, *needles):
    try:
        fn()
    except Exception as exc:                            # noqa: BLE001
        return all(n in str(exc) for n in needles), str(exc)[:200]
    return False, "no raise"


def test_a_concept_mode_contract():
    packet = [{"id": "L001", "text": "Girl, you ready?"}, {"id": "L002", "text": "Of course."},
              {"id": "L003", "text": "I packed OPTIONS."}]
    sheet = "[Intro (spoken): x]\nGirl, you ready?\nOf course.\n"
    ok, d = raises(lambda: music_director.build_generate_request(
        sheet, "x", "T", packet_lines=packet, mode="concept"), "L003")
    check("(a) sheet missing L003 is refused naming L003", ok, d)
    ok, d = raises(lambda: music_director.build_generate_request(
        sheet, "x", "T", mode="concept"), "PACKET_REQUIRED_IN_CONCEPT_MODE")
    check("(a) concept mode with no packet is refused", ok, d)
    lines = [{"line_id": "S001", "text": "I got you"}]
    r = LW.validate_lyrics(lines, {"mode": "concept"})
    check("(a) lyric_writer refuses concept mode with no packet",
          r["outcome"] == "rejected" and "PACKET_REQUIRED_IN_CONCEPT_MODE" in json.dumps(r), repr(r)[:200])
    r = LW.validate_lyrics(lines, {"mode": "concept", "packet_lines": packet})
    check("(a) lyric_writer names L003 when the sheet lacks it",
          r["outcome"] == "rejected" and "L003" in json.dumps(r), repr(r)[:200])
    # Control: quick mode (no mode flag) is unchanged and not refused for the packet.
    r = LW.validate_lyrics(lines, {})
    check("(a) control: no mode flag, no packet refusal",
          "PACKET_REQUIRED_IN_CONCEPT_MODE" not in json.dumps(r))
    # Control: all three lines present passes the packet check.
    full = sheet + "I packed OPTIONS.\n"
    check("(a) control: a complete sheet has no packet errors",
          PN.check_sheet(full, packet) == [])


def test_b_one_check_stop_card():
    packet = one_check_packet()
    brief = {"target_length_s": 150, "mode": "concept", "packet_lines": packet}
    card = IC.fit_card(brief, packet)
    check("(b) one row per music style",
          [r["style_id"] for r in card["rows"]] == list(MS.style_ids()), repr(card["rows"])[:200])
    check("(b) the rows carry the numbers",
          all(r["client_words"] > 250 and r["capacity_words"] > 0 and r["planned_s"] > 0
              for r in card["rows"]))
    check("(b) outcome is waiting", card["outcome"] == "waiting", card["outcome"])
    with tempfile.TemporaryDirectory() as d:
        bf, pf = os.path.join(d, "b.json"), os.path.join(d, "p.json")
        json.dump(brief, open(bf, "w"))
        json.dump(packet, open(pf, "w"))
        p = subprocess.run([sys.executable, os.path.join(CORE, "intake_preflight", "factory.py"),
                            "card", "--fit", "--brief-file", bf, "--packet-file", pf],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
    check("(b) factory.py card --fit exits 2", p.returncode == 2, "%s %s" % (p.returncode, p.stderr[-200:]))
    check("(b) the output has a row for every style",
          all(MS.style(s)["label"] in p.stdout for s in MS.style_ids()), p.stdout[:300])
    # Control: a tiny packet fits, so the check can pass.
    small = IC.fit_card({"target_length_s": 150}, [{"id": "L001", "text": "Of course."}])
    check("(b) control: a one-line packet fits (exit 0 path)", small["outcome"] == "ok")


def test_c_registry_only_options():
    packet = one_check_packet()
    card = IC.fit_card({"target_length_s": 150}, packet)
    ids = {k: [o["id"] for o in card["options"][k]] for k in ("longer_ad", "music_style", "voice")}
    check("(c) every length option is offered", set(ids["longer_ad"]) <= set(MS.OFFERED_LENGTHS_S))
    check("(c) 120 is not made up for a 150 s ad (only longer offered lengths)",
          all(x > 150 for x in ids["longer_ad"]), repr(ids))
    for kind, bad in (("longer_ad", 150), ("music_style", "synthwave"), ("voice", "echo_voice")):
        broken = json.loads(json.dumps(card))
        broken["options"][kind].append({"id": bad})
        ok, d = raises(lambda b=broken: IC.assert_registry_options(b), "FIT_CARD_OPTION_NOT_IN_REGISTRY")
        check("(c) a made-up %s option raises" % kind, ok, d)
    broken = json.loads(json.dumps(card))
    broken["options"]["fewer_words"]["id"] = "trim_it"
    ok, d = raises(lambda: IC.assert_registry_options(broken), "FIT_CARD_OPTION_NOT_IN_REGISTRY")
    check("(c) a made-up fewer_words id raises", ok, d)
    check("(c) control: the real card passes", IC.assert_registry_options(card) is card)


def test_d_notices():
    packet = [{"id": "L001", "speaker": "Friend", "text": "Girl! (HONK) you ready?"},
              {"id": "L002", "speaker": "SFX", "text": "crunch"},
              {"id": "L003", "speaker": "x", "text": "ok", "direction": "[DING] over the shot"}]
    brief = {"target_length_s": 150, "fps": 24, "voice": "echo voice on the friend",
             "packet_lines": packet}
    text = " ".join(n["text"] for n in INT.notices(brief))
    for needle in ("HONK", "CRUNCH", "DING", "echo", "150", "24"):
        check("(d) notices mention %s" % needle, needle in text, text[:300])
    check("(d) control: a clean brief has no notices",
          INT.notices({"target_length_s": 60, "packet_lines": [{"id": "L001", "text": "Hello."}]}) == [])
    r = INT.evaluate({"mode": "concept", "offer": "o", "audience": "a", "action": "b",
                      "budget_minor": 2500, "budget_currency": "USD"})
    check("(d) intake carries the mode flag and a concept brief with no packet waits",
          r["mode"] == "concept" and r["outcome"] == "waiting", "%s %s" % (r["mode"], r["outcome"]))


def main():
    for fn in (test_a_concept_mode_contract, test_b_one_check_stop_card,
               test_c_registry_only_options, test_d_notices):
        fn()
    print("FAILED: %s" % FAILS if FAILS else "ALL OK")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
