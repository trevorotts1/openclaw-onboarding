"""SWB-052: a package whose pages OTHER skills installed binds to an ``external-install`` dispatch manifest.

Before the fix a live package refused AF-LAUNCH-PKG-DISPATCH-MISSING whenever its pages had been built and
installed as GoHighLevel DRAFTS by the page skills through Skill 06's rail, because the only dispatch
evidence Skill 83 knew was its own dispatch run, and a real dispatch would redraw the installed pages.

Now ``dispatch/dispatch-manifest.json`` may declare ``kind: external-install``: it lists each PAGE unit with
its installer, its live draft version, the read-back content hash and the sha256 of its install receipt.
assemble accepts it only when the launch record beside it passes Skill 49's check and recomputes to the
intake's approval hash, every route page is filled by a listed unit, no launcher piece rides beside it, and
every listed unit's delivery passes the page lane in full and is the very receipt and draft it lists. It
never stands in for emails, texts or automations: a manifest that lists one is refused, and those units
still need their own lane deliveries.

The second half covers the restated install receipt (``skill83.page-install-restatement/v1``): an installer
receipt that nests the page under ``page`` and names no location is never edited; a different unit writes a
new receipt naming every fact plus the original by sha256, and the page lane believes it only through that
sealed original and the GET read-back's own ``locationId``.

Literals (kind, schema, codes) are spelled out on purpose.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import substrate  # noqa: E402
from launcher_core import checks, council, image_plan, intake, launch_bridge, package, route  # noqa: E402
from launcher_core import launch_plan as lp  # noqa: E402
from launcher_core.check_rules import delivery_units as du  # noqa: E402
from test_delivery_units import install_stand_in_validator  # noqa: E402
from test_launch_plan_law import lane_deliveries, plan_fixture, plan_intake, stub_council  # noqa: E402

PAGE_CONTRACT = "skill06.page-draft-install.v1"
KIND, SCHEMA = "external-install", "skill83.external-install-manifest/v1"
RESTATED = "skill83.page-install-restatement/v1"
EXT_CODE, LANE_CODE = "AF-LAUNCH-PKG-EXTERNAL-INSTALL", "AF-LAUNCH-PKG-RECEIPT-LANE"
READER = "SWB-052"

_SPOOL = {}


def setUpModule():
    _SPOOL["dir"] = tempfile.TemporaryDirectory()
    _SPOOL["env"] = mock.patch.dict(os.environ, {"LAUNCH_EVENTS_SPOOL": _SPOOL["dir"].name})
    _SPOOL["env"].start()


def tearDownModule():
    _SPOOL["env"].stop()
    _SPOOL["dir"].cleanup()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(root: Path, rel: str, doc) -> dict:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raw = target.read_bytes()
    return {"path": rel, "sha256": _sha(raw), "size": len(raw)}


def _page_facts(unit: str, location: str) -> dict:
    n = abs(hash(unit)) % 10_000
    return {"page_id": f"P-{unit}", "funnel_id": "F1", "step_id": f"S-{unit}", "location_id": location,
            "draft_version_id": f"v-{n:04d}-{unit}", "content_sha256": _sha(unit.encode()),
            "preview_http_status": 200, "published": False, "installed_by": f"INST-{unit}", "read_by": READER}


def _readback(units: dict, location: str, **page_over) -> dict:
    pages = {}
    for unit, f in units.items():
        pages[unit] = {"page_id": f["page_id"], "http_status": 200, "funnelId": f["funnel_id"],
                       "stepId": f["step_id"], "locationId": location, "deleted": False,
                       "published_version_present": False, "preview_http_status": 200,
                       "top_version": {"pageType": "draft", "versionId": f["draft_version_id"],
                                       "blob_sha256": f["content_sha256"]}, **page_over.get(unit, {})}
    return {"kind": "rest_readback", "unit": READER, "read_at": "2026-11-24T00:57:08Z",
            "method": "read-only HTTP GET only", "location_id": location, "pages": pages}


class _Base(unittest.TestCase):
    """A launch whose every route page was installed by another skill and read back by SWB-052."""

    def setUp(self):
        install_stand_in_validator(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "package"
        self.src = Path(self.tmp.name) / "run"
        raw = plan_intake()
        raw["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client"}
        normalized = intake.validate(raw)
        inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=True)
        self.launch = launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)
        self.plan_hash = substrate.dispatch().vlp.plan_document_hash(self.launch)
        raw["approval"] = {**raw["approval"], "hash": self.plan_hash}
        self.normalized = intake.validate(raw)
        self.location = self.normalized["location_id"]
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        plan = plan_fixture()
        plan["approved_plan_hash"] = self.plan_hash
        for page in plan["pages"]:  # this launch's first page is the landing page the route carries
            if page.get("kind") == "sales":
                page["kind"] = "landing"
        self.plan = plan
        self.page_units = [u["id"] for u in lp.planned_units(plan) if u["type"] == "page"]
        self.deliveries = lane_deliveries(plan, self.out)
        self.plan_sha = self.deliveries[self.page_units[0]]["request"]["plan_sha256"]
        self.facts = {u: _page_facts(u, self.location) for u in self.page_units}
        back = _write(self.out, "evidence/readback-SWB-052.json", _readback(self.facts, self.location))
        self.readback_art = {**back, "role": "independent_readback"}
        for unit in self.page_units:
            self.deliveries[unit] = self.page_delivery(unit)
        (self.src / "launch.json").parent.mkdir(parents=True, exist_ok=True)
        (self.src / "launch.json").write_text(json.dumps(self.launch, indent=2) + "\n", encoding="utf-8")

    # ---- builders --------------------------------------------------------------------------------
    def install_receipt(self, page_unit: str, **over) -> dict:
        f = self.facts[page_unit]
        doc = {"unit": f["installed_by"], "page_id": f["page_id"], "location_id": self.location,
               "readback": {"versionId": f["draft_version_id"], "blob_sha256": f["content_sha256"]}}
        doc.update(over)
        return doc

    def page_delivery(self, unit: str, receipts=None, **facts) -> dict:
        receipts = receipts or [self.install_receipt(unit)]
        arts = [{**_write(self.out, f"evidence/{unit}/receipt-{i}.json", doc), "role": "install_receipt"}
                for i, doc in enumerate(receipts)]
        page_install = {**self.facts[unit], **facts}
        return {"state": "complete", "artifacts": arts + [dict(self.readback_art)],
                "lane_validation": {"lane": f"{page_install['installed_by']} via Skill 06 rail; read back "
                                            f"by {READER}", "contract": PAGE_CONTRACT, "state": "passed"},
                "request": {"plan_sha256": self.plan_sha, "request_id": page_install["installed_by"],
                            "input_hash": page_install["content_sha256"]},
                "page_install": page_install}

    def manifest(self, **over) -> dict:
        pages = []
        for unit in self.page_units:
            row = self.deliveries[unit]
            receipt = next(a for a in row["artifacts"] if a["role"] == "install_receipt")
            pages.append({"unit_id": unit, "installed_by": row["page_install"]["installed_by"],
                          "draft_version_id": row["page_install"]["draft_version_id"],
                          "readback_sha256": row["page_install"]["content_sha256"],
                          "install_receipt_sha256": receipt["sha256"]})
        doc = {"kind": KIND, "schema": SCHEMA, "launch_id": self.normalized["launch_id"],
               "tenant_id": self.normalized["tenant_id"], "location_id": self.location,
               "revision": self.normalized["revision"], "plan_document_hash": self.plan_hash, "pages": pages}
        doc.update(over)
        return doc

    def write_manifest(self, doc) -> None:
        _write(self.src, "dispatch/dispatch-manifest.json", doc)

    def refused(self, code=EXT_CODE, **kwargs) -> str:
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(**kwargs)
        self.assertEqual(ctx.exception.code, code, ctx.exception)
        self.assertFalse((self.out / "receipt.json").exists())
        return str(ctx.exception)


class ExternalInstallDispatchTests(_Base):
    def assemble(self, deliveries=None, pieces=None, normalized=None):
        # The design gate is judged by its own tests (test_lane83_designs); it still applies to an external
        # install package (designs_required), so it is stood in for here, where the dispatch binding is under test.
        with mock.patch.object(package, "_refuse_incomplete_designs", return_value=None), \
                mock.patch.object(package.page_designs, "design_violations", return_value=[]):
            verified = {"store": "x", "state": "verified", "store_state_raw": "present", "entries": 1}
            with mock.patch.object(package, "receipt_evidence", return_value=verified):
                return package.assemble(self.out, normalized or self.normalized, self.graph, pieces or {},
                                        source_root=self.src, council=self.advice, launch_plan=self.plan,
                                        deliveries=deliveries or self.deliveries)

    # ---- acceptance ------------------------------------------------------------------------------
    def test_an_external_install_manifest_binds_a_package_of_installed_pages(self):
        self.write_manifest(self.manifest())
        out = self.assemble()
        binding = out["manifest"]["dispatch_binding"]
        self.assertEqual(binding["state"], "external_install")
        self.assertEqual(binding["plan_document_hash"], self.plan_hash)
        self.assertEqual(sorted(p["unit_id"] for p in binding["pages"]), sorted(self.page_units))
        rows = {r["unit_id"]: r for r in out["receipt"]["units"]}
        for unit in self.page_units:
            self.assertEqual(rows[unit]["lane_validation"]["contract"], PAGE_CONTRACT)
            self.assertEqual(rows[unit]["status"], "draft_delivered")
        self.assertEqual(out["manifest"]["pieces"], [])

    # ---- the dispatch requirement is not weakened ------------------------------------------------
    def test_a_live_package_with_no_manifest_still_refuses_dispatch_missing(self):
        live = intake.validate({**plan_intake(), "test_only": False,
                                "approval": {"ref": "approval-1", "hash": self.plan_hash}})
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(normalized=live)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-DISPATCH-MISSING")

    def test_emails_texts_and_automations_still_need_their_own_lane_delivery(self):
        self.write_manifest(self.manifest())
        others = [u["id"] for u in lp.planned_units(self.plan) if u["type"] in ("email", "text", "automation")]
        self.assertTrue(others)
        for unit in others[:3]:
            with self.subTest(unit):
                deliveries = copy.deepcopy(self.deliveries)
                del deliveries[unit]
                with self.assertRaises(package.PackageError) as ctx:
                    self.assemble(deliveries=deliveries)
                self.assertNotEqual(ctx.exception.code, EXT_CODE)
                self.assertIn(unit, str(ctx.exception))

    def test_a_manifest_that_lists_a_non_page_unit_is_refused(self):
        email = next(u["id"] for u in lp.planned_units(self.plan) if u["type"] == "email")
        doc = self.manifest()
        doc["pages"].append({"unit_id": email, "installed_by": "x", "draft_version_id": "x",
                             "readback_sha256": "0" * 64, "install_receipt_sha256": "0" * 64})
        self.write_manifest(doc)
        self.assertIn("pages only", self.refused())

    # ---- forged or unverifiable manifests are refused --------------------------------------------
    def test_a_page_listed_without_its_verified_receipt_is_refused(self):
        unit = self.page_units[1]
        cases = {
            "receipt names another draft": self.page_delivery(
                unit, [self.install_receipt(unit, readback={"versionId": "v-old", "blob_sha256": "c" * 64})]),
            "receipt by another installer": self.page_delivery(unit, [self.install_receipt(unit, unit="X")]),
            "published claim": self.page_delivery(unit, published=True),
            "self read": self.page_delivery(unit, read_by=self.facts[unit]["installed_by"]),
        }
        for name, row in cases.items():
            with self.subTest(name):
                deliveries = copy.deepcopy(self.deliveries)
                deliveries[unit] = row
                self.write_manifest(self.manifest())
                self.assertIn(unit, self.refused(deliveries=deliveries))
        deliveries = copy.deepcopy(self.deliveries)
        del deliveries[unit]["page_install"]
        self.write_manifest(self.manifest())
        self.assertIn(unit, self.refused(deliveries=deliveries))

    def test_a_manifest_entry_that_is_not_its_delivery_is_refused(self):
        for key, value in (("install_receipt_sha256", "e" * 64), ("draft_version_id", "v-forged"),
                           ("readback_sha256", "f" * 64), ("installed_by", "SWB-999")):
            with self.subTest(key):
                doc = self.manifest()
                doc["pages"][0][key] = value
                self.write_manifest(doc)
                self.assertIn(key, self.refused())

    def test_a_route_page_not_listed_is_refused(self):
        doc = self.manifest()
        doc["pages"] = doc["pages"][1:]
        self.write_manifest(doc)
        self.assertIn("not filled", self.refused())

    def test_identity_and_plan_hash_forgeries_are_refused(self):
        cases = {"plan hash": dict(plan_document_hash="a" * 64), "launch": dict(launch_id="other-2026"),
                 "tenant": dict(tenant_id="tenant-z"), "location": dict(location_id="loc-z"),
                 "revision": dict(revision=9), "schema": dict(schema="x")}
        for name, over in cases.items():
            with self.subTest(name):
                self.write_manifest(self.manifest(**over))
                self.refused()

    def test_an_intake_approval_that_is_not_the_recomputed_plan_hash_is_refused(self):
        self.write_manifest(self.manifest())
        other = intake.validate({**plan_intake(), "approval": {"ref": "approval-1", "hash": "b" * 64}})
        self.assertIn("approval hash", self.refused(normalized=other))

    def test_a_launcher_piece_beside_an_external_install_manifest_is_refused(self):
        self.write_manifest(self.manifest())
        self.assertIn("launcher piece", self.refused(pieces={"landing": {"page_id": "x"}}))

    def test_a_duplicate_listing_is_refused(self):
        doc = self.manifest()
        doc["pages"].append(dict(doc["pages"][0]))
        self.write_manifest(doc)
        self.assertIn("twice", self.refused())


class RestatedInstallReceiptTests(_Base):
    """The page lane alone (delivery_units.page_draft_violations) on a restated install receipt."""

    UNIT = "page_downsell_1"

    def nested_original(self, **over) -> dict:
        f = self.facts[self.UNIT]
        doc = {"schema": "swb-install-receipt/v1", "unit": f["installed_by"],
               "page": {"page_id": f["page_id"], "funnel_id": f["funnel_id"], "step_id": f["step_id"]},
               "readback": {"versionHistory": [{"versionId": f["draft_version_id"]}],
                            "vh0_blob_sha256": f["content_sha256"]}}
        doc.update(over)
        return doc

    def restatement(self, original_sha: str, **over) -> dict:
        f = self.facts[self.UNIT]
        doc = {"schema": RESTATED, "unit": READER, "published": False,
               **{k: f[k] for k in ("page_id", "funnel_id", "step_id", "location_id", "draft_version_id",
                                    "content_sha256", "installed_by")},
               "source_receipt": {"sha256": original_sha, "unit": f["installed_by"]}}
        doc.update(over)
        return doc

    def row(self, original=None, restated_over=None, back=None) -> dict:
        orig_art = {**_write(self.out, "evidence/orig.json", original or self.nested_original()),
                    "role": "install_receipt"}
        rest = self.restatement(orig_art["sha256"], **(restated_over or {}))
        rest_art = {**_write(self.out, "evidence/restated.json", rest), "role": "install_receipt"}
        back_art = ({**_write(self.out, "evidence/rb.json", back), "role": "independent_readback"}
                    if back is not None else dict(self.readback_art))
        return {"lane_validation": {"contract": PAGE_CONTRACT, "state": "passed", "lane": "x"},
                "page_install": dict(self.facts[self.UNIT]), "location_id": self.location,
                "artifacts": [orig_art, rest_art, back_art]}

    def law(self, row) -> list:
        return du.page_draft_violations(self.UNIT, row, self.out)

    def test_the_nested_original_alone_is_still_refused(self):
        row = self.row()
        row["artifacts"] = [row["artifacts"][0], row["artifacts"][2]]
        self.assertTrue(self.law(row))

    def test_a_restatement_anchored_to_the_installers_own_receipt_is_accepted(self):
        self.assertEqual(self.law(self.row()), [])

    def test_forged_restatements_are_refused(self):
        f = self.facts[self.UNIT]
        cases = {
            "written by the installer": dict(restated_over={"unit": f["installed_by"]}),
            "no publish record": dict(restated_over={"published": None}),
            "another draft": dict(restated_over={"draft_version_id": "v-other"}),
            "another location": dict(restated_over={"location_id": "loc-z"}),
            "another installer": dict(restated_over={"installed_by": "SWB-999"}),
            "source not sealed": dict(restated_over={"source_receipt": {"sha256": "0" * 64}}),
            "no source": dict(restated_over={"source_receipt": None}),
            "original by someone else": dict(original=self.nested_original(unit="SWB-999")),
            "original names another draft": dict(original=self.nested_original(
                readback={"versionHistory": [{"versionId": "v-old"}], "vh0_blob_sha256": "c" * 64})),
            "original names another page": dict(original=self.nested_original(page={"page_id": "P-9"})),
            "original records a publish": dict(original=self.nested_original(published=True)),
            "read-back location differs": dict(back=_readback(self.facts, self.location,
                                                              **{self.UNIT: {"locationId": "loc-z"}})),
            "read-back names no location": dict(back=_readback(self.facts, self.location,
                                                               **{self.UNIT: {"locationId": None}})),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                fails = self.law(self.row(**kwargs))
                self.assertTrue(fails and fails[0].startswith(LANE_CODE), fails)

    def test_a_restatement_cannot_source_itself(self):
        row = self.row()
        rest = self.restatement("x")
        art = _write(self.out, "evidence/self.json", rest)
        rest["source_receipt"]["sha256"] = art["sha256"]  # cannot point at its own bytes: bytes change
        row["artifacts"] = [{**_write(self.out, "evidence/self.json", rest), "role": "install_receipt"},
                            row["artifacts"][2]]
        self.assertTrue(self.law(row))


if __name__ == "__main__":
    unittest.main(verbosity=2)
