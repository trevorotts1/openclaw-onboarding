#!/usr/bin/env python3
"""
test_qc_timing_report.py -- W28b-B3 test suite for qc_timing_report.py, the
SMOKE-section TIMING report ("THE SMOKE (judged after Step 2)" in the
department QC document):

  - elapsed --new to DONE <= 60 minutes (state.json created_at .. last done
    phase_exit ended_at, with the updated_at fallback named out loud)
  - zero --resume invocations in the engine log
    (working/logs/engine-stdout.log)
  - no Kie window over 20 in the governor/engine log
  - per-phase wall-clock rows aggregated from FIX 5 stage-timings.jsonl rows

Doctrine under test (presentation_job/result.py):
  a missing or unreadable source yields UNDETERMINED, never a silent pass;
  a zero measured over an ABSENT instrument is not the same claim as a zero
  measured over a real one.

Hermetic: tempfile fixtures only, no network, no subprocesses, no engine.
Run:  python3 tests/test_qc_timing_report.py
      python3 -m pytest tests/test_qc_timing_report.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

import qc_timing_report as qtr  # noqa: E402


def _mk_run(root: Path) -> Path:
    rd = root / "run"
    (rd / "working" / "telemetry").mkdir(parents=True)
    (rd / "working" / "logs").mkdir(parents=True)
    return rd


def _write_state(rd: Path, **over) -> None:
    doc = {
        "schema_version": 1,
        "job_id": "pj_fixture",
        "run_dir": str(rd),
        "created_at": "2026-09-01T10:00:00+00:00",
        "updated_at": "2026-09-01T10:20:00+00:00",
        "terminal": "DONE",
        "phases": [],
        "heartbeat": {},
    }
    doc.update(over)
    (rd / "state.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_timing(rd: Path, rows) -> None:
    p = rd / qtr.STAGE_TIMINGS_RELATIVE
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_engine_log(rd: Path, text: str) -> None:
    p = rd / qtr.ENGINE_LOG_RELATIVE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _phase_exit(pid: str, started: str, ended: str, dur: float,
                status: str = "done", **over) -> dict:
    row = {
        "run_id": "run", "phase_id": pid, "wave": 0, "model_used": None,
        "event": "phase_exit", "started_at": started, "ended_at": ended,
        "duration_s": dur, "status": status, "return_code": 0,
    }
    row.update(over)
    return row


class ElapsedTest(unittest.TestCase):
    def test_clean_run_passes_at_20_minutes(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd)
            _write_timing(rd, [_phase_exit("P1-COPY",
                                           "2026-09-01T10:00:00+00:00",
                                           "2026-09-01T10:20:00+00:00", 1200.0)])
            row = qtr.collect_elapsed(qtr.json.loads((rd / "state.json").read_text()),
                                      qtr._read_jsonl(rd / qtr.STAGE_TIMINGS_RELATIVE)[0],
                                      True)
            self.assertIs(row["verdict"], qtr.Verdict.PASS)
            self.assertEqual(row["elapsed_minutes"], 20.0)
            self.assertEqual(row["end_anchor_source"], "stage-timings.jsonl")

    def test_61_minutes_fails_ceiling(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd, updated_at="2026-09-01T11:01:00+00:00")
            _write_timing(rd, [])  # no done row -> updated_at anchor
            row = qtr.collect_elapsed(qtr.json.loads((rd / "state.json").read_text()),
                                      [], True)
            self.assertIs(row["verdict"], qtr.Verdict.FAIL)
            self.assertEqual(row["elapsed_minutes"], 61.0)
            self.assertIn("updated_at", row["end_anchor_source"])

    def test_exactly_60_minutes_passes(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd, updated_at="2026-09-01T11:00:00+00:00")
            _write_timing(rd, [])
            row = qtr.collect_elapsed(qtr.json.loads((rd / "state.json").read_text()),
                                      [], True)
            self.assertIs(row["verdict"], qtr.Verdict.PASS)
            self.assertEqual(row["elapsed_minutes"], 60.0)

    def test_missing_state_is_undetermined(self):
        with tempfile.TemporaryDirectory() as td:
            row = qtr.collect_elapsed(None, [], False)
            self.assertIs(row["verdict"], qtr.Verdict.UNDETERMINED)
            self.assertIn("state.json", row["reason"])

    def test_unparseable_created_at_is_undetermined(self):
        with tempfile.TemporaryDirectory() as td:
            row = qtr.collect_elapsed({"created_at": "not-a-time",
                                       "updated_at": "2026-09-01T10:20:00+00:00"}, [], True)
            self.assertIs(row["verdict"], qtr.Verdict.UNDETERMINED)

    def test_negative_window_is_undetermined_not_fail(self):
        with tempfile.TemporaryDirectory() as td:
            row = qtr.collect_elapsed(
                {"created_at": "2026-09-01T11:00:00+00:00",
                 "updated_at": "2026-09-01T10:00:00+00:00"}, [], True)
            self.assertIs(row["verdict"], qtr.Verdict.UNDETERMINED)
            self.assertIsNone(row["elapsed_minutes"])


class ResumeInvocationsTest(unittest.TestCase):
    def test_zero_over_present_log_passes(self):
        row = qtr.collect_resume_invocations("engine up\nphase done\n", True)
        self.assertIs(row["verdict"], qtr.Verdict.PASS)
        self.assertEqual(row["resume_token_count"], 0)
        self.assertGreater(row["log_bytes"], 0)

    def test_one_resume_fails(self):
        row = qtr.collect_resume_invocations("dispatch --resume --run-dir x\n", True)
        self.assertIs(row["verdict"], qtr.Verdict.FAIL)
        self.assertEqual(row["resume_token_count"], 1)

    def test_absent_log_is_undetermined_never_pass(self):
        row = qtr.collect_resume_invocations("", False)
        self.assertIs(row["verdict"], qtr.Verdict.UNDETERMINED)
        self.assertIsNone(row["resume_token_count"])

    def test_resume_inside_longer_flag_counts(self):
        row = qtr.collect_resume_invocations("--resume-token=1 used\n", True)
        self.assertEqual(row["resume_token_count"], 1)


class KieWindowTest(unittest.TestCase):
    def test_window_21_fails(self):
        row = qtr.collect_kie_window("kie concurrency window now 21\n", True)
        self.assertIs(row["verdict"], qtr.Verdict.FAIL)
        self.assertEqual(row["observed_max"], 21)

    def test_window_20_passes(self):
        row = qtr.collect_kie_window("kie concurrency window now 20\n", True)
        self.assertIs(row["verdict"], qtr.Verdict.PASS)
        self.assertEqual(row["observed_max"], 20)

    def test_present_log_without_window_lines_passes_and_says_why(self):
        row = qtr.collect_kie_window("engine up\nphase done\n", True)
        self.assertIs(row["verdict"], qtr.Verdict.PASS)
        self.assertIsNone(row["observed_max"])
        self.assertIn("no kie-window line", row["reason"])

    def test_absent_log_is_undetermined(self):
        row = qtr.collect_kie_window("", False)
        self.assertIs(row["verdict"], qtr.Verdict.UNDETERMINED)

    def test_case_insensitive_match(self):
        row = qtr.collect_kie_window("KIE WINDOW size=35\n", True)
        self.assertIs(row["verdict"], qtr.Verdict.FAIL)
        self.assertEqual(row["observed_max"], 35)


class TerminalTest(unittest.TestCase):
    def test_done_recorded(self):
        row = qtr.collect_terminal({"terminal": "DONE"})
        self.assertIs(row["verdict"], qtr.Verdict.PASS)
        self.assertEqual(row["terminal"], "DONE")

    def test_missing_is_undetermined(self):
        row = qtr.collect_terminal(None)
        self.assertIs(row["verdict"], qtr.Verdict.UNDETERMINED)


class PhaseRowsTest(unittest.TestCase):
    def test_aggregates_attempts_and_durations(self):
        rows = qtr.collect_phase_rows([
            _phase_exit("P4-PROMPT", "2026-09-01T10:00:00+00:00",
                        "2026-09-01T10:01:00+00:00", 60.0, status="nonzero_rc_4"),
            _phase_exit("P4-PROMPT", "2026-09-01T10:02:00+00:00",
                        "2026-09-01T10:04:00+00:00", 120.0),
            _phase_exit("P1-COPY", "2026-09-01T10:00:30+00:00",
                        "2026-09-01T10:00:50+00:00", 20.0),
            {"event": "slide_author", "phase_id": "P4-PROMPT", "duration_s": 5.0},
        ])
        by = {r["phase_id"]: r for r in rows}
        self.assertEqual(by["P4-PROMPT"]["attempts"], 2)
        self.assertEqual(by["P4-PROMPT"]["total_duration_s"], 180.0)
        self.assertEqual(by["P4-PROMPT"]["max_duration_s"], 120.0)
        self.assertEqual(by["P4-PROMPT"]["last_status"], "done")
        self.assertEqual(by["P1-COPY"]["attempts"], 1)
        # slide-level rows are not phase rows
        self.assertNotIn("slide_author", {r["phase_id"] for r in rows})

    def test_missing_duration_flagged_not_crash(self):
        rows = qtr.collect_phase_rows([
            _phase_exit("P1-COPY", "2026-09-01T10:00:00+00:00",
                        "2026-09-01T10:01:00+00:00", None),
        ])
        self.assertEqual(rows[0]["errors"], ["duration_s missing or non-numeric"])

    def test_error_class_surfaced(self):
        rows = qtr.collect_phase_rows([
            _phase_exit("P4-PROMPT", "2026-09-01T10:00:00+00:00",
                        "2026-09-01T10:01:00+00:00", 60.0, status="crashed",
                        error_class="TimeoutError"),
        ])
        self.assertIn("TimeoutError", rows[0]["errors"])


class BuildReportTest(unittest.TestCase):
    def test_full_happy_run_overall_pass(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd)
            _write_timing(rd, [_phase_exit("P1-COPY",
                                           "2026-09-01T10:00:00+00:00",
                                           "2026-09-01T10:20:00+00:00", 1200.0)])
            _write_engine_log(rd, "engine up\n")
            rep = qtr.build_report(rd)
            self.assertIs(rep["overall"], qtr.Verdict.PASS)
            self.assertEqual(len(rep["claims"]), 4)
            self.assertTrue(rep["sources"]["state_json"]["parsed"])
            self.assertTrue(rep["sources"]["engine_log"]["present"])
            self.assertEqual(rep["sources"]["stage_timings"]["rows"], 1)

    def test_run_dir_may_not_exist_for_claims_but_cli_rejects(self):
        # build_report itself is tolerant (collectors go UNDETERMINED);
        # main() refuses a nonexistent --run-dir with EXIT_USAGE.
        with tempfile.TemporaryDirectory() as td:
            rep = qtr.build_report(Path(td) / "nope")
            self.assertIs(rep["overall"], qtr.Verdict.UNDETERMINED)
            rc = qtr.main(["--run-dir", str(Path(td) / "nope")])
            self.assertEqual(rc, qtr.EXIT_USAGE)

    def test_report_does_not_write_into_run_dir(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd)
            _write_engine_log(rd, "")
            before = sorted(str(p.relative_to(rd)) for p in rd.rglob("*"))
            out = Path(td) / "report.json"
            rc = qtr.main(["--run-dir", str(rd), "--out", str(out), "--json"])
            self.assertEqual(rc, qtr.EXIT_HAS_UNDETERMINED)  # empty log present
            after = sorted(str(p.relative_to(rd)) for p in rd.rglob("*"))
            self.assertEqual(before, after)  # run dir untouched
            self.assertTrue(out.is_file())

    def test_out_inside_run_dir_refused(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd)
            out = rd / "working" / "report.json"
            rc = qtr.main(["--run-dir", str(rd), "--out", str(out)])
            self.assertEqual(rc, qtr.EXIT_USAGE)
            self.assertFalse(out.exists())

    def test_exit_codes_distinguish_fail_and_undetermined(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _mk_run(Path(td))
            _write_state(rd)
            _write_engine_log(rd, "--resume used once\n")
            rc = qtr.main(["--run-dir", str(rd)])
            self.assertEqual(rc, qtr.EXIT_HAS_FAIL)


class SelftestTest(unittest.TestCase):
    def test_selftest_passes(self):
        self.assertEqual(qtr._selftest(), qtr.EXIT_OK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
