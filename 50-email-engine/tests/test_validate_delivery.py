"""Skill 50 delivery validator (issue 1): the producer of skill50.email-delivery.v1.

Fail-before: before tools/validate_delivery.py existed there was no producer of a Skill 50
lane receipt, so Skill 83 accepted any self-declared strings. Pass-after: the receipt is
written only from a run that passes the prover, the build-plan schema check and the
signed process certificate, and --check exits non-zero on any drift.

Run: python3 50-email-engine/tests/test_validate_delivery.py
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TOOL = SKILL / "tools" / "validate_delivery.py"
GOLDEN = SKILL / "examples" / "golden-landing-10"
UNIT = "email_golden"


def run_tool(*args):
    proc = subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class ValidateDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vd-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.run_dir = self.tmp / "run"
        shutil.copytree(GOLDEN, self.run_dir)
        self.plan = self.tmp / "plan.json"
        self.plan.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"id": UNIT, "email_count": 10}]}))
        self.receipt = self.run_dir / "receipt.json"

    def produce(self):
        return run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                        "--out", self.receipt)

    def test_real_run_produces_a_receipt_83_can_read(self):
        rc, _, err = self.produce()
        self.assertEqual(rc, 0, err)
        doc = json.loads(self.receipt.read_text())
        self.assertEqual(doc["state"], "complete")
        self.assertEqual(doc["lane_validation"]["lane"], "skill50")
        self.assertEqual(doc["lane_validation"]["contract"], "skill50.email-delivery.v1")
        self.assertEqual(doc["lane_validation"]["state"], "passed")
        self.assertEqual(doc["request"]["launch_id"], "vd-launch")
        self.assertEqual(len(doc["request"]["plan_sha256"]), 64)
        for art in doc["artifacts"]:  # exactly the shape package._lane_receipt hashes
            self.assertEqual(set(art) >= {"path", "sha256", "size"}, True)
        rc, out, _ = run_tool("--check", self.receipt, "--launch-plan", self.plan)
        self.assertEqual(rc, 0, out)
        self.assertTrue(json.loads(out)["signature_authenticated"])

    def test_check_resolves_against_the_receipt_not_the_cwd_and_needs_no_role_tags(self):
        # Skill 83 writes the delivery row into its package root and runs
        # `validate_delivery.py --check <row>` from there: no --root, any cwd, roles optional.
        self.assertEqual(self.produce()[0], 0)
        row = json.loads(self.receipt.read_text())
        for art in row["artifacts"]:
            art.pop("role")
        self.receipt.write_text(json.dumps(row))
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        proc = subprocess.run([sys.executable, str(TOOL), "--check", str(self.receipt)],
                              capture_output=True, text=True, cwd=elsewhere)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for bad in ("/etc/hosts", "../outside.json"):
            row["artifacts"][0]["path"] = bad
            self.receipt.write_text(json.dumps(row))
            proc = subprocess.run([sys.executable, str(TOOL), "--check", str(self.receipt)],
                                  capture_output=True, text=True, cwd=elsewhere)
            self.assertEqual(proc.returncode, 2, bad)

    def test_self_declared_receipt_is_refused(self):
        fake = self.run_dir / "fake.json"
        fake.write_text(json.dumps({
            "state": "complete", "artifacts": [{"path": "x", "sha256": "0" * 64, "size": 1}],
            "lane_validation": {"lane": "x", "contract": "y", "state": "passed"}}))
        rc, out, _ = run_tool("--check", fake)
        self.assertEqual(rc, 2, out)

    def test_tampered_artifact_fails_check(self):
        self.assertEqual(self.produce()[0], 0)
        emails = self.run_dir / "working" / "copy" / "emails.json"
        emails.write_text(emails.read_text() + "\n")
        rc, out, _ = run_tool("--check", self.receipt)
        self.assertEqual(rc, 2, out)
        self.assertIn("sha256", out)

    def test_copy_the_prover_refuses_is_not_delivered(self):
        copy = self.run_dir / "working" / "copy" / "emails.json"
        doc = json.loads(copy.read_text())
        doc["emails"] = doc["emails"][:-1]  # a 9-email sequence breaks the length floor
        copy.write_text(json.dumps(doc))
        rc, _, err = self.produce()
        self.assertEqual(rc, 2, err)
        self.assertFalse(self.receipt.exists(), "a refused run must write no receipt")

    def _shrink_one_body(self):
        """Break the prover's length floor in one email while count, plan and certificate stay consistent."""
        copy = self.run_dir / "working" / "copy" / "emails.json"
        doc = json.loads(copy.read_text())
        doc["emails"][3]["body"] = "Too short."
        copy.write_text(json.dumps(doc))

    def _restamp(self):
        """Rewrite the receipt so its artifact hashes match the bytes on disk (an honest-looking row)."""
        row = json.loads(self.receipt.read_text())
        for art in row["artifacts"]:
            data = (self.run_dir / art["path"]).read_bytes()
            art["sha256"] = hashlib.sha256(data).hexdigest()
            art["size"] = len(data)
        self.receipt.write_text(json.dumps(row))

    def test_same_count_copy_that_breaks_the_prover_floor_is_not_delivered(self):
        # Only the SACRED prover re-run catches this: email count, plan count, certificate all agree.
        self._shrink_one_body()
        rc, _, err = self.produce()
        self.assertEqual(rc, 2, err)
        self.assertIn("prove-email.py refused", err)
        self.assertFalse(self.receipt.exists())

    def test_check_re_runs_the_prover_on_a_restamped_receipt(self):
        self.assertEqual(self.produce()[0], 0)
        self._shrink_one_body()
        self._restamp()  # hashes now match the bytes; only the prover can still object
        rc, out, _ = run_tool("--check", self.receipt)
        self.assertEqual(rc, 2, out)
        self.assertIn("prove-email.py refused", out)

    def test_swapped_certificate_sha256_is_refused(self):
        self.assertEqual(self.produce()[0], 0)
        row = json.loads(self.receipt.read_text())
        row["lane_validation"]["certificate_sha256"] = "0" * 64
        self.receipt.write_text(json.dumps(row))
        rc, out, _ = run_tool("--check", self.receipt)
        self.assertEqual(rc, 2, out)
        self.assertIn("certificate_sha256 does not match", out)

    def test_wrong_lane_contract_or_state_is_refused_on_an_otherwise_true_receipt(self):
        self.assertEqual(self.produce()[0], 0)
        good = json.loads(self.receipt.read_text())
        for field, value in (("lane", "skill49"), ("contract", "skill50.email-delivery.v0"),
                             ("state", "failed")):
            row = json.loads(json.dumps(good))
            row["lane_validation"][field] = value
            self.receipt.write_text(json.dumps(row))
            rc, out, _ = run_tool("--check", self.receipt)
            self.assertEqual(rc, 2, field)
            self.assertIn("lane_validation is not a passed", out, field)

    def test_missing_certificate_is_refused(self):
        (self.run_dir / "delivery" / "PROCESS-CERTIFICATE.json").unlink()
        rc, _, err = self.produce()
        self.assertEqual(rc, 2, err)
        self.assertFalse(self.receipt.exists())

    def test_unsigned_run_cannot_produce(self):
        (self.run_dir / "working" / "checkpoints" / ".cert-hmac-key").unlink()
        rc, _, err = self.produce()
        self.assertEqual(rc, 2, err)
        self.assertIn("could not be authenticated", err)

    def test_staged_copy_without_the_run_key_is_content_checked(self):
        self.assertEqual(self.produce()[0], 0)
        staged = self.tmp / "staged"
        shutil.copytree(self.run_dir, staged)
        (staged / "working" / "checkpoints" / ".cert-hmac-key").unlink()
        rc, out, err = run_tool("--check", staged / "receipt.json")
        self.assertEqual(rc, 0, out)
        self.assertFalse(json.loads(out)["signature_authenticated"])
        self.assertIn("NOT authenticated", err)
        # the same staged copy with the certificate body altered is refused
        cert = staged / "delivery" / "PROCESS-CERTIFICATE.json"
        body = json.loads(cert.read_text())
        body["all_phases_pass"] = False
        cert.write_text(json.dumps(body))
        rc, out, _ = run_tool("--check", staged / "receipt.json")
        self.assertEqual(rc, 2, out)

    def test_launch_plan_count_and_hash_are_bound(self):
        self.assertEqual(self.produce()[0], 0)
        other = self.tmp / "other-plan.json"
        other.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"id": UNIT, "email_count": 5}]}))
        rc, out, _ = run_tool("--check", self.receipt, "--launch-plan", other)
        self.assertEqual(rc, 2, out)
        rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", "email_nope",
                              "--out", self.run_dir / "r2.json")
        self.assertEqual(rc, 2, err)

    def test_build_plan_with_an_extra_email_step_is_refused(self):
        bp = self.run_dir / "working" / "deploy" / "build-plan.json"
        doc = json.loads(bp.read_text())
        wf = next(v for k, v in doc.items() if k not in ("folder", "_meta"))
        wf["templates"].append(next(s for s in wf["templates"] if s["type"] == "email"))
        bp.write_text(json.dumps(doc))
        rc, _, err = self.produce()
        self.assertEqual(rc, 2, err)

    def test_selftest(self):
        rc, out, err = run_tool("--selftest")
        self.assertEqual(rc, 0, err)
        self.assertIn("selftest ok", out)


class EnforcementLineTests(unittest.TestCase):
    """One test per enforcement line of verify(): remove that line and exactly its test goes red.

    Each case starts from a receipt that is otherwise TRUE (hashes and sizes restamped), so the
    only thing left to object is the one check under test; the assertion names that check's own
    message. The keyless cases stage the run WITHOUT its HMAC key, which is how Skill 83 sees a
    package, so the engine's own certificate verification cannot mask a missing check here."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vde-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.run_dir = self.tmp / "run"
        shutil.copytree(GOLDEN, self.run_dir)
        self.plan = self.tmp / "plan.json"
        self.plan.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"id": UNIT, "email_count": 10}]}))
        self.receipt = self.run_dir / "receipt.json"
        rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                              "--out", self.receipt)
        self.assertEqual(rc, 0, err)

    # -- helpers ----------------------------------------------------------------------------
    def path(self, rel):
        return self.run_dir / rel

    def rewrite(self, rel, mutate):
        doc = json.loads(self.path(rel).read_text())
        mutate(doc)
        self.path(rel).write_text(json.dumps(doc, indent=2))

    def restamp(self):
        """Make the receipt's hashes, sizes and certificate_sha256 true for the bytes on disk."""
        row = json.loads(self.receipt.read_text())
        for art in row["artifacts"]:
            data = self.path(art["path"]).read_bytes()
            art["sha256"] = hashlib.sha256(data).hexdigest()
            art["size"] = len(data)
            if art["role"] == "certificate":
                row["lane_validation"]["certificate_sha256"] = art["sha256"]
        self.receipt.write_text(json.dumps(row))
        return row

    def keyless(self):
        self.path("working/checkpoints/.cert-hmac-key").unlink()

    def stamp_certificate(self, **fields):
        """Edit the certificate, give it the sha its new body recomputes to, restamp the receipt."""
        def mutate(cert):
            cert.update(fields)
            steps = [[s["phase_id"], bool(s["ok"])] for s in cert["steps"]]
            cert["certificate_sha"] = hashlib.sha256(json.dumps(
                {"seq": cert["sequence_id"], "n": cert["email_count"], "steps": steps},
                sort_keys=True).encode()).hexdigest()
        self.rewrite("delivery/PROCESS-CERTIFICATE.json", mutate)
        self.restamp()

    def check(self, *extra):
        return run_tool("--check", self.receipt, *extra)

    def assertRefused(self, why, *extra):
        rc, out, err = self.check(*extra)
        self.assertEqual(rc, 2, out + err)
        self.assertIn(why, out)

    # -- the build plan schema check -------------------------------------------------------
    def test_a_plan_whose_workflows_are_live_not_draft_is_refused(self):
        def live(plan):
            for key, wf in plan.items():
                if key not in ("folder", "_meta"):
                    wf["status"] = "live"
        self.rewrite("working/deploy/build-plan.json", live)
        self.restamp()
        self.assertRefused("build plan violates schema")
        self.receipt.unlink()  # produce must refuse the same run, with the same reason
        rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                              "--out", self.receipt)
        self.assertEqual(rc, 2, err)
        self.assertIn("build plan violates schema", err)
        self.assertFalse(self.receipt.exists())

    # -- the keyless certificate checks ----------------------------------------------------
    def test_certificate_that_did_not_pass_all_phases_is_refused_without_the_run_key(self):
        self.keyless()
        self.stamp_certificate(all_phases_pass=False)
        self.assertRefused("all_phases_pass is not true")

    def test_certificate_sha_that_does_not_recompute_is_refused_without_the_run_key(self):
        self.keyless()
        self.rewrite("delivery/PROCESS-CERTIFICATE.json",
                     lambda c: c.update(certificate_sha="0" * 64))
        self.restamp()
        self.assertRefused("certificate_sha does not recompute")

    def test_certificate_for_a_different_email_count_is_refused_without_the_run_key(self):
        self.keyless()
        self.stamp_certificate(email_count=9)
        self.assertRefused("different sequence or email count")

    def test_certificate_for_a_different_sequence_is_refused_without_the_run_key(self):
        self.keyless()
        self.stamp_certificate(sequence_id="sequence-some-other-launch")
        self.assertRefused("different sequence or email count")

    # -- the HMAC verify -------------------------------------------------------------------
    def test_corrupted_certificate_signature_is_refused_when_the_run_key_is_present(self):
        self.rewrite("delivery/PROCESS-CERTIFICATE.json",
                     lambda c: c.update(certificate_sig="0" * len(c["certificate_sig"])))
        self.restamp()
        self.assertRefused("certificate signature refused")

    # -- a certificate that is not JSON is a refusal by name, never a crash ------------------
    def test_a_certificate_that_is_not_json_is_refused_by_name_not_a_traceback(self):
        self.path("delivery/PROCESS-CERTIFICATE.json").write_text("this is not json")
        self.restamp()  # hashes and certificate_sha256 are true for the bytes; only the parse can object
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(json.loads(out)["failures"], ["PROCESS-CERTIFICATE.json is not JSON"])
        self.assertFalse(json.loads(out)["ok"])

    def test_a_certificate_that_is_json_but_not_an_object_is_refused_by_name_not_a_traceback(self):
        for body in ("[]", "null", "3"):
            self.path("delivery/PROCESS-CERTIFICATE.json").write_text(body)
            self.restamp()
            rc, out, err = self.check()
            self.assertEqual(rc, 2, body + out + err)
            self.assertNotIn("Traceback", out + err, body)
            self.assertEqual(json.loads(out)["failures"],
                             ["PROCESS-CERTIFICATE.json is not a JSON object"], body)
            self.assertFalse(json.loads(out)["ok"])

    def test_a_launch_plan_that_is_json_but_not_an_object_is_refused_by_name_not_a_traceback(self):
        for body in ("[]", "null", "3"):
            junk = self.tmp / "nonobject-plan.json"
            junk.write_text(body)
            rc, out, err = self.check("--launch-plan", junk)
            self.assertEqual(rc, 2, body + out + err)
            self.assertNotIn("Traceback", out + err, body)
            self.assertIn("launch plan: the launch plan is not a JSON object", json.loads(out)["failures"], body)
            rc, out, err = run_tool(self.run_dir, "--launch-plan", junk, "--unit", UNIT,
                                    "--out", self.tmp / "np.json")
            self.assertEqual(rc, 2, body + out + err)
            self.assertNotIn("Traceback", out + err, body)
            self.assertIn("the launch plan is not a JSON object", err)

    def test_a_build_plan_or_emails_file_that_is_not_json_is_refused_by_name_not_a_traceback(self):
        for rel in ("working/deploy/build-plan.json", "working/copy/emails.json"):
            shutil.rmtree(self.run_dir)
            shutil.copytree(GOLDEN, self.run_dir)
            rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                                  "--out", self.receipt)
            self.assertEqual(rc, 0, err)
            self.path(rel).write_text("this is not json")
            self.restamp()
            rc, out, err = self.check()
            self.assertEqual(rc, 2, rel + out + err)
            self.assertNotIn("Traceback", err, rel)
            self.assertTrue(any(f.startswith("build plan or emails.json unreadable: ")
                                for f in json.loads(out)["failures"]), rel + out)

    def test_an_artifact_path_that_is_only_whitespace_is_refused_even_when_such_a_file_exists(self):
        odd = self.path(" ")
        shutil.copy(self.path("working/copy/emails.json"), odd)
        self._point_the_emails_artifact_at(" ", odd)
        self.assertRefused("does not resolve under the receipt root")

    def test_a_run_refused_for_its_content_does_not_also_claim_the_signature_was_unauthenticated(self):
        self.keyless()
        self.path("working/copy/emails.json").unlink()
        copy_doc = json.loads((GOLDEN / "working/copy/emails.json").read_text())
        copy_doc["emails"][3]["body"] = "Too short."
        self.path("working/copy/emails.json").write_text(json.dumps(copy_doc))
        out = self.tmp / "keyless-receipt.json"
        rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT, "--out", out)
        self.assertEqual(rc, 2, err)
        self.assertIn("prove-email.py refused", err)
        self.assertNotIn("could not be authenticated", err)
        self.assertFalse(out.exists())

    def test_an_artifact_row_tagged_with_its_role_is_taken_at_the_role_not_the_path_name(self):
        # The role tag wins over the path-derived role: a true copy of emails.json filed under
        # another name inside the root, tagged "emails", is the emails artifact.
        copy = self.path("working/copy/emails-copy.json")
        shutil.copy(self.path("working/copy/emails.json"), copy)
        self._point_the_emails_artifact_at("working/copy/emails-copy.json", copy)
        rc, out, err = self.check()
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(json.loads(out)["failures"], [])

    def test_a_lane_validation_that_is_not_an_object_is_refused_not_a_traceback(self):
        for bad in (None, "passed", ["skill50"], 7):
            row = json.loads(self.receipt.read_text())
            row["lane_validation"] = bad
            self.receipt.write_text(json.dumps(row))
            rc, out, err = self.check()
            self.assertEqual(rc, 2, repr(bad) + out + err)
            self.assertNotIn("Traceback", err, repr(bad))
            self.assertIn("lane_validation is not a passed", out, repr(bad))

    def test_emails_that_are_not_an_object_with_a_certificate_for_zero_emails_is_refused_not_a_traceback(self):
        self.keyless()
        self.path("working/copy/emails.json").write_text("[]")
        self.stamp_certificate(email_count=0)  # count agrees with the 0 an unreadable list yields
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("tools/prove-email.py refused", out)

    def test_a_launch_plan_with_entries_that_are_not_objects_still_names_the_unit(self):
        self.plan.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            "junk", None, 3, {"id": UNIT, "email_count": 10}]}))
        rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                              "--out", self.receipt)
        self.assertEqual(rc, 0, err)
        rc, out, err = self.check("--launch-plan", self.plan)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", "email_nope",
                                  "--out", self.tmp / "x.json")[0], 2)

    def test_a_launch_plan_that_cannot_be_read_or_does_not_name_the_unit_is_refused_by_name(self):
        junk = self.tmp / "junk-plan.json"
        junk.write_text("this is not json")
        other = self.tmp / "other-unit-plan.json"
        other.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"id": "email_some_other_unit", "email_count": 10}]}))
        for plan, why in ((self.tmp / "no-such-plan.json", "launch plan: "),
                          (junk, "launch plan: "),
                          (other, "is not an email_sequence of the launch plan")):
            rc, out, err = self.check("--launch-plan", plan)
            self.assertEqual(rc, 2, str(plan) + out + err)
            self.assertNotIn("Traceback", err, str(plan))
            self.assertTrue(any(f.startswith("launch plan: ") and why in f
                                for f in json.loads(out)["failures"]), str(plan) + out)

    def test_only_email_steps_of_real_workflows_are_counted_and_odd_plan_entries_never_crash(self):
        def meta_templates(plan):
            plan["_meta"]["templates"] = [{"type": "email"}]  # not a workflow: never counted

        def stray_text(plan):
            plan["notes"] = "a bare string, not a workflow"

        def no_templates(plan):
            plan["sequence-without-steps"] = {"name": "x", "status": "draft"}

        def junk_step(plan):
            next(wf for k, wf in plan.items() if k not in ("folder", "_meta"))["templates"].append("junk")

        for label, edit in (("meta", meta_templates), ("stray", stray_text),
                            ("notemplates", no_templates), ("junkstep", junk_step)):
            plan_rel = "working/deploy/build-plan.json"
            original = self.path(plan_rel).read_bytes()
            self.rewrite(plan_rel, edit)
            self.restamp()
            rc, out, err = self.check()
            self.assertNotIn("Traceback", err, label)
            self.assertFalse(any(f.startswith("build plan has ") for f in json.loads(out)["failures"]),
                             label + out)  # still exactly the 10 emails the copy carries
            self.path(plan_rel).write_bytes(original)
            self.restamp()

    def test_a_certificate_without_steps_or_with_stray_step_entries_is_judged_not_crashed_on(self):
        self.keyless()
        real_steps = json.loads(self.path("delivery/PROCESS-CERTIFICATE.json").read_text())["steps"]
        self.rewrite("delivery/PROCESS-CERTIFICATE.json", lambda c: c.pop("steps"))
        self.restamp()
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("certificate_sha does not recompute", out)
        self.rewrite("delivery/PROCESS-CERTIFICATE.json",
                     lambda c: c.update(steps=["junk", None] + real_steps))
        self.restamp()
        rc, out, err = self.check()
        self.assertNotIn("Traceback", err)
        self.assertEqual(rc, 0, out + err)  # stray entries are ignored; the real steps still recompute the sha

    def test_emails_json_without_an_emails_list_is_refused_by_count_not_a_traceback(self):
        self.keyless()
        self.path("working/copy/emails.json").write_text("{}")
        self.restamp()
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("build plan has 10 email step(s), emails.json has 0", out)

    def test_a_launch_plan_without_email_sequences_is_refused_by_name_not_a_traceback(self):
        self.plan.write_text(json.dumps({"launch_id": "vd-launch"}))
        rc, out, err = self.check("--launch-plan", self.plan)
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("is not an email_sequence of the launch plan", out)

    def test_a_receipt_with_no_request_block_is_refused_against_a_plan_not_a_traceback(self):
        row = json.loads(self.receipt.read_text())
        del row["request"]
        self.receipt.write_text(json.dumps(row))
        rc, out, err = self.check("--launch-plan", self.plan)
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        # a plan whose row has no id matches the request-less receipt's missing unit: every
        # echoed field is then compared against nothing and each mismatch is named
        self.plan.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"email_count": 10}]}))
        rc, out, err = self.check("--launch-plan", self.plan)
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        failures = json.loads(out)["failures"]
        self.assertIn("receipt echoes a different launch plan than the one supplied", failures)
        self.assertIn("receipt launch_id is not the plan's", failures)

    def test_a_wrong_lane_state_is_the_only_objection_when_the_certificate_hash_is_true(self):
        row = json.loads(self.receipt.read_text())
        row["lane_validation"]["state"] = "failed"  # certificate_sha256 stays true
        self.receipt.write_text(json.dumps(row))
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertEqual(json.loads(out)["failures"],
                         ["lane_validation is not a passed skill50 skill50.email-delivery.v1"])

    # -- the launch plan binding, one check per test ---------------------------------------
    def test_a_launch_plan_with_other_bytes_is_refused_when_launch_id_and_count_agree(self):
        other = self.tmp / "other-plan.json"
        other.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"id": UNIT, "email_count": 10}], "note": "same ids, same count, other bytes"}))
        self.assertRefused("different launch plan", "--launch-plan", other)

    def test_a_receipt_for_another_launch_id_is_refused_when_plan_bytes_and_count_agree(self):
        row = json.loads(self.receipt.read_text())
        row["request"]["launch_id"] = "some-other-launch"
        self.receipt.write_text(json.dumps(row))
        self.assertRefused("launch_id is not the plan's", "--launch-plan", self.plan)

    def test_a_launch_plan_expecting_another_count_is_refused_when_the_receipt_echoes_its_bytes(self):
        other = self.tmp / "other-plan.json"
        other.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [
            {"id": UNIT, "email_count": 5}]}))
        row = json.loads(self.receipt.read_text())
        row["request"]["plan_sha256"] = hashlib.sha256(other.read_bytes()).hexdigest()
        self.receipt.write_text(json.dumps(row))
        self.assertRefused("launch plan expects 5 email(s)", "--launch-plan", other)

    # -- receipt state, artifact size, role, paths ------------------------------------------
    def test_receipt_state_other_than_complete_is_refused(self):
        row = json.loads(self.receipt.read_text())
        row["state"] = "failed"
        self.receipt.write_text(json.dumps(row))
        self.assertRefused("receipt state is not 'complete'")

    def test_artifact_with_a_wrong_recorded_size_is_refused_when_its_sha_is_true(self):
        row = json.loads(self.receipt.read_text())
        row["artifacts"][1]["size"] += 1
        self.receipt.write_text(json.dumps(row))
        self.assertRefused("the receipt says")

    def test_receipt_without_the_certificate_artifact_is_refused_not_a_crash(self):
        row = json.loads(self.receipt.read_text())
        row["artifacts"] = [a for a in row["artifacts"] if a["role"] != "certificate"]
        self.receipt.write_text(json.dumps(row))
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("receipt has no certificate artifact", out)

    def _point_the_emails_artifact_at(self, rel_path, real_file):
        """A receipt whose emails row is true in every way except where the file lives."""
        row = json.loads(self.receipt.read_text())
        art = next(a for a in row["artifacts"] if a["role"] == "emails")
        art["path"] = rel_path
        self.receipt.write_text(json.dumps(row))
        self.assertTrue(real_file.is_file())

    def test_an_artifact_path_that_climbs_out_of_the_root_is_refused_even_when_the_file_exists(self):
        outside = self.tmp / "outside.json"
        shutil.copy(self.path("working/copy/emails.json"), outside)
        self._point_the_emails_artifact_at("../outside.json", outside)
        self.assertRefused("does not resolve under the receipt root")

    def test_an_absolute_artifact_path_is_refused_even_when_the_file_exists(self):
        outside = self.tmp / "outside-abs.json"
        shutil.copy(self.path("working/copy/emails.json"), outside)
        self._point_the_emails_artifact_at(str(outside), outside)
        self.assertRefused("does not resolve under the receipt root")

    def test_an_absolute_artifact_path_is_refused_even_when_the_file_is_inside_the_root(self):
        inside = self.path("working/copy/emails.json")
        self._point_the_emails_artifact_at(str(inside.resolve()), inside)
        self.assertRefused("does not resolve under the receipt root")


    # -- exit codes and clean refusals (a missing validator is a refusal, never a pass) ------
    def test_check_on_a_receipt_that_cannot_be_read_exits_3_never_0(self):
        rc, out, err = run_tool("--check", self.tmp / "no-such-receipt.json")
        self.assertEqual(rc, 3, out + err)
        self.assertIn("cannot read", err)
        junk = self.tmp / "junk.json"
        junk.write_text("this is not json")
        rc, out, err = run_tool("--check", junk)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("cannot read", err)

    def test_check_on_a_receipt_that_is_not_an_object_is_refused_not_a_traceback(self):
        self.receipt.write_text(json.dumps(["not", "a", "receipt"]))
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("receipt is not a JSON object", out)

    def test_check_on_an_artifact_entry_that_is_not_an_object_is_refused_not_a_traceback(self):
        row = json.loads(self.receipt.read_text())
        row["artifacts"].append("a bare string, not an artifact")
        self.receipt.write_text(json.dumps(row))
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("an artifact entry is not an object", out)

    def test_produce_with_an_argument_missing_is_a_usage_error_not_a_traceback(self):
        for argv in ([self.run_dir, "--launch-plan", self.plan, "--unit", UNIT],
                     ["--launch-plan", self.plan, "--unit", UNIT, "--out", self.tmp / "o.json"],
                     [self.run_dir, "--unit", UNIT, "--out", self.tmp / "o.json"],
                     [self.run_dir, "--launch-plan", self.plan, "--out", self.tmp / "o.json"]):
            rc, out, err = run_tool(*argv)
            self.assertEqual(rc, 2, err)
            self.assertNotIn("Traceback", err)
            self.assertIn("produce needs", err)
        self.assertFalse((self.tmp / "o.json").exists())


    # -- sweep round 1: guards that would otherwise turn a refusal into a traceback ----------
    def _no_traceback_refusal(self, why):
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn(why, out)

    def test_verify_takes_the_root_as_a_plain_string(self):
        spec = importlib.util.spec_from_file_location("vd_under_test", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fails, authenticated = module.verify(str(self.run_dir), json.loads(self.receipt.read_text()),
                                             str(self.plan))
        self.assertEqual(fails, [])
        self.assertTrue(authenticated)

    def test_an_artifact_row_without_a_usable_path_is_refused_not_a_traceback(self):
        for bad in (None, 5, "", "   "):
            row = json.loads(self.receipt.read_text())
            if bad is None:
                del row["artifacts"][0]["path"]
            else:
                row["artifacts"][0]["path"] = bad
            self.receipt.write_text(json.dumps(row))
            self._no_traceback_refusal("does not resolve under the receipt root")

    def test_a_receipt_with_null_text_or_empty_artifacts_says_it_carries_none(self):
        for bad in (None, "text", []):
            row = json.loads(self.receipt.read_text())
            row["artifacts"] = bad
            self.receipt.write_text(json.dumps(row))
            self._no_traceback_refusal("receipt carries no artifacts")

    def test_emails_json_that_is_not_an_object_is_refused_not_a_traceback(self):
        self.path("working/copy/emails.json").write_text("[]")
        self.restamp()
        self._no_traceback_refusal("tools/prove-email.py refused")

    def test_a_build_plan_that_is_not_an_object_is_refused_not_a_traceback(self):
        self.path("working/deploy/build-plan.json").write_text("[]")
        self.restamp()
        self._no_traceback_refusal("build plan")

    def test_a_delivery_with_no_emails_at_all_is_refused_by_name_even_when_the_plan_has_none_too(self):
        def no_emails(doc):
            doc["emails"] = []
        self.rewrite("working/copy/emails.json", no_emails)

        def no_email_steps(plan):
            for wf in plan.values():
                if isinstance(wf, dict):
                    wf["templates"] = [t for t in wf.get("templates") or [] if t.get("type") != "email"]
        self.rewrite("working/deploy/build-plan.json", no_email_steps)
        self.restamp()
        self._no_traceback_refusal("build plan has 0 email step(s), emails.json has 0")

    def test_a_launch_plan_row_that_names_no_email_count_does_not_refuse(self):
        self.plan.write_text(json.dumps({"launch_id": "vd-launch", "email_sequences": [{"id": UNIT}]}))
        rc, _, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                              "--out", self.receipt)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.check("--launch-plan", self.plan)[0], 0)

    def test_produce_names_the_artifact_it_is_missing_and_says_where_it_wrote(self):
        rc, out, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                                "--out", self.receipt)
        self.assertEqual(rc, 0, err)
        self.assertIn("receipt written to", out)
        self.path("delivery/PROCESS-CERTIFICATE.json").unlink()
        rc, out, err = run_tool(self.run_dir, "--launch-plan", self.plan, "--unit", UNIT,
                                "--out", self.receipt)
        self.assertEqual(rc, 2, err)
        self.assertIn("missing certificate", err)


    def test_an_unauthenticated_signature_is_said_plainly_and_only_then(self):
        rc, out, err = self.check()
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("NOT authenticated", err)
        self.keyless()
        rc, out, err = self.check()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("NOT authenticated", err)
        self.assertFalse(json.loads(out)["signature_authenticated"])


    def test_a_keyless_check_that_fails_does_not_claim_the_content_was_re_verified(self):
        self.keyless()
        row = json.loads(self.receipt.read_text())
        row["artifacts"][1]["size"] += 1
        self.receipt.write_text(json.dumps(row))
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertFalse(json.loads(out)["ok"])
        self.assertNotIn("NOT authenticated", err)

    def test_a_true_receipt_reports_ok_true_and_check_honours_root(self):
        rc, out, err = self.check()
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(json.loads(out)["failures"], [])
        self.assertTrue(json.loads(out)["ok"])
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        moved = elsewhere / "receipt.json"
        shutil.copy(self.receipt, moved)
        rc, out, err = run_tool("--check", moved)  # default root is the receipt's own directory
        self.assertEqual(rc, 2, out + err)
        rc, out, err = run_tool("--check", moved, "--root", self.run_dir)
        self.assertEqual(rc, 0, out + err)

    def test_the_selftest_assertion_refuses_a_failing_or_unauthenticated_verify(self):
        spec = importlib.util.spec_from_file_location("vd_selftest_under_test", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        real_verify = module.verify
        for outcome in ((["a failure"], True), ([], False)):
            calls = []

            def verify(*args, _outcome=outcome, _calls=calls):
                _calls.append(args)
                return real_verify(*args) if len(_calls) == 1 else _outcome  # first call is produce()

            module.verify = verify
            with self.assertRaises(AssertionError):
                module._selftest()


if __name__ == "__main__":
    unittest.main(verbosity=2)
