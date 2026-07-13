"""MOCK-only unit tests — ghl_github_reconcile (reconciliation sweep proving a
VERCEL_EMBED page's code actually landed in GitHub, per SKILL.md's
Reconciliation section).

These tests are MOCK-ONLY. No live GitHub call, no real subprocess. Every
receipt is a real ``ghl_receipts`` file written to a tmp evidence root
(read/write flows are exercised for real); GitHub network calls, when a retry
needs one, go through an injected ``requester``.

Coverage:
  * No ``vercel_deploy`` receipts at all -> report is clean (nothing to check).
  * A deploy with a verified archive receipt -> counted archived_ok.
  * A deploy with NO archive receipt, retry=False -> counted missing_or_failed,
    NOT retried (retry is opt-in).
  * A deploy with NO archive receipt, retry=True, staged source present ->
    retried_ok (archive actually performed via the injected requester).
  * A deploy with NO archive receipt, retry=True, NO staged source -> flagged
    (reconciliation must never fabricate source code).
  * A deploy with a FAILED archive receipt -> treated as missing, retried the
    same as a fully-absent one.
  * CLI exit code: 0 when the report is all_clean, 1 otherwise.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_github_reconcile.py -v
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_receipts
import ghl_github_archive as gha
import ghl_github_reconcile as rec


def _write_deploy(evidence_root, marker, *, ok=True):
    ghl_receipts.write_receipt(evidence_root, ghl_receipts.make_receipt(
        gha.DEPLOY_RECEIPT_TYPE, marker, "created", response_id=f"dpl_{marker}",
        verify={"ok": ok}))


def _write_archive_ok(evidence_root, marker):
    ghl_receipts.write_receipt(evidence_root, ghl_receipts.make_receipt(
        gha.ARCHIVE_RECEIPT_TYPE, marker, "created", response_id=f"owner/repo-{marker}",
        verify={"ok": True, "repo_url": f"https://github.com/owner/repo-{marker}"}))


def _write_archive_failed(evidence_root, marker):
    ghl_receipts.write_receipt(evidence_root, ghl_receipts.make_receipt(
        gha.ARCHIVE_RECEIPT_TYPE, marker, "failed", error="simulated prior failure"))


def _good_requester():
    def fake_req(method, url, body, token):
        if method == "GET" and url.endswith("/user"):
            return 200, {"login": "fake-owner"}
        if method == "GET" and "/repos/" in url and "/contents/" not in url:
            return 404, {}
        if method == "POST" and url.endswith("/user/repos"):
            return 201, {"full_name": "fake-owner/repo", "html_url": "https://github.com/fake-owner/repo"}
        if method == "GET" and "/contents/" in url:
            return 404, {}
        if method == "PUT" and "/contents/" in url:
            return 201, {}
        raise AssertionError((method, url))
    return fake_req


def _stage(evidence_root, marker, tmp_path):
    src = tmp_path / f"src-{marker}"
    src.mkdir()
    (src / "index.html").write_text(f"<html>{marker}</html>")
    staged = gha.stage_source(str(src), evidence_root, marker)
    gha.write_task_file(evidence_root, marker, {
        "marker": marker, "src_dir": staged, "evidence_root": evidence_root,
        "deployment_url": "https://x.vercel.app", "project_name": "zhc-x",
    })


class TestReconcile:
    def test_empty_evidence_root_is_clean(self, tmp_path):
        report = rec.reconcile(str(tmp_path))
        assert report.total_deploys == 0
        assert report.all_clean() is True

    def test_fully_archived_page_counted_ok(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-A")
        _write_archive_ok(er, "PAGE-A")
        report = rec.reconcile(er)
        assert report.archived_ok == ["PAGE-A"]
        assert report.all_clean() is True

    def test_missing_archive_without_retry_is_flagged_missing(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-B")
        report = rec.reconcile(er, retry=False)
        assert report.missing_or_failed == ["PAGE-B"]
        assert report.retried_ok == []
        assert report.all_clean() is False

    def test_missing_archive_with_retry_and_staged_source_recovers(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-C")
        _stage(er, "PAGE-C", tmp_path)
        report = rec.reconcile(er, retry=True, requester=_good_requester(), env={"GH_TOKEN": "x"})
        assert report.retried_ok == ["PAGE-C"]
        assert report.missing_or_failed == []
        assert report.all_clean() is True

    def test_missing_archive_with_retry_but_no_staged_source_is_flagged(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-D")
        report = rec.reconcile(er, retry=True, requester=_good_requester(), env={"GH_TOKEN": "x"})
        assert report.retried_ok == []
        assert len(report.flagged) == 1
        assert report.flagged[0]["marker"] == "PAGE-D"
        assert "task.json" in report.flagged[0]["reason"] or "staged" in report.flagged[0]["reason"]
        assert report.all_clean() is False

    def test_malformed_task_json_is_flagged_not_a_crash(self, tmp_path, monkeypatch):
        """A corrupt/incomplete task.json (e.g. hand-edited, or written by a
        future bug) must never abort the whole sweep — it's flagged for that
        one page and reconciliation continues."""
        er = str(tmp_path)
        _write_deploy(er, "PAGE-BADTASK")
        # Stage a task.json missing a required key ('src_dir').
        task_dir = os.path.join(er, gha.ARCHIVE_SUBDIR, "PAGE-BADTASK")
        os.makedirs(task_dir, exist_ok=True)
        import json
        with open(os.path.join(task_dir, "task.json"), "w") as fh:
            json.dump({"marker": "PAGE-BADTASK", "evidence_root": er}, fh)  # no src_dir

        report = rec.reconcile(er, retry=True, requester=_good_requester(), env={"GH_TOKEN": "x"})
        assert report.retried_ok == []
        assert any(f["marker"] == "PAGE-BADTASK" for f in report.flagged)

    def test_failed_archive_receipt_treated_as_missing_and_can_be_retried(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-E")
        _write_archive_failed(er, "PAGE-E")
        _stage(er, "PAGE-E", tmp_path)
        report = rec.reconcile(er, retry=True, requester=_good_requester(), env={"GH_TOKEN": "x"})
        assert report.retried_ok == ["PAGE-E"]

    def test_retry_that_still_fails_stays_missing_or_failed(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-F")
        _stage(er, "PAGE-F", tmp_path)

        def boom(method, url, body, token):
            raise RuntimeError("still broken")

        report = rec.reconcile(er, retry=True, requester=boom, env={"GH_TOKEN": "x"})
        assert "PAGE-F" in report.missing_or_failed
        assert report.retried_ok == []

    def test_mixed_report_is_not_all_clean(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "OK-1")
        _write_archive_ok(er, "OK-1")
        _write_deploy(er, "MISSING-1")
        report = rec.reconcile(er)
        assert report.total_deploys == 2
        assert report.archived_ok == ["OK-1"]
        assert report.missing_or_failed == ["MISSING-1"]
        assert report.all_clean() is False


class TestCLI:
    def test_cli_exits_zero_when_clean(self, tmp_path, capsys):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-OK")
        _write_archive_ok(er, "PAGE-OK")
        rc = rec.main(["--evidence-root", er, "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        assert '"all_clean": true' in out

    def test_cli_exits_nonzero_when_dirty(self, tmp_path, capsys):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-MISSING")
        rc = rec.main(["--evidence-root", er, "--json"])
        assert rc == 1
        out = capsys.readouterr().out
        assert '"all_clean": false' in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
