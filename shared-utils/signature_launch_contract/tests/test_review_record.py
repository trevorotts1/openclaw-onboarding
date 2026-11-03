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
         "reviewer_model": "m1", "request_id": "rq",
         "reviewed_artifacts": [{"path": "a.png", "sha256": A},
                                {"path": "b.png", "sha256": B}]}
    r.update(kw)
    return r


def check(r, ledger=LEDGER, author="author-1", arts=ARTS):
    return rr.validate_review_record(r, ledger=ledger, author_session=author,
                                     artifacts=arts, request_id="rq")


class ReviewRecord(unittest.TestCase):
    def test_accepted(self):
        self.assertEqual(check(rec()), [])
        self.assertEqual(check(rec(), ledger=["rev-1"]), [])

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


if __name__ == "__main__":
    unittest.main()
