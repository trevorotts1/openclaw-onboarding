#!/usr/bin/env python3
"""Unit tests for compat_guard.py (T-39).

Run: python3 -m unittest discover -s tools/tests  (from the skill root)
 or: python3 tools/tests/test_compat_guard.py

Proves the four refusals the unit exists for:

  * compare-and-swap refuses a stale writer and leaves the record untouched;
  * a migration run twice is idempotent and the second run is a byte-identical
    no-op (sha256 compared, not assumed);
  * a record newer than this code understands is refused with a named error
    and is never downgraded;
  * a corrupt record is reported, not repaired silently, and its bytes do not
    change.

Each refusal is paired with a control that shows the same instrument accepts a
valid record, so a passing suite cannot come from a check that always fails.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import compat_guard as guard  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="compat-test-")
        self.dir = Path(self._td.name)
        self.path = self.dir / "record.json"

    def tearDown(self):
        self._td.cleanup()

    def write(self, record):
        self.path.write_text(json.dumps(record), encoding="utf-8")

    def good(self, version=1, generation=0, data=None):
        self.write({
            "version": version,
            "writer_generation": generation,
            "data": {} if data is None else data,
        })

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))


class TestControl(_Base):
    """Controls: the same checks accept a valid record."""

    def test_valid_record_reads(self):
        self.good(version=2, generation=4, data={"a": 1})
        rec = guard.read_record(self.path)
        self.assertEqual(rec["version"], 2)
        self.assertEqual(rec["writer_generation"], 4)
        self.assertEqual(rec["data"], {"a": 1})

    def test_record_at_known_version_is_compatible(self):
        self.good(version=2)
        guard.assert_compatible(guard.read_record(self.path), 2)  # must not raise

    def test_canonical_bytes_are_deterministic(self):
        rec = {"version": 1, "writer_generation": 0, "data": {"b": 2, "a": 1}}
        self.assertEqual(guard.canonical_bytes(rec), guard.canonical_bytes(dict(rec)))
        self.assertTrue(guard.canonical_bytes(rec).endswith(b"\n"))


class TestCompareAndSwap(_Base):
    def test_current_generation_is_accepted_and_bumped(self):
        self.good(generation=3, data={"n": 1})
        out = guard.cas_update(
            self.path, 3, lambda data: {**data, "n": 2}, known_version=1
        )
        self.assertEqual(out["writer_generation"], 4)
        self.assertEqual(self.read()["data"]["n"], 2)
        self.assertEqual(self.read()["writer_generation"], 4)

    def test_stale_writer_is_refused_and_writes_nothing(self):
        self.good(generation=7, data={"n": 1})
        before = _sha(self.path)
        with self.assertRaises(guard.StaleWriteError) as ctx:
            guard.cas_update(
                self.path, 6, lambda data: {**data, "n": 2}, known_version=1
            )
        self.assertEqual(ctx.exception.expected, 6)
        self.assertEqual(ctx.exception.actual, 7)
        self.assertEqual(_sha(self.path), before, "a refused CAS must not write")
        self.assertEqual(self.read()["data"]["n"], 1)

    def test_cas_refuses_a_record_newer_than_known(self):
        self.good(version=5, generation=0)
        before = _sha(self.path)
        with self.assertRaises(guard.NewerThanKnownError) as ctx:
            guard.cas_update(self.path, 0, lambda d: d, known_version=4)
        self.assertEqual((ctx.exception.on_disk, ctx.exception.known), (5, 4))
        self.assertEqual(_sha(self.path), before)

    def test_cas_refuses_to_roll_back_protected_state(self):
        self.good(generation=0, data={"consent": "granted", "n": 1})
        before = _sha(self.path)
        with self.assertRaises(guard.ProtectedStateError) as ctx:
            guard.cas_update(
                self.path, 0, lambda d: {"n": 2}, known_version=1
            )
        self.assertIn("consent", ctx.exception.keys)
        self.assertEqual(_sha(self.path), before)

    def test_cas_preserves_unknown_top_level_keys(self):
        self.write({
            "version": 1,
            "writer_generation": 0,
            "data": {"n": 1},
            "future_field": {"keep": True},
        })
        guard.cas_update(self.path, 0, lambda d: {**d, "n": 2}, known_version=1)
        self.assertEqual(self.read()["future_field"], {"keep": True})

    def test_cas_refuses_when_mutate_returns_non_dict(self):
        self.good(generation=0)
        before = _sha(self.path)
        with self.assertRaises(guard.CompatError):
            guard.cas_update(self.path, 0, lambda d: ["nope"], known_version=1)
        self.assertEqual(_sha(self.path), before)


class TestMigration(_Base):
    @staticmethod
    def _steps():
        return {
            1: lambda d: {**d, "v1": True},
            2: lambda d: {**d, "v2": True},
            3: lambda d: {**d, "v3": True},
        }

    def test_applies_only_pending_steps(self):
        self.good(version=1)
        report = guard.migrate(self.path, self._steps(), known_version=3)
        self.assertEqual(report["applied"], [2, 3])
        self.assertEqual(report["from_version"], 1)
        self.assertEqual(report["to_version"], 3)
        self.assertFalse(report["noop"])
        data = self.read()["data"]
        self.assertNotIn("v1", data, "a step at or below the current version must not replay")
        self.assertTrue(data["v2"])
        self.assertTrue(data["v3"])

    def test_second_run_is_byte_identical_noop(self):
        self.good(version=1)
        guard.migrate(self.path, self._steps(), known_version=3)
        first = _sha(self.path)
        report = guard.migrate(self.path, self._steps(), known_version=3)
        self.assertTrue(report["noop"])
        self.assertFalse(report["bytes_written"])
        self.assertEqual(report["applied"], [])
        self.assertEqual(
            _sha(self.path), first, "the second run must not change a single byte"
        )

    def test_no_pending_steps_never_writes(self):
        self.write({
            "version": 3,
            "writer_generation": 0,
            "data": {"a": 1},
            "unformatted": "kept",
        })
        # Deliberately non-canonical bytes: a write would reorder/reindent them.
        before = _sha(self.path)
        report = guard.migrate(self.path, self._steps(), known_version=3)
        self.assertTrue(report["noop"])
        self.assertEqual(_sha(self.path), before)

    def test_newer_record_is_refused_with_named_error(self):
        self.good(version=9)
        before = _sha(self.path)
        with self.assertRaises(guard.NewerThanKnownError) as ctx:
            guard.migrate(self.path, self._steps(), known_version=3)
        self.assertEqual(ctx.exception.on_disk, 9)
        self.assertEqual(ctx.exception.known, 3)
        self.assertIn("newer than known version", str(ctx.exception))
        self.assertEqual(_sha(self.path), before, "no downgrade may be written")

    def test_step_above_known_version_is_not_applied(self):
        self.good(version=1)
        guard.migrate(self.path, self._steps(), known_version=2)
        self.assertEqual(self.read()["version"], 2)
        self.assertNotIn("v3", self.read()["data"])

    def test_migration_may_not_drop_protected_state(self):
        self.good(version=1, data={"consent": "granted", "counters": {"sent": 3}})
        before = _sha(self.path)
        with self.assertRaises(guard.ProtectedStateError) as ctx:
            guard.migrate(
                self.path,
                {2: lambda d: {"other": True}},
                known_version=2,
            )
        self.assertEqual(set(ctx.exception.keys), {"consent", "counters"})
        self.assertEqual(_sha(self.path), before, "a refused migration must not write")

    def test_migration_preserves_unknown_data_keys(self):
        self.good(version=1, data={"future": {"keep": 1}})
        guard.migrate(
            self.path, {2: lambda d: {**d, "v2": True}}, known_version=2
        )
        self.assertEqual(self.read()["data"]["future"], {"keep": 1})


class TestForwardRepair(_Base):
    def test_corrupt_record_is_reported_not_repaired(self):
        self.path.write_text('{"version": "not-an-int", "data": {}}', encoding="utf-8")
        before = _sha(self.path)
        report = guard.forward_repair(self.path, {}, known_version=3)
        self.assertEqual(report["status"], "corrupt")
        self.assertFalse(report["wrote"])
        self.assertEqual(report["action"], "none")
        self.assertIn("writer_generation: required int >= 0", report["issues"])
        self.assertIn("version: required int >= 1", report["issues"])
        self.assertEqual(_sha(self.path), before, "a corrupt record is left untouched")

    def test_unparseable_json_is_reported(self):
        self.path.write_text("{not json", encoding="utf-8")
        before = _sha(self.path)
        report = guard.forward_repair(self.path, {}, known_version=3)
        self.assertEqual(report["status"], "corrupt")
        self.assertTrue(any("not valid JSON" in issue for issue in report["issues"]))
        self.assertEqual(_sha(self.path), before)

    def test_newer_than_known_is_reported_and_untouched(self):
        self.good(version=6)
        before = _sha(self.path)
        report = guard.forward_repair(self.path, {}, known_version=3)
        self.assertEqual(report["status"], "newer_than_known")
        self.assertEqual(report["on_disk_version"], 6)
        self.assertEqual(report["known_version"], 3)
        self.assertFalse(report["wrote"])
        self.assertEqual(_sha(self.path), before)

    def test_missing_record_is_reported(self):
        report = guard.forward_repair(self.path, {}, known_version=3)
        self.assertEqual(report["status"], "missing")
        self.assertFalse(report["wrote"])

    def test_old_record_is_advanced_once_then_noop(self):
        self.good(version=1, data={"n": 1})
        steps = {2: lambda d: {**d, "migrated": True}}
        report = guard.forward_repair(self.path, steps, known_version=2)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["wrote"])
        self.assertEqual(report["action"], "migrated")
        second = guard.forward_repair(self.path, steps, known_version=2)
        self.assertEqual(second["status"], "ok")
        self.assertFalse(second["wrote"])
        self.assertEqual(second["action"], "none")


if __name__ == "__main__":
    unittest.main(verbosity=2)
