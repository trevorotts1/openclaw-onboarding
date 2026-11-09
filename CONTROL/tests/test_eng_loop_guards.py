#!/usr/bin/env python3
"""Regression tests for the PBB-279 defects in CONTROL/eng_loop.py.

Every case here fails on the reviewed bytes (PBB-279 FAIL) and passes after the
repair: configuration is read at use time, and the three guards refuse malformed
input instead of raising out of the store or the JSON boundary.

Run: python3 -m unittest discover -s CONTROL/tests -v
"""
import importlib.util
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "eng_loop.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("eng_loop_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ConfigurationIsReadAtUseTime(unittest.TestCase):
    """D1: an import-time capture let the child write a different store."""

    def test_runtime_change_reaches_the_child_environment(self):
        old = os.environ.get("PB_STATE_DIR")
        try:
            os.environ["PB_STATE_DIR"] = "/tmp/state-at-import"
            mod = _load_module()
            os.environ["PB_STATE_DIR"] = "/tmp/state-set-at-runtime"
            self.assertEqual(mod.external_env()["PB_STATE_DIR"], "/tmp/state-set-at-runtime")
            mod.refresh_config()
            self.assertEqual(mod.STATE, "/tmp/state-set-at-runtime")
            self.assertEqual(mod.DB_PATH, os.path.join("/tmp/state-set-at-runtime", "engine.db"))
        finally:
            if old is None:
                os.environ.pop("PB_STATE_DIR", None)
            else:
                os.environ["PB_STATE_DIR"] = old

    def test_no_import_time_external_env_constant(self):
        mod = _load_module()
        self.assertFalse(hasattr(mod, "EXTERNAL_ENV"),
                         "a module-level env map is the import-time capture D1 named")


class _CliCase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="eng-loop-test-")
        self.state = os.path.join(self.work, "state")
        self.bin = os.path.join(self.work, "bin")
        os.makedirs(self.state)
        os.makedirs(self.bin)
        # A stub launchctl: no real job is ever touched, and a missing job reads back
        # as absent so a passing ownership guard completes without the host.
        stub = os.path.join(self.bin, "launchctl")
        with open(stub, "w") as f:
            f.write('#!/bin/sh\necho "Could not find service" >&2\nexit 113\n')
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def run_cli(self, args, plist=None):
        env = dict(os.environ)
        env.update({
            "PB_STATE_DIR": self.state,
            "PB_TMP": os.path.join(self.work, "tmp"),
            "PB_CACHE": os.path.join(self.work, "cache"),
            "PB_LABEL": "ai.blackceo.pb-eng-loop-test",
            "PATH": self.bin + os.pathsep + env.get("PATH", ""),
        })
        env.pop("PB_PLIST", None)
        if plist:
            env["PB_PLIST"] = plist
        p = subprocess.run([sys.executable, "-I", SCRIPT] + args, capture_output=True,
                           text=True, timeout=60, env=env)
        return p.returncode, p.stdout, p.stderr


class GuardRefusesInsteadOfRaising(_CliCase):
    def test_generation_outside_sqlite_integer_is_refused(self):
        for gen in (str(2 ** 63), "9" * 40):
            rc, out, err = self.run_cli(["request-stop", "--run-id", "r", "--generation", gen])
            self.assertEqual(rc, 3, (gen, rc, err[-300:]))
            self.assertEqual(json.loads(out)["reason"], "generation_out_of_range")
            self.assertNotIn("OverflowError", err)

    def test_generation_inside_sqlite_integer_still_accepted(self):
        for gen in (str(2 ** 63 - 1), "-1", "0"):
            rc, out, err = self.run_cli(["request-stop", "--run-id", "r", "--generation", gen])
            self.assertEqual(rc, 0, (gen, rc, err[-300:]))
            self.assertEqual(json.loads(out)["result"], "stop_requested_persisted")

    def test_malformed_payload_is_refused(self):
        for payload in ("  ", "{"):
            rc, out, err = self.run_cli(["create", "--type", "t", "--idempotency-key",
                                         "k-" + str(len(payload)), "--payload", payload,
                                         "--run-id", "r"])
            self.assertEqual(rc, 2, (payload, rc, err[-300:]))
            self.assertEqual(json.loads(out)["reason"], "invalid_payload")
            self.assertNotIn("JSONDecodeError", err)

    def test_valid_payload_shapes_still_accepted(self):
        for i, payload in enumerate(("", "{}", "[1,2]", "null", "5", '"hi"')):
            rc, out, err = self.run_cli(["create", "--type", "t", "--idempotency-key",
                                         "ok-%d" % i, "--payload", payload, "--run-id", "r"])
            self.assertEqual(rc, 0, (payload, rc, err[-300:]))
            self.assertEqual(json.loads(out)["result"], "created")

    def test_stop_path_refuses_a_program_arguments_flag_with_no_value(self):
        rc, out, err = self.run_cli(["request-stop", "--run-id", "run-1", "--generation", "1"])
        self.assertEqual(rc, 0, err[-300:])
        aid = json.loads(out)["action"]["action_id"]
        plist = os.path.join(self.work, "trailing.plist")
        with open(plist, "wb") as f:
            plistlib.dump({"Label": "probe", "ProgramArguments": ["x", "--run-id"]}, f)
        rc, out, err = self.run_cli(["dispatch-stop", "--action-id", aid, "--run-id", "run-1"],
                                    plist=plist)
        self.assertEqual(rc, 3, (rc, err[-300:]))
        self.assertEqual(json.loads(out)["reason"], "job_not_owned_by_action_run_id")
        self.assertNotIn("IndexError", err)

    def test_stop_path_ownership_guard_still_fires_and_still_admits_the_owner(self):
        rc, out, _ = self.run_cli(["request-stop", "--run-id", "run-1", "--generation", "1"])
        aid = json.loads(out)["action"]["action_id"]
        for label, pargs, want in (
                ("absent", ["x"], 3),
                ("empty", ["x", "--run-id", ""], 3),
                ("blank", ["x", "--run-id", "   "], 3),
                ("matching", ["x", "--run-id", "run-1"], 0)):
            plist = os.path.join(self.work, label + ".plist")
            with open(plist, "wb") as f:
                plistlib.dump({"Label": "probe-" + label, "ProgramArguments": pargs}, f)
            rc, out, err = self.run_cli(
                ["dispatch-stop", "--action-id", aid, "--run-id", "run-1"], plist=plist)
            self.assertEqual(rc, want, (label, rc, err[-300:]))
            if want == 3:
                self.assertEqual(json.loads(out)["reason"], "job_not_owned_by_action_run_id")


if __name__ == "__main__":
    unittest.main(verbosity=2)
