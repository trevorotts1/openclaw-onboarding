"""U-images-01: paid image spend needs a verified paid_asset_budget approval (ENF-05), a defaulted style
is never paid for (IMG-08), an unconfirmed palette is never paid for (IMG-09).

Free: nothing here calls a provider or Command Center. The approval verifier is faked at the one seam
(image_plan._approval_verify); a free-text reference, a falsy test_only, a default style or a default
palette must each stop before allow_paid can be True.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

from launcher_core import image_plan  # noqa: E402
from launcher_core.image_plan import ImagePlanError, resolve  # noqa: E402

PLAN_HASH = "a" * 64
APPROVAL_ID = "appr_budget_0001"


def ok_record(**over):
    rec = {"ok": True, "approval_id": APPROVAL_ID, "kind": "paid_asset_budget", "plan_hash": PLAN_HASH,
           "client_identity": "TEST-ONLY", "scope": ["paid_asset_budget"], "expires_at": "2999-01-01T00:00:00Z",
           "authority": "command-center", "test_only": False}
    rec.update(over)
    return rec


class PaidSpendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.brand = self.write_brand({"palette_status": "provided"})

    def write_brand(self, doc, name="brand.json"):
        path = self.tmp / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def raw(self, **over):
        raw = {"brand_file": self.brand, "brand_owner": "TEST-ONLY Client", "design_style": "B", "image_provider": "kie",
               "image_cap_minor": 4000, "image_currency": "USD", "paid_render_approval_ref": APPROVAL_ID}
        raw.update(over)
        return raw

    def paid(self, raw=None, verifier=None, **kw):
        verifier = verifier or mock.Mock(return_value=ok_record())
        kw.setdefault("plan_hash", PLAN_HASH)
        with mock.patch.object(image_plan, "_approval_verify", return_value=verifier):
            return resolve(self.raw() if raw is None else raw, test_only=False, **kw), verifier

    def refused(self, code, raw=None, **kw):
        with self.assertRaises(ImagePlanError) as ctx:
            self.paid(raw, **kw)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    # ---- ENF-05: test_only is a real bool; a free-text ref is not an approval -------------------
    def test_a_falsy_or_untyped_test_only_never_reaches_a_paid_run(self):
        for bad in (None, 0, "", [], "false", 1):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(), test_only=bad, plan_hash=PLAN_HASH)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-TEST-ONLY", repr(bad))

    def test_a_free_text_approval_ref_cannot_reach_allow_paid(self):
        def refuse(*_a, **_k):
            raise RuntimeError("no such approval in Command Center")
        err = self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", self.raw(paid_render_approval_ref="ok"),
                           verifier=refuse)
        self.assertIn("nothing has been spent", err.detail.lower())

    def test_with_no_approval_checker_installed_a_paid_run_fails_closed(self):
        with mock.patch.object(image_plan.Path, "is_file", return_value=False):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(), test_only=False, plan_hash=PLAN_HASH)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-APPROVAL")

    def test_the_real_verifier_refuses_a_made_up_reference(self):
        try:
            image_plan._approval_verify()
        except ImagePlanError:
            return  # checker not in this checkout: already proven to fail closed above
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(paid_render_approval_ref="ok"), test_only=False, plan_hash=PLAN_HASH)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-APPROVAL")

    def test_a_record_that_is_not_from_command_center_or_not_a_budget_is_refused(self):
        for rec in (ok_record(authority="local-test-record"), ok_record(kind="launch_plan_build"),
                    ok_record(approval_id="someone_else_1"), ok_record(ok=1), {}):
            self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", verifier=mock.Mock(return_value=rec))

    def test_a_paid_run_without_the_plan_hash_is_refused(self):
        self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", plan_hash=None)
        self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", plan_hash="  ")

    def test_a_verified_budget_allows_paid_and_reports_the_derived_picture_ceiling(self):
        (inputs, to_confirm), verifier = self.paid()
        price = image_plan.IMAGE_PRICE_MINOR["kie"]["USD"]
        self.assertTrue(inputs["allow_paid"])
        self.assertEqual(inputs["executor_provider"], "kie")
        self.assertEqual(inputs["paid_approval_id"], APPROVAL_ID)
        self.assertEqual((inputs["image_cap_minor"], inputs["image_currency"], inputs["image_price_minor"]),
                         (4000, "USD", price))
        self.assertEqual(inputs["image_cap"], 4000 // price)  # the picture ceiling, derived from the money
        self.assertEqual(to_confirm, [])
        args, kwargs = verifier.call_args
        self.assertEqual(args[1:3], ("paid_asset_budget", PLAN_HASH))
        self.assertEqual(kwargs["cap"], {"cap_minor": 4000, "currency": "USD"})
        self.assertIs(kwargs["test_only"], False)

    def test_the_spend_is_money_not_a_picture_count(self):
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", {k: v for k, v in self.raw().items()
                                                  if k not in ("image_cap_minor", "image_currency")} | {"image_cap": 50})
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_cap_minor=None))
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_currency="XYZ"))  # no price row: never guessed
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_cap_minor=3))     # not even one picture
        ceiling = 4000 // image_plan.IMAGE_PRICE_MINOR["kie"]["USD"]
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_cap=ceiling + 1))
        (inputs, _), _v = self.paid(self.raw(image_cap=ceiling - 1))
        self.assertEqual(inputs["image_cap"], ceiling - 1)

    def test_bad_money_values_are_named(self):
        for over in ({"image_cap_minor": True}, {"image_cap_minor": 0}, {"image_cap_minor": "40"},
                     {"image_currency": "usd"}, {"image_currency": 5}):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(**over), test_only=True)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-CAP", over)

    def test_a_practice_run_needs_no_approval_and_never_spends(self):
        verifier = mock.Mock()
        with mock.patch.object(image_plan, "_approval_verify", return_value=verifier):
            inputs, _ = resolve({"brand_file": "/nope.json", "brand_owner": "X"}, test_only=True)
        self.assertEqual((inputs["executor_provider"], inputs["allow_paid"]), ("stub", False))
        self.assertIsNone(inputs["paid_approval_id"])
        verifier.assert_not_called()

    # ---- IMG-24: an Agnes plan resolves and draws placeholders only -----------------------------
    def test_an_agnes_plan_resolves_and_draws_one_stub_section(self):
        inputs, _ = image_plan.resolve({"brand_file": self.brand, "brand_owner": "TEST-ONLY Client",
                                        "design_style": "A", "image_provider": "agnes"}, test_only=True)
        self.assertEqual(inputs["executor_provider"], "stub")
        self.assertIs(inputs["allow_paid"], False)
        self.assertEqual(image_plan.image_inputs_file(inputs)["image_provider"], "stub")
        sys.path.insert(0, str(SKILL_ROOT.parent / "71-blackceo-signature-page" / "tests"))
        import board_fixture as bf  # noqa: E402  (Skill 71's own run fixture)
        executor = SKILL_ROOT.parent / "71-blackceo-signature-page" / "scripts" / "stage_executor.py"
        run_dir = self.tmp / "agnes-run"
        run_dir.mkdir()
        bf.make_run(run_dir, base_request={"model": "STUB-NO-MODEL", "sections": [
            {"section_id": "hero", "section_name": "Hero", "copy": "New copy one.",
             "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9", "art_direction": "Window light."}]}]})
        proc = subprocess.run([sys.executable, str(executor), str(run_dir), "--provider", inputs["executor_provider"],
                               "--stages", "desktop-wireframe"], capture_output=True, text=True, env=bf.subprocess_env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        drawn = run_dir / "desktop-wireframe" / "section-01.png"
        self.assertEqual(drawn.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        record = json.loads((run_dir / "desktop-wireframe" / "stage-executor-record.json").read_text(encoding="utf-8"))
        self.assertEqual(record["provider"], "stub")

    # ---- IMG-08: a defaulted style is never paid for -------------------------------------------
    def test_a_paid_run_with_no_style_stops_until_the_client_picks_a_b_or_c(self):
        for raw in (self.raw(design_style=None), self.raw(design_style="not sure"),
                    self.raw(design_style="B", design_style_source="default_to_confirm")):
            verifier = mock.Mock(return_value=ok_record())
            self.refused("AF-LAUNCH-IMAGE-PLAN-STYLE", raw, verifier=verifier)
            verifier.assert_not_called()  # stopped before any approval lookup, nothing spent
        (inputs, _), _v = self.paid(self.raw(design_style="C", design_style_source="client_choice"))
        self.assertEqual((inputs["design_style"], inputs["design_style_source"]), ("C", "client_choice"))

    def test_a_defaulted_style_stays_flagged_and_is_never_called_a_client_choice_on_a_practice_run(self):
        inputs, to_confirm = resolve(self.raw(design_style="B", design_style_source="default_to_confirm"),
                                     test_only=True)
        self.assertEqual(inputs["design_style_source"], "default_to_confirm")
        self.assertIn("image_plan.design_style", {r["field"] for r in to_confirm})
        with self.assertRaises(ImagePlanError):
            resolve(self.raw(design_style_source="made_up"), test_only=True)

    # ---- IMG-09: an unconfirmed palette is never paid for --------------------------------------
    def test_a_paid_run_refuses_a_suggested_or_default_palette(self):
        for status in ("default_to_confirm", "suggested", "", None, "made_up"):
            brand = self.write_brand({"palette_status": status}, f"b-{status}.json")
            err = self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=brand))
            self.assertIn("nothing has been spent", err.detail.lower())
        self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=str(self.tmp / "missing.json")))
        self.write_brand([], "list.json")
        self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=str(self.tmp / "list.json")))

    def test_a_confirmed_or_legacy_palette_passes_and_a_practice_run_is_not_checked(self):
        for doc in ({"palette_status": "provided"}, {"palette_status": "client-confirmed"}, {}):
            brand = self.write_brand(doc, "ok.json")
            (inputs, _), _v = self.paid(self.raw(brand_file=brand))
            self.assertTrue(inputs["allow_paid"])
        bad = self.write_brand({"palette_status": "default_to_confirm"}, "d.json")
        inputs, _ = resolve(self.raw(brand_file=bad), test_only=True)
        self.assertFalse(inputs["allow_paid"])

    # ---- the shared file carries the style source and the creative direction -------------------
    def test_design_style_source_and_creative_direction_travel_in_the_shared_file(self):
        inputs, _ = resolve(self.raw(creative_direction="like the Acme homepage"), test_only=True)
        self.assertEqual(inputs["creative_direction"], "like the Acme homepage")
        takes_all = SimpleNamespace(dispatch=lambda: SimpleNamespace(pset=SimpleNamespace(
            IMAGE_INPUT_KEYS=image_plan.C3_KEYS + image_plan.C3_CARRIED_KEYS)))
        with mock.patch.dict(sys.modules, {"substrate": takes_all}):
            doc = image_plan.image_inputs_file(inputs)
        self.assertEqual(doc["design_style_source"], "client_choice")
        self.assertEqual(doc["creative_direction"], "like the Acme homepage")
        takes_base = SimpleNamespace(dispatch=lambda: SimpleNamespace(pset=SimpleNamespace(
            IMAGE_INPUT_KEYS=image_plan.C3_KEYS)))
        with mock.patch.dict(sys.modules, {"substrate": takes_base}):  # Skill 49 refuses unknown keys
            self.assertEqual(sorted(image_plan.image_inputs_file(inputs)), sorted(image_plan.C3_KEYS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
