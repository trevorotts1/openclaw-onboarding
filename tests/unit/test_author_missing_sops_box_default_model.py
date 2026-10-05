#!/usr/bin/env python3
"""author-missing-sops.py must author with the BOX'S OWN default model.

Rules covered (client sovereignty):
  1. The model is read from the box's openclaw.json agents.defaults.model
     (string or {"primary": ...}) - never a hardcoded id.
  2. A forbidden (Anthropic) default is never used and never swapped out.
  3. No resolvable default => the gap is recorded on the record and the role is
     stopped. Nothing is guessed, no sub-agent is spawned.

Run: python3 tests/unit/test_author_missing_sops_box_default_model.py
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "23-ai-workforce-blueprint" / "scripts" / "author-missing-sops.py"
sys.path.insert(0, str(SCRIPT.parent))


def load_module():
    spec = importlib.util.spec_from_file_location("ams_box_default", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Box(unittest.TestCase):
    def setUp(self):
        self.ams = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        # Hermetic: never read the real box config during tests.
        self.ams._config_candidates = lambda explicit=None: [explicit]

    def write_cfg(self, cfg):
        p = self.dir / "openclaw.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        return str(p)


class TestResolveBoxDefault(_Box):
    def test_dict_primary(self):
        p = self.write_cfg({"agents": {"defaults": {"model": {"primary": "ollama/box-own:cloud"}}}})
        self.assertEqual(self.ams.resolve_box_default_model(p), ("ollama/box-own:cloud", ""))

    def test_plain_string(self):
        p = self.write_cfg({"agents": {"defaults": {"model": "agnes/some-model"}}})
        self.assertEqual(self.ams.resolve_box_default_model(p)[0], "agnes/some-model")

    def test_missing_config_is_gap(self):
        mid, why = self.ams.resolve_box_default_model(str(self.dir / "nope.json"))
        self.assertIsNone(mid)
        self.assertIn("no openclaw.json", why)

    def test_malformed_config_is_gap(self):
        p = self.dir / "openclaw.json"
        p.write_text("{not json", encoding="utf-8")
        mid, why = self.ams.resolve_box_default_model(str(p))
        self.assertIsNone(mid)
        self.assertIn("cannot read", why)

    def test_no_default_is_gap(self):
        mid, why = self.ams.resolve_box_default_model(self.write_cfg({"agents": {"defaults": {}}}))
        self.assertIsNone(mid)
        self.assertIn("no agents.defaults.model", why)

    def test_forbidden_default_never_used(self):
        for bad in ("anthropic/some-model", "openrouter/anthropic/x", "claude-whatever"):
            mid, why = self.ams.resolve_box_default_model(
                self.write_cfg({"agents": {"defaults": {"model": {"primary": bad}}}}))
            self.assertIsNone(mid, bad)
            self.assertIn("forbidden", why)

    def test_resolve_model_returns_none_on_gap(self):
        self.ams._config_candidates = lambda explicit=None: []
        self.assertIsNone(self.ams.resolve_model())


class TestNoHardcodedModel(unittest.TestCase):
    def test_source_has_no_model_id_literals(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for needle in ("kimi", "deepseek", "ollama/", "glm", "gpt-", "minimax"):
            self.assertNotIn(needle, src.lower(), f"hardcoded model hint {needle!r}")
        self.assertIsNone(re.search(r'return\s+"[a-z-]+/[^"]*:cloud"', src))


class TestMainGapAndHappyPath(_Box):
    def setUp(self):
        super().setUp()
        self.ams.openclaw_available = lambda: False  # never spawn anything
        self.manifest = self.dir / "SOP-NEEDED.json"
        self.manifest.write_text(json.dumps({"records": [{
            "id": "sop-needed-0001", "role": "Widget Wrangler", "department": "ops",
            "role_folder": str(self.dir / "missing-role"), "how_to_path": "",
            "status": "routed", "role_description": "x"}]}), encoding="utf-8")

    def run_main(self):
        return self.ams.main(["--sop-needed", str(self.manifest), "--apply"])

    def test_no_default_records_gap_and_stops(self):
        self.ams._config_candidates = lambda explicit=None: []
        rc = self.run_main()
        self.assertEqual(rc, 2)
        rec = json.loads(self.manifest.read_text())["records"][0]
        self.assertEqual(rec["status"], "routed")
        self.assertIn("no openclaw.json", rec["model_gap"])
        self.assertFalse((self.dir / ".sop-author-queue").exists(), "must not queue work")

    def test_box_default_flows_into_work_file(self):
        cfg = self.write_cfg({"agents": {"defaults": {"model": {"primary": "ollama/box-own:cloud"}}}})
        self.ams._config_candidates = lambda explicit=None: [cfg]
        rc = self.run_main()
        self.assertNotEqual(rc, 2, "a resolved default must not be treated as a gap")
        work = list((self.dir / ".sop-author-queue").glob("sop-author-*.md"))
        self.assertEqual(len(work), 1)
        text = work[0].read_text(encoding="utf-8")
        self.assertIn("`ollama/box-own:cloud`", text)
        self.assertIn("this box's own default model", text)
        self.assertNotIn("model_gap", self.manifest.read_text())


if __name__ == "__main__":
    unittest.main()
