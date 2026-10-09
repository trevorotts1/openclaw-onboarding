#!/usr/bin/env python3
"""W1-A-U3 (manual H8 + L4): version-2 intake defaults and ten profiles.

Proves, behaviourally:
  * DEFAULTS target_length_s == 60 and the v1 30s default is gone;
  * length_option / shape / look / music / voice flow through normalize with
    provenance (provided > inherited > default), look/music from D24;
  * a provided length_option feeds target_length_s only when it was assumed;
  * the default allowed_profiles are the ten drama-<shape>-<length>s profiles
    and `preflight --profile drama-16x9-300s` never says
    delivery-profile-unknown (the manual's Done-when);
  * FU-ONE-SPEND-QUESTION: the story questions never ask about money (the
    choice card does, once); budget_currency still
    accepts credits (parser unchanged).

Run: python3 scripts/core/intake_preflight/test_intake_preflight.py
stdlib only, no network, no provider, no writes outside a temp dir.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                            # intake.py / preflight.py
sys.path.insert(0, os.path.dirname(HERE))           # core/

import intake as I            # noqa: E402  (package under test)
import preflight as P         # noqa: E402  (package under test)

FACTORY = os.path.join(HERE, "factory.py")

FAILS = []


import re
_MONEY = re.compile(r"spend|budget|cost|price|\$|dollar", re.I)


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def test_default_length_is_60():
    check("DEFAULTS target_length_s == 60",
          I.DEFAULTS.get("target_length_s") == 60,
          repr(I.DEFAULTS.get("target_length_s")))


def test_no_money_question_in_story_questions():
    check("Q_SPENDING is gone", not hasattr(I, "Q_SPENDING"))
    for name in ("Q_OFFER", "Q_AUDIENCE", "Q_WEBSITE", "Q_PLACEMENT"):
        check(name + " has no money words",
              not _MONEY.search(getattr(I, name)), getattr(I, name))


def test_weekly_brief_fields_pass_through():
    """What 35-social-media-planner's weekly brief sends must be read."""
    brief = {
        "schema_version": "blackceo.campaign/v1",
        "title": "Drama song of the week: rest",
        "shape": "9:16",
        "length_option": 90,
        "look": "2D Hand-Painted",
        "music": "R&B Flow",
        "voice": "Velvet Voiceover",
        "cta_text": "Buy",
        "cta_link": "https://example.test",
    }
    fields, prov = I.normalize(brief, {})
    for name, want in (("length_option", 90), ("shape", "9:16"),
                       ("look", "2D Hand-Painted"), ("music", "R&B Flow"),
                       ("voice", "Velvet Voiceover")):
        check("brief %s -> %r" % (name, want), fields.get(name) == want,
              repr(fields.get(name)))
        check("%s provenance is provided" % name, prov.get(name) == "provided",
              repr(prov.get(name)))
    check("length_option 90 feeds assumed target_length_s",
          fields.get("target_length_s") == 90, repr(fields.get("target_length_s")))


def test_explicit_target_length_wins():
    fields, _ = I.normalize({"target_length_s": 120, "length_option": 90}, {})
    check("explicit target_length_s not overridden by length_option",
          fields.get("target_length_s") == 120, repr(fields.get("target_length_s")))


def test_card_defaults_from_style_defaults():
    """Empty brief -> D24 look/music, card length/shape/voice defaults."""
    fields, prov = I.normalize({}, {})
    check("default length_option is 60",
          fields.get("length_option") == 60, repr(fields.get("length_option")))
    check("default shape is 9:16", fields.get("shape") == "9:16",
          repr(fields.get("shape")))
    check("default voice is all-suno", fields.get("voice") == "all-suno",
          repr(fields.get("voice")))
    check("default look is Lifelike 3D", fields.get("look") == "Lifelike 3D",
          repr(fields.get("look")))
    check("default music is Soul Ballad", fields.get("music") == "Soul Ballad",
          repr(fields.get("music")))
    check("default look provenance is default",
          prov.get("look") == "default", repr(prov.get("look")))
    check("default target_length_s is 60",
          fields.get("target_length_s") == 60, repr(fields.get("target_length_s")))


def test_ten_delivery_profiles():
    got = P.DEFAULT_PROFILES
    want = tuple(
        "drama-%s-%ss" % (shape, secs)
        for secs in (60, 90, 180, 300, 600)
        for shape in ("9x16", "16x9"))
    check("exactly the ten version-2 profiles",
          got == want, "%s != %s" % (got, want))
    check("ten profiles, five lengths x two shapes",
          len(got) == 10, str(len(got)))
    check("v1 profile retired from defaults",
          "short-9x16-30s" not in got)


def test_default_profile_known():
    r = P.check({"profile": "drama-16x9-300s", "auth": {"scope": "campaign"},
                 "summary_digest": "t"})
    check("preflight accepts drama-16x9-300s by default",
          r.get("reason_code") != "delivery-profile-unknown",
          repr(r.get("reason_code")))
    r2 = P.check({"profile": "bogus-profile-w1a-u3", "auth": {"scope": "campaign"},
                  "summary_digest": "t"})
    check("unknown profile still rejected",
          r2.get("reason_code") == "delivery-profile-unknown",
          repr(r2.get("reason_code")))


def test_cli_done_when():
    """The manual's Done-when, run verbatim through the real CLI.

    F15 (owner order 2026-10-08) added the choice-card gate: paid preflight
    also needs the recorded card receipt, so this test records one."""
    with tempfile.TemporaryDirectory() as tmp:
        auth = os.path.join(tmp, "auth.json")
        with open(auth, "w", encoding="utf-8") as fh:
            json.dump({"scope": "campaign"}, fh)
        answers = {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                   "length": 300, "video_model": "MiniMax H3 768P"}
        receipt_path = os.path.join(tmp, "card.json")
        try:
            core = os.path.join(HERE, "..", "style_defaults")
            sys.path.insert(0, core)
            from style_defaults import card_gate as CG
            receipt = CG.answered_stamped(answers, "W1-A-U3 test",
                                          "2026-10-08T09:00:00Z")
        except Exception:
            receipt = {"answers": answers, "who": "W1-A-U3 test",
                       "at": "2026-10-08T09:00:00Z"}
        with open(receipt_path, "w", encoding="utf-8") as fh:
            json.dump(receipt, fh)
        run = subprocess.run(
            [sys.executable, FACTORY, "preflight",
             "--root", tmp, "--storage-dir", tmp,
             "--profile", "drama-16x9-300s",
             "--auth-file", auth, "--summary-digest", "t",
             "--card-receipt-file", receipt_path],
            capture_output=True, text=True)
        env = json.loads(run.stdout)
        check("CLI: not delivery-profile-unknown",
              env.get("reason_code") != "delivery-profile-unknown",
              "%s (exit %s, stderr %s)" % (env.get("reason_code"), run.returncode,
                                           run.stderr.strip()[:200]))
        check("CLI: preflight passes end to end",
              env.get("outcome") == "ok" and env.get("reason_code") == "preflight-pass",
              "%s/%s" % (env.get("outcome"), env.get("reason_code")))
        # and the F15 refusal still fires when the receipt is absent
        run2 = subprocess.run(
            [sys.executable, FACTORY, "preflight",
             "--root", tmp, "--storage-dir", tmp,
             "--profile", "drama-16x9-300s",
             "--auth-file", auth, "--summary-digest", "t"],
            capture_output=True, text=True)
        env2 = json.loads(run2.stdout)
        check("CLI: paid preflight without card -> CARD_UNANSWERED",
              env2.get("reason_code") == "CARD_UNANSWERED",
              "%s/%s" % (env2.get("outcome"), env2.get("reason_code")))


def test_thin_brief_asks_no_money_question():
    """A thin brief asks story questions only; money is asked once, on the card."""
    r = I.evaluate({}, {})
    ids = [q["id"] for q in r.get("questions") or []]
    check("thin brief still waits on story questions", r.get("outcome") == "waiting", repr(ids))
    check("spending_authority not asked", "spending_authority" not in ids, repr(ids))
    check("no question mentions money",
          not _MONEY.search(r.get("question_message") or ""), repr(r.get("question_message")))


def test_freed_slot_goes_to_next_question():
    """The slot the money question used to take is given to the next needed one."""
    r = I.evaluate({"offer": "my book at example.com"}, {})
    ids = [q["id"] for q in r.get("questions") or []]
    check("audience, website and placement fill the three slots",
          ids == ["audience_action", "website", "placement"], repr(ids))


def test_credits_still_accepted():
    """L4 keep: the parser still takes credits as the currency unit."""
    fields, prov = I.normalize({"budget_minor": 2500, "budget_currency": "credits"}, {})
    check("budget_currency 'credits' accepted",
          fields.get("budget_currency") == "credits", repr(fields.get("budget_currency")))
    check("credits provenance provided", prov.get("budget_currency") == "provided")
    r = I.evaluate({"budget_minor": 2500, "budget_currency": "credits"}, {})
    ids = [q["id"] for q in r.get("questions") or []]
    check("credits budget needs no spending question",
          "spending_authority" not in ids, repr(ids))


TESTS = [
    test_default_length_is_60,
    test_no_money_question_in_story_questions,
    test_weekly_brief_fields_pass_through,
    test_explicit_target_length_wins,
    test_card_defaults_from_style_defaults,
    test_ten_delivery_profiles,
    test_default_profile_known,
    test_cli_done_when,
    test_thin_brief_asks_no_money_question,
    test_freed_slot_goes_to_next_question,
    test_credits_still_accepted,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d H8+L4 tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())