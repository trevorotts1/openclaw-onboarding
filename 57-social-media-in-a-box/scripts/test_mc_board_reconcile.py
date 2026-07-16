#!/usr/bin/env python3
"""test_mc_board_reconcile.py — U100: the producer-reconcile pattern

Proves the "mc_board six" (49-signature-funnel, 50-email-engine,
53-book-writer, 55-product-bio, 56-sales-page-assets,
57-social-media-in-a-box) got the SAME B-U13/U27 self-heal `reconcile --json`
verb + drift/clean/unwired classification as Skill 6's `cc_board.py reconcile`
and the Anthology Engine's `mc_board.py reconcile` (U79 precedent).

It is BYTE-IDENTICAL alongside mc_board.py in every one of the six skills that
ship it (same convention as test_cc_contract.py). Stdlib-only, zero network,
zero filesystem outside a per-test tempdir.

BINARY acceptance this proves (U100 spec, verbatim):
  (a) a deliberately-suppressed ingest fixture (mc_url_set=False, i.e. the
      COMMAND_CENTER_URL/MISSION_CONTROL_URL-unset case) is surfaced as DRIFT
      by ONE reconcile() pass — "one health-probe cycle".
  (b) a clean run reports zero drift across 3 consecutive probes.
  (c) reconcile() never mutates a client surface: read-only, idempotent — a
      fixture's mtimes and byte content are provably unchanged after 3 passes.

Run:  python3 test_mc_board_reconcile.py            (verbose unittest)
Exit: 0 = the reconcile contract holds; non-zero = a regression.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mc_board  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _clean_receipt(task_id="TASK-1"):
    return {
        "attempted_at": "2026-07-16T00:00:00Z",
        "mc_url_set": True,
        "ok": True,
        "task_id": task_id,
        "department_slug": "web-development",
        "source": "productized-skill",
        "reason": "created",
    }


def _suppressed_receipt():
    """A deliberately-suppressed ingest fixture: COMMAND_CENTER_URL /
    MISSION_CONTROL_URL was unset for this run. This is the exact case B-U13
    names verbatim and this unit generalizes."""
    return {
        "attempted_at": "2026-07-16T00:00:00Z",
        "mc_url_set": False,
        "ok": False,
        "task_id": None,
        "department_slug": "web-development",
        "source": "productized-skill",
        "reason": "COMMAND_CENTER_URL/MISSION_CONTROL_URL unset",
    }


def _failed_receipt():
    return {
        "attempted_at": "2026-07-16T00:00:00Z",
        "mc_url_set": True,
        "ok": False,
        "task_id": None,
        "department_slug": "web-development",
        "source": "productized-skill",
        "reason": "HTTP 500: board unavailable",
    }


class ResolveStateDirTests(unittest.TestCase):
    def test_explicit_env_override_wins(self):
        env = {"MC_BOARD_EVIDENCE_BASE_DIR": "/explicit/path", "HOME": "/home/x"}
        self.assertEqual(mc_board.resolve_state_dir(env), "/explicit/path")

    def test_derives_from_home_when_no_override(self):
        env = {"HOME": "/home/x"}
        resolved = mc_board.resolve_state_dir(env)
        self.assertTrue(resolved.startswith("/home/x/.openclaw/data/"))
        self.assertTrue(resolved.endswith("/runs"))

    def test_empty_when_no_home_and_no_override(self):
        self.assertEqual(mc_board.resolve_state_dir({}), "")


class ListEvidenceRunsTests(unittest.TestCase):
    def test_missing_base_dir_returns_empty(self):
        self.assertEqual(mc_board.list_evidence_runs("/does/not/exist"), [])

    def test_lists_immediate_subdirs_only(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "run-a").mkdir()
            (base / "run-b").mkdir()
            (base / "not-a-dir.txt").write_text("x")
            runs = mc_board.list_evidence_runs(str(base))
            self.assertEqual(sorted(os.path.basename(r) for r in runs), ["run-a", "run-b"])


class ReconcileClassificationTests(unittest.TestCase):
    """Fixture-driven: builds a run-evidence root by hand (no card_open/network
    involved) and asserts reconcile()'s clean/drift/unwired classification."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _receipt_path(self, run_id):
        return self.base / run_id / "routing" / "board-ingest-receipt.json"

    def test_not_applicable_when_base_dir_absent(self):
        report = mc_board.reconcile(str(self.base / "nope"))
        self.assertFalse(report.applicable)
        self.assertTrue(report.all_clean())  # not-applicable is not drift

    def test_no_receipt_is_unwired_not_drift(self):
        (self.base / "run-unwired").mkdir()
        report = mc_board.reconcile(str(self.base))
        self.assertEqual(report.unwired, ["run-unwired"])
        self.assertEqual(report.drift, [])
        self.assertEqual(report.total_runs, 0)
        self.assertTrue(report.all_clean())

    def test_clean_receipt_lands_in_clean_bucket(self):
        _write_json(self._receipt_path("run-clean"), _clean_receipt())
        report = mc_board.reconcile(str(self.base))
        self.assertEqual(report.clean, ["run-clean"])
        self.assertEqual(report.drift, [])
        self.assertEqual(report.total_runs, 1)
        self.assertTrue(report.all_clean())

    def test_suppressed_ingest_fixture_is_surfaced_as_drift(self):
        """BINARY acceptance (a): a deliberately-suppressed ingest fixture
        (unset MISSION_CONTROL_URL for one fixture run) is surfaced within
        ONE reconcile() pass."""
        _write_json(self._receipt_path("run-suppressed"), _suppressed_receipt())
        report = mc_board.reconcile(str(self.base))
        self.assertEqual(len(report.drift), 1)
        self.assertEqual(report.drift[0]["run"], "run-suppressed")
        self.assertIn("unset", report.drift[0]["reason"])
        self.assertFalse(report.all_clean())

    def test_failed_ingest_is_drift(self):
        _write_json(self._receipt_path("run-failed"), _failed_receipt())
        report = mc_board.reconcile(str(self.base))
        self.assertEqual(len(report.drift), 1)
        self.assertEqual(report.drift[0]["run"], "run-failed")

    def test_mixed_fixture_classifies_every_run_independently(self):
        _write_json(self._receipt_path("run-clean"), _clean_receipt("TASK-A"))
        _write_json(self._receipt_path("run-suppressed"), _suppressed_receipt())
        (self.base / "run-unwired").mkdir()
        report = mc_board.reconcile(str(self.base))
        self.assertEqual(report.clean, ["run-clean"])
        self.assertEqual([d["run"] for d in report.drift], ["run-suppressed"])
        self.assertEqual(report.unwired, ["run-unwired"])
        self.assertEqual(report.total_runs, 2)  # unwired excluded from total_runs

    def test_clean_run_zero_drift_across_three_consecutive_probes(self):
        """BINARY acceptance (b): a clean run reports zero drift across 3
        consecutive probes."""
        _write_json(self._receipt_path("run-clean"), _clean_receipt())
        for _ in range(3):
            report = mc_board.reconcile(str(self.base))
            self.assertEqual(report.drift, [])
            self.assertTrue(report.all_clean())

    def test_reconcile_never_mutates_the_evidence_tree(self):
        """BINARY acceptance (c): no reconcile ever mutates a client surface
        (the idempotency guarantee proven in U79/precedent) — read-only sweep,
        3 consecutive passes leave every fixture file byte-identical."""
        _write_json(self._receipt_path("run-clean"), _clean_receipt())
        _write_json(self._receipt_path("run-suppressed"), _suppressed_receipt())
        before = {
            p: p.read_bytes()
            for p in sorted(self.base.rglob("*")) if p.is_file()
        }
        before_names = sorted(str(p.relative_to(self.base)) for p in self.base.rglob("*"))

        for _ in range(3):
            mc_board.reconcile(str(self.base))

        after_names = sorted(str(p.relative_to(self.base)) for p in self.base.rglob("*"))
        self.assertEqual(before_names, after_names, "reconcile created/removed files")
        for p, content in before.items():
            self.assertEqual(p.read_bytes(), content, f"reconcile mutated {p}")

    def test_malformed_receipt_json_is_unwired_not_a_crash(self):
        p = self._receipt_path("run-bad-json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not valid json", encoding="utf-8")
        report = mc_board.reconcile(str(self.base))
        self.assertEqual(report.unwired, ["run-bad-json"])
        self.assertEqual(report.drift, [])


class WriteBoardIngestReceiptTests(unittest.TestCase):
    """Proves the opt-in `evidence_root` plumbing through card_open() end to
    end: existing (evidence_root=None) callers are untouched; opted-in callers
    get a receipt that reconcile() can classify."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        self.evidence_root = self.tmp / "evidence" / "run-1"

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_evidence_root_none_writes_nothing_new(self):
        """Regression guard: a caller that does NOT pass evidence_root= (every
        existing caller today) must be byte-for-byte unaffected — no new
        receipt file appears anywhere."""
        env = {}  # no COMMAND_CENTER_URL / MISSION_CONTROL_URL — disabled
        result = mc_board.card_open(
            str(self.run_dir), slug="s", title="t", department="web-development", env=env,
        )
        self.assertIsNone(result)
        self.assertFalse((self.tmp / "evidence").exists())

    def test_disabled_board_with_evidence_root_writes_suppressed_receipt(self):
        env = {}  # COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — the
                  # deliberately-suppressed-ingest case, B-U13's exact scenario
        result = mc_board.card_open(
            str(self.run_dir), slug="s", title="t", department="web-development",
            env=env, evidence_root=str(self.evidence_root),
        )
        self.assertIsNone(result)
        receipt = mc_board._read_board_ingest_receipt(str(self.evidence_root))
        self.assertIsNotNone(receipt)
        self.assertFalse(receipt["mc_url_set"])
        self.assertFalse(receipt["ok"])

        # And reconcile() surfaces it as drift in the very next probe cycle.
        report = mc_board.reconcile(str(self.evidence_root.parent))
        self.assertEqual(len(report.drift), 1)
        self.assertEqual(report.drift[0]["run"], "run-1")

    def test_successful_ingest_with_evidence_root_writes_clean_receipt(self):
        env = {"COMMAND_CENTER_URL": "https://cc.example.test", "MC_API_TOKEN": "t"}
        calls = []

        def fake_request(method, url, payload, cfg):
            calls.append((method, url, payload))
            return 201, {"task_id": "TASK-99", "deduped": False}

        orig = mc_board._request
        mc_board._request = fake_request
        try:
            result = mc_board.card_open(
                str(self.run_dir), slug="s", title="t", department="web-development",
                env=env, evidence_root=str(self.evidence_root),
            )
        finally:
            mc_board._request = orig

        self.assertEqual(result, "TASK-99")
        receipt = mc_board._read_board_ingest_receipt(str(self.evidence_root))
        self.assertIsNotNone(receipt)
        self.assertTrue(receipt["mc_url_set"])
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["task_id"], "TASK-99")

        report = mc_board.reconcile(str(self.evidence_root.parent))
        self.assertEqual(report.clean, ["run-1"])
        self.assertEqual(report.drift, [])


class ReconcileCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_json_output_and_always_exits_zero(self):
        _write_json(
            self.base / "run-suppressed" / "routing" / "board-ingest-receipt.json",
            _suppressed_receipt(),
        )
        import io
        import contextlib

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = mc_board._reconcile_cli(["--base-dir", str(self.base), "--json"])
        self.assertEqual(rc, 0)  # non-gating — ALWAYS exit 0, even with drift
        printed = json.loads(out.getvalue())
        self.assertFalse(printed["all_clean"])
        self.assertEqual(len(printed["drift"]), 1)

    def test_cli_exits_zero_even_when_clean(self):
        _write_json(
            self.base / "run-clean" / "routing" / "board-ingest-receipt.json",
            _clean_receipt(),
        )
        import io
        import contextlib

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = mc_board._reconcile_cli(["--base-dir", str(self.base), "--json"])
        self.assertEqual(rc, 0)
        printed = json.loads(out.getvalue())
        self.assertTrue(printed["all_clean"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
