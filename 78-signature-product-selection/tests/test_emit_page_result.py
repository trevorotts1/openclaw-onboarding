"""Tests for the Path A follow-on emitter fix (CR-S49-002, post-#2158).

Pins all four confirmed defects in scripts/emit_page_result.py:
  1. main() wrote no result file -> the CLI now writes the bare JSON
     result file at the --output path.
  2. page_id was the literal "selection" -> it is echoed from the request.
  3. input_hash was the SHA-256 of the serialized plan -> it is echoed
     from the request.
  4. The result always carried outcome, which page-result 1.0 rejects
     (additionalProperties: false) -> the page-result document has no
     outcome key, has exactly the 17 page-result fields, and validates
     against schema/page-result.schema.json. The outcome remains in
     Skill 78's own selection-result profile
     (emit_selection_result / schema/selection-result.schema.json).
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
import emit_page_result  # noqa: E402
from emit_page_result import PAGE_RESULT_FIELDS, check_review, emit, emit_selection_result  # noqa: E402

REQUEST = {
    "request_id": "TEST-REQ-78-PATHA",
    "page_id": "TEST-LAUNCH-SELECTION-PAGE",
    "input_hash": "e" * 64,
    "test_only": True,
}


def plan_hash_old_way(plan):
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate(instance, schema_path):
    try:
        import jsonschema
    except ImportError:
        # Manual equivalent for the properties these tests pin:
        # additionalProperties false plus the required key set.
        schema = json.loads(Path(schema_path).read_text())
        assert schema["additionalProperties"] is False
        assert set(instance.keys()) == set(schema["required"]), (
            set(instance.keys()), set(schema["required"]))
        return
    jsonschema.validate(instance, json.loads(Path(schema_path).read_text()))


class EmitFunctionTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_plan(SELF_TEST_LAUNCH)

    def test_page_id_echoed_from_request_not_literal(self):
        res = emit(self.plan, author_session="test", request=dict(REQUEST))
        self.assertEqual(res["page_id"], "TEST-LAUNCH-SELECTION-PAGE")
        self.assertNotEqual(res["page_id"], "selection")

    def test_input_hash_echoed_from_request_not_plan_hash(self):
        res = emit(self.plan, author_session="test", request=dict(REQUEST))
        self.assertEqual(res["input_hash"], "e" * 64)
        self.assertNotEqual(res["input_hash"], plan_hash_old_way(self.plan))

    def test_no_outcome_and_exactly_the_17_page_result_fields(self):
        res = emit(self.plan, author_session="test", request=dict(REQUEST))
        self.assertNotIn("outcome", res)
        self.assertEqual(tuple(res.keys()), PAGE_RESULT_FIELDS)
        self.assertEqual(len(res), 17)

    def test_page_result_validates_against_page_result_schema(self):
        res = emit(self.plan, author_session="test", request=dict(REQUEST))
        validate(res, ROOT / "schema" / "page-result.schema.json")

    def test_outcome_remains_in_selection_result_profile(self):
        profile = emit_selection_result(self.plan, author_session="test", request=dict(REQUEST))
        self.assertEqual(profile["outcome"], "plan")
        self.assertEqual(profile["page_id"], REQUEST["page_id"])
        self.assertEqual(profile["input_hash"], REQUEST["input_hash"])
        validate(profile, ROOT / "schema" / "selection-result.schema.json")

    def test_declined_plan_profile_outcome_and_clean_page_result(self):
        declined = build_plan(dict(SELF_TEST_LAUNCH, journey_mode="single_simple",
                                   offers=SELF_TEST_LAUNCH["offers"][:1]))
        res = emit(declined, author_session="test", request=dict(REQUEST))
        self.assertNotIn("outcome", res)
        validate(res, ROOT / "schema" / "page-result.schema.json")
        profile = emit_selection_result(declined, author_session="test", request=dict(REQUEST))
        self.assertEqual(profile["outcome"], "declined_single_offer")

    def test_missing_echo_source_fails_closed(self):
        with self.assertRaises(ValueError):
            emit(self.plan, author_session="test", request_id="r-only")
        with self.assertRaises(ValueError):
            emit(self.plan, author_session="test", request_id="r", page_id="P")


class ReviewGateTests(unittest.TestCase):
    """Issue 79: one meaning of locally_verified - it needs a reviewer and a review record."""

    def setUp(self):
        self.plan = build_plan(SELF_TEST_LAUNCH)

    def test_default_status_is_authored_l1_unreviewed(self):
        res = emit(self.plan, author_session="test", request=dict(REQUEST))
        self.assertEqual((res["status"], res["proof_class"], res["independent_review"]), ("authored", "L1", False))

    def test_locally_verified_without_reviewer_is_refused(self):
        with self.assertRaises(ValueError):
            emit(self.plan, author_session="test", request=dict(REQUEST), status="locally_verified")

    def test_cli_locally_verified_or_reviewer_without_record_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            plan = Path(td) / "plan.json"
            plan.write_text(json.dumps(self.plan))
            req = Path(td) / "request.json"
            req.write_text(json.dumps(REQUEST))
            for extra in (["--status", "locally_verified", "--reviewer-session", "rev-1"],
                          ["--reviewer-session", "rev-1"]):
                out = Path(td) / "out.json"
                run = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "emit_page_result.py"), str(plan),
                     "--author-session", "a", "--request", str(req), "--output", str(out)] + extra,
                    capture_output=True, text=True)
                self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
                self.assertIn("--review", run.stderr)
                self.assertFalse(out.exists())

    def test_cli_valid_review_record_and_ledger_emit_locally_verified(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            plan = td / "plan.json"
            plan.write_text(json.dumps(self.plan))
            req = td / "request.json"
            req.write_text(json.dumps(REQUEST))
            artifact = td / "page.txt"
            artifact.write_text("reviewed page bytes")
            sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
            record = td / "review.json"
            record.write_text(json.dumps({
                "schema": "signature-launch-review-record/v1", "verdict": "pass",
                "reviewer_session": "rev-1", "reviewer_model": "model-b",
                "request_id": REQUEST["request_id"],
                "reviewed_artifacts": [{"path": str(artifact), "sha256": sha}]}))
            ledger = td / "ledger.json"
            ledger.write_text(json.dumps(["rev-1"]))
            out = td / "out.json"
            run = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "emit_page_result.py"), str(plan),
                 "--author-session", "a", "--request", str(req), "--output", str(out),
                 "--artifact", str(artifact), "--status", "locally_verified",
                 "--reviewer-session", "rev-1", "--review", str(record),
                 "--review-ledger", str(ledger)],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            doc = json.loads(out.read_text())
            self.assertEqual((doc["status"], doc["reviewer_session"], doc["independent_review"]),
                             ("locally_verified", "rev-1", True))
            self.assertEqual(doc["artifacts"][0]["sha256"], sha)
            validate(doc, ROOT / "schema" / "page-result.schema.json")


class CheckReviewEnforcementTests(unittest.TestCase):
    """Each enforcement line in check_review and the CLI call to it is pinned:
    remove the line and exactly the matching test here fails."""

    SHA = "c" * 64

    def _result(self, **kw):
        base = {"author_session": "a", "request_id": "REQ-1", "reviewer_session": "rev-1",
                "artifacts": [{"path": "page.txt", "sha256": self.SHA}]}
        base.update(kw)
        return base

    def _record(self, **kw):
        base = {"schema": "signature-launch-review-record/v1", "verdict": "pass",
                "reviewer_session": "rev-1", "reviewer_model": "model-b", "request_id": "REQ-1",
                "reviewed_artifacts": [{"path": "page.txt", "sha256": self.SHA}]}
        base.update(kw)
        return base

    def test_valid_record_is_accepted(self):
        self.assertIsNone(check_review(self._result(), self._record(), ["rev-1"]))

    def test_validator_refusal_raises(self):
        # reviewer is not in the dispatch ledger
        with self.assertRaisesRegex(ValueError, "review record refused"):
            check_review(self._result(), self._record(), ["someone-else"])

    def test_reviewer_session_mismatch_raises(self):
        with self.assertRaisesRegex(ValueError, "differs from --reviewer-session"):
            check_review(self._result(reviewer_session="rev-2"), self._record(), ["rev-1"])

    def test_validator_not_found_fails_closed(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(emit_page_result, "__file__", str(Path(td) / "emit_page_result.py")):
                with self.assertRaisesRegex(ValueError, "validator not found"):
                    check_review(self._result(), self._record(), ["rev-1"])

    def test_record_for_another_request_is_refused(self):
        with self.assertRaisesRegex(ValueError, "does not echo the request"):
            check_review(self._result(), self._record(request_id="OTHER"), ["rev-1"])

    def test_reviewer_equal_to_author_is_refused(self):
        with self.assertRaisesRegex(ValueError, "reviewer session == author session"):
            check_review(self._result(reviewer_session="a"), self._record(reviewer_session="a"), ["a"])

    def test_cli_junk_review_record_is_refused_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "plan.json").write_text(json.dumps(build_plan(SELF_TEST_LAUNCH)))
            (td / "request.json").write_text(json.dumps(REQUEST))
            (td / "junk.json").write_text(json.dumps({"verdict": "pass"}))
            out = td / "out.json"
            run = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "emit_page_result.py"), str(td / "plan.json"),
                 "--author-session", "a", "--request", str(td / "request.json"), "--output", str(out),
                 "--reviewer-session", "rev-1", "--review", str(td / "junk.json")],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn("review record refused", run.stderr)
            self.assertFalse(out.exists())


class EmitCliTests(unittest.TestCase):
    def _run_cli(self, td, extra_args, request_via="file"):
        plan_path = Path(td) / "plan.json"
        plan_path.write_text(json.dumps(build_plan(SELF_TEST_LAUNCH)))
        req_path = Path(td) / "request.json"
        req_path.write_text(json.dumps(REQUEST))
        out_path = Path(td) / "nested" / "result.json"
        cmd = [sys.executable, str(ROOT / "scripts" / "emit_page_result.py"),
               str(plan_path), "--author-session", "test-cli"]
        if request_via == "file":
            cmd += ["--request", str(req_path)]
        elif request_via == "flags":
            cmd += ["--request-id", REQUEST["request_id"], "--page-id", REQUEST["page_id"],
                    "--input-hash", REQUEST["input_hash"], "--test-only"]
        cmd += extra_args(out_path)
        run = subprocess.run(cmd, capture_output=True, text=True)
        return run, out_path

    def test_cli_writes_bare_json_file_at_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            run, out_path = self._run_cli(td, lambda o: ["--output", str(o)])
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertTrue(out_path.exists())
            # Bare JSON: the file is exactly one JSON object, not an
            # envelope and not stdout-captured text with extra lines.
            doc = json.loads(out_path.read_text())
            self.assertIsInstance(doc, dict)
            self.assertEqual(doc["page_id"], REQUEST["page_id"])
            self.assertEqual(doc["input_hash"], REQUEST["input_hash"])
            self.assertEqual(doc["request_id"], REQUEST["request_id"])
            self.assertNotIn("outcome", doc)
            self.assertEqual(len(doc), 17)
            validate(doc, ROOT / "schema" / "page-result.schema.json")
            self.assertEqual(run.stdout, "")

    def test_cli_explicit_echo_flags_also_write_file(self):
        with tempfile.TemporaryDirectory() as td:
            run, out_path = self._run_cli(td, lambda o: ["--output", str(o)], request_via="flags")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            doc = json.loads(out_path.read_text())
            self.assertEqual(doc["page_id"], REQUEST["page_id"])
            self.assertEqual(doc["input_hash"], REQUEST["input_hash"])

    def test_cli_without_output_path_fails_closed_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            run, out_path = self._run_cli(td, lambda o: [])
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertFalse(out_path.exists())

    def test_cli_without_request_echo_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path = Path(td) / "plan.json"
            plan_path.write_text(json.dumps(build_plan(SELF_TEST_LAUNCH)))
            out_path = Path(td) / "result.json"
            run = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "emit_page_result.py"),
                 str(plan_path), "--output", str(out_path),
                 "--author-session", "test-cli", "--request-id", "r-only"],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn("FAIL-CLOSED", run.stderr)
            self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()
