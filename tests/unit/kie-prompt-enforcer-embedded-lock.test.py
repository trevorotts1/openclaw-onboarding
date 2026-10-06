#!/usr/bin/env python3
"""Lock for the embedded copies of the KIE prompt enforcer (rule 12) that standalone gates fall back to.

  * every copy listed in shared-utils/kie_prompt_gates.json "enforcer_copies" is byte-identical to
    shared-utils/kie_prompt_enforcer.py, and the last-known limit table matches the registry
    (scripts/embed-kie-prompt-enforcer.py --check);
  * a copy, loaded with NO shared-utils and NO Skill 74 adapter, still enforces the identical rule through
    last_known(): 79 percent rejected naming the chars to add, 95 and 100 percent pass, 101 percent rejected naming
    the chars to cut, verbatim exempt from the floor, and a model with no known limit FAILS CLOSED (never open).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DECL = json.loads((REPO / "shared-utils" / "kie_prompt_gates.json").read_text(encoding="utf-8"))
M = "gpt-image-2-5-sunburst-text-to-image"


def load(rel):
    os.environ["HOME"] = tempfile.mkdtemp()
    os.environ["KIE_LIVE_ADAPTER_PATH"] = ""  # no Skill 74 adapter
    os.environ.pop("KIE_API_KEY", None)
    spec = importlib.util.spec_from_file_location("embedded_copy_under_test", REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestEmbeddedCopies(unittest.TestCase):
    def test_generator_check_passes(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "embed-kie-prompt-enforcer.py"), "--check"],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_copy_is_byte_identical_to_the_source(self):
        src = (REPO / "shared-utils" / "kie_prompt_enforcer.py").read_bytes()
        self.assertGreaterEqual(len(DECL["enforcer_copies"]), 2)
        for rel in DECL["enforcer_copies"]:
            self.assertEqual((REPO / rel).read_bytes(), src, rel)

    def test_a_copy_enforces_the_same_rule_without_the_adapter(self):
        for rel in DECL["enforcer_copies"]:
            k = load(rel)
            fb = k.last_known(M)
            self.assertEqual(fb, 20000)
            low = k.check(M, "x" * (fb * 79 // 100), fallback_max=fb)
            self.assertFalse(low["ok"])
            self.assertIn("ADD at least 200", low["message"])
            for pct in (95, 100):
                self.assertTrue(k.check(M, "x" * (fb * pct // 100), fallback_max=fb)["ok"], (rel, pct))
            high = k.check(M, "x" * (fb * 101 // 100), fallback_max=fb)
            self.assertFalse(high["ok"])
            self.assertIn("CUT exactly 200", high["message"])
            self.assertTrue(k.check(M, "short spoken line", "verbatim", fallback_max=fb)["ok"])

    def test_an_unlisted_model_fails_closed_without_the_adapter(self):
        k = load(DECL["enforcer_copies"][0])
        v = k.check("no-such-model", "x" * 100, fallback_max=k.last_known("no-such-model"))
        self.assertFalse(v["ok"])
        self.assertEqual(v["status"], "ADAPTER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
