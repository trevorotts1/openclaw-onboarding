#!/usr/bin/env python3
"""ILG-009 (c): update-interview-state.sh STATE_DIR resolution.

Offline. No box, no state writes. Asserts on the script text:
  (1) the canonical platform resolver (platform/common.sh
      oc_set_platform_paths) is sourced and its workspace answer is
      preferred when it holds the state file;
  (2) the legacy /data-else-HOME directory check is retained as fallback;
  (3) the fail-closed "cannot find .openclaw/workspace" error is retained.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "23-ai-workforce-blueprint" / "scripts" / "update-interview-state.sh"


class StateDirResolver(unittest.TestCase):
    def setUp(self):
        self.source = SCRIPT.read_text()

    def test_canonical_resolver_preferred(self):
        self.assertIn("platform/common.sh", self.source)
        self.assertIn("oc_set_platform_paths", self.source)
        self.assertIn("OC_WORKSPACE_DEFAULT", self.source)
        self.assertIn(".workforce-build-state.json", self.source)

    def test_legacy_fallback_retained(self):
        self.assertIn("/data/.openclaw/workspace", self.source)
        self.assertIn("$HOME/.openclaw/workspace", self.source)

    def test_fail_closed_without_workspace(self):
        self.assertIn("cannot find .openclaw/workspace directory", self.source)


if __name__ == "__main__":
    unittest.main()
