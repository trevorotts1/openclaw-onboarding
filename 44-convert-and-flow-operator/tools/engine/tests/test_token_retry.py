"""Transport token-refresh retry-once tests (Skill 44 engine).

Proves the RETRY-ONCE on the transient Firebase token-refresh error added in
skill-version 1.0.4:

  - Transient token-refresh failure (securetoken exchange returns None ONCE)
    -> the exchange is retried EXACTLY ONCE -> success, no error surfaced.
  - Persistent token-refresh failure (exchange returns None every time)
    -> TOKEN_REFRESH_FAILED is surfaced AFTER exactly one retry (two attempts,
       never a loop).
  - A successful exchange is NEVER retried (single attempt on the happy path).
  - The retry covers ONLY the None (exchange-failed) case — a downstream HTTP
    error dict ({"_error": True, "http_code": 400, ...}, e.g. the corrupted-order
    rejection guarded by PR #163) is returned UNCHANGED and never triggers a
    token-refresh exchange, so the build-path fail-loud behaviour is preserved.

All tests use mocks — NO live host (leadconnectorhq.com / securetoken.googleapis.com)
is ever contacted.

Run:
    python3 -m pytest tests/test_token_retry.py -v
"""
from __future__ import annotations

import os
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

# ── Ensure engine root is on sys.path ─────────────────────────────────────────
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ── Network guard — any live connect to the CRM / Firebase is a HARD FAIL ─────
_BLOCKED_HOST = "leadconnectorhq.com"
_BLOCKED_FIREBASE = "securetoken.googleapis.com"
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = str(address[0])
        if _BLOCKED_HOST in host or _BLOCKED_FIREBASE in host:
            raise AssertionError(
                f"TOKEN RETRY CI SAFETY FAILURE: live host contacted: {host!r}. "
                "All transport tests must use mocks."
            )
    return _original_connect(self, address)


socket.socket.connect = _guarded_connect


from cli_anything.gohighlevel.internal.transport import InternalTransport
from cli_anything.gohighlevel.internal.adapter_types import AdapterError


_REFRESH_ENV = {"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "refresh-tok-abc"}


class TestTokenRefreshRetryOnce(unittest.TestCase):
    """get_token() retry-once semantics on the transient refresh failure."""

    def test_transient_failure_retries_once_then_succeeds(self):
        """First exchange returns None (transient), second returns a token ->
        get_token() returns the token with NO error surfaced, two attempts."""
        t = InternalTransport()
        # None on the first call (transient), a real token on the second.
        with patch.dict(os.environ, _REFRESH_ENV, clear=False), \
                patch.object(
                    t, "_refresh_firebase",
                    side_effect=[None, "fresh-id-token"],
                ) as mock_refresh:
            token = t.get_token()

        self.assertEqual(token, "fresh-id-token")
        # EXACTLY two attempts: the original + ONE retry (not a loop).
        self.assertEqual(mock_refresh.call_count, 2)

    def test_persistent_failure_surfaces_after_one_retry(self):
        """Exchange returns None every time -> TOKEN_REFRESH_FAILED raised AFTER
        exactly one retry (two attempts total — never more)."""
        t = InternalTransport()
        with patch.dict(os.environ, _REFRESH_ENV, clear=False), \
                patch.object(
                    t, "_refresh_firebase",
                    side_effect=[None, None, "should-never-reach"],
                ) as mock_refresh:
            with self.assertRaises(AdapterError) as ctx:
                t.get_token()

        self.assertEqual(ctx.exception.code, "TOKEN_REFRESH_FAILED")
        self.assertIn("may be revoked", ctx.exception.message)
        # Exactly two attempts: original + ONE retry. The third side_effect
        # ("should-never-reach") proves we did NOT loop.
        self.assertEqual(mock_refresh.call_count, 2)

    def test_happy_path_does_not_retry(self):
        """A successful exchange is taken on the FIRST attempt — never retried."""
        t = InternalTransport()
        with patch.dict(os.environ, _REFRESH_ENV, clear=False), \
                patch.object(
                    t, "_refresh_firebase",
                    side_effect=["good-token", "must-not-be-used"],
                ) as mock_refresh:
            token = t.get_token()

        self.assertEqual(token, "good-token")
        self.assertEqual(mock_refresh.call_count, 1)

    def test_http_error_dict_is_not_a_token_retry_trigger(self):
        """PRESERVE PR #163 fail-loud: a downstream HTTP error dict (e.g. the
        400 'corrupted order' save rejection) is returned UNCHANGED by
        request() and NEVER triggers a token-refresh exchange.

        Only a None from _do_request (401/403 auth signal) drives force_refresh;
        an _error dict is surfaced verbatim so workflow_builder can fail loud.
        """
        t = InternalTransport()
        corrupted = {"_error": True, "http_code": 400, "code": 400,
                     "message": "corrupted order"}
        with patch.dict(os.environ, _REFRESH_ENV, clear=False), \
                patch.object(t, "_refresh_firebase",
                             return_value="good-token") as mock_refresh, \
                patch.object(t, "_do_request",
                             return_value=corrupted) as mock_do:
            result = t.request("PUT", "/workflow/LOC/WF1", {"x": 1})

        # The 400 is surfaced unchanged — fail-loud preserved.
        self.assertEqual(result, corrupted)
        # Exactly one HTTP attempt (no auth-retry on an _error dict).
        self.assertEqual(mock_do.call_count, 1)
        # Token fetched once (happy path); the corrupted-order dict did NOT
        # provoke a second refresh exchange.
        self.assertEqual(mock_refresh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
