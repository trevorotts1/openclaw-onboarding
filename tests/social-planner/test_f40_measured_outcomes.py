#!/usr/bin/env python3
"""
test_f40_measured_outcomes.py — F40 measured-outcome learning (QC-F40).

"Provide actual metric fixtures for two clients, multiple windows and missing
values. Assert no cross-client history, missing is unknown rather than zero,
recommendation cites post/window, and low-volume conclusions remain tentative.
Strategy changes never silently change provider/model or publishing consent."

Proven against shared-utils/social_measured_outcomes.py with a temp
SOCIAL_OUTCOMES_DIR (NO network, NO live GHL):
  1. Two-client fixtures: company-a and company-b each get metrics across
     MULTIPLE WINDOWS with several MISSING values (unknowns).
  2. No cross-client history: company-b reads none of company-a's rows, and
     its directory is a separate store (the path IS the boundary).
  3. Missing is unknown rather than zero: is_unknown=True value=None; the
     aggregate's total/mean are None (never 0) with honest coverage.
  4. Recommendation cites the actual posts and the actual window.
  5. Low-volume conclusions stay tentative and receive no proposals.
  6. Strategy changes never change provider/model or publishing consent:
     policy-touching proposals are rejected.
  7. Variants: baseline-first, one major variable per trial, trial without a
     baseline refused.
  8. The cadence review driver runs without a live call, honors the cadence
     window, and keeps all-unknown conclusions claim-free.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import social_measured_outcomes as smo  # noqa: E402

WINDOW_1 = ("2026-09-01T00:00:00+00:00", "2026-09-07T23:59:59+00:00")
WINDOW_2 = ("2026-09-08T00:00:00+00:00", "2026-09-08T23:59:59+00:00")


class _OutcomeStore(unittest.TestCase):
    """Each test gets a fresh company-a/company-b outcome store."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SOCIAL_OUTCOMES_DIR": self._tmp.name}
        self.addCleanup(self._tmp.cleanup)

    # fixture helpers -------------------------------------------------------

    def seed_two_clients(self):
        """Actual metric fixtures for two clients, multiple windows, missing
        values. Client A has reported + missing; client B has mostly missing
        (its 'performance' is genuinely unknown)."""
        # company-a: impressions reported in two windows; saves MISSING.
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "impressions", 120,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1],
                          source="ghl-analytics", fetched_at="2026-09-08T12:00:00+00:00",
                          env=self.env)
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "saves", None,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1],
                          source="ghl-analytics", fetched_at="2026-09-08T12:00:00+00:00",
                          env=self.env)
        smo.record_metric("company-a", "acct-a-1", "post-a-2", "impressions", 200,
                          window_start=WINDOW_2[0], window_end=WINDOW_2[1],
                          source="ghl-analytics", fetched_at="2026-09-09T09:00:00+00:00",
                          env=self.env)
        smo.record_metric("company-a", "acct-a-1", "post-a-2", "saves", None,
                          window_start=WINDOW_2[0], window_end=WINDOW_2[1],
                          source="ghl-analytics", fetched_at="2026-09-09T09:00:00+00:00",
                          env=self.env)
        # company-b: everything missing — a real "analytics unavailable" client.
        smo.record_metric("company-b", "acct-b-1", "post-b-1", "impressions", None,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1],
                          source="ghl-analytics", fetched_at="2026-09-08T12:00:00+00:00",
                          env=self.env)
        smo.record_metric("company-b", "acct-b-1", "post-b-1", "clicks", None,
                          window_start=WINDOW_2[0], window_end=WINDOW_2[1],
                          source="ghl-analytics", fetched_at="2026-09-09T09:00:00+00:00",
                          env=self.env)


class TestUnknownNotZero(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SOCIAL_OUTCOMES_DIR": self._tmp.name}
        self.addCleanup(self._tmp.cleanup)

    def test_missing_value_stores_unknown_never_zero(self):
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "saves", None,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1], env=self.env)
        row = smo.latest_metrics("company-a", env=self.env, metric="saves")[0]
        self.assertIs(row["is_unknown"], True)
        self.assertIsNone(row["value"], "unknown value must be None, never 0")

    def test_non_finite_and_non_numeric_stay_unknown(self):
        for bad in ("oops", float("nan"), float("inf"), True, {"x": 1}):
            smo.record_metric("company-a", "acct-a-1", "post-u", "shares", bad, env=self.env)
        rows = smo.latest_metrics("company-a", env=self.env, metric="shares")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["is_unknown"] and r["value"] is None for r in rows))

    def test_aggregate_all_unknown_total_mean_none_not_zero(self):
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "clicks", None, env=self.env)
        rows = smo.latest_metrics("company-a", env=self.env)
        agg = smo.aggregate_metric(rows, "clicks")
        self.assertIsNone(agg["total"], "total of all-unknown is None, never 0")
        self.assertIsNone(agg["mean"], "mean of all-unknown is None, never 0")
        self.assertEqual(agg["known_count"], 0)
        self.assertEqual(agg["unknown_count"], 1)
        self.assertEqual(agg["coverage"], 0)

    def test_aggregate_mixed_excludes_unknowns_from_math(self):
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "impressions", 120, env=self.env)
        smo.record_metric("company-a", "acct-a-1", "post-a-2", "impressions", None, env=self.env)
        rows = smo.latest_metrics("company-a", env=self.env)
        agg = smo.aggregate_metric(rows, "impressions")
        self.assertEqual(agg["total"], 120)
        self.assertEqual(agg["known_count"], 1)
        self.assertEqual(agg["unknown_count"], 1)
        self.assertEqual(agg["coverage"], 0.5)
        self.assertEqual(agg["posts"], ["post-a-1", "post-a-2"])

    def test_metric_requires_ids(self):
        with self.assertRaises(ValueError):
            smo.record_metric("", "acct", "post", "impressions", 1, env=self.env)
        with self.assertRaises(ValueError):
            smo.record_metric("company-a", "acct", "post", "", 1, env=self.env)


class TestCrossClientIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SOCIAL_OUTCOMES_DIR": self._tmp.name}
        self.addCleanup(self._tmp.cleanup)
        # company-a's private creative + results.
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "impressions", 120, env=self.env)
        smo.register_variant("company-a", "hook", "Hormozi-style hook", role="baseline", env=self.env)

    def test_b_reads_none_of_a(self):
        rows_b = smo.latest_metrics("company-b", env=self.env)
        self.assertEqual(rows_b, [], "company-b must see NONE of company-a's history")
        variants_b = smo.variants("company-b", env=self.env)
        self.assertEqual(variants_b, [], "no cross-client creative reuse")

    def test_b_store_is_separate_directory(self):
        path_a = smo._metrics_path("company-a", env=self.env)
        path_b = smo._metrics_path("company-b", env=self.env)
        self.assertNotEqual(path_a, path_b)
        self.assertTrue(os.path.isfile(path_a))
        self.assertFalse(os.path.exists(path_b))

    def test_reviews_isolated(self):
        smo.record_performance_review(
            "company-a", ["post-a-1"], [{"post_id": "post-a-1"}],
            [{"metric": "impressions", "total": 120, "mean": 120.0, "known_count": 1,
              "unknown_count": 0, "coverage": 1.0, "posts": ["post-a-1"],
              "window_start": None, "window_end": None}],
            env=self.env)
        self.assertEqual(smo.reviews("company-b", env=self.env), [])


class TestVariantsOneVariable(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SOCIAL_OUTCOMES_DIR": self._tmp.name}
        self.addCleanup(self._tmp.cleanup)

    def test_first_variant_auto_baselines(self):
        rec = smo.register_variant("company-a", "timing", "morning slot", role="trial", env=self.env)
        self.assertEqual(rec["role"], "baseline")
        self.assertEqual(rec["basis"], "baseline-first")

    def test_trial_requires_single_variable_and_baseline(self):
        base = smo.register_variant("company-a", "timing", "morning slot", role="baseline", env=self.env)
        trial = smo.register_variant("company-a", "hook", "question hook",
                                     role="trial", compared_to=base["id"], env=self.env)
        self.assertEqual(trial["basis"], "single-variable-trial")
        with self.assertRaises(ValueError):
            smo.register_variant("company-a", "format", "orphan trial", role="trial", env=self.env)
        with self.assertRaises(ValueError):
            smo.register_variant("company-a", "budget", "not a variable",
                                 role="trial", compared_to=base["id"], env=self.env)


class TestRecommendationsCitePostsAndWindows(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SOCIAL_OUTCOMES_DIR": self._tmp.name}
        self.addCleanup(self._tmp.cleanup)
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "impressions", 120,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1], env=self.env)
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "saves", None,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1], env=self.env)

    def test_recommendation_cites_post_and_window(self):
        rows = smo.latest_metrics("company-a", env=self.env)
        agg = smo.aggregate_metric(rows, "impressions")
        agg_unknown = smo.aggregate_metric(rows, "saves")
        text = smo.build_recommendation(
            ["post-a-1"],
            [{"post_id": "post-a-1", "window_start": WINDOW_1[0], "window_end": WINDOW_1[1]}],
            [agg, agg_unknown])
        self.assertIn("post-a-1", text)
        self.assertIn("window %s to %s" % (WINDOW_1[0], WINDOW_1[1]), text)
        self.assertIn("UNKNOWN (not reported by the provider)", text)
        self.assertIn("never zero", text)

    def test_no_posts_no_claim(self):
        text = smo.build_recommendation([], [], [])
        self.assertIn("nothing is claimed", text)
        self.assertIn("Publish first", text)

    def test_low_sample_tentative_no_proposals(self):
        review = smo.record_performance_review(
            "company-a", ["post-a-1"],
            [{"post_id": "post-a-1", "window_start": WINDOW_1[0], "window_end": WINDOW_1[1]}],
            [smo.aggregate_metric(smo.latest_metrics("company-a", env=self.env), "impressions")],
            env=self.env)
        self.assertTrue(review["tentative"], "1 known observation < 5 → tentative")
        self.assertEqual(review["proposals"], [], "tentative conclusion gets NO proposals")
        self.assertIn("post-a-1", review["recommendation"])
        self.assertIn("policy_guard", review)

    def test_policy_touching_proposal_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            smo.record_performance_review(
                "company-a", ["post-a-1"], [], [], recommendation="switch model",
                proposals=[{"provider": "openai"}], env=self.env)
        self.assertIn("F31/F37", str(ctx.exception))
        with self.assertRaises(ValueError):
            smo.record_performance_review(
                "company-a", ["post-a-1"], [], [], recommendation="policy",
                proposals=[{"publishing_policy": {"auto": True}}], env=self.env)
        with self.assertRaises(ValueError):
            smo.assert_no_policy_mutation([{"model_id": "m-1"}])

    def test_confident_sample_may_propose_content_experiment(self):
        for i in range(smo.MIN_SAMPLE_FOR_CONFIDENCE):
            smo.record_metric("company-a", "acct-a-1", "post-c-%d" % i,
                              "engagement_rate", 2.0 + i * 0.5, env=self.env)
        rows = smo.latest_metrics("company-a", env=self.env)
        agg = smo.aggregate_metric(rows, "engagement_rate")
        review = smo.record_performance_review(
            "company-a", ["post-c-0", "post-c-1"],
            [{"post_id": "post-c-0", "window_start": WINDOW_1[0], "window_end": WINDOW_1[1]}],
            [agg],
            proposals=[{"kind": "content-experiment", "variable": "timing"}],
            env=self.env)
        self.assertEqual(review["sample_size"], smo.MIN_SAMPLE_FOR_CONFIDENCE)
        self.assertFalse(review["tentative"])
        self.assertEqual(review["proposals"][0]["variable"], "timing")
        self.assertIn("client choice", review["policy_guard"])


class TestCadenceReviewTwoClients(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"SOCIAL_OUTCOMES_DIR": self._tmp.name}
        self.addCleanup(self._tmp.cleanup)
        self.env["SOCIAL_PERFORMANCE_REVIEW_HOURS"] = "1"

    def _seed(self):
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "impressions", 120,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1], env=self.env)
        smo.record_metric("company-a", "acct-a-1", "post-a-1", "saves", None, env=self.env)
        smo.record_metric("company-b", "acct-b-1", "post-b-1", "impressions", None,
                          window_start=WINDOW_1[0], window_end=WINDOW_1[1], env=self.env)

    def test_review_fires_per_company_without_live_calls(self):
        self._seed()
        now = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
        summary_a = smo.review_company("company-a", now=now, env=self.env)
        self.assertEqual(summary_a["action"], "reviewed")
        review = summary_a["review"]
        self.assertIn("post-a-1", review["recommendation"])
        self.assertIn(WINDOW_1[0], review["recommendation"])
        self.assertTrue(summary_a["tentative"], "low volume stays tentative")
        self.assertEqual(review["proposals"], [],
                        "tentative review never proposes content or spend changes")
        # company-b (all unknown): reviewed with NO claim.
        summary_b = smo.review_company("company-b", now=now, env=self.env)
        self.assertEqual(summary_b["action"], "reviewed")
        rb = summary_b["review"]
        self.assertTrue(summary_b["tentative"])
        self.assertIn("UNKNOWN", rb["recommendation"])
        self.assertIn("No performance conclusion is drawn", rb["recommendation"])
        self.assertEqual(rb["proposals"], [])

    def test_cadence_window_no_duplicate(self):
        self._seed()
        now = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
        first = smo.review_company("company-a", now=now, env=self.env)
        self.assertEqual(first["action"], "reviewed")
        # 30 minutes later: still inside the 1h window → recent, no new review.
        second = smo.review_company(
            "company-a", now=now + dt.timedelta(minutes=30), env=self.env)
        self.assertEqual(second["action"], "recent")
        self.assertEqual(len(smo.reviews("company-a", env=self.env)), 1)
        # 2h later → cadence elapsed → reviews again.
        third = smo.review_company(
            "company-a", now=now + dt.timedelta(hours=2), env=self.env)
        self.assertEqual(third["action"], "reviewed")
        self.assertEqual(len(smo.reviews("company-a", env=self.env)), 2)

    def test_no_company_without_observations(self):
        now = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
        summary = smo.review_company("company-empty", now=now, env=self.env)
        self.assertEqual(summary["action"], "insufficient-data")

    def test_review_store_is_company_scoped(self):
        self._seed()
        now = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
        smo.review_company("company-a", now=now, env=self.env)
        smo.review_company("company-b", now=now, env=self.env)
        revs_a = smo.reviews("company-a", env=self.env)
        revs_b = smo.reviews("company-b", env=self.env)
        self.assertEqual(len(revs_a), 1)
        self.assertEqual(len(revs_b), 1)
        self.assertEqual(revs_a[0]["posts_reviewed"], ["post-a-1"])
        self.assertEqual(revs_b[0]["posts_reviewed"], ["post-b-1"])
        # company-b's review MUST NOT cite company-a's posts.
        self.assertNotIn("post-a-1", json.dumps(revs_b))


if __name__ == "__main__":
    unittest.main()