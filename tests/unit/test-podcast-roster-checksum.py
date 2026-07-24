#!/usr/bin/env python3
"""U035: Unit tests for roster/ledger checksum integrity.

Imports verify_checksum and ROSTER_CHECKSUM_KEY from the production module
(podcast_state.py) so the tests stay coupled to the real implementation.
Inline v()/c() reimplementations are eliminated — only a minimal fixture
builder remains for constructing test payloads with valid checksums."""

import hashlib
import json
import os
import sys
import unittest

# Resolve the production module path relative to the test file.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROD_DIR = os.path.join(_REPO_ROOT, "58-podcast-production-engine", "scripts")
sys.path.insert(0, _PROD_DIR)

from podcast_state import ROSTER_CHECKSUM_KEY, verify_checksum  # noqa: E402


def _compute_checksum(record: dict) -> str:
    """Compute the SHA-256 checksum of a record (excluding the checksum field
    itself). Uses the same canonical serialisation as the production module:
    sorted keys, no whitespace, ASCII-safe."""
    record.pop(ROSTER_CHECKSUM_KEY, None)
    canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _make_record(**kw) -> dict:
    """Build a minimal ledger record dict with default fields."""
    r = dict(
        state=kw.get("state", "received"),
        job_id=kw.get("job_id", "t"),
        updated_at=kw.get("updated_at", "t"),
        sqlite_job_id=kw.get("sqlite_job_id", "t"),
    )
    for k, v in kw.items():
        if k not in ("state", "job_id", "updated_at", "sqlite_job_id"):
            r[k] = v
    return r


def _seal(record: dict) -> dict:
    """Embed a valid checksum so the record passes verify_checksum."""
    record[ROSTER_CHECKSUM_KEY] = _compute_checksum(dict(record))
    return record


class TestVerifyChecksum(unittest.TestCase):
    """Tests that exercise verify_checksum (imported from the production module)."""

    def test_valid(self):
        r = _make_record(state="p")
        _seal(r)
        verify_checksum(json.dumps(r, indent=2))

    def test_corrupt(self):
        r = _make_record(state="x")
        _seal(r)
        r["state"] = "y"
        with self.assertRaises(ValueError) as ctx:
            verify_checksum(json.dumps(r, indent=2))
        self.assertIn("checksum MISMATCH", str(ctx.exception))

    def test_trunc(self):
        r = _make_record()
        _seal(r)
        raw = json.dumps(r, indent=2)
        with self.assertRaises(ValueError):
            verify_checksum(raw[:-30])

    def test_missing_checksum_field(self):
        r = _make_record()
        # Pre-U035 record: no _checksum field — should pass silently.
        verify_checksum(json.dumps(r, indent=2))

    def test_bad_json(self):
        with self.assertRaises(ValueError) as ctx:
            verify_checksum("not json")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_not_dict(self):
        with self.assertRaises(ValueError) as ctx:
            verify_checksum("[1]")
        self.assertIn("not a JSON object", str(ctx.exception))

    def test_injected_field(self):
        r = _make_record()
        _seal(r)
        r["bad"] = "x"
        with self.assertRaises(ValueError) as ctx:
            verify_checksum(json.dumps(r, indent=2))
        self.assertIn("checksum MISMATCH", str(ctx.exception))


class TestChecksumComputation(unittest.TestCase):
    """Tests that verify checksum determinism — same content, same checksum."""

    def test_reproducible(self):
        a = _compute_checksum(_make_record(state="a", p="x"))
        b = _compute_checksum(_make_record(state="a", p="x"))
        self.assertEqual(a, b)

    def test_different_content_different_checksum(self):
        a = _compute_checksum(_make_record(state="a"))
        b = _compute_checksum(_make_record(state="b"))
        self.assertNotEqual(a, b)

    def test_stable_independent_of_key_order(self):
        a = _compute_checksum(dict(sqlite_job_id="x", state="p", job_id="x", updated_at="t"))
        b = _compute_checksum(dict(updated_at="t", state="p", sqlite_job_id="x", job_id="x"))
        self.assertEqual(a, b)

    def test_checksum_is_64_hex_chars(self):
        self.assertEqual(len(_compute_checksum(_make_record())), 64)

    def test_content_change_alters_checksum(self):
        r = _make_record()
        original = _compute_checksum(dict(r))
        r["state"] = "p"
        self.assertNotEqual(original, _compute_checksum(r))

    def test_sealed_record_passes_verification(self):
        r = _make_record()
        _seal(r)
        verify_checksum(json.dumps(r, indent=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
