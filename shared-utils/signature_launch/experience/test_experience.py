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
        self.assertEqual([c["ids"] for c in calls],
                         [["brand_primary_color", "brand_fonts"], ["offer_price"], ["design_style"]])
        for c in calls:
            for q in c["questions"]:
                self.assertTrue(2 <= len(q["options"]) <= 4, q)
                self.assertLessEqual(len(q["header"]), 12)
                self.assertEqual(q["options"][-1]["label"], rq.HELP_LABEL)
                self.assertTrue(all(o["description"] for o in q["options"]))

    def test_more_than_four_questions_in_a_group_are_split(self):
        many = [{"id": f"q{i}", "text": "t", "group": "g"} for i in range(9)]
        self.assertEqual([len(c["questions"]) for c in rq.structured(many)], [4, 4, 1])

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
