"""read_skill must be in all four tool allow-list files that are kept in sync, and nowhere
missing from the CEO allow blocks. QC runs this (python3 tests/unit/test_frg_allowlist_sync.py)."""
import os, re, sys, unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = {
    "apply-fleet-standards": "scripts/apply-fleet-standards.sh",
    "apply-routing-fix": "scripts/apply-routing-fix.sh",
    "lib-ceo-tool-gate": "hooks/lib-ceo-tool-gate.sh",
    "build-workforce": "23-ai-workforce-blueprint/scripts/build-workforce.py",
}

def allow_tokens(src, name_re):
    m = re.search(name_re + r"\s*=\s*[\[\(](.*?)^[ \t]*[\]\)]", src, re.S | re.M)
    assert m, "allow block not found: " + name_re
    body = re.sub(r"#[^\n]*", "", m.group(1))
    return {a or b for a, b in re.findall(r'"([^"]*)"|\'([^\']*)\'', body)}

class AllowlistSync(unittest.TestCase):
    def test_read_skill_in_every_ceo_allow_block(self):
        pats = {
            "apply-fleet-standards": r"CEO_TOOL_ALLOW",
            "apply-routing-fix": r"CEO_TOOL_ALLOW",
            "lib-ceo-tool-gate": r"CEO_GATE_ALLOW_TOOLS",
            "build-workforce": r"CEO_TOOL_ALLOW",
        }
        for key, rel in FILES.items():
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
            toks = allow_tokens(src, pats[key])
            self.assertIn("read_skill", toks, rel)
            self.assertIn("read", toks, rel)

    def test_four_ceo_allow_sets_identical(self):
        sets = {}
        for key, rel in FILES.items():
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
            name = r"CEO_GATE_ALLOW_TOOLS" if key == "lib-ceo-tool-gate" else r"CEO_TOOL_ALLOW"
            sets[key] = allow_tokens(src, name)
        ref = sets["lib-ceo-tool-gate"]
        for key, s in sets.items():
            self.assertEqual(s, ref, key + " drifted from hooks/lib-ceo-tool-gate.sh")

    def test_department_generation_allow_has_read_skill(self):
        src = open(os.path.join(REPO, FILES["build-workforce"]), encoding="utf-8").read()
        self.assertIn("read_skill", allow_tokens(src, r"GENERATION_TOOLS_ALLOW"))

    def test_gate_test_expectation_includes_read_skill(self):
        src = open(os.path.join(REPO, "scripts/test-ceo-tool-gate.sh"), encoding="utf-8").read()
        m = re.search(r'^EXPECT_ALLOW="([^"]*)"', src, re.M)
        self.assertTrue(m)
        self.assertIn("read_skill", m.group(1).split())

if __name__ == "__main__":
    unittest.main()
