"""KEF001 K1: the KIE key is found wherever the box keeps it, under any alias.

Hermetic: temp stores + cleared KIE env; ENV_FILE_CANDIDATES is monkeypatched so
this box's real stores can never answer. Values are synthetic, never printed.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import secret_helper as sh  # noqa: E402

KEY = "k" + "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"  # synthetic 33 chars


def _resolve(files):
    """files: {filename: content}. Returns (value, source) with only those stores."""
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, body in files.items():
            p = Path(d) / name
            p.write_text(body)
            paths.append(str(p))
        env = {k: v for k, v in os.environ.items()
               if k not in ("KIE_API_KEY", "KIE_AI_KEY", "KIEAI_API_KEY", "KIE_AI_API_KEY", "KIE_KEY")}
        with mock.patch.object(sh, "ENV_FILE_CANDIDATES", paths), \
             mock.patch.dict(os.environ, env, clear=True):
            return sh.resolve_secret_with_source("KIE_API_KEY")


class KieKeyLookup(unittest.TestCase):
    def test_found_when_only_in_dot_env(self):
        v, src = _resolve({".env": f"KIE_API_KEY={KEY}\n"})
        self.assertEqual(v, KEY)
        self.assertTrue(src.startswith("file:") and src.endswith(":KIE_API_KEY"))
        self.assertNotIn(KEY, src)

    def test_found_when_only_in_workspace_secrets_env_as_KIE_AI_KEY(self):
        v, src = _resolve({"secrets.env": f"KIE_AI_KEY={KEY}\n"})
        self.assertEqual(v, KEY)
        self.assertTrue(src.endswith(":KIE_AI_KEY"))

    def test_absent_returns_none_with_empty_source(self):
        self.assertEqual(_resolve({".env": "OTHER=1\n"}), (None, ""))

    def test_workspace_candidates_are_in_the_real_list(self):
        self.assertTrue(any(p.endswith("workspace/secrets.env") for p in sh.ENV_FILE_CANDIDATES))
        self.assertIn("KIE_AI_KEY", sh.alias_list("KIE_API_KEY"))


class Skill48Wiring(unittest.TestCase):
    def test_skill48_resolve_kie_key_uses_alias_and_rejects_placeholder(self):
        sys.path.insert(0, str(HERE.parent / "48-facebook-ad-generator" / "scripts"))
        import ad_build_check as abc
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "secrets.env"
            p.write_text(f"KIE_AI_KEY={KEY}\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith("KIE")}
            with mock.patch.object(sh, "ENV_FILE_CANDIDATES", [str(p)]), \
                 mock.patch.dict(os.environ, env, clear=True):
                logs = []
                self.assertEqual(abc.resolve_kie_key(logs.append), KEY)
                self.assertEqual(len(logs), 1)
                self.assertNotIn(KEY, logs[0])
                p.write_text("KIE_AI_KEY=YOUR_CLIENT_KIE_API_KEY_HERE\n")
                self.assertIsNone(abc.resolve_kie_key())


class Skill59PreflightWiring(unittest.TestCase):
    def _run(self, home, **env):
        import re, subprocess
        src = (HERE.parent / "59-anthology-engine" / "preflight.sh").read_text()
        blk = re.search(r"^# KEF001.*?^fi$", src, re.S | re.M).group(0)
        e = {k: v for k, v in os.environ.items() if not k.startswith("KIE")}
        e.update(HOME=home, SELF_DIR=str(HERE.parent / "59-anthology-engine"), **env)
        return subprocess.run(["bash", "-c", blk + '\necho "len=${#KIE_API_KEY}"'],
                              env=e, capture_output=True, text=True)

    def test_preflight_exports_key_found_under_alias_and_logs_source_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".openclaw" / "workspace").mkdir(parents=True)
            (Path(d) / ".openclaw" / "workspace" / "secrets.env").write_text(f"KIE_AI_KEY={KEY}\n")
            r = self._run(d)
            self.assertIn(f"len={len(KEY)}", r.stdout)
            self.assertIn("KIE key resolved from file:", r.stderr)
            self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_preflight_absent_stays_unset_and_explicit_empty_wins(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("len=0", self._run(d).stdout)
            (Path(d) / ".openclaw").mkdir()
            (Path(d) / ".openclaw" / ".env").write_text(f"KIE_API_KEY={KEY}\n")
            self.assertIn("len=0", self._run(d, KIE_API_KEY="").stdout)


if __name__ == "__main__":
    unittest.main()
