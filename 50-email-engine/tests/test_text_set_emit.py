"""Issue 3 (50 side): Skill 50 emits the approved SMS copy per launch text set.

Fail-before: Skill 50 named itself the copy owner for launch texts but emitted nothing Skill 44 could bind, so
every compiled SMS step stayed copy_pending. Pass-after: emit_text_sets.py writes working/text/<set_id>.sms.json
for every text set or writes nothing, and validate_profile.py --check-sms judges the files.

Run: python3 50-email-engine/tests/test_text_set_emit.py
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
EMIT = SKILL / "tools" / "emit_text_sets.py"
VALIDATE = SKILL / "text-profile" / "validate_profile.py"

GOOD = ("Doors are open. Take a look: {link}\n"
        "Reply YES and I'll send the details. Reply STOP to opt out.")


def plan(**over):
    sets = [
        {"id": "text_doors_open", "kind": "doors_open", "messages": 1, "promotional": True},
        {"id": "text_access_link", "kind": "access_link", "messages": 2, "promotional": False},
    ]
    return {"launch_id": "t-1", "text_sets": sets, **over}


def copy(**over):
    sets = {"text_doors_open": [{"step_id": "s1", "body": GOOD}],
            "text_access_link": [{"step_id": "a1", "body": GOOD}, {"step_id": "a2", "body": GOOD}]}
    sets.update(over)
    return {"sets": sets}


def run(*args):
    proc = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


class TextSetEmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tse-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = self.tmp / "working" / "text"

    def emit(self, p=None, c=None):
        (self.tmp / "plan.json").write_text(json.dumps(p or plan()))
        (self.tmp / "copy.json").write_text(json.dumps(c or copy()))
        return run(EMIT, "--launch-plan", self.tmp / "plan.json", "--copy", self.tmp / "copy.json",
                   "--out-dir", self.out)

    def test_every_set_gets_a_validated_file_with_the_plans_category(self):
        rc, out = self.emit()
        self.assertEqual(rc, 0, out)
        doors = json.loads((self.out / "text_doors_open.sms.json").read_text())
        self.assertEqual(doors["set_id"], "text_doors_open")
        self.assertEqual([m["category"] for m in doors["messages"]], ["marketing"])
        self.assertEqual(len(doors["profile_sha256"]), 64)
        access = json.loads((self.out / "text_access_link.sms.json").read_text())
        self.assertEqual({m["category"] for m in access["messages"]}, {"operational"})
        for name in ("text_doors_open", "text_access_link"):
            rc, out = run(VALIDATE, "--check-sms", self.out / ("%s.sms.json" % name))
            self.assertEqual(rc, 0, out)

    def test_nothing_is_written_unless_every_set_is_valid(self):
        for label, c, why in (
            ("a set with no copy", copy(text_access_link=[]), "no approved copy"),
            ("wrong message count", copy(text_access_link=[{"step_id": "a1", "body": GOOD}]), "plan promises 2"),
            ("no STOP", copy(text_doors_open=[{"step_id": "s1", "body": "Doors open {link} Reply YES"}]), "no literal STOP"),
            ("no reply invitation", copy(text_doors_open=[{"step_id": "s1", "body": "Doors open {link} STOP"}]), "no reply invitation"),
            ("two links", copy(text_doors_open=[{"step_id": "s1", "body": GOOD + " https://a.example https://b.example"}]), "more than one link"),
            ("the word unsubscribe", copy(text_doors_open=[{"step_id": "s1", "body": GOOD + " unsubscribe"}]), "unsubscribe"),
            ("a set the plan does not have", copy(text_extra=[{"step_id": "x", "body": GOOD}]), "not a text set"),
            ("repeated step ids", copy(text_access_link=[{"step_id": "a1", "body": GOOD}, {"step_id": "a1", "body": GOOD}]), "repeated"),
        ):
            rc, out = self.emit(c=c)
            self.assertEqual(rc, 2, label + out)
            self.assertIn(why, out, label)
            self.assertFalse(self.out.exists(), label + ": a refused emit must write nothing")

    def test_promotional_cap_is_enforced(self):
        sets = [{"id": "t%d" % i, "kind": "doors_open", "messages": 1, "promotional": True} for i in range(6)]
        c = {"sets": {s["id"]: [{"step_id": "s", "body": GOOD}] for s in sets}}
        rc, out = self.emit(p={"launch_id": "t-1", "text_sets": sets}, c=c)
        self.assertEqual(rc, 2, out)
        self.assertIn("exceed the profile cap", out)

    def test_check_sms_rejects_a_stale_profile_hash_and_a_missing_stop(self):
        self.assertEqual(self.emit()[0], 0)
        path = self.out / "text_doors_open.sms.json"
        doc = json.loads(path.read_text())
        doc["profile_sha256"] = "0" * 64
        path.write_text(json.dumps(doc))
        rc, out = run(VALIDATE, "--check-sms", path)
        self.assertEqual(rc, 1, out)
        self.assertIn("profile_sha256", out)
        doc["messages"][0]["body"] = "Doors open. Reply YES."
        path.write_text(json.dumps(doc))
        rc, out = run(VALIDATE, "--check-sms", path)
        self.assertEqual(rc, 1, out)
        self.assertIn("no literal STOP", out)

    def test_a_body_over_320_characters_is_refused_and_nothing_is_written(self):
        long_body = GOOD + " " + "x" * (321 - len(GOOD) - 1)
        self.assertEqual(len(long_body), 321)
        rc, out = self.emit(c=copy(text_doors_open=[{"step_id": "s1", "body": long_body}]))
        self.assertEqual(rc, 2, out)
        self.assertIn("321 chars > 320", out)
        self.assertFalse(self.out.exists())
        edge = GOOD + " " + "x" * (320 - len(GOOD) - 1)
        self.assertEqual(len(edge), 320)
        self.assertEqual(self.emit(c=copy(text_doors_open=[{"step_id": "s1", "body": edge}]))[0], 0)

    def test_check_sms_refuses_a_category_that_is_not_marketing_or_operational(self):
        self.assertEqual(self.emit()[0], 0)
        path = self.out / "text_doors_open.sms.json"
        doc = json.loads(path.read_text())
        doc["messages"][0]["category"] = "promo"
        path.write_text(json.dumps(doc))
        rc, out = run(VALIDATE, "--check-sms", path)
        self.assertEqual(rc, 1, out)
        self.assertIn("is not marketing|operational", out)

    def test_check_sms_refuses_a_blank_step_id(self):
        self.assertEqual(self.emit()[0], 0)
        path = self.out / "text_doors_open.sms.json"
        doc = json.loads(path.read_text())
        for blank in ("", "   "):
            doc["messages"][0]["step_id"] = blank
            path.write_text(json.dumps(doc))
            rc, out = run(VALIDATE, "--check-sms", path)
            self.assertEqual(rc, 1, out)
            self.assertIn("step_id required", out)

    def test_check_sms_on_a_file_it_cannot_read_exits_1_never_0(self):
        rc, out = run(VALIDATE, "--check-sms", self.tmp / "no-such.sms.json")
        self.assertEqual(rc, 1, out)
        self.assertIn("unreadable", out)
        junk = self.tmp / "junk.sms.json"
        junk.write_text("not json at all")
        rc, out = run(VALIDATE, "--check-sms", junk)
        self.assertEqual(rc, 1, out)
        self.assertIn("unreadable", out)

    def test_emit_exits_3_on_an_input_it_cannot_read_and_2_on_a_missing_argument(self):
        (self.tmp / "plan.json").write_text(json.dumps(plan()))
        (self.tmp / "copy.json").write_text(json.dumps(copy()))
        (self.tmp / "junk.json").write_text("not json")
        for plan_arg, copy_arg in ((self.tmp / "absent.json", self.tmp / "copy.json"),
                                   (self.tmp / "plan.json", self.tmp / "absent.json"),
                                   (self.tmp / "junk.json", self.tmp / "copy.json"),
                                   (self.tmp / "plan.json", self.tmp / "junk.json")):
            rc, out = run(EMIT, "--launch-plan", plan_arg, "--copy", copy_arg, "--out-dir", self.out)
            self.assertEqual(rc, 3, out)
            self.assertIn("cannot read input", out)
        self.assertFalse(self.out.exists())
        rc, out = run(EMIT, "--launch-plan", self.tmp / "plan.json", "--copy", self.tmp / "copy.json")
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)

    def test_copy_whose_sets_is_not_an_object_is_refused_as_no_copy_not_a_traceback(self):
        rc, out = self.emit(c={"sets": ["not", "an", "object"]})
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("no approved copy supplied", out)
        self.assertFalse(self.out.exists())

    def test_a_message_that_is_not_an_object_is_refused_not_silently_dropped(self):
        rows = [{"step_id": "a1", "body": GOOD}, "a bare string, not a message"]
        rc, out = self.emit(c=copy(text_access_link=rows))
        self.assertEqual(rc, 2, out)
        self.assertIn("a message is not an object", out)
        self.assertFalse(self.out.exists())

    # -- sweep round 1: every guard and exit path of the emitter and of --check-sms ---------------
    def _check_sms(self, mutate):
        """--check-sms on a valid emitted file after `mutate(doc)`; (rc, output)."""
        self.assertEqual(self.emit()[0], 0)
        path = self.out / "text_doors_open.sms.json"
        doc = json.loads(path.read_text())
        doc = mutate(doc) or doc
        path.write_text(json.dumps(doc))
        return run(VALIDATE, "--check-sms", path)

    def test_check_sms_passes_a_true_file_and_says_so_only_then(self):
        rc, out = self._check_sms(lambda d: None)
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS:", out)
        self.assertIn("honours the launch-text profile", out)
        rc, out = self._check_sms(lambda d: d.update(set_id=""))
        self.assertEqual(rc, 1, out)
        self.assertNotIn("PASS:", out)

    def test_check_sms_refuses_a_document_that_is_not_an_object(self):
        rc, out = self._check_sms(lambda d: ["not", "an", "object"])
        self.assertEqual(rc, 1, out)
        self.assertIn("sms set is not a JSON object", out)
        self.assertNotIn("Traceback", out)

    def test_check_sms_refuses_a_missing_blank_or_non_string_set_id(self):
        for bad in ("", "  ", 5, None):
            rc, out = self._check_sms(lambda d, bad=bad: d.update(set_id=bad))
            self.assertEqual(rc, 1, out)
            self.assertIn("set_id required", out)
        rc, out = self._check_sms(lambda d: d.pop("set_id") and None)
        self.assertEqual(rc, 1, out)
        self.assertIn("set_id required", out)

    def test_check_sms_refuses_messages_that_are_not_a_non_empty_list(self):
        for bad in ([], "text", None, {"a": 1}):
            rc, out = self._check_sms(lambda d, bad=bad: d.update(messages=bad))
            self.assertEqual(rc, 1, out)
            self.assertIn("messages must be a non-empty list", out)
            self.assertNotIn("Traceback", out)
        rc, out = self._check_sms(lambda d: d.pop("messages") and None)
        self.assertEqual(rc, 1, out)
        self.assertIn("messages must be a non-empty list", out)

    def test_check_sms_refuses_a_message_that_is_not_an_object_or_has_no_string_step_id(self):
        for bad in (5, "text", None, {"body": GOOD, "category": "marketing"},
                    {"step_id": 7, "body": GOOD, "category": "marketing"}):
            rc, out = self._check_sms(lambda d, bad=bad: d.update(messages=[bad]))
            self.assertEqual(rc, 1, out)
            self.assertIn("messages[0]: step_id required", out)
            self.assertNotIn("Traceback", out)

    def test_check_sms_refuses_a_repeated_step_id(self):
        def repeat(d):
            d["messages"].append(dict(d["messages"][0]))
        rc, out = self._check_sms(repeat)
        self.assertEqual(rc, 1, out)
        self.assertIn("repeated", out)

    def test_check_sms_refuses_an_empty_or_non_string_body_by_name(self):
        for bad in ("", "   ", 5, None):
            rc, out = self._check_sms(lambda d, bad=bad: d["messages"][0].update(body=bad))
            self.assertEqual(rc, 1, out)
            self.assertIn("body is empty", out)
            self.assertNotIn("Traceback", out)

    def test_check_message_judges_against_the_profile_it_is_handed(self):
        spec = importlib.util.spec_from_file_location("vp_under_test", VALIDATE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        doc = {"set_id": "s", "profile_sha256": module.profile_sha256(),
               "messages": [{"step_id": "a", "body": GOOD, "category": "marketing"}]}
        self.assertEqual(module.check_sms_set(doc, {"rules": {}}), [])
        fails = module.check_sms_set(doc, {"rules": {"max_characters": 10}})
        self.assertEqual(len(fails), 1)
        self.assertIn("chars > 10", fails[0])
        self.assertEqual(module.check_sms_set(doc), [])

    def test_check_sms_with_another_flag_is_not_a_check_sms_run(self):
        rc, out = run(VALIDATE, "--bogus", self.tmp / "absent.sms.json")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("unreadable", out)

    def test_emit_prints_what_it_wrote_and_may_write_into_an_existing_directory(self):
        rc, out = self.emit()
        self.assertEqual(rc, 0, out)
        self.assertIn("wrote 2 set(s): text_access_link, text_doors_open", out)
        rc, out = self.emit()  # the directory exists now
        self.assertEqual(rc, 0, out)

    def test_exactly_the_promotional_cap_is_allowed(self):
        sets = [{"id": "t%d" % i, "kind": "doors_open", "messages": 1, "promotional": True} for i in range(5)]
        c = {"sets": {s["id"]: [{"step_id": "s", "body": GOOD}] for s in sets}}
        rc, out = self.emit(p={"launch_id": "t-1", "text_sets": sets}, c=c)
        self.assertEqual(rc, 0, out)

    def test_a_plan_set_that_promises_no_count_accepts_any_number_of_messages(self):
        sets = [{"id": "text_open_ended", "kind": "doors_open", "promotional": False}]
        c = {"sets": {"text_open_ended": [{"step_id": "a", "body": GOOD}, {"step_id": "b", "body": GOOD}]}}
        rc, out = self.emit(p={"launch_id": "t-1", "text_sets": sets}, c=c)
        self.assertEqual(rc, 0, out)

    def test_a_set_with_no_copy_is_named_and_nothing_is_written(self):
        sets = copy()["sets"]
        del sets["text_access_link"]
        rc, out = self.emit(c={"sets": sets})
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("text_access_link: no approved copy supplied", out)
        self.assertFalse(self.out.exists())

    def test_copy_that_is_not_a_list_of_messages_counts_as_no_copy(self):
        rc, out = self.emit(c=copy(text_access_link="two messages, as text"))
        self.assertEqual(rc, 2, out)
        self.assertIn("text_access_link: no approved copy supplied", out)

    def test_emit_with_any_one_of_its_three_arguments_missing_is_a_usage_error_not_a_traceback(self):
        (self.tmp / "plan.json").write_text(json.dumps(plan()))
        (self.tmp / "copy.json").write_text(json.dumps(copy()))
        full = {"--launch-plan": self.tmp / "plan.json", "--copy": self.tmp / "copy.json",
                "--out-dir": self.out}
        for missing in full:
            argv = [x for k, v in full.items() if k != missing for x in (k, v)]
            rc, out = run(EMIT, *argv)
            self.assertEqual(rc, 2, missing + out)
            self.assertNotIn("Traceback", out, missing)
            self.assertIn("--launch-plan, --copy and --out-dir are required", out)
        self.assertFalse(self.out.exists())

    def test_a_launch_plan_that_is_not_an_object_or_has_null_text_sets_is_refused_not_a_traceback(self):
        for body in ([], None, 3):
            rc, out = self.emit_raw(json.dumps(body), json.dumps(copy()))
            self.assertEqual(rc, 2, repr(body) + out)
            self.assertNotIn("Traceback", out, repr(body))
            self.assertIn("the launch plan is not a JSON object", out)
        # null text_sets / null copy sets are "nothing to write": named, not a crash
        rc, out = self.emit_raw(json.dumps({"launch_id": "t-1", "text_sets": None}), json.dumps(copy()))
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("is not a text set of the launch plan", out)
        rc, out = self.emit_raw(json.dumps(plan()), json.dumps({"sets": None}))
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("no approved copy supplied", out)
        rc, out = self.emit_raw(json.dumps(plan()), json.dumps(None))
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("no approved copy supplied", out)

    def emit_raw(self, plan_text, copy_text):
        (self.tmp / "plan.json").write_text(plan_text)
        (self.tmp / "copy.json").write_text(copy_text)
        return run(EMIT, "--launch-plan", self.tmp / "plan.json", "--copy", self.tmp / "copy.json",
                   "--out-dir", self.out)

    def test_a_copy_file_that_is_not_an_object_is_refused_not_a_traceback(self):
        (self.tmp / "plan.json").write_text(json.dumps(plan()))
        (self.tmp / "copy.json").write_text(json.dumps([1, 2]))
        rc, out = run(EMIT, "--launch-plan", self.tmp / "plan.json", "--copy", self.tmp / "copy.json",
                      "--out-dir", self.out)
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("no approved copy supplied", out)

    def test_a_wrong_message_count_is_reported_alone(self):
        rc, out = self.emit(c=copy(text_access_link=[{"step_id": "a1", "body": "no stop here"}]))
        self.assertEqual(rc, 2, out)
        self.assertIn("text_access_link: 1 message(s) supplied, the plan promises 2", out)
        self.assertNotIn("no literal STOP", out)

    def test_selftest_says_so(self):
        rc, out = run(EMIT, "--selftest")
        self.assertEqual(rc, 0, out)
        self.assertIn("selftest ok", out)

    def test_selftest_and_the_existing_profile_check(self):
        self.assertEqual(run(EMIT, "--selftest")[0], 0)
        self.assertEqual(run(VALIDATE)[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
