"""ENF-10: validate_result enforces a minimum proof per delivery scope and
never lets two session strings stand in for an independent review."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collect_launch_receipts as c  # noqa: E402

SHA = "ab" * 32
LEDGER = {"sessions": ["rev-1", "author-1"]}
REQ = {"request_id": "rq", "input_hash": "ih", "page_id": "P",
       "launch_id": "X", "revision": 1, "tenant_id": "T",
       "location_id": "L", "test_only": False}


def result(**kw):
    r = {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
         "launch_id": "X", "revision": 1, "request_id": "rq",
         "input_hash": "ih", "page_id": "P", "status": "locally_verified",
         "artifacts": [{"path": "a.png", "sha256": SHA}],
         "author_session": "author-1", "reviewer_session": "rev-1",
         "independent_review": True, "proof_class": "L2", "blockers": [],
         "native_bindings_ref": None, "test_only": False}
    r.update(kw)
    return r


def review(**kw):
    r = {"schema": "signature-launch-review-record/v1",
         "reviewer_session": "rev-1", "reviewer_model": "m",
         "verdict": "pass", "request_id": "rq",
         "reviewed_artifacts": [{"path": "a.png", "sha256": SHA}]}
    r.update(kw)
    return r


def val(res, scope="client_delivery", rec=None, ledger=LEDGER):
    return c.validate_result(res, REQ, scope=scope, ledger=ledger,
                             review=review() if rec is None else rec)


class MinimumProof(unittest.TestCase):
    def test_full_proof_accepted(self):
        self.assertEqual(val(result()), [])

    def test_authored_and_l1_refused_for_delivery_not_rehearsal(self):
        weak = result(status="authored", proof_class="L1",
                      independent_review=False, reviewer_session=None)
        self.assertTrue(any("status >=" in f for f in val(weak)))
        self.assertTrue(any("proof_class >=" in f for f in val(weak)))
        self.assertEqual(c.validate_result(weak, REQ, scope="rehearsal"), [])

    def test_delivery_needs_independent_review_and_artifacts(self):
        no_rev = result(independent_review=False, reviewer_session=None)
        self.assertTrue(any("independent review" in f for f in val(no_rev)))
        self.assertTrue(any("design artifacts" in f
                            for f in val(result(artifacts=[]))))

    def test_blocked_result_is_still_reportable(self):
        self.assertEqual(val(result(status="blocked", proof_class="L0",
                                    independent_review=False,
                                    reviewer_session=None, artifacts=[])), [])

    def test_strings_alone_are_not_independent(self):
        # reviewer 'a' vs author 'b': two different strings, no record/ledger
        r = result(author_session="b", reviewer_session="a")
        for scope in c.SCOPES:
            self.assertTrue(any("two session strings" in f for f in
                                c.validate_result(r, REQ, scope=scope)))
        # a record whose reviewer is not in the dispatch ledger is refused
        self.assertTrue(val(r, rec=review(reviewer_session="a")))

    def test_review_must_cover_every_artifact(self):
        two = result(artifacts=[{"path": "a.png", "sha256": SHA},
                                {"path": "b.png", "sha256": "cd" * 32}])
        self.assertTrue(any("not listed" in f for f in val(two)))

    def test_collect_withholds_delivery_for_authored_set(self):
        manifest = {"launch_id": "X", "revision": 1, "plan_document_hash": "p",
                    "route_graph_hash": "g", "execution": "executed",
                    "requests": [{"request_id": "rq", "page_id": "P",
                                  "page_role": "landing", "input_hash": "ih"}]}
        weak = result(status="authored", proof_class="L0",
                      independent_review=False, reviewer_session=None)
        cp = c.collect(manifest, [weak], {"rq": REQ}, scope="client_delivery",
                       ledger=LEDGER)
        self.assertEqual(cp["roles_reported"], [])
        self.assertEqual(cp["missing_roles"], ["landing"])
        self.assertTrue(cp["problems"])


class ApplyReview(unittest.TestCase):
    """Issue 30: apply_review makes a wrapper's result honest about its review."""

    def setUp(self):
        import json
        import tempfile
        self.json = json
        self.td = Path(tempfile.mkdtemp(prefix="apply-review-"))
        self.ledger = self.td / "ledger.json"
        self.ledger.write_text(json.dumps(LEDGER), encoding="utf-8")

    def rec(self, rec, name="review.json"):
        path = self.td / name
        path.write_text(rec if isinstance(rec, str) else self.json.dumps(rec), encoding="utf-8")
        return path

    def unreviewed(self, **kw):
        return result(independent_review=False, reviewer_session=None, **kw)

    def pending(self, res):
        hits = [b for b in res["blockers"] if b.startswith("REVIEW-PENDING")]
        self.assertEqual(len(hits), 1, res["blockers"])
        return hits[0]

    def assertHonest(self, res, proof="L1"):
        self.assertIs(res["independent_review"], False)
        self.assertIsNone(res["reviewer_session"])
        self.assertEqual((res["status"], res["proof_class"]), ("authored", proof))

    def test_no_record_keeps_the_page_authored_and_pending(self):
        res = result(blockers=["EARLIER"])
        self.assertIsNone(c.apply_review(res, None, self.ledger))
        self.assertHonest(res)
        self.assertEqual(res["blockers"][0], "EARLIER")
        text = self.pending(res)
        self.assertIn("no review record was supplied", text)
        self.assertTrue(text.endswith("a client delivery refuses it"), text)

    def test_the_proof_class_is_capped_at_l1_and_never_raised(self):
        for before, after in (("L0", "L0"), ("L1", "L1"), ("L2", "L1"), ("L3", "L1"), ("L5", "L1")):
            res = result(proof_class=before)
            c.apply_review(res, None, self.ledger)
            self.assertEqual(res["proof_class"], after, before)

    def test_an_unreadable_or_malformed_or_non_object_record_is_pending_not_a_crash(self):
        for why, path in (("missing", self.td / "absent.json"),
                          ("malformed", self.rec("{not json", "bad.json")),
                          ("a list", self.rec("[1, 2]", "list.json"))):
            res = result()
            self.assertIsNone(c.apply_review(res, path, self.ledger), why)
            self.assertHonest(res)
            self.assertIn("unreadable", self.pending(res), why)
        res = result()
        c.apply_review(res, self.rec("[1]", "list2.json"), self.ledger)
        self.assertIn("not an object", self.pending(res))

    def test_an_unreadable_ledger_is_pending(self):
        for ledger in (self.td / "absent-ledger.json", self.rec("{nope", "bad-ledger.json")):
            res = result()
            self.assertIsNone(c.apply_review(res, self.rec(review()), ledger))
            self.assertHonest(res)
            self.assertIn("unreadable", self.pending(res))

    def test_no_ledger_path_means_no_reviewer_can_be_vouched_for(self):
        res = result()
        self.assertIsNone(c.apply_review(res, self.rec(review()), None))
        self.assertHonest(res)
        self.assertIn("was refused", self.pending(res))

    def test_an_accepted_record_sets_the_review_fields_and_keeps_the_status(self):
        res = self.unreviewed(blockers=["EARLIER"])
        got = c.apply_review(res, self.rec(review()), self.ledger)
        self.assertEqual(got, {"ledger": LEDGER, "review": review()})
        self.assertIs(res["independent_review"], True)
        self.assertEqual(res["reviewer_session"], "rev-1")
        self.assertEqual((res["status"], res["proof_class"]), ("locally_verified", "L2"))
        self.assertEqual(res["blockers"], ["EARLIER"])
        self.assertEqual(c.validate_result(res, REQ, scope="client_delivery", **got), [])

    def test_a_refused_record_clears_a_claimed_review_and_names_why(self):
        res = result()  # claims a review by rev-1
        self.assertIsNone(c.apply_review(res, self.rec(review(verdict="FAIL")), self.ledger))
        self.assertHonest(res)
        self.assertIn("review record was refused", self.pending(res))
        self.assertIn("no recognised successful verdict", self.pending(res))

    def test_stale_artifacts_are_named_and_listed_ones_are_not(self):
        arts = [{"path": "kept.png", "sha256": SHA}, {"path": "moved.png", "sha256": "cd" * 32}]
        res = self.unreviewed(artifacts=arts)
        rec = review(reviewed_artifacts=[{"path": "kept.png", "sha256": SHA}])
        self.assertIsNone(c.apply_review(res, self.rec(rec), self.ledger))
        text = self.pending(res)
        self.assertIn("does not list: moved.png", text)
        self.assertNotIn("kept.png", text)

    def test_the_stale_list_stops_at_ten_with_an_ellipsis(self):
        for count, ellipsis in ((10, False), (11, True), (12, True)):
            arts = [{"path": f"p{i:02d}.png", "sha256": f"{i:02d}" * 32} for i in range(count)]
            res = self.unreviewed(artifacts=arts)
            rec = review(reviewed_artifacts=[{"path": "other.png", "sha256": SHA}])
            c.apply_review(res, self.rec(rec), self.ledger)
            text = self.pending(res)
            shown = [a["path"] for a in arts if a["path"] in text.split("does not list: ", 1)[1]]
            self.assertEqual(len(shown), min(count, 10), count)
            self.assertEqual(text.split("does not list: ", 1)[1].split(";")[0].endswith(" ..."),
                             ellipsis, count)


if __name__ == "__main__":
    unittest.main()
