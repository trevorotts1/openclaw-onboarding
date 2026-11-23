"""SWB-033: a page ANOTHER skill installed (a GoHighLevel DRAFT page) is sealed only from real receipts.

Before the fix ``LANE_CONTRACTS['page']`` was empty, so a funnel whose pages were installed by the page
skills through Skill 06's rail could never be packaged: every such page was refused "has no producer yet",
and ``assemble`` refused a route node with no launcher piece file. Now a page unit with no launcher piece
is sealed when its delivery is ``skill06.page-draft-install.v1`` AND its facts re-read from its own sealed
files hold: the installer's receipt names the page, the location and this exact draft; one independent
read-back, written by a different unit, shows the live record read by GET (same ids, a draft top version
with that version id and content sha256, no published version, not deleted, preview 200). Anything
unverifiable, forged, mismatched or published is refused, and the other lanes keep their own contracts.

The contract spelling is a literal here on purpose.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checks, council, intake, package, route  # noqa: E402
from launcher_core.check_rules import delivery_units as du  # noqa: E402
from test_delivery_units import install_stand_in_validator, with_sales_piece  # noqa: E402
from test_launch_plan_law import lane_deliveries, pieces_for, plan_fixture, plan_intake, stub_council  # noqa: E402

PAGE_CONTRACT = "skill06.page-draft-install.v1"
LANE_CODE = "AF-LAUNCH-PKG-RECEIPT-LANE"
UNIT, SLOT = "page_upsell_1", "upsell_1"
VERSION = "8fe0e136-2e39-44e8-97d5-32274845a5cf"
CONTENT = "32c08404f8816ca7bec690e32e457f5ef3177435b7757a9e4b63604f7ed02244"


def _write(run_dir: Path, rel: str, doc) -> dict:
    target = run_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raw = target.read_bytes()
    return {"path": rel, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def install_receipt(location: str, **over) -> dict:
    doc = {"unit": "SWB-029", "role": "upsell_1", "location_id": location, "funnel_id": "F1",
           "step_id": "S1", "page_id": "P1", "readback": {"versionId": VERSION, "blob_sha256": CONTENT}}
    doc.update(over)
    return doc


def readback(location: str, unit: str = UNIT, **page_over) -> dict:
    page = {"page_id": "P1", "http_status": 200, "funnelId": "F1", "stepId": "S1", "deleted": False,
            "published_version_present": False, "preview_http_status": 200,
            "top_version": {"pageType": "draft", "versionId": VERSION, "blob_sha256": CONTENT}}
    page.update(page_over)
    return {"kind": "rest_readback", "unit": "SWB-033", "read_at": "2026-11-23T23:00:00Z",
            "method": "read-only HTTP GET only", "location_id": location, "pages": {unit: page}}


def page_delivery(run_dir: Path, plan_sha: str, location: str, *, receipt=None, back=None, **facts) -> dict:
    arts = [{**_write(run_dir, "installs/W30/RECEIPT-upsell_1.json", receipt or install_receipt(location)),
             "role": "install_receipt"},
            {**_write(run_dir, "readbacks/readback-SWB-033.json", back or readback(location)),
             "role": "independent_readback"}]
    page_install = {"page_id": "P1", "funnel_id": "F1", "step_id": "S1", "location_id": location,
                    "draft_version_id": VERSION, "content_sha256": CONTENT, "preview_http_status": 200,
                    "published": False, "installed_by": "SWB-029", "read_by": "SWB-033"}
    page_install.update(facts)
    return {"state": "complete", "artifacts": arts,
            "lane_validation": {"lane": "Skill 80 install via Skill 06 rail, read back by SWB-033",
                                "contract": PAGE_CONTRACT, "state": "passed"},
            "request": {"plan_sha256": plan_sha, "request_id": "SWB-029", "input_hash": CONTENT},
            "page_install": page_install}


class ExternalPageInstallTests(unittest.TestCase):
    def setUp(self):
        install_stand_in_validator(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(plan_intake())
        self.location = self.normalized["location_id"]
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.assertIn(SLOT, [n["role"] for n in self.graph["nodes"]])
        pieces = with_sales_piece(pieces_for(self.run_dir, self.graph, self.normalized),
                                  self.run_dir, self.normalized)
        self.pieces = {slot: piece for slot, piece in pieces.items() if slot != SLOT}  # installed elsewhere
        self.plan = plan_fixture()
        self.deliveries = lane_deliveries(self.plan, self.run_dir)
        self.plan_sha = self.deliveries[UNIT]["request"]["plan_sha256"]

    def with_page(self, **kwargs) -> dict:
        shutil.rmtree(self.run_dir / "lanes" / UNIT, ignore_errors=True)  # a refused case's staged copy
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[UNIT] = page_delivery(self.run_dir, self.plan_sha, self.location, **kwargs)
        return deliveries

    def assemble(self, deliveries):
        return package.assemble(self.run_dir, self.normalized, self.graph, self.pieces, council=self.advice,
                                launch_plan=self.plan, deliveries=deliveries)

    def refused(self, deliveries, code=LANE_CODE) -> str:
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(deliveries)
        self.assertEqual(ctx.exception.code, code, ctx.exception)
        self.assertFalse((self.run_dir / "receipt.json").exists())
        return str(ctx.exception)

    # ---- acceptance -------------------------------------------------------------------------------
    def test_a_verified_draft_page_another_skill_installed_is_sealed_and_check_passes(self):
        out = self.assemble(self.with_page())
        rows = {r["unit_id"]: r for r in out["receipt"]["units"]}
        row = rows[UNIT]
        self.assertEqual(row["lane_validation"]["contract"], PAGE_CONTRACT)
        self.assertEqual(row["delivery"], "declared")
        self.assertEqual(row["page_slot"], SLOT)
        self.assertEqual(row["page_install"]["draft_version_id"], VERSION)
        self.assertFalse(row["page_install"]["published"])
        self.assertEqual(row["status"], "draft_delivered")
        self.assertNotIn(SLOT, [p.get("role_instance") or p.get("role") for p in out["manifest"]["pieces"]])
        self.assertEqual(checks.check_package(Path(out["manifest_path"]), self.run_dir), [])

    def test_the_page_contract_is_in_the_allow_list_for_pages_only(self):
        self.assertEqual(du.LANE_CONTRACTS["page"], (PAGE_CONTRACT,))
        for unit_type in ("email", "text", "automation", "conversation_ai"):
            with self.subTest(unit_type):
                self.assertEqual(len(du.lane_contract_violations("u", unit_type, {"contract": PAGE_CONTRACT})), 1)

    # ---- refusals: nothing unverifiable seals a page ----------------------------------------------
    def test_a_missing_route_page_with_no_page_install_delivery_is_still_refused(self):
        message = self.refused(self.deliveries, code="AF-LAUNCH-PKG-MISSING")
        self.assertIn(SLOT, message)

    def test_a_self_declared_page_contract_is_refused(self):
        deliveries = self.with_page()
        deliveries[UNIT]["lane_validation"]["contract"] = "swb032.page-draft-readback.v1"
        self.refused(deliveries, code="AF-LAUNCH-PKG-MISSING")

    def test_forged_or_mismatched_page_facts_are_refused(self):
        cases = {
            "published claim": dict(published=True),
            "published as a string": dict(published="false"),
            "wrong draft version": dict(draft_version_id="0f86c6c2-409e-404d-8548-e134118c9a62"),
            "wrong content hash": dict(content_sha256="a" * 64),
            "malformed content hash": dict(content_sha256="A" * 64),
            "wrong page id": dict(page_id="P2"),
            "wrong step id": dict(step_id="S2"),
            "wrong funnel id": dict(funnel_id="F2"),
            "another location": dict(location_id="loc-other"),
            "preview not 200": dict(preview_http_status=404),
            "installer reads itself": dict(read_by="SWB-029"),
            "no installer": dict(installed_by=""),
        }
        for name, facts in cases.items():
            with self.subTest(name):
                self.assertIn(UNIT, self.refused(self.with_page(**facts)))

    def test_a_read_back_that_does_not_show_an_unpublished_draft_is_refused(self):
        loc = self.normalized["location_id"]
        cases = {
            "published version present": readback(loc, published_version_present=True),
            "top version is published": readback(loc, top_version={"pageType": "published",
                                                                    "versionId": VERSION, "blob_sha256": CONTENT}),
            "another draft": readback(loc, top_version={"pageType": "draft", "versionId": "v-other",
                                                        "blob_sha256": CONTENT}),
            "other bytes": readback(loc, top_version={"pageType": "draft", "versionId": VERSION,
                                                      "blob_sha256": "b" * 64}),
            "deleted": readback(loc, deleted=True),
            "preview 404": readback(loc, preview_http_status=404),
            "page read failed": readback(loc, http_status=401),
            "another unit's record": readback(loc, unit="page_downsell_1"),
            "not a rest read-back": {**readback(loc), "kind": "notes"},
            "not read by GET": {**readback(loc), "method": "PUT autosave"},
            "read by someone else": {**readback(loc), "unit": "SWB-999"},
        }
        for name, back in cases.items():
            with self.subTest(name):
                self.assertIn(UNIT, self.refused(self.with_page(back=back)))

    def test_an_install_receipt_that_does_not_name_this_draft_is_refused(self):
        loc = self.normalized["location_id"]
        cases = {
            "another page": install_receipt(loc, page_id="P9"),
            "another installer": install_receipt(loc, unit="SWB-000"),
            "another draft": install_receipt(loc, readback={"versionId": "v-old", "blob_sha256": "c" * 64}),
            "written by the reader": install_receipt(loc, unit="SWB-033"),
            "records a publish": install_receipt(loc, published=True),
        }
        for name, receipt in cases.items():
            with self.subTest(name):
                self.assertIn(UNIT, self.refused(self.with_page(receipt=receipt)))

    def test_missing_proof_files_are_refused(self):
        for role in ("install_receipt", "independent_readback"):
            with self.subTest(role):
                deliveries = self.with_page()
                deliveries[UNIT]["artifacts"] = [a for a in deliveries[UNIT]["artifacts"] if a["role"] != role]
                self.assertIn(role, self.refused(deliveries))
        deliveries = self.with_page()
        del deliveries[UNIT]["page_install"]
        self.assertIn("page_install", self.refused(deliveries))

    def test_bytes_changed_after_the_receipt_was_recorded_are_refused(self):
        deliveries = self.with_page()
        (self.run_dir / "readbacks/readback-SWB-033.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(deliveries)
        self.assertIn(ctx.exception.code, ("AF-LAUNCH-PKG-HASH", "AF-LAUNCH-PKG-ARTIFACT-SIZE"))

    # ---- check re-judges the sealed row: a row edited after sealing fails ------------------------
    def test_check_refuses_a_sealed_page_row_edited_after_assembly(self):
        out = self.assemble(self.with_page())
        receipt_path = self.run_dir / "receipt.json"
        for edit in ({"published": True}, {"draft_version_id": "v-forged"}, {"read_by": "SWB-029"}):
            with self.subTest(edit=edit):
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                for row in receipt["units"]:
                    if row["unit_id"] == UNIT:
                        row["page_install"].update(edit)
                receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                fails = checks.check_package(Path(out["manifest_path"]), self.run_dir)
                self.assertTrue(any(f.startswith(LANE_CODE) and UNIT in f for f in fails), fails)

    def test_check_does_not_count_a_route_slot_from_a_row_under_another_contract(self):
        out = self.assemble(self.with_page())
        receipt_path = self.run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for row in receipt["units"]:
            if row["unit_id"] == UNIT:
                row["lane_validation"]["contract"] = "x"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        fails = checks.check_package(Path(out["manifest_path"]), self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-MISSING-ROLE") and SLOT in f for f in fails), fails)
        self.assertTrue(any(f.startswith(LANE_CODE) and UNIT in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main(verbosity=2)
