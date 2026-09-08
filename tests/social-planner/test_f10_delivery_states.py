#!/usr/bin/env python3
"""F10 — Prove publishing for each destination and status.

QC-F10 matrix (unittest, NO network):
  1. Three account deliveries read back draft / scheduled / failed: ONLY
     published counts as published; every destination has its OWN delivery
     row (per company/cycle/content-revision/account).
  2. A scheduled post that becomes published after its due time reconciles.
  3. A create success followed by a timeout reconciles the remote post id
     before any retry — NO duplicate post is created.
  4. Only failed destinations are retry candidates; unknown (ambiguous) must
     be reconciled first.

Run:  python3 -m unittest tests.social-planner.test_f10_delivery_states -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SKILL_DIR = _REPO_ROOT / "57-social-media-in-a-box"
_RUNNER_PATH = _SKILL_DIR / "run_social_media.py"
assert _RUNNER_PATH.is_file()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rsm = _load("run_social_media_f10", _RUNNER_PATH)


def _run_dir(tmp, accounts=("fb-1", "ig-1", "li-1")):
    rd = Path(tmp) / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "publish").mkdir(parents=True, exist_ok=True)
    (rd / "delivery").mkdir(parents=True, exist_ok=True)
    cfg = {"brandName": "Brand One", "locationId": "loc-1", "userId": "u-1",
           "timezone": "America/New_York", "status": "Paid"}
    (rd / "working" / "copy" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (rd / "working" / "execution_mode.json").write_text(
        json.dumps({"mode": "production", "set_by": "trusted-entry", "simulated": False}),
        encoding="utf-8")
    (rd / "delivery" / "PROCESS-CERTIFICATE.json").write_text("{}", encoding="utf-8")
    plan = {"weekOf": "2026-09-07", "themeOfWeek": "Theme", "plannerSheetId": "sheet-1",
            "companyId": "co-1", "cycleId": "cy-1", "contentRevision": 3,
            "accounts": [{"account_id": a, "platform": p, "account_name": a}
                         for a, p in zip(accounts, ("facebook", "instagram", "linkedin"))]}
    (rd / "working" / "plan").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    results = [{"kind": "publish_result", "platform": "facebook", "success": True,
                "totalPosts": len(accounts), "processedAccounts": len(accounts), "errors": []}]
    (rd / "working" / "publish" / "publish_results.json").write_text(
        json.dumps(results), encoding="utf-8")
    return rd


def _listing(accounts_states):
    """The INDEPENDENT readback shape (ghl_contracts.normalize_post output)."""
    return [{"post_id": pid, "status": state, "scheduled_at": sched, "published_url": url}
            for pid, state, sched, url in accounts_states]


class TestStateMatrix(unittest.TestCase):
    """QC-F10: draft/scheduled/failed readbacks -> ONLY published is published."""

    def test_three_accounts_three_outcomes(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            # Seed the poster's rows, then reconcile against an independent
            # readback where fb-1 is draft, ig-1 scheduled, li-1 failed.
            for aid in ("fb-1", "ig-1", "li-1"):
                rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, aid,
                                         remote_post_id="post-%s" % aid,
                                         provider_state="unknown")
            rsm._reconcile_deliveries_from_listing(rd, _listing([
                ("post-fb-1", "draft", None, None),
                ("post-ig-1", "scheduled", "2026-09-09T09:00:00Z", None),
                ("post-li-1", "failed", None, None),
            ]))
            published = rsm._delivery_published_set(rd)
            self.assertEqual(published, set())  # NOTHING is published
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(len(rows), 3)  # one row PER destination
            self.assertEqual(rows["fb-1"]["provider_state"], "draft")
            self.assertEqual(rows["ig-1"]["provider_state"], "scheduled")
            self.assertEqual(rows["li-1"]["provider_state"], "failed")
            self.assertEqual(rows["ig-1"]["content_revision"], 3)

    def test_published_after_due_time_reconciles(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="scheduled",
                                     scheduled_at="2026-09-09T09:00:00Z")
            rsm._reconcile_deliveries_from_listing(rd, _listing([
                ("post-fb-1", "published", "2026-09-09T09:00:00Z",
                 "https://facebook.com/brand/posts/1"),
            ]))
            published = rsm._delivery_published_set(rd)
            self.assertEqual(published, {"fb-1"})
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(rows["fb-1"]["published_url"],
                             "https://facebook.com/brand/posts/1")

    def test_missing_status_is_unknown_never_published(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._reconcile_deliveries_from_listing(rd, _listing([
                ("post-fb-1", "", None, None),  # no status field
            ]))
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(rows["fb-1"]["provider_state"], "unknown")
            self.assertNotIn("fb-1", rsm._delivery_published_set(rd))

    def test_empty_listing_keeps_unknown_and_names_it(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            rsm._reconcile_deliveries_from_listing(rd, [])
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(rows["fb-1"]["provider_state"], "unknown")
            self.assertIn("reconcile", rows["fb-1"]["failure_reason"])


class TestTimeoutReconciliation(unittest.TestCase):
    """QC-F10: create success + timeout -> reconcile remote id, NO duplicate."""

    def test_lost_response_adopts_existing_post(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            # The poster CREATED post-fb-1 then the response was lost: the
            # staged row already carries the adopted remote id.
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id="post-fb-1", provider_state="unknown",
                                     failure_reason="create timeout (response lost)")
            # The reconcile pass runs BEFORE any retry: the row adopts the
            # EXISTING remote post (published), no second post is created.
            rsm._reconcile_deliveries_from_listing(rd, _listing([
                ("post-fb-1", "published", None, "https://facebook.com/x/1"),
            ]))
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(len(rows), 1)                       # ONE destination row
            self.assertEqual(rows["fb-1"]["remote_post_id"], "post-fb-1")
            self.assertEqual(rows["fb-1"]["provider_state"], "published")
            self.assertEqual(len(rsm._retryable_deliveries(rd)), 0)

    def test_content_key_scan_adopts_when_id_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, accounts=("fb-1",))
            # The staged row has NO remote id (the response was lost before
            # any id was recorded); the listing post carries the content key.
            rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, "fb-1",
                                     remote_post_id=None, provider_state="unknown")
            listing = [{"post_id": "post-x", "status": "published", "scheduled_at": None,
                        "published_url": None,
                        "meta": {"account_id": "fb-1", "content_revision": 3}}]
            rsm._reconcile_deliveries_from_listing(rd, listing)
            rows = {r["account_id"]: r for r in rsm._delivery_rows(rd)}
            self.assertEqual(rows["fb-1"]["remote_post_id"], "post-x")
            self.assertEqual(rows["fb-1"]["provider_state"], "published")

    def test_retry_only_failed(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            for aid, st in (("fb-1", "draft"), ("ig-1", "failed"), ("li-1", "unknown")):
                rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, aid, provider_state=st)
            retryable = rsm._retryable_deliveries(rd)
            self.assertEqual([r["account_id"] for r in retryable], ["ig-1"])


class TestLivePublishGate(unittest.TestCase):
    """The production _chk_publish path reconciles rows and requires EVERY
    expected destination published; mock the independent readback."""

    def test_live_gate_requires_all_published(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            for aid in ("fb-1", "ig-1", "li-1"):
                rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, aid,
                                         remote_post_id="post-%s" % aid, provider_state="unknown")
            (rd / "working" / "publish" / "posted_ids.json").write_text(
                json.dumps(["post-fb-1", "post-ig-1", "post-li-1"]), encoding="utf-8")
            listing = _listing([
                ("post-fb-1", "published", None, "u1"),
                ("post-ig-1", "scheduled", "2026-09-09T09:00:00Z", None),   # not yet
                ("post-li-1", "failed", None, None),
            ])
            orig = rsm._live_ghl_post_listing_with_status
            rsm._live_ghl_post_listing_with_status = lambda cfg: listing
            try:
                ok, msg = rsm._chk_publish(rd)
            finally:
                rsm._live_ghl_post_listing_with_status = orig
            self.assertFalse(ok)
            self.assertIn("AF-SM-PUBLISH-UNVERIFIED", msg)
            self.assertIn("ig-1=scheduled", msg)

    def test_live_gate_passes_when_all_published(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            for aid in ("fb-1", "ig-1", "li-1"):
                rsm._upsert_delivery_row(rd, "co-1", "cy-1", 3, aid,
                                         remote_post_id="post-%s" % aid, provider_state="unknown")
            (rd / "working" / "publish" / "posted_ids.json").write_text(
                json.dumps(["post-fb-1", "post-ig-1", "post-li-1"]), encoding="utf-8")
            listing = _listing([
                ("post-fb-1", "published", None, "u1"),
                ("post-ig-1", "published", None, "u2"),
                ("post-li-1", "published", None, "u3"),
            ])
            orig = rsm._live_ghl_post_listing_with_status
            rsm._live_ghl_post_listing_with_status = lambda cfg: listing
            try:
                ok, msg = rsm._chk_publish(rd)
            finally:
                rsm._live_ghl_post_listing_with_status = orig
            self.assertTrue(ok, msg)
            self.assertEqual(rsm._delivery_published_set(rd), {"fb-1", "ig-1", "li-1"})


if __name__ == "__main__":
    unittest.main()