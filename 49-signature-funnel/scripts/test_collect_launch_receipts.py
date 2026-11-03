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
         "request_id": "rq",
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


if __name__ == "__main__":
    unittest.main()
