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


# ── run_pipeline — NON-BLOCKING GitHub archival wiring ───────────────────────
#
# Operator standing rule: a VERCEL_EMBED page's source must ALWAYS also land
# in GitHub. These tests prove the archival hook is (a) wired into
# run_pipeline AFTER the Vercel deploy succeeds, (b) fully optional/backward
# compatible when evidence_root is omitted, and (c) NEVER able to turn the
# Vercel pipeline's own success into a raised error, no matter what the
# archival step does. All mock-only — no live Vercel, no live GitHub, no real
# subprocess spawn (ghl_github_archive.archive_async's own popen seam is
# exercised in tests/test_ghl_github_archive.py; here we only assert
# run_pipeline calls it and handles its result/errors correctly).

import ghl_receipts  # noqa: E402
import ghl_github_archive  # noqa: E402


def _vercel_requester():
    """Fake requester for deploy()/make_public() — mirrors the real Vercel
    deployments API shape closely enough for run_pipeline to complete."""
    def _req(method, url, body, *, token=""):
        if method == "POST" and url.endswith("/deployments"):
            return {"id": "dpl_test123", "url": "test-deploy.vercel.app"}
        if method == "GET" and "/deployments/" in url:
            return {"readyState": "READY", "url": "test-deploy.vercel.app"}
        if method == "PATCH":
            return {"ok": True}
        raise AssertionError(f"unexpected vercel call {method} {url}")
    return _req


def _embeddable_fetcher(marker: str):
    def _f(url: str) -> dict:
        return {
            "status": 200,
            "headers": {"content-security-policy": "frame-ancestors https://*.leadconnectorhq.com"},
            "body": f"<html>{marker}</html>",
        }
    return _f


class TestRunPipelineGithubArchival:
    def test_no_evidence_root_skips_archival_backward_compatible(self, tmp_path, monkeypatch):
        called = {"n": 0}

        def fake_archive_async(*a, **kw):
            called["n"] += 1
            return {"status": "spawned"}

        monkeypatch.setattr(ghl_github_archive, "archive_async", fake_archive_async)

        marker = "PIPE-NOROOT"
        receipt = gv.run_pipeline(
            "<p>hi</p>", marker, str(tmp_path / "proj"),
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_embeddable_fetcher(marker),
        )
        assert receipt.github_archive == {}
        assert called["n"] == 0, "archive_async must not be called when evidence_root is omitted"

    def test_evidence_root_triggers_deploy_receipt_and_archive_call(self, tmp_path, monkeypatch):
        captured = {}

        def fake_archive_async(project, deployment, marker, evidence_root, **kw):
            captured["marker"] = marker
            captured["evidence_root"] = evidence_root
            captured["project_name"] = kw.get("project_name")
            return {"status": "spawned", "task_path": "x"}

        monkeypatch.setattr(ghl_github_archive, "archive_async", fake_archive_async)

        marker = "PIPE-WITHROOT"
        evidence_root = str(tmp_path / "evidence")
        receipt = gv.run_pipeline(
            "<p>hi</p>", marker, str(tmp_path / "proj"),
            project_name="zhc-test-page",
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_embeddable_fetcher(marker),
            evidence_root=evidence_root,
        )

        assert receipt.github_archive["status"] == "spawned"
        assert captured["marker"] == marker
        assert captured["evidence_root"] == evidence_root
        assert captured["project_name"] == "zhc-test-page"

        # A vercel_deploy F6 receipt must exist so reconciliation can find this page.
        summ = ghl_receipts.reduce_receipts(evidence_root)
        assert f"vercel_deploy:{marker}" in summ["created"]
        assert f"vercel_deploy:{marker}" in summ["verified"]

    def test_archive_async_exception_never_propagates_out_of_run_pipeline(self, tmp_path, monkeypatch):
        def exploding_archive_async(*a, **kw):
            raise RuntimeError("simulated archive_async crash")

        monkeypatch.setattr(ghl_github_archive, "archive_async", exploding_archive_async)

        marker = "PIPE-ARCHIVEBOOM"
        evidence_root = str(tmp_path / "evidence")
        # Must NOT raise — the Vercel deploy already succeeded by this point.
        receipt = gv.run_pipeline(
            "<p>hi</p>", marker, str(tmp_path / "proj"),
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_embeddable_fetcher(marker),
            evidence_root=evidence_root,
        )
        assert receipt.github_archive["status"] == "failed"
        assert "simulated archive_async crash" in receipt.github_archive["reason"]
        # The deploy itself still fully succeeded despite the archival crash.
        assert receipt.embeddability.embeddable is True

    def test_vercel_failure_raises_before_any_archive_attempt(self, tmp_path, monkeypatch):
        called = {"n": 0}

        def fake_archive_async(*a, **kw):
            called["n"] += 1
            return {"status": "spawned"}

        monkeypatch.setattr(ghl_github_archive, "archive_async", fake_archive_async)

        def failing_fetcher(url: str) -> dict:
            # No marker in body -> assert_embeddable fails -> VercelEmbedError.
            return {"status": 200, "headers": {}, "body": "<html>no marker here</html>"}

        with pytest.raises(gv.VercelEmbedError):
            gv.run_pipeline(
                "<p>hi</p>", "PIPE-VERCELFAIL", str(tmp_path / "proj"),
                env={"VERCEL_TOKEN": "fake"},
                requester=_vercel_requester(),
                fetcher=failing_fetcher,
                evidence_root=str(tmp_path / "evidence"),
            )
        assert called["n"] == 0, "archival must never be attempted when the Vercel gate itself fails"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
