#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: roster atomic write + backup (U046)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB: the roster functions are pure
# file I/O driven in a temp directory. Proves F46: the roster is written
# atomically (temp + fsync + rename) with a timestamped backup of the previous
# copy kept for manual recovery, so an interrupted write can never corrupt the
# roster.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_roster_atomic_write.py
# =============================================================================
"""Deterministic tests for the roster atomic write + backup (U046 / F46)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podcast_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("podcast_state", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: Python 3.14's dataclass machinery resolves the
    # defining module via sys.modules during class creation.
    sys.modules["podcast_state"] = mod
    spec.loader.exec_module(mod)
    return mod


PS = _load_module()

SAMPLE = [
    {"episode_number": 1, "title": "Pilot", "media_key": "k1"},
    {"episode_number": 2, "title": "Ep 2", "media_key": "k2"},
]


class RosterAtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="podcast-u046-")
        self.roster = os.path.join(self.tmp, "episode-roster.json")

    # -- required test 1: a write creates a timestamped backup --------------
    def test_write_creates_timestamped_backup(self):
        PS.write_roster(self.roster, SAMPLE)
        # Second write must back up the first.
        PS.write_roster(self.roster, SAMPLE + [{"episode_number": 3}])
        backups = [f for f in os.listdir(self.tmp)
                   if f.startswith("episode-roster.json.bak.") and f.endswith(".json")]
        self.assertGreaterEqual(len(backups), 1, "no timestamped backup was created")
        # The backup holds the FIRST write's content.
        with open(os.path.join(self.tmp, backups[0]), encoding="utf-8") as fh:
            backed_up = json.load(fh)
        self.assertEqual(backed_up["entries"], SAMPLE)

    # -- required test 2: a write failure leaves the original unchanged -----
    def test_write_failure_preserves_original(self):
        PS.write_roster(self.roster, SAMPLE)
        original = open(self.roster, encoding="utf-8").read()
        # Simulate a failure at the final atomic step (e.g. disk full / EIO).
        with mock.patch("os.replace", side_effect=OSError("simulated disk full")):
            with self.assertRaises(PS.RosterWriteError):
                PS.write_roster(self.roster, [{"episode_number": 99}])
        # The original roster is byte-for-byte unchanged.
        self.assertEqual(open(self.roster, encoding="utf-8").read(), original)
        # No torn temp file is left behind.
        temps = [f for f in os.listdir(self.tmp) if ".tmp." in f]
        self.assertEqual(temps, [], f"temp file leaked: {temps}")

    # -- round trip ----------------------------------------------------------
    def test_write_read_round_trip(self):
        PS.write_roster(self.roster, SAMPLE)
        self.assertEqual(PS.read_roster(self.roster), SAMPLE)

    # -- backup rotation keeps only the last N ------------------------------
    def test_backup_rotation_keeps_last_n(self):
        for i in range(8):
            PS.write_roster(self.roster, [{"episode_number": i}], keep_backups=5)
            # ensure distinct epochs even within the same second
            import time as _t; _t.sleep(0.001)
        backups = [f for f in os.listdir(self.tmp)
                   if f.startswith("episode-roster.json.bak.") and f.endswith(".json")]
        self.assertLessEqual(len(backups), 5, f"rotation kept {len(backups)} backups")

    # -- edge: first write (no prior roster) creates no backup --------------
    def test_first_write_creates_no_backup(self):
        PS.write_roster(self.roster, SAMPLE)
        backups = [f for f in os.listdir(self.tmp) if ".bak." in f]
        self.assertEqual(backups, [], "first write should not create a backup")

    # -- edge: corrupt roster raises on read --------------------------------
    def test_read_corrupt_raises(self):
        with open(self.roster, "w", encoding="utf-8") as fh:
            fh.write("{ not valid json")
        with self.assertRaises((PS.RosterWriteError, json.JSONDecodeError)):
            PS.read_roster(self.roster)

    def test_read_wrong_shape_raises(self):
        with open(self.roster, "w", encoding="utf-8") as fh:
            json.dump({"not_entries": []}, fh)
        with self.assertRaises(PS.RosterWriteError):
            PS.read_roster(self.roster)

    # -- edge: missing roster raises FileNotFoundError ----------------------
    def test_read_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            PS.read_roster(os.path.join(self.tmp, "absent.json"))

    # -- the written file is valid JSON with an entries field ---------------
    def test_written_file_shape(self):
        PS.write_roster(self.roster, SAMPLE)
        with open(self.roster, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("entries", data)
        self.assertEqual(data["entries"], SAMPLE)


if __name__ == "__main__":
    unittest.main()
