#!/usr/bin/env python3
"""W1-agnes-core-U3 tests: remembered answer round trip + the presence-only key lookup.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/agnes_access
  or: python3 test_agnes_access.py
No network. No live key: every key here is an obvious fake string.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
try:                                   # pytest imports the agnes_access
    from agnes_access import agnes_access as AA  # noqa: E402
except ImportError:                    # PACKAGE (dir has __init__.py) first;
    import agnes_access as AA          # a script run gets the module file

FAKE_ENV_KEY = "sk-fake-agnes-key-env-0001"
FAKE_DOCS_KEY = "sk-fake-agnes-key-docs-0002"


class Remembered(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.client = os.path.join(self.t, "client-a")

    def test_nothing_yet_is_unknown(self):
        self.assertEqual(AA.remembered(self.client), "unknown")
        self.assertEqual(AA.remembered(None), "unknown")
        self.assertEqual(AA.remembered(""), "unknown")

    def test_unknown_yes_no_round_trip(self):
        self.assertEqual(AA.remember(self.client, "yes"), "yes")
        self.assertEqual(AA.remembered(self.client), "yes")
        self.assertEqual(AA.remember(self.client, "no"), "no")
        self.assertEqual(AA.remembered(self.client), "no")

    def test_remember_writes_the_documented_shape(self):
        AA.remember(self.client, "yes")
        with open(os.path.join(self.client, AA.AGNES_FILE), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(rec["subscriber"], "yes")
        self.assertRegex(rec["answered_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_remember_keeps_the_other_keys(self):
        os.makedirs(self.client, exist_ok=True)
        with open(os.path.join(self.client, AA.AGNES_FILE), "w", encoding="utf-8") as f:
            json.dump({"subscriber": "yes", "answered_at": "2026-10-13T00:00:00Z",
                       "plan": "plus", "notes": "asked on the phone"}, f)
        AA.remember(self.client, "no")
        with open(os.path.join(self.client, AA.AGNES_FILE), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(rec["subscriber"], "no")
        self.assertEqual(rec["plan"], "plus")
        self.assertEqual(rec["notes"], "asked on the phone")
        self.assertNotEqual(rec["answered_at"], "2026-10-13T00:00:00Z")

    def test_two_clients_never_share_an_answer(self):
        other = os.path.join(self.t, "client-b")
        AA.remember(self.client, "no")
        self.assertEqual(AA.remembered(other), "unknown")

    def test_unreadable_file_reads_unknown(self):
        os.makedirs(self.client, exist_ok=True)
        with open(os.path.join(self.client, AA.AGNES_FILE), "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(AA.remembered(self.client), "unknown")

    def test_unrecognized_answer_reads_unknown(self):
        os.makedirs(self.client, exist_ok=True)
        with open(os.path.join(self.client, AA.AGNES_FILE), "w", encoding="utf-8") as f:
            json.dump({"subscriber": "maybe", "other": 1}, f)
        self.assertEqual(AA.remembered(self.client), "unknown")

    def test_a_bad_answer_is_refused_and_written_nowhere(self):
        for bad in ("maybe", "", None, "YES PLEASE"):
            with self.assertRaises(AA.AccessError):
                AA.remember(self.client, bad)
        self.assertFalse(os.path.exists(os.path.join(self.client, AA.AGNES_FILE)))

    def test_no_temp_file_is_left_behind(self):
        AA.remember(self.client, "yes")
        self.assertEqual(sorted(os.listdir(self.client)), [AA.AGNES_FILE])


class KeyLookup(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.docs = os.path.join(self.t, "Documents")
        os.makedirs(self.docs)

    def _write_docs(self, text):
        with open(os.path.join(self.docs, AA.API_DOCS_NAME), "w", encoding="utf-8") as f:
            f.write(text)

    def test_env_agnes_ai_api_key_wins(self):
        self.assertEqual(AA.key_value(env={"AGNES_AI_API_KEY": FAKE_ENV_KEY},
                                      documents_dir=self.docs), FAKE_ENV_KEY)

    def test_env_agnes_api_key_is_the_second_name(self):
        self.assertEqual(AA.key_value(env={"AGNES_API_KEY": FAKE_ENV_KEY},
                                      documents_dir=self.docs), FAKE_ENV_KEY)

    def test_the_first_name_wins_when_both_are_set(self):
        self.assertEqual(
            AA.key_value(env={"AGNES_AI_API_KEY": FAKE_ENV_KEY,
                              "AGNES_API_KEY": FAKE_DOCS_KEY},
                         documents_dir=self.docs), FAKE_ENV_KEY)

    def test_no_env_falls_through_to_api_docs_md(self):
        self._write_docs("# my keys\n\nOLLAMA_API_KEY=%s\nAGNES_API_KEY=%s\n"
                         % (FAKE_ENV_KEY, FAKE_DOCS_KEY))
        self.assertEqual(AA.key_value(env={}, documents_dir=self.docs), FAKE_DOCS_KEY)

    def test_api_docs_md_accepts_spaces_and_quotes(self):
        self._write_docs("AGNES_API_KEY = \"%s\"\n" % FAKE_DOCS_KEY)
        self.assertEqual(AA.key_value(env={}, documents_dir=self.docs), FAKE_DOCS_KEY)

    def test_api_docs_md_comments_and_headings_are_not_keys(self):
        self._write_docs("## AGNES_API_KEY=not-the-key\n<!-- AGNES_API_KEY=also-not -->\n"
                         "```\nAGNES_API_KEY=fenced-not-it\n```\n"
                         "OLLAMA_API_KEY=%s\n" % FAKE_ENV_KEY)
        self.assertIsNone(AA.key_value(env={}, documents_dir=self.docs))

    def test_missing_api_docs_md_is_none(self):
        self.assertIsNone(AA.key_value(env={}, documents_dir=self.docs))
        self.assertIsNone(AA.key_value(env={}, documents_dir=os.path.join(self.t, "nope")))

    def test_a_file_without_the_agnes_line_is_none(self):
        self._write_docs("DEEPSEEK_API_KEY=%s\n" % FAKE_ENV_KEY)
        self.assertIsNone(AA.key_value(env={}, documents_dir=self.docs))

    def test_placeholders_are_absent(self):
        for bad in ("replace_with_real_key", "ChangeMe", "your-key-here",
                    "<your key here>", "{{AGNES_API_KEY}}", "xxx", ""):
            self.assertIsNone(AA.key_value(env={"AGNES_AI_API_KEY": bad},
                                           documents_dir=self.docs),
                              "placeholder %r counted as a key" % bad)
            self.assertFalse(AA.key_present(env={"AGNES_AI_API_KEY": bad},
                                            documents_dir=self.docs))

    def test_a_placeholder_env_falls_through_to_the_file(self):
        self._write_docs("AGNES_API_KEY=%s\n" % FAKE_DOCS_KEY)
        self.assertEqual(AA.key_value(env={"AGNES_AI_API_KEY": "replace_with_real_key"},
                                      documents_dir=self.docs), FAKE_DOCS_KEY)

    def test_placeholder_in_the_file_is_none(self):
        self._write_docs("AGNES_API_KEY=replace_with_real_key\n")
        self.assertIsNone(AA.key_value(env={}, documents_dir=self.docs))

    def test_key_present_is_the_only_thing_to_print(self):
        self.assertTrue(AA.key_present(env={"AGNES_AI_API_KEY": FAKE_ENV_KEY},
                                       documents_dir=self.docs))
        self.assertFalse(AA.key_present(env={}, documents_dir=self.docs))


class Cli(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.client = os.path.join(self.t, "client-a")
        self.docs = os.path.join(self.t, "Documents")
        os.makedirs(self.docs)

    def _run(self, env_extra):
        env = dict(os.environ)
        env.pop("AGNES_AI_API_KEY", None)
        env.pop("AGNES_API_KEY", None)
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "agnes_access.py"), "status",
             "--client-dir", self.client, "--documents-dir", self.docs],
            capture_output=True, text=True, env=env)

    def test_status_is_one_json_line_and_never_the_key(self):
        out = self._run({"AGNES_AI_API_KEY": FAKE_ENV_KEY})
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout.strip())
        self.assertEqual(sorted(payload), ["key_present", "remembered"])
        self.assertEqual(payload["remembered"], "unknown")
        self.assertIs(payload["key_present"], True)
        for stream in (out.stdout, out.stderr):
            self.assertNotIn(FAKE_ENV_KEY, stream)
            self.assertNotIn(FAKE_DOCS_KEY, stream)

    def test_status_reports_the_remembered_answer(self):
        AA.remember(self.client, "no")
        payload = json.loads(self._run({}).stdout)
        self.assertEqual(payload["remembered"], "no")
        self.assertIs(payload["key_present"], False)

    def test_status_reads_the_fake_key_from_api_docs_md(self):
        with open(os.path.join(self.docs, AA.API_DOCS_NAME), "w", encoding="utf-8") as f:
            f.write("AGNES_API_KEY=%s\n" % FAKE_DOCS_KEY)
        out = self._run({})
        self.assertIs(json.loads(out.stdout)["key_present"], True)
        self.assertNotIn(FAKE_DOCS_KEY, out.stdout + out.stderr)

    def test_no_command_prints_help_and_fails(self):
        env = dict(os.environ)
        env["AGNES_AI_API_KEY"] = FAKE_ENV_KEY
        out = subprocess.run([sys.executable, os.path.join(HERE, "agnes_access.py")],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 2)
        self.assertNotIn(FAKE_ENV_KEY, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
