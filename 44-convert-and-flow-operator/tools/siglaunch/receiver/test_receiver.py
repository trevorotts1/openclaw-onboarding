"""S44-02 receiver proofs against a recording fake executor.

Covers the design's refusal discipline (nothing written on refusal),
idempotent redispatch, resume semantics, _meta stripping, blocked-auth
receipts, and the consumer judge's honesty rule.
"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
from receiver import (EXIT_BLOCKED, EXIT_GATE, EXIT_OK, EXIT_VALIDATION,
                      Receiver, judge_receipt, plan_hash)
from store import Store


class FakeExecutor:
    def __init__(self, token_state="healthy"):
        self.token_state = token_state
        self.build_calls = []
        self.snapshot_ok = True
        self.missing = []

    def probe(self):
        return {"token_state": self.token_state, "access_tier_used": "tier0"}

    def dependencies_present(self, location_id, workflow):
        return list(self.missing)

    def snapshot(self, location_id, slug):
        return self.snapshot_ok

    def build(self, builder_plan):
        self.build_calls.append(copy.deepcopy(builder_plan))
        slug = next(k for k in builder_plan if k != "folder")
        return {
            "exit_code": 0, "workflow_id": "wf-" + slug, "errors": [],
            "notes": [],
            "export": {
                "id": "wf-" + slug, "status": "draft",
                "triggers": [{"id": "t1", "type": "contact_tag"}],
                "steps": [{"id": "s1"}, {"id": "s2"}],
                "allowMultiple": True,
            },
            "qc_exit_code": 0, "rubric": 9.1,
        }


def make_request(**overrides):
    plan = {
        "_meta": {"deploy_mode": "draft-only", "emitter": "s50"},
        "folder": "Signature Launch",
        "welcome": {"name": "Welcome", "tag": "email-engine:welcome"},
    }
    req = {
        "request_id": "gxo_0123456789ab", "request_version": 1,
        "location_id": "LOC1", "launch_id": "LN1",
        "requesting_room": "S50", "deploy_mode": "draft-only",
        "approval": {"ref": "owner-batch-1", "plan_hash": plan_hash(plan)},
        "plan": plan,
        "workflows": [{
            "slug": "welcome", "expected_steps": 2, "allow_multiple": True,
            "trigger": {"type": "contact_tag", "tag": "email-engine:welcome"},
        }],
    }
    req.update(overrides)
    return req


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))
        self.fake = FakeExecutor()
        self.rx = Receiver(self.store, self.fake, configured_location="LOC1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_happy_path_and_meta_stripped(self):
        code, receipt = self.rx.dispatch(make_request())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(receipt["status_claimed"], "verified")
        # the builder received exactly {folder, slug: workflow} — no _meta
        self.assertEqual(len(self.fake.build_calls), 1)
        sent = self.fake.build_calls[0]
        self.assertEqual(set(sent), {"folder", "welcome"})
        self.assertNotIn("_meta", sent)
        # judge agrees with the claim because read-backs are present
        self.assertEqual(judge_receipt(receipt)["overall"], "VERIFIED")

    def test_redispatch_returns_prior_receipt_without_rebuild(self):
        code1, r1 = self.rx.dispatch(make_request())
        code2, r2 = self.rx.dispatch(make_request())
        self.assertEqual((code1, code2), (EXIT_OK, EXIT_OK))
        self.assertEqual(r1["execution"]["execution_id"],
                         r2["execution"]["execution_id"])
        self.assertEqual(len(self.fake.build_calls), 1)

    def test_wrong_location_refused_nothing_written(self):
        code, refusal = self.rx.dispatch(make_request(location_id="LOC2"))
        self.assertEqual(code, EXIT_GATE)
        self.assertEqual(refusal["refused"], "WRONG_LOCATION")
        self.assertEqual(self.fake.build_calls, [])
        self.assertIsNone(self.store.get_request("gxo_0123456789ab"))

    def test_deploy_mode_never_defaulted(self):
        req = make_request()
        del req["deploy_mode"]
        code, refusal = self.rx.dispatch(req)
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertIsNone(self.store.get_request("gxo_0123456789ab"))
        code2, _ = self.rx.dispatch(make_request(deploy_mode="live"))
        self.assertEqual(code2, EXIT_VALIDATION)

    def test_plan_hash_mismatch_refused(self):
        req = make_request()
        req["plan"]["welcome"]["name"] = "Tampered"
        code, refusal = self.rx.dispatch(req)
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "PLAN_HASH_MISMATCH")

    def test_superseded_version_refused(self):
        self.rx.dispatch(make_request(request_version=2))
        code, refusal = self.rx.dispatch(make_request(request_version=1))
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "SUPERSEDED")

    def test_blocked_auth_receipt_and_resume_after_heal(self):
        self.fake.token_state = "revoked"
        code, receipt = self.rx.dispatch(make_request())
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(receipt["status_claimed"], "blocked-auth")
        self.assertEqual(self.fake.build_calls, [])
        # after the token heals, the SAME request_id proceeds (not stuck)
        self.fake.token_state = "healthy"
        code2, receipt2 = self.rx.dispatch(make_request())
        self.assertEqual(code2, EXIT_OK)
        self.assertEqual(len(self.fake.build_calls), 1)

    def test_missing_dependency_fails_operation_not_request(self):
        self.fake.missing = ["tag:email-engine:welcome"]
        code, receipt = self.rx.dispatch(make_request())
        self.assertNotEqual(code, EXIT_OK)
        op = receipt["operations"][0]
        self.assertEqual(op["status_claimed"], "failed")
        self.assertIn("missing dependencies", op["errors"][0])
        self.assertEqual(self.fake.build_calls, [])

    def test_snapshot_failure_aborts_without_build(self):
        self.fake.snapshot_ok = False
        code, receipt = self.rx.dispatch(make_request())
        self.assertNotEqual(code, EXIT_OK)
        self.assertEqual(self.fake.build_calls, [])
        self.assertIn("snapshot", receipt["operations"][0]["errors"][0])

    def test_judge_rejects_claim_without_readback(self):
        _, receipt = self.rx.dispatch(make_request())
        forged = copy.deepcopy(receipt)
        forged["operations"][0]["readback"] = None
        self.assertEqual(judge_receipt(forged)["overall"], "NOT_VERIFIED")
        self.assertEqual(
            judge_receipt(forged)["operations"]["welcome"], "UNVERIFIED")
        # read-back id mismatch is also unverified, never success
        forged2 = copy.deepcopy(receipt)
        forged2["operations"][0]["readback"]["id"] = "wf-OTHER"
        self.assertEqual(
            judge_receipt(forged2)["operations"]["welcome"], "UNVERIFIED")

    def test_partial_resume_reuses_success_and_rebuilds_failure(self):
        # two workflows: 'welcome' builds, 'nurture' lacks a dependency
        plan = {
            "_meta": {"deploy_mode": "draft-only"},
            "folder": "Signature Launch",
            "welcome": {"name": "Welcome", "tag": "email-engine:welcome"},
            "nurture": {"name": "Nurture", "tag": "email-engine:nurture"},
        }
        req = make_request(plan=plan, workflows=[
            {"slug": "welcome", "expected_steps": 2, "allow_multiple": True,
             "trigger": {"type": "contact_tag"}},
            {"slug": "nurture", "expected_steps": 2, "allow_multiple": True,
             "trigger": {"type": "contact_tag"}},
        ])
        req["approval"]["plan_hash"] = plan_hash(plan)

        class DepFake(FakeExecutor):
            def dependencies_present(self, location_id, workflow):
                if workflow["slug"] == "nurture" and not self.healed:
                    return ["tag:email-engine:nurture"]
                return []
            healed = False

        fake = DepFake()
        rx = Receiver(self.store, fake, configured_location="LOC1")
        code, receipt = rx.dispatch(req)
        self.assertNotEqual(code, EXIT_OK)
        self.assertEqual(receipt["status_claimed"], "partial")
        self.assertEqual(len(fake.build_calls), 1)  # only welcome built
        # dependency provisioned (Phase A lands); redispatch resumes
        fake.healed = True
        code2, receipt2 = rx.dispatch(req)
        self.assertEqual(code2, EXIT_OK)
        self.assertEqual(len(fake.build_calls), 2)  # only nurture rebuilt
        ops = {op["slug"]: op for op in receipt2["operations"]}
        self.assertEqual(ops["welcome"]["status_claimed"], "reused")
        self.assertEqual(ops["nurture"]["status_claimed"], "created")

    def test_unknown_envelope_field_refused(self):
        req = make_request()
        req["surprise"] = True
        code, refusal = self.rx.dispatch(req)
        self.assertEqual(code, EXIT_VALIDATION)
        self.assertEqual(refusal["refused"], "UNKNOWN_FIELDS")


if __name__ == "__main__":
    unittest.main()
