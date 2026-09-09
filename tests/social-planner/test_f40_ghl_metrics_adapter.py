#!/usr/bin/env python3
"""
test_f40_ghl_metrics_adapter.py — F40 GHL analytics adapter contract (QC-F40,
adapter half).

The adapter seam extends Skill 57's documented ghl_contracts.py (F09 S1/S2
patterns; fake transports, NO network):
  - a posts/list payload with provider-reported engagement normalizes into
    metric observations carrying post/account id, window and fetched_at;
  - a metric the payload does NOT carry is an explicit UNKNOWN row
    (value None, is_unknown True) — never zero, never interpolated;
  - a post with no resolvable id yields no rows (never an invented post);
  - end-to-end: adapter rows feed social_measured_outcomes.record_metric and
    the aggregate preserves unknown-not-zero.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "57-social-media-in-a-box" / "scripts"
_REPO_ROOT = _HERE.parent.parent


def _load(name, path):
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ghl_contracts = _load("ghl_contracts_f40", _SCRIPTS / "ghl_contracts.py")

_ONB_ROOT = str(_REPO_ROOT)
if _ONB_ROOT + "/shared-utils" not in sys.path:
    sys.path.insert(0, _ONB_ROOT + "/shared-utils")
import social_measured_outcomes as smo  # noqa: E402


class TestExtractPostMetrics(unittest.TestCase):
    def test_reported_metrics_extracted_with_ids_and_window(self):
        raw = {
            "_id": "post-1",
            "accountId": "acct-1",
            "counts": {"reactions": 12, "comments": 3},
            "metrics": {"impressions": 800, "reach": 640},
        }
        rows = ghl_contracts.extract_post_metrics(
            raw, fetched_at="2026-09-09T10:00:00+00:00",
            window_start="2026-09-08T00:00:00+00:00",
            window_end="2026-09-09T00:00:00+00:00")
        by_metric = {r["metric"]: r for r in rows}
        self.assertEqual(by_metric["impressions"]["value"], 800.0)
        self.assertFalse(by_metric["impressions"]["is_unknown"])
        self.assertEqual(by_metric["reach"]["value"], 640.0)
        self.assertEqual(by_metric["reactions"]["value"], 12.0)
        self.assertEqual(by_metric["comments"]["value"], 3.0)
        for r in rows:
            self.assertEqual(r["post_id"], "post-1")
            self.assertEqual(r["account_id"], "acct-1")
            self.assertEqual(r["fetched_at"], "2026-09-09T10:00:00+00:00")
            self.assertEqual(r["window_start"], "2026-09-08T00:00:00+00:00")
            self.assertEqual(r["window_end"], "2026-09-09T00:00:00+00:00")
            self.assertEqual(r["source"], "ghl-analytics")

    def test_unreported_metric_is_unknown_never_zero(self):
        raw = {"_id": "post-2", "counts": {"reactions": 5}}
        rows = ghl_contracts.extract_post_metrics(raw)
        by_metric = {r["metric"]: r for r in rows}
        self.assertFalse(by_metric["reactions"]["is_unknown"])
        self.assertEqual(by_metric["reactions"]["value"], 5.0)
        for metric in ("impressions", "reach", "comments", "clicks"):
            self.assertTrue(by_metric[metric]["is_unknown"],
                            "%s unreported must be unknown" % metric)
            self.assertIsNone(by_metric[metric]["value"], "never a fabricated 0")

    def test_non_numeric_string_value_stays_unknown(self):
        raw = {"_id": "post-3", "metrics": {"impressions": "not-a-number"}}
        rows = ghl_contracts.extract_post_metrics(raw)
        by_metric = {r["metric"]: r for r in rows}
        self.assertTrue(by_metric["impressions"]["is_unknown"])
        self.assertIsNone(by_metric["impressions"]["value"])

    def test_no_post_id_yields_no_invented_rows(self):
        raw = {"metrics": {"impressions": 10}}
        rows = ghl_contracts.extract_post_metrics(raw)
        self.assertEqual(rows, [])

    def test_e2e_into_outcome_store_unknown_preserved(self):
        env = {"SOCIAL_OUTCOMES_DIR": tempfile.mkdtemp()}
        raw = {"_id": "post-e2e", "accountId": "acct-e2e",
               "metrics": {"impressions": 500}}
        for obs in ghl_contracts.extract_post_metrics(
                raw, fetched_at="2026-09-09T10:00:00+00:00"):
            smo.record_metric(
                "company-e2e", obs["account_id"] or "acct-e2e", obs["post_id"],
                obs["metric"], obs["value"],
                window_start=obs["window_start"], window_end=obs["window_end"],
                source=obs["source"], fetched_at=obs["fetched_at"], env=env)
        rows = smo.latest_metrics("company-e2e", env=env)
        agg_known = smo.aggregate_metric(rows, "impressions")
        self.assertEqual(agg_known["total"], 500.0)
        agg_unknown = smo.aggregate_metric(rows, "clicks")
        self.assertIsNone(agg_unknown["total"], "unreported clicks: total None, never 0")
        self.assertEqual(agg_unknown["unknown_count"], 1)
        # Cross-client: another company sees none of it.
        self.assertEqual(smo.latest_metrics("company-other", env=env), [])


if __name__ == "__main__":
    unittest.main()