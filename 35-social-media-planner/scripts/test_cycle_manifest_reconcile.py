#!/usr/bin/env python3
"""test_cycle_manifest_reconcile.py — U100: Skill 35's cycle-manifest variant
of the producer-reconcile pattern.

Fixture-driven, stdlib-only, zero network. Proves the SAME BINARY acceptance
criteria the "mc_board six" reconcile proves (see
49-signature-funnel/scripts/test_mc_board_reconcile.py), generalized to
Skill 35's `cycle-manifest.json` + `cc_board_attempt` shape:

  (a) a deliberately-suppressed ingest fixture (mc_token_resolved=False, i.e.
      MC_API_TOKEN unresolved / MISSION_CONTROL_URL unreachable) is surfaced
      as DRIFT by ONE reconcile() pass.
  (b) a clean run reports zero drift across 3 consecutive probes.
  (c) reconcile() never mutates a client surface: read-only, idempotent — a
      fixture's mtimes and byte content are provably unchanged after 3 passes.

Run:  python3 test_cycle_manifest_reconcile.py     (verbose unittest)
Exit: 0 = the reconcile contract holds; non-zero = a regression.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cycle_manifest_reconcile as cmr  # noqa: E402


def _base_manifest(run_id="20260716-000000-1"):
    return {
        "skill": "35-social-media-planner",
        "skill_version": "v10.14.33",
        "run_id": run_id,
        "created_at": "2026-07-16T00:00:00Z",
        "topic": "test topic",
        "platforms": ["linkedin"],
        "schedule": "auto",
        "workdir": "/tmp/whatever",
        "phases": [],
    }


def _clean_manifest(run_id="run-clean", task_id="TASK-1"):
    m = _base_manifest(run_id)
    m["cc_task_id"] = task_id
    m["cc_board_attempt"] = {"mc_token_resolved": True, "ok": True, "task_id": task_id}
    return m


def _suppressed_manifest(run_id="run-suppressed"):
    """A deliberately-suppressed ingest fixture: MC_API_TOKEN could not be
    resolved / MISSION_CONTROL_URL was unreachable for this cycle. This is
    B-U13's exact scenario generalized to Skill 35."""
    m = _base_manifest(run_id)
    m["cc_board_attempt"] = {"mc_token_resolved": False, "ok": False, "task_id": None}
    return m


def _failed_manifest(run_id="run-failed"):
    m = _base_manifest(run_id)
    m["cc_board_attempt"] = {"mc_token_resolved": True, "ok": False, "task_id": None}
    return m


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class ResolveStateDirTests(unittest.TestCase):
    def test_explicit_env_override_wins(self):
        env = {"SKILL35_EVIDENCE_BASE_DIR": "/explicit/path", "HOME": "/home/x"}
        self.assertEqual(cmr.resolve_state_dir(env), "/explicit/path")

    def test_derives_default_from_home(self):
        env = {"HOME": "/home/x"}
        self.assertEqual(
            cmr.resolve_state_dir(env), "/home/x/.openclaw/data/skill-35/runs"
        )

    def test_empty_when_no_home_and_no_override(self):
        self.assertEqual(cmr.resolve_state_dir({}), "")


class ListEvidenceRunsTests(unittest.TestCase):
    def test_missing_base_dir_returns_empty(self):
        self.assertEqual(cmr.list_evidence_runs("/does/not/exist"), [])

    def test_lists_immediate_subdirs_only(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "run-a").mkdir()
            (base / "run-b").mkdir()
            (base / "stray.txt").write_text("x")
            runs = cmr.list_evidence_runs(str(base))
            self.assertEqual(sorted(os.path.basename(r) for r in runs), ["run-a", "run-b"])


class ReconcileClassificationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _manifest_path(self, run_id):
        return self.base / run_id / "cycle-manifest.json"

    def test_not_applicable_when_base_dir_absent(self):
        report = cmr.reconcile(str(self.base / "nope"))
        self.assertFalse(report.applicable)
        self.assertTrue(report.all_clean())

    def test_no_manifest_is_unwired_not_drift(self):
        (self.base / "run-empty").mkdir()
        report = cmr.reconcile(str(self.base))
        self.assertEqual(report.unwired, ["run-empty"])
        self.assertEqual(report.drift, [])
        self.assertEqual(report.total_runs, 0)

    def test_pre_u100_manifest_without_attempt_field_is_unwired(self):
        """A manifest written before this unit shipped (no cc_board_attempt
        at all) must be treated as unwired/informational — never drift."""
        _write(self._manifest_path("run-legacy"), _base_manifest("run-legacy"))
        report = cmr.reconcile(str(self.base))
        self.assertEqual(report.unwired, ["run-legacy"])
        self.assertEqual(report.drift, [])

    def test_clean_manifest_lands_in_clean_bucket(self):
        _write(self._manifest_path("run-clean"), _clean_manifest("run-clean"))
        report = cmr.reconcile(str(self.base))
        self.assertEqual(report.clean, ["run-clean"])
        self.assertEqual(report.drift, [])
        self.assertEqual(report.total_runs, 1)
        self.assertTrue(report.all_clean())

    def test_suppressed_ingest_fixture_is_surfaced_as_drift(self):
        """BINARY acceptance (a): a deliberately-suppressed ingest fixture is
        surfaced within ONE reconcile() pass."""
        _write(self._manifest_path("run-suppressed"), _suppressed_manifest("run-suppressed"))
        report = cmr.reconcile(str(self.base))
        self.assertEqual(len(report.drift), 1)
        self.assertEqual(report.drift[0]["run"], "run-suppressed")
        self.assertIn("unresolved", report.drift[0]["reason"])
        self.assertFalse(report.all_clean())

    def test_failed_ingest_is_drift(self):
        _write(self._manifest_path("run-failed"), _failed_manifest("run-failed"))
        report = cmr.reconcile(str(self.base))
        self.assertEqual(len(report.drift), 1)
        self.assertEqual(report.drift[0]["run"], "run-failed")

    def test_mixed_fixture_classifies_every_run_independently(self):
        _write(self._manifest_path("run-clean"), _clean_manifest("run-clean", "TASK-A"))
        _write(self._manifest_path("run-suppressed"), _suppressed_manifest("run-suppressed"))
        (self.base / "run-legacy-empty").mkdir()
        report = cmr.reconcile(str(self.base))
        self.assertEqual(report.clean, ["run-clean"])
        self.assertEqual([d["run"] for d in report.drift], ["run-suppressed"])
        self.assertEqual(report.unwired, ["run-legacy-empty"])
        self.assertEqual(report.total_runs, 2)

    def test_clean_run_zero_drift_across_three_consecutive_probes(self):
        """BINARY acceptance (b): a clean run reports zero drift across 3
        consecutive probes."""
        _write(self._manifest_path("run-clean"), _clean_manifest("run-clean"))
        for _ in range(3):
            report = cmr.reconcile(str(self.base))
            self.assertEqual(report.drift, [])
            self.assertTrue(report.all_clean())

    def test_reconcile_never_mutates_the_evidence_tree(self):
        """BINARY acceptance (c): no reconcile ever mutates a client surface
        — read-only sweep, 3 consecutive passes leave every manifest
        byte-identical."""
        _write(self._manifest_path("run-clean"), _clean_manifest("run-clean"))
        _write(self._manifest_path("run-suppressed"), _suppressed_manifest("run-suppressed"))
        before = {p: p.read_bytes() for p in sorted(self.base.rglob("*")) if p.is_file()}
        before_names = sorted(str(p.relative_to(self.base)) for p in self.base.rglob("*"))

        for _ in range(3):
            cmr.reconcile(str(self.base))

        after_names = sorted(str(p.relative_to(self.base)) for p in self.base.rglob("*"))
        self.assertEqual(before_names, after_names, "reconcile created/removed files")
        for p, content in before.items():
            self.assertEqual(p.read_bytes(), content, f"reconcile mutated {p}")

    def test_malformed_manifest_json_is_unwired_not_a_crash(self):
        p = self._manifest_path("run-bad-json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not valid json", encoding="utf-8")
        report = cmr.reconcile(str(self.base))
        self.assertEqual(report.unwired, ["run-bad-json"])
        self.assertEqual(report.drift, [])


class ReconcileCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_json_output_and_always_exits_zero_with_drift(self):
        _write(
            self.base / "run-suppressed" / "cycle-manifest.json",
            _suppressed_manifest("run-suppressed"),
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cmr._reconcile_cli(["--base-dir", str(self.base), "--json"])
        self.assertEqual(rc, 0)  # non-gating — ALWAYS exit 0, even with drift
        printed = json.loads(out.getvalue())
        self.assertFalse(printed["all_clean"])
        self.assertEqual(len(printed["drift"]), 1)

    def test_cli_exits_zero_when_clean(self):
        _write(self.base / "run-clean" / "cycle-manifest.json", _clean_manifest("run-clean"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cmr._reconcile_cli(["--base-dir", str(self.base), "--json"])
        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertTrue(printed["all_clean"])

    def test_main_routes_reconcile_subcommand(self):
        _write(self.base / "run-clean" / "cycle-manifest.json", _clean_manifest("run-clean"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cmr.main(["reconcile", "--base-dir", str(self.base), "--json"])
        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertTrue(printed["all_clean"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
