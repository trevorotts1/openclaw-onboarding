"""Issue 1 (83 side): a sha256 is 64 lowercase hex and nothing after it, not even a newline.

The pattern is ``^[a-f0-9]{64}$``; ``re.match`` lets ``$`` match before a trailing newline, so ``"<64hex>\\n"``
passed the format check. Each of the five sites uses ``fullmatch`` now. A test per site feeds the digest with
a newline appended and expects the format refusal (not a later hash-mismatch refusal).
"""

from __future__ import annotations

import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_l04_artifact_proof as l04  # noqa: E402
from launcher_core import checks, council, intake, package, route  # noqa: E402
from test_delivery_units import (install_stand_in_validator,  # noqa: E402
                                 with_sales_piece)
from test_launch_plan_law import (lane_deliveries, pieces_for, plan_fixture,  # noqa: E402
                                  plan_intake, stub_council)

NL = "\n"


class ReceiptCheckSites(l04._RunFixture):
    """checks.py: the receipt's artifact sha256 and its approved_plan_hash."""

    def test_a_receipt_artifact_sha256_with_a_trailing_newline_is_refused(self):
        receipt = self.read_receipt()
        art = receipt["units"][0]["artifacts"][0]
        art["sha256"] = art["sha256"] + NL
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any("is not 64 lowercase hex" in f for f in fails), fails)

    def test_an_approved_plan_hash_with_a_trailing_newline_is_refused(self):
        receipt = self.read_receipt()
        receipt["approved_plan_hash"] = receipt["approved_plan_hash"] + NL
        self.write_receipt(receipt)
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any("approved_plan_hash is not a sha256" in f for f in fails), fails)


class PieceSite(l04._RunFixture):
    """package.py: a page piece's artifact sha256."""

    def test_a_piece_artifact_sha256_with_a_trailing_newline_is_refused(self):
        pieces = copy.deepcopy(self.pieces)
        art = next(iter(pieces.values()))["artifacts"][0]
        art["sha256"] = art["sha256"] + NL
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(pieces=pieces)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-PIECE")
        self.assertIn("64 lowercase hex", str(ctx.exception))


class LaneDeliverySites(unittest.TestCase):
    """package.py: a lane delivery's artifact sha256 and its certificate_sha256."""

    def setUp(self):
        install_stand_in_validator(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(plan_intake())
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.pieces = with_sales_piece(pieces_for(self.run_dir, self.graph, self.normalized),
                                       self.run_dir, self.normalized)
        self.plan = plan_fixture()
        self.deliveries = lane_deliveries(self.plan, self.run_dir)

    def assemble(self, deliveries):
        return package.assemble(self.run_dir, self.normalized, self.graph, self.pieces, council=self.advice,
                                launch_plan=self.plan, deliveries=deliveries)

    def test_a_delivery_artifact_sha256_with_a_trailing_newline_is_refused(self):
        deliveries = copy.deepcopy(self.deliveries)
        art = deliveries[self.plan["text_sets"][0]["id"]]["artifacts"][0]
        art["sha256"] = art["sha256"] + NL
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(deliveries)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-RECEIPT-ARTIFACT")
        self.assertIn("64 lowercase hex", str(ctx.exception))

    def test_a_certificate_sha256_with_a_trailing_newline_is_not_sealed(self):
        unit_id = self.plan["text_sets"][0]["id"]
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[unit_id]["lane_validation"]["certificate_sha256"] = "a" * 64 + NL
        rows = {r["unit_id"]: r for r in self.assemble(deliveries)["receipt"]["units"]}
        self.assertNotIn("certificate_sha256", rows[unit_id]["lane_validation"])


if __name__ == "__main__":
    unittest.main()
