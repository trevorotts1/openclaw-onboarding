"""ENF-10: a review record is accepted only when the reviewer session is in the
dispatch ledger, differs from the author, and lists every artifact sha256."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import review_record as rr  # noqa: E402

A, B = "aa" * 32, "bb" * 32
LEDGER = {"sessions": [{"session_id": "rev-1", "model": "m1"}, "author-1"]}
ARTS = [{"path": "a.png", "sha256": A}, {"path": "b.png", "sha256": B}]


def rec(**kw):
    r = {"schema": rr.SCHEMA, "reviewer_session": "rev-1",
         "reviewer_model": "m1", "request_id": "rq", "verdict": "pass",
         "reviewed_artifacts": [{"path": "a.png", "sha256": A},
                                {"path": "b.png", "sha256": B}]}
    r.update(kw)
    return r


def check(r, ledger=LEDGER, author="author-1", arts=ARTS, **kw):
    return rr.validate_review_record(r, ledger=ledger, author_session=author,
                                     artifacts=arts, request_id="rq", **kw)


class ReviewRecord(unittest.TestCase):
    def test_accepted(self):
        self.assertEqual(check(rec()), [])
        self.assertEqual(check(rec(), ledger=["rev-1"]), [])
        self.assertEqual(check(rec(verdict="APPROVED")), [])
        self.assertEqual(check(rec(verdict=None, passed=True)), [])

    def test_a_verdict_must_be_a_recognised_success(self):
        for bad in (None, "", "banana", "fail", "rejected", False):
            self.assertTrue(any("no recognised successful verdict" in f
                                for f in check(rec(verdict=bad))), bad)
        no_verdict = rec()
        del no_verdict["verdict"]
        self.assertTrue(any("no recognised successful verdict" in f
                            for f in check(no_verdict)))

    def test_typed_reviewer_not_in_ledger_refused(self):
        self.assertTrue(any("not in the dispatch ledger" in f
                            for f in check(rec(reviewer_session="b"))))
        self.assertTrue(check(rec(), ledger=None))

    def test_reviewer_equals_author_refused(self):
        led = {"sessions": ["same"]}
        self.assertTrue(any("never its author" in f for f in
                            check(rec(reviewer_session="same"), led, "same")))

    def test_every_artifact_sha_must_be_listed(self):
        one = rec(reviewed_artifacts=[{"path": "a.png", "sha256": A}])
        self.assertTrue(any("not listed" in f for f in check(one)))
        self.assertTrue(check(rec(reviewed_artifacts=[])))
        self.assertTrue(check(rec(), arts=[]))
        self.assertTrue(check(rec(reviewed_artifacts=[
            {"path": "a.png", "sha256": "abc"}])))

    def test_model_and_request_binding(self):
        self.assertTrue(check(rec(reviewer_model="other")))
        self.assertTrue(check(rec(reviewer_model="")))
        self.assertTrue(check(rec(request_id="elsewhere")))
        self.assertTrue(check("not a record"))

    def test_independence_must_be_declared_and_not_the_author_model(self):
        self.assertTrue(any("requires independent review" in f
                            for f in check(rec(), require_independence=True)))
        self.assertEqual(check(rec(independent_review=True),
                               require_independence=True), [])
        self.assertTrue(any("not model independence" in f
                            for f in check(rec(independent_review=True),
                                           require_model_independence=True,
                                           author_model="m1")))
        self.assertEqual(check(rec(independent_review=True),
                               require_model_independence=True,
                               author_model="m2"), [])

    def test_exact_artifact_set_refuses_stale_bytes(self):
        C = "cc" * 32
        stale = rec(reviewed_artifacts=[{"path": "a.png", "sha256": A},
                                        {"path": "b.png", "sha256": B},
                                        {"path": "old.png", "sha256": C}])
        self.assertEqual(check(stale), [])
        self.assertTrue(any("not the current artifact set" in f
                            for f in check(stale, exact_artifact_set=True)))

    # F19 item 1 - author and dispatch identity are bound, not typed strings.
    def test_author_identity_mismatch_refused(self):
        self.assertTrue(any("identity mismatch" in f
                            for f in check(rec(author_session="someone-else"))))
        self.assertEqual(check(rec(author_session="author-1")), [])

    def test_dispatch_identity_is_bound(self):
        self.assertTrue(any("does not echo the dispatch" in f
                            for f in check(rec(), dispatch_id="d1")))
        self.assertEqual(check(rec(dispatch_id="d1"), dispatch_id="d1"), [])
        led = {"sessions": [{"session_id": "rev-1", "model": "m1",
                             "dispatch_id": "d1"}, "author-1"]}
        self.assertTrue(any("disagrees with" in f
                            for f in check(rec(dispatch_id="d2"), led,
                                           dispatch_id="d2")))

    # F19 item 2 - item/stage use the same rule; a weaker scope cannot close.
    def test_weaker_scope_cannot_close_a_stage(self):
        self.assertTrue(any("cannot close the 'stage' closure" in f
                            for f in check(rec(scope="item"), min_scope="stage")))
        self.assertEqual(check(rec(scope="stage"), min_scope="stage"), [])
        self.assertTrue(any("names no recognised scope" in f
                            for f in check(rec(), min_scope="item")))

    def test_review_closure_applies_same_policy_to_item_and_stage(self):
        policy = {"require_independent_review": True, "author_model": "m9"}
        for scope in ("item", "stage"):
            fails = rr.validate_review_closure(
                rec(scope=scope), scope=scope, ledger=LEDGER,
                author_session="author-1", artifacts=ARTS, policy=policy)
            self.assertTrue(any("requires independent review" in f for f in fails),
                            scope)

    # F19 item 3 - separate session is not model independence.
    def test_model_independence_needs_known_models(self):
        fails = check(rec(independent_review=True), require_model_independence=True)
        self.assertTrue(any("author model is unknown" in f for f in fails))
        led = {"sessions": [{"session_id": "rev-1"}, "author-1"]}
        fails = check(rec(independent_review=True), led,
                      require_model_independence=True, author_model="m2")
        self.assertTrue(any("records no model for the reviewer" in f for f in fails))
        self.assertEqual(check(rec(independent_review=True),
                               require_model_independence=True,
                               author_model="m2"), [])

    # F19 item 4 - a repaired byte needs another reviewer.
    def test_repaired_bytes_need_another_reviewer(self):
        self.assertTrue(any("repaired the reviewed bytes" in f
                            for f in check(rec(repaired_by="rev-1"))))
        fails = rr.validate_review_after_repair(
            rec(), repaired_by="rev-1", ledger=LEDGER,
            author_session="author-1", artifacts=ARTS, request_id="rq")
        self.assertTrue(any("repairing reviewer cannot certify" in f for f in fails))
        led2 = {"sessions": [{"session_id": "rev-1", "model": "m1"},
                             {"session_id": "rev-2", "model": "m2"},
                             "author-1"]}
        ok = rr.validate_review_after_repair(
            rec(reviewer_session="rev-2", reviewer_model="m2",
                independent_review=True), repaired_by="rev-1", ledger=led2,
            author_session="author-1", artifacts=ARTS, request_id="rq")
        self.assertEqual(ok, [])
        # Same reviewer reviewing DIFFERENT bytes is refused by prior_review.
        prior = rec(reviewed_artifacts=[{"path": "a.png", "sha256": "dd" * 32}])
        fails = check(rec(), prior_review=prior)
        self.assertTrue(any("covers different bytes" in f for f in fails))

    # F19 item 6 - attempt identity and stale results.
    def test_attempt_identity_is_required_and_bound(self):
        fails = check(rec(), require_attempt_identity=True, attempt_id="att-1")
        self.assertTrue(any("names no attempt_id" in f for f in fails))
        self.assertEqual(check(rec(attempt_id="att-1", revision="r1"),
                               require_attempt_identity=True,
                               attempt_id="att-1", revision="r1"), [])
        fails = check(rec(attempt_id="att-1", revision="r1"),
                      require_attempt_identity=True, attempt_id="att-2")
        self.assertTrue(any("not the current attempt" in f for f in fails))
        self.assertTrue(any("marked stale" in f
                            for f in check(rec(stale=True))))

    # F19 item 11 - Image Guide thresholds and no denominator shrink.
    def test_image_criteria_thresholds(self):
        applicable = ("composition", "colour", "lighting")
        good = {"kind": "image", "criteria": {
            "composition": 8, "colour": 9, "lighting": 9}, "autofails": []}
        self.assertEqual(rr.validate_image_review_criteria(
            good, applicable=applicable, kind="image"), [])
        missing = {"criteria": {"composition": 9, "colour": 9}, "autofails": []}
        self.assertTrue(any("omitted from the review evidence" in f
                            for f in rr.validate_image_review_criteria(
                                missing, applicable=applicable)))
        low = {"criteria": {"composition": 7, "colour": 9, "lighting": 9}}
        self.assertTrue(any("below 8" in f
                            for f in rr.validate_image_review_criteria(
                                low, applicable=applicable)))
        average = {"criteria": {"composition": 8, "colour": 8, "lighting": 8}}
        self.assertTrue(any("below 8.5" in f
                            for f in rr.validate_image_review_criteria(
                                average, applicable=applicable)))
        af = {"criteria": {"composition": 9, "colour": 9, "lighting": 9},
              "autofails": ["AF-1"]}
        self.assertTrue(any("auto-fails" in f
                            for f in rr.validate_image_review_criteria(
                                af, applicable=applicable)))

    # F19 item 12 - failed-only repairs, stop on PASS, max three.
    def test_repair_budget(self):
        self.assertEqual(rr.repair_budget([{"verdict": "fail"},
                                           {"verdict": "pass"}])["action"],
                         "stop_pass")
        after_pass = [{"verdict": "pass"}, {"verdict": "fail"}]
        self.assertTrue(any("must not be repeatedly reviewed" in f
                            for f in rr.validate_repair_budget(after_pass)))
        self.assertEqual(rr.repair_budget(
            [{"verdict": "fail"}] * 4)["action"], "escalate")
        self.assertTrue(rr.validate_repair_budget([{"verdict": "fail"}] * 4))

    # F19 item 13 - the master's PASS does not certify transformed bytes.
    def test_derivative_delivery_requires_binding(self):
        D = "dd" * 32
        arts = ARTS + [{"path": "a.webp", "sha256": D,
                        "transformation": "crop:1200x628", "derivative_of": A}]
        fails = check(rec(), arts=arts)
        self.assertTrue(any("no derivative binding" in f for f in fails))
        bound = rec(
            reviewed_artifacts=[{"path": "a.png", "sha256": A},
                                {"path": "b.png", "sha256": B},
                                {"path": "a.webp", "sha256": D}],
            derivatives=[{"sha256": D, "from_sha256": A,
                          "transformation": "crop:1200x628"}])
        self.assertEqual(check(bound, arts=arts), [])
        unbound_source = rec(
            reviewed_artifacts=[{"path": "a.png", "sha256": A},
                                {"path": "b.png", "sha256": B},
                                {"path": "a.webp", "sha256": D}],
            derivatives=[{"sha256": D, "transformation": "crop"}])
        self.assertTrue(any("no 64-hex from_sha256" in f
                            for f in check(unbound_source, arts=arts)))

    # F19 items 5/14 - a local flag is not F20-scoped authority.
    def test_upload_waiver_and_checkpoint_laundering(self):
        bad = rr.validate_upload_waiver(True)
        self.assertTrue(bad)
        local = {"ok": True, "approval_id": "A1", "kind": "publish",
                 "plan_hash": "a" * 64, "scope": ["graphics_upload_waiver"],
                 "verification_class": "local_test_record", "revoked": False,
                 "expires_at": "2999-01-01T00:00:00Z"}
        self.assertTrue(any("authenticated authority" in f
                            for f in rr.validate_upload_waiver(local)))
        verified = dict(local,
                        verification_class="authenticated_platform_record")
        self.assertEqual(rr.validate_upload_waiver(verified), [])
        result = {"locally_verified": True, "completion": "complete"}
        fails = rr.validate_delivery_admission(
            result, ledger=LEDGER, author_session="author-1", artifacts=ARTS)
        self.assertTrue(any("not a completed designed page" in f for f in fails))
        self.assertTrue(any("carries no review record" in f for f in fails))


if __name__ == "__main__":
    unittest.main()
