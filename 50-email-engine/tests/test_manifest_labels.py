#!/usr/bin/env python3
"""Doc-lockstep test: the EMAIL-MANIFEST P1 label says what the prover does.

Issue 95: the P1 label demanded `asked_all_at_once:true` of every brief, but a
launch brief (the adapter path, intake_mode signature_launch) must NEVER carry
that attestation (it would be a fabricated claim). The prover has always been
right; the label was the lie. This test keeps the label and the prover agreeing:

  * the label names both brief paths;
  * it never asks for `asked_all_at_once:true` outside the interactive path;
  * the prover really does accept a launch brief with no attestation and really
    does refuse an interactive brief without it.

Hermetic: no network, no provider call; writes only to a temp dir.
Run: python3 -m pytest 50-email-engine/tests/test_manifest_labels.py -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TOOLS = SKILL / "tools"
PROVER = TOOLS / "prove-email.py"
sys.path.insert(0, str(TOOLS))

import launch_intake_adapter as adapter  # noqa: E402


def _p1_label() -> str:
    manifest = json.loads((SKILL / "EMAIL-MANIFEST.json").read_text(encoding="utf-8"))
    phase = next(p for p in manifest["phases"] if p["id"] == "P1-SELECT")
    return phase["preflight"]["label"]


def _prove(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PROVER), str(path), *args],
                          capture_output=True, text=True)


class ManifestP1LabelTests(unittest.TestCase):
    def test_label_names_both_brief_paths(self):
        label = _p1_label()
        self.assertIn("asked_all_at_once:true (interactive briefs)", label)
        self.assertIn("launch brief (adapter path, no attestation", label)

    def test_label_never_demands_the_flag_outside_the_interactive_path(self):
        label = _p1_label()
        for match in re.finditer(r"asked_all_at_once:true", label):
            tail = label[match.end():match.end() + len(" (interactive briefs)")]
            self.assertEqual(tail, " (interactive briefs)", label[match.start() - 40:match.end() + 40])

    def test_prover_accepts_a_launch_brief_that_carries_no_attestation(self):
        fx = adapter.build_fixtures()
        brief = adapter.adapt(fx["session"], fx["launch"], fx["approval"],
                              fx["brand_facts"], fx["landing_facts"],
                              worker_identity_ref=fx["worker_identity_ref"])
        self.assertNotIn("asked_all_at_once", brief)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            result = _prove(path, "--kind", "intake")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_prover_refuses_an_interactive_brief_without_the_attestation(self):
        golden = SKILL / "examples" / "golden-landing-10" / "brief.json"
        brief = json.loads(golden.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            self.assertEqual(_prove(path, "--kind", "intake").returncode, 0)  # control
            del brief["asked_all_at_once"]
            path.write_text(json.dumps(brief), encoding="utf-8")
            result = _prove(path, "--kind", "intake")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("AF-EMAIL-INTAKE-SPLIT", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
