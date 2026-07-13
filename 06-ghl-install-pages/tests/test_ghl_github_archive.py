"""MOCK-only unit tests — ghl_github_archive (non-blocking GitHub archival for
the Skill 06 VERCEL_EMBED path).

These tests are MOCK-ONLY. There is NO live GitHub API call, NO real
subprocess spawn, and NO network of any kind. Every GitHub REST call is
exercised through an injected ``requester`` callable (same seam style as
``tests/test_ghl_vercel.py``'s injected ``fetcher``); every subprocess spawn is
exercised through an injected ``popen`` callable.

Coverage:
  * ``slugify`` / ``default_repo_name`` — deterministic, collision-safe naming.
  * ``stage_source`` — copies generated files to a stable evidence-root path.
  * ``ensure_repo`` — reuses an existing repo (200) vs creates one (404 -> POST),
    NEVER deletes/force-overwrites.
  * ``put_file`` — create path (no prior sha) vs update path (existing sha sent).
  * ``run_archive_task`` — success writes a created/reused receipt with
    verify.ok True; any exception writes a 'failed' receipt with an error
    message, and NEVER raises past the function.
  * ``archive_async`` — no evidence_root => skipped; no token => honest
    'failed' receipt (not raised); happy path stages source + writes task.json
    + calls the injected popen with a command containing --run-task, and
    returns immediately (never blocks on the popen call actually finishing).

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_github_archive.py -v
"""
from __future__ import annotations

import json
import os
import sys
import types

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_github_archive as gha
import ghl_receipts


# ── Naming ────────────────────────────────────────────────────────────────────

class TestNaming:
    def test_default_repo_name_deterministic(self):
        n1 = gha.default_repo_name("zhc-acme-landing", "MARKER-1")
        n2 = gha.default_repo_name("zhc-acme-landing", "MARKER-1")
        assert n1 == n2

    def test_default_repo_name_differs_by_marker(self):
        n1 = gha.default_repo_name("zhc-acme-landing", "MARKER-1")
        n2 = gha.default_repo_name("zhc-acme-landing", "MARKER-2")
        assert n1 != n2

    def test_slugify_strips_unsafe_chars(self):
        assert gha.slugify("Zhc Acme Landing!!") == "zhc-acme-landing"
        assert gha.slugify("") == "page"


# ── Token resolution ──────────────────────────────────────────────────────────

class TestTokenResolution:
    def test_gh_token_wins_first(self):
        tok = gha.resolve_github_token({"GH_TOKEN": "a", "GITHUB_TOKEN": "b"})
        assert tok == "a"

    def test_falls_back_to_github_token(self):
        tok = gha.resolve_github_token({"GITHUB_TOKEN": "b"})
        assert tok == "b"

    def test_raises_when_absent(self):
        with pytest.raises(gha.GithubTokenError):
            gha.resolve_github_token({})


# ── Staging (local disk only) ─────────────────────────────────────────────────

class TestStageSource:
    def test_copies_files_to_stable_path(self, tmp_path):
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "index.html").write_text("<html>hi</html>")
        (project_dir / "vercel.json").write_text("{}")

        evidence_root = str(tmp_path / "evidence")
        src_dir = gha.stage_source(str(project_dir), evidence_root, "MARKER-STAGE")

        assert os.path.isfile(os.path.join(src_dir, "index.html"))
        assert os.path.isfile(os.path.join(src_dir, "vercel.json"))
        # Stable path is under the evidence root, not the (possibly ephemeral)
        # project_dir.
        assert evidence_root in src_dir


# ── ensure_repo / put_file (mocked GitHub REST) ───────────────────────────────

class TestEnsureRepo:
    def test_reuses_existing_repo_never_recreates(self):
        calls = []

        def fake_req(method, url, body, token):
            calls.append((method, url))
            if method == "GET":
                return 200, {"full_name": "owner/existing-repo", "html_url": "https://github.com/owner/existing-repo"}
            raise AssertionError("must not POST when repo already exists")

        repo, created = gha.ensure_repo("owner", "existing-repo", "tok", requester=fake_req)
        assert created is False
        assert repo["full_name"] == "owner/existing-repo"
        # Only a GET was made — no create call.
        assert all(m == "GET" for m, _ in calls)

    def test_creates_repo_on_404(self):
        calls = []

        def fake_req(method, url, body, token):
            calls.append((method, url))
            if method == "GET":
                return 404, {"message": "Not Found"}
            if method == "POST" and url.endswith("/user/repos"):
                assert body["name"] == "new-repo"
                return 201, {"full_name": "owner/new-repo", "html_url": "https://github.com/owner/new-repo"}
            raise AssertionError(f"unexpected call {method} {url}")

        repo, created = gha.ensure_repo("owner", "new-repo", "tok", requester=fake_req)
        assert created is True
        assert repo["full_name"] == "owner/new-repo"

    def test_unexpected_status_raises(self):
        def fake_req(method, url, body, token):
            return 500, {"message": "boom"}

        with pytest.raises(gha.GithubArchiveError):
            gha.ensure_repo("owner", "repo", "tok", requester=fake_req)


class TestPutFile:
    def test_create_path_no_prior_sha(self):
        seen_bodies = []

        def fake_req(method, url, body, token):
            if method == "GET":
                return 404, {"message": "Not Found"}
            if method == "PUT":
                seen_bodies.append(body)
                return 201, {"content": {"sha": "newsha"}}
            raise AssertionError((method, url))

        gha.put_file("owner", "repo", "index.html", b"<html></html>", "msg", "tok", requester=fake_req)
        assert "sha" not in seen_bodies[0]

    def test_update_path_sends_existing_sha(self):
        seen_bodies = []

        def fake_req(method, url, body, token):
            if method == "GET":
                return 200, {"sha": "oldsha123"}
            if method == "PUT":
                seen_bodies.append(body)
                return 200, {"content": {"sha": "updatedsha"}}
            raise AssertionError((method, url))

        gha.put_file("owner", "repo", "index.html", b"<html>v2</html>", "msg", "tok", requester=fake_req)
        assert seen_bodies[0]["sha"] == "oldsha123"


# ── run_archive_task (the unit the detached subprocess AND retry both call) ──

class TestRunArchiveTask:
    def _good_requester(self):
        def fake_req(method, url, body, token):
            if method == "GET" and url.endswith("/user"):
                return 200, {"login": "fake-owner"}
            if method == "GET" and "/repos/" in url and "/contents/" not in url:
                return 404, {}
            if method == "POST" and url.endswith("/user/repos"):
                return 201, {"full_name": "fake-owner/zhc-page-x",
                              "html_url": "https://github.com/fake-owner/zhc-page-x"}
            if method == "GET" and "/contents/" in url:
                return 404, {}
            if method == "PUT" and "/contents/" in url:
                return 201, {}
            raise AssertionError((method, url))
        return fake_req

    def test_success_writes_created_receipt(self, tmp_path):
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "index.html").write_text("<html>ok</html>")
        evidence_root = str(tmp_path / "evidence")
        src_dir = gha.stage_source(str(project_dir), evidence_root, "M-OK")

        task = {"marker": "M-OK", "src_dir": src_dir, "evidence_root": evidence_root,
                "deployment_url": "https://x.vercel.app", "project_name": "zhc-x"}
        result = gha.run_archive_task(task, requester=self._good_requester(),
                                       env={"GH_TOKEN": "tok"})
        assert result["receipt"]["action"] in ("created", "reused")
        assert result["receipt"]["verify"]["ok"] is True
        assert os.path.isfile(result["receipt_path"])

        summ = ghl_receipts.reduce_receipts(evidence_root)
        assert "vercel_github_archive:M-OK" in summ["created"] + summ["reused"]

    def test_no_token_writes_failed_receipt_never_raises(self, tmp_path):
        evidence_root = str(tmp_path / "evidence")
        task = {"marker": "M-NOTOK", "src_dir": str(tmp_path), "evidence_root": evidence_root,
                "deployment_url": "https://x.vercel.app", "project_name": "zhc-x"}
        result = gha.run_archive_task(task, requester=self._good_requester(), env={})
        assert result["receipt"]["action"] == "failed"
        assert "token" in result["receipt"]["error"].lower()

    def test_network_error_writes_failed_receipt_never_raises(self, tmp_path):
        def boom(method, url, body, token):
            raise RuntimeError("simulated network failure")

        evidence_root = str(tmp_path / "evidence")
        task = {"marker": "M-BOOM", "src_dir": str(tmp_path), "evidence_root": evidence_root,
                "deployment_url": "https://x.vercel.app", "project_name": "zhc-x"}
        result = gha.run_archive_task(task, requester=boom, env={"GH_TOKEN": "tok"})
        assert result["receipt"]["action"] == "failed"
        assert "simulated network failure" in result["receipt"]["error"]


# ── archive_async (the non-blocking entry point run_pipeline calls) ──────────

class TestArchiveAsync:
    def _fake_project_and_deployment(self, project_dir):
        return (types.SimpleNamespace(project_dir=project_dir),
                types.SimpleNamespace(url="https://x.vercel.app"))

    def test_no_evidence_root_skips(self, tmp_path):
        project, deployment = self._fake_project_and_deployment(str(tmp_path))
        result = gha.archive_async(project, deployment, "M-SKIP", "", env={"GH_TOKEN": "x"})
        assert result["status"] == "skipped"

    def test_no_token_records_failed_receipt_not_exception(self, tmp_path):
        project, deployment = self._fake_project_and_deployment(str(tmp_path))
        evidence_root = str(tmp_path / "evidence")
        result = gha.archive_async(project, deployment, "M-NOTOKEN", evidence_root, env={})
        assert result["status"] == "failed"
        summ = ghl_receipts.reduce_receipts(evidence_root)
        assert "vercel_github_archive:M-NOTOKEN" in summ["failed"]

    def test_happy_path_spawns_detached_and_returns_immediately(self, tmp_path):
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "index.html").write_text("<html>ok</html>")
        (project_dir / "vercel.json").write_text("{}")

        project, deployment = self._fake_project_and_deployment(str(project_dir))
        evidence_root = str(tmp_path / "evidence")

        spawned = []

        def fake_popen(cmd, log_path):
            spawned.append(cmd)

        result = gha.archive_async(project, deployment, "M-SPAWN", evidence_root,
                                    project_name="zhc-spawn-test",
                                    env={"GH_TOKEN": "x"}, popen=fake_popen)
        assert result["status"] == "spawned"
        assert spawned, "the injected popen must have been invoked"
        assert "--run-task" in spawned[0]
        assert os.path.isfile(result["task_path"])

        # No archive receipt yet — the (mocked) subprocess never actually ran.
        # This is the expected shape: archive_async returns before the real
        # work completes (that's the whole point of "non-blocking").
        summ = ghl_receipts.reduce_receipts(evidence_root)
        assert "vercel_github_archive:M-SPAWN" not in summ["created"] + summ["reused"] + summ["failed"]

    def test_spawn_failure_records_failed_receipt_not_exception(self, tmp_path):
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "index.html").write_text("<html>ok</html>")

        project, deployment = self._fake_project_and_deployment(str(project_dir))
        evidence_root = str(tmp_path / "evidence")

        def failing_popen(cmd, log_path):
            raise OSError("simulated fork failure")

        result = gha.archive_async(project, deployment, "M-SPAWNFAIL", evidence_root,
                                    env={"GH_TOKEN": "x"}, popen=failing_popen)
        assert result["status"] == "failed"
        summ = ghl_receipts.reduce_receipts(evidence_root)
        assert "vercel_github_archive:M-SPAWNFAIL" in summ["failed"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
