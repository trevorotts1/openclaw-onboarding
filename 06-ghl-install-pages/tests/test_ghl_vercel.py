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


_API = "https://api.vercel.com"
_PROJECT_ID = "prj_test123"


class _FakeVercel:
    """Fake Vercel REST API, routed by exact (method, URL) like the real one.

    Only the routes Vercel really publishes answer: POST /v13/deployments,
    GET /v13/deployments/<id>, PATCH + GET /v9/projects/<projectId>,
    DELETE /v13/deployments/<id>. Any other call (including the old,
    non-existent PATCH /v13/deployments/<id>) raises VercelEmbedError the way
    _http_request does on Vercel's HTTP 404. Every call is recorded.
    """

    def __init__(self, project_name="zhc-ghl-page", team_id=None,
                 protection_after_patch=None, project_patch_404=False):
        self.calls = []
        self.project_name = project_name
        self.q = f"?teamId={team_id}" if team_id else ""
        self.protection_after_patch = protection_after_patch
        self.project_patch_404 = project_patch_404
        self.project = {"id": _PROJECT_ID, "name": project_name,
                        "ssoProtection": {"deploymentType": "all_except_custom_domains"},
                        "passwordProtection": None}

    def __call__(self, method, url, body, *, token=""):
        self.calls.append((method, url, body))
        dep = f"{_API}/v13/deployments/dpl_test123{self.q}"
        proj = f"{_API}/v9/projects/{_PROJECT_ID}{self.q}"
        if (method, url) == ("POST", f"{_API}/v13/deployments{self.q}"):
            return {"id": "dpl_test123", "url": "test-deploy.vercel.app",
                    "projectId": _PROJECT_ID, "name": self.project_name}
        if (method, url) == ("GET", dep):
            return {"id": "dpl_test123", "readyState": "READY", "url": "test-deploy.vercel.app",
                    "projectId": _PROJECT_ID, "name": self.project_name}
        if (method, url) == ("PATCH", proj) and not self.project_patch_404:
            self.project.update(body)
            if self.protection_after_patch:
                self.project.update(self.protection_after_patch)
            return dict(self.project)
        if (method, url) == ("GET", proj):
            return dict(self.project)
        if (method, url) == ("DELETE", dep):
            return {"state": "DELETED", "uid": "dpl_test123"}
        raise gv.VercelEmbedError(f"HTTP 404 from {url}: not_found")

    def only(self, method):
        return [(u, b) for m, u, b in self.calls if m == method]


def _vercel_requester(**kw):
    """Fake requester for deploy()/make_public() (see _FakeVercel)."""
    return _FakeVercel(**kw)


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


# ── make_public: project-scoped PATCH with readback (FRF-003) ────────────────


class TestMakePublic:
    def test_patches_project_not_deployment_and_reads_back(self):
        fake = _FakeVercel()
        assert gv.make_public("dpl_test123", "fake", requester=fake) is True
        assert fake.only("PATCH") == [
            (f"{_API}/v9/projects/{_PROJECT_ID}",
             {"ssoProtection": None, "passwordProtection": None})]
        gets = [u for u, _ in fake.only("GET")]
        assert gets == [f"{_API}/v13/deployments/dpl_test123",
                        f"{_API}/v9/projects/{_PROJECT_ID}"]
        assert not any("/v13/deployments/" in u for u, _ in fake.only("PATCH"))

    def test_team_id_on_every_call(self):
        fake = _FakeVercel(team_id="team_x")
        gv.make_public("dpl_test123", "fake", team_id="team_x", requester=fake)
        assert len(fake.calls) == 3
        assert all(u.endswith("?teamId=team_x") for _, u, _ in fake.calls)

    def test_missing_project_id_raises_before_any_patch(self):
        calls = []

        def req(method, url, body, *, token=""):
            calls.append(method)
            return {"id": "dpl_test123", "name": "zhc-ghl-page"}  # no projectId

        with pytest.raises(gv.VercelEmbedError, match="no projectId"):
            gv.make_public("dpl_test123", "fake", requester=req)
        assert calls == ["GET"]

    def test_refuses_non_zhc_project(self):
        fake = _FakeVercel(project_name="client-real-site")
        with pytest.raises(gv.VercelEmbedError, match="refusing project"):
            gv.make_public("dpl_test123", "fake", requester=fake)
        assert fake.only("PATCH") == []

    def test_readback_still_protected_raises(self):
        fake = _FakeVercel(protection_after_patch={"ssoProtection": {"deploymentType": "preview"}})
        with pytest.raises(gv.VercelEmbedError, match="still protected"):
            gv.make_public("dpl_test123", "fake", requester=fake)

    def test_project_patch_404_propagates(self):
        fake = _FakeVercel(project_patch_404=True)
        with pytest.raises(gv.VercelEmbedError, match="HTTP 404"):
            gv.make_public("dpl_test123", "fake", requester=fake)


class TestRunPipelineProjectGuard:
    def test_non_zhc_project_name_refused_before_any_network(self, tmp_path):
        def must_not_call(*a, **kw):
            raise AssertionError("network must not be touched")

        with pytest.raises(gv.VercelEmbedError, match="must start with"):
            gv.run_pipeline("<p>hi</p>", "M-GUARD", str(tmp_path / "proj"),
                            project_name="client-real-site",
                            env={"VERCEL_TOKEN": "fake"},
                            requester=must_not_call,
                            fetcher=_embeddable_fetcher("M-GUARD"))

    def test_protection_disabled_reflects_proven_readback(self, tmp_path):
        r = gv.run_pipeline("<p>hi</p>", "M-OK", str(tmp_path / "proj"),
                            env={"VERCEL_TOKEN": "fake"},
                            requester=_FakeVercel(),
                            fetcher=_embeddable_fetcher("M-OK"))
        assert r.deployment.protection_disabled is True


class TestDeleteDeployment:
    def test_delete_hits_v13_with_team_and_reports_deleted(self):
        fake = _FakeVercel(team_id="team_x")
        assert gv.delete_deployment("dpl_test123", "fake", team_id="team_x",
                                    requester=fake) is True
        assert fake.only("DELETE") == [(f"{_API}/v13/deployments/dpl_test123?teamId=team_x", None)]


# ── resolve_token: shared secret-store fallback (FRF-003) ────────────────────

_FAKE_TOKEN = "FAKEvercelTOKENfixture0123456789"  # synthetic, not a real secret


class TestResolveTokenStoreFallback:
    def _isolate(self, monkeypatch, tmp_path, store_text=None):
        import ghl_image_stage
        helper = ghl_image_stage._load_secret_helper()
        assert helper is not None, "shared-utils/secret_helper.py must load from the repo"
        store = tmp_path / "secrets.env"
        if store_text is not None:
            store.write_text(store_text, encoding="utf-8")
        monkeypatch.setattr(helper, "ENV_FILE_CANDIDATES", [str(store)])
        for name in ("VERCEL_TOKEN", "VERCEL_API_TOKEN", "VERCEL_API_KEY"):
            monkeypatch.delenv(name, raising=False)

    def test_env_none_reads_secret_store(self, monkeypatch, tmp_path):
        self._isolate(monkeypatch, tmp_path, f"VERCEL_TOKEN={_FAKE_TOKEN}\n")
        assert gv.resolve_token() == _FAKE_TOKEN

    def test_explicit_env_never_reads_store(self, monkeypatch, tmp_path):
        self._isolate(monkeypatch, tmp_path, f"VERCEL_TOKEN={_FAKE_TOKEN}\n")
        with pytest.raises(gv.VercelTokenError):
            gv.resolve_token({})

    def test_placeholder_in_store_is_not_a_token(self, monkeypatch, tmp_path):
        self._isolate(monkeypatch, tmp_path, "VERCEL_TOKEN=PASTE_REAL_TOKEN\n")
        with pytest.raises(gv.VercelTokenError) as exc:
            gv.resolve_token()
        assert "PASTE_REAL_TOKEN" not in str(exc.value)

    def test_nothing_anywhere_raises(self, monkeypatch, tmp_path):
        self._isolate(monkeypatch, tmp_path, None)
        with pytest.raises(gv.VercelTokenError):
            gv.resolve_token()

    def test_store_token_never_appears_in_error_or_files(self, monkeypatch, tmp_path):
        self._isolate(monkeypatch, tmp_path, f"VERCEL_TOKEN={_FAKE_TOKEN}\n")
        before = sorted(p.name for p in tmp_path.iterdir())
        gv.resolve_token()
        assert sorted(p.name for p in tmp_path.iterdir()) == before, "resolve_token must not write files"


# ── Live-path regression: requester=None, only urlopen stubbed (FRF-003) ─────

import io  # noqa: E402
import json as _json  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402


class _LiveResp:
    def __init__(self, body):
        self.status = 200
        self._b = _json.dumps(body).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestLivePathMakePublic:
    """The production transport (_http_request) against a fake Vercel that,
    like the real one, answers 404 to PATCH /v13/deployments/<id>. FAILS on
    the pre-fix code (HTTP 404 VercelEmbedError), PASSES after the fix."""

    def test_make_public_live_transport(self, monkeypatch):
        seen = []
        project = {"id": _PROJECT_ID, "name": "zhc-ghl-page",
                   "ssoProtection": {"deploymentType": "preview"}, "passwordProtection": None}

        def fake_urlopen(req, timeout=None):
            method, url = req.get_method(), req.full_url
            body = _json.loads(req.data) if req.data else None
            seen.append((method, url, body))
            if method == "GET" and url == f"{_API}/v13/deployments/dpl_live1":
                return _LiveResp({"id": "dpl_live1", "projectId": _PROJECT_ID, "name": "zhc-ghl-page"})
            if method == "PATCH" and url == f"{_API}/v9/projects/{_PROJECT_ID}":
                project.update(body)
                return _LiveResp(project)
            if method == "GET" and url == f"{_API}/v9/projects/{_PROJECT_ID}":
                return _LiveResp(project)
            raise urllib.error.HTTPError(url, 404, "Not Found", {},
                                         io.BytesIO(b'{"error": {"code": "not_found"}}'))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert gv.make_public("dpl_live1", "fake", requester=None) is True
        assert ("PATCH", f"{_API}/v9/projects/{_PROJECT_ID}",
                {"ssoProtection": None, "passwordProtection": None}) in seen


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
