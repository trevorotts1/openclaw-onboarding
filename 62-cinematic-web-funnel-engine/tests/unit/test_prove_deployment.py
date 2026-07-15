#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_deployment.py — offline unit tests for scripts/prove_deployment.py
(Skill 62, U17), the CWFE-MANIFEST.json py_symbol home for P14-PREVIEW
(``prove_deployment.evaluate_preview``) and P15-PRODUCTION
(``prove_deployment.evaluate_production``).

NO NETWORK. Every deployment receipt used here is hand-appended directly
through ``state_engine.ProjectState.append_deployment_receipt`` (the same
real, schema-validated write path ``scripts/deploy_vercel.py`` itself uses)
against a minimal hand-built run_dir — this suite never runs a real npm/next
build (that slow, end-to-end coverage, including the identical fail-closed
proofs exercised here, lives in ``scripts/prove_deployment.py``'s own
``--self-test``, spec 19.1 vs 19.2 scope split).

Every "independent re-fetch" the gate performs is driven by a small fake
``deploy_vercel.VercelTransport`` — this is the crux of the fail-closed
doctrine under test: the gate must reach its verdict from what the ADAPTER
reports right now, never from the receipt's own recorded ``status`` field.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"

for _p in (str(_SKILL_DIR), str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deploy_vercel as dv  # noqa: E402
import prove_deployment as pd  # noqa: E402
import state_engine  # noqa: E402


class _FixedStatusTransport(dv.VercelTransport):
    """Always answers get_status() with a fixed readyState, regardless of
    what any on-disk receipt claims — the point of the fake."""

    def __init__(self, ready_state: str, *, url: str = "cwfe-fixture.vercel.app") -> None:
        self._ready_state = ready_state
        self._url = url

    def get_json(self, url, *, headers, params, timeout):
        deployment_id = url.rsplit("/", 1)[-1].split("?")[0]
        return dv.HttpResponse(status_code=200, json_body={
            "id": deployment_id, "url": self._url, "readyState": self._ready_state, "projectId": "prj_x",
        })


def _make_run_dir(root: Path, *, project_id: str = "u17-prove-fixture") -> Path:
    run_dir = root / "run"
    run_dir.mkdir(parents=True)
    state = state_engine.ProjectState(run_dir)
    state.create_project(
        project_id=project_id, client_slug="u17-prove-client", project_slug=project_id,
        deliverable_type="cinematic-landing-page", budget_cap_usd=25.0,
    )
    return run_dir


def _append_receipt(run_dir: Path, *, environment: str, status: str = "ready",
                     commit_sha: str = "c0ffee", host_deployment_id: str = "dpl_fixture_0001",
                     url: str = "https://cwfe-fixture.vercel.app",
                     project_id: str = "u17-prove-fixture", host: str = "vercel") -> Dict[str, Any]:
    state = state_engine.ProjectState(run_dir)
    receipt = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "environment": environment,
        "host": host,
        "host_project_id": "prj_fixture",
        "host_deployment_id": host_deployment_id,
        "url": url,
        "commit_sha": commit_sha,
        "status": status,
        "restart_verified": False,
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }
    state.append_deployment_receipt(receipt)
    return receipt


class NoReceiptTests(unittest.TestCase):
    def test_evaluate_preview_fails_with_no_receipts_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            passed, detail = pd.evaluate_preview(run_dir)
            self.assertFalse(passed)
            self.assertIn("deployment-receipts.json not found", detail)

    def test_evaluate_preview_fails_with_no_matching_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="production")
            passed, detail = pd.evaluate_preview(run_dir)
            self.assertFalse(passed)
            self.assertIn("no preview deployment receipt", detail)


class StructuralChecksTests(unittest.TestCase):
    def test_non_https_url_fails_without_calling_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", url="http://not-https.example.com")

            class _ExplodingAdapter(dv.VercelHostingAdapter):
                def get_status(self, host_deployment_id):
                    raise AssertionError("adapter must not be called when a structural check already failed")

            adapter = _ExplodingAdapter(_FixedStatusTransport("READY"), "tok")
            passed, detail = pd.evaluate_preview(run_dir, adapter=adapter)
            self.assertFalse(passed)
            self.assertIn("not https", detail)

    def test_unsupported_host_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", host="netlify")
            passed, detail = pd.evaluate_preview(run_dir, adapter=dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok"))
            self.assertFalse(passed)
            self.assertIn("expected one of", detail)

    def test_missing_host_deployment_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", host_deployment_id="")
            passed, detail = pd.evaluate_preview(run_dir, adapter=dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok"))
            self.assertFalse(passed)
            self.assertIn("host_deployment_id", detail)

    def test_receipt_status_not_ready_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", status="building")
            passed, detail = pd.evaluate_preview(run_dir, adapter=dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok"))
            self.assertFalse(passed)
            self.assertIn("not 'ready'", detail)

    def test_secret_shaped_value_in_receipt_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            # host_project_id is free-text in the schema; smuggle a secret-shaped
            # value into it to prove the scan actually inspects the whole receipt.
            state = state_engine.ProjectState(run_dir)
            receipt = {
                "schema_version": "1.0.0", "project_id": "u17-prove-fixture", "environment": "preview",
                "host": "vercel", "host_project_id": "sk-abcdefghijklmnopqrstuvwx",
                "host_deployment_id": "dpl_fixture_0001", "url": "https://cwfe-fixture.vercel.app",
                "commit_sha": "c0ffee", "status": "ready", "restart_verified": False,
                "created_at": "2026-07-15T00:00:00Z", "updated_at": "2026-07-15T00:00:00Z",
            }
            state.append_deployment_receipt(receipt)
            passed, detail = pd.evaluate_preview(run_dir, adapter=dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok"))
            self.assertFalse(passed)
            self.assertIn("secret-shaped value", detail)


class IndependentRefetchTests(unittest.TestCase):
    def test_pass_when_host_agrees_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("READY", url="cwfe-fixture.vercel.app"), "tok")
            passed, detail = pd.evaluate_preview(run_dir, adapter=adapter)
            self.assertTrue(passed, detail)
            self.assertIn("independently", detail)

    def test_fail_when_host_disagrees_still_building(self) -> None:
        """The central fail-closed proof: a well-formed receipt claiming
        status='ready' must still FAIL when the live host disagrees."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("BUILDING"), "tok")
            passed, detail = pd.evaluate_preview(run_dir, adapter=adapter)
            self.assertFalse(passed)
            self.assertIn("stale or tampered", detail)

    def test_fail_when_host_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("ERROR"), "tok")
            passed, detail = pd.evaluate_preview(run_dir, adapter=adapter)
            self.assertFalse(passed)

    def test_fail_when_adapter_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview")

            class _BrokenTransport(dv.VercelTransport):
                def get_json(self, url, *, headers, params, timeout):
                    raise ConnectionError("network fixture failure")

            adapter = dv.VercelHostingAdapter(_BrokenTransport(), "tok")
            passed, detail = pd.evaluate_preview(run_dir, adapter=adapter)
            self.assertFalse(passed)
            self.assertIn("independent re-fetch", detail)

    def test_url_mismatch_between_receipt_and_live_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", url="https://recorded.vercel.app")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("READY", url="different-live-url.vercel.app"), "tok")
            passed, detail = pd.evaluate_preview(run_dir, adapter=adapter)
            self.assertFalse(passed)
            self.assertIn("does not match", detail)


class ProductionCrossCheckTests(unittest.TestCase):
    def test_production_fails_without_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="production", commit_sha="c0ffee")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok")
            passed, detail = pd.evaluate_production(run_dir, adapter=adapter)
            self.assertFalse(passed)
            self.assertIn("no preview receipt", detail)

    def test_production_fails_on_commit_sha_mismatch_with_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", commit_sha="c0ffee", host_deployment_id="dpl_preview")
            _append_receipt(run_dir, environment="production", commit_sha="deadbeef", host_deployment_id="dpl_prod")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok")
            passed, detail = pd.evaluate_production(run_dir, adapter=adapter)
            self.assertFalse(passed)
            self.assertIn("does not match preview commit_sha", detail)

    def test_production_passes_when_commit_sha_matches_ready_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", commit_sha="c0ffee", host_deployment_id="dpl_preview", url="https://preview.vercel.app")
            _append_receipt(run_dir, environment="production", commit_sha="c0ffee", host_deployment_id="dpl_prod", url="https://prod.vercel.app")

            class _PerDeployment(dv.VercelTransport):
                def get_json(self, url, *, headers, params, timeout):
                    deployment_id = url.rsplit("/", 1)[-1].split("?")[0]
                    live_url = "preview.vercel.app" if deployment_id == "dpl_preview" else "prod.vercel.app"
                    return dv.HttpResponse(status_code=200, json_body={"id": deployment_id, "url": live_url, "readyState": "READY", "projectId": "prj_x"})

            adapter = dv.VercelHostingAdapter(_PerDeployment(), "tok")
            passed, detail = pd.evaluate_production(run_dir, adapter=adapter)
            self.assertTrue(passed, detail)

    def test_production_fails_when_preview_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp))
            _append_receipt(run_dir, environment="preview", commit_sha="c0ffee", status="building", host_deployment_id="dpl_preview")
            _append_receipt(run_dir, environment="production", commit_sha="c0ffee", host_deployment_id="dpl_prod")
            adapter = dv.VercelHostingAdapter(_FixedStatusTransport("READY"), "tok")
            passed, detail = pd.evaluate_production(run_dir, adapter=adapter)
            self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
