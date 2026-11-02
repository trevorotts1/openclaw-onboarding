"""Package check: the check_rules seam, honest design levels, the to_confirm gate and route-graph law.

Free: pure files and the fake page consumer. Nothing calls a provider or a hosting service.
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import hashlib
import io
import json
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import route_law  # noqa: E402
import substrate  # noqa: E402
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK  # noqa: E402
from launcher_core import (check_rules, checks, cli, intake, launch_bridge, package,  # noqa: E402
                           page_designs, route)
from test_lane83_designs import COUNCIL, make_piece  # noqa: E402
from test_page_designs_real import make_client_delivery  # noqa: E402

PDF_AND_BOARD = ["wireframe_desktop_pdf", "wireframe_mobile_pdf", "mockup_desktop_pdf",
                 "mockup_mobile_pdf", "board"]


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


IMAGE_STAGES = ("image-inventory-prompts", "image-generation-qc", "image-map-upload",
                "design-board", "final-mockups")


def close_image_stages(root, manifest):
    """A paid run delivers finished pages (DECISIONS 2026-11-02 09:25, IMG-01): every page's image
    stages closed by stage_gate and an image QC report with passing averages (check_rules/image_qc.py)."""
    from launcher_core import graphics_hooks
    root, pages = Path(root), []
    for n, piece in enumerate(manifest["pieces"]):
        run, state = root / "image-runs" / f"{n}-{piece['role']}", {"stages": {}}
        for stage in IMAGE_STAGES:
            art = run / stage / "artifact.txt"
            art.parent.mkdir(parents=True, exist_ok=True)
            art.write_text(stage, encoding="utf-8")
            state["stages"][stage] = {"status": "closed", "receipt_status": "pass", "artifact_hashes": {
                f"{stage}/artifact.txt": hashlib.sha256(art.read_bytes()).hexdigest()}}
            receipt = run / "private" / "receipts" / f"{stage}.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        (run / "private" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        pages.append({"page": run.name, "role": piece["role"], "run_dir": str(run)})
    (root / "qc").mkdir(exist_ok=True)
    (root / "qc" / "image_stages_report.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
    assets = [{"local_path": i["local_path"], "asset_id": i["asset_id"], "average": 9.0, "pass": True,
               "triggered_autofails": []} for i in graphics_hooks.collect_images(manifest, root)]
    (root / "qc" / "image_qc_report.json").write_text(json.dumps({"assets": assets}), encoding="utf-8")


def store(ok=True, detail="verified"):
    """A stand-in Skill 49 receipt module: verify_delivery_store answers as told, and the store it reads
    holds one signed line (what package.assemble's own evidence step reads)."""
    return types.SimpleNamespace(verify_delivery_store=lambda root: (ok, detail),
                                 load=lambda root: [{"phase": "pages"}],
                                 store_state=lambda root: "present" if ok else "unsigned")


def verified_design_waiver(plan_hash: str) -> dict:
    """The owner's design_waiver approval record (TEST-ONLY ids), bound to this plan hash, as
    package._verify_design_waiver requires it. Never loosened: every field below is checked."""
    return {"approval_ref": "APPR-WAIVE-TEST", "subject_type": "design_waiver", "subject_hash": plan_hash,
            "owner_identity_ref": "client-test-1", "revoked": False}


class PackageCase(unittest.TestCase):
    test_only = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        raw = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
        raw["test_only"] = self.test_only
        self.normalized = intake.validate(raw)
        self.graph = route.compile_route(self.normalized)

    def tearDown(self):
        self.tmp.cleanup()

    def pieces(self, **kw):
        return {n["role"]: make_piece(self.work, self.normalized, n, **kw) for n in self.graph["nodes"]}

    def build(self, pieces=None, name="pkg", **kw):
        kw.setdefault("require_designs", True)
        kw.setdefault("checkout_readback", TEST_ONLY_CHECKOUT_READBACK)
        if kw["require_designs"] is False:  # waiving designs needs the owner's recorded approval
            kw.setdefault("design_waiver", verified_design_waiver(self.normalized["approval"]["hash"]))
        built = package.assemble(self.work / name, self.normalized, self.graph,
                                 pieces if pieces is not None else self.pieces(),
                                 source_root=self.work, council=COUNCIL, **kw)
        return built, self.work / name

    def check(self, built, root, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fails = checks.check_package(Path(built["manifest_path"]), root, **kw)
        return fails, out.getvalue()

    @staticmethod
    def reseal(root: Path, mutate):
        """Change the manifest and re-seal the receipt over it, as a hand edit that keeps the seal."""
        manifest_path = root / "package-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutate(manifest)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt_path = root / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["manifest"]["sha256"] = sha(manifest_path)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest_path


    @staticmethod
    def edit_receipt(root: Path, **changes):
        """Change receipt.json fields only (the receipt seals the manifest hash, not itself)."""
        path = root / "receipt.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt.update(changes)
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class SeamTests(PackageCase):
    def run_with_rule(self, source: str):
        built, root = self.build()
        rules = self.work / "rules"
        rules.mkdir(exist_ok=True)
        (rules / "rule_one.py").write_text(textwrap.dedent(source), encoding="utf-8")
        with mock.patch.object(check_rules, "RULES_DIR", rules):
            return self.check(built, root)[0]

    def test_a_package_with_no_rule_violation_passes(self):
        self.assertEqual(self.run_with_rule("def violations(manifest, root, skill_root):\n    return []\n"), [])

    def test_check_package_fails_on_every_violation_a_rule_module_returns(self):
        fails = self.run_with_rule("""
            def violations(manifest, root, skill_root):
                return ["AF-RULE-ONE: first", "AF-RULE-ONE: second"]
            """)
        self.assertEqual(fails, ["AF-RULE-ONE: first", "AF-RULE-ONE: second"])

    def test_a_rule_receives_the_manifest_and_the_package_root(self):
        fails = self.run_with_rule("""
            def violations(manifest, root, skill_root):
                return [f"saw {manifest['launch_id']} at {root.name}"]
            """)
        self.assertEqual(fails, ["saw TEST-FIXTURE-ELEVATION at pkg"])

    def test_a_broken_rule_module_is_a_violation_never_a_skip(self):
        for label, source in (("no function", "x = 1\n"),
                              ("raises", "def violations(m, r, s):\n    raise RuntimeError('boom')\n"),
                              ("bad return", "def violations(m, r, s):\n    return 'ok'\n"),
                              ("syntax error", "def violations(:\n")):
            fails = self.run_with_rule(source)
            self.assertEqual(len(fails), 1, (label, fails))
            self.assertTrue(fails[0].startswith("AF-LAUNCH-CHECK-RULE: rule_one"), (label, fails))

    def test_the_shipped_rules_folder_loads_cleanly(self):
        built, root = self.build()
        self.assertEqual(check_rules.run(json.loads(Path(built["manifest_path"]).read_text()), root, SKILL_ROOT), [])


class DesignLevelTests(PackageCase):
    def test_the_stub_lane_output_passes_as_images_only_render_pending(self):
        # The stub provider writes placeholder section images and never composes PDFs or boards.
        pieces = self.pieces(provider="stub", omit=PDF_AND_BOARD)
        built, root = self.build(pieces)
        fails, printed = self.check(built, root)
        self.assertEqual(fails, [])
        self.assertIn("images only, render pending", printed)

    def test_images_only_counts_the_section_images_against_the_sections(self):
        pieces = self.pieces(provider="stub", omit=PDF_AND_BOARD)
        pieces["checkout"]["artifacts"] = [
            a for a in pieces["checkout"]["artifacts"]
            if not (a["kind"] == "wireframe_desktop_section" and "_s02-of-02_" in a["path"])]
        built, root = self.build(pieces)
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: checkout wireframe desktop section has sections [1] of 2", fails)

    def test_images_only_still_needs_every_section_kind(self):
        pieces = self.pieces(provider="stub", omit=PDF_AND_BOARD + ["mockup_mobile_section"])
        built, root = self.build(pieces)
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing mockup mobile section", fails)

    def test_a_half_rendered_stub_package_is_not_images_only(self):
        built, root = self.build(self.pieces(provider="stub", omit=["board"]))
        fails, printed = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: checkout is missing board", fails)
        self.assertNotIn("images only", printed)

    def test_a_full_test_package_is_labelled_a_full_set(self):
        built, root = self.build()
        fails, printed = self.check(built, root)
        self.assertEqual(fails, [])
        self.assertIn("full set (test package)", printed)

    def waived(self, record, label="designs waived"):
        built, root = self.build(require_designs=False)
        # record None: the label claims a waiver the manifest does not carry (assemble always records one)
        path = self.reseal(root, lambda m: m.update(design_waiver=record, delivery_label=label))
        return self.check({"manifest_path": path}, root), root

    def good_waiver(self, root):
        plan_hash = json.loads((root / "package-manifest.json").read_text())["approved_plan_hash"]
        return {"approval_ref": "owner-ok-2026-11-02", "owner_identity_ref": "client-test-1",
                "subject_hash": plan_hash}

    def test_a_waiver_without_an_approval_ref_fails(self):
        (fails, _), _ = self.waived({"approval_ref": "", "owner_identity_ref": "client-test-1",
                                     "subject_hash": "x"})
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: the design waiver is not an owner approval bound "
                      "to this plan hash", fails)

    def test_a_full_waiver_record_passes_and_the_label_is_printed(self):
        built, root = self.build(require_designs=False)
        path = self.reseal(root, lambda m: m.update(
            design_waiver=self.good_waiver(root), delivery_label="designs waived"))
        fails, printed = self.check({"manifest_path": path}, root)
        self.assertEqual(fails, [])
        self.assertIn("designs waived (owner approval owner-ok-2026-11-02)", printed)

    def test_a_waiver_bound_to_another_plan_hash_fails(self):
        built, root = self.build(require_designs=False)
        record = dict(self.good_waiver(root), subject_hash="f" * 64)
        path = self.reseal(root, lambda m: m.update(design_waiver=record))
        fails, _ = self.check({"manifest_path": path}, root)
        self.assertTrue(any("not an owner approval bound to this plan hash" in f for f in fails), fails)

    def test_a_waiver_with_no_owner_identity_fails(self):
        built, root = self.build(require_designs=False)
        record = dict(self.good_waiver(root), owner_identity_ref="")
        path = self.reseal(root, lambda m: m.update(design_waiver=record))
        fails, _ = self.check({"manifest_path": path}, root)
        self.assertTrue(any("not an owner approval bound to this plan hash" in f for f in fails), fails)

    def test_a_label_that_claims_a_waiver_with_no_record_fails(self):
        (fails, _), _ = self.waived(None)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: the delivery label claims designs waived but the "
                      "manifest carries no design_waiver", fails)

    def test_the_old_waiver_key_is_not_a_record(self):
        built, root = self.build(require_designs=False)
        path = self.reseal(root, lambda m: m.update(  # a manifest that carries only the old key and no waiver claim
            designs_waiver={"approval_ref": "owner-ok-2026-11-02"}, design_waiver=None,
            delivery_label=package.DELIVERY_LABELS[package.DELIVERY_SCOPE_FULL]))
        fails, printed = self.check({"manifest_path": path}, root)
        self.assertEqual(fails, [])
        self.assertIn("designs: not checked (designs_required is false)", printed)


class _ClockedS79Validator:
    """Skill 79's validator with `now` supplied, as a production-bound request requires it.

    DEFECT NOT IN THIS LANE (checkout_instances.build calls validate_request(request) with no `now`, so every
    per-offer request of a test_only-false launch is recorded `rejected`: "production-bound request requires
    `now` to check mapping expiry"). This stand-in lets the paid-package checks below be proved against the
    real validator; the missing argument is owned by the checkout lane and needs its own test there.
    """

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def validate_request(self, request, now=None):
        return self._real.validate_request(request, now=now or datetime.datetime.now(datetime.timezone.utc).isoformat())


class PaidPackageTests(PackageCase):
    test_only = False

    def setUp(self):
        super().setUp()
        # the build (checkout_instances) and the check's replay (checks._replay_checkout) both reach Skill 79
        # without `now`; give both the same clocked validator so the record and its replay agree
        clocked = _ClockedS79Validator(substrate.s79_validate_checkout())
        for target, name in ((substrate, "s79_validate_checkout"), (checks, "_load_checkout_validator")):
            patcher = mock.patch.object(target, name, return_value=clocked)
            patcher.start()
            self.addCleanup(patcher.stop)

    def build(self, pieces=None, name="pkg", **kw):
        """A client delivery is assembled from a dispatch that happened (ENF-24, ENF-17).

        The binding to a real dispatch run is proved against real dispatches in test_assemble_binding.py
        (a live run cannot use the free fake consumer: Skill 49's allow-list refuses it). Here the binding
        is a recorded stand-in carrying a good landing bridge receipt, and Skill 49's receipt store is the
        stand-in `store()`, so these tests exercise what `check` holds a paid package to.
        """
        run = self.work / f"dispatch-run-{name}"
        (run / "dispatch").mkdir(parents=True, exist_ok=True)
        (run / "dispatch" / "result-landing.json").write_text("{}", encoding="utf-8")
        (run / "dispatch" / "bridge-receipt-result-landing.json").write_text(json.dumps(
            {"request_id": "req-landing", "draft": False, "receipt_validation": "schema",
             "pipeline_exit": 0}), encoding="utf-8")
        approved = self.normalized["approval"]["hash"]
        # a production launch needs the native product and price ids the Skill 06 read-back returns
        launch = launch_bridge.to_launch_record(self.normalized, self.graph,
                                                {"image_provider": "other_explicit", "design_style": "A"})
        kw.setdefault("checkout_readback", {**TEST_ONLY_CHECKOUT_READBACK, "native": {
            price["price_choice_id"]: {"native_product_id": f"TEST-ONLY-PRODUCT-{offer['offer_id']}",
                                       "native_price_id": f"TEST-ONLY-PRICE-{price['price_choice_id']}"}
            for offer in launch["offers"] for price in offer["prices"]}})
        binding = {"state": package.DISPATCH_STATE_BOUND, "root": run, "plan_document_hash": approved,
                   "requests": {}, "plan_hash_matches": True, "to_confirm": [], "landing_pages": ["landing"],
                   "landing_results": {"landing": run / "dispatch" / "result-landing.json"},
                   "record": {"state": package.DISPATCH_STATE_BOUND, "plan_document_hash": approved}}
        with mock.patch.object(package, "_find_dispatch_root", return_value=(run, True)), \
                mock.patch.object(package, "_bind_dispatch", return_value=binding), \
                mock.patch.object(package, "_bind_piece"), \
                mock.patch.object(package, "_load_receipt_module", return_value=store()):
            return super().build(pieces, name, **kw)

    def proven_paid(self, name="pkg", omit=(), provider="kie"):
        """A paid package that earned its pass: locally verified, L2, independently reviewed, a
        verified receipt store, and live_effects naming the paid renders."""
        pieces = self.pieces(provider=provider, omit=omit)
        for piece in pieces.values():
            piece.update(status="locally_verified", proof_class="L2", independent_review=True,
                         reviewer_session="qc-session-1")
        built, root = self.build(pieces, name=name)

        def carry_reviewer(manifest):
            for piece in manifest["pieces"]:  # package.assemble carries it once U-launcher-core-01 lands
                piece.setdefault("reviewer_session", "qc-session-1")
            make_client_delivery(root, manifest)  # real design files and a closed stage_gate state (STR-25)

        path = self.reseal(root, carry_reviewer)
        paid = checks._paid_image_renders(json.loads(path.read_text(encoding="utf-8")))
        self.edit_receipt(root,  # the writer records the paid renders once U-launcher-core-01 lands
                          live_effects=f"paid_image_renders:{paid}" if paid else "none",
                          receipt_evidence={"state": "verified", "entries": 1})
        close_image_stages(root, json.loads(path.read_text(encoding="utf-8")))
        return {"manifest_path": path, "manifest": built["manifest"]}, root

    def check_with_store(self, built, root, module=None):
        with mock.patch.object(package, "_load_receipt_module", return_value=module or store()):
            return self.check(built, root)

    def test_a_paid_package_with_every_design_kind_passes_with_no_blanket_test_only_assertion(self):
        built, root = self.proven_paid()
        self.assertIs(built["manifest"]["test_only"], False)
        fails, printed = self.check_with_store(built, root)
        self.assertEqual(fails, [])
        self.assertIn("full set (paid package)", printed)

    def test_a_paid_package_missing_a_kind_fails(self):
        built, root = self.proven_paid(omit=["board"])
        fails, _ = self.check_with_store(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing board", fails)

    def test_a_paid_package_with_stub_images_fails_the_provider_consistency_check(self):
        built, root = self.proven_paid(provider="stub")
        fails, _ = self.check_with_store(built, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-MANIFEST: test_only is false but")
                            and "stub provider" in f for f in fails), fails[:3])

    def test_a_paid_package_cannot_skip_designs(self):
        built, root = self.build(self.pieces(provider="kie"), require_designs=False)
        self.assertIs(built["manifest"]["designs_required"], False)
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: designs are never waived for a client delivery "
                      "(test_only false); a paid package carries the full design set", fails)

    def test_a_valid_design_waiver_does_not_open_a_client_delivery(self):
        built, root = self.build(self.pieces(provider="kie"), require_designs=False)
        plan_hash = built["manifest"]["approved_plan_hash"]
        path = self.reseal(root, lambda m: m.update(
            design_waiver={"approval_ref": "owner-ok-2026-11-02", "owner_identity_ref": "client-test-1",
                           "subject_hash": plan_hash}, delivery_label="designs waived"))
        fails, _ = self.check({"manifest_path": path}, root)
        self.assertTrue(any("designs are never waived for a client delivery" in f for f in fails), fails)

    def test_a_paid_package_of_authored_pieces_fails_the_proof_floor(self):
        built, root = self.build(self.pieces(provider="kie"))
        fails, _ = self.check_with_store(built, root)
        floor = [f for f in fails if f.startswith("AF-LAUNCH-PKG-PROOF-FLOOR")]
        self.assertIn("AF-LAUNCH-PKG-PROOF-FLOOR: landing status authored is below locally_verified", floor)
        self.assertIn("AF-LAUNCH-PKG-PROOF-FLOOR: landing proof_class L0 is below L2", floor)
        self.assertIn("AF-LAUNCH-PKG-PROOF-FLOOR: landing has no independent review record", floor)

    def test_a_proven_paid_package_has_no_proof_floor_violation(self):
        built, root = self.proven_paid()
        fails, _ = self.check_with_store(built, root)
        self.assertEqual([f for f in fails if "PROOF-FLOOR" in f], [])

    def test_a_test_package_is_not_held_to_the_client_proof_floor(self):
        self.assertEqual([f for f in checks._proof_floor_violations(
            {"test_only": True, "pieces": [{"role": "landing", "status": "authored", "proof_class": "L0",
                                           "independent_review": False}]})], [])

    def test_a_status_that_is_not_a_page_status_fails_the_floor(self):
        fails = checks._proof_floor_violations(
            {"test_only": False, "pieces": [{"role": "landing", "status": "shipped", "proof_class": "L2",
                                            "independent_review": True, "reviewer_session": "s"}]})
        self.assertEqual(fails, ["AF-LAUNCH-PKG-PROOF-FLOOR: landing status shipped is not a page status"])

    def test_a_paid_package_with_no_receipt_store_fails_naming_the_recorded_state(self):
        built, root = self.build(self.pieces(provider="kie"))
        self.edit_receipt(root, receipt_evidence={"state": "absent", "entries": 0})
        fails, _ = self.check(built, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT: client delivery requires a verified "
                                         "Skill 49 receipt store, recorded state is ") for f in fails), fails)

    def test_a_recorded_verified_state_is_not_trusted_without_the_live_store(self):
        built, root = self.proven_paid()
        for module, text in ((None, "Skill 49 receipt module unavailable"),
                             (types.SimpleNamespace(), "has no verify_delivery_store"),
                             (store(False, "AF-RECEIPT-UNSIGNED: no signature"), "AF-RECEIPT-UNSIGNED")):
            with mock.patch.object(package, "_load_receipt_module", return_value=module):
                fails, _ = self.check(built, root)
            self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT") and text in f for f in fails),
                            (text, fails))

    def test_a_paid_package_with_a_verified_store_has_no_receipt_violation(self):
        built, root = self.proven_paid()
        fails, _ = self.check_with_store(built, root)
        self.assertEqual([f for f in fails if f.startswith("AF-LAUNCH-PKG-RECEIPT")], [])

    def test_the_receipt_must_name_the_paid_renders(self):
        built, root = self.proven_paid()
        self.edit_receipt(root, live_effects="none")
        fails, _ = self.check_with_store(built, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-RECEIPT: receipt live_effects 'none' does not "
                                         "match the package's paid picture renders ('paid_image_renders:")
                            for f in fails), fails)


class LiveEffectsTests(PackageCase):
    def test_a_stub_package_records_no_live_effects(self):
        built, root = self.build()
        self.assertEqual([f for f in self.check(built, root)[0] if "live_effects" in f], [])

    def test_paid_renders_claimed_on_a_stub_package_fail(self):
        built, root = self.build()
        self.edit_receipt(root, live_effects="paid_image_renders:1")
        fails, _ = self.check(built, root)
        self.assertTrue(any("live_effects 'paid_image_renders:1' does not match" in f for f in fails), fails)


class ReviewRecordTests(PackageCase):
    def test_a_claimed_independent_review_with_no_reviewer_fails_in_every_scope(self):
        built, root = self.build()
        path = self.reseal(root, lambda m: m["pieces"][0].update(independent_review=True,
                                                                  reviewer_session=None))
        fails, _ = self.check({"manifest_path": path}, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-REVIEW: ") and "no reviewer_session" in f
                            for f in fails), fails)


class ToConfirmTests(PackageCase):
    ENTRY = {"field": "image_plan.design_style", "reason": "defaulted", "how_to_change": "say A, B or C"}

    def test_an_unconfirmed_default_blocks_the_check_until_a_record_names_it(self):
        built, root = self.build(to_confirm=[dict(self.ENTRY)])
        fails, _ = self.check(built, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-TO-CONFIRM: 'image_plan.design_style'") for f in fails), fails)
        (root / checks.TO_CONFIRM_RECORD).write_text(json.dumps({"confirmations": [
            {"field": "image_plan.design_style", "confirmation_ref": "client-reply-2026-11-02"}]}),
            encoding="utf-8")
        self.assertEqual(self.check(built, root)[0], [])

    def test_a_confirmation_with_no_reference_does_not_count(self):
        built, root = self.build(to_confirm=[dict(self.ENTRY)])
        (root / checks.TO_CONFIRM_RECORD).write_text(json.dumps({"confirmations": [
            {"field": "image_plan.design_style", "confirmation_ref": " "}]}), encoding="utf-8")
        self.assertTrue(any("AF-LAUNCH-TO-CONFIRM" in f for f in self.check(built, root)[0]))

    def test_a_default_hidden_from_the_manifest_is_caught_by_the_dispatch_report(self):
        built, root = self.build()
        (root / checks.DISPATCH_REPORT).write_text(json.dumps({"to_confirm": [dict(self.ENTRY)],
                                                               "landing_pages": ["landing"]}), encoding="utf-8")
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-TO-CONFIRM: the dispatch report lists default "
                      "'image_plan.design_style' that the package manifest does not carry", fails)

    def test_a_planned_sales_page_that_was_never_built_is_caught_by_the_dispatch_report(self):
        built, root = self.build()
        (root / checks.DISPATCH_REPORT).write_text(json.dumps({"to_confirm": [],
                                                               "landing_pages": ["landing", "sales"]}), encoding="utf-8")
        fails, _ = self.check(built, root)
        self.assertTrue(any("no signature sales page piece" in f for f in fails), fails)


class RouteGraphTests(PackageCase):
    def test_a_manifest_without_its_upsell_piece_fails(self):
        built, root = self.build()
        self.assertEqual(self.check(built, root)[0], [])
        manifest_path = self.reseal(root, lambda m: m.update(
            pieces=[p for p in m["pieces"] if p["role"] != "upsell_1"]))
        fails, _ = self.check({"manifest_path": manifest_path}, root)
        self.assertIn("AF-LAUNCH-PKG-MISSING-ROLE: route node 'upsell_1' has no delivered piece in the "
                      "package manifest", fails)

    def test_a_manifest_without_its_second_upsell_piece_fails(self):
        built, root = self.build()
        manifest_path = self.reseal(root, lambda m: m.update(
            pieces=[p for p in m["pieces"] if p["role"] != "upsell_2"]))
        fails, _ = self.check({"manifest_path": manifest_path}, root)
        self.assertTrue(any("route node 'upsell_2'" in f for f in fails), fails)

    def test_a_carried_graph_missing_a_doc_02_edge_fails_the_check(self):
        built, root = self.build()
        graph = json.loads((root / "route-graph.json").read_text(encoding="utf-8"))
        graph["edges"] = [e for e in graph["edges"] if e["event"] != "explicit_decline"][:]
        (root / "route-graph.json").write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n",
                                               encoding="utf-8")
        manifest_path = self.reseal(root, lambda m: m["route_graph"].update(
            sha256=sha(root / "route-graph.json")))
        fails, _ = self.check({"manifest_path": manifest_path}, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-ROUTE-LAW: missing contract edges") for f in fails), fails)

    def test_an_intact_graph_holds_the_law(self):
        built, root = self.build()
        graph = json.loads((root / "route-graph.json").read_text(encoding="utf-8"))
        record = route.launch_record(json.loads((root / "intake.json").read_text(encoding="utf-8")))
        self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_assemble_refuses_a_compiled_graph_missing_a_doc_02_edge(self):
        compiler = substrate.compiler()
        real = compiler.compile_route

        def drop_an_edge(launch):
            graph = copy.deepcopy(real(launch))
            graph["edges"] = graph["edges"][1:]
            return graph

        law_errors = (route_law.RouteInvariantError, route.RouteError)
        with mock.patch.object(compiler, "compile_route", drop_an_edge):
            with self.assertRaises(law_errors) as ctx:
                route.compile_route(self.normalized)
            self.assertIn("missing contract edges", str(ctx.exception))
            intake_file = self.work / "intake.json"
            intake_file.write_text(json.dumps(json.loads(
                (FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))), encoding="utf-8")
            pieces_dir = self.work / "pieces-in"
            pieces_dir.mkdir()
            stderr = io.StringIO()
            with mock.patch.object(cli.council, "planning_step", return_value=COUNCIL):
                try:
                    with contextlib.redirect_stderr(stderr):
                        rc = cli.main(["assemble", "--intake", str(intake_file), "--pieces", str(pieces_dir),
                                       "--out", str(self.work / "out"), "--page-only"])
                except route_law.RouteInvariantError as exc:  # before route.compile_route wraps it
                    self.assertIn("missing contract edges", str(exc))
                else:  # the CLI contract: exit 2 and name the law
                    self.assertEqual(rc, 2)
                    self.assertIn("missing contract edges", stderr.getvalue())
        self.assertFalse((self.work / "out" / "package-manifest.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
