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
    def test_structured_is_valid_tool_shape_and_asks_one_at_a_time(self):
        calls = rq.structured(QS)
        # one question per call, in bank order: the client is never handed a wall of pickers
        self.assertEqual([c["ids"] for c in calls],
                         [["brand_primary_color"], ["brand_fonts"], ["offer_price"], ["design_style"]])
        for c in calls:
            self.assertEqual(len(c["questions"]), 1)
            for q in c["questions"]:
                self.assertTrue(2 <= len(q["options"]) <= 4, q)
                self.assertLessEqual(len(q["header"]), 12)
                self.assertEqual(q["options"][-1]["label"], rq.HELP_LABEL)
                # the bank's own explanation is kept; the help option is always explained; a label that
                # already says it all (QS has "Yes, I will tell you") carries an empty description
                self.assertTrue(all(isinstance(o["description"], str) for o in q["options"]))
                self.assertTrue(q["options"][-1]["description"])
                self.assertNotIn("Use this one", [o["description"] for o in q["options"]])

    def test_many_questions_never_batch(self):
        many = [{"id": f"q{i}", "text": "t", "group": "g"} for i in range(9)]
        self.assertEqual([len(c["questions"]) for c in rq.structured(many)], [1] * 9)

    def test_nested_help_examples_and_default_survive_rendering(self):
        q = {"id": "timing", "group": "launch", "text": "When do the doors open?",
             "why": "Every message is timed from it.",
             "help": {"explain": "Give the date and both times.",
                      "examples": ["Doors open 14 Nov 2026 9:00 a.m. New York",
                                   "Launch 1 Dec 2026 10:00 a.m. London time"]},
             "default": {"value": "no deadline until you give one", "flag": "to confirm"},
             "never_default": False, "choices": []}
        n = rq.normalize(q)
        self.assertEqual(n["examples"], q["help"]["examples"])
        self.assertEqual(n["safe_default"], "no deadline until you give one")
        self.assertEqual(n["help_text"], "Give the date and both times.")
        msg = rq.chat(q)
        self.assertIn("Doors open 14 Nov 2026 9:00 a.m. New York", msg)
        self.assertIn("Give the date and both times.", msg)

    def test_per_option_explanations_are_kept(self):
        q = {"id": "design_style", "text": "Which look?", "choices": [
            {"value": "A", "label": "A, Block", "example": "Clean rectangular photos."},
            {"value": "B", "label": "B, Circle"}]}
        n = rq.normalize(q)
        self.assertEqual(n["choices"][0]["description"], "Clean rectangular photos.")
        self.assertEqual(n["choices"][1]["description"], "")  # the bank said nothing: nothing is invented
        opts = rq.structured([q])[0]["questions"][0]["options"]
        self.assertEqual(opts[0]["description"], "Clean rectangular photos.")
        self.assertEqual(opts[1]["description"], rq.HINT)  # a short label gets one warm line under it
        self.assertNotIn("Circle", opts[1]["description"])  # ... that never repeats the label

    def test_a_label_that_says_it_all_gets_no_filler(self):
        """33 of the 60 bank questions carry choices with no description. A long label or one that reads
        as a sentence is never followed by a line that repeats it; a question of short labels gets the one
        warm hint on every option; a mix gets none, so no row looks unfinished; the chat message never
        adds a hint (a numbered 'Monthly' needs none)."""
        def hints(labels, **described):
            cs = [{"label": x, "description": described.get(x, "")} for x in labels]
            return rq._hints(cs)
        for label in ["A: Recommend a plan for me (use what is known, ask only what is missing, let them review)",
                      "Yes, send access after purchase", "Light (white or cream)", "Use my own story for it.",
                      "Is this right?"]:
            self.assertTrue(rq._says_it_all(label), label)
            self.assertEqual(hints([label, "No"]), ["", ""], label)
        for label in ["Monthly", "Dark", "88", "I have a price", "No"]:
            self.assertFalse(rq._says_it_all(label), label)
            self.assertNotIn(label, rq.HINT)
        self.assertEqual(hints(["All at once", "Monthly"]), [rq.HINT, rq.HINT])
        self.assertEqual(hints(["All at once", "Monthly", "In parts or trial first"]), ["", "", ""])
        self.assertEqual(hints(["Dark", "Light"], Dark="Dark backgrounds."), ["Dark backgrounds.", rq.HINT])
        self.assertEqual(hints(["Dark", "Light (white or cream)"], Dark="Dark backgrounds."), ["Dark backgrounds.", ""])
        q = {"id": "b", "text": "How do you bill?", "choices": ["All at once", "Monthly"]}
        self.assertEqual([o["description"] for o in rq.structured([q])[0]["questions"][0]["options"][:2]],
                         [rq.HINT, rq.HINT])
        msg = rq.chat(q)
        self.assertIn("\n2. Monthly\n", msg)
        self.assertNotIn("Pick this one", msg)
        self.assertNotIn(" - ", msg)

    def test_a_way_out_never_gets_the_pick_this_one_hint(self):
        """"Pick this one if it sounds right to you" under "Not sure" reads as nonsense. A way out
        (Not sure / I don't know / Skip / Other ...) gets no hint, does not stop the real answers
        from getting theirs, and keeps the bank's own words when the bank wrote some."""
        def hints(labels, **described):
            return rq._hints([{"label": x, "description": described.get(x, "")} for x in labels])
        for label in ["Not sure", "Not sure yet", "Unsure", "I don't know", "I don\u2019t know yet", "Skip",
                      "Skip this one", "Other", "Other (type it in)", "Something else", "Decide later",
                      "None of these", "Prefer not to say"]:
            self.assertTrue(rq._is_way_out(label), label)
            self.assertEqual(hints(["Monthly", label]), [rq.HINT, ""], label)
        for label in ["Monthly", "Sure thing", "Skipper", "Others", "Darkness", "None yet", "A different logo"]:
            self.assertFalse(rq._is_way_out(label), label)
        # a way out is not a real answer: its length never silences the others, and the others' hints stay
        self.assertEqual(hints(["Monthly", "Yearly", "Not sure about this one"]), [rq.HINT, rq.HINT, ""])
        self.assertEqual(hints(["Monthly", "Not sure"], **{"Not sure": "We can work it out together."}),
                         [rq.HINT, "We can work it out together."])
        q = {"id": "b", "text": "How do you bill?", "choices": ["All at once", "Monthly", "Not sure"]}
        opts = rq.structured([q])[0]["questions"][0]["options"]
        self.assertEqual([o["description"] for o in opts[:3]], [rq.HINT, rq.HINT, ""])
        self.assertNotIn("Pick this one", rq.chat(q))

    def test_a_one_sentence_help_is_kept_as_the_explanation(self):
        """Skill 83's picture questions carry `help` as a plain sentence; its coaching must survive."""
        q = {"id": "image_provider", "text": "Standard image service?",
             "help": "Say yes unless someone told you otherwise."}
        self.assertEqual(rq.normalize(q)["help_text"], "Say yes unless someone told you otherwise.")
        self.assertIn("explain it in plain language",
                      rq.structured([q])[0]["questions"][0]["options"][-1]["description"])
        self.assertIn("Say yes unless someone told you otherwise", rq.chat(q))

    def test_help_option_names_the_coaching_ways_out(self):
        q = {"id": "channels", "text": "Email only or email and text?",
             "help": {"explain": "Email always works."}, "default": {"value": "Email only"}}
        opts = rq.structured([q])[0]["questions"][0]["options"]
        self.assertEqual(opts[-1]["label"], rq.HELP_LABEL)
        self.assertIn("show you an example", opts[-1]["description"])
        self.assertIn("recommend", opts[-1]["description"])

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
        for r in ("I\u2019m not sure", "I don\u2019t know", "not sure?", "Not sure, help", "No clue", "I have no idea", "?", "??",
                  "help me answer", "show me an example", "recommend using what is known"):
            self.assertEqual(rq.parse_reply(q, r)["kind"], "help", r)
            self.assertEqual(rq.parse_reply(QS[2], r)["kind"], "help", r)
        self.assertEqual(rq.parse_reply(q, "default"), {"kind": "default", "value": "#2B2B2B"})
        self.assertEqual(rq.parse_reply(q, "teal, like the ocean")["kind"], "free_text")
        self.assertEqual(rq.parse_reply(q, "9")["kind"], "free_text")
        self.assertEqual(rq.parse_reply(q, "  ")["kind"], "repeat")
        self.assertEqual(rq.parse_reply(QS[2], "1499")["value"], "1499")  # no choices: digits are an answer

    def test_resume_asks_one_at_a_time_and_suggested_is_still_asked(self):
        # the resume path is no longer a list: it is exactly ONE question, chosen by the engine
        self.assertEqual([q["id"] for q in rq.pending(QS, ANS)], ["offer_price"])
        self.assertEqual(len(rq.pending(QS, None)), 1)
        self.assertEqual(rq.pending(QS, None)[0]["id"], "brand_primary_color")
        as_list = {"answers": [{"question_id": "brand_primary_color", "status": "provided", "value": "x"},
                               {"question_id": "brand_fonts", "status": "provided", "value": "y"}]}
        self.assertEqual([q["id"] for q in rq.pending(QS, as_list)], ["offer_price"])
        # a suggestion is not the client's answer: design_style comes back once the rest is answered
        all_but = {"answers": {k: {"value": "v", "status": "provided"}
                               for k in ("brand_primary_color", "brand_fonts", "offer_price")}}
        self.assertEqual([q["id"] for q in rq.pending(QS, all_but)], ["design_style"])

    def test_conditional_questions_never_render_when_inapplicable(self):
        bank = {"help_label": rq.HELP_LABEL, "questions": [
            {"id": "always_one", "text": "Always?", "condition": "always"},
            {"id": "bf_only", "text": "Black Friday only?", "condition": "mode == bf"},
            {"id": "legacy_only", "text": "Legacy only?", "condition": "mode == legacy"}]}
        self.assertEqual([q["id"] for q in rq.pending(bank, None, "launch")], ["always_one"])
        self.assertEqual([q["id"] for q in rq.pending(bank, None, "bf")], ["always_one"])
        self.assertEqual(rq.pending({"questions": []}, None), [])

    def test_every_applicable_question_stays_reachable(self):
        """Nothing is silently skipped: walking the one-at-a-time flow covers every applicable one."""
        answered, seen = {}, []
        for _ in range(20):
            one = rq.pending(QS, answered)
            if not one:
                break
            seen.append(one[0]["id"])
            answered.setdefault("answers", {})[one[0]["id"]] = {"value": "v", "status": "provided"}
        self.assertEqual(seen, [q["id"] for q in QS])  # all four, in bank order, one per step

    def test_done_renders_nothing(self):
        answered = {"answers": {q["id"]: {"value": "v", "status": "provided"} for q in QS}}
        self.assertEqual(rq.render(rq.pending(QS, answered), hp.detect("claude-code")), [])
        self.assertEqual(rq.render(rq.pending(QS, answered), hp.detect("openclaw")), [])

    def test_open_question_keeps_its_default_and_help_even_from_the_engine(self):
        one = rq.pending({"help_label": rq.HELP_LABEL, "questions": [QS[1]]}, None)[0]
        self.assertEqual(one["help_label"], rq.HELP_LABEL)  # engine labels the help option
        self.assertIn('"default"', rq.render([one], hp.detect("openclaw"))[0]["message"])

    def test_same_bank_same_answers_file_any_harness(self):
        a = rq.render(rq.pending(QS, ANS), hp.detect("claude-code"))
        b = rq.render(rq.pending(QS, ANS), hp.detect("openclaw"))
        self.assertEqual([i for c in a for i in c["ids"]], [m["id"] for m in b])
        self.assertEqual(len(a), 1)  # one question, never a wall, in either shape


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
