#!/usr/bin/env python3
"""The pinned external authorities hold, and Skill 45's five sources are among them (issues 8, 40).

check_authority_pins.py --strict is the check that turns a moved authority into a failure. It used to
exit 1 (four of the seven pins had drifted) and nothing ran it strict; the pins are re-stamped to the
current blobs, the four Skill 45 sources the Image Intelligence guide cites (R4, R7, R8, R9) are
pinned too, and the guide's own table carries the same hashes.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PINS = ROOT / "references" / "external-authorities.json"
GUIDE = ROOT / "references" / "BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md"
SKILL_45 = {
    "R4": "45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md",
    "R7": "45-design-intelligence-library/library/funnel-page-designs/_RULES.md",
    "R8": "45-design-intelligence-library/library/_system/prompt-bands.json",
    "R9": "45-design-intelligence-library/library/_system/MODEL-SPECS.md",
}


class AuthorityPins(unittest.TestCase):
    def test_strict_check_exits_zero(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_authority_pins.py"), "--strict",
                               "--repo-root", str(REPO)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("PIN DRIFT", proc.stdout)
        self.assertNotIn("PIN MISSING", proc.stdout)

    def test_the_four_skill_45_sources_are_pinned(self):
        pinned = {a["path"] for a in json.loads(PINS.read_text(encoding="utf-8"))["authorities"]}
        for ref, path in SKILL_45.items():
            self.assertIn(path, pinned, f"{ref} {path} is not pinned")

    def test_the_guide_table_carries_the_pinned_hashes(self):
        guide = GUIDE.read_text(encoding="utf-8")
        for a in json.loads(PINS.read_text(encoding="utf-8"))["authorities"]:
            if a["path"] in SKILL_45.values():
                row = next(line for line in guide.splitlines() if line.startswith("|") and f"`{a['path']}`" in line)
                self.assertIn(a["blob_sha"], row, f"the guide row for {a['path']} cites a stale hash")
                self.assertRegex(row, r"[0-9a-f]{40}")

    def test_no_skill_45_file_is_written_by_this_skill(self):
        # Skill 45 is only read: no script in this skill opens a file under 45-design-intelligence-library for writing
        pattern = re.compile(r"45-design-intelligence-library[^\n]{0,120}(open\([^)]*[\"']w|write_text|write_bytes)")
        offenders = [p.name for p in (ROOT / "scripts").glob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
