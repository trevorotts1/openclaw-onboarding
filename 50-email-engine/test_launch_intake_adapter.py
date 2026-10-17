#!/usr/bin/env python3
"""test_launch_intake_adapter.py: S50-04 shared-launch intake adapter tests.

Proves, in the engine's existing test style:
  (a) a valid launch intake adapts to a locked brief that passes the
      prover's intake gate, and the golden Signature Launch emails pass
      against that adapted brief;
  (b) fabricated or unprovenanced inputs are refused: a launch brief
      claiming the launch path without provenance fails the prover with
      AF-EMAIL-LAUNCH-PROVENANCE, and the adapter refuses a session whose
      only approval evidence is a bare flag, a tampered plan, a revoked
      approval, worker self-approval, and facts without provenance;
  (c) the legacy intake contract is untouched (its bytes do not change
      across an adapter run) and its authority test still passes, and the
      legacy-style golden briefs still pass the prover.

Hermetic: fixtures come from launch_intake_adapter.build_fixtures()
(fictional, aligned with examples/golden-signature-launch-10) and all
writes happen in a temp directory. Exit 0 = all tests pass.
"""

from __future__ import annotations

import hashlib
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
import s49_launch_shape as s49  # noqa: E402

PROVER = TOOLS / "prove-email.py"
ADAPTER_CLI = TOOLS / "launch_intake_adapter.py"
LEGACY_CONTRACT = SKILL_DIR / "intake" / "email-intake-questions.json"
GOLDEN_SIG = SKILL_DIR / "examples" / "golden-signature-launch-10"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], capture_output=True,
                          text=True)


class LaunchIntakeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.fx = adapter.build_fixtures()
        self.paths = {}
        for name in ("session", "launch", "approval", "brand_facts",
                     "landing_facts"):
            p = self.dir / f"{name}.json"
            p.write_text(json.dumps(self.fx[name], indent=2),
                         encoding="utf-8")
            self.paths[name] = p
        self.legacy_contract_hash_before = hashlib.sha256(
            LEGACY_CONTRACT.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _adapt_cli(self, out_name: str = "brief.json",
                   worker: str | None = None) -> subprocess.CompletedProcess:
        args = [str(ADAPTER_CLI),
                "--session", str(self.paths["session"]),
                "--launch", str(self.paths["launch"]),
                "--approval", str(self.paths["approval"]),
                "--brand-facts", str(self.paths["brand_facts"]),
                "--landing-facts", str(self.paths["landing_facts"]),
                "--out", str(self.dir / out_name)]
        if worker is not None:
            args += ["--worker-identity", worker]
        return _run(*args)

    def _rewrite(self, name: str, doc) -> None:
        self.paths[name].write_text(json.dumps(doc, indent=2),
                                    encoding="utf-8")

    # (a) ------------------------------------------------------------------
    def test_valid_launch_brief_adapts_and_passes_prover(self) -> None:
        proc = self._adapt_cli(worker=self.fx["worker_identity_ref"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        brief_path = self.dir / "brief.json"
        self.assertTrue(brief_path.is_file())
        gate = _run(str(PROVER), str(brief_path))
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        emails = _run(str(PROVER), str(GOLDEN_SIG / "emails.json"),
                      "--brief", str(brief_path))
        self.assertEqual(emails.returncode, 0,
                         emails.stdout + emails.stderr)

    def test_emitted_brief_shape_and_provenance(self) -> None:
        brief = adapter.adapt(
            self.fx["session"], self.fx["launch"], self.fx["approval"],
            self.fx["brand_facts"], self.fx["landing_facts"],
            worker_identity_ref=self.fx["worker_identity_ref"])
        self.assertEqual(brief["kind"], "brief")
        self.assertEqual(brief["intake_mode"], "signature_launch")
        for fabricated in ("asked_all_at_once", "one_question_per_turn",
                           "question_block_msg_id", "conversation_ledger"):
            self.assertNotIn(fabricated, brief)
        prov = brief["launch_provenance"]
        self.assertEqual(prov["plan_hash"],
                         s49.plan_document_hash(self.fx["launch"]))
        self.assertEqual(prov["approval"]["subject_hash"], prov["plan_hash"])
        self.assertEqual(prov["approval"]["subject_type"],
                         "launch_plan_build")
        self.assertEqual(
            prov["fields"]["testimonial_evidence"]["state"],
            "not_applicable")
        self.assertEqual(brief["answers"]["founder_name"], "Jordan Marsh")
        self.assertEqual(brief["answers"]["sequence_position"],
                         "signature-launch-landing-10")
        for entry in prov["fields"].values():
            self.assertTrue(entry["source_ref"])

    # (b) ------------------------------------------------------------------
    def test_launch_brief_without_provenance_fails_prover(self) -> None:
        brief = adapter.adapt(
            self.fx["session"], self.fx["launch"], self.fx["approval"],
            self.fx["brand_facts"], self.fx["landing_facts"],
            worker_identity_ref=self.fx["worker_identity_ref"])
        del brief["launch_provenance"]
        path = self.dir / "stripped-brief.json"
        path.write_text(json.dumps(brief), encoding="utf-8")
        gate = _run(str(PROVER), str(path), "--json")
        self.assertEqual(gate.returncode, 2, gate.stdout)
        self.assertIn("AF-EMAIL-LAUNCH-PROVENANCE", gate.stdout)

    def test_bare_approved_flag_is_not_evidence(self) -> None:
        session = json.loads(json.dumps(self.fx["session"]))
        session["status"] = "collecting"
        session["approved"] = True  # a fabricated flag changes nothing
        self._rewrite("session", session)
        proc = self._adapt_cli()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("REFUSAL", proc.stdout)

    def test_tampered_plan_is_refused(self) -> None:
        launch = json.loads(json.dumps(self.fx["launch"]))
        launch["offers"][0]["display_name"] = "The Renamed Method"
        self._rewrite("launch", launch)
        proc = self._adapt_cli()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("REFUSAL", proc.stdout)

    def test_revoked_approval_is_refused(self) -> None:
        approval = json.loads(json.dumps(self.fx["approval"]))
        approval["revoked"] = True
        self._rewrite("approval", approval)
        proc = self._adapt_cli()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("revoked", proc.stdout)

    def test_worker_self_approval_is_refused(self) -> None:
        proc = self._adapt_cli(worker=self.fx["client_identity_ref"])
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("REFUSAL", proc.stdout)

    def test_facts_without_provenance_are_refused(self) -> None:
        landing = json.loads(json.dumps(self.fx["landing_facts"]))
        del landing["provenance"]
        self._rewrite("landing_facts", landing)
        proc = self._adapt_cli()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("provenance", proc.stdout)

    def test_deadline_without_provenance_is_refused(self) -> None:
        landing = json.loads(json.dumps(self.fx["landing_facts"]))
        landing["landing"]["deadline"] = {
            "statement": "Enrollment closes Thursday.",
            "when_provenance": "none",
        }
        self._rewrite("landing_facts", landing)
        proc = self._adapt_cli()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("deadline", proc.stdout)

    def test_unknown_state_answer_is_refused(self) -> None:
        session = json.loads(json.dumps(self.fx["session"]))
        session["answers"][s49.LEDGER_PAINS]["state"] = "unknown"
        self._rewrite("session", session)
        proc = self._adapt_cli()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("REFUSAL", proc.stdout)

    # (c) ------------------------------------------------------------------
    def test_legacy_contract_untouched_and_authority_passes(self) -> None:
        proc = self._adapt_cli(worker=self.fx["worker_identity_ref"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        after = hashlib.sha256(LEGACY_CONTRACT.read_bytes()).hexdigest()
        self.assertEqual(after, self.legacy_contract_hash_before)
        contract = json.loads(LEGACY_CONTRACT.read_text(encoding="utf-8"))
        required = tuple(
            str(q.get("storeOn") or q.get("id"))
            for q in contract["questions"] if q.get("required") is True)
        self.assertEqual(
            required,
            ("objective", "buyer_type", "offer", "brand_voice",
             "sequence_position", "founder_name"))
        authority = _run(str(SKILL_DIR / "test_intake_contract_authority.py"))
        self.assertEqual(authority.returncode, 0,
                         authority.stdout + authority.stderr)

    def test_legacy_style_golden_briefs_still_pass(self) -> None:
        for golden in ("golden-landing-10", "golden-signature-launch-10"):
            brief = SKILL_DIR / "examples" / golden / "brief.json"
            gate = _run(str(PROVER), str(brief), "--kind", "intake")
            self.assertEqual(gate.returncode, 0,
                             f"{golden}: " + gate.stdout + gate.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
