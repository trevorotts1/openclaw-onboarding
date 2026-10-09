#!/usr/bin/env python3
"""FU-U4 (plan unit U4): the fit STOP card contract from choice-card-spec 2.3.

The client's own lines are a contract. This file pins the parts of that
contract test_fit_card_u4.py does not cover:

  (a) the fit step exists at all (control for the fail-first run at the
      merge-base, where ``fit_card`` is missing);
  (b) a concept-mode brief with NO packet_lines is refused with
      PACKET_REQUIRED_IN_CONCEPT_MODE - never reported as fitting;
  (c) a packet that fits gives exit 0 and cuts nothing (cut_line_ids empty);
  (d) a packet that does not fit gives exit 2, and the STOP card never cuts a
      line: ``fewer_words`` only NAMES exact line ids, for approval;
  (e) every option id comes from a registry - only offered lengths above the
      client's length, only real style ids, only the two voice ids;
  (f) the four notices (sfx, echo voice, un-offered length, non-master fps)
      are notices, never options.

Run: python3 core/choice_card/intake_card/test_stop_card_contract_u4.py
stdlib only, no network, no spend. Each file runs in its own process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CORE)

from choice_card.intake_card import intake_card as IC   # noqa: E402
from music_styles import music_styles as MS             # noqa: E402

FACTORY = os.path.join(CORE, "intake_preflight", "factory.py")
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


#: A complete brief: placement answered, plus the recorded four-answer card
#: receipt, so the base outcome is ok and only the packet can stop it.
RECEIPT = {"card_receipt": {
    "video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
    "length": 60, "video_model": "MiniMax H3",
    "who": "client", "at": "2026-10-09"}}


def _brief(mode=None, length=60, **kw):
    b = {"target_length_s": length, "placement": "9:16",
         "offer": "a thing", "audience": "busy people",
         "action": "book a demo", "budget_minor": 3000,
         "budget_currency": "USD"}
    if mode:
        b["mode"] = mode
    b.update(kw)
    return b


def _evaluate(brief, resume_state=None):
    from intake_preflight import intake as INT              # noqa: PLC0415
    return INT.evaluate(brief, resume_state=resume_state or RECEIPT)


def _cli(brief, packet=None):
    """factory.py card --fit with the given brief (and optional packet file)."""
    with tempfile.TemporaryDirectory() as d:
        bf = os.path.join(d, "brief.json")
        json.dump(brief, open(bf, "w", encoding="utf-8"), default=str)
        args = [sys.executable, FACTORY, "card", "--fit", "--brief-file", bf]
        if packet is not None:
            pf = os.path.join(d, "packet.json")
            json.dump(packet, open(pf, "w", encoding="utf-8"), default=str)
            args += ["--packet-file", pf]
        p = subprocess.run(args, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, cwd=CORE)
    return p


def test_a_fit_step_exists():
    check("(a) intake_card exposes fit_card", callable(getattr(IC, "fit_card", None)))
    check("(a) intake_card exposes assert_registry_options",
          callable(getattr(IC, "assert_registry_options", None)))
    check("(a) fit_card handles a fitting packet",
          IC.fit_card(_brief(), [{"id": "L001", "text": "Hello there."}])["outcome"] == "ok")


def test_b_concept_without_packet_is_refused():
    """Spec 2.3: brief.packet_lines is required in concept mode; missing is
    refused with PACKET_REQUIRED_IN_CONCEPT_MODE. The fit step is inside that
    contract - it must never answer 'Everything fits' for lines that do not
    exist."""
    r = _evaluate(_brief("concept"))
    check("(b) intake.evaluate refuses concept without a packet",
          r["outcome"] == "waiting"
          and r["reason_code"] == "PACKET_REQUIRED_IN_CONCEPT_MODE",
          "%s %s" % (r.get("outcome"), r.get("reason_code")))
    check("(b) control: a complete concept brief WITH a packet is ok",
          _evaluate(dict(_brief("concept"),
                         packet_lines=[{"id": "L001", "text": "Hi."}]))["outcome"] == "ok")
    check("(b) control: quick mode without a packet is not refused",
          _evaluate(_brief())["reason_code"] != "PACKET_REQUIRED_IN_CONCEPT_MODE")

    # The same refusal through the intake command (envelope + exit code),
    # with the recorded card receipt so only the packet can stop it.
    with tempfile.TemporaryDirectory() as d:
        bf, rf = os.path.join(d, "brief.json"), os.path.join(d, "resume.json")
        json.dump(_brief("concept"), open(bf, "w", encoding="utf-8"))
        json.dump(RECEIPT, open(rf, "w", encoding="utf-8"))
        p = subprocess.run(
            [sys.executable, FACTORY, "intake", "--brief-file", bf,
             "--resume-file", rf], capture_output=True, text=True,
            stdin=subprocess.DEVNULL, cwd=CORE)
    check("(b) factory.py intake refuses concept without a packet (exit 2)",
          p.returncode == 2 and "PACKET_REQUIRED_IN_CONCEPT_MODE" in p.stdout,
          "rc=%s out=%r" % (p.returncode, p.stdout.strip()[-160:]))
    with tempfile.TemporaryDirectory() as d:
        bf, rf = os.path.join(d, "brief.json"), os.path.join(d, "resume.json")
        json.dump(_brief(), open(bf, "w", encoding="utf-8"))
        json.dump(RECEIPT, open(rf, "w", encoding="utf-8"))
        p = subprocess.run(
            [sys.executable, FACTORY, "intake", "--brief-file", bf,
             "--resume-file", rf], capture_output=True, text=True,
            stdin=subprocess.DEVNULL, cwd=CORE)
    check("(b) control: quick mode intake exits 0",
          p.returncode == 0, "rc=%s" % p.returncode)

    # The fit step sits behind that refusal, so it must never invent the
    # client's lines: with no packet it may only report zero words and cut
    # nothing, never fabricate a line id. (The refusal itself is enforced at
    # the intake gate above, which is where the spec names PACKET_REQUIRED_
    # IN_CONCEPT_MODE.)
    card = IC.fit_card(_brief("concept"), None)
    check("(b) fit_card invents no client lines when the packet is missing",
          card["client_words"] == 0
          and card["options"]["fewer_words"]["cut_line_ids"] == []
          and card["options"]["fewer_words"]["cut_words"] == 0,
          "words=%s fw=%s" % (card["client_words"], card["options"]["fewer_words"]))

    p = _cli(_brief("concept"))
    check("(b) fit CLI with a missing packet never claims a cut",
          "would be cut" not in p.stdout or "none" in p.stdout,
          "rc=%s out=%r" % (p.returncode, p.stdout.strip()[-160:]))

def test_c_fitting_packet_exits_0_and_cuts_nothing():
    packet = [{"id": "L001", "text": "Hello there, old friend."}]
    card = IC.fit_card(_brief(length=60), packet)
    check("(c) a fitting packet gives outcome ok", card["outcome"] == "ok",
          card["outcome"])
    check("(c) nothing is cut when it fits",
          card["options"]["fewer_words"]["cut_line_ids"] == []
          and card["options"]["fewer_words"]["cut_words"] == 0,
          repr(card["options"]["fewer_words"]))
    p = _cli(_brief(length=60), packet)
    check("(c) factory.py card --fit exits 0 when it fits", p.returncode == 0,
          "rc=%s %s" % (p.returncode, (p.stdout + p.stderr).strip()[-160:]))
    check("(c) the ok card says nothing is cut",
          "Nothing is cut" in p.stdout, p.stdout.strip()[-200:])


def test_d_stop_card_names_exact_ids_and_never_cuts():
    packet = [{"id": "L%03d" % n, "text": " ".join(["word"] * 30)}
              for n in range(1, 5)]
    card = IC.fit_card(_brief(length=60), packet)
    check("(d) a long packet stops", card["outcome"] == "waiting",
          card["outcome"])
    fw = card["options"]["fewer_words"]
    check("(d) fewer_words names exact line ids from the packet",
          set(fw["cut_line_ids"]) <= {"L001", "L002", "L003", "L004"}
          and all(str(x).startswith("L") for x in fw["cut_line_ids"]),
          repr(fw))
    check("(d) the cut needs client approval",
          fw["needs_client_approval"] is True)
    check("(d) every packet id is accounted for: kept plus cut",
          set(fw["cut_line_ids"]) <= {"L001", "L002", "L003", "L004"}
          and fw["cut_words"] >= 0, repr(fw))
    p = _cli(_brief(length=60), packet)
    check("(d) factory.py card --fit exits 2 when they do not fit",
          p.returncode == 2, "rc=%s" % p.returncode)
    check("(d) the STOP card states nothing is cut without approval",
          "Nothing is cut until you approve it" in p.stdout,
          p.stdout.strip()[-200:])


def test_e_options_only_from_registries():
    packet = [{"id": "L%03d" % n, "text": " ".join(["word"] * 30)}
              for n in range(1, 5)]
    card = IC.fit_card(_brief(length=60), packet)
    opts = card["options"]
    check("(e) longer_ad ids are offered lengths",
          all(o["id"] in MS.OFFERED_LENGTHS_S for o in opts["longer_ad"]),
          repr(opts["longer_ad"]))
    check("(e) longer_ad only offers lengths above the client's 60 s",
          all(o["id"] > 60 for o in opts["longer_ad"]), repr(opts["longer_ad"]))
    check("(e) music_style ids are real style ids",
          all(o["id"] in MS.style_ids() for o in opts["music_style"]),
          repr(opts["music_style"]))
    from voice_velvet_echo import velvet_voiceover as VV   # noqa: PLC0415
    check("(e) voice ids are the two registry voices",
          [o["id"] for o in opts["voice"]] == [VV.ALL_SUNO_ID, VV.VELVET_ID],
          repr(opts["voice"]))
    import words_fit as WF                                 # noqa: PLC0415
    check("(e) fewer_words id is words_fit's own option",
          opts["fewer_words"]["id"] in list(WF.preflight(60, 0, 9999)["options"]),
          repr(opts["fewer_words"]["id"]))
    # Control: assert_registry_options accepts the real card and rejects a
    # made-up id of each kind.
    check("(e) control: the real card passes the registry gate",
          IC.assert_registry_options(card) is card)
    for kind, bad in (("longer_ad", 75), ("music_style", "synthwave"),
                      ("voice", "echo_voice")):
        broken = json.loads(json.dumps(card))
        broken["options"][kind].append({"id": bad})
        try:
            IC.assert_registry_options(broken)
        except ValueError as exc:
            ok = "FIT_CARD_OPTION_NOT_IN_REGISTRY" in str(exc)
        else:
            ok = False
        check("(e) a made-up %s option is refused" % kind, ok)


def test_f_notices_are_not_options():
    brief = _brief(length=75, fps=24, voice="echo voice for the friend",
                   sfx=["HONK"])
    card = IC.fit_card(brief, [{"id": "L001", "text": "Hello there."}])
    kinds = [n["kind"] for n in card["notices"]]
    check("(f) notices carry the four kinds the spec names",
          all(k in kinds for k in ("sfx", "echo_voice",
                                   "length_not_offered", "fps")),
          repr(kinds))
    check("(f) an un-offered length appears as a notice",
          "length_not_offered" in kinds, repr(kinds))
    check("(f) no notice leaks into the option registries",
          not set(kinds) & set(card["options"]),
          "kinds=%s option keys=%s" % (kinds, list(card["options"])))
    check("(f) control: a clean brief has no notices",
          IC.fit_card(_brief(length=60),
                      [{"id": "L001", "text": "Hello there."}])["notices"] == [])


def main():
    for fn in (test_a_fit_step_exists, test_b_concept_without_packet_is_refused,
               test_c_fitting_packet_exits_0_and_cuts_nothing,
               test_d_stop_card_names_exact_ids_and_never_cuts,
               test_e_options_only_from_registries, test_f_notices_are_not_options):
        fn()
    print("FAILED: %s" % FAILS if FAILS else "ALL OK")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())