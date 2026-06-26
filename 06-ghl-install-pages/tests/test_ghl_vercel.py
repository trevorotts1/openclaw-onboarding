"""MOCK-only unit tests — ghl_vercel (Vercel build/host/embeddability path).

These tests are MOCK-ONLY. There is NO live Vercel deploy, NO GoHighLevel,
NO network of any kind.  ``assert_embeddable`` (the hard gate) is exercised
through a mocked ``curl -D-`` fixture (a fake HTTP response with headers
and body), so the tests run completely offline.

Coverage (all via mocked curl -D- fixture):
  * assert_embeddable FAILS on HTTP 401 / SSO-protected response.
  * assert_embeddable FAILS on X-Frame-Options: DENY.
  * assert_embeddable FAILS on X-Frame-Options: SAMEORIGIN.
  * assert_embeddable FAILS on restrictive frame-ancestors CSP
    (e.g. "frame-ancestors 'none'" or "frame-ancestors 'self'").
  * assert_embeddable PASSES on HTTP 200 + no X-Frame-Options +
    frame-ancestors that include the GoHighLevel wildcard + marker in body.
  * assert_embeddable FAILS when the page marker is absent.

All via mocked curl-response; no live deploy is needed or initiated.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_vercel.py -v
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_vercel as gv


# ── Import ghl_vercel (may not exist yet — B3 pending) ───────────────────────

def _import_vercel():
    """Return ghl_vercel module; never None since the module exists."""
    return gv


# ── Helpers — build fake curl -D- style responses (headers + body) ────────────
#
# curl -D- prints the HTTP response headers to stdout followed by the body.
# The format is:
#   HTTP/2 200
#   header-name: value
#   ...
#   <blank line>
#   <body>
#
# assert_embeddable accepts an injected `fetcher` callable that returns a dict:
#   {status: int, headers: dict[str,str], body: str}
# (This is the seam the production code uses; the tests inject a fake fetcher.)

FAKE_URL = "https://skill6-fixture-abc123.vercel.app"
FAKE_MARKER = "SKILL6-VERCEL-MARKER-TEST"
GHL_WILDCARD = "*.leadconnectorhq.com"


def _good_headers() -> dict:
    """Headers for a fully embeddable Vercel page (no XFO, open frame-ancestors)."""
    return {
        "content-type": "text/html; charset=utf-8",
        "content-security-policy": (
            f"frame-ancestors https://{GHL_WILDCARD} "
            "https://*.msgsndr.com https://*.gohighlevel.com"
        ),
        # Explicitly NO x-frame-options header.
    }


def _sso_headers() -> dict:
    """Headers when Vercel SSO/Deployment Protection is still active."""
    return {
        "x-frame-options": "DENY",
        "content-type": "text/html; charset=utf-8",
        # Vercel SSO also sets frame-ancestors: 'none' in the CSP.
        "content-security-policy": "frame-ancestors 'none'",
    }


def _fake_fetcher(status: int, headers: dict, body: str):
    """Return an assert_embeddable-compatible injected fetcher.

    The production fetcher is called as fetcher(url) -> {status, headers, body}
    (only url; the marker check is done inside assert_embeddable on the body).
    """
    def _f(url: str) -> dict:
        return {"status": status, "headers": dict(headers), "body": body}
    return _f


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAssertEmbeddableFailModes:
    """assert_embeddable must FAIL LOUD on every embeddability blocker."""

    def _get_assert_embeddable(self):
        m = _import_vercel()
        if m is None:
            pytest.skip("ghl_vercel not yet implemented (B3 pending)")
        if not hasattr(m, "assert_embeddable"):
            pytest.skip("ghl_vercel.assert_embeddable not yet implemented (B3 pending)")
        return m.assert_embeddable

    # ── HTTP 401 (SSO active) ─────────────────────────────────────────────────

    def test_fails_on_http_401(self):
        """HTTP 401 means Vercel's SSO/Deployment Protection is still active.
        Embedding an SSO-protected page produces a blank iframe (the browser
        follows the 401 → login redirect, which the iframe can't do)."""
        ae = self._get_assert_embeddable()
        fetcher = _fake_fetcher(
            status=401,
            headers=_sso_headers(),
            body="<html><body>Please log in</body></html>",
        )
        with pytest.raises(Exception) as exc_info:
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        assert "401" in str(exc_info.value) or "sso" in str(exc_info.value).lower() or \
               "auth" in str(exc_info.value).lower(), \
            f"exception must mention 401/SSO/auth; got: {exc_info.value}"

    def test_fails_on_http_403(self):
        """HTTP 403 (another SSO variant) must also fail."""
        ae = self._get_assert_embeddable()
        fetcher = _fake_fetcher(
            status=403,
            headers={"content-type": "text/html"},
            body="<html><body>Forbidden</body></html>",
        )
        with pytest.raises(Exception):
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)

    # ── X-Frame-Options ───────────────────────────────────────────────────────

    def test_fails_on_xfo_deny(self):
        """X-Frame-Options: DENY prevents the page from being embedded in any
        frame — the Vercel deploy is not embeddable."""
        ae = self._get_assert_embeddable()
        headers = dict(_good_headers())
        headers["x-frame-options"] = "DENY"
        fetcher = _fake_fetcher(
            status=200,
            headers=headers,
            body=f"<html><body><p>{FAKE_MARKER}</p></body></html>",
        )
        with pytest.raises(Exception) as exc_info:
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        err = str(exc_info.value).lower()
        assert "deny" in err or "x-frame-options" in err or "frame" in err, \
            f"exception must mention XFO/DENY; got: {exc_info.value}"

    def test_fails_on_xfo_sameorigin(self):
        """X-Frame-Options: SAMEORIGIN prevents cross-origin embedding, which
        is required because GoHighLevel is a different origin from Vercel."""
        ae = self._get_assert_embeddable()
        headers = dict(_good_headers())
        headers["x-frame-options"] = "SAMEORIGIN"
        fetcher = _fake_fetcher(
            status=200,
            headers=headers,
            body=f"<html><body><p>{FAKE_MARKER}</p></body></html>",
        )
        with pytest.raises(Exception) as exc_info:
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        err = str(exc_info.value).lower()
        assert "sameorigin" in err or "x-frame-options" in err or "frame" in err, \
            f"exception must mention SAMEORIGIN; got: {exc_info.value}"

    # ── Restrictive CSP frame-ancestors ──────────────────────────────────────

    def test_fails_on_frame_ancestors_none(self):
        """frame-ancestors: 'none' is the Vercel SSO default — no iframe anywhere."""
        ae = self._get_assert_embeddable()
        headers = {
            "content-type": "text/html",
            "content-security-policy": "frame-ancestors 'none'",
        }
        fetcher = _fake_fetcher(
            status=200,
            headers=headers,
            body=f"<html><body><p>{FAKE_MARKER}</p></body></html>",
        )
        with pytest.raises(Exception) as exc_info:
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        err = str(exc_info.value).lower()
        assert "frame-ancestors" in err or "csp" in err or "frame" in err, \
            f"exception must mention frame-ancestors/CSP; got: {exc_info.value}"

    def test_fails_on_frame_ancestors_self_only(self):
        """frame-ancestors: 'self' restricts embedding to same origin — blocks GHL."""
        ae = self._get_assert_embeddable()
        headers = {
            "content-type": "text/html",
            "content-security-policy": "frame-ancestors 'self'",
        }
        fetcher = _fake_fetcher(
            status=200,
            headers=headers,
            body=f"<html><body><p>{FAKE_MARKER}</p></body></html>",
        )
        with pytest.raises(Exception) as exc_info:
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        err = str(exc_info.value).lower()
        assert "frame-ancestors" in err or "csp" in err or "frame" in err or \
               "self" in err, \
            f"exception must mention frame-ancestors/'self'/CSP; got: {exc_info.value}"

    # ── Marker absent ─────────────────────────────────────────────────────────

    def test_fails_when_marker_absent(self):
        """HTTP 200 with correct headers but marker not in body must fail.
        A missing marker means the page didn't actually render our content."""
        ae = self._get_assert_embeddable()
        fetcher = _fake_fetcher(
            status=200,
            headers=_good_headers(),
            body="<html><body><p>no marker here at all</p></body></html>",
        )
        with pytest.raises(Exception) as exc_info:
            ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        err = str(exc_info.value).lower()
        assert "marker" in err or "not found" in err or "missing" in err, \
            f"exception must mention marker; got: {exc_info.value}"


class TestAssertEmbeddablePassPath:
    """assert_embeddable must PASS when all conditions are satisfied."""

    def _get_assert_embeddable(self):
        m = _import_vercel()
        if m is None:
            pytest.skip("ghl_vercel not yet implemented (B3 pending)")
        if not hasattr(m, "assert_embeddable"):
            pytest.skip("ghl_vercel.assert_embeddable not yet implemented (B3 pending)")
        return m.assert_embeddable

    def test_passes_on_200_no_xfo_open_frame_ancestors_marker_present(self):
        """The only path to a PASS: HTTP 200, no X-Frame-Options header, a
        frame-ancestors CSP that includes the GoHighLevel wildcard, and the
        marker appears in the body.

        This mirrors the LIVE-CONFIRMED setup from ghl-browser-builder-full.md
        PART C (operator fixture, 2026-06-21)."""
        ae = self._get_assert_embeddable()
        fetcher = _fake_fetcher(
            status=200,
            headers=_good_headers(),
            body=f"<html><body><p>{FAKE_MARKER}</p><p>Page content here.</p></body></html>",
        )
        # Must NOT raise.
        result = ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)
        # If it returns a value, it should be truthy / indicate success.
        if result is not None:
            assert result, f"assert_embeddable must return a truthy result on pass; got {result!r}"

    def test_passes_without_csp_header_when_no_xfo(self):
        """A page with no CSP header at all and no X-Frame-Options must also pass —
        the embeddability gate's minimum is 'not blocked', not 'explicitly permitted'."""
        ae = self._get_assert_embeddable()
        fetcher = _fake_fetcher(
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=f"<html><body><p>{FAKE_MARKER}</p></body></html>",
        )
        # No XFO, no CSP, marker present, HTTP 200 — must pass.
        ae(FAKE_URL, FAKE_MARKER, fetcher=fetcher)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
