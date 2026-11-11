"""emit_checkout_manuscript.py (issue 12): the order form's copy comes from the approved checkout request.

The manuscript is the one money-bearing page copy; nobody types its price. These cases run the real emitter as a
subprocess and then the real Skill 49 checkout wrapper's CHK-13 check over what it wrote.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL = HERE.parents[1]
REPO = HERE.parents[2]
EMITTER = SKILL / "scripts" / "emit_checkout_manuscript.py"
sys.path.insert(0, str(REPO / "49-signature-funnel" / "scripts"))

TERMS = {"guarantee_text": "Try it for 30 days. If it is not right for you, ask for your money back.",
         "terms_text": "By placing this order you agree to the terms of sale.",
         "consent_text": "I agree to the terms of sale.",
         "guarantee_ref": "G", "terms_ref": "T", "consent_ref": "C"}


def price(amount, currency="USD", billing="one_time"):
    return {"price_choice_id": "x", "amount_minor": amount, "currency": currency, "billing_type": billing}


def launch_fixture(currency="USD"):
    def offer(oid, slot, name, amount, deliverables, exclusions=()):
        return {"offer_id": oid, "slot": slot, "display_name": name, "deliverables": list(deliverables),
                "exclusions": list(exclusions), "prices": [price(amount, currency)]}
    return {"offers": [offer("MAIN", "main", "Monthly Planning Studio", 9700, ["a weekly session", "a planner"],
                             ["one-to-one coaching"]),
                       offer("BUMP", "bump", "Quick-Start Template Pack", 2700, ["ten templates"])]}


def request(currency="USD", with_bump=True, billing="one_time"):
    return {"main_offer_id": "MAIN", "main_price": price(9700, currency, billing),
            "bump": {"offer_id": "BUMP", "price": price(2700, currency), "headline": "Start faster",
                     "benefit_explanation": "Ten ready-to-use templates."} if with_bump else None}


class EmitCheckoutManuscriptTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s79-emit-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))

    def emit(self, req=None, launch_doc=None, terms=None):
        files = {"request.json": req or request(), "launch.json": launch_doc or launch_fixture(),
                 "terms.json": {"checkout_terms": terms or TERMS}}
        for name, doc in files.items():
            (self.td / name).write_text(json.dumps(doc), encoding="utf-8")
        self.out = self.td / "copy-checkout.md"
        return subprocess.run([sys.executable, str(EMITTER), "--request", str(self.td / "request.json"),
                               "--launch", str(self.td / "launch.json"), "--checkout-terms", str(self.td / "terms.json"),
                               "--out", str(self.out)], capture_output=True, text=True, timeout=120)

    def test_it_writes_the_five_sections_stamped_with_the_requests_sha(self):
        proc = self.emit()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.out.read_text(encoding="utf-8")
        digest = hashlib.sha256((self.td / "request.json").read_bytes()).hexdigest()
        self.assertIn(f"<!-- source_request_sha256: {digest} -->", text)
        for n in range(1, 6):
            self.assertIn(f"## Section {n}:", text)
        self.assertIn("Monthly Planning Studio, one payment of $97.00.", text)
        self.assertIn("Yes, add the Quick-Start Template Pack to my order.", text)
        self.assertIn("One-time price of $27.00.", text)
        self.assertIn(TERMS["guarantee_text"], text)
        self.assertIn("It does not include one-to-one coaching.", text)

    def test_what_it_writes_passes_the_wrappers_chk_13_and_its_stamp_check(self):
        import checkout_wrapper as cw
        proc = self.emit()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.out.read_text(encoding="utf-8")
        cw.check_copy(text, {"offers": [dict(o, slot=o["slot"]) for o in launch_fixture()["offers"]]}, {}, TERMS)
        cw.check_source_stamp(text, self.td / "request.json")
        (self.td / "request.json").write_text(json.dumps(request(with_bump=False)), encoding="utf-8")
        with self.assertRaises(cw.WrapperError):  # the request moved on after the copy was written
            cw.check_source_stamp(text, self.td / "request.json")

    def test_a_euro_launch_is_written_in_euro(self):
        proc = self.emit(req=request("EUR"), launch_doc=launch_fixture("EUR"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("€97.00", self.out.read_text(encoding="utf-8"))
        self.assertNotIn("$", self.out.read_text(encoding="utf-8"))

    def test_no_bump_means_no_section_3(self):
        proc = self.emit(req=request(with_bump=False))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.out.read_text(encoding="utf-8")
        self.assertNotIn("## Section 3", text)
        self.assertNotIn("Quick-Start", text)

    def test_a_missing_fact_refuses_by_name_and_leaves_no_file(self):
        cases = {
            "an installment price": dict(req=request(billing="installment")),
            "no deliverables": dict(launch_doc={"offers": [dict(o, deliverables=[]) for o in launch_fixture()["offers"]]}),
            "an unnamed main offer": dict(launch_doc={"offers": [dict(o, display_name="") for o in launch_fixture()["offers"]]}),
            "no consent text": dict(terms={k: v for k, v in TERMS.items() if k != "consent_text"}),
            "blank consent text": dict(terms=dict(TERMS, consent_text="   ")),
            "a zero price": dict(req=dict(request(), main_price=price(0))),
            "a true for a price": dict(req=dict(request(), main_price=price(True))),
        }
        for label, kw in cases.items():
            with self.subTest(label):
                (self.td / "copy-checkout.md").write_text("stale", encoding="utf-8")
                proc = self.emit(**kw)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertIn("FAIL-CLOSED", proc.stderr)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
