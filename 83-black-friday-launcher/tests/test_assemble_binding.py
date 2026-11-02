"""ENF-03 / CHK-17: assemble is bound to the dispatch run, and page blockers survive packaging.

A real (free) dispatch is run once with the fake page consumer. Every case then tampers one thing
and expects a named AF-LAUNCH-PKG code: invented request ids, a +1 cent price, another approval hash,
another entitlement basis, a forged artifact. Nothing here calls a provider or the network.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
from launcher_core import (checks, image_plan, intake, launch_bridge, package,  # noqa: E402
                           route)

CLIENT, WORKER = "client-test-1", "worker-test-9"
LABELS = substrate.source("71-blackceo-signature-page/scripts/deliverable_labels.py")
CONSUMER = HERE / "lane83_fake_consumer.py"
COUNCIL = {"step": "council_launch_planning", "skill": "x", "entry_point": "x", "status": "not_ready",
           "advice_state": "pending_live_session", "blocks_build": False, "is_permission": False}
BLOCKERS = ["native order form is not installed", "checkout images are placeholders"]


def payload(**plan) -> dict:
    doc = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client", **plan}
    return doc


def launch_for(doc: dict) -> dict:
    normalized = intake.validate(doc)
    inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
    return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)


def plan_hash(doc: dict) -> str:
    return substrate.dispatch().vlp.plan_document_hash(launch_for(doc))


def approved_doc(**plan) -> dict:
    """An intake whose approval hash IS the plan hash the client approved (the hash ignores approval)."""
    doc = payload(**plan)
    doc["approval"]["hash"] = plan_hash(doc)
    return doc


def approval_for(doc: dict) -> dict:
    return {"schema_version": "1.0", "approval_id": "APPR-TEST", "subject_type": "launch_plan_build",
            "subject_hash": plan_hash(doc), "owner_identity_ref": CLIENT, "source_message_ref": "msg-test-1",
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scope": ["launch_plan_build"], "revoked": False,
            "verification_class": "recorded_consent_not_cryptographically_sealed"}


def consumer_config(provider: str = "stub") -> dict:
    landing_pages = ["--pages", "{landing_pages}"]
    return {"adapters": {role: {"command": [sys.executable, str(CONSUMER), "{request}", "{result}",
                                            str(LABELS), "--provider", provider,
                                            *(landing_pages if role == "landing" else [])],
                                "timeout_s": 60} for role in substrate.dispatch().PAGE_ROLES}}


def dispatch(doc: dict, out: Path, provider: str = "stub") -> dict:
    return launch_bridge.run(doc, out, approval=approval_for(doc), client_identity_ref=CLIENT,
                             worker_identity_ref=WORKER, adapters_config=consumer_config(provider))


class DispatchedRun(unittest.TestCase):
    """One real dispatch shared by every case; each case works on copies, never on the original."""

    provider = "stub"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.doc = approved_doc()
        cls.rundir = cls.base / "run"
        cls.report = dispatch(cls.doc, cls.rundir, cls.provider)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.base))

    def pieces(self, run: Path | None = None) -> dict:
        run = run or self.rundir
        return {r: json.loads((run / "pieces" / f"{r}.json").read_text(encoding="utf-8"))
                for r in self.report["pages"]}

    def copy_run(self, name: str = "copy") -> Path:
        target = self.work / name
        shutil.copytree(self.rundir, target)
        return target

    def assemble(self, name="pkg", doc=None, pieces=None, run=None, named=True, **kw):
        doc = doc or self.doc
        run = run or self.rundir
        normalized = intake.validate(doc)
        kw.setdefault("require_designs", True)
        if named:
            kw["dispatch_run"] = run
        return package.assemble(
            run_dir=self.work / name, intake=normalized, route=route.compile_route(normalized),
            pieces=self.pieces(run) if pieces is None else pieces, source_root=run, council=COUNCIL,
            to_confirm=self.report["to_confirm"], landing_pages=self.report["landing_pages"], **kw)

    def refused(self, code, **kw):
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(**kw)
        self.assertEqual(ctx.exception.code, code, ctx.exception)
        return ctx.exception


class BoundToDispatchTests(DispatchedRun):
    def test_a_real_dispatch_assembles_with_the_approved_plan_hash_computed_from_it(self):
        built = self.assemble()
        want = plan_hash(self.doc)
        for record in (built["manifest"], built["receipt"]):
            self.assertEqual(record["approved_plan_hash"], want)
            self.assertEqual(record["dispatch_binding"]["state"], "bound")
            self.assertEqual(record["dispatch_binding"]["plan_document_hash"], want)
        self.assertTrue(all(row["approved_plan_hash"] == want for row in built["receipt"]["units"]))
        self.assertEqual(built["receipt"]["live_effects"], "none")  # a stub run rendered nothing paid
        self.assertEqual(checks.check_package(Path(built["manifest_path"]), self.work / "pkg"), [])

    def test_invented_piece_files_with_made_up_request_ids_are_refused(self):
        roles = ("landing", "checkout", "upsell_1", "downsell_1", "thank_you")
        for role in roles:
            with self.subTest(role=role):
                pieces = self.pieces()
                pieces[role]["request_id"] = f"made-up-{role}"
                err = self.refused("AF-LAUNCH-PKG-REQUEST", name=f"inv-{role}", pieces=pieces)
                self.assertIn("is not in dispatch-manifest.json", err.detail)
        every = self.pieces()
        for role, piece in every.items():
            piece["request_id"], piece["input_hash"] = f"made-up-{role}", "f" * 64
        self.refused("AF-LAUNCH-PKG-REQUEST", name="inv-all", pieces=every)

    def test_a_request_id_borrowed_from_another_page_or_a_wrong_input_hash_is_refused(self):
        pieces = self.pieces()
        pieces["landing"]["request_id"] = pieces["checkout"]["request_id"]
        self.assertIn("another page's request",
                      self.refused("AF-LAUNCH-PKG-REQUEST", name="borrow", pieces=pieces).detail)
        pieces = self.pieces()
        pieces["checkout"]["input_hash"] = "0" * 64
        self.refused("AF-LAUNCH-PKG-REQUEST", name="hash", pieces=pieces)

    def test_a_plus_one_cent_price_change_is_refused_by_name(self):
        doc = copy.deepcopy(self.doc)
        doc["offers"][0]["price"]["amount_minor"] += 1
        err = self.refused("AF-LAUNCH-PKG-PLAN-DRIFT", doc=doc)
        self.assertIn("price", err.detail)

    def test_another_approval_hash_is_refused_and_the_computed_hash_is_what_is_recorded(self):
        doc = copy.deepcopy(self.doc)
        doc["approval"]["hash"] = "e" * 64
        self.refused("AF-LAUNCH-PKG-APPROVAL-HASH", doc=doc)

    def test_another_entitlement_basis_or_approval_is_refused_against_the_dispatch_time_intake(self):
        run = self.copy_run()
        (run / package.INTAKE_SNAPSHOT_REL).write_text(json.dumps(self.doc), encoding="utf-8")
        ok = self.assemble(name="same", run=run)
        self.assertEqual(ok["manifest"]["dispatch_binding"]["intake_snapshot"], "verified")
        other = copy.deepcopy(self.doc)
        other["entitlement_attestation"] = {"basis": "brand_management_membership",
                                            "evidence_ref": "ev-2", "attested_by": "operator"}
        err = self.refused("AF-LAUNCH-PKG-INTAKE-DRIFT", name="basis", doc=other, run=run)
        self.assertIn("entitlement", err.detail)
        # a practice run found beside the pieces (no named dispatch run) is held to the same snapshot
        other = copy.deepcopy(self.doc)
        other["approval"]["hash"] = "e" * 64
        err = self.refused("AF-LAUNCH-PKG-INTAKE-DRIFT", name="approval", doc=other, run=run, named=False)
        self.assertIn("approval", err.detail)

    def test_a_piece_the_dispatch_never_produced_is_refused_even_with_the_right_request_ids(self):
        pieces = self.pieces()
        forged = self.work / "forged.html"
        forged.write_text("<html>not made by the dispatch</html>", encoding="utf-8")
        art = pieces["checkout"]["artifacts"][0]
        art["path"], art["sha256"] = str(forged), hashlib.sha256(forged.read_bytes()).hexdigest()
        err = self.refused("AF-LAUNCH-PKG-RESULT", name="forged", pieces=pieces)
        self.assertIn("not one the dispatch produced", err.detail)
        pieces = self.pieces()
        pieces["checkout"]["status"], pieces["checkout"]["proof_class"] = "live_verified", "L5"
        self.assertIn("status", self.refused("AF-LAUNCH-PKG-RESULT", name="raised", pieces=pieces).detail)

    def test_without_a_dispatch_run_a_live_package_is_refused_and_a_test_fixture_is_labelled(self):
        live = payload(image_cap=9, paid_render_approval_ref="TEST-APPROVAL-REF")
        live["test_only"] = False
        empty = self.work / "empty"
        empty.mkdir()
        self.refused("AF-LAUNCH-PKG-DISPATCH-MISSING", name="live", doc=live, run=empty, named=False,
                     pieces={})
        self.refused("AF-LAUNCH-PKG-DISPATCH-MISSING", name="named", run=empty, pieces={})
        loose = self.copy_run("loose")
        shutil.rmtree(loose / "dispatch")
        built = self.assemble(name="fixture", run=loose, named=False)
        self.assertEqual(built["receipt"]["dispatch_binding"]["state"], "unbound_fixture")

    def test_a_reviewer_is_required_when_independent_review_is_claimed(self):
        for slot in ("landing", "sales"):  # the route-node path and the extra-slot path
            for reviewer in (None, "lane83-fake-consumer"):
                with self.subTest(slot=slot, reviewer=reviewer):
                    pieces = self.pieces()
                    pieces[slot]["independent_review"], pieces[slot]["reviewer_session"] = True, reviewer
                    self.refused("AF-LAUNCH-PKG-REVIEW", name=f"rev-{slot}", pieces=pieces)

    def waiver(self, **over):
        return {"approval_ref": "APPR-WAIVE-1", "subject_type": "design_waiver",
                "subject_hash": plan_hash(self.doc), "owner_identity_ref": CLIENT, "revoked": False,
                **over}

    def test_assembling_without_designs_needs_a_verified_approval(self):
        self.refused("AF-LAUNCH-PKG-DESIGN-WAIVER", name="none", require_designs=False)
        for bad in ({"approval_ref": ""}, {"subject_hash": "9" * 64}, {"revoked": True},
                    {"subject_type": "plan"}, {"owner_identity_ref": ""}):
            with self.subTest(bad=bad):
                self.refused("AF-LAUNCH-PKG-DESIGN-WAIVER", name="bad", require_designs=False,
                             design_waiver=self.waiver(**bad))

    def test_a_verified_waiver_is_recorded_and_stamps_the_delivery_label(self):
        built = self.assemble(name="waived", require_designs=False, design_waiver=self.waiver())
        for record in (built["manifest"], built["receipt"]):
            self.assertIn("designs waived", record["delivery_label"])
            self.assertEqual(record["design_waiver"]["approval_ref"], "APPR-WAIVE-1")
        self.assertFalse(built["manifest"]["designs_required"])

    def blocked_run(self) -> Path:
        run = self.copy_run("blocked")
        for rel in ("pieces/checkout.json", "dispatch/result-checkout.json"):
            doc = json.loads((run / rel).read_text(encoding="utf-8"))
            doc["blockers"] = list(BLOCKERS)
            (run / rel).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return run

    def test_blockers_travel_into_the_manifest_and_receipt_and_the_label_is_not_a_full_launch(self):
        built = self.assemble(name="blocked", run=self.blocked_run())
        manifest, receipt = built["manifest"], built["receipt"]
        checkout = next(p for p in manifest["pieces"] if p["role"] == "checkout")
        self.assertEqual(checkout["blockers"], BLOCKERS)
        unit = next(u for u in receipt["units"] if u["unit_id"] == checkout["slot"])
        self.assertEqual(unit["blockers"], BLOCKERS)
        for record in (manifest, receipt):
            self.assertEqual([b["role"] for b in record["open_blockers"]], ["checkout"])
            self.assertTrue(record["delivery_label"].startswith("design-only"))
            self.assertNotEqual(record["delivery_label"], package.DELIVERY_LABELS[package.DELIVERY_SCOPE_FULL])
        self.assertIn(package.SEAM_NATIVE_CHECKOUT_INSTALL, manifest["seams"])

    def test_a_full_launch_refuses_while_any_page_blocker_is_open_and_names_them(self):
        run = self.blocked_run()
        plan = {"launch_id": self.doc["launch_id"]}
        err = self.refused("AF-LAUNCH-PKG-BLOCKERS", name="full", run=run, launch_plan=plan,
                           delivery_scope=package.DELIVERY_SCOPE_FULL)
        self.assertIn("checkout", err.detail)
        self.assertIn("native order form is not installed", err.detail)

    def test_a_clean_package_carries_empty_blockers_and_the_open_checkout_seam(self):
        built = self.assemble(name="clean")
        self.assertEqual(built["manifest"]["open_blockers"], [])
        self.assertTrue(all(p["blockers"] == [] for p in built["manifest"]["pieces"]))
        self.assertFalse(built["manifest"]["delivery_label"].startswith("design-only"))
        self.assertIn(package.SEAM_NATIVE_CHECKOUT_INSTALL, built["manifest"]["seams"])

    def test_a_dispatched_full_launch_refuses_when_the_lane_receipts_are_absent(self):
        plan = {"launch_id": self.doc["launch_id"]}
        err = self.refused("AF-LAUNCH-PKG-RECEIPTS", name="norcpt", launch_plan=plan,
                           delivery_scope=package.DELIVERY_SCOPE_FULL)
        self.assertIn("lane receipts", err.detail)
        self.assertIn("absent", err.detail)


class PaidRenderTests(DispatchedRun):
    provider = "kie"  # the fake consumer records provider kie on every picture it "renders"

    def test_live_effects_counts_the_paid_picture_renders_instead_of_the_constant_none(self):
        pieces = self.pieces()
        want = sum(1 for piece in pieces.values() for art in piece["artifacts"]
                   if (art["kind"].endswith("_section") or art["kind"] == "board")
                   and art["provider"] == "kie")
        self.assertGreater(want, 0)
        built = self.assemble()
        self.assertEqual(built["manifest"]["live_effects"], f"paid_image_renders:{want}")
        self.assertEqual(built["receipt"]["live_effects"], f"paid_image_renders:{want}")


if __name__ == "__main__":
    unittest.main()
