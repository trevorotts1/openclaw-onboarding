"""RFX-007 B3 and B5: a draft launch carries only the named not-installed blockers, and every email unit seals.

B3. The page producers attach standing blockers to every design-time result that mean only "not installed by
Skill 06 yet" (the checkout wrapper's two BLOCKERS, Skill 80's S80-06 binding note, the thank-you translator's
THANK-YOU-RUNTIME-NOT-INSTALLED). ``assemble --launch-plan`` refused every one, so no draft launch could ever be
packaged. A draft_constructed package now carries exactly those, by name, open by design; every other blocker,
and any of these on an installed or published package, still refuses.

B5. ``_lane_receipt`` dropped each artifact's ``role``, and every Skill 50 run names its files by the same
run-relative paths, so Skill 50's ``validate_delivery.py --check`` could find the roles only at fixed root paths
and at most one email sequence could be sealed. The role is now carried and each lane unit is sealed under its
own ``lanes/<unit id>/`` prefix. The four-unit test runs Skill 50's REAL validator.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checks, constants, council, intake, launch_plan, package, route  # noqa: E402
from launcher_core.check_rules import delivery_units as du  # noqa: E402
from test_delivery_units import (EMAIL_VALIDATOR_PATH, install_stand_in_validator,  # noqa: E402
                                 with_sales_piece)
from test_launch_plan_law import (lane_deliveries, pieces_for, plan_fixture, plan_intake,  # noqa: E402
                                  stub_council)

CODE = "AF-LAUNCH-PKG-BLOCKERS"
GOLDEN = REPO_ROOT / "50-email-engine" / "examples" / "golden-landing-10"
EMAIL_VALIDATOR = REPO_ROOT / EMAIL_VALIDATOR_PATH


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def producer_blockers() -> dict:
    """role -> the standing blockers the REAL producer modules attach at design time (never typed here)."""
    checkout = _load("49-signature-funnel/scripts/checkout_wrapper.py", "rfx7_checkout_wrapper")
    thanks = _load("49-signature-funnel/scripts/translate_thank_you_result.py", "rfx7_thank_you")
    adapters = REPO_ROOT / "80-signature-upsell" / "components" / "adapters"
    sys.path.insert(0, str(adapters))
    try:
        common = _load("80-signature-upsell/components/adapters/adapter_common.py", "rfx7_adapter_common")
    finally:
        sys.path.remove(str(adapters))
    s80 = next(b for b in common.build_result.__code__.co_consts
               if isinstance(b, str) and b.startswith("S80-06 extra-offer binding"))
    return {"checkout": list(checkout.BLOCKERS), "upsell_1": [s80], "upsell_2": [s80],
            "thank_you": [thanks.DESIGN_BLOCKER, thanks.DESIGN_BLOCKER_TEXT]}


class Launch(unittest.TestCase):
    """A full Black Friday launch: every planned page, email, text and automation delivered."""

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

    def with_standing_blockers(self, extra=None):
        pieces = copy.deepcopy(self.pieces)
        for role, blockers in producer_blockers().items():
            if role in pieces:
                pieces[role]["blockers"] = list(blockers)
        for role, blocker in (extra or {}).items():
            pieces[role]["blockers"].append(blocker)
        return pieces

    def binding(self) -> dict:
        """A recorded dispatch binding (a real one needs Skill 49's signed live store, which is proved in
        test_assemble_binding.py). With it, package._activation itself derives draft_constructed."""
        run = Path(self.tmp.name) / "dispatch-run"
        (run / "dispatch").mkdir(parents=True, exist_ok=True)
        (run / "dispatch" / "result-landing.json").write_text("{}", encoding="utf-8")
        (run / "dispatch" / "bridge-receipt-result-landing.json").write_text(json.dumps(
            {"request_id": "req-landing", "draft": False, "receipt_validation": "schema", "pipeline_exit": 0}),
            encoding="utf-8")
        approved = self.normalized["approval"]["hash"]
        return {"state": package.DISPATCH_STATE_BOUND, "root": run, "plan_document_hash": approved,
                "requests": {}, "plan_hash_matches": True, "to_confirm": [], "landing_pages": ["landing"],
                "landing_results": {"landing": run / "dispatch" / "result-landing.json"},
                "record": {"state": package.DISPATCH_STATE_BOUND, "plan_document_hash": approved}}

    def assemble(self, pieces, stage="draft_constructed"):
        intake_doc, readback = self.normalized, None
        if stage in ("installed", "published"):  # a recorded authority and an observed read-back reach it
            intake_doc = {**self.normalized, "activation": {"desired_state": stage, "authority": {
                "ref": "TEST-ONLY-AUTHORITY", "scope": {"installed": "installation"}.get(stage, "publication"),
                "location_id": self.normalized["location_id"]}}}
            readback = {"stage": stage, "source": "GET /funnels/page/TEST-ONLY-PAGE", "page_id": "TEST-ONLY-PAGE",
                        "page_url": "https://example.com/test-only", "observed_at": "2026-11-23T12:00:00Z",
                        "page_type": "published", "page_version": 1,
                        "install": {"native_product_id": "TEST-ONLY-PRODUCT"}}
        binding = self.binding()
        store = mock.Mock(verify_delivery_store=mock.Mock(return_value=(True, "verified")),
                          load=mock.Mock(return_value=[{"phase": "pages"}]),
                          store_state=mock.Mock(return_value="present"))
        waiver = {"approval_ref": "TEST-ONLY-WAIVER", "subject_type": "design_waiver", "revoked": False,
                  "subject_hash": binding["plan_document_hash"], "owner_identity_ref": "TEST-ONLY-OWNER"}
        with mock.patch.object(package, "_find_dispatch_root", return_value=(binding["root"], True)), \
                mock.patch.object(package, "_bind_dispatch", return_value=binding), \
                mock.patch.object(package, "_bind_piece"), \
                mock.patch.object(package, "_load_receipt_module", return_value=store):
            return package.assemble(self.run_dir, intake_doc, self.graph, pieces, council=self.advice,
                                    launch_plan=self.plan, deliveries=self.deliveries,
                                    require_designs=False, design_waiver=waiver,  # these fixture pages carry no designs
                                    activation_readback=readback)

    def refused(self, pieces, stage="draft_constructed"):
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(pieces, stage)
        self.assertEqual(ctx.exception.code, CODE, ctx.exception)
        self.assertFalse((self.run_dir / "receipt.json").exists(), "a refused package seals nothing")
        return ctx.exception.detail


class DraftBlockerTests(Launch):
    def test_the_producers_still_attach_every_allow_listed_text(self):
        # Lockstep: a reworded producer blocker would otherwise drop off the allow-list unnoticed.
        for role, blockers in producer_blockers().items():
            for text in blockers:
                with self.subTest(role=role, text=text[:40]):
                    self.assertIn(text, package.OPEN_BY_DESIGN_BLOCKERS)
                    self.assertIn(role, package.OPEN_BY_DESIGN_BLOCKERS[text][1])

    def test_a_draft_launch_with_only_the_named_not_installed_blockers_assembles_and_checks_clean(self):
        out = self.assemble(self.with_standing_blockers())
        want = [{"slot": "checkout", "role": "checkout",
                 "names": ["CHECKOUT-NATIVE-FORM-NOT-INSTALLED", "CHECKOUT-BOARD-AWAITS-CLIENT-APPROVAL"]}]
        roles = {p["role"] for p in out["manifest"]["pieces"]}
        if "upsell_1" in roles:
            want.append({"slot": "upsell_1", "role": "upsell_1", "names": ["S80-06-BINDING-NOT-INSTALLED"]})
        if "thank_you" in roles:
            want.append({"slot": "thank_you", "role": "thank_you", "names": ["THANK-YOU-RUNTIME-NOT-INSTALLED"]})
        for record in (out["manifest"], out["receipt"]):
            self.assertEqual(sorted(record["open_by_design_blockers"], key=lambda r: r["slot"]),
                             sorted(want, key=lambda r: r["slot"]))
            self.assertTrue(record["delivery_label"].startswith("design-only"))
            self.assertEqual(record["delivery_scope"], package.DELIVERY_SCOPE_FULL)
        self.assertEqual(out["manifest"]["activation"]["achieved_state"], "draft_constructed")
        self.assertEqual(out["manifest"]["dispatch_binding"]["state"], package.DISPATCH_STATE_BOUND)
        self.assertEqual(checks.check_package(Path(out["manifest_path"]), self.run_dir), [])

    def test_the_same_blockers_refuse_a_full_launch_with_no_dispatch_run(self):
        # local_prepared (no dispatch happened) is not a draft: the allow-list does not apply to it.
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, self.with_standing_blockers(),
                             council=self.advice, launch_plan=self.plan, deliveries=self.deliveries)
        self.assertEqual(ctx.exception.code, CODE)
        self.assertIn("local_prepared", ctx.exception.detail)

    def test_an_unlisted_blocker_still_refuses_a_draft_launch(self):
        for role, text in (("checkout", "checkout images are placeholders"),
                           ("upsell_1", "copy_validation not_run: the copy validator could not be run"),
                           ("thank_you", "REVIEW-PENDING: no accepted independent review")):
            with self.subTest(role=role):
                detail = self.refused(self.with_standing_blockers({role: text}))
                self.assertIn(text, detail)
                self.assertIn(role, detail)

    def test_a_named_blocker_on_another_page_is_not_open_by_design(self):
        pieces = self.with_standing_blockers()
        pieces["landing"]["blockers"] = list(producer_blockers()["thank_you"])
        self.assertIn("landing", self.refused(pieces))

    def test_an_installed_or_published_package_with_a_named_blocker_still_refuses(self):
        for stage in ("installed", "published"):
            with self.subTest(stage=stage):
                detail = self.refused(self.with_standing_blockers(), stage=stage)
                self.assertIn(stage, detail)
                self.assertIn("native checkout form is installed by Skill 06", detail)

    def test_check_refuses_a_sealed_draft_whose_blockers_or_names_were_edited(self):
        out = self.assemble(self.with_standing_blockers())
        path = Path(out["manifest_path"])
        manifest = json.loads(path.read_text(encoding="utf-8"))

        def reseal(edit):
            doc = copy.deepcopy(manifest)
            edit(doc)
            path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return [f for f in checks.check_package(path, self.run_dir) if f.startswith(CODE)]

        def add_unlisted(doc):
            next(p for p in doc["pieces"] if p["role"] == "checkout")["blockers"].append("hand-added")
        self.assertTrue(any("hand-added" in f for f in reseal(add_unlisted)))
        self.assertTrue(any("installed" in f for f in reseal(
            lambda doc: doc["activation"].update(achieved_state="installed"))))
        self.assertTrue(any("open_by_design_blockers" in f for f in reseal(
            lambda doc: doc.update(open_by_design_blockers=[]))))


class FourEmailUnitsTests(unittest.TestCase):
    """B5 with Skill 50's REAL validate_delivery.py: four email runs, one package, every unit seals."""

    UNITS = ("email_pre_launch", "email_main_launch", "email_doors_closing", "email_welcome_access")
    # the plan's other email sequences are real Skill 50 runs too, so the real validator judges every one
    OTHERS = ("email_upsell_1", "email_downsell_1", "email_abandoned_checkout")

    def setUp(self):
        if not (GOLDEN.is_dir() and EMAIL_VALIDATOR.is_file()):
            self.skipTest("Skill 50's validator or its golden run is not installed beside this skill")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(plan_intake())
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.pieces = with_sales_piece(pieces_for(self.run_dir, self.graph, self.normalized),
                                       self.run_dir, self.normalized)
        self.plan = plan_fixture()
        for seq in self.plan["email_sequences"]:
            if seq["id"] in self.UNITS + self.OTHERS:
                seq["email_count"] = 10  # one golden 10-email run per unit, produced for real below
        self.deliveries = lane_deliveries(self.plan, self.run_dir)
        plan_path = Path(self.tmp.name) / "plan.json"
        plan_path.write_text(json.dumps(self.plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertEqual({s["id"] for s in self.plan["email_sequences"]}, set(self.UNITS + self.OTHERS))
        for unit in self.UNITS + self.OTHERS:  # every run names its files by the SAME run-relative paths
            run = self.run_dir / "email-runs" / unit
            shutil.copytree(GOLDEN, run)
            receipt = run / "receipt.json"
            done = subprocess.run([sys.executable, "-I", str(EMAIL_VALIDATOR), str(run), "--launch-plan",
                                   str(plan_path), "--unit", unit, "--out", str(receipt)],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            row = json.loads(receipt.read_text(encoding="utf-8"))
            for art in row["artifacts"]:
                art["path"] = f"email-runs/{unit}/{art['path']}"
            self.deliveries[unit] = row
            # the signing key is a run secret; it is never staged with a package
            (run / "working" / "checkpoints" / ".cert-hmac-key").unlink()
        real = constants.resolve_ref  # the REAL Skill 50 validator, not the stand-in
        patcher = mock.patch.object(constants, "resolve_ref",
                                    lambda rel, root=None: EMAIL_VALIDATOR if rel == EMAIL_VALIDATOR_PATH
                                    else real(rel, root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_four_email_units_each_seal_and_pass_the_real_check(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces, council=self.advice,
                               launch_plan=self.plan, deliveries=self.deliveries)
        rows = {r["unit_id"]: r for r in out["receipt"]["units"]}
        for unit in self.UNITS:
            with self.subTest(unit=unit):
                arts = rows[unit]["artifacts"]
                self.assertEqual({a["role"] for a in arts}, {"build_plan", "emails", "brief", "certificate"})
                self.assertTrue(all(a["path"].startswith(f"lanes/{unit}/") for a in arts), arts)
                self.assertEqual(du.email_delivery_violations(unit, du.lane_document(unit, rows[unit]),
                                                              self.run_dir), [])
        self.assertEqual(checks.check_package(Path(out["manifest_path"]), self.run_dir), [])

    def test_a_tampered_email_file_in_one_unit_fails_that_unit_only(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces, council=self.advice,
                               launch_plan=self.plan, deliveries=self.deliveries)
        unit = self.UNITS[2]
        emails = next(a for a in out["receipt"]["units"] if a["unit_id"] == unit)["artifacts"]
        target = self.run_dir / next(a["path"] for a in emails if a["role"] == "emails")
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        fails = [f for f in checks.check_package(Path(out["manifest_path"]), self.run_dir)
                 if "delivery validator refused" in f]
        self.assertEqual(len(fails), 1, fails)
        self.assertIn(unit, fails[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
