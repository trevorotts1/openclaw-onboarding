#!/usr/bin/env python3
"""PBB-917 / T-54 — review C3 step 7: the publishing approval gate.

Pins the onboarding half of C3:

  • `monthly_manifest.py check` refuses unless the manifest is approved and
    every named placement is APPROVED at its current terms/revision;
  • an amended (INVALIDATED) placement is refused while its sibling still
    passes — invalidation is targeted, never campaign-wide;
  • `--expected-revision` and `--advance-from` refuse a stale or non-advancing
    revision;
  • `run-publishing-cycle.sh --check-approval-only --approval-manifest M`
    exits 0 on a pass and 7 on a refusal BEFORE anything is staged (no workdir
    is created).

Run: python3 -I shared-utils/manifest/tests/test_check_cli.py
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
MODULE_DIR = HERE.parents[1]
REPO_ROOT = HERE.parents[3]
CONTRACTS_TOOLS = REPO_ROOT / "38-conversational-ai-system" / "tools"

sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(CONTRACTS_TOOLS))

import monthly_manifest as mm  # noqa: E402

FIXTURES = MODULE_DIR / "fixtures"
AT = "2026-10-20T18:00:00Z"
REV = "rev-3"
PREV = "rev-2"
SCRIPT = REPO_ROOT / "35-social-media-planner" / "scripts" / "run-publishing-cycle.sh"


def fixture():
    with open(FIXTURES / "manifest-two-placement.json") as handle:
        return json.load(handle)


def approved():
    """The shipped fixture IS the approved two-placement manifest (rev-3)."""
    doc = fixture()
    assert mm.check_manifest(doc) == [], mm.check_manifest(doc)
    return doc


def draft():
    doc = copy.deepcopy(fixture())
    doc["status"] = "DRAFT"
    doc["approved_by"] = None
    doc["approved_at"] = None
    for placement in doc["placements"]:
        placement["approval_status"] = "DRAFT"
    return doc


class CheckManifestTests(unittest.TestCase):
    def test_approved_manifest_passes_every_placement(self):
        self.assertEqual(mm.check_manifest(approved()), [])

    def test_draft_manifest_is_refused(self):
        errs = mm.check_manifest(draft())
        self.assertTrue(any("not an approved manifest" in err for err in errs), errs)
        self.assertTrue(any("requires APPROVED" in err for err in errs), errs)

    def test_amended_placement_is_refused_and_sibling_still_passes(self):
        doc = approved()
        first = [p["placement_id"] for p in doc["placements"]][0]
        second = [p["placement_id"] for p in doc["placements"]][1]
        amended, errs = mm.amend(
            doc, first, {"keyword": "NEWWORD"}, "owner changed the keyword", AT, REV
        )
        self.assertEqual(errs, [])
        self.assertTrue(
            any(first in err and "INVALIDATED" in err for err in mm.check_manifest(amended))
        )
        self.assertEqual(mm.check_manifest(amended, placements=[second]), [])

    def test_expected_revision_and_advance_from(self):
        doc = approved()
        self.assertEqual(mm.check_manifest(doc, expected_revision=REV), [])
        self.assertTrue(mm.check_manifest(doc, expected_revision="rev-2"))
        self.assertTrue(mm.check_manifest(doc, advance_from=REV))
        self.assertEqual(mm.check_manifest(doc, advance_from=PREV), [])

    def test_unknown_placement_is_named(self):
        errs = mm.check_manifest(approved(), placements=["not-a-placement"])
        self.assertTrue(any("not-a-placement" in err for err in errs), errs)


class CheckCliTests(unittest.TestCase):
    def _write(self, doc):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(doc, handle)
        handle.close()
        return handle.name

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "-I", str(MODULE_DIR / "monthly_manifest.py"), "check", *args],
            capture_output=True,
            text=True,
        )

    def test_cli_exit_codes(self):
        good = self._run("--manifest", self._write(approved()))
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertEqual(json.loads(good.stdout)["ok"], True)
        bad = self._run("--manifest", self._write(draft()))
        self.assertEqual(bad.returncode, 3, bad.stdout + bad.stderr)
        self.assertEqual(json.loads(bad.stdout)["ok"], False)
        missing = self._run("--manifest", str(FIXTURES / "absent.json"))
        self.assertEqual(missing.returncode, 2)

    def test_cli_placement_narrowing(self):
        doc = approved()
        first = doc["placements"][0]["placement_id"]
        amended, errs = mm.amend(doc, first, {"keyword": "NEWWORD"}, "changed", AT, REV)
        self.assertEqual(errs, [])
        path = self._write(amended)
        refused = self._run("--manifest", path, "--placement", first)
        self.assertEqual(refused.returncode, 3, refused.stdout + refused.stderr)
        sibling = [p["placement_id"] for p in amended["placements"] if p["placement_id"] != first][0]
        passed = self._run("--manifest", path, "--placement", sibling)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)


class PublishingGateTests(unittest.TestCase):
    def _gate(self, doc, *extra):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(doc, handle)
        handle.close()
        with tempfile.TemporaryDirectory() as workdir:
            result = subprocess.run(
                [
                    "bash", str(SCRIPT),
                    "--check-approval-only",
                    "--approval-manifest", handle.name,
                    *extra,
                ],
                capture_output=True,
                text=True,
                cwd=workdir,
            )
            self.assertEqual(
                list(Path(workdir).iterdir()), [],
                "a refused/staged cycle must create nothing in the workdir",
            )
        return result

    def test_gate_passes_an_approved_manifest(self):
        result = self._gate(approved())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("approval gate passed", result.stdout)

    def test_gate_refuses_a_draft_manifest_with_exit_7(self):
        result = self._gate(draft())
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertIn("REFUSED", result.stderr)

    def test_gate_requires_a_manifest(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--check-approval-only"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
