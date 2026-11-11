"""AF-LAUNCH-CHECKOUT-RUNTIME (Harmony issue 31): a checkout is not ready or live without its runtime binding.

Skill 79's purchase-safety rules run only as fixture models; the one production host is Skill 44's
purchase-event normalizer. A checkout page may therefore claim ``ready_for_activation`` or
``live_verified`` only when the package holds ``runtime-binding.json``, sealed in the manifest.

Two layers are proved here, both free (files only, no provider, no network):

  * the rule module on hand-built manifests, loaded the way the check_rules seam loads it;
  * the real ``package.assemble`` and ``checks.check_package`` on a built package, so the refusal
    is shown at the point a package is sealed and again when it is checked.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import check_rules, package  # noqa: E402
from test_check_rules import PackageCase  # noqa: E402

RULE_FILE = SKILL_ROOT / "launcher_core" / "check_rules" / "checkout_runtime.py"
CODE = "AF-LAUNCH-CHECKOUT-RUNTIME"
BINDING = "runtime-binding.json"
CLAIMS = ("ready_for_activation", "live_verified")
NOT_CLAIMS = ("authored", "locally_verified", "installed_test_verified")
GOOD = {
    "normalizer": "44/tools/siglaunch/normalizer",
    "schema_version": "1.2",
    "grant_policy": "once",
    "paid_edges_only": True,
    "verified_at": "2026-11-10T12:00:00-05:00",
    "evidence_ref": "evidence/normalizer-install-readback.json",
}


def load_rule():
    """The rule file by path, under the name the seam gives it (no relative import may be needed)."""
    spec = importlib.util.spec_from_file_location("launcher_core.check_rules.checkout_runtime", RULE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_binding(root: Path, doc=GOOD) -> Path:
    path = Path(root) / BINDING
    path.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
    return path


def sealed(root: Path) -> dict:
    return {"path": BINDING, "sha256": sha(Path(root) / BINDING)}


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rule = load_rule()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, status="live_verified", *, role="checkout", seal=None):
        out = {"tenant_id": "tenant-a", "location_id": "loc-a", "launch_id": "launch-a",
               "pieces": [{"role": role, "slot": role, "page_id": f"launch-a-{role}", "status": status}]}
        if seal is not None:
            out["runtime_binding"] = seal
        return out

    def run_rule(self, manifest):
        return self.rule.violations(manifest, self.root, SKILL_ROOT)

    def test_a_status_the_runtime_does_not_back_needs_no_binding(self):
        for status in NOT_CLAIMS:
            with self.subTest(status=status):
                self.assertEqual(self.run_rule(self.manifest(status)), [])

    def test_a_page_with_no_purchase_is_not_this_rules_business(self):
        for role in ("landing", "thank_you"):
            with self.subTest(role=role):
                self.assertEqual(self.run_rule(self.manifest("live_verified", role=role)), [])

    def test_a_checkout_claim_with_no_binding_file_is_refused_by_name(self):
        for status in CLAIMS:
            with self.subTest(status=status):
                out = self.run_rule(self.manifest(status))
                self.assertEqual(len(out), 1, out)
                self.assertTrue(out[0].startswith(f"{CODE}: "), out)
                self.assertIn(status, out[0])
                self.assertIn(BINDING, out[0])

    def test_a_sealed_complete_binding_backs_both_claims_in_either_spelling(self):
        for spelling in GOOD["normalizer"], "44-convert-and-flow-operator/tools/siglaunch/normalizer":
            write_binding(self.root, {**GOOD, "normalizer": spelling})
            for status in CLAIMS:
                with self.subTest(status=status, spelling=spelling):
                    self.assertEqual(self.run_rule(self.manifest(status, seal=sealed(self.root))), [])

    def test_every_key_of_the_record_is_required_and_judged(self):
        bad = {
            "normalizer": ("somewhere/else", "44/tools/other", "", None, 5, 44),
            "schema_version": ("", None, 2),
            "grant_policy": ("every_event", None, "ONCE"),
            "paid_edges_only": (False, "true", None),
            "verified_at": ("yesterday", "", "2026-11-10T12:00:00", None),
            "evidence_ref": ("", "  ", None),
        }
        for key, values in bad.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    write_binding(self.root, {**GOOD, key: value})
                    out = self.run_rule(self.manifest(seal=sealed(self.root)))
                    self.assertTrue(out and all(v.startswith(f"{CODE}: ") for v in out), out)
                    self.assertTrue(any(key in v for v in out), out)
            with self.subTest(key=key, value="<absent>"):
                write_binding(self.root, {k: v for k, v in GOOD.items() if k != key})
                self.assertTrue(any(key in v for v in self.run_rule(self.manifest(seal=sealed(self.root)))))

    def test_a_binding_for_another_client_does_not_cover_this_checkout(self):
        for key in ("tenant_id", "location_id", "launch_id"):
            with self.subTest(key=key):
                write_binding(self.root, {**GOOD, key: "someone-else"})
                out = self.run_rule(self.manifest(seal=sealed(self.root)))
                self.assertTrue(any(key in v and "someone-else" in v for v in out), out)
        write_binding(self.root, {**GOOD, "tenant_id": "tenant-a", "location_id": "loc-a",
                                  "launch_id": "launch-a"})
        self.assertEqual(self.run_rule(self.manifest(seal=sealed(self.root))), [])

    def test_a_record_that_is_not_a_readable_object_is_refused(self):
        for label, text in (("not json", "{nope"), ("a list", "[]"), ("a string", '"ok"')):
            with self.subTest(label=label):
                (self.root / BINDING).write_text(text, encoding="utf-8")
                out = self.run_rule(self.manifest(seal=sealed(self.root)))
                self.assertEqual(len(out), 1, out)
                self.assertTrue(out[0].startswith(f"{CODE}: "), out)

    def test_a_link_out_of_the_package_does_not_count_as_the_binding(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = write_binding(Path(elsewhere))
            os.symlink(outside, self.root / BINDING)
            out = self.run_rule(self.manifest(seal=sealed(self.root)))
            self.assertEqual(len(out), 1, out)
            self.assertIn("outside the package", out[0])

    def test_the_manifest_must_seal_the_binding_and_the_digest_must_hold(self):
        write_binding(self.root)
        for label, seal in (("no seal", None), ("empty seal", {}), ("other path", {"path": "x.json", "sha256": "a" * 64}),
                            ("no digest", {"path": BINDING})):
            with self.subTest(label=label):
                out = self.run_rule(self.manifest(seal=seal))
                self.assertTrue(any("does not seal" in v for v in out), out)
        good = sealed(self.root)
        write_binding(self.root, {**GOOD, "evidence_ref": "evidence/a-different-record.json"})
        out = self.run_rule(self.manifest(seal=good))
        self.assertEqual(len(out), 1, out)
        self.assertIn("changed after assembly", out[0])

    def test_a_receipt_row_for_the_checkout_page_cannot_out_claim_the_manifest(self):
        manifest = self.manifest("authored")
        receipt = {"units": [
            {"unit_id": "checkout", "status": "live_verified",
             "artifacts": [{"path": "pieces/launch-a-checkout/page.html"}]},
            {"unit_id": "landing", "status": "live_verified",
             "artifacts": [{"path": "pieces/launch-a-landing/page.html"}]}]}
        (self.root / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        out = self.run_rule(manifest)
        self.assertEqual(len(out), 1, out)
        self.assertIn("receipt unit 'checkout'", out[0])
        receipt["units"][0]["status"] = "authored"
        (self.root / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(self.run_rule(manifest), [])

    def test_a_manifest_with_no_pieces_or_an_unreadable_receipt_is_not_a_crash(self):
        self.assertEqual(self.run_rule({}), [])
        (self.root / "receipt.json").write_text("{nope", encoding="utf-8")
        self.assertEqual(self.run_rule(self.manifest("authored")), [])

    def test_the_seam_runs_the_rule_with_the_shipped_rules_folder(self):
        manifest = self.manifest()
        fails = check_rules.run(manifest, self.root, SKILL_ROOT)
        self.assertTrue(any(v.startswith(f"{CODE}: ") for v in fails), fails)
        self.assertFalse(any(v.startswith("AF-LAUNCH-CHECK-RULE") and "checkout_runtime" in v for v in fails), fails)


class PackageTests(PackageCase):
    """The real packager and the real check, on the elevation fixture's pieces."""

    def claim(self, status):
        pieces = self.pieces()
        pieces["checkout"]["status"] = status
        return pieces

    def put_binding(self, name="pkg", doc=GOOD):
        root = self.work / name
        root.mkdir(parents=True, exist_ok=True)
        write_binding(root, doc)
        return root

    def runtime(self, fails):
        return [f for f in fails if f.startswith(CODE)]

    def test_assemble_refuses_a_claim_without_the_binding_and_seals_nothing(self):
        for status in CLAIMS:
            with self.subTest(status=status):
                with self.assertRaises(package.PackageError) as ctx:
                    self.build(self.claim(status), name=f"refused-{status}")
                self.assertEqual(ctx.exception.code, CODE)
                self.assertIn(BINDING, ctx.exception.detail)
                self.assertFalse((self.work / f"refused-{status}" / "package-manifest.json").exists())
                self.assertFalse((self.work / f"refused-{status}" / "receipt.json").exists())

    def test_assemble_refuses_an_incomplete_or_foreign_binding(self):
        for label, doc in (("grant every time", {**GOOD, "grant_policy": "always"}),
                           ("not paid edges only", {**GOOD, "paid_edges_only": False}),
                           ("another location", {**GOOD, "location_id": "someone-else"})):
            with self.subTest(label=label):
                self.put_binding(label.replace(" ", "-"), doc)
                with self.assertRaises(package.PackageError) as ctx:
                    self.build(self.claim("ready_for_activation"), name=label.replace(" ", "-"))
                self.assertEqual(ctx.exception.code, CODE)

    def test_a_bound_claim_is_sealed_and_check_holds(self):
        self.put_binding()
        built, root = self.build(self.claim("ready_for_activation"))
        self.assertEqual(built["manifest"]["runtime_binding"], sealed(root))
        fails, _ = self.check(built, root)
        self.assertEqual(fails, [])

    def test_a_binding_staged_in_the_run_is_copied_into_the_package_and_sealed(self):
        write_binding(self.work)  # beside the pieces, not in the package folder
        built, root = self.build(self.claim("ready_for_activation"))
        self.assertEqual((root / BINDING).read_bytes(), (self.work / BINDING).read_bytes())
        self.assertEqual(built["manifest"]["runtime_binding"], sealed(root))
        self.assertEqual(self.check(built, root)[0], [])

    def test_a_bad_binding_staged_in_the_run_is_refused_and_nothing_is_copied(self):
        write_binding(self.work, {**GOOD, "grant_policy": "always"})
        with self.assertRaises(package.PackageError) as ctx:
            self.build(self.claim("ready_for_activation"))
        self.assertEqual(ctx.exception.code, CODE)
        self.assertFalse((self.work / "pkg" / BINDING).exists())

    def test_a_live_claim_is_sealed_and_this_rule_holds(self):
        self.put_binding()
        built, root = self.build(self.claim("live_verified"))
        self.assertEqual(built["manifest"]["runtime_binding"], sealed(root))
        self.assertEqual(self.runtime(self.check(built, root)[0]), [])

    def test_a_package_that_claims_nothing_is_unchanged(self):
        built, root = self.build(self.claim("authored"))
        self.assertNotIn("runtime_binding", built["manifest"])
        self.assertEqual(self.check(built, root)[0], [])

    def test_check_names_a_binding_removed_or_swapped_after_assembly(self):
        self.put_binding()
        built, root = self.build(self.claim("ready_for_activation"))
        write_binding(root, {**GOOD, "evidence_ref": "evidence/swapped.json"})
        swapped = self.runtime(self.check(built, root)[0])
        self.assertEqual(len(swapped), 1, swapped)
        self.assertIn("changed after assembly", swapped[0])
        (root / BINDING).unlink()
        removed = self.runtime(self.check(built, root)[0])
        self.assertEqual(len(removed), 1, removed)
        self.assertIn(f"holds no {BINDING}", removed[0])

    def test_check_names_a_claim_added_to_a_sealed_package_by_hand(self):
        built, root = self.build(self.claim("authored"))
        write_binding(root)  # a binding dropped in after the fact is not what was assembled
        def raise_checkout(manifest):
            next(p for p in manifest["pieces"] if p["role"] == "checkout")["status"] = "ready_for_activation"

        self.reseal(root, raise_checkout)
        out = self.runtime(self.check(built, root)[0])
        self.assertEqual(len(out), 1, out)
        self.assertIn("does not seal", out[0])
        (root / BINDING).unlink()
        out = self.runtime(self.check(built, root)[0])
        self.assertEqual(len(out), 1, out)
        self.assertIn(f"holds no {BINDING}", out[0])

    def test_check_names_a_receipt_row_that_claims_what_the_manifest_does_not(self):
        built, root = self.build(self.claim("authored"))
        receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
        row = next(u for u in receipt["units"] if u["unit_id"] == "checkout")
        row["status"] = "ready_for_activation"
        row["proof"] = dict(zip(package.PROOF_KEYS, package.PROOF_BY_STATUS["ready_for_activation"]))
        self.edit_receipt(root, units=receipt["units"])
        out = self.runtime(self.check(built, root)[0])
        self.assertEqual(len(out), 1, out)
        self.assertIn("receipt unit 'checkout'", out[0])


if __name__ == "__main__":
    unittest.main()
