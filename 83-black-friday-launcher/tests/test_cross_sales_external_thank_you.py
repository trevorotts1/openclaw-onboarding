"""SWB-095: an external-install package has no launcher piece, so its thank-you page is the sealed page row.

The cross-sales rule needs a thank_you surface. A launcher piece with role thank_you is one; so is a sealed page
row another skill delivered under the page contract for the thank_you slot (an external-install package can carry
no piece at all). Anything else still has nothing to surface the relationships on.

Literals (codes, contract id) are spelled out on purpose.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checks  # noqa: E402

CODE = "AF-LAUNCH-CROSS-SALES"
PAGE_CONTRACT = "skill06.page-draft-install.v1"


def _row(slot="thank_you", unit="page_thank_you", contract=PAGE_CONTRACT, delivery="declared", unit_type="page"):
    return {"unit_id": unit, "unit_type": unit_type, "delivery": delivery, "page_slot": slot,
            "lane_validation": {"contract": contract, "state": "passed"}}


def _manifest(pieces=None, with_plan=True):
    manifest = {"cross_sales": {"relationships": [], "route_node": False, "surface": "thank_you",
                                "teaching": {"state": "pending"}},
                "pieces": pieces or []}
    if with_plan:
        manifest["launch_plan"] = {"plan": {"path": "launch-plan.json"}}
    return manifest


def _cross_sales(manifest, rows=None):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        if rows is not None:
            (root / "receipt.json").write_text(json.dumps({"units": rows}), encoding="utf-8")
        found = checks._decided_requirement_violations(manifest, root, SKILL_ROOT)
    return [f for f in found if f.startswith(CODE) and "thank_you piece" in f]


class ThankYouSurfaceTests(unittest.TestCase):
    def test_a_launcher_thank_you_piece_still_surfaces(self):
        self.assertEqual(_cross_sales(_manifest(pieces=[{"role": "thank_you"}]), rows=[]), [])

    def test_a_sealed_external_thank_you_page_row_surfaces(self):
        self.assertEqual(_cross_sales(_manifest(), rows=[_row()]), [])

    def test_no_piece_and_no_row_is_refused(self):
        self.assertEqual(len(_cross_sales(_manifest(), rows=[])), 1)

    def test_no_receipt_is_refused(self):
        self.assertEqual(len(_cross_sales(_manifest(), rows=None)), 1)

    def test_a_row_for_another_slot_does_not_count(self):
        self.assertEqual(len(_cross_sales(_manifest(), rows=[_row(slot="checkout", unit="page_checkout")])), 1)

    def test_a_row_under_another_contract_does_not_count(self):
        self.assertEqual(len(_cross_sales(_manifest(), rows=[_row(contract="skill50.email-delivery.v1")])), 1)

    def test_a_row_that_is_not_a_declared_page_does_not_count(self):
        self.assertEqual(len(_cross_sales(_manifest(), rows=[_row(delivery="piece")])), 1)
        self.assertEqual(len(_cross_sales(_manifest(), rows=[_row(unit_type="email")])), 1)

    def test_a_package_with_no_sealed_plan_cannot_claim_an_external_page(self):
        self.assertEqual(len(_cross_sales(_manifest(with_plan=False), rows=[_row()])), 1)

    def test_the_other_cross_sales_rules_are_untouched(self):
        manifest = _manifest(pieces=[{"role": "thank_you"}])
        manifest["cross_sales"]["route_node"] = True
        manifest["cross_sales"]["teaching"] = {"state": "known"}
        with tempfile.TemporaryDirectory() as td:
            found = checks._decided_requirement_violations(manifest, Path(td), SKILL_ROOT)
        text = " | ".join(found)
        self.assertIn("cross-sales must never be a route node", text)
        self.assertIn("teaching source is not in hand", text)


if __name__ == "__main__":
    unittest.main()
