"""LANE-HARNESS tests: stdlib unittest, fixtures only, no network, no credentials."""
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import delivery_report as dr  # noqa: E402
import harness_profile as hp  # noqa: E402
import progress_report as pr  # noqa: E402
import render_question as rq  # noqa: E402


def fx(name):
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


QS = fx("questions.sample.json")["questions"]
ANS = fx("answers.partial.json")
ROWS = fx("rows.fullfunnel.json")


class Detect(unittest.TestCase):
    def test_order_flag_then_answers_then_env_then_plain(self):
        env = {"OPENCLAW_SESSION_ID": "s1"}
        self.assertEqual(hp.detect("claude-nine", ANS, env)["harness"], "claude-nine")
        self.assertEqual(hp.detect(None, ANS, {"CLAUDECODE": "1"})["source"], "answers:harness")
        self.assertEqual(hp.detect(None, {}, env)["harness"], "openclaw")
        self.assertEqual(hp.detect(None, {}, {"CLAUDE_CODE_SESSION_ID": "x"})["harness"], "claude-code")
        self.assertEqual(hp.detect(None, {}, {"CLAUDE_CONFIG_DIR": "/h/.claude-nine"})["harness"], "claude-nine")
        self.assertEqual(hp.detect(None, {}, {}), {"harness": "plain", "source": "default", "skills_root": None,
                                                    "question_shape": "chat", "progress_shape": "messages"})

    def test_unknown_flag_is_plain_not_a_guess_and_never_a_skills_path(self):
        p = hp.detect("emacs", None, {"CLAUDECODE": "1"})
        self.assertEqual((p["harness"], p["source"], p["skills_root"]), ("plain", "flag:unrecognised", None))
        self.assertEqual(hp.detect("openclaw", None, {}, skills_root="/given")["skills_root"], "/given")


class Questions(unittest.TestCase):
    def test_structured_is_valid_tool_shape(self):
        calls = rq.structured(QS)
        # one question per call, never a batch
        self.assertEqual([c["ids"] for c in calls], [[q["id"]] for q in QS])
        for c in calls:
            for q in c["questions"]:
                self.assertTrue(2 <= len(q["options"]) <= 4, q)
                self.assertLessEqual(len(q["header"]), 12)
                self.assertEqual(q["options"][-1]["label"], rq.HELP_LABEL)
                # per-option explanations are the bank's own; a missing one stays missing
                self.assertTrue(all("Use this one" not in o["description"] for o in q["options"]))

    def test_every_question_gets_its_own_call(self):
        many = [{"id": f"q{i}", "text": "t", "group": "g"} for i in range(9)]
        self.assertEqual([len(c["questions"]) for c in rq.structured(many)], [1] * 9)

    def test_per_option_explanations_survive_to_the_surface(self):
        q = dict(QS[0], choices=[{"label": "Navy blue", "value": "#1F3A5F", "description": "from your logo"},
                                 {"label": "Gold", "value": "#C9A227", "example": "warm and classic"}])
        opts = rq.structured([q])[0]["questions"][0]["options"]
        self.assertEqual(opts[0]["description"], "from your logo")
        self.assertEqual(opts[1]["description"], "warm and classic")  # example also carries an explanation
        n = rq.normalize({"id": "x", "text": "t", "help": {"explain": "e", "examples": ["ex1"]},
                          "default": {"value": "V", "reason": "R", "flag": "to confirm"}})
        self.assertEqual(n["examples"], ["ex1"])
        self.assertEqual(n["default"]["value"], "V")

    def test_conditions_hold_a_question_back(self):
        qs = [dict(QS[2], condition="extra == yes"), dict(QS[0], condition="always")]
        left = [q["id"] for q in rq.pending(qs, {"answers": {"extra": {"value": "no", "status": "provided"}}})]
        self.assertEqual(left, ["brand_primary_color"])
        left = [q["id"] for q in rq.pending(qs, {"answers": {"extra": {"value": "yes", "status": "provided"}}})]
        self.assertEqual(left, ["offer_price", "brand_primary_color"])  # bank order

    def test_three_choice_cap_reported_not_silent(self):
        n = rq.normalize(QS[3])
        self.assertEqual(len(n["choices"]), 3)
        self.assertEqual(n["dropped"], ["D: extra (should be cut)"])

    def test_chat_message_is_short_numbered_and_offers_help(self):
        msg = rq.chat(QS[0], 1, 4)
        self.assertIn("Question 1 of 4:", msg)
        self.assertIn("3. " + rq.HELP_LABEL, msg)
        self.assertIn('"default"', msg)
        self.assertLessEqual(len(msg.splitlines()), 9)

    def test_never_default_question_never_offers_a_default(self):
        self.assertNotIn("default", rq.chat(QS[2]).replace("Just type", ""))
        self.assertEqual(rq.parse_reply(QS[2], "skip")["kind"], "help")
        self.assertFalse([o for o in rq.structured([QS[2]])[0]["questions"][0]["options"]
                          if "default" in o["description"]])

    def test_parse_reply(self):
        q = QS[0]
        self.assertEqual(rq.parse_reply(q, "2"), {"kind": "choice", "value": "#C9A227"})
        self.assertEqual(rq.parse_reply(q, "3")["kind"], "help")
        self.assertEqual(rq.parse_reply(q, "Help"), {"kind": "help", "value": None})
        self.assertEqual(rq.parse_reply(q, "I don't know.")["kind"], "help")
        for r in ("I\u2019m not sure", "I don\u2019t know", "not sure?", "Not sure, help", "No clue", "I have no idea", "?", "??"):
            self.assertEqual(rq.parse_reply(q, r)["kind"], "help", r)
            self.assertEqual(rq.parse_reply(QS[2], r)["kind"], "help", r)
        self.assertEqual(rq.parse_reply(q, "default"), {"kind": "default", "value": "#2B2B2B"})
        self.assertEqual(rq.parse_reply(q, "teal, like the ocean")["kind"], "free_text")
        self.assertEqual(rq.parse_reply(q, "9")["kind"], "free_text")
        self.assertEqual(rq.parse_reply(q, "  ")["kind"], "repeat")
        self.assertEqual(rq.parse_reply(QS[2], "1499")["value"], "1499")  # no choices: digits are an answer

    def test_resume_skips_provided_and_defaulted_only(self):
        left = [q["id"] for q in rq.pending(QS, ANS)]
        self.assertEqual(left, ["offer_price", "design_style"])  # suggested is asked again
        self.assertEqual(len(rq.pending(QS, None)), 4)
        as_list = {"answers": [{"question_id": "offer_price", "status": "provided", "value": "997"}]}
        self.assertNotIn("offer_price", [q["id"] for q in rq.pending(QS, as_list)])

    def test_same_bank_same_answers_file_any_harness(self):
        a = rq.render(rq.pending(QS, ANS), hp.detect("claude-code"))
        b = rq.render(rq.pending(QS, ANS), hp.detect("openclaw"))
        self.assertEqual([i for c in a for i in c["ids"]], [m["id"] for m in b])


class StyleExamples(unittest.TestCase):
    """Finding 20: the client must SEE the style examples before choosing A/B/C."""

    Q = {"id": "design_style", "text": "Which look do you want for your page: A, B or C?",
         "why": "The style sets the shape of the photos and sections.",
         "choices": ["A Block", "B Circle", "C Hybrid"],
         "help": {"examples": [
             "Classic and professional: A",
             "Warm and friendly: B",
             "Modern and personal: C",
             "A Block example: https://example.test/a.png",
             "B Circle example: https://example.test/b.png",
             "C Hybrid example: none available yet - this style has no example image",
         ]}}

    def test_chat_shows_the_style_images_above_the_question(self):
        msg = rq.chat(self.Q, 1, 4)
        self.assertIn("https://example.test/a.png", msg)
        self.assertIn("https://example.test/b.png", msg)  # never truncated to two items
        self.assertLess(msg.index("https://example.test/a.png"), msg.index("A, B or C"))
        self.assertIn("C Hybrid example: none available yet", msg)  # a style with no example says so

    def test_structured_carries_the_style_images(self):
        text = rq.structured([self.Q])[0]["questions"][0]["question"]
        self.assertIn("https://example.test/a.png", text)
        self.assertIn("none available yet", text)
        self.assertLess(text.index("https://example.test/a.png"), text.index("A, B or C"))

    def test_engine_offers_an_image_or_says_there_is_none(self):
        eng = rq._engine()
        self.assertIsNotNone(eng, "client_intake engine must resolve in this checkout")
        links = eng._style_links()
        self.assertTrue(any("http" in l for l in links), links)
        self.assertTrue(any("none available" in l for l in links), links)  # Style C has no example

    def test_malformed_engine_entries_never_crash_or_invent_a_url(self):
        eng = rq._engine()
        self.assertIsNotNone(eng)
        lines = eng._style_lines(["oops", 5, {"id": "X"},
                                  {"id": "Y", "name": "Why", "example": {"url": "https://e/y.png"}}])
        self.assertEqual(2, len(lines))  # malformed entries skipped, real styles kept
        self.assertIn("Y Why example: https://e/y.png", lines)
        self.assertNotIn("http", lines[0])  # a style with no example never claims a picture

    def test_non_string_examples_never_crash_the_render(self):
        q = {"id": "design_style", "text": "Pick one.",
             "help": {"examples": [{"note": "dict"}, "C Hybrid example: none available yet"]}}
        self.assertIn("none available yet", rq.chat(q))
        self.assertIn("none available yet", rq.structured([q])[0]["questions"][0]["question"])

    def test_no_style_block_without_style_lines(self):
        q = {"id": "design_style", "text": "Pick one.",
             "help": {"examples": ["Classic and professional: A"]}}
        self.assertNotIn("Style examples", rq.chat(q))
        self.assertNotIn("Style examples", rq.structured([q])[0]["questions"][0]["question"])

    def test_only_design_style_gets_the_block_above_the_question(self):
        q = {"id": "photos", "text": "What photos do you have?",
             "help": {"examples": ["See https://example.test/p.png"]}}
        msg = rq.chat(q)
        self.assertNotIn("Style examples", msg)
        self.assertGreater(msg.index("https://example.test/p.png"), msg.index("What photos do you have?"))
        text = rq.structured([q])[0]["questions"][0]["question"]
        self.assertNotIn("Style examples", text)
        self.assertGreater(text.index("https://example.test/p.png"), text.index("What photos do you have?"))


class Reports(unittest.TestCase):
    def test_progress_table_for_claude_and_messages_for_chat(self):
        t = pr.render(ROWS, hp.detect("claude-code"))
        self.assertEqual(t["shape"], "table")
        self.assertIn("| Upsell 2 | working | D yes / M yes | D yes / M no | no | pending |", t["text"])
        self.assertIn("6 of 9 pages finished.", t["text"])

    def test_chat_announces_each_finished_page_once(self):
        first = pr.render(ROWS, hp.detect("openclaw"))
        self.assertEqual(len(first["messages"]), 7)  # 6 done + 1 failed; working/queued are silent
        self.assertIn("Signature Landing Page is finished. Wireframes: desktop and mobile.", first["messages"][0])
        self.assertTrue(first["messages"][-1].startswith("Thank-You Page is failed. The mobile mockup"))
        again = pr.render(ROWS, hp.detect("openclaw"), first["announced"])
        self.assertEqual(again["messages"], [])

    def test_delivery_complete_vs_incomplete_is_honest(self):
        prof = hp.detect("claude-nine")
        out = dr.render(ROWS, prof, ANS, fx("ledger.sample.json"))
        self.assertTrue(out.startswith("INCOMPLETE: 3 of 9 pages"))
        self.assertIn("Review (fail)", dr.render(ROWS, hp.detect("openclaw")))
        self.assertIn("| Thank-You Page | yes | yes | yes | MISSING | yes | fail |", out)
        self.assertIn("MISSING", out)
        done = [dict(r, state="done", wireframe={"desktop": 1, "mobile": 1}, mockup={"desktop": 1, "mobile": 1},
                     labels=True, qc="pass") for r in ROWS]
        self.assertTrue(dr.render(done, prof).startswith("COMPLETE: all 9 pages"))

    def test_to_confirm_items_and_one_line_change(self):
        out = dr.render(ROWS, hp.detect("openclaw"), ANS, fx("ledger.sample.json"), {})
        self.assertIn('Fonts: we used clean modern fonts (you were not sure). To change: Reply "change Fonts: <your answer>"', out)
        self.assertIn('- design style: we used B. To change: Reply "change design style: <your answer>"', out)
        self.assertEqual(out.count("Fonts: we used"), 1)  # explicit + derived de-duplicated
        self.assertIn("Images: 27 of 40 allowed (provider kie).", out)
        self.assertNotIn("|", out)  # chat shape has no table

    def test_stub_ledger_says_nothing_was_charged(self):
        self.assertIn("nothing was charged", dr.spend_line({"images_used": 3, "test_only": True, "provider": "stub"}))
        self.assertEqual(dr.spend_line(None), "No image spend was recorded.")


class NoBorrowedChannel(unittest.TestCase):
    def test_modules_have_no_network_or_credentials(self):
        for f in HERE.glob("*.py"):
            if f.name.startswith("test_"):
                continue
            src = f.read_text(encoding="utf-8")
            self.assertFalse(re.search(r"^\s*(import|from)\s+(urllib|http|socket|requests|subprocess)", src, re.M), f.name)
            self.assertNotRegex(src.lower(), r"telegram_|bot_token|api_key|\.env\b")


if __name__ == "__main__":
    unittest.main()
