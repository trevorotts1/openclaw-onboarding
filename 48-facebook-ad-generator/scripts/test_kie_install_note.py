#!/usr/bin/env python3
"""INF002: installer 48 installs with or without a KIE key; the lookup reads every
store/alias, skips placeholders for a real key, and never prints a value.
Hermetic: temp stores, KIE env cleared, ENV_FILE_CANDIDATES patched. Synthetic keys."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ad_build_check as abc  # noqa: E402
import kie_install_note as kin  # noqa: E402

KEY = "".join("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"[(i * 37 + 3) % 57]
              for i in range(32))
PLACEHOLDER = "YOUR_CLIENT_KIE_API_KEY_HERE"


class Note(unittest.TestCase):
    def _run(self, files):
        """files: {relative path: content}. Returns (result, status_exists, printed)."""
        sh = abc._secret_helper()
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for rel, body in files.items():
                p = Path(d) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body)
                paths.append(str(p))
            env = {k: v for k, v in os.environ.items() if not k.startswith("KIE")}
            status = Path(d) / "install-status.txt"
            status.write_text("stale\n") if "stale" in files else None
            out = []
            with mock.patch.object(sh, "ENV_FILE_CANDIDATES", paths), \
                 mock.patch.dict(os.environ, env, clear=True):
                res = kin.run(status, out.append)
            return res, status.exists(), "\n".join(out), (status.read_text() if status.exists() else "")

    def test_keyless_box_installs_with_one_note(self):
        res, exists, printed, body = self._run({"secrets/.env": "OTHER=1\n"})
        self.assertEqual(res, "missing")
        self.assertTrue(exists)
        self.assertIn("KIE API key needed", body)
        self.assertIn("KIE_API_KEY", printed)

    def test_box_with_key_has_no_note_and_stale_note_removed(self):
        res, exists, printed, _ = self._run({"secrets/.env": f"KIE_API_KEY={KEY}\n", "stale": ""})
        self.assertEqual(res, "found")
        self.assertFalse(exists)
        self.assertNotIn(KEY, printed)
        self.assertNotIn("needed", printed)

    def test_every_store_and_alias(self):
        for rel, line in (("workspace/.env", "KIE_API_KEY"), ("workspace/secrets/.env", "KIE_API_KEY"),
                          ("workspace/secrets.env", "KIE_AI_KEY"), ("clawd/secrets/.env", "KIEAI_API_KEY"),
                          ("service-env/ai.openclaw.gateway.env", "KIE_API_KEY")):
            with self.subTest(rel=rel):
                self.assertEqual(self._run({rel: f"export {line}='{KEY}'\n"})[0], "found")

    def test_placeholder_in_one_store_never_shadows_a_real_key_in_another(self):
        files = {"a/.env": f"KIE_API_KEY={PLACEHOLDER}\n", "b/.env": f"KIE_AI_KEY={KEY}\n"}
        self.assertEqual(self._run(files)[0], "found")
        files = {"b/.env": f"KIE_AI_KEY={KEY}\n", "a/.env": f"KIE_API_KEY={PLACEHOLDER}\n"}
        self.assertEqual(self._run(files)[0], "found")

    def test_only_placeholder_counts_as_missing(self):
        self.assertEqual(self._run({".env": f"KIE_API_KEY={PLACEHOLDER}\n"})[0], "missing")
        self.assertEqual(self._run({".env": "KIE_API_KEY=short\n"})[0], "missing")

    def test_container_roots_are_in_the_real_store_list(self):
        sh = abc._secret_helper()
        for frag in ("/home/node/.openclaw/.env", "/data/.openclaw/secrets/.env",
                     "/workspace/.env", "/workspace/secrets/.env", "clawd/secrets/.env"):
            self.assertTrue(any(p.endswith(frag) for p in sh.ENV_FILE_CANDIDATES), frag)

    def test_unchecked_when_helper_missing_never_claims_keyless(self):
        out = []
        with mock.patch.object(abc, "_secret_helper", return_value=None), \
             tempfile.TemporaryDirectory() as d:
            res = kin.run(Path(d) / "s.txt", out.append)
            self.assertEqual(res, "unchecked")
            self.assertFalse((Path(d) / "s.txt").exists())

    def test_zero_balance_is_not_an_install_concern(self):
        # the install note never calls the credit endpoint
        with mock.patch.object(abc, "_fetch_kie_balance", side_effect=AssertionError("called")):
            self._run({".env": f"KIE_API_KEY={KEY}\n"})


if __name__ == "__main__":
    unittest.main()
