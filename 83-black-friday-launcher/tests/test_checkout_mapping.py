"""Checkout mapping and the checkout check rule (CHK-02, 03, 04, 05, 08).

Every case builds a real intake, route and package, then breaks exactly one thing.
The rule under test is launcher_core/check_rules/checkout.py; it is called directly
and, when the check_rules seam is present, through check_package as well.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

from launcher_core import checkout, checks, council, intake, package, route  # noqa: E402
from launcher_core.check_rules import checkout as rule  # noqa: E402
import test_only_readback  # noqa: E402
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK  # noqa: E402

READBACK = {  # a TEST-ONLY Skill 06 read-back: everything intake does not own
    "native_capability_evidence_ref": "TEST-ONLY-CAPABILITY",
    "fulfillment_mapping_ref": "TEST-ONLY-FULFILLMENT",
    "failed_pending_requirements": {
        "failed_state_copy_ref": "TEST-ONLY-FAILED",
        "pending_state_copy_ref": "TEST-ONLY-PENDING",
        "retry_policy": "reconcile_native_records_first",
    },
    "native": {"main-1": {"currency_exponent": 2}},
}


_ANSWERS_DIR = tempfile.TemporaryDirectory()  # the client's answers each intake below names (every price has a source)


def _answered(value: dict) -> dict:
    return {"value": value, "status": "provided", "source": "client"}


def write_answers(offers: list) -> str:
    """The client's answers file for these offers; each offer's price names its entry (price.source_ref).
    Several mains are the packages list; one main is the price and offer_name answers."""
    def item(o):
        return {"offer_id": o["offer_id"], "display_name": o["name"], "price": dict(o["price"]),
                "deliverables": list(o["level"]["deliverables"])}
    mains = [o for o in offers if o["role"] == "main"]
    answers = {}
    if len(mains) == 1:
        answers.update(offer_name=_answered(mains[0]["name"]), price=_answered(dict(mains[0]["price"])),
                       deliverables=_answered(list(mains[0]["level"]["deliverables"])))
        mains[0]["price"]["source_ref"] = "answers-file:price"
    else:
        answers["packages"] = _answered([item(o) for o in mains])
        for i, o in enumerate(mains):
            o["price"]["source_ref"] = f"answers-file:packages[{i}]"
    for o in offers:
        if o["role"] != "main":
            answers[o["role"]] = _answered(item(o))
            o["price"]["source_ref"] = f"answers-file:{o['role']}"
    text = json.dumps({"schema": "client-intake-answers/v1", "answers": answers}, sort_keys=True)
    path = Path(_ANSWERS_DIR.name) / f"answers-{hashlib.sha256(text.encode()).hexdigest()[:16]}.json"
    path.write_text(text, encoding="utf-8")
    return str(path)


def raw_intake(mode: str = "single_simple", rich: bool = True, bump: bool = False) -> dict:
    def offer(offer_id, role, amount):
        out = {"offer_id": offer_id, "name": f"Offer {offer_id}", "role": role,
               "price": {"amount_minor": amount, "currency": "USD"},
               "level": {"state": "supplied", "name": offer_id, "deliverables": [offer_id]}}
        if rich:
            out["delivery"] = {"destination": f"https://delivery.test-only.invalid/{offer_id}",
                               "owner_confirmed": True}
        return out
    offers = [offer("main-1", "main", 49700)]
    if mode != "single_simple":
        offers.append(offer("main-2", "main", 99700))
        offers.append(offer("main-3", "main", 199700))
    if bump:
        offers.append(offer("bump-1", "bump", 2700))
    payload = {
        "schema_version": "1.0", "tenant_id": "tenant-a", "location_id": "loc-a",
        "launch_id": "bf-2026", "revision": 1, "journey_mode": mode,
        "brand": {"ref": "brand-a", "hash": "a" * 64}, "copy_profile": "signature_12_section",
        "approval": {"ref": "approval-1", "hash": "b" * 64},
        "offers": offers,
        # issue 36: test_only is said out loud, never defaulted; these fixtures are practice runs
        "test_only": True,
    }
    payload["answers_file"] = write_answers(offers)
    if rich:
        payload["checkout_terms"] = {"guarantee_ref": "g", "guarantee_text": "g",
                                     "terms_ref": "TEST-TERMS", "terms_text": "t",
                                     "consent_ref": "TEST-CONSENT", "consent_text": "c"}
    return payload


def normalized(mode: str = "single_simple", complete: bool = False, bump: bool = False) -> dict:
    """A validated intake. ``complete`` carries the owner checkout facts (terms, consent,
    delivery); otherwise they are stripped, so the case is the same whichever intake
    generation this tree validates."""
    n = intake.validate(raw_intake(mode, bump=bump))
    if complete:
        n.setdefault("checkout_terms", {"terms_ref": "TEST-TERMS", "consent_ref": "TEST-CONSENT"})
        for o in n["offers"]:
            o.setdefault("delivery", {"destination": f"https://delivery.test-only.invalid/{o['offer_id']}",
                                      "owner_confirmed": True})
            o.setdefault("checkout", {"billing_type": "one_time"})
    else:
        n.pop("checkout_terms", None)
        for o in n["offers"]:
            o.pop("delivery", None)
            o.pop("checkout", None)
    return n


def build(n: dict, readback=None) -> dict:
    return checkout.order_form_mapping(n, route.compile_route(n), readback=readback)


def assemble(tmp: str, n: dict, readback_mapping=None):
    """A real package on disk; returns (manifest, run_dir)."""
    advice = council.planning_step(n, runner=lambda _l: {
        "status": "advice_returned", "ready": True, "advice": {"r": "stub"},
        "advice_state": "returned"})
    graph = route.compile_route(n, advice)
    run_dir = Path(tmp) / "run"
    pieces = {}
    for node in graph["nodes"]:
        rel = f"pieces/{node['page_id']}/page.html"
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"<html>{node['role']}</html>\n", encoding="utf-8")
        pieces[node["role"]] = {
            "schema_version": "1.0", "tenant_id": n["tenant_id"], "location_id": n["location_id"],
            "launch_id": n["launch_id"], "revision": n["revision"],
            "request_id": f"req-{node['page_id']}", "input_hash": "c" * 64,
            "page_id": node["page_id"], "status": "authored",
            "artifacts": [{"path": rel, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
            "author_session": "builder-1", "independent_review": False, "proof_class": "L0",
            "blockers": [], "native_bindings_ref": None, "test_only": True,
        }
    out = package.assemble(run_dir, n, graph, pieces, council=advice)
    return out["manifest"], run_dir


def codes(fails):
    return [f.split(":", 1)[0] for f in fails]


class ProbeRequestTests(unittest.TestCase):
    """CHK-03: the probe is built from contract fields only."""

    def test_a_fully_supplied_request_is_accepted(self):
        mapping = build(normalized(complete=True), READBACK)
        self.assertEqual(mapping["validator"]["probe"], {"result": "accepted"}, mapping["unknown"])
        request = checkout.contract_request(mapping["supplied"], mapping["operational_defaults"])
        self.assertNotIn("unknown", request["main_price"])
        self.assertEqual(checkout.missing_facts(request), [])
        self.assertEqual(mapping["missing_facts"], [])
        self.assertIsNone(mapping["checkout_incomplete_label"])

    def test_removing_one_fact_is_rejected_and_named(self):
        readback = {k: v for k, v in READBACK.items() if k != "fulfillment_mapping_ref"}
        mapping = build(normalized(complete=True), readback)
        self.assertEqual(mapping["validator"]["probe"]["result"], "rejected")
        self.assertEqual(mapping["missing_facts"], ["fulfillment_mapping_ref"])

    def test_bookkeeping_never_reaches_the_request(self):
        mapping = build(normalized())  # billing is answered by the canonical (one_time): no annotation needed
        request = checkout.contract_request(mapping["supplied"], mapping["operational_defaults"])
        self.assertNotIn("unknown", mapping["supplied"]["main_price"])
        self.assertNotIn("unknown", request["main_price"])
        request = checkout.contract_request(build(normalized(bump=True))["supplied"])
        self.assertIn("unresolved", build(normalized(bump=True))["supplied"]["bump"])
        self.assertNotIn("unresolved", request["bump"])
        self.assertNotIn("unknown", request["bump"]["price"])


class DerivedExponentTests(unittest.TestCase):
    """Rehearsal F2: the exponent is a fact of the currency (ISO 4217), not of the read-back."""
    NO_NATIVE = {k: v for k, v in READBACK.items() if k != "native"}

    def test_a_single_offer_checkout_derives_the_exponent_from_its_currency(self):
        mapping = build(normalized(complete=True, bump=True), self.NO_NATIVE)
        self.assertEqual(mapping["supplied"]["main_price"]["currency_exponent"], 2)
        self.assertEqual(mapping["supplied"]["bump"]["price"]["currency_exponent"], 2)
        self.assertNotIn("currency_exponent", mapping["supplied"]["main_price"].get("unknown", []))
        self.assertNotIn("main_price.currency_exponent", mapping["missing_facts"])

    def test_a_zero_decimal_currency_derives_zero_not_two(self):
        offer_ = {"offer_id": "main-1", "price": {"amount_minor": 5000, "currency": "JPY"}}
        self.assertEqual(checkout._price_choice(offer_, {}, None)["currency_exponent"], 0)

    def test_the_readback_still_wins_over_the_derived_exponent(self):
        offer_ = {"offer_id": "main-1", "price": {"amount_minor": 5000, "currency": "USD"}}
        rb = {"native": {"main-1": {"currency_exponent": 3}}}
        self.assertEqual(checkout._price_choice(offer_, {}, rb)["currency_exponent"], 3)

    def test_recurring_billing_comes_from_the_canonical_not_the_intake_default(self):
        # the flattening: a canonical recurring price behind an intake checkout block
        # that carries no stated billing must not be charged as one payment.
        offer_ = {"offer_id": "U1", "price": {"amount_minor": 4900, "currency": "USD"},
                  "checkout": {"billing_type": "one_time"},
                  "canonical": {"prices": [{"billing_type": "recurring", "recurring_interval": "month"}]}}
        choice = checkout._price_choice(offer_, {}, None)
        self.assertEqual(choice["billing_type"], "recurring")
        self.assertEqual(choice["recurring_interval"], "month")

    def test_recurring_without_an_interval_is_named_never_silently_one_payment(self):
        offer_ = {"offer_id": "U1", "price": {"amount_minor": 4900, "currency": "USD"},
                  "checkout": {},
                  "canonical": {"prices": [{"billing_type": "recurring"}]}}
        choice = checkout._price_choice(offer_, {}, None)
        self.assertEqual(choice["billing_type"], "recurring")
        self.assertIn("recurring_interval", choice.get("unknown", []))
        self.assertNotIn("billing_type", choice.get("unknown", []))

    def test_the_stated_block_stands_in_only_when_no_canonical_exists(self):
        offer_ = {"offer_id": "MAIN-1", "price": {"amount_minor": 12900, "currency": "USD"},
                  "checkout": {"billing_type": "one_time"}}
        self.assertEqual(checkout._price_choice(offer_, {}, None)["billing_type"], "one_time")

    def test_the_package_replay_does_not_choke_on_bookkeeping(self):
        # a cleared checkout block never hides the answers' billing: the canonical decides
        n = normalized(complete=True)
        for o in n["offers"]:
            o["checkout"] = {}
        mapping = build(n, self.NO_NATIVE)
        self.assertNotIn("unknown", mapping["supplied"]["main_price"])
        verdict = checks._checkout_probe_violations(mapping, mapping["validator"])
        self.assertEqual(verdict, [])


class MappingFactTests(unittest.TestCase):
    """CHK-05: the plan hash is mapped; defaults are applied before unknown is computed."""

    def test_approved_plan_hash_is_mapped_and_unknown_is_clean(self):
        for mode in ("single_simple", "multiple_options", "folded_levels"):
            n = normalized(mode)
            mapping = build(n)
            self.assertEqual(mapping["supplied"]["approved_plan_hash"], n["approval"]["hash"], mode)
            self.assertEqual(mapping["unknown"], sorted(set(mapping["unknown"])), mode)
            self.assertNotIn("quantity", mapping["unknown"], mode)
            self.assertNotIn("approved_plan_hash", mapping["unknown"], mode)
            self.assertEqual(mapping["supplied"]["quantity"], 1, mode)


class ModeRuleTests(unittest.TestCase):
    """CHK-02 and CHK-04 against a real package."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_rule(self, manifest, run_dir):
        return rule.violations(manifest, run_dir, SKILL_ROOT)

    def test_single_simple_with_a_main_price_passes_offline_with_its_label(self):
        manifest, run_dir = assemble(self.tmp.name, normalized())
        self.assertEqual(self.run_rule(manifest, run_dir), [])
        self.assertIn("checkout incomplete", manifest["checkout"]["checkout_incomplete_label"])
        self.assertIn("terms_ref", manifest["checkout"]["missing_facts"])

    def test_multiple_options_returns_a_named_checkout_violation(self):
        manifest, run_dir = assemble(self.tmp.name, normalized("multiple_options"))
        fails = self.run_rule(manifest, run_dir)
        self.assertTrue(fails)
        self.assertTrue(all(c.startswith("AF-LAUNCH-CHECKOUT-") for c in codes(fails)), fails)

    def test_a_post_selection_record_without_a_selection_binding_fails(self):
        manifest, run_dir = assemble(self.tmp.name, normalized("multiple_options"))
        manifest["checkout"].update({"checkout_mode": "post_selection", "binding_plan": None,
                                     "realisation": "single_request"})
        manifest["checkout"]["supplied"].pop("selection_ref", None)
        self.assertIn("AF-LAUNCH-CHECKOUT-SELECTION", codes(rule.mode_violations(manifest["checkout"])))

    def test_a_combined_record_without_a_main_offer_or_price_fails(self):
        fails = rule.mode_violations({"checkout_mode": "combined_single_offer", "supplied": {}})
        self.assertEqual(codes(fails), ["AF-LAUNCH-CHECKOUT-OFFER"])
        self.assertIn("main_offer_id", fails[0])
        self.assertIn("main_price", fails[0])

    def test_a_rejected_probe_in_delivery_scope_fails_and_lists_the_missing_facts(self):
        manifest, run_dir = assemble(self.tmp.name, normalized())
        manifest["test_only"] = False
        fails = [f for f in self.run_rule(manifest, run_dir) if f.startswith("AF-LAUNCH-CHECKOUT-INCOMPLETE")]
        self.assertEqual(len(fails), 1, fails)
        for fact in ("terms_ref", "consent_ref", "fulfillment_mapping_ref",
                     "native_capability_evidence_ref", "successful_payment_next_route"):
            self.assertIn(fact, fails[0])

    def test_offline_without_the_label_fails_and_a_false_label_is_not_enough(self):
        manifest, run_dir = assemble(self.tmp.name, normalized())
        bare = copy.deepcopy(manifest)
        bare["checkout"]["checkout_incomplete_label"] = None
        self.assertIn("AF-LAUNCH-CHECKOUT-INCOMPLETE", codes(rule.incomplete_violations(bare, bare["checkout"])))
        lying = copy.deepcopy(manifest)
        lying["checkout"]["missing_facts"] = []  # a label that hides what is missing
        self.assertIn("AF-LAUNCH-CHECKOUT-INCOMPLETE", codes(rule.incomplete_violations(lying, lying["checkout"])))

    def test_a_complete_package_has_no_checkout_violation_in_any_scope(self):
        n = normalized(complete=True)
        manifest, run_dir = assemble(self.tmp.name, n)
        self.assertEqual(manifest["checkout"]["validator"]["probe"]["result"], "rejected")  # no read-back at assembly
        # the same package once the read-back is in hand
        full = copy.deepcopy(manifest)
        full["checkout"] = {**full["checkout"], **checkout.order_form_mapping(
            n, route.compile_route(n), readback=READBACK)}
        for test_only in (True, False):
            full["test_only"] = test_only
            self.assertEqual(rule.incomplete_violations(full, full["checkout"]), [], test_only)
            self.assertEqual(rule.mode_violations(full["checkout"]), [], test_only)

    @unittest.skipUnless(hasattr(checks, "check_rules"), "the check_rules seam is not in this tree")
    def test_check_package_runs_the_rule(self):
        manifest, run_dir = assemble(self.tmp.name, normalized("multiple_options"))
        fails = checks.check_package(run_dir / "package-manifest.json", run_dir, announce=False)
        self.assertTrue(any(f.startswith("AF-LAUNCH-CHECKOUT-") for f in fails), fails)


class RecordTests(unittest.TestCase):
    """CHK-08: an edited and resealed checkout record fails."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest, self.run_dir = assemble(self.tmp.name, normalized("folded_levels"))

    def reseal(self, manifest, mapping_too=False):
        """Rewrite the manifest checkout record (and optionally the mapping file) as an editor would."""
        mapping_path = self.run_dir / manifest["checkout"]["mapping_path"]
        if mapping_too:
            body = {k: v for k, v in manifest["checkout"].items() if k not in ("mapping_path", "mapping_sha256")}
            mapping_path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["checkout"]["mapping_sha256"] = hashlib.sha256(mapping_path.read_bytes()).hexdigest()

    def record_fails(self, manifest):
        return [f for f in rule.record_violations(manifest, self.run_dir)]

    def test_an_untouched_record_is_clean(self):
        self.assertEqual(self.record_fails(self.manifest), [])

    def test_a_record_edited_away_from_the_mapping_file_fails(self):
        edited = copy.deepcopy(self.manifest)
        edited["checkout"]["checkout_mode_state"] = "resolved"
        edited["checkout"]["delivery_blocked"] = False
        fails = self.record_fails(edited)
        self.assertEqual(codes(fails)[0], "AF-LAUNCH-CHECKOUT-RECORD")
        self.assertIn("differs from checkout-mapping.json", fails[0])

    def test_a_record_and_mapping_edited_together_still_fails_the_rederivation(self):
        edited = copy.deepcopy(self.manifest)
        edited["checkout"]["main_offers"][0]["price"]["amount_minor"] = 100
        self.reseal(edited, mapping_too=True)
        fails = self.record_fails(edited)
        self.assertEqual(codes(fails), ["AF-LAUNCH-CHECKOUT-RECORD"])
        self.assertIn("main_offers", fails[0])

    def test_the_full_rule_reports_the_resealed_record(self):
        edited = copy.deepcopy(self.manifest)
        edited["checkout"]["main_offers"][0]["price"]["amount_minor"] = 100
        self.reseal(edited, mapping_too=True)
        self.assertIn("AF-LAUNCH-CHECKOUT-RECORD", codes(rule.violations(edited, self.run_dir, SKILL_ROOT)))


class NativeIdTests(unittest.TestCase):
    """PRD-05 carried row: a live multiple_options checkout needs native price ids."""

    def manifest(self, pro_price_id):
        def entry(offer_id, price_id):
            return {"offer_id": offer_id, "price": {"native_product_id": f"prod_{offer_id}",
                                                    "native_price_id": price_id}}
        return {"journey_mode": "multiple_options", "test_only": False,
                "checkout": {"main_offers": [entry("MAIN-ESS", "price_1"), entry("MAIN-PRO", pro_price_id),
                                             entry("MAIN-ELITE", "price_3")]}}

    def test_ids_present_pass_and_a_missing_one_names_the_offer_and_field(self):
        self.assertEqual(rule.native_id_violations(self.manifest("price_2")), [])
        fails = rule.native_id_violations(self.manifest(None))
        self.assertEqual(len(fails), 1)
        self.assertTrue(fails[0].startswith("AF-LAUNCH-CHECKOUT-NATIVE-IDS"))
        self.assertIn("MAIN-PRO", fails[0])
        self.assertIn("native_price_id", fails[0])

    def test_test_only_manifests_are_exempt(self):
        manifest = self.manifest(None)
        manifest["test_only"] = True
        self.assertEqual(rule.native_id_violations(manifest), [])

    def test_readback_ids_reach_main_offers(self):
        mapping = build(normalized("multiple_options"), {"native": {"main-2-USD": {
            "native_product_id": "prod_2", "native_price_id": "price_2"}}})
        prices = {m["offer_id"]: m["price"] for m in mapping["main_offers"]}
        self.assertEqual(prices["main-2"]["native_price_id"], "price_2")
        self.assertIsNone(prices["main-1"]["native_price_id"])  # never defaulted


class PerOfferRealisationTests(unittest.TestCase):
    """CHK-10/CHK-12 carried rows: several mains ride on the instance module when it exists."""

    def fake_instances(self, violations):
        fake = mock.Mock()
        fake.record.return_value = {"instances": [{"slot": "checkout-main-1", "missing": ["terms_ref"]}],
                                    "binding_plan": {"mappings": []}, "violations": violations}
        fake.replay_violations.return_value = ["AF-LAUNCH-CHECKOUT-REPLAY: stub"]
        return fake

    def test_several_mains_are_judged_by_the_instances(self):
        fake = self.fake_instances(["AF-LAUNCH-CHECKOUT-REJECTED: checkout-main-1: stub"])
        with mock.patch.object(checkout, "instances_module", return_value=fake):
            mapping = build(normalized("folded_levels"))
        self.assertEqual(mapping["realisation"], "per_offer_instances")
        self.assertEqual(mapping["checkout_mode"], "combined_single_offer")
        self.assertEqual(mapping["checkout_mode_state"], "resolved")
        self.assertTrue(mapping["delivery_blocked"])
        self.assertTrue(all(b.startswith("AF-LAUNCH-CHECKOUT-REJECTED") for b in mapping["delivery_blockers"]))
        with mock.patch.object(checkout, "instances_module", return_value=fake):
            self.assertEqual(rule.instance_violations(mapping), ["AF-LAUNCH-CHECKOUT-REPLAY: stub"])
        with mock.patch.object(checkout, "instances_module", return_value=None):
            self.assertEqual(codes(rule.instance_violations(mapping)), ["AF-LAUNCH-CHECKOUT-INSTANCES"])

    def test_one_main_stays_a_single_request(self):
        with mock.patch.object(checkout, "instances_module", return_value=self.fake_instances([])) as m:
            mapping = build(normalized("single_simple"))
        self.assertEqual(mapping["realisation"], "single_request")
        m.assert_not_called()


class WorkedExampleRealisationTests(unittest.TestCase):
    """CARRIED 49 (DECISIONS-NEEDED[4]): every several-mains worked example is one native
    combined_single_offer order form per main price choice, judged by the instances."""

    def mapping(self, fixture, readback):
        payload = json.loads((SKILL_ROOT / "fixtures" / fixture / "intake.json").read_text(encoding="utf-8"))
        n = intake.validate(payload)
        return checkout.order_form_mapping(n, route.compile_route(n), readback=readback)

    def test_a_test_only_readback_gives_three_accepted_instances(self):
        for fixture in ("seven-figure-preneur", "elevation"):  # folded_levels, multiple_options
            with self.subTest(fixture=fixture):
                mapping = self.mapping(fixture, TEST_ONLY_CHECKOUT_READBACK)
                self.assertEqual(mapping["realisation"], "per_offer_instances")
                self.assertEqual(mapping["checkout_mode"], "combined_single_offer")
                self.assertEqual(mapping["checkout_mode_state"], "resolved")
                self.assertEqual(len(mapping["instances"]), 3)
                self.assertEqual([i["validation"]["result"] for i in mapping["instances"]], ["accepted"] * 3)
                self.assertIs(mapping["delivery_blocked"], False)
                self.assertEqual(mapping["delivery_blockers"], [])

    def test_without_the_readback_delivery_is_blocked_by_named_rejections(self):
        for fixture in ("seven-figure-preneur", "elevation"):
            with self.subTest(fixture=fixture):
                mapping = self.mapping(fixture, None)
                self.assertEqual(mapping["realisation"], "per_offer_instances")
                self.assertIs(mapping["delivery_blocked"], True)
                self.assertTrue(mapping["delivery_blockers"])
                self.assertTrue(all(b.startswith("AF-LAUNCH-CHECKOUT-REJECTED")
                                    for b in mapping["delivery_blockers"]), mapping["delivery_blockers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
