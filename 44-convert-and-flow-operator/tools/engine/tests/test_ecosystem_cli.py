"""T3 ecosystem CLI subcommands — MOCK-only unit tests.

Covers the three subcommands added for the ecosystem build:
  * caf calendars create        -> POST /calendars/        (Version 2021-04-15)
  * caf payments create-product -> POST /payments/products (Version 2021-07-28)
  * caf payments create-price   -> POST /payments/products/{id}/prices

Every test uses mocks/fixtures — NO live CRM is contacted. Two layers are
exercised:
  1. command -> api.post: the right PATH + BODY are sent (api.post patched).
  2. command -> safety gate: a non-whitelisted / unapproved write is REFUSED
     (requests patched at the lowest layer; the gate must fire first).

A module-level network guard hard-fails on any real connect to
leadconnectorhq.com.

Run:
    python3 -m pytest tests/test_ecosystem_cli.py -v
"""
from __future__ import annotations

import json
import os
import socket
import sys
import unittest
from unittest.mock import patch, MagicMock

# ── Ensure engine root is on sys.path ─────────────────────────────────────────
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ── Network guard — any connect to leadconnectorhq.com is a hard FAIL ─────────
_BLOCKED_HOST = "leadconnectorhq.com"
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = address[0]
        if _BLOCKED_HOST in str(host):
            raise AssertionError(
                f"SAFETY FAILURE: live CRM host contacted: {host!r}. "
                "All tests must use mocks — no live API calls."
            )
    return _original_connect(self, address)


socket.socket.connect = _guarded_connect


# ── Fixtures ──────────────────────────────────────────────────────────────────

LOC = "TESTLOCATION00000001"  # fake fixture location id (mock-only; the only allowed one)


def _approved_env():
    """Env that passes the safety gate for the fixture location."""
    os.environ["GHL_API_KEY"] = "fake-pit-token"
    os.environ["GHL_LOCATION_ID"] = LOC
    os.environ["CAF_ALLOWED_LOCATION_IDS"] = LOC
    os.environ["CAF_APPROVAL_TOKEN"] = "test-approval"
    os.environ.pop("CAF_DRY_RUN", None)


def _clear_env():
    for k in ("GHL_API_KEY", "GHL_LOCATION_ID", "CAF_ALLOWED_LOCATION_IDS",
              "CAF_APPROVAL_TOKEN", "CAF_DRY_RUN", "CAF_DRAFT_ONLY"):
        os.environ.pop(k, None)


class _PatchedApiBase(unittest.TestCase):
    """Patches gohighlevel_cli.api.post and returns the recorded call."""

    def setUp(self):
        _approved_env()

    def tearDown(self):
        _clear_env()

    def _invoke(self, args, post_return):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.post",
            return_value=post_return,
        ) as mock_post:
            runner = CliRunner()
            result = runner.invoke(cli, args)
        return result, mock_post


# ── calendars create ──────────────────────────────────────────────────────────

class TestCalendarsCreate(_PatchedApiBase):
    def test_posts_to_calendars_with_correct_body(self):
        result, mock_post = self._invoke(
            ["--json", "--location-id", LOC,
             "calendars", "create",
             "--name", "ZHC Scent-Bar Workshop",
             "--slot-duration", "45",
             "--team-member", "USER123"],
            post_return={"id": "CAL_NEW", "name": "ZHC Scent-Bar Workshop"},
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        self.assertEqual(mock_post.call_count, 1)
        path = mock_post.call_args.args[0]
        body = mock_post.call_args.kwargs["data"]
        self.assertEqual(path, "/calendars/")
        self.assertEqual(body["locationId"], LOC)
        self.assertEqual(body["name"], "ZHC Scent-Bar Workshop")
        self.assertEqual(body["slotDuration"], 45)
        self.assertEqual(body["teamMembers"], [{"userId": "USER123"}])
        data = json.loads(result.output)
        self.assertEqual(data["id"], "CAL_NEW")

    def test_omits_team_members_when_none_given(self):
        result, mock_post = self._invoke(
            ["--json", "--location-id", LOC,
             "calendars", "create", "--name", "ZHC Cal"],
            post_return={"id": "CAL2"},
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        body = mock_post.call_args.kwargs["data"]
        self.assertNotIn("teamMembers", body)


# ── payments create-product / create-price ────────────────────────────────────

class TestPaymentsCreateProduct(_PatchedApiBase):
    def test_posts_to_products_with_alt_keys(self):
        result, mock_post = self._invoke(
            ["--json", "--location-id", LOC,
             "payments", "create-product",
             "--name", "ZHC Workshop Seat",
             "--type", "SERVICE",
             "--image-url", "https://storage.googleapis.com/msgsndr/x.png"],
            post_return={"product": {"_id": "PROD_NEW"}},
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        path = mock_post.call_args.args[0]
        body = mock_post.call_args.kwargs["data"]
        self.assertEqual(path, "/payments/products")
        self.assertEqual(body["name"], "ZHC Workshop Seat")
        self.assertEqual(body["productType"], "SERVICE")
        self.assertEqual(body["altId"], LOC)
        self.assertEqual(body["altType"], "location")
        self.assertEqual(body["image"], "https://storage.googleapis.com/msgsndr/x.png")


class TestPaymentsCreatePrice(_PatchedApiBase):
    def test_posts_to_product_prices_with_amount_cents(self):
        result, mock_post = self._invoke(
            ["--json", "--location-id", LOC,
             "payments", "create-price",
             "--product-id", "PROD_NEW",
             "--name", "Workshop Seat",
             "--amount", "4900",
             "--currency", "USD"],
            post_return={"_id": "PRICE_NEW", "amount": 4900},
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        path = mock_post.call_args.args[0]
        body = mock_post.call_args.kwargs["data"]
        self.assertEqual(path, "/payments/products/PROD_NEW/prices")
        self.assertEqual(body["amount"], 4900)
        self.assertEqual(body["currency"], "USD")
        self.assertEqual(body["type"], "one_time")


# ── Safety gate fires (lowest-layer requests patched; gate must refuse first) ─

class TestSafetyGateRefusesForeignLocation(unittest.TestCase):
    """A create targeting a location NOT in the whitelist must be REFUSED before
    any HTTP call — even though api.post is the real (unpatched) function. We
    patch requests.post so that IF the gate ever let it through, the test would
    still not hit the network; the assertion is that exit!=0 and requests.post
    was NEVER called."""

    def setUp(self):
        os.environ["GHL_API_KEY"] = "fake-pit-token"
        os.environ["GHL_LOCATION_ID"] = "FOREIGNLOCATION00000"
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = LOC  # whitelist != target
        os.environ["CAF_APPROVAL_TOKEN"] = "test-approval"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        _clear_env()

    def test_foreign_location_create_refused(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        with patch("cli_anything.gohighlevel.utils.ghl_client.requests.post") as mock_req:
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--location-id", "FOREIGNLOCATION00000",
                "calendars", "create", "--name", "ZHC Cal",
            ])
        self.assertNotEqual(result.exit_code, 0,
                            "Foreign-location write must be refused (non-zero exit)")
        mock_req.assert_not_called()
        self.assertIn("SAFETY GATE", result.output + (result.stderr or ""))


class TestSafetyGateRefusesUnapproved(unittest.TestCase):
    """Without CAF_APPROVAL_TOKEN and without a ZHC-prefixed name, the write is
    refused by Rule 3 of the gate."""

    def setUp(self):
        os.environ["GHL_API_KEY"] = "fake-pit-token"
        os.environ["GHL_LOCATION_ID"] = LOC
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = LOC
        os.environ.pop("CAF_APPROVAL_TOKEN", None)  # no explicit approval
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        _clear_env()

    def test_unapproved_create_refused(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        with patch("cli_anything.gohighlevel.utils.ghl_client.requests.post") as mock_req:
            runner = CliRunner()
            # plain (non-ZHC) product name => not standing-approved
            result = runner.invoke(cli, [
                "--location-id", LOC,
                "payments", "create-product", "--name", "Plain Product",
            ])
        self.assertNotEqual(result.exit_code, 0)
        mock_req.assert_not_called()


if __name__ == "__main__":
    unittest.main()
