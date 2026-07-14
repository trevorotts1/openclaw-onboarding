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

import json
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

    def test_cli_requires_one_of_evidence_root_or_sweep_base(self):
        with pytest.raises(SystemExit):
            rec.main([])

    def test_cli_rejects_both_evidence_root_and_sweep_base(self, tmp_path):
        with pytest.raises(SystemExit):
            rec.main(["--evidence-root", str(tmp_path), "--sweep-base", str(tmp_path)])


# ── U24/B-U10 item 2 — the daily maintenance-window multi-root sweep ─────────

class TestSweepBase:
    def _seed_run(self, base_dir, run_id, tmp_path):
        """Build one v2-<RUN_ID> evidence run with an intake receipt (the
        cc_board.list_evidence_runs discovery signal) under base_dir."""
        run_dir = os.path.join(base_dir, run_id)
        os.makedirs(os.path.join(run_dir, "routing"), exist_ok=True)
        with open(os.path.join(run_dir, "routing", "intake-receipt.json"), "w") as fh:
            fh.write("{}")
        return run_dir

    def test_missing_base_dir_is_not_applicable_and_is_not_an_alarm(self, tmp_path):
        """U24 rebuild fix: a fresh/absent evidence base (the NORMAL state for
        any fleet box that has never run a Skill-6 build) must be honestly
        'not applicable', which is NOT the same thing as 'attention needed'.
        The prior build conflated the two (``all_clean()`` returned False for
        ``applicable=False``), which made the CLI print RESULT: ATTENTION
        NEEDED and exit 1 on every never-built box, every night. Proof this
        is a real behavior change, not a tautology: reverting SweepReport
        .all_clean() to `return self.applicable and all(...)` makes this
        assertion fail (reproduced by hand before this fix: `assert
        report.all_clean() is False` was the PRIOR passing assertion here)."""
        report = rec.sweep_base(str(tmp_path / "does-not-exist"), write_log=False)
        assert report.applicable is False
        assert report.all_clean() is True          # <-- the actual bug fix
        assert report.total_runs == 0

    def test_missing_base_dir_cli_exits_zero_and_does_not_say_attention(self, tmp_path, capsys):
        """Same fix, proven at the CLI boundary a real cron invocation hits."""
        missing = str(tmp_path / "does-not-exist")
        rc = rec.main(["--sweep-base", missing, "--retry"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "ATTENTION NEEDED" not in out
        assert "N/A" in out

    def test_bare_sweep_base_flag_auto_resolves_via_cc_board(self, tmp_path, monkeypatch):
        """Fixes the false claim that sweep_base 'reuses the canonical
        evidence-root resolver' — it previously only reused
        cc_board.list_evidence_runs, never cc_board.resolve_evidence_base,
        so a scheduled sweep pointed at a literal path silently ignored the
        SKILL6_EVIDENCE_BASE_DIR override. Proof this is real, not a
        tautology: monkeypatch resolve_evidence_base to a distinct sentinel
        dir and assert sweep_base(None) actually used it — this assertion
        FAILS against the prior implementation (which required an explicit
        base_dir argument and never called the resolver at all; passing
        base_dir=None crashed with `not base_dir` -> applicable=False,
        report.base_dir == '', never equal to the sentinel below)."""
        sentinel = str(tmp_path / "sentinel-evidence-base")
        os.makedirs(sentinel, exist_ok=True)
        calls = []

        def fake_resolver(env=None):
            calls.append(env)
            return sentinel

        monkeypatch.setattr(rec.cc_board, "resolve_evidence_base", fake_resolver)
        report = rec.sweep_base(None, write_log=False)
        assert calls, "sweep_base(None) never called cc_board.resolve_evidence_base"
        assert report.base_dir == sentinel
        assert report.applicable is True

    def test_cli_bare_sweep_base_also_auto_resolves(self, tmp_path, monkeypatch, capsys):
        """Same proof at the CLI boundary (bare `--sweep-base`, no value —
        exactly what the scheduled cron entry passes)."""
        sentinel = str(tmp_path / "sentinel-evidence-base-cli")
        os.makedirs(sentinel, exist_ok=True)
        monkeypatch.setattr(rec.cc_board, "resolve_evidence_base", lambda env=None: sentinel)
        rc = rec.main(["--sweep-base", "--no-log"])
        out = capsys.readouterr().out
        assert rc == 0
        assert sentinel in out

    def test_empty_base_dir_no_runs_is_clean(self, tmp_path):
        base = str(tmp_path)
        report = rec.sweep_base(base, write_log=False)
        assert report.applicable is True
        assert report.total_runs == 0
        assert report.all_clean() is True

    def test_sweeps_every_run_and_aggregates(self, tmp_path):
        base = str(tmp_path)
        r1 = self._seed_run(base, "v2-RUN1", tmp_path)
        r2 = self._seed_run(base, "v2-RUN2", tmp_path)
        _write_deploy(r1, "PAGE-A")
        _write_archive_ok(r1, "PAGE-A")
        _write_deploy(r2, "PAGE-B")   # no archive receipt at all -> dirty

        report = rec.sweep_base(base, retry=False, write_log=False)
        assert report.total_runs == 2
        by_run = {r["run"]: r["report"] for r in report.runs}
        assert by_run["v2-RUN1"]["all_clean"] is True
        assert by_run["v2-RUN2"]["all_clean"] is False
        assert report.all_clean() is False

    def test_sweep_with_retry_recovers_a_run_from_staged_source(self, tmp_path):
        base = str(tmp_path)
        r1 = self._seed_run(base, "v2-RUN1", tmp_path)
        _write_deploy(r1, "PAGE-C")
        _stage(r1, "PAGE-C", tmp_path)

        report = rec.sweep_base(base, retry=True, requester=_good_requester(),
                                 env={"GH_TOKEN": "x"}, write_log=False)
        assert report.all_clean() is True
        assert report.runs[0]["report"]["retried_ok"] == ["PAGE-C"]

    def test_writes_a_dated_log_by_default(self, tmp_path):
        """B-U10 acceptance (d): 'the maintenance-window schedule entry ...
        its first run writes a dated log' — proven here at the mechanism
        level: sweep_base's own default behavior writes one timestamped JSON
        log file under <base>/github-archive-reconcile-logs/ whose content
        matches the returned report."""
        base = str(tmp_path)
        self._seed_run(base, "v2-RUN1", tmp_path)

        report = rec.sweep_base(base, clock=lambda: "20260714T040000Z")
        expected = os.path.join(base, "github-archive-reconcile-logs", "20260714T040000Z.json")
        assert report.log_path == expected
        assert os.path.isfile(expected)

        with open(expected) as fh:
            logged = json.load(fh)
        assert logged["base_dir"] == base
        assert logged["total_runs"] == 1
        assert logged["log_path"] == expected

    def test_writes_a_dated_log_even_on_a_pristine_box_with_no_evidence_yet(self, tmp_path):
        """U24 rebuild fix, the other half of acceptance (d): a box that has
        never run a Skill-6 build (resolved base dir doesn't exist yet) must
        STILL get a dated proof-of-run log on its first scheduled fire — not
        just once evidence happens to exist. Proof this is real: the log's
        own content honestly records applicable=False / total_runs=0, it
        never fabricates a run, and the CLI's exit code for this pass is 0
        (see test_missing_base_dir_cli_exits_zero_and_does_not_say_attention)."""
        base = str(tmp_path / "pristine-box-no-builds-yet")
        assert not os.path.isdir(base)

        report = rec.sweep_base(base, clock=lambda: "20260714T040000Z")
        expected = os.path.join(base, "github-archive-reconcile-logs", "20260714T040000Z.json")
        assert report.applicable is False
        assert report.log_path == expected
        assert os.path.isfile(expected)

        with open(expected) as fh:
            logged = json.load(fh)
        assert logged["applicable"] is False
        assert logged["total_runs"] == 0
        assert logged["all_clean"] is True

    def test_no_log_flag_suppresses_the_log_file(self, tmp_path):
        base = str(tmp_path)
        report = rec.sweep_base(base, write_log=False)
        assert report.log_path == ""
        assert not os.path.isdir(os.path.join(base, "github-archive-reconcile-logs"))

    def test_two_sweeps_never_overwrite_each_others_log(self, tmp_path):
        base = str(tmp_path)
        self._seed_run(base, "v2-RUN1", tmp_path)
        r1 = rec.sweep_base(base, clock=lambda: "20260714T040000Z")
        r2 = rec.sweep_base(base, clock=lambda: "20260715T040000Z")
        assert r1.log_path != r2.log_path
        assert os.path.isfile(r1.log_path)
        assert os.path.isfile(r2.log_path)

    def test_cli_sweep_base_mode_json_and_exit_code(self, tmp_path, capsys):
        base = str(tmp_path)
        r1 = self._seed_run(base, "v2-RUN1", tmp_path)
        _write_deploy(r1, "PAGE-D")
        _write_archive_ok(r1, "PAGE-D")

        rc = rec.main(["--sweep-base", base, "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["all_clean"] is True
        assert data["log_path"] and os.path.isfile(data["log_path"])

    def test_cli_sweep_base_mode_dirty_exit_code(self, tmp_path, capsys):
        base = str(tmp_path)
        r1 = self._seed_run(base, "v2-RUN1", tmp_path)
        _write_deploy(r1, "PAGE-E")   # no archive receipt

        rc = rec.main(["--sweep-base", base, "--json", "--no-log"])
        assert rc == 1
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["all_clean"] is False
        assert data["log_path"] == ""


# ── B-U10 acceptance (b) — deliberately-broken token, then restored, retries ─

class TestBrokenTokenThenRestoredRetry:
    def test_no_token_then_restored_token_retry_succeeds(self, tmp_path):
        """End-to-end round trip (not a hand-written fixture receipt): a real
        ``archive_async`` call with NO token on the box writes an honest
        FAILED F6 receipt and never raises or touches the (already-live)
        deployed page; a subsequent reconcile --retry, run once the token is
        restored, recovers it from the staged source with no fabrication."""
        import types

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "index.html").write_text("<html>live page, unaffected</html>")
        evidence_root = str(tmp_path / "evidence")

        project = types.SimpleNamespace(project_dir=str(project_dir))
        deployment = types.SimpleNamespace(url="https://x.vercel.app")

        # 1. Deliberately-broken token (none set at all) — the live page is
        #    represented by the deploy receipt below, written independently
        #    of the archive attempt: it is never touched by archive_async.
        _write_deploy(evidence_root, "PAGE-BROKEN")
        result = gha.archive_async(project, deployment, "PAGE-BROKEN", evidence_root, env={})
        assert result["status"] == "failed"
        assert "token" in result["reason"].lower()

        summ = ghl_receipts.reduce_receipts(evidence_root)
        assert "vercel_github_archive:PAGE-BROKEN" in summ["failed"]
        # The deploy object itself is untouched/unaffected by the archive failure.
        assert "vercel_deploy:PAGE-BROKEN" in summ["created"]

        # Pre-retry: reconcile without --retry reports it dirty.
        pre = rec.reconcile(evidence_root, retry=False)
        assert pre.all_clean() is False
        assert "PAGE-BROKEN" in pre.missing_or_failed

        # archive_async's own staging (which runs before the token check's
        # spawn attempt is reached) does NOT happen on the no-token path (it
        # returns before staging) — so reconcile's retry must stage nothing
        # to work with here and correctly FLAGS it (never fabricates source).
        post_no_stage = rec.reconcile(evidence_root, retry=True,
                                       requester=_good_requester(), env={"GH_TOKEN": "restored-token"})
        assert any(f["marker"] == "PAGE-BROKEN" for f in post_no_stage.flagged)

        # 2. Now prove the SAME scenario recovers when a build DID stage
        #    source (the realistic case: archive_async staged the files
        #    before the detached subprocess — which never got to run because
        #    the box's token was broken at the time the subprocess itself
        #    resolved it, e.g. a token file that got corrupted mid-run) and
        #    only the retry pass has the restored token.
        _stage(evidence_root, "PAGE-BROKEN", tmp_path)
        recovered = rec.reconcile(evidence_root, retry=True,
                                   requester=_good_requester(), env={"GH_TOKEN": "restored-token"})
        assert "PAGE-BROKEN" in recovered.retried_ok
        assert recovered.all_clean() is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
