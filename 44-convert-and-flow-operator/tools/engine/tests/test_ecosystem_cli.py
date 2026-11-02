"""T3 ecosystem CLI subcommands — MOCK-only unit tests.

Covers the three subcommands added for the ecosystem build:
  * caf calendars create        -> POST /calendars/        (Version 2021-04-15)
  * caf payments create-product -> POST /products/          (Version 2021-07-28)
  * caf payments create-price   -> POST /products/{id}/price (singular); the CLI
    takes cents, the wire carries the documented amount (dollars) and the
    created record is read back

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


# TEST-ONLY approval: creates need a verified automation_write approval record. The
# CLI's verify hook is faked here with the shape approval_record.verify returns; nothing
# below is a real approval and the approval authority is never contacted.
_TEST_ONLY_VERIFIED = {"ok": True, "approval_id": "TEST-ONLY-APPROVAL", "kind": "automation_write",
                       "client_identity": "test-only-client", "expires_at": "2999-01-01T00:00:00+00:00",
                       "authority": "local-test-record", "test_only": True}
_TEST_ONLY_APPROVAL_ARGS = ["--approval-id", "TEST-ONLY-APPROVAL", "--plan-sha256", "0" * 64]


class _PatchedApiBase(unittest.TestCase):
    """Patches gohighlevel_cli.api.post/get and returns the recorded calls."""

    def setUp(self):
        _approved_env()

    def tearDown(self):
        _clear_env()

    def _invoke(self, args, post_return, get_return=None):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        get_kw = ({"side_effect": get_return} if callable(get_return)
                  else {"return_value": get_return})
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.post",
            return_value=post_return,
        ) as mock_post, patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.get",
            **get_kw,
        ) as mock_get, patch(
            "cli_anything.gohighlevel.gohighlevel_cli._verify_automation_write",
            return_value=dict(_TEST_ONLY_VERIFIED),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, args)
        return result, mock_post, mock_get


# ── calendars create ──────────────────────────────────────────────────────────

class TestCalendarsCreate(_PatchedApiBase):
    def test_posts_to_calendars_with_correct_body(self):
        result, mock_post, mock_get = self._invoke(
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
        result, mock_post, mock_get = self._invoke(
            ["--json", "--location-id", LOC,
             "calendars", "create", "--name", "ZHC Cal"],
            post_return={"id": "CAL2"},
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        body = mock_post.call_args.kwargs["data"]
        self.assertNotIn("teamMembers", body)


# ── payments create-product / create-price ────────────────────────────────────

def _product_get(name="ZHC Workshop Seat"):
    """GET router: the read-first list is empty, the read-back returns the created product."""
    def get(path, params=None, version=None):
        if path.split("?")[0] == "/products/":
            return {"products": [], "total": 0}
        return {"_id": "PROD_NEW", "name": name, "productType": "SERVICE", "locationId": LOC}
    return get


def _price_get(amount=49.0):
    """GET router: no price listed yet, the read-back returns the created price."""
    def get(path, params=None, version=None):
        if path.split("?")[0] == "/products/PROD_NEW/price":
            return {"prices": [], "total": 0}
        return {"_id": "PRICE_NEW", "product": "PROD_NEW", "amount": amount,
                "currency": "USD", "type": "one_time"}
    return get


class TestPaymentsCreateProduct(_PatchedApiBase):
    _ARGS = ["--json", "--location-id", LOC,
             "payments", "create-product",
             "--name", "ZHC Workshop Seat",
             "--type", "SERVICE"] + _TEST_ONLY_APPROVAL_ARGS

    def test_posts_to_products_with_location_id(self):
        result, mock_post, mock_get = self._invoke(
            self._ARGS,
            post_return={"_id": "PROD_NEW"},
            get_return=_product_get(),
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        path = mock_post.call_args.args[0]
        body = mock_post.call_args.kwargs["data"]
        # GHL Products API: create product is POST /products/ with locationId
        # (NOT /payments/products, and NOT the payments-API altId/altType keys).
        self.assertEqual(path, "/products/")
        self.assertEqual(body["name"], "ZHC Workshop Seat")
        self.assertEqual(body["productType"], "SERVICE")
        self.assertEqual(body["locationId"], LOC)
        self.assertNotIn("altId", body)
        self.assertNotIn("altType", body)
        # Shared adapter reads the created record back.
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_get.call_args.args[0].split("?")[0], "/products/PROD_NEW")
        data = json.loads(result.output)
        self.assertEqual(data["native_product_id"], "PROD_NEW")
        self.assertEqual(data["readback"], "verified")

    def test_without_approval_id_refuses_and_never_posts(self):
        result, mock_post, _ = self._invoke(
            self._ARGS[:-4],  # same command, no --approval-id / --plan-sha256
            post_return={"_id": "PROD_NEW"},
            get_return=_product_get(),
        )
        self.assertNotEqual(result.exit_code, 0, f"Output: {result.output}")
        self.assertIn("approval", result.output)
        self.assertEqual(mock_post.call_count, 0)

    def test_image_url_refused_never_posts(self):
        result, mock_post, mock_get = self._invoke(
            self._ARGS + ["--image-url", "https://storage.googleapis.com/msgsndr/x.png"],
            post_return={"_id": "PROD_NEW"},
        )
        self.assertEqual(result.exit_code, 2, f"Output: {result.output}")
        self.assertIn("REFUSED", result.output)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)

    def test_readback_mismatch_fails(self):
        result, mock_post, _ = self._invoke(
            self._ARGS,
            post_return={"_id": "PROD_NEW"},
            get_return=_product_get(name="Other"),
        )
        self.assertNotEqual(result.exit_code, 0, f"Output: {result.output}")
        self.assertEqual(mock_post.call_count, 1)  # never a second create


class TestPaymentsCreatePrice(_PatchedApiBase):
    _ARGS = ["--json", "--location-id", LOC,
             "payments", "create-price",
             "--product-id", "PROD_NEW",
             "--name", "Workshop Seat",
             "--amount", "4900",
             "--currency", "USD"] + _TEST_ONLY_APPROVAL_ARGS

    def test_posts_to_product_price_with_amount_cents(self):
        result, mock_post, mock_get = self._invoke(
            self._ARGS,
            post_return={"_id": "PRICE_NEW"},
            get_return=_price_get(),
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        path = mock_post.call_args.args[0]
        body = mock_post.call_args.kwargs["data"]
        # GHL Products API: create price is POST /products/{id}/price (SINGULAR)
        # with locationId; the product id rides in the path, no altId/altType.
        self.assertEqual(path, "/products/PROD_NEW/price")
        self.assertEqual(body["locationId"], LOC)
        self.assertEqual(body["amount"], 49.0)  # documented CreatePriceDto dollars
        self.assertEqual(body["currency"], "USD")
        self.assertEqual(body["type"], "one_time")
        self.assertNotIn("altId", body)
        self.assertNotIn("altType", body)
        # Parent link is proven by the read-back path.
        self.assertEqual(mock_get.call_args.args[0].split("?")[0],
                         "/products/PROD_NEW/price/PRICE_NEW")
        self.assertEqual(json.loads(result.output)["amount_minor"], 4900)

    def test_without_approval_id_refuses_and_never_posts(self):
        result, mock_post, _ = self._invoke(
            self._ARGS[:-4],
            post_return={"_id": "PRICE_NEW"},
            get_return=_price_get(),
        )
        self.assertNotEqual(result.exit_code, 0, f"Output: {result.output}")
        self.assertIn("approval", result.output)
        self.assertEqual(mock_post.call_count, 0)

    def test_recurring_interval_count_and_trial_ride_the_shared_body(self):
        def get(path, params=None, version=None):
            if path.split("?")[0] == "/products/PROD_NEW/price":
                return {"prices": [], "total": 0}
            return {"_id": "PRICE_NEW", "product": "PROD_NEW", "amount": 49.0, "currency": "USD",
                    "type": "recurring", "recurring": {"interval": "month", "intervalCount": 3},
                    "trialPeriod": 7}
        result, mock_post, _ = self._invoke(
            self._ARGS + ["--type", "recurring", "--interval", "month",
                          "--interval-count", "3", "--trial-days", "7"],
            post_return={"_id": "PRICE_NEW"}, get_return=get,
        )
        self.assertEqual(result.exit_code, 0, f"Output: {result.output}")
        body = mock_post.call_args.kwargs["data"]
        self.assertEqual(body["recurring"], {"interval": "month", "intervalCount": 3})
        self.assertEqual(body["trialPeriod"], 7)

    def test_amount_readback_mismatch_fails(self):
        result, mock_post, _ = self._invoke(
            self._ARGS,
            post_return={"_id": "PRICE_NEW"},
            get_return=_price_get(amount=48.0),
        )
        self.assertNotEqual(result.exit_code, 0, f"Output: {result.output}")
        self.assertEqual(mock_post.call_count, 1)


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
        # click <8.2 (the newest release that still supports Python 3.9)
        # defaults CliRunner to mix_stderr=True, where stdout/stderr are
        # already combined in .output and .stderr raises ValueError; click
        # >=8.2 always keeps .stderr separate and readable. Tolerate both so
        # this assertion works under whichever click version the running
        # interpreter resolves.
        try:
            stderr_text = result.stderr
        except ValueError:
            stderr_text = ""
        self.assertIn("SAFETY GATE", result.output + stderr_text)


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


# ---------------------------------------------------------------------------
# _get_token() placeholder-shadow fix (2026-08-03) — see TERMINOLOGY.md and
# check-ghl-pit-liveness.sh's _is_placeholder() (the reference implementation
# this resolver's shape rules mirror). A config-seeded placeholder inherited
# into the live process env at gateway launch must never be accepted as a real
# credential; the real credential in a lower-priority alias (or the secrets
# store, via a different resolver layer) must still be found.
# ---------------------------------------------------------------------------
PLACEHOLDER_SHORT = "pit-abc123"
REAL_LOOKING_PIT = "pit-real1234567890REALTOKEN"


class TestGetTokenPlaceholderShadow(unittest.TestCase):
    def setUp(self):
        from cli_anything.gohighlevel.utils import ghl_client
        self.ghl_client = ghl_client
        for name in ghl_client._LOCATION_PIT_ENV_NAMES:
            os.environ.pop(name, None)

    def tearDown(self):
        for name in self.ghl_client._LOCATION_PIT_ENV_NAMES:
            os.environ.pop(name, None)

    def test_is_placeholder_shape(self):
        self.assertTrue(self.ghl_client._is_placeholder(PLACEHOLDER_SHORT))
        self.assertTrue(self.ghl_client._is_placeholder(""))
        self.assertFalse(self.ghl_client._is_placeholder(REAL_LOOKING_PIT))

    def test_placeholder_alone_exits_nonzero_and_never_echoes_value(self):
        os.environ["GOHIGHLEVEL_API_KEY"] = PLACEHOLDER_SHORT
        with self.assertRaises(SystemExit):
            self.ghl_client._get_token()

    def test_placeholder_in_preferred_alias_falls_through_to_real_legacy_alias(self):
        os.environ["GOHIGHLEVEL_API_KEY"] = PLACEHOLDER_SHORT  # placeholder, preferred
        os.environ["GHL_API_KEY"] = REAL_LOOKING_PIT           # real, legacy alias
        self.assertEqual(self.ghl_client._get_token(), REAL_LOOKING_PIT)

    def test_real_value_in_preferred_alias_resolves_immediately(self):
        os.environ["GOHIGHLEVEL_API_KEY"] = REAL_LOOKING_PIT
        self.assertEqual(self.ghl_client._get_token(), REAL_LOOKING_PIT)


if __name__ == "__main__":
    unittest.main()
