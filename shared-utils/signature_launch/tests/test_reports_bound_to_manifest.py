#!/usr/bin/env python3
"""CON-19: client progress/delivery reports run only on rows generated from the checked package manifest.

Free: fake consumer + stub provider, no network. Run: python3 -m pytest shared-utils/signature_launch/tests/test_reports_bound_to_manifest.py -q
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = ROOT = Path(__file__).resolve().parents[3]


def _skill(name):  # onboarding: 49-signature-funnel; 999: .claude/skills/signature-funnel
    p = ROOT / name
    return p if p.is_dir() else ROOT / ".claude/skills" / name.split("-", 1)[1]


EXP = REPO / "shared-utils/signature_launch/experience"
sys.path.insert(0, str(_skill("83-black-friday-launcher") / "tests"))
from test_lane83_designs import Base  # noqa: E402
sys.path.insert(0, str(_skill("83-black-friday-launcher") / "fixtures"))
import test_only_readback  # noqa: E402
from launcher_core import entitlement  # noqa: E402


def run(script, *args):
    return subprocess.run([sys.executable, str(EXP / script), *map(str, args)], capture_output=True, text=True)


class BoundRows(Base):
    def setUp(self):
        # the fixture's entitlement attestation carries TEST-ONLY references: read them back offline
        test_only_readback.install()
        self.addCleanup(entitlement.set_transport, None)
        super().setUp()
        self.built = self.assemble(self.pieces())
        self.manifest = Path(self.built["manifest_path"])
        self.rows = self.work / "rows.json"

    def emit(self):
        r = run("progress_report.py", "--manifest", self.manifest, "--emit-rows", self.rows)
        self.assertEqual(r.returncode, 0, r.stderr)

    def deliver(self, rows=None):
        return run("delivery_report.py", "--manifest", self.manifest, "--rows-file", rows or self.rows, "--harness", "claude-code")

    def test_generated_rows_are_bound_and_accepted(self):
        self.emit()
        doc = json.loads(self.rows.read_text())
        self.assertEqual(len(doc["rows"]), len(self.graph["nodes"]))
        r = self.deliver()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("COMPLETE", r.stdout)
        self.assertEqual(run("progress_report.py", "--manifest", self.manifest, "--rows-file", self.rows).returncode, 0)

    def test_hand_authored_rows_are_refused(self):
        hand = self.work / "hand.json"
        hand.write_text((EXP / "fixtures/rows.fullfunnel.json").read_text())  # bare list, claims every page is done
        for r in (self.deliver(hand), run("progress_report.py", "--manifest", self.manifest, "--rows-file", hand)):
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("REFUSED", r.stderr)

    def test_rows_with_a_different_manifest_sha_are_refused(self):
        self.emit()
        doc = json.loads(self.rows.read_text())
        doc["manifest_sha256"] = "0" * 64
        self.rows.write_text(json.dumps(doc))
        r = self.deliver()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not bound", r.stderr)

    def test_edited_rows_with_the_right_sha_are_refused(self):
        self.emit()
        doc = json.loads(self.rows.read_text())
        doc["rows"][0]["wireframe"]["mobile"] = not doc["rows"][0]["wireframe"]["mobile"]
        self.rows.write_text(json.dumps(doc))
        self.assertNotEqual(self.deliver().returncode, 0)

    def test_no_rows_from_a_package_that_fails_its_check(self):
        m = json.loads(self.manifest.read_text())
        m["pieces"][0]["artifacts"] = []  # a page with no designs
        self.manifest.write_text(json.dumps(m))
        r = run("progress_report.py", "--manifest", self.manifest, "--emit-rows", self.rows)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.rows.exists())


ADAPTER_READMES = [
    "83-black-friday-launcher/adapters/claude-nine/README.md",
    "83-black-friday-launcher/adapters/openclaw/README.md",
    "49-signature-funnel/adapters/claude-code/README.md",
    "49-signature-funnel/adapters/claude-nine/README.md",
    "49-signature-funnel/adapters/openclaw/README.md",
    "71-blackceo-signature-page/adapters/openclaw/README.md",
]


class AdapterDocs(unittest.TestCase):
    def test_adapter_docs_pass_the_manifest(self):
        for rel in ADAPTER_READMES:
            first, _, rest = rel.partition("/")
            cmds = [c for c in re.findall(r"`([^`]+)`", (_skill(first) / rest).read_text())
                    if "progress_report.py" in c or "delivery_report.py" in c]
            self.assertTrue(cmds, rel)
            for c in cmds:
                self.assertIn("--manifest", c, f"{rel}: {c}")
            self.assertTrue(any("--emit-rows" in c for c in cmds), f"{rel}: no --emit-rows command")


if __name__ == "__main__":
    unittest.main()
