"""S80-06 binding integration tests (adapters -> extra-offer binding).

Verifies, for all three production bundles (U1, U2 from U1, U2 from D1):

  * the bundle carries a top-level native_binding record of exactly the
    fixed contract shape (kind / interface_ref / binding_status /
    native_action_id null / TEST capability evidence ref / the nine
    open interface questions);
  * every CTA in the result cta_map and the page_plan action_binding
    bind the binding action ref "extra-offer-binding:<offer_id>", while
    the page_plan also records the copy/request-layer native ref it
    wraps ("native-one-click:<offer_id>") for audit;
  * result.native_action keeps action_id null (never invented) with
    verified_by "s80_06_binding";
  * the bundle is deterministic against the stored expected bundles
    (covered per-instance in the U1/U2 suites; the binding record is
    part of those dicts).

Plus the cross-check against the parallel S80-06 binding module
(work/binding/extra_offer_binding.py): when that tree exists, each
bundle's BindingContext-compatible data must reproduce the bundle's
native_binding via binding_record() (capability_evidence_ref VALUE
excluded - it is fixture data). When the binding tree is not present
yet, that test SKIPS with a stated reason instead of failing.

Run: python3 -m unittest discover -s tests -v   (from adapters/)
"""

import importlib.util
import inspect
import json
import sys
import unittest
from pathlib import Path

ADAPTERS_DIR = Path(__file__).resolve().parents[1]
WORK_DIR = ADAPTERS_DIR.parent
SKILL_DIR = WORK_DIR / "80-signature-upsell"
FIXTURES = ADAPTERS_DIR / "fixtures"
BINDING_MODULE = WORK_DIR / "binding" / "extra_offer_binding.py"
sys.path.insert(0, str(ADAPTERS_DIR))

import adapter_common as common
import upsell1_adapter
import upsell2_adapter

EXPECTED_OPEN_QUESTIONS = [
    "S06-Q1", "S06-Q2", "S06-Q3", "S06-Q4", "S06-Q5", "S06-Q6",
    "S44-Q7", "S44-Q8", "S49-Q9",
]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_all_bundles():
    """The three production bundles, built exactly as the U1/U2 suites do.

    Returns {name: (bundle, request, journey)} - the reconciliation test
    needs the inputs alongside the bundle to construct a BindingContext.
    """
    u1_copy = SKILL_DIR / "fixtures" / "copy-upsell1-public.valid.json"
    u2_copy = SKILL_DIR / "fixtures" / "copy-upsell2-public.valid.json"
    built = {}

    request = load(SKILL_DIR / "fixtures" / "request-upsell1.testonly.json")
    journey = load(FIXTURES / "journey-main-only.testonly.json")
    built["upsell_1"] = (
        upsell1_adapter.build_bundle(
            request, load(u1_copy), journey,
            copy_sha256=common.sha256_file(u1_copy),
            copy_artifact_path="80-signature-upsell/fixtures/copy-upsell1-public.valid.json",
        ),
        request, journey,
    )

    request = load(FIXTURES / "request-upsell2-from-upsell1.testonly.json")
    journey = load(FIXTURES / "journey-upsell2-from-upsell1.testonly.json")
    built["upsell_2_from_upsell_1"] = (
        upsell2_adapter.build_bundle(
            request, load(u2_copy), journey,
            copy_sha256=common.sha256_file(u2_copy),
            copy_artifact_path="80-signature-upsell/fixtures/copy-upsell2-public.valid.json",
        ),
        request, journey,
    )

    request = load(SKILL_DIR / "fixtures" / "request-upsell2.testonly.json")
    journey = load(FIXTURES / "journey-upsell2-from-downsell1.testonly.json")
    built["upsell_2_from_downsell_1"] = (
        upsell2_adapter.build_bundle(
            request, load(u2_copy), journey,
            copy_sha256=common.sha256_file(u2_copy),
            copy_artifact_path="80-signature-upsell/fixtures/copy-upsell2-public.valid.json",
        ),
        request, journey,
    )
    return built


class NativeBindingRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles = {
            name: bundle for name, (bundle, _req, _j) in build_all_bundles().items()
        }

    def test_native_binding_record_exact_contract_shape(self):
        for name, bundle in self.bundles.items():
            with self.subTest(bundle=name):
                self.assertEqual(
                    bundle["native_binding"],
                    {
                        "kind": "extra_offer_binding",
                        "interface_ref": "S79 extra_offer_interface.md DRAFT (fixture level)",
                        "binding_status": "interface_conformant_pending_s06",
                        "native_action_id": None,
                        "capability_evidence_ref": "native:TEST-CAPABILITY-EVIDENCE",
                        "open_questions": EXPECTED_OPEN_QUESTIONS,
                    },
                )

    def test_all_ctas_and_plan_bind_the_binding_ref(self):
        for name, bundle in self.bundles.items():
            with self.subTest(bundle=name):
                offer_id = bundle["result"]["approved_offer_mapping"]["offer_id"]
                binding_ref = "extra-offer-binding:" + offer_id
                self.assertEqual(
                    {c["action_ref"] for c in bundle["result"]["cta_map"]},
                    {binding_ref},
                )
                plan_binding = bundle["page_plan"]["action_binding"]
                self.assertEqual(plan_binding["action_ref"], binding_ref)
                self.assertEqual(plan_binding["kind"], "extra_offer_binding")
                self.assertEqual(
                    plan_binding["status"], "interface_conformant_pending_s06"
                )
                # The wrapped native ref stays recorded for audit, in the
                # copy/request-layer form the schemas govern.
                self.assertEqual(
                    plan_binding["native_action_ref"],
                    "native-one-click:" + offer_id,
                )

    def test_native_action_stays_uninvented_with_binding_verifier(self):
        for name, bundle in self.bundles.items():
            with self.subTest(bundle=name):
                native = bundle["result"]["native_action"]
                self.assertIsNone(native["action_id"])
                self.assertEqual(native["verified_by"], "s80_06_binding")
                self.assertIsNone(bundle["native_binding"]["native_action_id"])
                # Honest status text: the blocker must name the L3 gap.
                blockers = " ".join(bundle["result"]["blockers"])
                self.assertIn("interface-conformance level only", blockers)
                self.assertIn("NOT installed or live proof", blockers)


def _load_binding_module():
    spec = importlib.util.spec_from_file_location(
        "s80_extra_offer_binding", BINDING_MODULE
    )
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the binding module uses dataclasses, whose
    # processing looks the module up in sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _context_kwargs(bundle, request, journey):
    """BindingContext kwargs constructed from the bundle and the exact
    inputs that produced it.

    Every field is sourced from the bundle/request/journey. Two fields
    the fixtures honestly record as unmapped (native_product_id /
    native_price_id are null - no native mapping exists yet) are given
    plainly-TEST structured stand-ins at this test layer only; they are
    never written into any bundle. launch_revision / copy_refs /
    disclosure_terms_ref (validated BindingContext fields) come from
    the bundle's revision, its recorded copy artifact, and its
    request_id, as structured refs.
    """
    result = bundle["result"]
    plan = bundle["page_plan"]
    mapping = result["approved_offer_mapping"]
    disclosure = plan["disclosure"]
    main_record = common.journey_record_for(journey, "main") or {}
    offer_id = mapping["offer_id"]
    return {
        "tenant_ref": result["tenant_id"],
        "location_ref": result["location_id"],
        "launch_ref": result["launch_id"],
        "launch_revision": str(result["revision"]),
        "parent_order_ref": main_record.get("evidence_ref"),
        "parent_verification_source": main_record.get("verification_source"),
        "offer_id": offer_id,
        "native_product_ref": mapping["native_product_id"]
        or "native:TEST-PRODUCT-%s" % offer_id,
        "native_price_ref": mapping["native_price_id"]
        or "native:TEST-PRICE-%s" % offer_id,
        "capability_evidence_ref": bundle["native_binding"][
            "capability_evidence_ref"
        ],
        "amount_minor": mapping["amount_minor"],
        "currency": mapping["currency"],
        "success_route_ref": plan["success_route"]["target_page_id"],
        "decline_route_ref": plan["states"]["decline"]["target_page_id"],
        # Pending/failed payments remain on the page recoverable, so the
        # error route for these fixtures is the page itself.
        "error_route_ref": result["page_id"],
        "disclosure_terms_ref": "request:%s/disclosure" % result["request_id"],
        "copy_refs": (result["artifacts"][0]["path"],),
        "billing_type": mapping["billing_type"],
        "recurring_terms": disclosure.get("recurring_terms"),
        "entry_context": result["eligibility_check"].get("entry_context"),
    }


class BindingModuleReconciliationTests(unittest.TestCase):
    """DO #5 cross-check against the parallel worker's binding module:
    a BindingContext built from each bundle (+ its producing inputs)
    must yield, via ExtraOfferBinding.binding_record(), exactly the
    bundle's native_binding record."""

    def test_binding_record_matches_bundle_native_binding(self):
        if not BINDING_MODULE.exists():
            self.skipTest(
                "work/binding/extra_offer_binding.py not present yet "
                "(parallel S80-06 binding worker still building); "
                "reconciliation runs when the binding tree lands"
            )
        module = _load_binding_module()
        context_cls = getattr(module, "BindingContext", None)
        binding_cls = getattr(module, "ExtraOfferBinding", None)
        self.assertIsNotNone(
            context_cls, "binding module exposes no BindingContext"
        )
        self.assertIsNotNone(
            binding_cls, "binding module exposes no ExtraOfferBinding"
        )
        for name, (bundle, request, journey) in build_all_bundles().items():
            with self.subTest(bundle=name):
                kwargs = _context_kwargs(bundle, request, journey)
                # N2 tightening (S80-10 packaging pass, 2026-10-16): the
                # context is constructed from the EXPLICIT full kwarg set
                # - no signature filtering. The kwarg key set must equal
                # the BindingContext parameter set exactly, so a field
                # added, renamed, or dropped on either side fails loudly
                # here instead of being silently dropped.
                params = set(inspect.signature(context_cls).parameters)
                self.assertEqual(
                    set(kwargs),
                    params,
                    "BindingContext kwargs drift: this test builds %s but "
                    "BindingContext takes %s"
                    % (sorted(kwargs), sorted(params)),
                )
                context = context_cls(**kwargs)
                record = dict(binding_cls(context).binding_record())
                expected = dict(bundle["native_binding"])
                # capability_evidence_ref VALUE is fixture data (contract);
                # the key must exist on both sides, the value is not compared.
                self.assertIn("capability_evidence_ref", record)
                record.pop("capability_evidence_ref")
                expected.pop("capability_evidence_ref")
                self.assertEqual(record, expected)


if __name__ == "__main__":
    unittest.main()
