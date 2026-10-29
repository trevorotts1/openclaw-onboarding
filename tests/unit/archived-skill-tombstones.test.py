#!/usr/bin/env python3
"""Unit tests for the retired-skill registry, docs/archived-skill-tombstones.json.

History. T2-12 first made the retired `*-ARCHIVED` folders harmless tombstones. That was
not enough: OpenClaw rescans the skills folder constantly and logs an error for every
folder it cannot load, and a retired folder carries no description, so each one logged
234 errors in 13 hours on a real client box. The repository therefore no longer ships any
`*-ARCHIVED` folder, and update-skills.sh / scripts/remove-archived-skills.sh move the
copies older rolls left on boxes out of the skills folder.

The registry stays, because two live mechanisms read it: update-skills.sh moves the old
LIVE copy of each retired skill aside, and scripts/onboarding-state.sh drops the stale
onboarding-state key. These tests keep it honest, in both directions:

  * a `*-ARCHIVED` folder reappearing at the repository root turns this suite RED, so a
    retired skill can never be shipped again by accident;
  * a registry entry that is malformed, names a successor that does not exist, or lost the
    commit that last shipped the folder turns it RED, so a retired skill stays restorable.

Run:
    python3 tests/unit/archived-skill-tombstones.test.py
    or: pytest tests/unit/archived-skill-tombstones.test.py
"""
from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_MANIFEST_PATH = _REPO_ROOT / "docs" / "archived-skill-tombstones.json"
assert _MANIFEST_PATH.is_file(), f"manifest not found at {_MANIFEST_PATH}"

_ENTRIES = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))["archived"]

_KEY_RE = re.compile(r"^[0-9]+-.+-ARCHIVED$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _archived_dirs(root: Path):
    return sorted(
        name for name in os.listdir(root)
        if name.endswith("-ARCHIVED") and (root / name).is_dir()
    )


class TestNoArchivedFolderShips(unittest.TestCase):
    def test_no_archived_directory_at_the_repository_root(self):
        self.assertEqual(
            _archived_dirs(_REPO_ROOT), [],
            "a *-ARCHIVED folder is back at the repository root. Retired skills are not "
            "shipped: OpenClaw logs an error on every skills rescan for each one. Delete "
            "the folder and record it in docs/archived-skill-tombstones.json instead.",
        )


class TestRegistryIsWellFormed(unittest.TestCase):
    def test_registry_is_not_empty(self):
        self.assertTrue(_ENTRIES, "registry is empty: the live copies would never be retired")

    def test_every_key_is_a_numbered_archived_name(self):
        for key in sorted(_ENTRIES):
            with self.subTest(key=key):
                self.assertRegex(key, _KEY_RE)

    def test_every_successor_is_a_live_skill_folder(self):
        for key, entry in sorted(_ENTRIES.items()):
            with self.subTest(key=key):
                successor = entry.get("successor", "")
                self.assertTrue(successor, f"{key} names no successor")
                self.assertTrue(
                    (_REPO_ROOT / successor).is_dir(),
                    f"{key} names successor {successor!r}, which is not a folder at the repository root",
                )
                self.assertFalse(successor.endswith("-ARCHIVED"),
                                 f"{key} names another retired skill as its successor")

    def test_every_entry_records_the_commit_that_last_shipped_it(self):
        for key, entry in sorted(_ENTRIES.items()):
            with self.subTest(key=key):
                self.assertRegex(
                    entry.get("last_commit", ""), _SHA_RE,
                    f"{key} has no 40-character last_commit: the retired skill could not be restored",
                )

    def test_a_retired_skill_is_not_also_a_live_folder(self):
        for key in sorted(_ENTRIES):
            live = key[: -len("-ARCHIVED")]
            with self.subTest(key=key):
                self.assertFalse(
                    (_REPO_ROOT / live).is_dir(),
                    f"{live} is registered as retired but still ships as a live skill folder",
                )


class TestTheCheckCanGoRed(unittest.TestCase):
    """Directed negative cases: prove the rules catch the defects they name."""

    def test_a_planted_archived_folder_is_detected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "99-gone-ARCHIVED").mkdir()
            (root / "98-live").mkdir()
            (root / "97-archive-tools").mkdir()
            self.assertEqual(_archived_dirs(root), ["99-gone-ARCHIVED"])

    def test_a_malformed_key_or_sha_is_rejected(self):
        self.assertIsNone(_KEY_RE.match("11-superdesign"))
        self.assertIsNone(_KEY_RE.match("superdesign-ARCHIVED"))
        self.assertIsNone(_SHA_RE.match("83f54c2"))
        self.assertIsNone(_SHA_RE.match("G" * 40))


if __name__ == "__main__":
    unittest.main(verbosity=2)
