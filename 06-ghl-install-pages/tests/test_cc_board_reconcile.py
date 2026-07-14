# test_cc_board_reconcile.py — U27 / B-U13: Skill-6 board reconcile.
#
# Clones the Anthology drift pattern (mc_board.py reconcile /
# checkAnthologyBoardProjection()) for Skill 6's fail-soft producer.
# SKILL.md:607-608 names the blindness verbatim: "cc_board.py fail-softs (the
# card just never lands / never moves) and the build continues unregistered".
#
# No network: the transport (_post_json) is monkeypatched. Every scenario is
# built from real on-disk evidence roots under tmp_path so the reconcile sweep
# exercises the exact filesystem contract v2_dispatcher / ingest_task write.
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402

BASE_URL = "https://demo.zerohumanworkforce.com"
ENV_CONFIGURED = {"MISSION_CONTROL_URL": BASE_URL}


def _make_run(base_dir, run_id, *, with_intake=True):
    """Create a v2-<run_id> evidence root, optionally with an intake receipt."""
    run_dir = os.path.join(base_dir, f"v2-{run_id}")
    routing_dir = os.path.join(run_dir, "routing")
    os.makedirs(routing_dir, exist_ok=True)
    if with_intake:
        with open(os.path.join(routing_dir, "intake-receipt.json"), "w", encoding="utf-8") as f:
            json.dump({"skipped": False, "answers": {}}, f)
    return run_dir


class TestResolveEvidenceBase:
    def test_explicit_env_override_wins(self, tmp_path):
        env = {"SKILL6_EVIDENCE_BASE_DIR": "/custom/base", "HOME": str(tmp_path)}
        assert cc_board.resolve_evidence_base(env) == "/custom/base"

    def test_falls_back_to_home_clawd_skill6_fix(self, tmp_path):
        env = {"HOME": str(tmp_path)}
        assert cc_board.resolve_evidence_base(env) == os.path.join(str(tmp_path), "clawd", "skill6-fix")

    def test_no_home_no_override_returns_empty(self):
        assert cc_board.resolve_evidence_base({}) == ""


class TestListEvidenceRuns:
    def test_missing_base_dir_returns_empty(self, tmp_path):
        assert cc_board.list_evidence_runs(str(tmp_path / "nope")) == []

    def test_only_v2_dirs_with_intake_receipt_counted(self, tmp_path):
        base = str(tmp_path)
        _make_run(base, "A", with_intake=True)
        _make_run(base, "B", with_intake=False)  # no intake receipt — excluded
        os.makedirs(os.path.join(base, "not-a-run-dir"), exist_ok=True)  # wrong prefix — excluded
        runs = cc_board.list_evidence_runs(base)
        assert len(runs) == 1
        assert os.path.basename(runs[0]) == "v2-A"


class TestIngestTaskBoardReceipt:
    """U27's closure of the SKILL.md:607-608 blindness: ingest_task(evidence_root=...)
    ALWAYS leaves an on-disk trace, whatever the outcome."""

    def test_no_evidence_root_is_byte_identical_legacy_behavior(self, tmp_path):
        # Omitting evidence_root writes nothing and behaves exactly as before.
        result = cc_board.ingest_task("Test funnel job", env={})
        assert result is None
        assert list(tmp_path.iterdir()) == []

    def test_suppressed_board_writes_drift_evidence(self, tmp_path):
        run_dir = _make_run(str(tmp_path), "SUPPRESSED")
        result = cc_board.ingest_task("Test funnel job", env={}, evidence_root=run_dir)
        assert result is None
        receipt_path = os.path.join(run_dir, "routing", "board-ingest-receipt.json")
        assert os.path.isfile(receipt_path)
        with open(receipt_path) as f:
            receipt = json.load(f)
        assert receipt["mission_control_url_set"] is False
        assert receipt["ok"] is False
        assert receipt["task_id"] is None

    def test_successful_ingest_writes_ok_receipt(self, tmp_path, monkeypatch):
        run_dir = _make_run(str(tmp_path), "OK")
        monkeypatch.setattr(
            cc_board, "_post_json",
            lambda *a, **k: (201, {"task_id": "cc-task-1", "deduped": False,
                                    "resolved_by": "web-development", "status": "backlog"}),
        )
        result = cc_board.ingest_task("Clean job", env=ENV_CONFIGURED, evidence_root=run_dir)
        assert result == "cc-task-1"
        with open(os.path.join(run_dir, "routing", "board-ingest-receipt.json")) as f:
            receipt = json.load(f)
        assert receipt["mission_control_url_set"] is True
        assert receipt["ok"] is True
        assert receipt["task_id"] == "cc-task-1"

    def test_configured_but_failed_ingest_writes_fail_receipt(self, tmp_path, monkeypatch):
        run_dir = _make_run(str(tmp_path), "FAIL")
        monkeypatch.setattr(cc_board, "_post_json", lambda *a, **k: (500, {"error": "boom"}))
        result = cc_board.ingest_task("Job", env=ENV_CONFIGURED, evidence_root=run_dir)
        assert result is None
        with open(os.path.join(run_dir, "routing", "board-ingest-receipt.json")) as f:
            receipt = json.load(f)
        assert receipt["mission_control_url_set"] is True
        assert receipt["ok"] is False
        assert receipt["task_id"] is None

    def test_receipt_write_never_raises_on_unwritable_root(self):
        # evidence_root points at something that cannot become a directory
        # (a plain file in the way of makedirs) — must still return normally.
        import tempfile
        with tempfile.NamedTemporaryFile() as tf:
            blocked_root = os.path.join(tf.name, "sub")  # tf.name is a FILE, not a dir
            result = cc_board.ingest_task("Job", env={}, evidence_root=blocked_root)
            assert result is None  # no exception raised


class TestReconcile:
    """BINARY acceptance (B-U13):
      (a) a deliberately-suppressed ingest_task (unset MISSION_CONTROL_URL for
          one fixture run) is surfaced within one health-probe cycle;
      (b) a clean run reports zero drift across 3 consecutive probes.
    """

    def test_not_provisioned_base_dir(self, tmp_path):
        report = cc_board.reconcile(str(tmp_path / "does-not-exist"))
        d = report.as_dict()
        assert d["applicable"] is False
        assert d["all_clean"] is True
        assert d["total_runs"] == 0

    def test_empty_base_dir_healthy_idle(self, tmp_path):
        os.makedirs(str(tmp_path), exist_ok=True)
        report = cc_board.reconcile(str(tmp_path))
        d = report.as_dict()
        assert d["applicable"] is True
        assert d["total_runs"] == 0
        assert d["all_clean"] is True

    def test_legacy_unwired_run_is_never_drift(self, tmp_path):
        # A run with an intake receipt but NO board-ingest receipt (pre-U27,
        # or a caller that hasn't threaded evidence_root through yet) must
        # never be reported as drift — that would turn every existing box red
        # the moment this ships.
        _make_run(str(tmp_path), "LEGACY")
        report = cc_board.reconcile(str(tmp_path))
        d = report.as_dict()
        assert d["total_runs"] == 1
        assert d["drift"] == []
        assert d["unwired"] == ["v2-LEGACY"]
        assert d["all_clean"] is True

    def test_binary_a_suppressed_ingest_surfaced_as_drift(self, tmp_path):
        run_dir = _make_run(str(tmp_path), "SUPPRESSED")
        cc_board.ingest_task("Test funnel job", env={}, evidence_root=run_dir)  # MISSION_CONTROL_URL unset

        report = cc_board.reconcile(str(tmp_path))
        d = report.as_dict()
        assert d["total_runs"] == 1
        assert len(d["drift"]) == 1
        assert d["drift"][0]["run"] == "v2-SUPPRESSED"
        assert "MISSION_CONTROL_URL" in d["drift"][0]["reason"]
        assert d["all_clean"] is False

    def test_binary_b_clean_run_zero_drift_across_three_probes(self, tmp_path, monkeypatch):
        run_dir = _make_run(str(tmp_path), "CLEAN")
        monkeypatch.setattr(
            cc_board, "_post_json",
            lambda *a, **k: (201, {"task_id": "cc-task-clean", "deduped": False,
                                    "resolved_by": "web-development", "status": "backlog"}),
        )
        cc_board.ingest_task("Clean job", env=ENV_CONFIGURED, evidence_root=run_dir)

        for _ in range(3):
            report = cc_board.reconcile(str(tmp_path))
            d = report.as_dict()
            assert d["drift"] == []
            assert d["clean"] == ["v2-CLEAN"]
            assert d["all_clean"] is True

    def test_configured_but_failed_ingest_is_drift(self, tmp_path, monkeypatch):
        run_dir = _make_run(str(tmp_path), "FAILED")
        monkeypatch.setattr(cc_board, "_post_json", lambda *a, **k: (500, {"error": "boom"}))
        cc_board.ingest_task("Job", env=ENV_CONFIGURED, evidence_root=run_dir)

        report = cc_board.reconcile(str(tmp_path))
        d = report.as_dict()
        assert len(d["drift"]) == 1
        assert d["drift"][0]["run"] == "v2-FAILED"

    def test_reconcile_is_read_only_and_idempotent(self, tmp_path):
        run_dir = _make_run(str(tmp_path), "IDEMPOTENT")
        cc_board.ingest_task("Job", env={}, evidence_root=run_dir)

        before = sorted(os.listdir(os.path.join(run_dir, "routing")))
        for _ in range(3):
            cc_board.reconcile(str(tmp_path))
        after = sorted(os.listdir(os.path.join(run_dir, "routing")))
        assert before == after  # reconcile never wrote/removed a file

    def test_base_dir_resolved_from_env_when_omitted(self, tmp_path, monkeypatch):
        base = str(tmp_path / "clawd" / "skill6-fix")
        os.makedirs(base, exist_ok=True)
        monkeypatch.setenv("SKILL6_EVIDENCE_BASE_DIR", base)
        report = cc_board.reconcile(env={"SKILL6_EVIDENCE_BASE_DIR": base})
        assert report.base_dir == base
        assert report.applicable is True


class TestReconcileCLI:
    def test_cli_json_output_exits_zero_even_with_drift(self, tmp_path, capsys):
        run_dir = _make_run(str(tmp_path), "SUPPRESSED")
        cc_board.ingest_task("Job", env={}, evidence_root=run_dir)

        rc = cc_board._reconcile_cli(["--base-dir", str(tmp_path), "--json"])
        assert rc == 0  # non-gating — ALWAYS exits 0 (mirrors mc_board.py cmd_reconcile)

        out = json.loads(capsys.readouterr().out)
        assert out["all_clean"] is False
        assert len(out["drift"]) == 1

    def test_cli_human_output_exits_zero_when_clean(self, tmp_path, capsys):
        os.makedirs(str(tmp_path), exist_ok=True)
        rc = cc_board._reconcile_cli(["--base-dir", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "RESULT: CLEAN" in out
