#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_golden_repairs.py — FC-51: the three causes that kept verify.sh red on a fresh HOME.

1. the committed golden copy ledger clears prove_sf_copy (derived pages carry the section 7 CTA) and is
   byte-for-byte what build_golden.py emits, so the fixture cannot drift from its own builder;
2. the checkout wrapper never lists Skill 71's .attempts staging copies as artifacts;
3. verify.sh names a platform for its self-tests, so they pass under `env -i` with an empty HOME.

Run: python3 49-signature-funnel/scripts/test_verify_golden_repairs.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
GOLDEN = SKILL / "examples" / "golden-daybreak"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(GOLDEN))


class GoldenCopyLedger(unittest.TestCase):
    def test_committed_golden_copy_clears_the_copy_prover(self):
        proc = subprocess.run([sys.executable, str(HERE / "prove_sf_copy.py"), "--ledger",
                               str(GOLDEN / "copy_ledger.json")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_every_derived_page_section_7_carries_a_cta(self):
        ledger = json.loads((GOLDEN / "copy_ledger.json").read_text(encoding="utf-8"))
        derived = [p for p in ledger["pages"] if p["page_type"] in ("upsell", "downsell", "upsell-2", "downsell-2")]
        self.assertEqual(len(derived), 4)
        for page in derived:
            sec7 = next(s for s in page["sections"] if s["section"] == 7)
            self.assertTrue(str(sec7.get("cta", "")).strip(), page["page_type"])

    def test_committed_golden_copy_is_what_build_golden_emits(self):
        import build_golden
        committed = json.loads((GOLDEN / "copy_ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(build_golden.build_copy_ledger(), committed)


class CheckoutArtifactsSkipStaging(unittest.TestCase):
    def test_attempt_staging_copies_are_not_artifacts(self):
        import checkout_wrapper
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            for stage in checkout_wrapper.STAGES:
                (run / stage).mkdir()
                (run / f"production-request-{stage}.json").write_text("{}", encoding="utf-8")
            final = run / checkout_wrapper.STAGES[0] / "section-01.png"
            staged = run / checkout_wrapper.STAGES[0] / ".attempts" / "slot-1" / "section-01.png"
            staged.parent.mkdir(parents=True)
            final.write_bytes(b"png")
            staged.write_bytes(b"png")
            got = {Path(a["path"]).relative_to(run).as_posix() for a in checkout_wrapper.artifacts(run)}
            self.assertIn(f"{checkout_wrapper.STAGES[0]}/section-01.png", got)
            self.assertFalse([n for n in got if ".attempts" in n], got)


class VerifyShNamesAPlatform(unittest.TestCase):
    def test_orchestrator_self_test_passes_under_verify_sh_environment(self):
        # run verify.sh's own preamble (everything before `fails=0`), then the exact self-test it runs
        preamble = Path(SKILL / "verify.sh").read_text(encoding="utf-8").split("\nfails=0\n")[0]
        with tempfile.TemporaryDirectory() as home:
            env = {"HOME": home, "PATH": os.environ["PATH"], "TMPDIR": os.environ.get("TMPDIR", home)}
            proc = subprocess.run(
                ["bash", "-c", preamble + '\n"$PY" "$1" --self-test', "verify-preamble",
                 str(SKILL / "run_signature_funnel.py")],
                capture_output=True, text=True, env={**env, "PYTHON": sys.executable}, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
