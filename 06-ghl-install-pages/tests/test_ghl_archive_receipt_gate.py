"""MOCK-only unit tests — ghl_archive_receipt_gate (U24/B-U10 item 3: the
FAB-QC archive-receipt presence gate wired into qc-built-funnel.sh).

No live GitHub call, no real subprocess, no network of any kind — every
receipt is a real ``ghl_receipts`` file written to a tmp evidence root.

Coverage (each one is a direct proof of a B-U10 BINARY acceptance criterion
or module-level design rule):
  * No VERCEL_EMBED deploy in evidence at all -> N/A, passed (the vast
    majority of non-VERCEL_EMBED builds are a clean no-op here).
  * A deploy with a verified archive receipt -> ok, passed.
  * A deploy with NO archive receipt of any kind -> missing, NOT passed
    (acceptance (c): "FAB-QC flags a VERCEL_EMBED evidence root with no
    archive receipt").
  * A deploy with an honest FAILED archive receipt -> failed_open, STILL
    passed (the non-blocking D6/B-D2 doctrine: never gate a build over a
    transient archive failure that the reconcile sweep will retry).
  * Mixed evidence roots classify every marker independently.
  * Token presence is reported by NAME only and never leaks a value.
  * CLI --gate exit codes; --json shape; --selftest.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_archive_receipt_gate.py -v
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
import ghl_archive_receipt_gate as gate


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


class TestCheckNotApplicable:
    def test_empty_evidence_root_is_not_applicable(self, tmp_path):
        result = gate.check(str(tmp_path))
        assert result["applicable"] is False
        assert result["passed"] is True
        assert result["total_deploys"] == 0

    def test_no_evidence_root_string_is_not_applicable(self):
        result = gate.check("")
        assert result["applicable"] is False
        assert result["passed"] is True

    def test_non_deploy_receipts_only_is_not_applicable(self, tmp_path):
        er = str(tmp_path)
        ghl_receipts.write_receipt(er, ghl_receipts.make_receipt(
            "some_other_object", "X1", "created", verify={"ok": True}))
        result = gate.check(er)
        assert result["applicable"] is False
        assert result["passed"] is True


class TestCheckVerifiedArchive:
    def test_deploy_with_verified_archive_passes(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-A")
        _write_archive_ok(er, "PAGE-A")
        result = gate.check(er)
        assert result["applicable"] is True
        assert result["ok"] == ["PAGE-A"]
        assert result["failed_open"] == []
        assert result["missing"] == []
        assert result["passed"] is True


class TestCheckMissingReceiptFlags:
    """B-U10 acceptance (c): FAB-QC flags a VERCEL_EMBED evidence root with
    no archive receipt at all."""

    def test_deploy_with_no_archive_receipt_at_all_flags_missing(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-B")
        result = gate.check(er)
        assert result["applicable"] is True
        assert result["missing"] == ["PAGE-B"]
        assert result["ok"] == []
        assert result["failed_open"] == []
        assert result["passed"] is False


class TestCheckHonestFailureIsNonBlocking:
    """D6/B-D2 non-blocking doctrine: a present-but-failed archive receipt
    must NEVER fail this gate — only total silence does."""

    def test_deploy_with_failed_archive_receipt_is_non_blocking(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-C")
        _write_archive_failed(er, "PAGE-C")
        result = gate.check(er)
        assert result["failed_open"] == ["PAGE-C"]
        assert result["missing"] == []
        assert result["passed"] is True


class TestCheckMixed:
    def test_mixed_markers_classified_independently(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "OK-1")
        _write_archive_ok(er, "OK-1")
        _write_deploy(er, "FAILED-1")
        _write_archive_failed(er, "FAILED-1")
        _write_deploy(er, "MISSING-1")

        result = gate.check(er)
        assert result["total_deploys"] == 3
        assert result["ok"] == ["OK-1"]
        assert result["failed_open"] == ["FAILED-1"]
        assert result["missing"] == ["MISSING-1"]
        assert result["passed"] is False   # the missing one alone fails the gate


class TestTokenPresenceWiring:
    def test_token_presence_reachable_and_name_only(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "a-real-secret-value-must-not-leak")
        report = gha.token_presence()
        assert report["GH_TOKEN"] == "SET"
        assert "a-real-secret-value-must-not-leak" not in json.dumps(report)


class TestCLI:
    def test_gate_flag_exits_nonzero_on_missing(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-D")
        rc = gate.main(["--evidence-root", er, "--gate", "--json"])
        assert rc == 1

    def test_gate_flag_exits_zero_on_verified(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-E")
        _write_archive_ok(er, "PAGE-E")
        rc = gate.main(["--evidence-root", er, "--gate", "--json"])
        assert rc == 0

    def test_gate_flag_exits_zero_on_honest_failure(self, tmp_path):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-F")
        _write_archive_failed(er, "PAGE-F")
        rc = gate.main(["--evidence-root", er, "--gate", "--json"])
        assert rc == 0

    def test_without_gate_flag_always_exits_zero(self, tmp_path):
        """Without --gate the tool is report-only (no build-quality opinion) —
        the caller (qc-built-funnel.sh) always passes --gate explicitly."""
        er = str(tmp_path)
        _write_deploy(er, "PAGE-G")
        rc = gate.main(["--evidence-root", er, "--json"])
        assert rc == 0

    def test_json_output_includes_token_presence_never_a_value(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("GH_TOKEN", "super-secret-do-not-print-EF12")
        er = str(tmp_path)
        _write_deploy(er, "PAGE-H")
        _write_archive_ok(er, "PAGE-H")
        gate.main(["--evidence-root", er, "--json"])
        out = capsys.readouterr().out
        assert "super-secret-do-not-print-EF12" not in out
        data = json.loads(out)
        assert data["token_presence"]["GH_TOKEN"] == "SET"

    def test_human_output_shows_flag_line_for_missing(self, tmp_path, capsys):
        er = str(tmp_path)
        _write_deploy(er, "PAGE-I")
        gate.main(["--evidence-root", er])
        out = capsys.readouterr().out
        assert "FLAG" in out
        assert "PAGE-I" in out

    def test_missing_evidence_root_arg_errors(self):
        with pytest.raises(SystemExit):
            gate.main([])

    def test_selftest_passes(self):
        assert gate.main(["--selftest"]) == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
