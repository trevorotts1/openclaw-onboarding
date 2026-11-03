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
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK, paid_image_plan, patch_paid_budget  # noqa: E402
from launcher_core import (checks, council, image_plan, intake, launch_bridge, package,  # noqa: E402
                           route)
from test_intake_validation import reprice  # noqa: E402
from test_lane83_designs import make_piece  # noqa: E402
from test_launch_plan_law import lane_deliveries, plan_fixture, pieces_for  # noqa: E402,F401

CLIENT, WORKER = "client-test-1", "worker-test-9"
LABELS = substrate.source("71-blackceo-signature-page/scripts/deliverable_labels.py")
CONSUMER = HERE / "lane83_fake_consumer.py"
COUNCIL = {"step": "council_launch_planning", "skill": "x", "entry_point": "x", "status": "not_ready",
           "advice_state": "pending_live_session", "blocks_build": False, "is_permission": False}
BLOCKERS = ["native order form is not installed", "checkout images are placeholders"]


def recorded_binding(run: Path, approved: str) -> dict:
    """A stand-in for the ENF-03 dispatch binding, for tests of what a CLIENT delivery is held to.

    A live (test_only false) run cannot use the free fake consumer (Skill 49's adapter allow-list refuses
    it), so a real live dispatch is not available offline; the binding itself is proved against real
    dispatches in this file. The landing result carries a good bridge-receipt sidecar.
    """
    (run / "dispatch").mkdir(parents=True, exist_ok=True)
    (run / "dispatch" / "result-landing.json").write_text("{}", encoding="utf-8")
    (run / "dispatch" / "bridge-receipt-result-landing.json").write_text(json.dumps(
        {"request_id": "req-landing", "draft": False, "receipt_validation": "schema",
         "pipeline_exit": 0}), encoding="utf-8")
    return {"state": package.DISPATCH_STATE_BOUND, "root": run, "plan_document_hash": approved,
            "requests": {}, "plan_hash_matches": True, "to_confirm": [], "landing_pages": ["landing"],
            "landing_results": {"landing": run / "dispatch" / "result-landing.json"},
            "record": {"state": package.DISPATCH_STATE_BOUND, "plan_document_hash": approved}}


def payload(**plan) -> dict:
    doc = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client", **plan}
    # a test-only dispatch records the verified record's approval ref (approval_for: APPR-TEST)
    doc["approval"] = {**doc["approval"], "ref": "APPR-TEST"}
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
    return {"schema_version": "1.0", "approval_id": "APPR-TEST", "kind": "launch_plan_build",
            "plan_hash": plan_hash(doc), "client_identity": CLIENT, "source_message_ref": "msg-test-1",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
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
        snapshot = cls.rundir / package.INTAKE_SNAPSHOT_REL
        cls.bridge_wrote_snapshot = snapshot.is_file()
        if not cls.bridge_wrote_snapshot:
            # what launch_bridge.run writes once U-products-03's carried edit lands
            snapshot.write_text(json.dumps(intake.validate(cls.doc), sort_keys=True), encoding="utf-8")

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
        kw.setdefault("checkout_readback", TEST_ONLY_CHECKOUT_READBACK)
        kw.setdefault("council", COUNCIL)
        kw.setdefault("to_confirm", self.report["to_confirm"])
        kw.setdefault("landing_pages", self.report["landing_pages"])
        if named:
            kw["dispatch_run"] = run
        return package.assemble(
            run_dir=self.work / name, intake=normalized, route=route.compile_route(normalized),
            pieces=self.pieces(run) if pieces is None else pieces, source_root=run, **kw)

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
        # every default the dispatch report lists awaits the client; the package holds once it is confirmed
        (self.work / "pkg" / checks.TO_CONFIRM_RECORD).write_text(json.dumps({"confirmations": [
            {"field": e["field"], "confirmation_ref": "TEST-CLIENT-CONFIRMATION"}
            for e in self.report["to_confirm"]]}), encoding="utf-8")
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
        # the intake refuses a price its answers file does not hold, so the drift is one the answers hold too
        reprice(doc, doc["offers"][0]["offer_id"], amount_minor=doc["offers"][0]["price"]["amount_minor"] + 1)
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
                                            "evidence_ref": "TEST-ONLY-EVIDENCE", "attested_by": "operator"}
        err = self.refused("AF-LAUNCH-PKG-INTAKE-DRIFT", name="basis", doc=other, run=run)
        self.assertIn("entitlement", err.detail)
        # a practice run found beside the pieces (no named dispatch run) is held to the same snapshot
        other = copy.deepcopy(self.doc)
        other["approval"]["hash"] = "e" * 64
        err = self.refused("AF-LAUNCH-PKG-INTAKE-DRIFT", name="approval", doc=other, run=run, named=False)
        self.assertIn("approval", err.detail)

    def test_a_named_run_without_the_dispatch_time_intake_refuses(self):
        run = self.copy_run("nosnap")
        (run / package.INTAKE_SNAPSHOT_REL).unlink()
        self.refused("AF-LAUNCH-PKG-INTAKE-MISSING", name="named", run=run)
        built = self.assemble(name="found-beside", run=run, named=False)  # test_only intake: not strict
        self.assertEqual(built["manifest"]["dispatch_binding"]["intake_snapshot"], "absent")

    def test_a_real_dispatch_with_another_entitlement_basis_never_assembles(self):
        run = self.copy_run("real")
        if not self.bridge_wrote_snapshot:  # exercise exactly what dispatch left behind
            (run / package.INTAKE_SNAPSHOT_REL).unlink()
        other = copy.deepcopy(self.doc)
        other["entitlement_attestation"] = {"basis": "brand_management_membership",
                                            "evidence_ref": "TEST-ONLY-EVIDENCE", "attested_by": "operator"}
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(name="real-pkg", doc=other, run=run)
        self.assertIn(ctx.exception.code, {"AF-LAUNCH-PKG-INTAKE-MISSING", "AF-LAUNCH-PKG-INTAKE-DRIFT"})
        self.assertFalse((self.work / "real-pkg" / "package-manifest.json").exists())

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
        patch_paid_budget(self)
        live = payload(**paid_image_plan(9))
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

    def test_an_unbound_fixture_without_designs_needs_the_same_waiver(self):
        loose = self.copy_run("loose-waiver")
        shutil.rmtree(loose / "dispatch")
        self.refused("AF-LAUNCH-PKG-DESIGN-WAIVER", name="nowaiver", run=loose, named=False,
                     require_designs=False)
        built = self.assemble(name="waived-fixture", run=loose, named=False, require_designs=False,
                              design_waiver=self.waiver())
        self.assertEqual(built["manifest"]["dispatch_binding"]["state"], "unbound_fixture")
        for record in (built["manifest"], built["receipt"]):
            self.assertIn("designs waived", record["delivery_label"])

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


class CheckoutReadbackTests(DispatchedRun):
    def test_checkout_readback_is_passed_to_the_order_form_mapping(self):
        real = package.checkout_module.order_form_mapping
        seen = []

        def fake(intake_, route_, **kw):
            seen.append(kw)
            return {**real(intake_, route_), "readback_seen": kw.get("readback")}

        original = package.checkout_module.order_form_mapping
        package.checkout_module.order_form_mapping = fake
        try:
            built = self.assemble(name="rb", checkout_readback={"probe": 1})
            self.assertEqual(built["manifest"]["checkout"]["readback_seen"], {"probe": 1})
            self.assemble(name="no-rb")
        finally:
            package.checkout_module.order_form_mapping = original
        # per-offer checkout instances (CARRIED 49) hand a readback to every instance: the second assemble
        # passes the suite's TEST-ONLY readback through the same keyword
        self.assertEqual(seen, [{"readback": {"probe": 1}}, {"readback": TEST_ONLY_CHECKOUT_READBACK}])


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


class DispatchReportTests(DispatchedRun):
    """ENF-07: a bound package takes to_confirm and landing_pages from the run's own dispatch-report.json."""

    def test_a_bound_assemble_without_the_dispatch_report_is_refused_and_writes_nothing(self):
        run = self.copy_run("no-report")
        (run / package.DISPATCH_REPORT_REL).unlink()
        self.refused("AF-LAUNCH-PKG-DISPATCH-REPORT", name="norep", run=run)
        self.assertFalse((self.work / "norep" / "package-manifest.json").exists())

    def test_the_manifest_records_the_reports_to_confirm_and_hash_when_the_caller_gives_none(self):
        built = self.assemble(name="from-report", to_confirm=None, landing_pages=None)
        report = json.loads((self.rundir / package.DISPATCH_REPORT_REL).read_text(encoding="utf-8"))
        self.assertTrue(report["to_confirm"])
        self.assertEqual(built["manifest"]["to_confirm"], report["to_confirm"])
        record = built["manifest"]["dispatch_binding"]["dispatch_report"]
        self.assertEqual(record["sha256"],
                         hashlib.sha256((self.rundir / package.DISPATCH_REPORT_REL).read_bytes()).hexdigest())

    def test_a_to_confirm_that_drops_a_default_is_refused(self):
        shorter = self.report["to_confirm"][1:]
        err = self.refused("AF-LAUNCH-PKG-DISPATCH-REPORT", name="dropped", to_confirm=shorter)
        self.assertIn("to_confirm", err.detail)
        self.refused("AF-LAUNCH-PKG-DISPATCH-REPORT", name="pages", landing_pages=["landing"])


class AssembleLawTests(DispatchedRun):
    def test_a_graph_missing_a_doc_02_edge_is_refused_before_anything_is_written(self):
        normalized = intake.validate(self.doc)
        graph = route.compile_route(normalized)
        graph["edges"] = [e for e in graph["edges"] if e["event"] != "explicit_decline"]
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.work / "law", normalized, graph, self.pieces(), source_root=self.rundir,
                             council=COUNCIL, require_designs=True, dispatch_run=self.rundir,
                             checkout_readback=TEST_ONLY_CHECKOUT_READBACK)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ROUTE-LAW")
        self.assertIn("missing contract edges", ctx.exception.detail)
        self.assertFalse((self.work / "law" / "package-manifest.json").exists())

    def test_the_manifest_says_the_skill_number_is_final_because_registration_says_so(self):
        built = self.assemble(name="number")
        registered = json.loads((SKILL_ROOT / "registration.json").read_text(encoding="utf-8"))
        manifest = json.loads((self.work / "number" / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertIs(manifest["launcher"]["skill_number_final"], registered["skill"]["number_final"])
        self.assertIs(built["manifest"]["launcher"]["skill_number_final"], True)

    def test_a_receipt_without_a_live_council_session_never_reads_like_a_council_review(self):
        normalized = intake.validate(self.doc)
        stub = lambda _launch: {"status": "ready_no_advice", "ready": True, "advice": None,  # noqa: E731
                                "advice_state": "pending_live_session"}
        advice = council.planning_step(normalized, runner=stub)
        legacy = {k: v for k, v in advice.items() if k not in ("council_session_held", "client_summary")}
        for name, record in (("planning-step", advice), ("legacy", legacy)):
            with self.subTest(name):
                self.assemble(name=f"council-{name}", council=record)
                receipt = json.loads((self.work / f"council-{name}" / "receipt.json").read_text(encoding="utf-8"))
                self.assertIs(receipt["council"]["council_session_held"], False)
                self.assertIn("No Council advice was obtained", receipt["council"]["client_summary"])

    def test_an_approval_that_does_not_resolve_to_a_recorded_design_board_approval_is_refused(self):
        unresolved = {"design_board": {"state": "approved", "approval_ref": "nope.json",
                                        "record_sha256": "0" * 64},
                      "final_mockups": {"state": "awaiting_client_approval", "approval_ref": None}}
        self.refused("AF-LAUNCH-PAGE-DESIGNS", name="approvals", design_approvals=unresolved)
        self.assertFalse((self.work / "approvals" / "package-manifest.json").exists())


class BridgeReceiptTests(DispatchedRun):
    """ENF-09: assemble refuses a landing result whose bridge receipt names a fallback or an open gate."""

    SIDECAR = "bridge-receipt-result-landing.json"

    def run_with_sidecar(self, doc):
        run = self.copy_run(f"sidecar-{len(list(self.work.iterdir()))}")  # a fresh copy per shape
        if doc is not None:
            (run / "dispatch" / self.SIDECAR).write_text(json.dumps(doc), encoding="utf-8")
        return run

    GOOD = {"request_id": "r", "draft": False, "receipt_validation": "schema", "pipeline_exit": 0}

    def test_a_good_sidecar_is_copied_into_the_package_and_recorded(self):
        run = self.run_with_sidecar(self.GOOD)
        built = self.assemble(name="good-sidecar", run=run)
        recorded = built["manifest"]["dispatch_binding"]["bridge_receipts"]
        self.assertIn("landing", [r["slot"] for r in recorded])
        for row in recorded:
            self.assertTrue((self.work / "good-sidecar" / row["path"]).is_file())
        self.assertEqual(checks._bridge_receipt_violations(built["manifest"], (self.work / "good-sidecar").resolve()), [])

    def test_every_failing_shape_is_refused_by_name(self):
        for label, doc in (("fallback", {**self.GOOD, "receipt_validation": "vendored_schema_fallback"}),
                           ("opt-in fallback", {**self.GOOD, "opt_in_receipt_validation": "vendored_schema_fallback",
                                                "opt_in_pipeline_exit": 0}),
                           ("exit", {**self.GOOD, "pipeline_exit": 2}),
                           ("no exit", {k: v for k, v in self.GOOD.items() if k != "pipeline_exit"}),
                           ("opt-in exit", {**self.GOOD, "opt_in_receipt_validation": "schema",
                                            "opt_in_pipeline_exit": 1})):
            with self.subTest(label):
                err = self.refused(package.BRIDGE_RECEIPT_CODE, name="bad-sidecar", run=self.run_with_sidecar(doc))
                self.assertIn("landing", err.detail)

    def test_a_draft_only_stops_a_delivery_and_a_missing_sidecar_only_a_client_delivery(self):
        draft = {**self.GOOD, "draft": True}
        self.assertEqual(package.bridge_receipt_violations(draft, delivery=False), [])
        self.assertTrue(any("draft" in why for why in package.bridge_receipt_violations(draft, delivery=True)))
        run = self.copy_run("no-sidecar")
        (run / "dispatch" / self.SIDECAR).unlink(missing_ok=True)
        built = self.assemble(name="test-run-no-sidecar", run=run)  # a test run has no landing_bridge sidecar
        self.assertEqual(built["manifest"]["dispatch_binding"]["bridge_receipts"], [])


class ClientDeliveryStoreTests(unittest.TestCase):
    """ENF-17: a client delivery (test_only false) needs Skill 49's live receipt store to verify."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patch_paid_budget(self)
        raw = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
        raw["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client",
                             **paid_image_plan(9)}
        raw["test_only"] = False
        self.normalized = intake.validate(raw)
        self.graph = route.compile_route(self.normalized)
        node_pieces = {n["role"]: make_piece(self.work, self.normalized, n, provider="kie")
                       for n in self.graph["nodes"]}
        self.pieces = node_pieces
        run = self.work / "dispatch-run"
        self.binding = recorded_binding(run, self.normalized["approval"]["hash"])

    def assemble(self, **kw):
        with mock.patch.object(package, "_find_dispatch_root", return_value=(self.work / "dispatch-run", True)), \
                mock.patch.object(package, "_bind_dispatch", return_value=self.binding), \
                mock.patch.object(package, "_bind_piece"):
            return package.assemble(self.work / "pkg", self.normalized, self.graph, self.pieces,
                                    source_root=self.work, council=COUNCIL, require_designs=True,
                                    checkout_readback=TEST_ONLY_CHECKOUT_READBACK, **kw)

    def test_no_receipt_store_refuses_the_delivery_naming_absent(self):
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble()
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-RECEIPTS")
        self.assertIn("ABSENT", ctx.exception.detail)
        self.assertFalse((self.work / "pkg" / "package-manifest.json").exists())

    def test_a_hand_appended_unsigned_line_refuses_the_delivery_naming_unsigned(self):
        (self.work / "pkg").mkdir()
        (self.work / "pkg" / "delegation_receipts.jsonl").write_text(
            json.dumps({"phase": "pages", "provider": "kie", "operation": "image"}) + "\n", encoding="utf-8")
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble()
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-RECEIPTS")
        self.assertIn("UNSIGNED", ctx.exception.detail)

    def test_the_same_missing_store_does_not_stop_a_test_only_package(self):  # control: the rule is for deliveries
        normalized = intake.validate(json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8")))
        graph = route.compile_route(normalized)
        pieces = {n["role"]: make_piece(self.work, normalized, n) for n in graph["nodes"]}
        built = package.assemble(self.work / "test-pkg", normalized, graph, pieces, source_root=self.work,
                                 council=COUNCIL, require_designs=True,
                                 checkout_readback=TEST_ONLY_CHECKOUT_READBACK)
        self.assertIs(built["manifest"]["test_only"], True)


class LaunchPlanBindingTests(unittest.TestCase):
    """CON-04 and S44-21 at assemble: the plan is the approved launch, and an automation is a Skill 44 build."""

    def setUp(self):
        from test_launch_plan_law import base_intake, stub_council
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.addCleanup(self.tmp.cleanup)
        self.normalized = intake.validate(base_intake())
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.pieces = pieces_for(self.run_dir, self.graph, self.normalized)

    def assemble(self, plan, deliveries):
        return package.assemble(self.run_dir, self.normalized, self.graph, self.pieces, council=self.advice,
                                launch_plan=plan, deliveries=deliveries)

    def test_a_plan_whose_hash_is_not_the_approved_hash_is_refused(self):
        plan = {**plan_fixture(), "approved_plan_hash": "c" * 64}
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(plan, lane_deliveries(plan, self.run_dir))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-BIND")

    def test_a_done_file_and_three_strings_do_not_seal_an_automation(self):
        plan = plan_fixture()
        deliveries = lane_deliveries(plan, self.run_dir)
        (self.run_dir / "done.txt").write_bytes(b"done\n")
        for unit in plan["automations"]:
            deliveries[unit["id"]]["artifacts"] = [{"path": "done.txt", "size": 5,
                                                      "sha256": hashlib.sha256(b"done\n").hexdigest()}]
            deliveries[unit["id"]]["lane_validation"] = {"lane": "s44", "contract": "x", "state": "passed"}
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(plan, deliveries)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-UNIT-AUTOMATION")

    def test_the_unmodified_plan_and_deliveries_assemble(self):  # control: the two refusals above are not always-on
        plan = plan_fixture()
        built = self.assemble(plan, lane_deliveries(plan, self.run_dir))
        self.assertEqual(built["manifest"]["launch_plan"]["completeness"]["percentage"], 100)


if __name__ == "__main__":
    unittest.main()
