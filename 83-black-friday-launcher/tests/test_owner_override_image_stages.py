"""SWB-096: the owner override for the Skill 71 image stages of named pages (scope image_stages).

Separate from the page_designs override: another record kind, another signed field set, and it names the
package run id and the exact pages it covers. Every positive has a negative twin on the same instrument.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import secrets
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checks, owner_override  # noqa: E402
from launcher_core.cli import build_parser  # noqa: E402

PLAN = "b" * 64
PKG = "package-8"
ROLES = ["upsell_1", "upsell_2", "downsell_1"]
WORDS = ["finish ALL THE WORK NOW", "I CAN BYPASS ANY MOTHERFUCKINTHING I WANT"]


def _rule():
    path = SKILL_ROOT / "launcher_core" / "check_rules" / "image_qc.py"
    spec = importlib.util.spec_from_file_location("image_qc_for_swb096", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "operator.key"
        self.key.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        self.key.chmod(0o600)
        patcher = mock.patch.dict(os.environ, {"SF_OPERATOR_KEY_FILE": str(self.key)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = Path(self.tmp.name) / PKG
        (self.root / "qc").mkdir(parents=True)

    def record(self, plan=PLAN, package=PKG, roles=ROLES, **kw):
        return owner_override.mint_image_stages(plan, package, list(roles), kw.pop("words", WORDS), note="test")

    def manifest(self, record, planned=("landing", "checkout", "upsell_1", "upsell_2", "downsell_1")):
        return {"test_only": False, "approved_plan_hash": PLAN,
                "pieces": [{"role": r, "page_id": r, "slot": r} for r in planned],
                "owner_override_image_stages": record}

    def write_report(self, roles):
        rows = [{"role": r, "page_key": r, "status": "missing_page",
                 "reason": "no Skill 71 run folder for it was found"} for r in roles]
        (self.root / "qc" / "image_stages_report.json").write_text(
            json.dumps({"pages": rows, "expected_pages_state": "known"}), encoding="utf-8")


class MintVerifyTests(Base):
    def test_a_minted_record_verifies_for_its_plan_package_and_pages_and_never_carries_the_key(self):
        rec = self.record()
        self.assertEqual(owner_override.verify_image_stages(rec, PLAN, PKG), [])
        self.assertNotIn(self.key.read_text().strip(), json.dumps(rec))
        self.assertEqual(rec["scope"], "image_stages")
        self.assertEqual(rec["page_roles"], ROLES)

    def test_minting_refuses_landing_checkout_thank_you_empty_and_duplicate_roles(self):
        for roles in (["landing"], ["upsell_1", "checkout"], ["thank_you"], [], ["upsell_1", "upsell_1"]):
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                self.record(roles=roles)
        with self.assertRaises(ValueError):
            self.record(package="")
        with self.assertRaises(ValueError):
            self.record(words=[])

    def test_each_negative_twin_is_refused(self):
        good = self.record()
        cases = {
            "unsigned": {k: v for k, v in good.items() if k != "signature"},
            "edited words": dict(good, owner_words=["something else"]),
            "edited roles (an extra page)": dict(good, page_roles=ROLES + ["downsell_2"]),
            "landing added": dict(good, page_roles=ROLES + ["landing"]),
            "forged signature": dict(good, signature="3" * 64),
            "wrong scope": dict(good, scope="page_designs"),
            "wrong kind": dict(good, kind="owner_override"),
        }
        for name, rec in cases.items():
            with self.subTest(name=name):
                self.assertTrue(owner_override.verify_image_stages(rec, PLAN, PKG), name)
        self.assertTrue(owner_override.verify_image_stages(good, "c" * 64, PKG))      # wrong plan hash
        self.assertTrue(owner_override.verify_image_stages(good, PLAN, "package-9"))  # wrong package id
        self.assertTrue(owner_override.verify_image_stages(good, PLAN, ""))
        other = Path(self.tmp.name) / "other.key"
        other.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        other.chmod(0o600)
        with mock.patch.dict(os.environ, {"SF_OPERATOR_KEY_FILE": str(other)}):
            self.assertTrue(owner_override.verify_image_stages(good, PLAN, PKG))      # another key
        with mock.patch.dict(os.environ):
            os.environ.pop("SF_OPERATOR_KEY_FILE")
            self.assertTrue(any("operator key" in f for f in owner_override.verify_image_stages(good, PLAN, PKG)))
            with self.assertRaises(ValueError):
                self.record()                                                          # no key, no record

    def test_a_page_designs_record_never_covers_the_image_stages_and_the_reverse(self):
        designs = owner_override.mint(PLAN, owner_override.SCOPE_PAGE_DESIGNS, WORDS)
        self.assertTrue(owner_override.verify_image_stages(designs, PLAN, PKG))
        self.assertTrue(owner_override.verify(self.record(), PLAN, owner_override.SCOPE_PAGE_DESIGNS))
        with self.assertRaises(ValueError):
            owner_override.mint(PLAN, owner_override.SCOPE_IMAGE_STAGES, WORDS)

    def test_the_cli_writes_a_signed_record_and_prints_no_key(self):
        out = Path(self.tmp.name) / "rec.json"
        args = build_parser().parse_args(["owner-override", "--plan-hash", PLAN, "--scope", "image_stages",
                                          "--package-id", PKG, "--page-role", "upsell_1", "--page-role", "downsell_1",
                                          "--owner-word", WORDS[0], "--out", str(out)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.fn(args), 0)
        self.assertEqual(owner_override.verify_image_stages(json.loads(out.read_text()), PLAN, PKG), [])
        self.assertNotIn(self.key.read_text().strip(), buf.getvalue())


class CheckRuleTests(Base):
    def fails(self, manifest):
        return _rule().violations(manifest, self.root, SKILL_ROOT)

    def stage_fails(self, manifest):
        return [f for f in self.fails(manifest) if "IMAGE-STAGES" in f or "OVERRIDE" in f]

    def test_without_an_override_every_missing_page_is_named(self):
        self.write_report(["landing", *ROLES])
        text = " ".join(self.stage_fails(self.manifest(None)))
        for role in ("landing", *ROLES):
            self.assertIn(role, text)

    def test_a_verified_override_clears_exactly_the_named_pages(self):
        self.write_report(["landing", *ROLES])
        manifest = self.manifest(self.record())
        text = " ".join(self.stage_fails(manifest))
        for role in ROLES:
            self.assertNotIn(role, text)
        self.assertIn("landing", text)  # a page the record does not name is judged as before
        roles, why, banner = owner_override.image_stage_waiver(manifest, PKG)
        self.assertEqual((roles, why), (ROLES, []))
        self.assertEqual(banner, "OWNER OVERRIDE: image stages waived by the owner for upsell_1, upsell_2, "
                                 f"downsell_1 (signed record {manifest['owner_override_image_stages']['signature'][:16]})")

    def test_a_record_naming_only_one_page_clears_only_that_page(self):
        self.write_report(ROLES)
        text = " ".join(self.stage_fails(self.manifest(self.record(roles=["upsell_1"]))))
        self.assertNotIn("upsell_1", text)
        self.assertIn("upsell_2", text)
        self.assertIn("downsell_1", text)

    def test_every_negative_twin_waives_nothing_and_is_named(self):
        self.write_report(ROLES)
        good = self.record()
        bad = {
            "unsigned": {k: v for k, v in good.items() if k != "signature"},
            "edited": dict(good, owner_words=["edited"]),
            "landing added": dict(good, page_roles=ROLES + ["landing"]),
            "wrong package": self.record(package="package-7"),
            "wrong plan": self.record(plan="d" * 64),
        }
        for name, rec in bad.items():
            with self.subTest(name=name):
                fails = self.stage_fails(self.manifest(rec))
                text = " ".join(fails)
                self.assertIn("does not verify", text)
                for role in ROLES:
                    self.assertIn(role, text)
        with mock.patch.dict(os.environ):
            os.environ.pop("SF_OPERATOR_KEY_FILE")
            fails = self.stage_fails(self.manifest(good))
        self.assertTrue(any("operator key" in f for f in fails), fails)
        self.assertIn("upsell_1", " ".join(fails))

    def test_a_record_naming_a_page_the_package_does_not_have_waives_nothing(self):
        self.write_report(["upsell_1"])
        manifest = self.manifest(self.record(), planned=("landing", "upsell_1"))
        text = " ".join(self.stage_fails(manifest))
        self.assertIn("does not verify", text)
        self.assertIn("upsell_1", text)

    def test_an_external_install_package_plans_its_pages_without_launcher_pieces(self):
        """Pages another skill installed carry no piece: the route graph and the install binding plan them."""
        self.write_report(["landing", *ROLES])
        manifest = self.manifest(self.record(), planned=("landing",))
        # only landing is a piece: the three named pages are unknown to the package, so nothing is waived
        self.assertTrue(owner_override.image_stage_waiver(manifest, PKG, root=self.root)[1])
        (self.root / "route-graph.json").write_text(
            json.dumps({"nodes": [{"role": r} for r in ("landing", "checkout", *ROLES)]}), encoding="utf-8")
        self.assertEqual(owner_override.image_stage_waiver(manifest, PKG, root=self.root)[:2], (ROLES, []))
        text = " ".join(self.stage_fails(manifest))
        for role in ROLES:
            self.assertNotIn(role, text)
        self.assertIn("landing", text)
        (self.root / "route-graph.json").unlink()
        manifest["dispatch_binding"] = {"pages": [{"page_slot": r} for r in ROLES]}
        self.assertEqual(owner_override.image_stage_waiver(manifest, PKG, root=self.root)[:2], (ROLES, []))

    def test_a_practice_package_is_not_waived(self):
        manifest = dict(self.manifest(self.record()), test_only=True)
        self.assertEqual(owner_override.image_stage_waiver(manifest, PKG), ([], [], ""))

    def test_a_manifest_with_no_record_is_unchanged(self):
        self.assertEqual(owner_override.image_stage_waiver(self.manifest(None), PKG), ([], [], ""))


class CheckPrintsTheBanner(Base):
    def test_check_package_prints_the_banner_only_for_a_verified_record(self):
        self.write_report(ROLES)
        manifest = self.manifest(self.record())
        path = self.root / "package-manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            checks.check_package(path, self.root)
        self.assertIn("OWNER OVERRIDE: image stages waived by the owner for upsell_1, upsell_2, downsell_1 (signed record ",
                      buf.getvalue())
        edited = copy.deepcopy(manifest)
        edited["owner_override_image_stages"]["owner_words"] = ["edited"]
        path.write_text(json.dumps(edited), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            checks.check_package(path, self.root)
        self.assertNotIn("image stages waived", buf.getvalue())
        self.assertIn("NOT verified", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
