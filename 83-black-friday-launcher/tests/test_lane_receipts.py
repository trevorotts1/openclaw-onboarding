"""Issue 1 (83 side): a unit another lane delivers is sealed only on its producer's contract.

Before the fix ``package._lane_receipt`` accepted any three non-empty strings
(``{"lane": "x", "contract": "y", "state": "passed"}``) as the producing lane's validation, so a hand-written
file sealed an email or a text as delivered. Now the contract id must be the one that unit type's producer
writes (email: Skill 50, text and automation: Skill 44), and an email is also re-verified by Skill 50's own
``validate_delivery.py --check`` run by path at assemble and again at ``check``; an absent validator is a
refusal, never a pass.

These tests run Skill 83 against ``lane83_stand_in_validate_delivery.py`` (the real validator is Skill 50's
tool). The contract spellings and the validator path are literals here on purpose.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lane83_stand_in_validate_delivery as stand_in  # noqa: E402
from launcher_core import checks, constants, council, intake, package, route  # noqa: E402
from launcher_core.check_rules import delivery_units as du  # noqa: E402
from test_delivery_units import (EMAIL_VALIDATOR_PATH, LANE_CONTRACT_IDS,  # noqa: E402
                                 install_stand_in_validator, qc_artifact, with_sales_piece)
from test_launch_plan_law import (lane_deliveries, pieces_for, plan_fixture, plan_intake,  # noqa: E402
                                  stub_council)

SELF_DECLARED = {"lane": "x", "contract": "y", "state": "passed"}
LANE_CODE = "AF-LAUNCH-PKG-RECEIPT-LANE"


class LaneReceiptTests(unittest.TestCase):
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
        self.email = self.plan["email_sequences"][0]["id"]
        self.text = self.plan["text_sets"][0]["id"]

    def assemble(self, deliveries=None):
        return package.assemble(self.run_dir, self.normalized, self.graph, self.pieces, council=self.advice,
                                launch_plan=self.plan, deliveries=deliveries or self.deliveries)

    def refused(self, deliveries=None, code=LANE_CODE) -> str:
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(deliveries)
        self.assertEqual(ctx.exception.code, code, ctx.exception)
        self.assertFalse((self.run_dir / "receipt.json").exists())
        return str(ctx.exception)

    def leftovers(self):
        return sorted(p.name for p in self.run_dir.glob(".lane-check-*"))

    # ---- the control: the producers' own contracts assemble, and check agrees --------------------
    def test_a_launch_whose_lanes_carry_their_producers_contracts_assembles_and_checks_clean(self):
        out = self.assemble()
        rows = {r["unit_id"]: r for r in out["receipt"]["units"]}
        self.assertEqual(rows[self.email]["lane_validation"]["contract"], LANE_CONTRACT_IDS["email"])
        self.assertEqual(rows[self.text]["lane_validation"]["contract"], LANE_CONTRACT_IDS["text"])
        self.assertEqual(rows[self.plan["automations"][0]["id"]]["lane_validation"]["contract"],
                         LANE_CONTRACT_IDS["automation"])
        self.assertEqual(checks.check_package(Path(out["manifest_path"]), self.run_dir), [])
        self.assertEqual(self.leftovers(), [])

    # ---- the allow-list ---------------------------------------------------------------------------
    def test_a_self_declared_email_or_text_contract_is_refused(self):
        for unit_id, kind in ((self.email, "email"), (self.text, "text")):
            with self.subTest(kind):
                deliveries = copy.deepcopy(self.deliveries)
                deliveries[unit_id]["lane_validation"] = dict(SELF_DECLARED)
                message = self.refused(deliveries)
                self.assertIn(unit_id, message)
                self.assertIn(LANE_CONTRACT_IDS[kind], message)

    def test_one_unit_types_contract_does_not_pass_for_another(self):
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[self.email]["lane_validation"]["contract"] = LANE_CONTRACT_IDS["text"]
        self.assertIn(LANE_CONTRACT_IDS["email"], self.refused(deliveries))
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[self.text]["lane_validation"]["contract"] = LANE_CONTRACT_IDS["email"]
        self.assertIn(LANE_CONTRACT_IDS["text"], self.refused(deliveries))

    # ---- no producer yet (question WP-06a-3): a page another lane delivers and the Conversation AI ----
    def test_a_page_or_conversation_ai_has_no_producer_so_no_lane_delivery_seals_it(self):
        for unit_type in ("page", "conversation_ai"):
            for lane in (SELF_DECLARED, {"lane": "S50", "contract": LANE_CONTRACT_IDS["email"], "state": "passed"}):
                with self.subTest(unit_type=unit_type, contract=lane["contract"]):
                    fails = du.lane_contract_violations("u", unit_type, lane)
                    self.assertEqual(len(fails), 1, fails)
                    self.assertIn("no producer yet", fails[0])
                    self.assertTrue(fails[0].startswith(LANE_CODE))

    def test_a_requested_conversation_ai_delivered_by_a_lane_is_refused(self):
        self.plan = copy.deepcopy(self.plan)
        self.plan["conversation_ai"] = {"requested": True, "mode": "faq", "channels": ["sms"]}
        self.deliveries = lane_deliveries(self.plan, self.run_dir)
        self.assertEqual(self.deliveries["conversation_ai"]["lane_validation"]["contract"], "lane.output.v1")
        message = self.refused()
        self.assertIn("conversation_ai", message)
        self.assertIn("no producer yet", message)

    def test_a_plan_page_no_launcher_piece_carries_is_refused_even_with_a_lane_delivery(self):
        self.pieces = {slot: piece for slot, piece in self.pieces.items() if slot != "sales"}
        self.assertIn("lane_validation", self.deliveries["page_sales"])
        message = self.refused()
        self.assertIn("page_sales", message)
        self.assertIn("no producer yet", message)

    def test_check_refuses_a_page_row_another_lane_declared(self):
        _, manifest = self.sealed()
        receipt_path = self.run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for row in receipt["units"]:
            if row["unit_id"] == "page_sales":
                row.update(delivery="declared", lane_validation=dict(SELF_DECLARED))
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        fails = checks.check_package(manifest, self.run_dir)
        self.assertTrue(any(f.startswith(LANE_CODE) and "page_sales" in f and "no producer yet" in f
                            for f in fails), fails)

    def test_a_certificate_is_sealed_only_when_it_is_64_lowercase_hex(self):
        cases = {"a" * 64: True, "A" * 64: False, "not-a-hash": False, "a" * 63: False, 5: False}
        texts = [t["id"] for t in self.plan["text_sets"]]
        self.assertGreaterEqual(len(texts), len(cases))
        deliveries = copy.deepcopy(self.deliveries)
        for unit_id, value in zip(texts, cases):
            deliveries[unit_id]["lane_validation"]["certificate_sha256"] = value
        rows = {r["unit_id"]: r for r in self.assemble(deliveries)["receipt"]["units"]}
        for unit_id, (value, kept) in zip(texts, cases.items()):
            with self.subTest(certificate=value):
                lane = rows[unit_id]["lane_validation"]
                self.assertEqual("certificate_sha256" in lane, kept, lane)
                if kept:
                    self.assertEqual(lane["certificate_sha256"], value)

    def test_a_lane_detail_is_carried_into_the_sealed_row_and_its_absence_is_not_invented(self):
        other = next(t["id"] for t in self.plan["text_sets"] if t["id"] != self.text)
        self.assertNotIn("detail", self.deliveries[other]["lane_validation"])
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[self.text]["lane_validation"]["detail"] = "three sets checked"
        rows = {r["unit_id"]: r for r in self.assemble(deliveries)["receipt"]["units"]}
        self.assertEqual(rows[self.text]["lane_validation"]["detail"], "three sets checked")
        self.assertNotIn("detail", rows[other]["lane_validation"])

    def test_the_receipt_schema_types_the_certificate_as_64_lowercase_hex(self):
        # receipt.schema.json is the published contract for the sealed row; launcher_core never loads it
        # (package.py and checks.py enforce the row in code, see the test above), so this test is what
        # keeps the certificate_sha256 property it carries from drifting.
        import jsonschema
        schema = json.loads((SKILL_ROOT / "receipt.schema.json").read_text(encoding="utf-8"))
        rule = jsonschema.Draft7Validator({"$ref": "#/definitions/unit_receipt", "definitions": schema["definitions"]})
        row = next(r for r in self.assemble()["receipt"]["units"] if r["unit_id"] == self.email)
        self.assertEqual(row["lane_validation"]["certificate_sha256"],
                         self.deliveries[self.email]["lane_validation"]["certificate_sha256"])
        self.assertEqual(list(rule.iter_errors(row)), [], "the shape the launcher seals must satisfy its schema")
        for value, ok in (("a" * 64, True), ("0123456789abcdef" * 4, True), ("a" * 63, False), ("a" * 65, False),
                          ("", False), ("A" * 64, False), ("g" * 64, False), (" " + "a" * 63, False),
                          (5, False), (None, False), (["a" * 64], False)):
            with self.subTest(certificate=value):
                candidate = copy.deepcopy(row)
                candidate["lane_validation"]["certificate_sha256"] = value
                self.assertEqual(rule.is_valid(candidate), ok)
        prop = schema["definitions"]["unit_receipt"]["properties"]["lane_validation"]["properties"]["certificate_sha256"]
        self.assertEqual(prop["pattern"], package._SHA256_RE.pattern)

    # ---- the by-path re-check of Skill 50's own validator -----------------------------------------
    def test_the_right_contract_without_a_certificate_the_validator_accepts_is_refused(self):
        deliveries = copy.deepcopy(self.deliveries)
        del deliveries[self.email]["lane_validation"]["certificate_sha256"]
        self.assertIn("delivery validator refused", self.refused(deliveries))
        self.assertEqual(self.leftovers(), [])

    def test_a_certificate_issued_for_other_bytes_is_refused(self):
        other = next(u for u in self.plan["email_sequences"][1:])["id"]
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[self.email]["lane_validation"]["certificate_sha256"] = \
            deliveries[other]["lane_validation"]["certificate_sha256"]
        self.assertIn("delivery validator refused", self.refused(deliveries))

    def test_an_absent_validator_is_a_refusal_never_a_pass(self):
        real = constants.resolve_ref

        def gone(rel_path, root=None):
            if rel_path == EMAIL_VALIDATOR_PATH:
                raise constants.SkillResolutionError("no email-engine tree")
            return real(rel_path, root)

        with mock.patch.object(constants, "resolve_ref", gone):
            self.assertIn("is not installed", self.refused())
        missing = Path(self.tmp.name) / "tools" / "validate_delivery.py"
        with mock.patch.object(constants, "resolve_ref",
                               lambda rel, root=None: missing if rel == EMAIL_VALIDATOR_PATH else real(rel, root)):
            self.assertIn("is not installed", self.refused())

    def test_a_validator_that_exits_non_zero_or_cannot_start_is_a_refusal(self):
        real = constants.resolve_ref
        failing = Path(self.tmp.name) / "validate_delivery.py"
        failing.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        with mock.patch.object(constants, "resolve_ref",
                               lambda rel, root=None: failing if rel == EMAIL_VALIDATOR_PATH else real(rel, root)):
            self.assertIn("refused the receipt (exit 3)", self.refused())
        self.assertEqual(self.leftovers(), [])
        with mock.patch.object(du.subprocess, "run", side_effect=OSError("no interpreter")):
            self.assertIn("could not run", self.refused())
        self.assertEqual(self.leftovers(), [])

    def test_a_package_folder_that_cannot_be_written_cannot_be_re_verified(self):
        with mock.patch.object(du.tempfile, "mkstemp", side_effect=OSError("read-only")):
            self.assertIn("not writable", self.refused())

    # ---- check re-runs the same law on the sealed receipt -----------------------------------------
    def sealed(self):
        out = self.assemble()
        return out, Path(out["manifest_path"])

    def rewrite_row(self, edit):
        receipt_path = self.run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for row in receipt["units"]:
            if row["unit_id"] == self.email:
                edit(row)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_check_refuses_a_sealed_receipt_whose_contract_was_swapped_for_a_string(self):
        _, manifest = self.sealed()
        self.rewrite_row(lambda row: row.update(lane_validation=dict(SELF_DECLARED)))
        fails = checks.check_package(manifest, self.run_dir)
        self.assertTrue(any(f.startswith(LANE_CODE) and self.email in f for f in fails), fails)

    def test_check_re_runs_the_validator_on_the_sealed_row(self):
        _, manifest = self.sealed()
        self.rewrite_row(lambda row: row["lane_validation"].pop("certificate_sha256"))
        fails = checks.check_package(manifest, self.run_dir)
        self.assertTrue(any("delivery validator refused" in f and self.email in f for f in fails), fails)
        self.assertEqual(self.leftovers(), [])

    def test_check_refuses_an_email_artifact_changed_after_sealing(self):
        out, manifest = self.sealed()
        row = next(r for r in out["receipt"]["units"] if r["unit_id"] == self.email)
        (self.run_dir / row["artifacts"][0]["path"]).write_bytes(b"<html>changed after sealing</html>\n")
        fails = checks.check_package(manifest, self.run_dir)
        self.assertTrue(any(self.email in f and "hash" in f for f in fails), fails)
        self.assertTrue(any("delivery validator refused" in f and self.email in f for f in fails), fails)

    # ---- issue 33 at assemble: no QC result, no sealed automation ---------------------------------
    def test_an_automation_with_no_passing_qc_result_does_not_assemble(self):
        unit = self.plan["automations"][0]["id"]
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[unit]["artifacts"] = deliveries[unit]["artifacts"][:1]  # the export alone
        self.assertIn(f"qc-wf-{unit}.json", self.refused(deliveries, code=du.CODE_AUTOMATION))
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[unit]["artifacts"][1] = qc_artifact(self.run_dir, unit, exit_code=1)
        self.assertIn("QC did not pass", self.refused(deliveries, code=du.CODE_AUTOMATION))


class SkillDocLockstepTests(unittest.TestCase):
    """SKILL.md says what LANE_CONTRACTS enforces. Change one without the other and this fails."""

    DOC = " ".join((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split())
    # Each unit type's producer contract as SKILL.md spells it, found by the words that introduce it.
    DOC_CONTRACT = {
        "automation": r"an automation is Skill 44's build export \(`([\w.-]+)`",
        "email": r"an email sequence is the row .*? writes \(`([\w.-]+)`",
        "text": r"a text set is Skill 44's `([\w.-]+)`",
    }
    DOC_NO_PRODUCER = r"A page another lane delivers and the Conversation AI have no producer contract yet"

    def test_every_contract_the_doc_names_is_the_one_the_rule_allows(self):
        for unit_type, pattern in self.DOC_CONTRACT.items():
            with self.subTest(unit_type):
                found = re.search(pattern, self.DOC)
                self.assertIsNotNone(found, f"SKILL.md no longer names the {unit_type} producer contract")
                self.assertEqual((found.group(1),), du.LANE_CONTRACTS[unit_type])
        documented = set(re.findall(r"`(skill\d+\.[a-z-]+\.v\d+)`", self.DOC))
        allowed = {c for contracts in du.LANE_CONTRACTS.values() for c in contracts}
        self.assertEqual(documented, allowed)

    def test_the_doc_and_the_rule_agree_on_which_unit_types_have_no_producer(self):
        self.assertEqual({t for t, contracts in du.LANE_CONTRACTS.items() if not contracts},
                         {"page", "conversation_ai"})
        self.assertRegex(self.DOC, self.DOC_NO_PRODUCER)
        self.assertNotIn("keep their existing rule", self.DOC)
        self.assertEqual(set(du.LANE_CONTRACTS), {"email", "text", "automation", "page", "conversation_ai"})

    def test_the_refusal_text_the_doc_quotes_is_the_refusal_the_rule_gives(self):
        for unit_type in ("page", "conversation_ai"):
            fails = du.lane_contract_violations("u", unit_type, {"contract": "anything"})
            self.assertIn("has no producer yet", fails[0])
            self.assertTrue(fails[0].startswith(LANE_CODE))
        self.assertIn(f"`{LANE_CODE}` (\"has no producer yet\")", self.DOC)


class StandInContractTests(unittest.TestCase):
    """The stand-in must discriminate, or every test above would pass against a validator that accepts all."""

    def run_check(self, root: Path, document: dict) -> int:
        import subprocess
        path = root / "r.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return subprocess.run([sys.executable, "-I", stand_in.__file__, "--check", str(path)],
                              capture_output=True, cwd=str(root)).returncode

    def test_it_accepts_only_a_receipt_whose_artifacts_and_certificate_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.html").write_bytes(b"<html>a</html>\n")
            arts = [{"path": "a.html", "sha256": hashlib.sha256(b"<html>a</html>\n").hexdigest(), "size": 15}]
            good = {"artifacts": arts, "lane_validation": {
                "lane": "S50", "contract": LANE_CONTRACT_IDS["email"], "state": "passed",
                "certificate_sha256": stand_in.certificate(arts)}}
            self.assertEqual(self.run_check(root, good), 0)
            bad_cert = copy.deepcopy(good)
            bad_cert["lane_validation"]["certificate_sha256"] = "0" * 64
            self.assertNotEqual(self.run_check(root, bad_cert), 0)
            self.assertNotEqual(self.run_check(root, {**good, "lane_validation": dict(SELF_DECLARED)}), 0)
            (root / "a.html").write_bytes(b"<html>changed</html>\n")
            self.assertNotEqual(self.run_check(root, good), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
