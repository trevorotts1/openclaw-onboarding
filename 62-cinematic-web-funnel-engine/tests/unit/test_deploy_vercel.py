#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_deploy_vercel.py — offline unit tests for scripts/deploy_vercel.py
(Skill 62, U17).

NO NETWORK, NO VERCEL_TOKEN, NO LIVE/PAID CALL. Every HTTP interaction goes
through a FakeTransport driven by the fixtures in tests/fixtures/vercel/
(spec §19.2 "Vercel deployment adapter with mocked ... live run") —
RequestsTransport (the only implementation that ever touches the network)
is never instantiated by this suite. Slow, real-toolchain, end-to-end
coverage (the full preview->production round trip, restart reconciliation,
and the fail-closed proofs) lives in scripts/deploy_vercel.py's own
``--self-test`` and is re-exercised by tests/unit/test_prove_deployment.py's
self-test companion — this suite is the fast/offline layer (spec 19.1
"unit tests" scope): payload shape, state mapping, file-tree walking,
token resolution, and each producer function's precondition/fail-closed
branch, each tested in isolation against a hand-built minimal run_dir
(never a real npm/next build — that would make this an integration test).

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"

for _p in (str(_SKILL_DIR), str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deploy_vercel as dv  # noqa: E402
import state_engine  # noqa: E402

_FIXTURES_DIR = _TESTS_DIR.parent / "fixtures" / "vercel"


def _load_fixture(name: str) -> Dict[str, Any]:
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _resp(status_code: int, body: Dict[str, Any]) -> dv.HttpResponse:
    return dv.HttpResponse(status_code=status_code, json_body=body)


# ---------------------------------------------------------------------------
# FakeTransport — FIFO-queued responses per verb, never touches the network.
# ---------------------------------------------------------------------------


class FakeTransport(dv.VercelTransport):
    def __init__(self) -> None:
        self.post_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self.patch_calls: List[Dict[str, Any]] = []
        self.put_calls: List[Dict[str, Any]] = []
        self.fetch_calls: List[str] = []
        self._post_queue: List[dv.HttpResponse] = []
        self._get_queue: List[dv.HttpResponse] = []
        self._patch_queue: List[dv.HttpResponse] = []
        self._put_queue: List[dv.HttpResponse] = []
        self._fetch_queue: List[dv.HttpResponse] = []

    def queue_post(self, resp: dv.HttpResponse) -> None:
        self._post_queue.append(resp)

    def queue_get(self, resp: dv.HttpResponse) -> None:
        self._get_queue.append(resp)

    def queue_patch(self, resp: dv.HttpResponse) -> None:
        self._patch_queue.append(resp)

    def queue_put(self, resp: dv.HttpResponse) -> None:
        self._put_queue.append(resp)

    def queue_fetch(self, resp: dv.HttpResponse) -> None:
        self._fetch_queue.append(resp)

    def post_json(self, url, *, headers, body, timeout):
        self.post_calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        if not self._post_queue:
            raise AssertionError(f"FakeTransport: no queued POST response for {url}")
        return self._post_queue.pop(0)

    def get_json(self, url, *, headers, params, timeout):
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if not self._get_queue:
            raise AssertionError(f"FakeTransport: no queued GET response for {url}")
        return self._get_queue.pop(0)

    def patch_json(self, url, *, headers, body, timeout):
        self.patch_calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        if not self._patch_queue:
            raise AssertionError(f"FakeTransport: no queued PATCH response for {url}")
        return self._patch_queue.pop(0)

    def put_bytes(self, url, *, headers, data, timeout):
        self.put_calls.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        if not self._put_queue:
            raise AssertionError(f"FakeTransport: no queued PUT response for {url}")
        return self._put_queue.pop(0)

    def fetch(self, url, *, timeout):
        self.fetch_calls.append(url)
        if not self._fetch_queue:
            raise AssertionError(f"FakeTransport: no queued fetch response for {url}")
        return self._fetch_queue.pop(0)


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------


class TokenResolutionTests(unittest.TestCase):
    def test_resolve_token_precedence(self) -> None:
        env = {"VERCEL_TOKEN": "", "VERCEL_API_TOKEN": "second", "VERCEL_API_KEY": "third"}
        self.assertEqual(dv.resolve_token(env), "second")

    def test_resolve_token_first_wins(self) -> None:
        env = {"VERCEL_TOKEN": "first", "VERCEL_API_TOKEN": "second"}
        self.assertEqual(dv.resolve_token(env), "first")

    def test_resolve_token_missing_raises_with_names_only(self) -> None:
        with self.assertRaises(dv.VercelTokenError) as ctx:
            dv.resolve_token({})
        msg = str(ctx.exception)
        for name in dv.VERCEL_TOKEN_ENV_CANDIDATES:
            self.assertIn(name, msg)

    def test_resolve_blob_token(self) -> None:
        self.assertEqual(dv.resolve_blob_token({"BLOB_READ_WRITE_TOKEN": "blobtok"}), "blobtok")
        with self.assertRaises(dv.VercelTokenError):
            dv.resolve_blob_token({})


# ---------------------------------------------------------------------------
# readyState mapping — fail closed on an unrecognized value
# ---------------------------------------------------------------------------


class ReadyStateMappingTests(unittest.TestCase):
    def test_known_states(self) -> None:
        self.assertEqual(dv._map_ready_state("QUEUED"), "queued")
        self.assertEqual(dv._map_ready_state("INITIALIZING"), "building")
        self.assertEqual(dv._map_ready_state("BUILDING"), "building")
        self.assertEqual(dv._map_ready_state("READY"), "ready")
        self.assertEqual(dv._map_ready_state("ERROR"), "error")
        self.assertEqual(dv._map_ready_state("CANCELED"), "cancelled")
        self.assertEqual(dv._map_ready_state("canceled"), "cancelled")  # case-insensitive

    def test_unknown_state_fails_closed(self) -> None:
        with self.assertRaises(dv.DeploymentError):
            dv._map_ready_state("SOME_NEW_STATE_VERCEL_ADDS_LATER")


# ---------------------------------------------------------------------------
# _read_deployable_files
# ---------------------------------------------------------------------------


class ReadDeployableFilesTests(unittest.TestCase):
    def test_excludes_build_and_hidden_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app").mkdir()
            (root / "app" / "page.tsx").write_text("export default function Page() { return null; }")
            (root / "package.json").write_text('{"name": "fixture"}')
            (root / "node_modules").mkdir()
            (root / "node_modules" / "junk.js").write_text("should not be deployed")
            (root / ".next").mkdir()
            (root / ".next" / "cache.bin").write_bytes(b"\x00\x01")
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: refs/heads/main")
            (root / ".env.local").write_text("SECRET=should-not-ship")

            files = dv._read_deployable_files(str(root))
            names = {f["file"] for f in files}

            self.assertIn("app/page.tsx", names)
            self.assertIn("package.json", names)
            self.assertFalse(any(n.startswith("node_modules/") for n in names))
            self.assertFalse(any(n.startswith(".next/") for n in names))
            self.assertFalse(any(n.startswith(".git/") for n in names))
            self.assertNotIn(".env.local", names)

    def test_base64_round_trips_real_bytes(self) -> None:
        import base64

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public").mkdir()
            payload = b"\x89PNG\r\n\x1a\nfixture-bytes-not-a-real-png"
            (root / "public" / "poster.jpg").write_bytes(payload)

            files = dv._read_deployable_files(str(root))
            self.assertEqual(len(files), 1)
            entry = files[0]
            self.assertEqual(entry["file"], "public/poster.jpg")
            self.assertEqual(entry["encoding"], "base64")
            self.assertEqual(base64.b64decode(entry["data"]), payload)

    def test_empty_dir_returns_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(dv._read_deployable_files(tmp), [])


# ---------------------------------------------------------------------------
# resolve_commit_sha
# ---------------------------------------------------------------------------


class ResolveCommitShaTests(unittest.TestCase):
    def test_explicit_value_passthrough(self) -> None:
        self.assertEqual(dv.resolve_commit_sha("  abc123  "), "abc123")

    def test_explicit_empty_raises(self) -> None:
        with self.assertRaises(dv.DeploymentError):
            dv.resolve_commit_sha("   ")

    def test_git_failure_in_non_git_dir_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(dv.DeploymentError):
                dv.resolve_commit_sha(None, cwd=Path(tmp))

    def test_git_success_against_this_skill_repo(self) -> None:
        # _SKILL_DIR lives inside a real git worktree in this build environment.
        sha = dv.resolve_commit_sha(None, cwd=_SKILL_DIR)
        self.assertRegex(sha, r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# VercelHostingAdapter
# ---------------------------------------------------------------------------


class VercelHostingAdapterDeployTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = dv.VercelHostingAdapter(
            self.transport, "fixture-token", poll_interval_seconds=0.0, sleep_fn=lambda *_: None,
        )

    def _site_dir_with_one_file(self) -> str:
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "package.json").write_text('{"name": "fixture"}')
        return tmp

    def test_preview_omits_target_field(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("deploy_create_queued.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_ready.json")))
        self.adapter.deploy(self._site_dir_with_one_file(), environment="preview", project_name="fixture-proj", commit_sha="deadbeef")
        body = self.transport.post_calls[0]["body"]
        self.assertNotIn("target", body)
        self.assertEqual(body["gitMetadata"]["commitSha"], "deadbeef")
        self.assertEqual(body["projectSettings"]["framework"], "nextjs")

    def test_production_sets_target_field(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("deploy_create_queued.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_ready.json")))
        self.adapter.deploy(self._site_dir_with_one_file(), environment="production", project_name="fixture-proj", commit_sha="deadbeef")
        body = self.transport.post_calls[0]["body"]
        self.assertEqual(body["target"], "production")

    def test_polls_through_building_to_ready(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("deploy_create_queued.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_building.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_ready.json")))
        result = self.adapter.deploy(self._site_dir_with_one_file(), environment="preview", project_name="fixture-proj", commit_sha="deadbeef")
        self.assertEqual(result.status, "ready")
        self.assertEqual(len(self.transport.get_calls), 2)
        self.assertTrue(result.url.startswith("https://"))

    def test_terminal_error_state_returned_not_raised_by_adapter(self) -> None:
        # The adapter reports state honestly; deciding pass/fail from a
        # terminal ERROR is the PRODUCER's job (scripts/deploy_vercel._deploy),
        # not the adapter's — see module docstring.
        self.transport.queue_post(_resp(200, _load_fixture("deploy_create_queued.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_error.json")))
        result = self.adapter.deploy(self._site_dir_with_one_file(), environment="preview", project_name="fixture-proj", commit_sha="deadbeef")
        self.assertEqual(result.status, "error")

    def test_http_error_on_submission_raises(self) -> None:
        self.transport.queue_post(_resp(500, {"error": "internal"}))
        with self.assertRaises(dv.DeploymentError):
            self.adapter.deploy(self._site_dir_with_one_file(), environment="preview", project_name="fixture-proj", commit_sha="deadbeef")

    def test_missing_id_in_response_raises(self) -> None:
        self.transport.queue_post(_resp(200, {"url": "x.vercel.app", "readyState": "QUEUED"}))
        with self.assertRaises(dv.DeploymentError):
            self.adapter.deploy(self._site_dir_with_one_file(), environment="preview", project_name="fixture-proj", commit_sha="deadbeef")

    def test_empty_site_dir_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(dv.DeploymentError):
                self.adapter.deploy(tmp, environment="preview", project_name="fixture-proj", commit_sha="deadbeef")

    def test_poll_timeout_raises(self) -> None:
        adapter = dv.VercelHostingAdapter(
            self.transport, "fixture-token", poll_max=2, poll_interval_seconds=0.0, sleep_fn=lambda *_: None,
        )
        self.transport.queue_post(_resp(200, _load_fixture("deploy_create_queued.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_building.json")))
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_building.json")))
        with self.assertRaises(dv.DeploymentError):
            adapter.deploy(self._site_dir_with_one_file(), environment="preview", project_name="fixture-proj", commit_sha="deadbeef")

    def test_get_status_maps_fixture(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("deploy_status_ready.json")))
        result = self.adapter.get_status("dpl_fixture_0000000000000001")
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.host, "vercel")
        self.assertEqual(result.host_deployment_id, "dpl_fixture_0000000000000001")

    def test_get_status_http_error_raises(self) -> None:
        self.transport.queue_get(_resp(404, {"error": "not found"}))
        with self.assertRaises(dv.DeploymentError):
            self.adapter.get_status("dpl_missing")

    def test_smoke_test_ok(self) -> None:
        self.transport.queue_fetch(dv.HttpResponse(status_code=200, json_body={}, content=b"<html>ok</html>"))
        result = self.adapter.smoke_test("https://cwfe-fixture.vercel.app")
        self.assertTrue(result.ok)
        self.assertEqual(result.http_status, 200)

    def test_smoke_test_failure(self) -> None:
        self.transport.queue_fetch(dv.HttpResponse(status_code=500, json_body={}, content=b""))
        result = self.adapter.smoke_test("https://cwfe-fixture.vercel.app")
        self.assertFalse(result.ok)
        self.assertEqual(result.http_status, 500)

    def test_disable_protection_success(self) -> None:
        self.transport.queue_patch(_resp(200, {"protection": {"deploymentType": "none"}}))
        self.assertTrue(self.adapter.disable_protection("dpl_fixture_0000000000000001"))
        self.assertEqual(self.transport.patch_calls[0]["body"], {"protection": {"deploymentType": "none"}})

    def test_disable_protection_http_error_raises(self) -> None:
        self.transport.queue_patch(_resp(404, {"error": "not found"}))
        with self.assertRaises(dv.DeploymentError):
            self.adapter.disable_protection("dpl_missing")

    def test_unknown_environment_rejected(self) -> None:
        with self.assertRaises(dv.DeploymentError):
            self.adapter.deploy(self._site_dir_with_one_file(), environment="staging", project_name="p", commit_sha="deadbeef")


# ---------------------------------------------------------------------------
# VercelBlobAdapter
# ---------------------------------------------------------------------------


class VercelBlobAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = dv.VercelBlobAdapter(self.transport, "fixture-blob-token")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local_path = Path(self.tmp.name) / "hero-open.mp4"
        self.local_path.write_bytes(b"fixture-video-bytes")

    def test_put_success_sends_documented_headers(self) -> None:
        self.transport.queue_put(_resp(200, _load_fixture("blob_put_success.json")))
        result = self.adapter.put(str(self.local_path), pathname="proj/hero-open/hero-open.mp4")
        self.assertEqual(result.provider, "vercel-blob")
        self.assertTrue(result.url.startswith("https://"))
        self.assertEqual(result.size_bytes, len(b"fixture-video-bytes"))

        headers = self.transport.put_calls[0]["headers"]
        self.assertEqual(headers["authorization"], "Bearer fixture-blob-token")
        self.assertEqual(headers["x-api-version"], dv.BLOB_API_VERSION)
        self.assertEqual(headers["access"], "public")
        self.assertIn("x-content-type", headers)
        self.assertIn("x-cache-control-max-age", headers)
        self.assertEqual(self.transport.put_calls[0]["url"], f"{dv.BLOB_API_ORIGIN}/proj/hero-open/hero-open.mp4")
        self.assertEqual(self.transport.put_calls[0]["data"], b"fixture-video-bytes")

    def test_put_missing_local_file_raises(self) -> None:
        with self.assertRaises(dv.VercelBlobError):
            self.adapter.put(str(Path(self.tmp.name) / "does-not-exist.mp4"), pathname="x/y.mp4")

    def test_put_http_error_raises(self) -> None:
        self.transport.queue_put(_resp(403, {"error": "forbidden"}))
        with self.assertRaises(dv.VercelBlobError):
            self.adapter.put(str(self.local_path), pathname="proj/hero-open/hero-open.mp4")

    def test_put_missing_url_in_response_raises(self) -> None:
        self.transport.queue_put(_resp(200, {"pathname": "x"}))
        with self.assertRaises(dv.VercelBlobError):
            self.adapter.put(str(self.local_path), pathname="proj/hero-open/hero-open.mp4")

    def test_put_non_https_url_raises(self) -> None:
        self.transport.queue_put(_resp(200, {"url": "http://insecure.example.com/x", "pathname": "x"}))
        with self.assertRaises(dv.VercelBlobError):
            self.adapter.put(str(self.local_path), pathname="proj/hero-open/hero-open.mp4")


# ---------------------------------------------------------------------------
# Producer functions — hand-built minimal run_dir (fast, offline; NOT a real
# npm/next build — see module docstring for why that's the correct layer
# for this suite).
# ---------------------------------------------------------------------------


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_fixture_run_dir(root: Path, *, project_id: str = "u17-fixture-project",
                            build_status: str = "pass", scene_count: int = 2) -> Path:
    """Hand-builds the minimal on-disk state deploy_vercel.py's producer
    functions need: project-manifest.json (via the real state_engine, so
    every write goes through the SAME schema-validated path a real P1
    would have used) + a materialized site_dir with real scene media bytes
    + a schema-valid build-receipt.json referencing them (spec 19.1 unit
    test scope — deliberately NOT a real npm/next build; that coverage
    lives in --self-test / tests/integration)."""
    run_dir = root / "run"
    site_dir = run_dir / "site"
    (site_dir / "app").mkdir(parents=True)
    (site_dir / "public" / "media").mkdir(parents=True)
    (site_dir / "app" / "page.tsx").write_text("export default function Page(){return null;}")
    (site_dir / "package.json").write_text(json.dumps({"name": project_id}))

    scenes = []
    for i in range(scene_count):
        scene_id = f"scene-{i:02d}"
        video_bytes = f"fixture-video-{scene_id}".encode("utf-8")
        poster_bytes = f"fixture-poster-{scene_id}".encode("utf-8")
        (site_dir / "public" / "media" / f"{scene_id}.mp4").write_bytes(video_bytes)
        (site_dir / "public" / "media" / f"{scene_id}.jpg").write_bytes(poster_bytes)
        scenes.append({
            "scene_id": scene_id,
            "video_path": f"public/media/{scene_id}.mp4",
            "poster_path": f"public/media/{scene_id}.jpg",
            "video_sha256": _sha256_hex(video_bytes),
            "poster_sha256": _sha256_hex(poster_bytes),
            "video_bytes": len(video_bytes),
            "poster_bytes": len(poster_bytes),
        })

    build_receipt = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "project_slug": project_id,
        "site_dir": str(site_dir),
        "template_source": {"nextjs_app_hash": "0" * 64, "components_hash": "0" * 64},
        "content_hash": "0" * 64,
        "scenes": scenes,
        "sections": ["hero"],
        "routes": ["app/layout.tsx", "app/page.tsx"],
        "steps": {
            "install": {"ran": True, "exit_code": 0, "duration_seconds": 1.0},
            "lint": {"ran": True, "exit_code": 0, "duration_seconds": 1.0},
            "typecheck": {"ran": True, "exit_code": 0, "duration_seconds": 1.0},
            "build": {"ran": True, "exit_code": 0, "duration_seconds": 1.0},
        },
        "checks": {"no_placeholders": True, "no_hardcoded_secrets": True, "media_references_resolve": True},
        "status": build_status,
        "created_at": "2026-07-15T00:00:00Z",
    }
    run_dir.mkdir(exist_ok=True)
    (run_dir / "build-receipt.json").write_text(json.dumps(build_receipt, indent=2), encoding="utf-8")

    state = state_engine.ProjectState(run_dir)
    state.create_project(
        project_id=project_id, client_slug="u17-fixture-client", project_slug=project_id,
        deliverable_type="cinematic-landing-page", budget_cap_usd=25.0,
    )
    return run_dir


class _ScriptedTransport(dv.VercelTransport):
    """Always answers QUEUED then READY on the first poll, for producer
    tests that don't care about the polling loop itself (already covered
    above)."""

    def __init__(self, *, terminal_state: str = "READY") -> None:
        self._terminal_state = terminal_state

    def post_json(self, url, *, headers, body, timeout):
        return dv.HttpResponse(status_code=200, json_body={"id": "dpl_producer_fixture", "url": "producer-fixture.vercel.app", "readyState": "QUEUED", "projectId": "prj_x"})

    def get_json(self, url, *, headers, params, timeout):
        return dv.HttpResponse(status_code=200, json_body={"id": "dpl_producer_fixture", "url": "producer-fixture.vercel.app", "readyState": self._terminal_state, "projectId": "prj_x"})

    def fetch(self, url, *, timeout):
        return dv.HttpResponse(status_code=200, json_body={}, content=b"<html>ok</html>")


class ProducerFunctionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-deploy-vercel-producer-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _adapter(self, **kwargs) -> dv.VercelHostingAdapter:
        return dv.VercelHostingAdapter(_ScriptedTransport(**kwargs), "fixture-token", poll_interval_seconds=0.0, sleep_fn=lambda *_: None)

    def test_deploy_preview_happy_path_appends_receipt(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        receipt = dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")
        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["environment"], "preview")
        self.assertEqual(receipt["commit_sha"], "c0ffee")

        state = state_engine.ProjectState(run_dir)
        stored = state.latest_deployment_receipt("preview")
        self.assertEqual(stored["host_deployment_id"], "dpl_producer_fixture")
        manifest = state.load("project-manifest")
        self.assertEqual(manifest["deployment"]["preview"]["status"], "ready")

    def test_deploy_refuses_when_build_not_passed(self) -> None:
        run_dir = _build_fixture_run_dir(self.root, build_status="failed")
        with self.assertRaises(dv.DeploymentError):
            dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")

    def test_deploy_refuses_on_project_id_mismatch(self) -> None:
        run_dir = _build_fixture_run_dir(self.root, project_id="fixture-a")
        receipt_path = run_dir / "build-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["project_id"] = "fixture-b-does-not-match-project-manifest"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaises(dv.DeploymentError):
            dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")

    def test_terminal_error_is_recorded_and_raises(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        with self.assertRaises(dv.DeploymentError):
            dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(terminal_state="ERROR"), project_name="fixture-proj")
        state = state_engine.ProjectState(run_dir)
        stored = state.latest_deployment_receipt("preview")
        self.assertEqual(stored["status"], "error")

    def test_smoke_test_failure_is_recorded_and_raises(self) -> None:
        class _ReadyButUnservable(_ScriptedTransport):
            def fetch(self, url, *, timeout):
                return dv.HttpResponse(status_code=500, json_body={}, content=b"")

        run_dir = _build_fixture_run_dir(self.root)
        adapter = dv.VercelHostingAdapter(_ReadyButUnservable(), "fixture-token", poll_interval_seconds=0.0, sleep_fn=lambda *_: None)
        with self.assertRaises(dv.DeploymentError):
            dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=adapter, project_name="fixture-proj")
        state = state_engine.ProjectState(run_dir)
        stored = state.latest_deployment_receipt("preview")
        self.assertEqual(stored["status"], "error")

    def test_production_requires_existing_preview(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        with self.assertRaises(dv.DeploymentError):
            dv.deploy_production(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")

    def test_production_refuses_commit_sha_mismatch(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")
        with self.assertRaises(dv.DeploymentError):
            dv.deploy_production(run_dir, commit_sha="different-sha", adapter=self._adapter(), project_name="fixture-proj")

    def test_production_defaults_to_preview_commit_sha(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")
        receipt = dv.deploy_production(run_dir, adapter=self._adapter(), project_name="fixture-proj")
        self.assertEqual(receipt["commit_sha"], "c0ffee")

    def test_production_can_bypass_preview_requirement(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        receipt = dv.deploy_production(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj", require_preview=False)
        self.assertEqual(receipt["status"], "ready")

    def test_reconcile_deployment_refetches_from_host(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        dv.deploy_preview(run_dir, commit_sha="c0ffee", adapter=self._adapter(), project_name="fixture-proj")
        reconciled = dv.reconcile_deployment(run_dir, "preview", adapter=self._adapter())
        self.assertTrue(reconciled["restart_verified"])
        self.assertEqual(reconciled["status"], "ready")

    def test_reconcile_deployment_no_receipt_raises(self) -> None:
        run_dir = _build_fixture_run_dir(self.root)
        with self.assertRaises(dv.DeploymentError):
            dv.reconcile_deployment(run_dir, "preview", adapter=self._adapter())

    def test_upload_scene_media_to_blob_happy_path(self) -> None:
        run_dir = _build_fixture_run_dir(self.root, scene_count=2)
        transport = FakeTransport()
        for _ in range(4):  # 2 scenes x (video + poster)
            transport.queue_put(_resp(200, _load_fixture("blob_put_success.json")))
        adapter = dv.VercelBlobAdapter(transport, "fixture-blob-token")
        manifest = dv.upload_scene_media_to_blob(run_dir, adapter=adapter)
        self.assertEqual(len(manifest["assets"]), 4)
        self.assertEqual(manifest["provider"], "vercel-blob")
        self.assertTrue((run_dir / "blob-manifest.json").is_file())
        # Pathnames are deterministic: <project_id>/<scene_id>/<filename>, no randomness.
        put_urls = [c["url"] for c in transport.put_calls]
        self.assertTrue(any("scene-00" in u for u in put_urls))

    def test_upload_scene_media_missing_file_raises(self) -> None:
        run_dir = _build_fixture_run_dir(self.root, scene_count=1)
        # Delete a referenced media file out from under the receipt.
        build_receipt = json.loads((run_dir / "build-receipt.json").read_text(encoding="utf-8"))
        video_rel = build_receipt["scenes"][0]["video_path"]
        (Path(build_receipt["site_dir"]) / video_rel).unlink()
        transport = FakeTransport()
        adapter = dv.VercelBlobAdapter(transport, "fixture-blob-token")
        with self.assertRaises(dv.DeploymentError):
            dv.upload_scene_media_to_blob(run_dir, adapter=adapter)


if __name__ == "__main__":
    unittest.main()
