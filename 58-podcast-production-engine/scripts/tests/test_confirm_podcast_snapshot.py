#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: confirm-podcast-snapshot.py unit tests
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: the live-touching functions
# (run_dry_run_provision, and any n8n fetch) are never exercised here -- only the
# pure registry/comparison/log-classification logic and the CLI's non-network
# paths (registry-only check, --record-snapshot, malformed-registry handling).
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_confirm_podcast_snapshot.py
# =============================================================================
"""Deterministic tests for the GK-05/U67 podcast snapshot confirmation gate."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "confirm-podcast-snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("confirm_podcast_snapshot", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CPS = _load_module()


def _base_registry(current="v1", v2_snapshot_id=None, v2_blocked_on=None):
    return {
        "engine": "podcast",
        "template_location_id": "CjxATjhv9Gt21qSqURIt",
        "n8n_workflow_id": "ol9YLeCpvYdNsbsg",
        "n8n_workflow_name": "Snapshot Provisioner (Podcast + Anthology)",
        "n8n_env_var": "PODCAST_SNAPSHOT_ID",
        "current": current,
        "snapshots": {
            "v1": {"snapshot_id": "IEmFFkIngiskcfJk9MH6", "status": "live-in-n8n", "blocked_on": []},
            "v2": {
                "snapshot_id": v2_snapshot_id,
                "status": "pending" if v2_snapshot_id is None else "cut-pending-n8n-confirm",
                "blocked_on": v2_blocked_on if v2_blocked_on is not None else ["GK-01/U63"],
            },
        },
    }


class RegistryLoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="confirm-podcast-snapshot-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "registry.json")

    def _write(self, obj):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def test_valid_registry_loads(self):
        self._write(_base_registry())
        data = CPS.load_registry(self.path)
        self.assertEqual(data["engine"], "podcast")
        self.assertEqual(data["current"], "v1")

    def test_missing_file_raises(self):
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(os.path.join(self.tmp, "nope.json"))

    def test_invalid_json_raises(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(self.path)

    def test_wrong_engine_raises(self):
        obj = _base_registry()
        obj["engine"] = "anthology"
        self._write(obj)
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(self.path)

    def test_missing_top_level_key_raises(self):
        obj = _base_registry()
        del obj["n8n_env_var"]
        self._write(obj)
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(self.path)

    def test_current_not_in_snapshots_raises(self):
        obj = _base_registry()
        obj["current"] = "v3"
        self._write(obj)
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(self.path)

    def test_snapshot_row_missing_key_raises(self):
        obj = _base_registry()
        del obj["snapshots"]["v1"]["status"]
        self._write(obj)
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(self.path)

    def test_empty_snapshots_raises(self):
        obj = _base_registry()
        obj["snapshots"] = {}
        obj["current"] = "v1"
        self._write(obj)
        with self.assertRaises(CPS.RegistryError):
            CPS.load_registry(self.path)


class RegistryStateTest(unittest.TestCase):
    def test_ready_when_current_has_id(self):
        data = _base_registry(current="v1")
        state = CPS.registry_state(data)
        self.assertTrue(state["ready"])
        self.assertEqual(state["current_snapshot_id"], "IEmFFkIngiskcfJk9MH6")
        self.assertEqual(state["reason"], "")

    def test_blocked_when_current_snapshot_id_missing(self):
        data = _base_registry(current="v2", v2_snapshot_id=None)
        state = CPS.registry_state(data)
        self.assertFalse(state["ready"])
        self.assertIsNone(state["current_snapshot_id"])
        self.assertIn("GK-01/U63", state["reason"])

    def test_blocked_reason_omits_deps_when_none_recorded(self):
        data = _base_registry(current="v2", v2_snapshot_id=None, v2_blocked_on=[])
        state = CPS.registry_state(data)
        self.assertFalse(state["ready"])
        self.assertNotIn("blocked_on", state["reason"])


class CompareN8nValueTest(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(CPS.compare_n8n_value("IEmFFkIngiskcfJk9MH6", "IEmFFkIngiskcfJk9MH6"))

    def test_whitespace_trimmed(self):
        self.assertTrue(CPS.compare_n8n_value("IEmFFkIngiskcfJk9MH6", "  IEmFFkIngiskcfJk9MH6\n"))

    def test_mismatch(self):
        self.assertFalse(CPS.compare_n8n_value("IEmFFkIngiskcfJk9MH6", "some-stale-id"))

    def test_case_sensitive(self):
        self.assertFalse(CPS.compare_n8n_value("AbCdEf", "abcdef"))

    def test_non_string_observed_value(self):
        self.assertFalse(CPS.compare_n8n_value("IEmFFkIngiskcfJk9MH6", None))  # type: ignore[arg-type]


class ParseFireProvisionLogTest(unittest.TestCase):
    """Fixtures are copied VERBATIM from the log() lines actually emitted by
    shared-utils/fire-provision-snapshot.sh so this stays honest to the real
    script's output shape, not an imagined one."""

    def test_2xx_accepted_is_pass(self):
        log = ("[fire-provision-snapshot] firing snapshot provision: engine=podcast client_slug=gk05-scratch\n"
               "[fire-provision-snapshot] webhook accepted (HTTP 202). ack: {\"ok\":true}\n"
               "[fire-provision-snapshot] snapshot push requested via pipeline — the box-side verify gate "
               "confirms genuine completion (~20 min).\n")
        result = CPS.parse_fire_provision_log(log)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["code_class"], "2xx")

    def test_409_is_fail(self):
        log = ("[fire-provision-snapshot] webhook returned 409 (HTTP 409): {\"error\":\"snapshot not set\"}\n"
               "[fire-provision-snapshot]   (podcast: PODCAST_SNAPSHOT_ID is not set yet in n8n — "
               "fail-closed by design.)\n"
               "[fire-provision-snapshot] MANUAL FALLBACK (webhook-409-not-configured): the automated "
               "snapshot push was NOT fired.\n")
        result = CPS.parse_fire_provision_log(log)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["code_class"], "409")

    def test_unreachable_is_fail(self):
        log = ("[fire-provision-snapshot] webhook unreachable\n"
               "[fire-provision-snapshot] MANUAL FALLBACK (webhook-unreachable): the automated snapshot "
               "push was NOT fired.\n")
        result = CPS.parse_fire_provision_log(log)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["code_class"], "manual-fallback")

    def test_unconfigured_is_fail(self):
        log = ("[fire-provision-snapshot] PROVISION_SNAPSHOT_WEBHOOK_URL = NOT SET; "
               "PROVISION_SNAPSHOT_TOKEN = NOT SET (values never printed)\n"
               "[fire-provision-snapshot] MANUAL FALLBACK (webhook-unconfigured): the automated snapshot "
               "push was NOT fired.\n")
        result = CPS.parse_fire_provision_log(log)
        self.assertEqual(result["verdict"], "FAIL")

    def test_empty_or_unrecognized_output_is_fail(self):
        result = CPS.parse_fire_provision_log("")
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["code_class"], "unknown")

    def test_non_2xx_non_409_still_fails(self):
        """A 500 is not literally a 409, but 'does not 409' names the KNOWN failure
        mode, not a license to accept a different live error."""
        log = ("[fire-provision-snapshot] webhook returned non-2xx (HTTP 500): {\"error\":\"boom\"}\n"
               "[fire-provision-snapshot] MANUAL FALLBACK (webhook-http-500): the automated snapshot "
               "push was NOT fired.\n")
        result = CPS.parse_fire_provision_log(log)
        self.assertEqual(result["verdict"], "FAIL")


class RecordSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="confirm-podcast-snapshot-record-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "registry.json")
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(_base_registry(), fh)

    def test_record_writes_id_and_clears_block(self):
        CPS.record_snapshot(self.path, "v2", "NewSnapId12345")
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        row = data["snapshots"]["v2"]
        self.assertEqual(row["snapshot_id"], "NewSnapId12345")
        self.assertEqual(row["status"], "cut-pending-n8n-confirm")
        self.assertEqual(row["blocked_on"], [])
        # current is never auto-flipped by record_snapshot
        self.assertEqual(data["current"], "v1")

    def test_record_trims_whitespace(self):
        CPS.record_snapshot(self.path, "v2", "  PaddedId  \n")
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["snapshots"]["v2"]["snapshot_id"], "PaddedId")

    def test_record_unknown_version_raises(self):
        with self.assertRaises(CPS.RegistryError):
            CPS.record_snapshot(self.path, "v99", "x")

    def test_record_empty_id_raises(self):
        with self.assertRaises(CPS.RegistryError):
            CPS.record_snapshot(self.path, "v2", "   ")

    def test_record_is_atomic_no_stray_tempfiles(self):
        CPS.record_snapshot(self.path, "v2", "AtomicId")
        leftovers = [f for f in os.listdir(self.tmp) if f.startswith(".podcast-snapshot-registry-")]
        self.assertEqual(leftovers, [])


class CliTest(unittest.TestCase):
    """Exercises main() end-to-end for every NETWORK-FREE code path. --dry-run-provision
    is intentionally never exercised here (it fires a live network call by design)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="confirm-podcast-snapshot-cli-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "registry.json")

    def _write(self, obj):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def test_blocked_state_exits_zero(self):
        self._write(_base_registry(current="v2", v2_snapshot_id=None))
        rc = CPS.main(["--registry", self.path])
        self.assertEqual(rc, 0)

    def test_ready_registry_only_exits_zero(self):
        self._write(_base_registry(current="v1"))
        rc = CPS.main(["--registry", self.path])
        self.assertEqual(rc, 0)

    def test_ready_with_matching_n8n_value_exits_zero(self):
        self._write(_base_registry(current="v1"))
        rc = CPS.main(["--registry", self.path, "--confirm-n8n-value", "IEmFFkIngiskcfJk9MH6"])
        self.assertEqual(rc, 0)

    def test_ready_with_mismatched_n8n_value_exits_one(self):
        self._write(_base_registry(current="v1"))
        rc = CPS.main(["--registry", self.path, "--confirm-n8n-value", "stale-id"])
        self.assertEqual(rc, 1)

    def test_malformed_registry_exits_one(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{bad json")
        rc = CPS.main(["--registry", self.path])
        self.assertEqual(rc, 1)

    def test_record_snapshot_flag_exits_zero_and_persists(self):
        self._write(_base_registry())
        rc = CPS.main(["--registry", self.path, "--record-snapshot", "v2", "CliRecordedId"])
        self.assertEqual(rc, 0)
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["snapshots"]["v2"]["snapshot_id"], "CliRecordedId")


class RealRegistryFileTest(unittest.TestCase):
    """The actual shipped registry (config/podcast-snapshot-registry.json) must itself
    load clean and report the expected pre-GK-01 BLOCKED state."""

    def test_shipped_registry_loads_and_is_blocked_on_v2(self):
        repo_registry = _HERE.parent.parent.parent / "config" / "podcast-snapshot-registry.json"
        data = CPS.load_registry(str(repo_registry))
        self.assertEqual(data["current"], "v1")
        v1_state = CPS.registry_state(data)
        self.assertTrue(v1_state["ready"])
        self.assertEqual(v1_state["current_snapshot_id"], "IEmFFkIngiskcfJk9MH6")
        # v2 itself (not yet current) must still report not-ready if it were selected
        v2_only = dict(data)
        v2_only["current"] = "v2"
        v2_state = CPS.registry_state(v2_only)
        self.assertFalse(v2_state["ready"])
        self.assertIn("GK-01/U63", v2_state["reason"])


if __name__ == "__main__":
    unittest.main()
