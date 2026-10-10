#!/usr/bin/env python3
"""Planted-bad tests for setup-kie-live-adapter.sh (unit KIEX-F7-U1).

Owner order 2026-10-10 — the installer inserts ONLY `env.KIE_API_KEY`, with a
byte-minimal in-place edit. Two defects have to be impossible to ship:

  REFORMAT plant  -> test_b_pre_existing_lines_stay_byte_identical fails (rc 1)
  .bak plant      -> test_c_no_backup_file_of_any_kind      fails (rc 1)
  clean edit      -> the whole file passes                  (rc 0)

`test_b` proves it by subtraction: drop the single added line from the result
and what is left must equal the input byte for byte. Anything that re-serializes
the document (different indentation, reordered keys, dropped trailing newline)
changes lines that were never meant to move, so the subtraction stops matching.

Hermetic: every case runs the real installer against a throwaway config root and
a throwaway HOME, so no test can ever reach the machine's own settings.json.
Nothing is written inside the skill folder. The key below is a fixture literal,
never a credential, and the installer must never print it.
"""

import json
import os
import stat
import subprocess
import tempfile
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(SKILL_DIR, "setup-kie-live-adapter.sh")
BASE_URL = "https://api.kie.ai/anthropic"
KEY = "kie-live-adapter-fixture-key-not-a-secret"

# A realistic messy settings.json: tabs, uneven spacing, a nested object, an
# array, a float, a null, a pre-existing ANTHROPIC_API_KEY line, and a
# trailing newline that must survive the edit untouched.
FIXTURE_WITH_ENV = (
    "{\n"
    '\t"model": "opus",\n'
    '\t"env": {\n'
    '\t\t"ANTHROPIC_API_KEY": "preexisting-anthropic-fixture",\n'
    '\t\t"FOO":  "bar",\n'
    '\t\t"nested": {"a": [1, 2, {"b": "c"}], "f": 1.5},\n'
    '\t\t"none": null\n'
    "\t},\n"
    ' "permissions": {"allow": ["Bash(pytest*)"]},\n'
    '    "trailing": true,\n'
    '    "emptyObj": {}\n'
    "}\n"
)

# No `env` object at all, no trailing newline — the second shape the writer has
# to handle without reformatting anything it did not add.
FIXTURE_NO_ENV = (
    '{   "model" : "sonnet" ,\n'
    '    "hooks": { "pre": [ "a" , "b" ] }\n'
    '}'
)


def added_lines(old, new):
    """Lines present in `new` but not in `old`, as a multiset difference.

    Used two ways: to assert exactly one entry was added, and (by deleting them
    from `new`) to assert every other byte stayed put.
    """
    pool = list(old.splitlines(keepends=True))
    extra = []
    for line in new.splitlines(keepends=True):
        if line in pool:
            pool.remove(line)
        else:
            extra.append(line)
    return extra, "".join(pool)


class InstallerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        self.root = os.path.join(self.home, ".claude")
        os.makedirs(self.root)
        self.path = os.path.join(self.root, "settings.json")

    def write_fixture(self, text):
        with open(self.path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def run_installer(self, key=KEY, *extra):
        env = dict(os.environ)
        env.pop("CLAUDE_CONFIG_DIR", None)
        env.pop("KIE_API_KEY", None)
        env.pop("API_DOCS_PATH", None)
        if key is not None:
            env["KIE_API_KEY"] = key
        env["HOME"] = self.home
        return subprocess.run(
            [INSTALLER, "--config-root", self.root, *extra],
            capture_output=True, text=True, env=env, cwd=self.tmp.name,
        )

    def read(self):
        with open(self.path, "rb") as fh:
            return fh.read().decode("utf-8")

    def names(self):
        return sorted(os.listdir(self.root))


class TestMinimalInPlaceEdit(InstallerBase):
    def test_b_pre_existing_lines_stay_byte_identical(self):
        """REFORMAT tripwire: exactly one line added, every other byte untouched."""
        self.write_fixture(FIXTURE_WITH_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        new = self.read()
        extra, leftover = added_lines(FIXTURE_WITH_ENV, new)
        self.assertEqual(len(extra), 1, "more than one line added: %r" % extra)
        self.assertTrue(
            extra[0].lstrip().startswith('"KIE_API_KEY"'),
            "the added line is not the KIE_API_KEY entry: %r" % extra)
        self.assertEqual(
            leftover, "",
            "pre-existing bytes moved — the file was reformatted:\n%r" % leftover)
        self.assertTrue(new.endswith("\n"), "trailing newline style changed")

    def test_g_settings_without_env_object(self):
        """The env object is created by insertion; the rest of the file is inert."""
        self.write_fixture(FIXTURE_NO_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        new = self.read()
        self.assertFalse(FIXTURE_NO_ENV.endswith("\n"))
        self.assertTrue(new.endswith("}"), "trailing newline was added")
        start = new.index('"env": {')
        end = new.index('"KIE_API_KEY"', start)
        end = new.index(",", end) + 1
        self.assertEqual(new[:start] + new[end:], FIXTURE_NO_ENV,
                         "a pre-existing byte changed when env was created")
        self.assertEqual(json.loads(new)["env"], {"KIE_API_KEY": KEY})

    def test_h_existing_kie_key_left_byte_identical(self):
        """An already-present entry is never rewritten — no value is ever moved."""
        already = ('{\n  "env": {\n    "KIE_API_KEY": "some-other-value",\n'
                   '    "A": 1\n  }\n}\n')
        self.write_fixture(already)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read(), already)
        self.assertIn("already present", proc.stdout)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_i_missing_settings_json_created(self):
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads(self.read())
        self.assertEqual(doc, {"env": {"KIE_API_KEY": KEY}})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)


class TestSingleAllowedKey(InstallerBase):
    def test_a_only_env_kie_api_key_is_added(self):
        self.write_fixture(FIXTURE_WITH_ENV)
        before = json.loads(FIXTURE_WITH_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        after = json.loads(self.read())

        self.assertEqual(list(after), list(before), "top-level key order changed")
        raw = self.read()
        # Every other key must appear exactly as often as it did before: a plant
        # that inserts a second ANTHROPIC_API_KEY hides inside json.loads(), but
        # not inside a literal count. KIE_API_KEY is the one allowed +1.
        for token in ('"ANTHROPIC_API_KEY"', '"ANTHROPIC_BASE_URL"', '"FOO"',
                      '"model"', '"permissions"', '"trailing"', '"emptyObj"'):
            self.assertEqual(raw.count(token), FIXTURE_WITH_ENV.count(token),
                             "count of %s changed: an entry was duplicated or dropped"
                             % token)
        self.assertEqual(raw.count('"KIE_API_KEY"'), 1)
        self.assertEqual(set(after["env"]) - set(before["env"]), {"KIE_API_KEY"})
        self.assertEqual(set(before["env"]) - set(after["env"]), set())
        for key in before["env"]:
            self.assertEqual(after["env"][key], before["env"][key],
                             "pre-existing value changed: %s" % key)
        added = set(after["env"]) - set(before["env"])
        for key in added:
            self.assertFalse(key.startswith("ANTHROPIC_"),
                             "an ANTHROPIC_* key was inserted: %s" % key)
        self.assertNotIn("ANTHROPIC_BASE_URL", after["env"])
        for container in (after, after.get("env") or {}):
            for key, val in container.items():
                self.assertNotIn("api.kie.ai", json.dumps(val),
                                 "a base URL was written into settings.json")
        self.assertEqual(after["env"]["KIE_API_KEY"], KEY)

    def test_f_base_url_reported_not_written(self):
        self.write_fixture(FIXTURE_WITH_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(BASE_URL, proc.stdout)
        self.assertIn("never written to settings.json", proc.stdout)
        self.assertNotIn("api.kie.ai", self.read())

    def test_d_key_value_never_printed(self):
        self.write_fixture(FIXTURE_WITH_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        stream = proc.stdout + proc.stderr
        self.assertNotIn(KEY, stream, "the key value reached stdout/stderr")
        self.assertIn("KIE key: SET", stream)
        self.assertNotIn(KEY, json.dumps(sorted(os.listdir(self.root))))

    def test_e_settings_mode_600(self):
        self.write_fixture(FIXTURE_WITH_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        proc2 = self.run_installer()          # idempotent re-run keeps the mode
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)


class TestNoBackupEver(InstallerBase):
    def test_c_no_backup_file_of_any_kind(self):
        """.bak tripwire: the root holds settings.json and nothing else."""
        self.write_fixture(FIXTURE_WITH_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        names = self.names()
        self.assertEqual(names, ["settings.json"],
                         "stray files appeared beside settings.json: %r" % names)
        for name in names:
            self.assertNotIn("bak", name.lower(), "a backup file was written")

    def test_j_no_backup_when_env_is_created(self):
        self.write_fixture(FIXTURE_NO_ENV)
        proc = self.run_installer()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.names(), ["settings.json"])

    def test_k_key_absent_writes_nothing(self):
        before = self.names()
        proc = self.run_installer(key=None)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("KIE key: NOT SET", proc.stdout)
        self.assertEqual(self.names(), before)


if __name__ == "__main__":
    unittest.main()
