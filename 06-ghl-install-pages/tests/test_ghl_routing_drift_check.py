"""MOCK-only unit tests — U23/B-U9 decision-engine hardening, gap (3b):
the monthly routing-drift live-proof orchestrator.

These tests are MOCK-ONLY. There is NO live Vercel deploy, NO GoHighLevel,
NO network of any kind. ``ghl_vercel.run_pipeline`` is exercised through
INJECTED ``requester``/``fetcher`` callables (the exact same seam
``tests/test_ghl_vercel.py`` uses) so the whole pipeline runs offline.

Coverage:
  * The golden ADVANCED fixture self-check: classify_page on
    GOLDEN_ADVANCED_FIXTURE_HTML actually scores VERCEL_EMBED (proves the
    fixture is honest, not merely asserted).
  * A full mock run: deploy succeeds, is embeddable -> a
    RoutingDriftCheckReceipt is returned and a dated receipt JSON is
    written to routing/routing-drift-check-<date>.json.
  * The receipt's ghl_embed_leg is honestly "deferred_to_live_run" -- never
    fabricated as PASS.
  * A non-embeddable deployment (SSO/XFO blocked) raises
    RoutingDriftCheckError AND still writes the receipt (honest FAIL, never
    silence) -- fail-closed.
  * A Vercel deploy API failure raises RoutingDriftCheckError and writes NO
    receipt (never fabricate success from a hard failure).
  * A seeded decision-engine regression (classify_page monkeypatched/forced
    to return DIRECT for the golden fixture) raises RoutingDriftCheckError
    BEFORE any network call is attempted.
  * Empty evidence_root/project_dir raise ValueError.
  * The CLI (main()) exits 0 on success and 1 on failure, printing the
    receipt path.

No real client/operator names, ids, emails, or location-ids appear. No real
Vercel token value appears (the fixture "fake" string is not a real secret).

Run:
    python3 -m pytest tests/test_ghl_routing_drift_check.py -v
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_method as m
import ghl_vercel as gv
import ghl_routing_drift_check as rdc


# ── Fake Vercel transport (mirrors tests/test_ghl_vercel.py's pattern) ────────

_API = "https://api.vercel.com"
_DEP = "dpl_driftcheck123"
_PRJ = "prj_driftcheck123"


class _FakeVercel:
    """Fake Vercel routed by exact (method, URL); records every call.
    Unknown routes (e.g. the non-existent PATCH /v13/deployments/<id>)
    raise VercelEmbedError like _http_request on a real HTTP 404."""

    def __init__(self, delete_fails=False, patch_404=False):
        self.calls = []
        self.delete_fails = delete_fails
        self.patch_404 = patch_404
        self.project = {"id": _PRJ, "name": "zhc-routing-drift-check",
                        "ssoProtection": {"deploymentType": "preview"}, "passwordProtection": None}

    def __call__(self, method, url, body, *, token=""):
        self.calls.append((method, url, body))
        dep, proj = f"{_API}/v13/deployments/{_DEP}", f"{_API}/v9/projects/{_PRJ}"
        if (method, url) == ("POST", f"{_API}/v13/deployments"):
            return {"id": _DEP, "url": "drift-check.vercel.app", "projectId": _PRJ,
                    "name": "zhc-routing-drift-check"}
        if (method, url) == ("GET", dep):
            return {"id": _DEP, "readyState": "READY", "url": "drift-check.vercel.app",
                    "projectId": _PRJ, "name": "zhc-routing-drift-check"}
        if (method, url) == ("PATCH", proj) and not self.patch_404:
            self.project.update(body)
            return dict(self.project)
        if (method, url) == ("GET", proj):
            return dict(self.project)
        if (method, url) == ("DELETE", dep) and not self.delete_fails:
            return {"state": "DELETED", "uid": _DEP}
        raise gv.VercelEmbedError(f"HTTP 404 from {url}: not_found")


def _vercel_requester(**kw):
    return _FakeVercel(**kw)


def _embeddable_fetcher(marker: str):
    def _f(url: str) -> dict:
        return {
            "status": 200,
            "headers": {
                "content-security-policy": "frame-ancestors https://*.leadconnectorhq.com"
            },
            "body": f"<html>{marker}</html>",
        }
    return _f


def _sso_blocked_fetcher():
    def _f(url: str) -> dict:
        return {
            "status": 401,
            "headers": {"x-frame-options": "DENY"},
            "body": "<html>Please log in</html>",
        }
    return _f


# ── Golden fixture self-check ──────────────────────────────────────────────────

class TestGoldenFixtureSelfCheck:
    def test_golden_fixture_classifies_vercel_embed(self):
        """The fixture used for the drift check must actually BE advanced --
        proven by running the real classifier (via the SAME
        classify_page_from_html path the tool itself uses) on it, not
        merely asserted."""
        decision = m.classify_page_from_html(rdc.GOLDEN_ADVANCED_FIXTURE_HTML)
        assert decision.method == m.PageMethod.VERCEL_EMBED

    def test_golden_fixture_score_at_or_above_threshold(self):
        decision = m.classify_page_from_html(rdc.GOLDEN_ADVANCED_FIXTURE_HTML)
        assert decision.score >= m.ADVANCED_THRESHOLD


# ── run_routing_drift_check — happy path ───────────────────────────────────────

class TestRunRoutingDriftCheckSuccess:
    def test_full_mock_run_returns_receipt(self, tmp_path):
        evidence_root = str(tmp_path / "evidence")
        project_dir = str(tmp_path / "proj")
        marker = "ZHC-ROUTING-DRIFT-CHECK-TEST"

        receipt = rdc.run_routing_drift_check(
            evidence_root, project_dir,
            marker=marker,
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_embeddable_fetcher(marker),
        )

        assert receipt.classification_method == "vercel_embed"
        assert receipt.embeddable is True
        assert receipt.vercel_url
        assert os.path.isfile(receipt.receipt_path)

    def test_receipt_json_written_to_dated_path(self, tmp_path):
        evidence_root = str(tmp_path / "evidence")
        project_dir = str(tmp_path / "proj")
        marker = "ZHC-ROUTING-DRIFT-CHECK-TEST2"

        receipt = rdc.run_routing_drift_check(
            evidence_root, project_dir,
            marker=marker,
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_embeddable_fetcher(marker),
        )

        import time
        expected_name = f"routing-drift-check-{time.strftime('%Y%m%d', time.gmtime())}.json"
        assert os.path.basename(receipt.receipt_path) == expected_name

        with open(receipt.receipt_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["marker"] == marker
        assert data["classification_method"] == "vercel_embed"
        assert data["embeddable"] is True

    def test_ghl_embed_leg_is_honestly_deferred_never_fabricated(self, tmp_path):
        receipt = rdc.run_routing_drift_check(
            str(tmp_path / "evidence"), str(tmp_path / "proj"),
            marker="ZHC-ROUTING-DRIFT-CHECK-TEST3",
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_embeddable_fetcher("ZHC-ROUTING-DRIFT-CHECK-TEST3"),
        )
        assert receipt.ghl_embed_leg["status"] == "deferred_to_live_run"
        assert "U22" in receipt.ghl_embed_leg["reason"]

    def test_auto_generated_marker_when_none_given(self, tmp_path):
        """No marker passed -> the tool generates one itself. The injected
        fetcher reads the marker back out of the prepared project's own
        index.html (written by ghl_vercel.prepare_app before deploy) so the
        test stays correct regardless of the auto-generated marker's exact
        value -- no guessing, no partial-substring shortcuts."""
        project_dir = str(tmp_path / "proj")

        def _self_consistent_fetcher(url: str) -> dict:
            html_path = os.path.join(project_dir, "index.html")
            body = open(html_path, encoding="utf-8").read() if os.path.isfile(html_path) else ""
            return {
                "status": 200,
                "headers": {
                    "content-security-policy": "frame-ancestors https://*.leadconnectorhq.com"
                },
                "body": body,
            }

        receipt = rdc.run_routing_drift_check(
            str(tmp_path / "evidence"), project_dir,
            env={"VERCEL_TOKEN": "fake"},
            requester=_vercel_requester(),
            fetcher=_self_consistent_fetcher,
        )
        assert receipt.marker.startswith("ZHC-ROUTING-DRIFT-CHECK-")
        assert receipt.embeddable is True


# ── run_routing_drift_check — fail-closed paths ─────────────────────────────────

class TestRunRoutingDriftCheckFailClosed:
    def test_non_embeddable_raises_and_still_writes_receipt(self, tmp_path):
        """An honest FAIL: the receipt is written (never silence) even
        though the check itself must raise."""
        evidence_root = str(tmp_path / "evidence")
        project_dir = str(tmp_path / "proj")
        marker = "ZHC-ROUTING-DRIFT-CHECK-BLOCKED"

        with pytest.raises(rdc.RoutingDriftCheckError, match="is NOT embeddable"):
            rdc.run_routing_drift_check(
                evidence_root, project_dir,
                marker=marker,
                env={"VERCEL_TOKEN": "fake"},
                requester=_vercel_requester(),
                fetcher=_sso_blocked_fetcher(),
            )

        import time
        expected_path = os.path.join(
            evidence_root, "routing",
            f"routing-drift-check-{time.strftime('%Y%m%d', time.gmtime())}.json",
        )
        assert os.path.isfile(expected_path), (
            "a non-embeddable result must still write the receipt (honest "
            "FAIL, never silence)"
        )
        with open(expected_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["embeddable"] is False

    def test_vercel_deploy_failure_raises_and_writes_no_receipt(self, tmp_path):
        """A hard Vercel API failure must never fabricate a receipt claiming
        any outcome -- there is nothing honest to write yet."""
        evidence_root = str(tmp_path / "evidence")
        project_dir = str(tmp_path / "proj")

        def _exploding_requester(method, url, body, *, token=""):
            raise RuntimeError("simulated Vercel API outage")

        with pytest.raises(rdc.RoutingDriftCheckError, match="Vercel deploy"):
            rdc.run_routing_drift_check(
                evidence_root, project_dir,
                marker="ZHC-ROUTING-DRIFT-CHECK-DEPLOYFAIL",
                env={"VERCEL_TOKEN": "fake"},
                requester=_exploding_requester,
                fetcher=_embeddable_fetcher("ZHC-ROUTING-DRIFT-CHECK-DEPLOYFAIL"),
            )

        routing_dir = os.path.join(evidence_root, "routing")
        assert not os.path.isdir(routing_dir) or not os.listdir(routing_dir), (
            "a hard deploy failure must not leave a fabricated receipt behind"
        )

    def test_missing_vercel_token_raises(self, tmp_path):
        with pytest.raises(rdc.RoutingDriftCheckError):
            rdc.run_routing_drift_check(
                str(tmp_path / "evidence"), str(tmp_path / "proj"),
                marker="ZHC-ROUTING-DRIFT-CHECK-NOTOKEN",
                env={},  # no VERCEL_TOKEN / VERCEL_API_TOKEN / VERCEL_API_KEY
                requester=_vercel_requester(),
                fetcher=_embeddable_fetcher("x"),
            )

    def test_decision_engine_regression_raises_before_any_network_call(self, tmp_path, monkeypatch):
        """If the golden fixture stops classifying VERCEL_EMBED (a
        decision-engine regression), the check must fail LOUD before
        touching the network -- proven by a requester that raises if
        called at all."""
        def _requester_must_not_be_called(*a, **kw):
            raise AssertionError("network must not be touched after a self-check failure")

        def _fake_classify_page_from_html(html, *a, **kw):
            # Force a DIRECT result regardless of the real fixture's HTML --
            # simulates a decision-engine threshold regression.
            return m.classify_page({"html": "<p>boring</p>"})

        monkeypatch.setattr(
            rdc.ghl_method, "classify_page_from_html", _fake_classify_page_from_html
        )

        with pytest.raises(rdc.RoutingDriftCheckError, match="DECISION-ENGINE REGRESSION"):
            rdc.run_routing_drift_check(
                str(tmp_path / "evidence"), str(tmp_path / "proj"),
                marker="ZHC-ROUTING-DRIFT-CHECK-REGRESSION",
                env={"VERCEL_TOKEN": "fake"},
                requester=_requester_must_not_be_called,
                fetcher=_embeddable_fetcher("x"),
            )

    def test_empty_evidence_root_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            rdc.run_routing_drift_check("", str(tmp_path / "proj"))

    def test_empty_project_dir_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            rdc.run_routing_drift_check(str(tmp_path / "evidence"), "")


# ── CLI (main()) ────────────────────────────────────────────────────────────────

class TestCli:
    def test_main_prints_ok_and_exits_zero_on_success(self, tmp_path, monkeypatch, capsys):
        def _fake_run(evidence_root, project_dir, **kw):
            return rdc.RoutingDriftCheckReceipt(
                marker="ZHC-TEST", classification_method="vercel_embed",
                classification_score=5, vercel_url="https://x.vercel.app",
                embeddable=True, ghl_embed_leg={"status": "deferred_to_live_run"},
                receipt_path=str(tmp_path / "receipt.json"),
            )
        monkeypatch.setattr(rdc, "run_routing_drift_check", _fake_run)
        rc = rdc.main([
            "--evidence-root", str(tmp_path / "ev"),
            "--project-dir", str(tmp_path / "proj"),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out

    def test_main_prints_fail_and_exits_one_on_error(self, tmp_path, monkeypatch, capsys):
        def _fake_run_raises(evidence_root, project_dir, **kw):
            raise rdc.RoutingDriftCheckError("simulated failure")
        monkeypatch.setattr(rdc, "run_routing_drift_check", _fake_run_raises)
        rc = rdc.main([
            "--evidence-root", str(tmp_path / "ev"),
            "--project-dir", str(tmp_path / "proj"),
        ])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out


# ── FRF-003: real Vercel shape, cleanup of the throwaway deployment ──────────


class TestThrowawayCleanup:
    def test_success_path_patches_project_and_deletes_after_receipt(self, tmp_path):
        fake = _FakeVercel()
        marker = "ZHC-ROUTING-DRIFT-CHECK-CLEAN"
        receipt = rdc.run_routing_drift_check(
            str(tmp_path / "evidence"), str(tmp_path / "proj"), marker=marker,
            env={"VERCEL_TOKEN": "fake"}, requester=fake,
            fetcher=_embeddable_fetcher(marker))
        methods = [m for m, _, _ in fake.calls]
        assert ("PATCH", f"{_API}/v9/projects/{_PRJ}",
                {"ssoProtection": None, "passwordProtection": None}) in fake.calls
        assert methods[-1] == "DELETE"
        assert fake.calls[-1][1] == f"{_API}/v13/deployments/{_DEP}"
        assert receipt.cleanup == {"deployment_id": _DEP, "deleted": True}
        data = json.load(open(receipt.receipt_path, encoding="utf-8"))
        assert data["cleanup"]["deleted"] is True

    def test_non_embeddable_still_deletes_and_records(self, tmp_path):
        fake = _FakeVercel()
        with pytest.raises(rdc.RoutingDriftCheckError, match="is NOT embeddable"):
            rdc.run_routing_drift_check(
                str(tmp_path / "evidence"), str(tmp_path / "proj"),
                marker="ZHC-ROUTING-DRIFT-CHECK-BLOCKED2",
                env={"VERCEL_TOKEN": "fake"}, requester=fake,
                fetcher=_sso_blocked_fetcher())
        assert [m for m, _, _ in fake.calls][-1] == "DELETE"

    def test_failed_delete_is_recorded_not_raised(self, tmp_path):
        fake = _FakeVercel(delete_fails=True)
        marker = "ZHC-ROUTING-DRIFT-CHECK-DELFAIL"
        receipt = rdc.run_routing_drift_check(
            str(tmp_path / "evidence"), str(tmp_path / "proj"), marker=marker,
            env={"VERCEL_TOKEN": "fake"}, requester=fake,
            fetcher=_embeddable_fetcher(marker))
        assert receipt.cleanup["deleted"] is False
        assert "HTTP 404" in receipt.cleanup["error"]

    def test_make_public_failure_deletes_orphan_and_raises(self, tmp_path):
        fake = _FakeVercel(patch_404=True)
        with pytest.raises(rdc.RoutingDriftCheckError, match="Vercel deploy leg failed"):
            rdc.run_routing_drift_check(
                str(tmp_path / "evidence"), str(tmp_path / "proj"),
                marker="ZHC-ROUTING-DRIFT-CHECK-404",
                env={"VERCEL_TOKEN": "fake"}, requester=fake,
                fetcher=_embeddable_fetcher("x"))
        assert [m for m, _, _ in fake.calls][-1] == "DELETE"
        routing_dir = os.path.join(str(tmp_path / "evidence"), "routing")
        assert not os.path.isdir(routing_dir) or not os.listdir(routing_dir)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
