#!/usr/bin/env python3
"""F21 — Portable deployment and service health contract.

QC-F21 matrix (unittest, NO network, fixture sandboxes):
  1. The doctor's healthy fixture layout returns ok with every hard check
     passing (identity, engine, worker, cycles, sheet, n8n, retries).
  2. A STOPPED WORKER (stale receipt) is reported as a HEALTH PROBLEM with a
     state that never claims work is progressing.
  3. A missing n8n mapping (or a stale schema_version) fails the health
     contract — the deployment cannot silently run an old mapping.
  4. The durable cycle CLI runs ONE advance step per invocation against a
     fixture state dir and writes the durable outbox; a second run in the
     same week NEVER re-invites (idempotent).
  5. Engine ownership verify: exactly one active owner per company -> ok;
     a violated invariant exits unhealthy.
  6. The service installer produces the correct per-profile registration
     receipt (launchd/systemd) with the CLIENT timezone and the service-user
     HOME baked in — and records the scheduler-registration.json the doctor
     reads (fixture sandbox; no live service touched).

Run:  python3 tests/social-planner/test_f21_doctor_contract.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


doctor = _load("social_planner_doctor_f21", _REPO_ROOT / "shared-utils" / "social-planner-doctor.py")
cli = _load("social_cycle_cli_f21", _REPO_ROOT / "shared-utils" / "social_cycle_cli.py")
scs = _load("social_cycle_service_f21", _REPO_ROOT / "shared-utils" / "social_cycle_service.py")


def _env(root: str) -> dict:
    return {"OPENCLAW_ROOT": root, "HOME": "/home/operator", "SOCIAL_PLANNER_TIMEZONE": "America/New_York"}


def _healthy_fixture() -> str:
    """A complete, healthy deployment fixture under a temp root."""
    base = tempfile.mkdtemp(prefix="f21-healthy-")
    skill35 = Path(base) / "data" / "skill35"
    skill35.mkdir(parents=True)
    (skill35 / "company-identity.json").write_text(json.dumps(
        {"company_id": "co-f21", "locationId": "LOC-FIXTURE", "planner_kind": "social-planner"}))
    (skill35 / "sheet-registry.json").write_text(json.dumps({"rows": [
        {"sheet_id": "SHEET-F21", "sharing": "anyone,writer", "verified_at": _now(), "schema_version": "1.1.0"}]}))
    (skill35 / "n8n-mapping.json").write_text(json.dumps(
        {"schema_version": "1.1.0", "sheet_create_workflow_id": "INyGjT8jQ6JjrZSh",
         "row_append_workflow_id": "myXde6jbIIkaG5zW"}))
    sc = Path(base) / "data" / "social-cycle"
    sc.mkdir(parents=True)
    (sc / "engine-ownership.json").write_text(json.dumps({"rows": [
        {"company_id": "co-f21", "engine": "cc-cycle-service", "state": "active"}]}))
    (sc / "scheduler-registration.json").write_text(json.dumps(
        {"scheduler_name": "systemd", "expr": "*/5 * * * *", "verified_at": _now()}))
    # A fresh worker receipt (recent mtime).
    runs = Path(base) / "data" / "skill-35" / "runs" / "run-20260909-f21"
    (runs / "working").mkdir(parents=True)
    (runs / "working" / "dispatch.json").write_text(json.dumps(
        {"state": "review", "queued_at": _now(), "run_id": "run-20260909-f21"}))
    return base


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class TestDoctorVerdict(unittest.TestCase):
    def test_1_healthy_fixture_is_ok(self):
        root = _healthy_fixture()
        v = doctor.run_doctor(env=_env(root), root_override=root)
        self.assertTrue(v["ok"], json.dumps(v["checks"], indent=1))
        for hard in ("identity", "engine", "worker", "sheet", "n8n", "retries"):
            self.assertTrue(v["checks"][hard]["ok"], f"{hard}: {v['checks'][hard]}")

    def test_2_stale_worker_is_a_health_problem_never_progress(self):
        root = _healthy_fixture()
        # Age the newest receipt beyond the worker-staleness window.
        runs = Path(root) / "data" / "skill-35" / "runs" / "run-20260909-f21"
        old = time.time() - 8.5 * 86400
        os.utime(runs / "working" / "dispatch.json", (old, old))
        v = doctor.run_doctor(env=_env(root), root_override=root)
        self.assertFalse(v["ok"])
        self.assertEqual(v["checks"]["worker"]["state"], "worker_stale")
        # The receipt states the worker is NOT progressing (a stopped worker
        # is never reported as work in progress — the F21 required outcome).
        self.assertIn("NOT progressing", v["checks"]["worker"]["detail"])
        self.assertFalse(v["checks"]["worker"]["ok"])

    def test_2b_hard_failures_exit_unhealthy_never_degraded(self):
        """F21-ONB-01: a failed check other than a labeled SOFT state exits
        UNHEALTHY (2), never DEGRADED (1)."""
        root = _healthy_fixture()
        runs = Path(root) / "data" / "skill-35" / "runs" / "run-20260909-f21"
        old = time.time() - 8.5 * 86400
        os.utime(runs / "working" / "dispatch.json", (old, old))
        env = _env(root)
        # Reproduce main()'s verdict->exit mapping on a worker_stale verdict.
        v = doctor.run_doctor(env=env, root_override=root)
        self.assertTrue(v["degraded_soft"] == [], "worker_stale must NOT be classified soft")
        mapped = doctor.EXIT_UNHEALTHY if not v["degraded_soft"] else doctor.EXIT_DEGRADED
        self.assertGreaterEqual(mapped, 2, "worker_stale must exit >= 2, never a soft 1")
        # The only soft state is the --live GHL probe skip.
        self.assertEqual(doctor.SOFT_FAIL_STATES, {"skipped_offline"})
        # A probe_error (check_ghl exception path) is ALSO hard: verify the
        # state name is not in the soft set.
        self.assertNotIn("probe_error", doctor.SOFT_FAIL_STATES)
        self.assertNotIn("worker_stale", doctor.SOFT_FAIL_STATES)
        self.assertNotIn("credentials_missing", doctor.SOFT_FAIL_STATES)

    def test_3_stale_or_missing_n8n_mapping_fails_health(self):
        root = _healthy_fixture()
        (Path(root) / "data" / "skill35" / "n8n-mapping.json").unlink()
        v = doctor.run_doctor(env=_env(root), root_override=root)
        self.assertFalse(v["ok"])
        self.assertEqual(v["checks"]["n8n"]["state"], "mapping_missing")
        # Stale schema version is equally a FAILED health check.
        root2 = _healthy_fixture()
        p = Path(root2) / "data" / "skill35" / "n8n-mapping.json"
        p.write_text(json.dumps({"schema_version": "1.0.0"}))
        v2 = doctor.run_doctor(env=_env(root2), root_override=root2)
        self.assertFalse(v2["ok"])
        self.assertEqual(v2["checks"]["n8n"]["state"], "contract_stale")

    def test_3b_registry_sharing_drift_detected(self):
        root = _healthy_fixture()
        p = Path(root) / "data" / "skill35" / "sheet-registry.json"
        reg = json.loads(p.read_text())
        reg["rows"][0]["sharing"] = "named-users-only"  # F02 violation
        p.write_text(json.dumps(reg))
        v = doctor.run_doctor(env=_env(root), root_override=root)
        self.assertFalse(v["ok"])
        self.assertEqual(v["checks"]["sheet"]["state"], "sharing_drift")


class TestCycleCli(unittest.TestCase):
    def _patch_env(self, root: str, send: str = "outbox") -> dict:
        """The CLI reads state via os.environ (service-manager context), so the
        fixture override is applied to the process env and restored after."""
        env = {"SOCIAL_CYCLE_STATE_DIR": os.path.join(root, "sc"), "SOCIAL_CYCLE_SEND": send}
        self._saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        return env

    def tearDown(self):
        saved = getattr(self, "_saved", None)
        if saved:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_4_one_advance_step_idempotent_outbox(self):
        root = tempfile.mkdtemp(prefix="f21-cli-")
        env = self._patch_env(root)
        # 2026-09-06 is a local-week Sunday.
        T = 1788696000000
        r1 = cli.main(["advance", "--company", "co-f21", "--now-ms", str(T)])
        self.assertEqual(r1, 0)
        state = json.loads((Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "co-f21" / "cycles.json").read_text())
        self.assertEqual(len(state), 1)
        outbox = Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "outbox.jsonl"
        self.assertTrue(outbox.is_file(), "the durable outbox must record the invitation send")
        # Second advance in the same week NEVER re-invites (durable state).
        r2 = cli.main(["advance", "--company", "co-f21", "--now-ms", str(T + 300_000)])
        state2 = json.loads((Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "co-f21" / "cycles.json").read_text())
        self.assertEqual(len(state2), 1)
        # The durable state still carries exactly ONE cycle row and the
        # invitation timestamp is unchanged (idempotent re-run, no re-send).
        wk = next(iter(state))
        self.assertEqual(state2[wk]["invitation_sent_at"], state[wk]["invitation_sent_at"])

    def test_5_verify_ownership_exit_codes(self):
        root = tempfile.mkdtemp(prefix="f21-own-")
        env = self._patch_env(root, send="none")
        scs.claim_engine_ownership("co-f21", env=os.environ)
        rc = cli.main(["verify-ownership"])
        self.assertEqual(rc, 0)
        # Break the invariant: a second active owner for the same company.
        with open(Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "engine-ownership.json") as fh:
            data = json.load(fh)
        data["rows"].append({"id": "x", "company_id": "co-f21", "engine": "legacy", "state": "active"})
        with open(Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "engine-ownership.json", "w") as fh:
            json.dump(data, fh)
        rc2 = cli.main(["verify-ownership"])
        self.assertEqual(rc2, cli.EXIT_UNHEALTHY)


class TestServiceInstaller(unittest.TestCase):
    def test_6_installer_receipts_fixture(self):
        # The installer self-test already proves plist/unit + registration
        # receipt + client timezone on a fixture HOME. Run it as a subprocess
        # so the assertion here IS the QC evidence for the receipt shape.
        proc = subprocess.run(
            ["bash", str(_REPO_ROOT / "shared-utils" / "social-service.sh"), "--self-test"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("fail=0", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)