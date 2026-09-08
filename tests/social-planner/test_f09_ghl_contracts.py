#!/usr/bin/env python3
"""F09 — GHL API contract tests (unittest, fake transports, NO network).

Proves the documented S1/S2 contracts are implemented exactly:
  S1  GET /social-media-posting/:locationId/accounts, Version header,
      results.accounts wrapper, account IDs preserved.
  S2  POST /social-media-posting/:locationId/posts/list, number-string
      skip/limit body, results wrapper, skip/offset pagination, status fields.
  Error taxonomy: 401 authentication / 403 scope / 404 disconnected_account /
  429 rate_limited (Retry-After honored) / transient / contract (a malformed
  2xx body is NEVER misreported as zero accounts).

Run:  python3 -m unittest tests.social_planner... (or discover -s tests/social-planner)
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "57-social-media-in-a-box" / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ghl_contracts = _load("ghl_contracts")


def _fake_transport(status, body, headers=None):
    """A fake transport: (method, url, headers, body) -> (status, bytes, headers)."""
    hdrs = headers or {}

    def transport(method, url, req_headers, req_body):
        return status, json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body, hdrs
    return transport


def _recording_transport(status, body, calls, headers=None):
    hdrs = headers or {}

    def transport(method, url, req_headers, req_body):
        calls.append({"method": method, "url": url, "headers": dict(req_headers),
                      "body": req_body})
        return status, json.dumps(body).encode("utf-8"), hdrs
    return transport


class TestAccountsContract(unittest.TestCase):
    """S1 — GET /social-media-posting/:locationId/accounts."""

    def test_method_path_and_version_header(self):
        calls = []
        body = {"results": {"accounts": [{"id": "fb-1", "name": "Main FB", "platform": "facebook"}]}}
        t = _recording_transport(200, body, calls)
        accounts = ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=t)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[0]["url"],
                         "https://services.leadconnectorhq.com/social-media-posting/loc-abc/accounts")
        self.assertEqual(calls[0]["headers"].get("Version"), ghl_contracts.API_VERSION)
        self.assertTrue(str(calls[0]["headers"].get("Authorization", "")).startswith("Bearer "))

    def test_results_accounts_wrapper_parsed_ids_preserved(self):
        body = {"results": {"accounts": [
            {"id": "fb-1", "name": "Main FB", "platform": "facebook"},
            {"id": "fb-2", "name": "Second FB", "platform": "facebook"},
            {"id": "ig-1", "name": "Main IG", "platform": "instagram"}]}}
        accounts = ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=_fake_transport(200, body))
        self.assertEqual(len(accounts), 3)
        ids = [a["account_id"] for a in accounts]
        # IDs PRESERVED — two facebook accounts are distinct rows, never collapsed.
        self.assertEqual(ids, ["fb-1", "fb-2", "ig-1"])
        self.assertEqual([a["platform"] for a in accounts], ["facebook", "facebook", "instagram"])
        self.assertEqual(accounts[0]["account_name"], "Main FB")

    def test_empty_results_is_empty_not_error(self):
        body = {"results": {"accounts": []}}
        accounts = ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=_fake_transport(200, body))
        self.assertEqual(accounts, [])

    def test_malformed_results_is_contract_error_never_zero(self):
        # results missing entirely
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.parse_accounts_payload({"message": "Fetched Accounts"})
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_CONTRACT)
        # results is a dict without accounts
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.parse_accounts_payload({"results": {"nope": 1}})
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_CONTRACT)
        # a bare non-dict payload
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.parse_accounts_payload([1, 2, 3])
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_CONTRACT)

    def test_error_taxonomy_401(self):
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=_fake_transport(401, {}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_AUTHENTICATION)
        self.assertEqual(ctx.exception.status, 401)

    def test_error_taxonomy_403_scope(self):
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=_fake_transport(403, {}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_SCOPE)

    def test_error_taxonomy_404_disconnected_account(self):
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=_fake_transport(404, {}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_DISCONNECTED_ACCOUNT)

    def test_error_taxonomy_429_rate_limited_honors_retry_after(self):
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_accounts("pit-test", "loc-abc",
                                         transport=_fake_transport(429, {}, {"Retry-After": "7"}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_RATE_LIMITED)
        self.assertEqual(ctx.exception.retry_after, 7)

    def test_error_taxonomy_transient_timeout_and_5xx(self):
        def dead_transport(method, url, headers, body):
            raise TimeoutError("simulated timeout")
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=dead_transport)
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_TRANSIENT)
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_accounts("pit-test", "loc-abc", transport=_fake_transport(503, {}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_TRANSIENT)


class TestPostsListContract(unittest.TestCase):
    """S2 — POST /social-media-posting/:locationId/posts/list."""

    def test_method_path_version_and_number_string_body(self):
        calls = []
        body = {"results": {"posts": []}}
        t = _recording_transport(200, body, calls)
        ghl_contracts.fetch_posts("pit-test", "loc-abc", transport=t)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["url"],
                         "https://services.leadconnectorhq.com/social-media-posting/loc-abc/posts/list")
        self.assertEqual(calls[0]["headers"].get("Version"), ghl_contracts.API_VERSION)
        sent = json.loads(calls[0]["body"].decode("utf-8"))
        # The live-422 contract: skip/limit are NUMBER STRINGS, not JSON integers.
        self.assertEqual(sent["skip"], "0")
        self.assertEqual(sent["limit"], str(ghl_contracts.DEFAULT_PAGE_LIMIT))
        self.assertIsInstance(sent["skip"], str)
        self.assertIsInstance(sent["limit"], str)
        self.assertNotIn("locationId", sent)  # URL path carries the location; body must not repeat it

    def test_results_wrapper_and_status_fields(self):
        body = {"results": {"posts": [
            {"_id": "p1", "status": "published", "locationId": "loc-abc"},
            {"_id": "p2", "status": "scheduled"},
            {"_id": "p3", "status": "draft"},
            {"_id": "p4", "status": "failed"},
            {"_id": "p5"}]}}
        posts = ghl_contracts.fetch_posts("pit-test", "loc-abc", transport=_fake_transport(200, body))
        by_id = {p["post_id"]: p for p in posts}
        self.assertEqual(by_id["p1"]["status"], "published")
        self.assertEqual(by_id["p2"]["status"], "scheduled")
        self.assertEqual(by_id["p3"]["status"], "draft")
        self.assertEqual(by_id["p4"]["status"], "failed")
        self.assertEqual(by_id["p5"]["status"], "unknown")  # a missing status is NEVER 'published'

    def test_pagination_follows_until_short_page(self):
        calls = []

        def paged_transport(method, url, headers, req_body):
            sent = json.loads(req_body.decode("utf-8"))
            calls.append(sent["skip"])
            page_n = int(sent["skip"]) // 3
            if page_n < 2:  # two full pages then a short page
                posts = [{"_id": "p%d" % i, "status": "published"}
                         for i in range(page_n * 3, page_n * 3 + 3)]
            else:
                posts = [{"_id": "p-last", "status": "published"}]
            return 200, json.dumps({"results": {"posts": posts}}).encode("utf-8"), {}

        posts = ghl_contracts.fetch_posts("pit-test", "loc-abc", transport=paged_transport,
                                          page_limit=3)
        self.assertEqual(len(posts), 7)
        self.assertEqual(calls, ["0", "3", "6"])  # skip/offset traversal followed

    def test_accounts_filter_is_comma_string(self):
        calls = []
        t = _recording_transport(200, {"results": {"posts": []}}, calls)
        ghl_contracts.fetch_posts("pit-test", "loc-abc", accounts=["fb-1", "fb-2"], transport=t)
        sent = json.loads(calls[0]["body"].decode("utf-8"))
        self.assertEqual(sent["accounts"], "fb-1,fb-2")

    def test_error_taxonomy_and_contract_failures(self):
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_posts("pit-test", "loc-abc", transport=_fake_transport(401, {}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_AUTHENTICATION)
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_posts("pit-test", "loc-abc",
                                      transport=_fake_transport(429, {}, {"Retry-After": "3"}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_RATE_LIMITED)
        self.assertEqual(ctx.exception.retry_after, 3)
        # malformed 2xx: contract error, never zero posts
        with self.assertRaises(ghl_contracts.GhlApiError) as ctx:
            ghl_contracts.fetch_posts("pit-test", "loc-abc", transport=_fake_transport(200, {"nope": 1}))
        self.assertEqual(ctx.exception.error_class, ghl_contracts.E_CONTRACT)


if __name__ == "__main__":
    unittest.main()