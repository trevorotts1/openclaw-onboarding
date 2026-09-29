#!/usr/bin/env python3
"""U054 + N29: real TOOLS/USER kept, symlinks become real copies, AGENTS.md retired (U053). Hermetic."""
import os, pathlib, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from create_role_workspaces import augment_all_existing_role_folders

class TestRoleWorkspaceSymlinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        b = pathlib.Path(self.tmp.name)
        self.ws = b / "ws"; self.ws.mkdir()
        (self.ws/"TOOLS.md").write_text("ws tools\n", encoding="utf-8")
        (self.ws/"USER.md").write_text("ws user\n", encoding="utf-8")
        self.dept = b / "dept"; self.dept.mkdir()
        r = self.dept / "role"; r.mkdir()
        self.ot = "stale tools\n"; self.ou = "stale user\n"; self.oa = "stale agents\n"
        (r/"TOOLS.md").write_text(self.ot, encoding="utf-8")
        (r/"USER.md").write_text(self.ou, encoding="utf-8")
        (r/"AGENTS.md").write_text(self.oa, encoding="utf-8")
        s = self.dept / "sops"; s.mkdir()
        self.oas = "stale sops agents\n"; self.ots = "stale sops tools\n"; self.ous = "stale sops user\n"
        (s/"AGENTS.md").write_text(self.oas, encoding="utf-8")
        (s/"TOOLS.md").write_text(self.ots, encoding="utf-8")
        (s/"USER.md").write_text(self.ous, encoding="utf-8")
    def tearDown(self): self.tmp.cleanup()
    def _bak(self, d, stem):
        c = list(d.glob(f"{stem}.bak-unify-*")); return c[0] if c else None
    def test_conversion(self):
        # N29: real TOOLS.md/USER.md are KEPT byte-identical (the updater refreshes
        # them); AGENTS.md is still retired with a backup (U053).
        results = augment_all_existing_role_folders(str(self.dept), str(self.ws))
        rr = [r for r in results if r.get("role")=="role"][0]
        self.assertEqual(rr.get("symlinked",[]), [])
        self.assertEqual(rr.get("converted",[]), [])
        rd = self.dept / "role"
        for f, orig in (("TOOLS.md",self.ot),("USER.md",self.ou)):
            self.assertFalse((rd/f).is_symlink(), f"{f} must stay a real file")
            self.assertEqual((rd/f).read_text(encoding="utf-8"), orig)
            self.assertIsNone(self._bak(rd, f), f"no backup churn for kept {f}")
        self.assertFalse((rd/"AGENTS.md").exists(), "AGENTS.md should be deleted")
        ab = self._bak(rd, "AGENTS.md")
        self.assertIsNotNone(ab, "AGENTS.md backup")
        self.assertEqual(ab.read_text(encoding="utf-8"), self.oa)
    def test_symlinks_become_real_copies(self):
        rd = self.dept / "role"
        for f in ("TOOLS.md","USER.md"):
            (rd/f).unlink(); (rd/f).symlink_to(self.ws/f)
        results = augment_all_existing_role_folders(str(self.dept), str(self.ws))
        rr = [r for r in results if r.get("role")=="role"][0]
        self.assertEqual(sorted(rr.get("converted",[])), ["TOOLS.md","USER.md"])
        for f in ("TOOLS.md","USER.md"):
            self.assertFalse((rd/f).is_symlink(), f"{f} should be a real copy")
            self.assertEqual((rd/f).read_bytes(), (self.ws/f).read_bytes())
    def test_sops_cleaned(self):
        augment_all_existing_role_folders(str(self.dept), str(self.ws))
        sd = self.dept / "sops"
        for f, orig in (("TOOLS.md",self.ots),("USER.md",self.ous)):
            self.assertFalse((sd/f).is_symlink(), f"sops/{f} must stay a real file")
            self.assertEqual((sd/f).read_text(encoding="utf-8"), orig)
        self.assertFalse((sd/"AGENTS.md").exists())
        ab = self._bak(sd, "AGENTS.md")
        self.assertIsNotNone(ab, "sops AGENTS.md backup")
        self.assertEqual(ab.read_text(encoding="utf-8"), self.oas)
    def test_converted_count(self):
        results = augment_all_existing_role_folders(str(self.dept), str(self.ws))
        all_c = [i for r in results for i in r.get("converted",[])]
        self.assertEqual(len(all_c), 0)
    def test_dry_run(self):
        rd = self.dept/"role"; sd = self.dept/"sops"
        def snap(d):
            s = set()
            for p in d.iterdir():
                s.add((p.name, p.is_symlink(), p.read_text(encoding="utf-8") if p.is_file() else None))
            return s
        sb = {rd:snap(rd), sd:snap(sd)}
        augment_all_existing_role_folders(str(self.dept), str(self.ws), dry_run=True)
        for d in (rd,sd):
            self.assertEqual(sb[d], snap(d), f"{d.name}: dry-run must not mutate")

if __name__ == "__main__":
    unittest.main()
