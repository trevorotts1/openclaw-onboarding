#!/usr/bin/env python3
"""F08 — Do not let fixture configuration disable live verification.

QC-F08 matrix (unittest, NO network):
  1. A production execution-mode stamp + a nonempty probes config -> the run
     FAILS with a configuration error (AF-SM-EXEC-MODE), preflight included.
  2. SMIB_PREFLIGHT_OFFLINE=0 / false / empty STAYS LIVE (strict boolean
     parsing; any nonempty legacy value no longer flips the mode at all).
  3. A simulated (test) run stamps simulated=true on its artifacts; a fixture
     (simulated) receipt against a LIVE completion is REJECTED.
  4. The trusted entry stamps the mode; a missing stamp fails closed.
  5. An exceptional offline run is recorded separately.

Run:  python3 -m unittest tests.social-planner.test_f08_execution_mode -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SKILL_DIR = _REPO_ROOT / "57-social-media-in-a-box"
_RUNNER_PATH = _SKILL_DIR / "run_social_media.py"
_ENTRY_PATH = _SKILL_DIR / "social-media-entry.sh"
assert _RUNNER_PATH.is_file(), "run_social_media.py not found"
assert _ENTRY_PATH.is_file(), "social-media-entry.sh not found"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rsm = _load("run_social_media_under_test", _RUNNER_PATH)
pg = _load("preflight_gate_f08", _SKILL_DIR / "scripts" / "preflight_gate.py")


def _run_dir(tmp, mode="production", probes=None, extra=None):
    rd = Path(tmp) / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "publish").mkdir(parents=True, exist_ok=True)
    (rd / "delivery").mkdir(parents=True, exist_ok=True)
    cfg = {"brandName": "Brand One", "locationId": "loc-1", "userId": "u-1",
           "timezone": "America/New_York", "status": "Paid"}
    if probes is not None:
        cfg["probes"] = probes
    (rd / "working" / "copy" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    stamp = {"mode": mode, "set_by": "trusted-entry", "simulated": mode != "production"}
    (rd / "working" / "execution_mode.json").write_text(json.dumps(stamp), encoding="utf-8")
    (rd / "delivery" / "PROCESS-CERTIFICATE.json").write_text("{}", encoding="utf-8")
    plan = {"weekOf": "2026-09-07", "themeOfWeek": "Theme", "plannerSheetId": "sheet-1",
            "companyId": "co-1", "cycleId": "cy-1", "contentRevision": 1,
            "platforms": ["facebook"], "accounts": [
                {"account_id": "fb-1", "platform": "facebook", "account_name": "FB"}]}
    (rd / "working" / "plan").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    results = [{"kind": "publish_result", "platform": "facebook", "success": True,
                "totalPosts": 1, "processedAccounts": 1, "errors": []}]
    (rd / "working" / "publish" / "publish_results.json").write_text(
        json.dumps(results), encoding="utf-8")
    for k, v in (extra or {}).items():
        p = rd / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(v), encoding="utf-8")
    return rd


class TestProductionRejectsProbes(unittest.TestCase):
    """QC-F08: run production with nonempty probes -> fail with a config error."""

    def test_probes_in_production_is_configuration_error(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production",
                          probes={"kieCredits": 500, "openrouterBalance": 25.0})
            ok, msg = rsm._chk_preflight(rd)
            self.assertFalse(ok)
            self.assertIn("AF-SM-EXEC-MODE", msg)
            self.assertIn("probes", msg)

    def test_assert_no_probes_in_production_raises(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production", probes={"ghlTokenValid": True})
            with self.assertRaises(rsm.ConfigurationError):
                rsm._assert_no_probes_in_production(rd)

    def test_empty_probes_object_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production", probes={})
            try:
                rsm._assert_no_probes_in_production(rd)  # must NOT raise
            except rsm.ConfigurationError as exc:  # pragma: no cover
                self.fail("empty probes object rejected: %s" % exc)

    def test_preflight_gate_live_rejects_probes(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production", probes={"kieCredits": 500})
            cfgp = rd / "working" / "copy" / "config.json"
            rc = pg.run(str(cfgp), live=True, as_json=True)
            self.assertEqual(rc, pg.EXIT_AUTOFAIL)


class TestStrictBooleanParsing(unittest.TestCase):
    """QC-F08: OFFLINE=0/false/empty retains PRODUCTION semantics; any nonempty
    value no longer flips the run mode (only the trusted entry can stamp)."""

    def _with_env(self, value):
        old = os.environ.get("SMIB_PREFLIGHT_OFFLINE")
        if value is None:
            os.environ.pop("SMIB_PREFLIGHT_OFFLINE", None)
        else:
            os.environ["SMIB_PREFLIGHT_OFFLINE"] = value
        try:
            return rsm._strict_bool(
                os.environ.get("SMIB_PREFLIGHT_OFFLINE"), "SMIB_PREFLIGHT_OFFLINE", "rd")
        finally:
            if old is None:
                os.environ.pop("SMIB_PREFLIGHT_OFFLINE", None)
            else:
                os.environ["SMIB_PREFLIGHT_OFFLINE"] = old

    def test_zero_string_is_false(self):
        self.assertFalse(self._with_env("0"))

    def test_false_string_is_false(self):
        self.assertFalse(self._with_env("false"))

    def test_empty_is_false(self):
        self.assertFalse(self._with_env(""))
        self.assertFalse(self._with_env(None))

    def test_one_is_true(self):
        self.assertTrue(self._with_env("1"))

    def test_garbage_is_configuration_error(self):
        with self.assertRaises(rsm.ConfigurationError):
            self._with_env("please-be-offline")

    def test_env_flag_never_flips_mode(self):
        """The OLD bug: any nonempty env value made _live_mode False. Now mode
        comes ONLY from the trusted stamp — OFFLINE=1 with a production stamp
        stays LIVE."""
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production", probes=None)
            old = os.environ.get("SMIB_PREFLIGHT_OFFLINE")
            os.environ["SMIB_PREFLIGHT_OFFLINE"] = "1"
            try:
                self.assertTrue(rsm._live_mode(rd))
            finally:
                if old is None:
                    os.environ.pop("SMIB_PREFLIGHT_OFFLINE", None)
                else:
                    os.environ["SMIB_PREFLIGHT_OFFLINE"] = old

    def test_probes_never_flip_mode(self):
        """The OLD bug: a nonempty probes object made _live_mode False. Now a
        production stamp stays live; the probes config is instead REJECTED."""
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production", probes={"kieCredits": 1})
            self.assertTrue(rsm._live_mode(rd))


class TestTrustedStamp(unittest.TestCase):
    def test_missing_stamp_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            (rd / "working" / "execution_mode.json").unlink()
            with self.assertRaises(rsm.ConfigurationError):
                rsm._run_is_simulated(rd)

    def test_unknown_mode_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            (rd / "working" / "execution_mode.json").write_text(
                json.dumps({"mode": "wingit", "set_by": "trusted-entry"}), encoding="utf-8")
            with self.assertRaises(rsm.ConfigurationError):
                rsm._run_is_simulated(rd)

    def test_non_entry_writer_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td)
            (rd / "working" / "execution_mode.json").write_text(
                json.dumps({"mode": "production", "set_by": "i-staged-this-myself"}),
                encoding="utf-8")
            with self.assertRaises(rsm.ConfigurationError):
                rsm._run_is_simulated(rd)

    def test_write_helper_stamps(self):
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td) / "run"
            (rd / "working").mkdir(parents=True)
            rec = rsm._write_execution_mode(rd, rsm.EXECUTION_TEST, offline_reason="q")
            self.assertEqual(rec["mode"], "test")
            self.assertTrue(rec["simulated"])
            self.assertEqual(rsm._run_is_simulated(rd), True)


class TestSimulatedEvidenceNeverSatisfiesLive(unittest.TestCase):
    """QC-F08: fixture receipts against live completion -> reject."""

    def test_simulated_receipt_rejected_in_production(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="production", probes=None)
            results = [{"kind": "publish_result", "platform": "facebook", "success": True,
                        "totalPosts": 1, "processedAccounts": 1, "errors": [],
                        "simulated": True}]
            (rd / "working" / "publish" / "publish_results.json").write_text(
                json.dumps(results), encoding="utf-8")
            ok, msg = rsm._chk_publish(rd)
            self.assertFalse(ok)
            self.assertIn("SIMULATED", msg.upper())

    def test_simulated_run_stamps_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="test", probes=None)
            (rd / "working" / "copy" / "preflight-offline-token.json").write_text(
                json.dumps({"owner_approved": True, "reason": "q"}), encoding="utf-8")
            (rd / "working" / "publish" / "staged_provider_states.json").write_text(
                json.dumps({"fb-1": "scheduled"}), encoding="utf-8")
            ok, msg = rsm._chk_publish(rd)
            self.assertTrue(ok)
            sim = json.loads((rd / "working" / "publish" /
                              "publish_results_simulated.json").read_text())
            self.assertTrue(all(r.get("simulated") is True for r in sim))
            # and the delivery rows can NEVER read published from a test run
            for r in rsm._delivery_rows(rd):
                self.assertNotEqual(r.get("provider_state"), "published")

    def test_test_run_without_owner_token_refused(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _run_dir(td, mode="test", probes=None)
            ok, msg = rsm._chk_preflight(rd)
            self.assertFalse(ok)
            self.assertIn("AF-SM-EXEC-MODE", msg)


class TestEntryOfflineFlagStrictParse(unittest.TestCase):
    """D-F08-01: production entry strict-parses SMIB_PREFLIGHT_OFFLINE.

    Regression: the entry used `[ -n ... ]` and DIED on OFFLINE=0/false.
    Now 0/false/empty pass the stamp block (production stamp), 1/true dies
    pointing at the trusted test entry, and garbage dies as non-boolean.
    Exercises the live shell entry end to end. --plan exits BEFORE the stamp
    block, so the negative halves run WITHOUT --plan (they must reach the
    stamp block and die there); the positive halves assert the stamp file."""

    def _entry(self, value, plan=False):
        env = dict(os.environ)
        if value is None:
            env.pop("SMIB_PREFLIGHT_OFFLINE", None)
        else:
            env["SMIB_PREFLIGHT_OFFLINE"] = value
        env.pop("SMIB_TEST_ENTRY", None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rd = Path(tmp.name) / "run"
        (rd / "working" / "checkpoints").mkdir(parents=True)
        argv = ["bash", str(_ENTRY_PATH), "--run-dir", str(rd),
                "--mode", "week"]
        if plan:
            argv.append("--plan")
        proc = subprocess.run(argv, capture_output=True, text=True, env=env)
        return proc, rd

    def test_entry_offline_zero_false_empty_pass_gates(self):
        for value in ("", "0", "false"):
            proc, _ = self._entry(value, plan=True)
            self.assertEqual(proc.returncode, 0,
                             "OFFLINE=%r must stay live (rc=0): %s"
                             % (value, proc.stderr[-2000:]))
            self.assertIn("OK: enforcement hash matches the pinned head",
                          proc.stdout + proc.stderr)

    def test_entry_offline_zero_stamps_production(self):
        # OFFLINE=0 without --plan reaches the stamp block and stamps
        # production (the run then fails closed on the empty fixture config,
        # which is the runner's business, not the flag's).
        proc, rd = self._entry("0", plan=False)
        stamp = rd / "working" / "execution_mode.json"
        self.assertTrue(stamp.is_file(),
                        "OFFLINE=0 must reach the stamp block, not die on the flag")
        self.assertEqual(json.loads(stamp.read_text())["mode"], "production")

    def test_entry_offline_true_dies_to_test_entry(self):
        proc, rd = self._entry("1", plan=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PRODUCTION entry", proc.stderr)
        self.assertFalse((rd / "working" / "execution_mode.json").exists(),
                         "a refused offline posture must not stamp anything")

    def test_entry_offline_garbage_dies_strict_boolean(self):
        proc, _ = self._entry("please-be-offline", plan=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not a strict boolean", proc.stderr)


class TestOfflineExceptionSeparate(unittest.TestCase):
    def test_exception_record_is_separate_file(self):
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td) / "run"
            (rd / "working").mkdir(parents=True)
            rec = rsm._record_offline_exception(rd, "owner authorized offline preflight")
            self.assertTrue(rec["offline_exception"])
            self.assertTrue(rsm._offline_exception_on_record(rd))
            rsm._write_execution_mode(rd, rsm.EXECUTION_PRODUCTION)
            sim = rsm._stamp_simulated({}, rd)
            self.assertNotIn("simulated", sim)  # production run: no simulated stamp
            mode_rec = json.loads((rd / "working" / "execution_mode.json").read_text())
            self.assertFalse(mode_rec["simulated"])


if __name__ == "__main__":
    unittest.main()