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


class ReceiptRaisesProof(unittest.TestCase):
    """B4: a verified independent Skill 71 Review Receipt v2 of this page's mockup
    raises it to locally_verified / L2; anything less leaves it where it was."""

    def setUp(self):
        import hashlib
        import json
        import tempfile
        self.h, self.json = hashlib.sha256, json
        self.td = Path(tempfile.mkdtemp(prefix="receipt-raise-"))
        run = self.td / "checkout-run"
        (run / "visual-mockup").mkdir(parents=True)
        self.mockup = run / "visual-mockup" / "mockup.html"
        self.mockup.write_text("<html>mockup</html>", encoding="utf-8")
        record = run / "visual-mockup" / "stage-executor-record.json"
        record.write_text(json.dumps({"provider": "kie"}), encoding="utf-8")
        self.arts = [{"path": str(p), "sha256": self.sha(p)} for p in (self.mockup, record)]
        self.receipt = run / "private" / "reviews" / "visual-mockup" / "mockup.review.json"
        self.receipt.parent.mkdir(parents=True)
        self.ledger = self.td / "ledger.json"
        self.ledger.write_text(json.dumps({"sessions": [{"session_id": "rev-1", "model": "model-b"}]}),
                               encoding="utf-8")

    def sha(self, p):
        return self.h(Path(p).read_bytes()).hexdigest()

    def page(self):
        return result(status="authored", proof_class="L0", independent_review=False,
                      reviewer_session=None, artifacts=[dict(a) for a in self.arts])

    def run_review(self, **over):
        """Write the receipt (write_review.py's v2 shape), point a review record at it, apply."""
        note = "the section order, the brand hex values and every slot were checked by eye"
        rec = {"item": "mockup", "artifact": "visual-mockup/mockup.html",
               "artifact_sha256": self.sha(self.mockup), "author_session": "author-1",
               "reviewer_session": "rev-1", "reviewed_at": "2026-11-23T00:00:00+00:00",
               "criteria": {k: {"score": 9, "note": note}
                            for k in c.PAGE_RECEIPT_CRITERIA["visual-mockup"]},
               "verdict": "pass", "automatic_failures": [], "repair_attempt": 0,
               "specific_defects": [], "performed_check": "opened the mockup beside the wireframe",
               "next_current_artifact": "final-mockups", "independent_review": True,
               "author_model": "model-a", "reviewer_model": "model-b",
               "model_independence": "independent"}
        rec.update(over.pop("receipt", {}))
        self.receipt.write_text(self.json.dumps(rec), encoding="utf-8")
        pointer = {"path": "checkout-run/private/reviews/visual-mockup/mockup.review.json",
                   "sha256": self.sha(self.receipt)}
        record = review(reviewer_model="model-b", reviewed_artifacts=self.arts,
                        review_receipts=[dict(pointer, **over.pop("pointer", {}))])
        path = self.td / "review-checkout.json"
        path.write_text(self.json.dumps(record), encoding="utf-8")
        res = self.page()
        got = c.apply_review(res, path, self.ledger)
        return res, got

    def floor_83(self, res):
        sys.path.insert(0, str(HERE.parents[1] / "83-black-friday-launcher"))
        from launcher_core import checks
        return checks._proof_floor_violations({"test_only": False, "pieces": [dict(res, role="checkout")]})

    def test_a_valid_independent_receipt_raises_the_page_and_the_floor_passes(self):
        res, got = self.run_review()
        self.assertEqual((res["status"], res["proof_class"]), ("locally_verified", "L2"), res["blockers"])
        self.assertFalse(any(str(b).startswith(c.RECEIPT_PENDING) for b in res["blockers"]))
        self.assertEqual(c.validate_result(res, REQ, scope="client_delivery", **got), [])
        self.assertEqual(self.floor_83(res), [])

    def test_a_self_review_mismatch_missing_item_or_low_score_never_raises(self):
        drop = c.PAGE_RECEIPT_CRITERIA["visual-mockup"]
        cases = {
            "self-review": dict(receipt={"author_session": "rev-1"}),
            "sha mismatch": dict(receipt={"artifact_sha256": "cd" * 32}),
            "missing item": dict(receipt={"criteria": {k: {"score": 9, "note": "x" * 40}
                                                       for k in list(drop)[1:]}}),
            "below floor": dict(receipt={"criteria": {k: {"score": 7 if i == 0 else 9, "note": "x" * 40}
                                                      for i, k in enumerate(drop)}}),
            "receipt edited after it was recorded": dict(pointer={"sha256": "0" * 64}),
            "same model": dict(receipt={"author_model": "model-b"}),
        }
        for why, over in cases.items():
            res, got = self.run_review(**over)
            self.assertEqual((res["status"], res["proof_class"]), ("authored", "L0"), why)
            self.assertTrue(any(str(b).startswith(c.RECEIPT_PENDING) for b in res["blockers"]), why)
            fails = c.validate_result(res, REQ, scope="client_delivery", **got)
            self.assertTrue(any("status >=" in f for f in fails), (why, fails))
            self.assertTrue(any("proof_class >=" in f for f in fails), (why, fails))
            self.assertTrue(any("below locally_verified" in f for f in self.floor_83(res)), why)

    def test_a_stub_drawn_page_is_never_raised(self):
        record = Path(self.arts[1]["path"])
        record.write_text(self.json.dumps({"provider": "stub"}), encoding="utf-8")
        self.arts[1]["sha256"] = self.sha(record)
        res, _ = self.run_review()
        self.assertEqual((res["status"], res["proof_class"]), ("authored", "L0"))
        self.assertTrue(any("stub" in b for b in res["blockers"] if str(b).startswith(c.RECEIPT_PENDING)))

    def test_the_floor_constants_are_unchanged(self):
        self.assertEqual((c.MIN_STATUS, c.MIN_PROOF),
                         ({"client_delivery": "locally_verified"}, {"client_delivery": "L2"}))


if __name__ == "__main__":
    unittest.main()
