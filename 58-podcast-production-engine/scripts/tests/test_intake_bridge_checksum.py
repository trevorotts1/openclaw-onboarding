#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: intake-bridge ledger checksum order
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB: a throwaway file DB, a throwaway
# job-index dir and a throwaway ledger. Proves the bridge checksum ORDERING fix:
# the SQLite bridge (podcast_state.py create) stamps _checksum onto the ledger
# record when it mirrors its own status, and the webhook layer then writes its
# own fields (the bridge note, the flow binding, a duplicate, a retry). Those
# writes used to be persisted with the PREVIOUS stamp, so the record no longer
# verified and podcast_state.py refused the next transition with "ledger
# checksum MISMATCH ... the fail was rolled back" -- a bridged job could not be
# closed without a manual checksum repair.
#
# The two layers share one record file on a provisioned box. At the pinned base
# the bridge passes the ledger BASE dir to podcast_state.py, whose --ledger-dir
# expects the intake-ledger dir itself, so the two writes land in different
# directories; the self-referential intake-ledger symlink below forces the
# shared-file condition that the live box exhibits (and that the ledger-dir
# plumbing fix lands), which is what makes this test discriminate.
#
# Run:
#   python3 -m unittest 58-podcast-production-engine/scripts/tests/test_intake_bridge_checksum.py
# =============================================================================
"""Bridged ledger records must stay checksum-valid so the job can be closed."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
_WEBHOOK = _HERE.parent.parent / "webhook"
sys.path.insert(0, str(_WEBHOOK))
import ledger  # noqa: E402
import intake_handler  # noqa: E402

_PODCAST_STATE = _HERE.parent.parent / "podcast_state.py"


def _load_podcast_state():
    spec = importlib.util.spec_from_file_location("podcast_state", str(_PODCAST_STATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PS = _load_podcast_state()

JOB_KEY = "pd-unitTestBridgeCs01-0123456789abcdef"
CANONICAL = {
    "mode": "personal_podcast_style",
    "style": "counter_intuitive",
    "contact_id": "unit-test-contact-0001",
    "location_id": "unit-test-location-0001",
    "_test": True,
}
ROUTE_ID = "podcast-intake-unit-test"


class BridgeChecksumTests(unittest.TestCase):
    """A bridged _test job must close through podcast_state.py fail."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pd-bridge-cs-")
        self.base = Path(self.tmp) / "state"
        self.base.mkdir(mode=0o700)
        # Both layers onto ONE record file (see the header). Relative target, so the
        # fixture does not depend on the temp-dir path of the machine running it.
        os.symlink(".", str(self.base / "intake-ledger"))
        self.jobindex = str(Path(self.tmp) / "job-index")
        os.makedirs(self.jobindex, mode=0o700, exist_ok=True)
        self.db = str(Path(self.tmp) / "podcast-engine.db")
        self._env = mock.patch.dict(os.environ, {
            "PODCAST_ENGINE_STATE_DIR": str(self.base),
            "PODCAST_DB_PATH": self.db,
            "PODCAST_JOBINDEX_DIR": self.jobindex,
            "PODCAST_LEDGER_DIR": str(self.base / "intake-ledger"),
            "PODCAST_INTAKE_ROUTE_ID": ROUTE_ID,
        }, clear=False)
        self._env.start()
        self.addCleanup(self._env.stop)
        # No board mirror, no alert routing, no test-canary identity of a real box.
        for var in ("CC_BASE_URL", "PODCAST_TEST_CONTACT_ID"):
            os.environ.pop(var, None)

    def _config(self):
        return {"route_id": ROUTE_ID, "base": str(self.base), "mode": "no-flow"}

    def _record_path(self):
        return self.base / "intake-ledger" / (JOB_KEY + ".json")

    def _read_record(self):
        return json.loads(self._record_path().read_text(encoding="utf-8"))

    def _bridge(self):
        claimed, rec = ledger.claim(JOB_KEY, CANONICAL, state="test", base=str(self.base))
        self.assertTrue(claimed, "fixture claim must create the record")
        verdict = {}
        intake_handler._bridge_and_record(JOB_KEY, CANONICAL, str(self.base),
                                          self._config(), verdict, None)
        self.assertEqual(verdict.get("bridge"), "ok",
                         "bridge must succeed (verdict=%s)" % json.dumps(verdict))
        return verdict

    # -- AC3: the bridged record verifies as podcast_state.py reads it ---------
    def test_bridged_record_carries_a_verifiable_checksum(self):
        self._bridge()
        raw = self._record_path().read_text(encoding="utf-8")
        self.assertIn(PS.ROSTER_CHECKSUM_KEY, json.loads(raw))
        PS.verify_checksum(raw)  # raises on a stale checksum

    # -- AC1: the bridged job CLOSES through podcast_state.py fail -------------
    def test_bridged_test_job_closes_through_state_fail(self):
        verdict = self._bridge()
        job_id = self._read_record()["sqlite_job_id"]
        proc = subprocess.run(
            [sys.executable or "python3", str(_PODCAST_STATE), "--json", "fail",
             "--job-id", job_id, "--step", "unit-test",
             "--error", "intake-bridge checksum regression check"],
            capture_output=True, text=True, timeout=60, env=dict(os.environ),
        )
        self.assertNotIn("ledger checksum MISMATCH", proc.stderr)
        self.assertEqual(proc.returncode, 0,
                         "fail must be accepted (rc=%d): %s" %
                         (proc.returncode, (proc.stderr or proc.stdout).strip()))
        self.assertEqual(verdict["job_id"], job_id)
        record = self._read_record()
        # A designated test intake keeps its terminal ledger "test" state: the bridge
        # payload carries `_test`, and podcast_state.py deliberately leaves the ledger
        # record's state alone so a test never walks the real state machine. The close
        # was still accepted at the SQLite layer -- the `fail` above returned 0 with
        # {"status": "failed"} -- and that acceptance is what this test owns: before
        # the ordering fix the same call was REFUSED with "ledger checksum MISMATCH".
        self.assertEqual(record["state"], "test")
        PS.verify_checksum(self._record_path().read_text(encoding="utf-8"))

    # -- AC3 (later writes): any webhook-layer write after the bridge ---------
    def test_post_bridge_ledger_write_keeps_the_checksum_valid(self):
        self._bridge()
        ledger.update_state(JOB_KEY, None, base=str(self.base),
                            note="bound to plugin flow flow-unittest-0001")
        PS.verify_checksum(self._record_path().read_text(encoding="utf-8"))
        ledger.register_duplicate(JOB_KEY, base=str(self.base))
        PS.verify_checksum(self._record_path().read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
