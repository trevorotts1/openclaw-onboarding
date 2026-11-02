"""DTY-11 / DTY-29: the D1 S06 install wrapper is design-only.

The wrapper builds a plan; no installer exists. A caller asking it to
install must get a named refusal that reports the scheduled Skill 06
work items, never a silent no-op. Plans and the package docs must say
"design only; not installed" and must not carry the stale status text.

Stdlib unittest only. All data is TEST ONLY.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "adapters"))
sys.path.insert(0, str(ROOT / "validators"))

import s06_install_wrapper as wrapper  # noqa: E402

STALE = "Not merged, not installed, not live"


def _plan():
    request = json.loads(
        (ROOT / "fixtures" / "valid-downsell-request.json").read_text())
    binding = {"native_product_id": "TEST-NATIVE-PRODUCT",
               "native_price_id": "TEST-NATIVE-PRICE"}
    bundle = {"bundle_ref": "TEST-D1-BUNDLE",
              "action_refs": {"purchase_action_ref": "native-d1-action",
                              "decline_action_ref": "native-decline-d1"},
              "canonical_u2_page_id": "TEST-UPSELL_2"}
    return wrapper.build_install_plan(request, binding, bundle)


class InstallRefusalTests(unittest.TestCase):
    def test_install_refuses_and_names_scheduled_skill06_work(self):
        with self.assertRaises(wrapper.InstallRefusedError) as ctx:
            wrapper.install_d1_page(_plan())
        err = ctx.exception
        self.assertEqual(err.code, "D1-INSTALL-DESIGN-ONLY")
        self.assertIn("design only; not installed", err.detail)
        for item in ("S06-02", "UPS-08"):
            self.assertIn(item, err.detail)

    def test_refusal_is_an_install_plan_error(self):
        # Callers already catching InstallPlanError keep failing closed.
        with self.assertRaises(wrapper.InstallPlanError):
            wrapper.install_d1_page()


class PlanStatusTests(unittest.TestCase):
    def test_plan_states_design_only_and_scheduled_work(self):
        plan = _plan()
        self.assertFalse(plan["installed"])
        self.assertFalse(plan["executes_install"])
        self.assertEqual(plan["install_status"], "design only; not installed")
        self.assertEqual(plan["scheduled_skill06_work_items"],
                         ["S06-02", "UPS-08"])
        # No read-back recorded, so nothing may read as installed.
        self.assertFalse(plan["binding_readback"]["recorded"])
        self.assertIsNone(plan["binding_readback"]["result"])


class StaleStatusTextTests(unittest.TestCase):
    def test_no_stale_status_line_in_81_or_83_routes_docs(self):
        docs = [ROOT / "SKILL.md", ROOT / "adapters" / "README.md",
                ROOT / "references" / "downsell-copy-profile.md",
                ROOT.parent / "83-black-friday-launcher" / "routes"
                / "README.md"]
        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            self.assertNotIn(STALE, text, str(doc))
            self.assertNotIn("Not installed, not merged", text, str(doc))

    def test_skill_md_references_only_shipped_files(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for rel in ("references/downsell-copy-profile.md",
                    "references/offer-alternatives.md",
                    "references/native-action-states.md",
                    "references/design-profile.md",
                    "references/terms-entitlement-review.md",
                    "references/wireframe-layout.md",
                    "adapters/README.md", "fixtures/README.md",
                    "validators/validate_downsell.py",
                    "validators/validate_request.py"):
            self.assertIn(rel, text)
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_routes_readme_does_not_claim_translator_calls_resolver(self):
        text = (ROOT.parent / "83-black-friday-launcher" / "routes"
                / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "→ S82 `run_manifest.build_run_manifest` + "
            "`thank_you_resolver.resolve_order_view`", text)


if __name__ == "__main__":
    unittest.main()
