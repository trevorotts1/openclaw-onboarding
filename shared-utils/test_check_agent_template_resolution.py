#!/usr/bin/env python3
"""Tests for check_agent_template_resolution.py with mutation proof."""

import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_agent_template_resolution import check_file, find_markers, scan_directory


class TestFindMarkers(unittest.TestCase):
    def test_clean(self): self.assertEqual(find_markers("# Clean\n"), [])
    def test_single(self): self.assertEqual(find_markers("{{OWNER_NAME}}"), ["{{OWNER_NAME}}"])
    def test_multiple(self): self.assertEqual(len(find_markers("{{A}} {{B}}")), 2)
    def test_duplicates(self): self.assertEqual(find_markers("{{X}} {{X}}"), ["{{X}}"])
    def test_curly_braces_not_markers(self): self.assertEqual(find_markers("{single}"), [])
    def test_empty(self): self.assertEqual(find_markers(""), [])


class TestCheckFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
    def _w(self, name, content):
        p = os.path.join(self.tmpdir, name)
        with open(p, "w") as f: f.write(content)
        return p
    def test_clean(self): self.assertIsNone(check_file(self._w("S.md", "# Clean\n")))
    def test_dirty(self):
        r = check_file(self._w("I.md", "{{ROLE_TITLE}}\n"))
        self.assertIsNotNone(r); self.assertIn("{{ROLE_TITLE}}", r["markers"])
    def test_many(self):
        r = check_file(self._w("I.md", "{{A}}\n{{B}}\n{{C}}\n"))
        self.assertEqual(r["marker_count"], 3)
    def test_missing_file(self): self.assertIsNone(check_file("/no/such/SOUL.md"))


class TestScanDirectory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
    def _make(self, name, clean=True):
        d = os.path.join(self.tmpdir, name); os.makedirs(d, exist_ok=True)
        c = "# Clean\n" if clean else "{{OWNER_NAME}}\n"
        with open(os.path.join(d, "SOUL.md"), "w") as f: f.write(c)
        with open(os.path.join(d, "IDENTITY.md"), "w") as f: f.write(c)
    def test_all_clean(self): self._make("a"); self._make("b"); self.assertEqual(len(scan_directory(self.tmpdir)), 0)
    def test_one_dirty(self): self._make("a"); self._make("b", clean=False); self.assertEqual(len(scan_directory(self.tmpdir)), 2)
    def test_empty(self): self.assertEqual(len(scan_directory(self.tmpdir)), 0)


class TestMutationProof(unittest.TestCase):
    """GREEN -> RED -> GREEN cycles prove the gate is not always-passing/always-failing."""
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
    def _w(self, name, content):
        p = os.path.join(self.tmpdir, name)
        with open(p, "w") as f: f.write(content)
        return p
    def test_soul_mutation(self):
        clean, dirty = "# SOUL\nReal.\n", "# SOUL\n{{ROLE_TITLE}}\n"
        p = self._w("SOUL.md", clean)
        self.assertIsNone(check_file(p), "GREEN")
        with open(p, "w") as f: f.write(dirty)
        self.assertIsNotNone(check_file(p), "RED")
        with open(p, "w") as f: f.write(clean)
        self.assertIsNone(check_file(p), "GREEN")
    def test_owner_name_mutation(self):
        clean, dirty = "# ID\nOwner: boss\n", "# ID\nOwner: {{OWNER_NAME}}\n"
        p = self._w("IDENTITY.md", clean)
        self.assertIsNone(check_file(p))
        with open(p, "w") as f: f.write(dirty)
        self.assertIsNotNone(check_file(p))
        with open(p, "w") as f: f.write(clean)
        self.assertIsNone(check_file(p))
    def test_tool_markers_mutation(self):
        clean, dirty = "# ID\nTools: Gmail.\n", "# ID\nTools: {{EMAIL_TOOL}}, {{DOCS_TOOL}}.\n"
        p = self._w("ID.md", clean)
        self.assertIsNone(check_file(p))
        with open(p, "w") as f: f.write(dirty)
        r = check_file(p); self.assertIsNotNone(r); self.assertEqual(len(r["markers"]), 2)
        with open(p, "w") as f: f.write(clean)
        self.assertIsNone(check_file(p))
    def test_scan_mutation(self):
        spec = os.path.join(self.tmpdir, "specialists")
        d1 = os.path.join(spec, "a"); d2 = os.path.join(spec, "b")
        os.makedirs(d1); os.makedirs(d2)
        for d in [d1, d2]:
            for n, c in [("SOUL.md", "# Clean\n"), ("IDENTITY.md", "# Clean\n")]:
                with open(os.path.join(d, n), "w") as f: f.write(c)
        self.assertEqual(len(scan_directory(self.tmpdir)), 0, "GREEN")
        with open(os.path.join(d1, "SOUL.md"), "w") as f: f.write("{{OWNER_NAME}}\n")
        self.assertEqual(len(scan_directory(self.tmpdir)), 1, "RED")
        with open(os.path.join(d1, "SOUL.md"), "w") as f: f.write("# Clean\n")
        self.assertEqual(len(scan_directory(self.tmpdir)), 0, "GREEN")


if __name__ == "__main__":
    unittest.main()
