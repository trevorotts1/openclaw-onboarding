#!/usr/bin/env python3
"""test_launch_email_profiles.py: UL-007 — one profile registry, seven families.

Proves, against the real tools (never a copy of their constants):
  (a) the registry defines all seven planned families, each with its own
      count, paired variants, purpose and timing;
  (b) all seven families pass their OWN profile checks from ONE approved
      intake (the adapter's launch-plan mode -> one locked brief per family,
      each brief passing the prover);
  (c) a wrong family, a wrong count and a missing message FAIL;
  (d) non-main paired subject/preview variants SURVIVE emission and a saved-
      draft read-back (JSON save + load), with no legacy flattened `ab` block;
  (e) the L01 session consumer records an absent contract explicitly (with
      the blocked acceptance) and, when a contract is present, validates the
      declared typed fields — a string "No" is never accepted as a boolean.

Hermetic: fictional fixtures only, no network, no provider call, all writes in
a temp directory. Exit 0 = all tests pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
TOOLS = SKILL_DIR / "tools"
sys.path.insert(0, str(TOOLS))

import launch_intake_adapter as adapter  # noqa: E402
import launch_profiles  # noqa: E402

PROVER = TOOLS / "prove-email.py"
EMITTER = TOOLS / "emit_build_plan.py"
EMITTER_MODULE = TOOLS / "emit_build_plan.py"
GOLDEN_SIG = SKILL_DIR / "examples" / "golden-signature-launch-10"
FOUNDER = "Jordan Marsh"

REGISTRY = launch_profiles.load_registry()
FAMILIES = launch_profiles.families(REGISTRY)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], capture_output=True,
                          text=True)


def _body(words: int, cta: str) -> str:
    text = " ".join(["value"] * max(1, words - 6))
    paras = [" ".join(text.split()[i:i + 30]) for i in range(0, len(text.split()), 30)]
    return ("{{contact.first_name}},\n\n" + "\n\n".join(p + "." for p in paras)
            + "\n\n" + cta + "\n\n" + FOUNDER)


def _emails_for(fam):
    """A valid synthetic sequence for one family, built from the registry."""
    emails = []
    for slot in range(1, fam["email_count"] + 1):
        band = launch_profiles.word_band(fam, slot)
        cta_floor = launch_profiles.cta_floor(fam, slot)
        ctas = ["[Take step %d ->]" % (n + 1) for n in range(cta_floor)]
        body = _body(90 if band[1] < 150 else 200, ctas[0])
        emails.append({
            "e_slot": slot,
            "framework": fam["framework_map"][str(slot)],
            "objective": fam["objective"],
            "subjects": ["{{contact.first_name}}, the quiet cost of waiting a week",
                         "Everyone booked it but you last call now"],
            "previews": ["Pair A preview line %d" % slot,
                         "Pair B disruptive preview line %d" % slot][:fam["preview_count"]],
            "body": body,
            "ctas": ctas,
        })
    return {"sequence_type": fam["profile"], "profile": fam["profile"],
            "sequence_id": fam["sequence_id"], "founder_name": FOUNDER,
            "emails": emails}


class LaunchEmailProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.fx = adapter.build_fixtures()
        self._saved_session_path = adapter._session_contract_path

    def tearDown(self) -> None:
        adapter._session_contract_path = self._saved_session_path
        self._tmp.cleanup()

    def _write(self, name: str, doc) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return path

    def _briefs(self):
        plan = adapter.build_launch_plan_fixture()
        return adapter.adapt_launch_plan(
            self.fx["session"], self.fx["launch"], self.fx["approval"],
            self.fx["brand_facts"], self.fx["landing_facts"], plan,
            worker_identity_ref=self.fx["worker_identity_ref"])

    # (a) ------------------------------------------------------------------
    def test_registry_defines_all_seven_families(self) -> None:
        self.assertEqual(len(FAMILIES), 7)
        self.assertEqual(set(FAMILIES), set(launch_profiles.PLANNED_KINDS))
        for kind, fam in FAMILIES.items():
            self.assertTrue(fam["purpose"], kind)
            self.assertTrue(fam["timing"]["anchor"], kind)
            self.assertIn("wait_after_hours", fam["timing"], kind)
            self.assertEqual(fam["subject_count"], 2, kind)
            self.assertIn(fam["preview_count"], (1, 2), kind)
            self.assertEqual(
                sorted(int(k) for k in fam["framework_map"]),
                list(range(1, fam["email_count"] + 1)), kind)
            self.assertTrue(fam["eligibility"], kind)
            self.assertTrue(fam["lifecycle"]["stop_rules"], kind)
            self.assertIn("required_refs", fam["sender"], kind)

    # (b) ------------------------------------------------------------------
    def test_all_seven_families_pass_from_one_approved_intake(self) -> None:
        briefs = self._briefs()
        self.assertEqual(len(briefs), 7)
        self.assertEqual({b["kind"] for b in briefs}, set(FAMILIES))
        for item in briefs:
            fam = FAMILIES[item["kind"]]
            brief = item["brief"]
            self.assertEqual(brief["family"]["profile"], fam["profile"])
            self.assertEqual(brief["answers"]["sequence_position"],
                             fam["sequence_position"])
            brief_path = self._write("BRIEF-%s.json" % item["sequence_id"],
                                     brief)
            gate = _run(str(PROVER), str(brief_path), "--kind", "intake")
            self.assertEqual(gate.returncode, 0,
                             "%s brief: %s%s" % (item["kind"], gate.stdout,
                                                 gate.stderr))

    def test_each_family_sequence_passes_its_own_profile_checks(self) -> None:
        briefs = {b["kind"]: b["brief"] for b in self._briefs()}
        for kind, fam in FAMILIES.items():
            brief_path = self._write("B-%s.json" % kind, briefs[kind])
            if kind == "main_launch":
                emails_path = GOLDEN_SIG / "emails.json"
            else:
                emails_path = self._write("E-%s.json" % kind,
                                          _emails_for(fam))
            gate = _run(str(PROVER), str(emails_path), "--kind", "sequence",
                        "--brief", str(brief_path))
            self.assertEqual(gate.returncode, 0,
                             "%s sequence: %s%s" % (kind, gate.stdout,
                                                    gate.stderr))

    # (c) ------------------------------------------------------------------
    def test_wrong_family_fails(self) -> None:
        briefs = {b["kind"]: b["brief"] for b in self._briefs()}
        brief = json.loads(json.dumps(briefs["pre_launch"]))
        brief["family"]["profile"] = FAMILIES["doors_closing"]["profile"]
        path = self._write("wrong-family.json", brief)
        gate = _run(str(PROVER), str(path), "--kind", "intake", "--json")
        self.assertEqual(gate.returncode, 2, gate.stdout)
        self.assertIn("AF-EMAIL-TYPE-MISMATCH", gate.stdout)

    def test_wrong_count_fails_in_adapter_and_prover(self) -> None:
        plan = adapter.build_launch_plan_fixture()
        plan["email_sequences"][3]["email_count"] += 1
        with self.assertRaises(adapter.Refusal):
            adapter.adapt_launch_plan(
                self.fx["session"], self.fx["launch"], self.fx["approval"],
                self.fx["brand_facts"], self.fx["landing_facts"], plan,
                worker_identity_ref=self.fx["worker_identity_ref"])
        fam = FAMILIES["doors_closing"]
        ledger = _emails_for(fam)
        ledger["emails"] = ledger["emails"][:-1]
        path = self._write("short.json", ledger)
        gate = _run(str(PROVER), str(path), "--kind", "sequence", "--json")
        self.assertEqual(gate.returncode, 2, gate.stdout)
        self.assertIn("AF-EMAIL-SEQUENCE-LENGTH", gate.stdout)

    def test_missing_message_fails(self) -> None:
        fam = FAMILIES["abandoned_checkout"]
        ledger = _emails_for(fam)
        del ledger["emails"][1]["body"]
        ledger["emails"][1]["body"] = ""
        path = self._write("missing-body.json", ledger)
        gate = _run(str(PROVER), str(path), "--kind", "sequence", "--json")
        self.assertEqual(gate.returncode, 2, gate.stdout)

    # (d) ------------------------------------------------------------------
    def test_non_main_paired_variants_survive_emission_and_readback(self) -> None:
        briefs = {b["kind"]: b["brief"] for b in self._briefs()}
        for kind, fam in FAMILIES.items():
            brief_path = self._write("EB-%s.json" % kind, briefs[kind])
            if kind == "main_launch":
                emails_doc = json.loads(
                    (GOLDEN_SIG / "emails.json").read_text(encoding="utf-8"))
            else:
                emails_doc = _emails_for(fam)
            emails_path = self._write("EE-%s.json" % kind, emails_doc)
            out = self.dir / ("PLAN-%s.json" % kind)
            proc = _run(str(EMITTER), "--brief", str(brief_path),
                        "--emails", str(emails_path), "--out", str(out),
                        "--folder", "Email Engine — Test")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            # SAVED-DRAFT READ-BACK: read the plan back from disk.
            plan = json.loads(out.read_text(encoding="utf-8"))
            slug = [k for k in plan if k not in ("folder", "_meta")][0]
            steps = [s for s in plan[slug]["templates"] if s["type"] == "email"]
            self.assertEqual(len(steps), fam["email_count"], kind)
            for step, email in zip(steps, emails_doc["emails"]):
                self.assertNotIn("ab", step, kind)
                pairs = step["variant_pairs"]
                self.assertEqual(pairs["A"]["subject"], email["subjects"][0])
                self.assertEqual(pairs["A"]["preview"], email["previews"][0])
                self.assertEqual(pairs["B"]["subject"], email["subjects"][1])
                expected_b_preview = (email["previews"][1]
                                      if fam["preview_count"] > 1
                                      else email["previews"][0])
                self.assertEqual(pairs["B"]["preview"], expected_b_preview)
            meta = plan["_meta"]
            self.assertEqual(meta["family"], kind)
            self.assertEqual(meta["profile"], fam["profile"])
            self.assertEqual(meta["variant_strategy"]["previews_per_pair"],
                             fam["preview_count"])
            self.assertEqual(meta["expected_email_count"], fam["email_count"])
            self.assertEqual(meta["timing_anchors"]["anchor_event"],
                             fam["timing"]["anchor"])
            self.assertTrue(meta["eligibility"])
            self.assertTrue(meta["lifecycle"]["stop_rules"])
            self.assertTrue(meta["sender"])
            self.assertTrue(meta["sender_config_refs"]["sender_profile_ref"])
            self.assertTrue(meta["draft_only"])
            self.assertEqual(plan[slug]["status"], "draft")

    # (e) ------------------------------------------------------------------
    def test_session_contract_absent_is_recorded_not_invented(self) -> None:
        adapter._session_contract_path = lambda: None
        brief = adapter.adapt(
            self.fx["session"], self.fx["launch"], self.fx["approval"],
            self.fx["brand_facts"], self.fx["landing_facts"],
            worker_identity_ref=self.fx["worker_identity_ref"])
        sc = brief["session_contract"]
        self.assertEqual(sc["state"], "absent")
        self.assertIn("blocked_acceptance", sc)
        self.assertIn("typed_metadata", sc)

    def test_session_contract_present_is_consumed_typed(self) -> None:
        contract = {
            "contract": "signature-launch-session",
            "contract_version": "1.0",
            "required_answers": [adapter.s49.LEDGER_PAINS],
            "typed_fields": {"email_consent": {"type": "boolean"},
                             "confirmed_at": {"type": "timestamp"}},
        }
        path = self._write("session_contract.json", contract)
        adapter._session_contract_path = lambda: path
        session = json.loads(json.dumps(self.fx["session"]))
        session["answers"]["email_consent"] = True
        session["answers"]["confirmed_at"] = "2026-10-15T14:30:00+00:00"
        brief = adapter.adapt(
            session, self.fx["launch"], self.fx["approval"],
            self.fx["brand_facts"], self.fx["landing_facts"],
            worker_identity_ref=self.fx["worker_identity_ref"])
        sc = brief["session_contract"]
        self.assertEqual(sc["state"], "consumed")
        self.assertIs(sc["typed"]["email_consent"], True)
        self.assertEqual(sc["typed_metadata"]["sender"]["required_refs"],
                         ["sender_profile_ref", "reply_to_ref"])

    def test_session_contract_never_coerces_a_string_boolean(self) -> None:
        contract = {
            "contract": "signature-launch-session",
            "contract_version": "1.0",
            "typed_fields": {"email_consent": {"type": "boolean"}},
        }
        path = self._write("session_contract_bad.json", contract)
        adapter._session_contract_path = lambda: path
        session = json.loads(json.dumps(self.fx["session"]))
        session["answers"]["email_consent"] = "No"  # the defect class
        with self.assertRaises(adapter.Refusal):
            adapter.adapt(
                session, self.fx["launch"], self.fx["approval"],
                self.fx["brand_facts"], self.fx["landing_facts"],
                worker_identity_ref=self.fx["worker_identity_ref"])

    def test_session_contract_version_is_checked(self) -> None:
        path = self._write("session_contract_v2.json",
                           {"contract": "signature-launch-session",
                            "contract_version": "2.0"})
        adapter._session_contract_path = lambda: path
        with self.assertRaises(adapter.Refusal):
            adapter.adapt(
                self.fx["session"], self.fx["launch"], self.fx["approval"],
                self.fx["brand_facts"], self.fx["landing_facts"],
                worker_identity_ref=self.fx["worker_identity_ref"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
