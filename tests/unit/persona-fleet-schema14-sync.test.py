#!/usr/bin/env python3
"""
tests/unit/persona-fleet-schema14-sync.test.py

A-U3 spec: "the publish path (pipeline/persona_fleet.py) already carries
whole-persona fields workspace→repo per CHANGELOG v6.18.0 note — verify,
don't assume, in the unit's test."

VERIFIED FALSE prior to this unit: v6.18.0's own note only ever promised the
FOUR v1.3 fields (audiences/topics/voice_style/usable_as) survive
workspace→repo sync — `_ENRICHMENT_FIELDS` / `CANONICAL_ENTRY_FIELDS` in
persona_fleet.py did NOT include the three A-U3 schema-1.4 scalar fields
(emotional_register/audience_resonance/conversion_style), so a publish run
would have silently STRIPPED them even though orchestrator.py's D6 pipeline
stamps them on the workspace-side entry. This file hermetically proves the
fix (and would fail-first against the pre-fix `_ENRICHMENT_FIELDS` tuple).

Cases:
  1. HAPPY PATH — a workspace persona carrying all three A-U3 fields (plus
     the four v1.3 fields) syncs into the repo catalog with EVERY field
     intact — no allowlist silently drops the new fields.
  2. VOCAB-FIRST — an out-of-vocab `emotional_register` is rejected by
     `sync_categories` (SystemExit(4), no categories written) — the SAME
     controlled-vocabulary contract audiences/topics already enforce.
  3. NO-WEAKENING — repo-side A-U3 enrichment already present on an entry
     SURVIVES a workspace sync whose (older-shape) workspace entry does not
     itself carry those fields — mirrors the existing v1.3
     "preserve any enrichment the workspace sync doesn't supply" contract,
     extended to the three new fields.

Run:
    python3 tests/unit/persona-fleet-schema14-sync.test.py
    or: pytest tests/unit/persona-fleet-schema14-sync.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_PF = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system" / "pipeline" / "persona_fleet.py"
assert _PF.is_file(), f"required file not found at {_PF}"


def _load_by_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PersonaFleetSchema14Sync(unittest.TestCase):
    def setUp(self):
        self.pf = _load_by_path(_PF, "persona_fleet_schema14_under_test")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.ws_path = self.tmp / "workspace-persona-categories.json"
        self.repo_path = self.tmp / "repo-persona-categories.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, path, obj):
        path.write_text(json.dumps(obj, indent=2))

    def _base_repo(self, **extra_top):
        base = {
            "schemaVersion": "1.4",
            "domainTags": ["leadership", "coaching"],
            "perspectiveTags": [],
            "audienceTags": ["some-audience"],
            "topicTags": ["some-topic"],
            "emotionalRegisterTags": ["tough-love", "warm-encouragement"],
            "audienceResonanceTags": ["challenged-to-rise"],
            "conversionStyleTags": ["challenge-close"],
            "personas": {},
        }
        base.update(extra_top)
        return base

    # ── 1. HAPPY PATH — all three A-U3 fields survive the sync ─────────────
    def test_schema14_fields_survive_workspace_to_repo_sync(self):
        self._write(self.ws_path, {
            "personas": {
                "test-persona-s14": {
                    "author": "Test Author", "book": "Test Book",
                    "domain": ["leadership"], "perspective": [], "custom": [],
                    "audiences": ["some-audience"],
                    "topics": ["some-topic"],
                    "voice_style": {"summary": "x"},
                    "usable_as": ["audience", "topic", "task"],
                    "emotional_register": "tough-love",
                    "audience_resonance": "challenged-to-rise",
                    "conversion_style": "challenge-close",
                },
            },
        })
        self._write(self.repo_path, self._base_repo())

        changed = self.pf.sync_categories(self.ws_path, self.repo_path, ["test-persona-s14"])
        self.assertEqual(changed, ["test-persona-s14"])

        repo = json.loads(self.repo_path.read_text())
        entry = repo["personas"]["test-persona-s14"]
        self.assertEqual(entry.get("emotional_register"), "tough-love",
                          "emotional_register must survive workspace->repo sync")
        self.assertEqual(entry.get("audience_resonance"), "challenged-to-rise",
                          "audience_resonance must survive workspace->repo sync")
        self.assertEqual(entry.get("conversion_style"), "challenge-close",
                          "conversion_style must survive workspace->repo sync")
        # the v1.3 fields must ALSO still survive (no regression on the
        # existing enrichment layer while fixing the new one).
        self.assertEqual(entry.get("audiences"), ["some-audience"])
        self.assertEqual(entry.get("voice_style"), {"summary": "x"})

    # ── 2. VOCAB-FIRST — out-of-vocab scalar value rejected ────────────────
    def test_out_of_vocab_emotional_register_rejected(self):
        self._write(self.ws_path, {
            "personas": {
                "test-persona-bad": {
                    "author": "Test Author", "book": "Test Book",
                    "domain": ["leadership"], "perspective": [], "custom": [],
                    "emotional_register": "not-a-real-register",  # NOT in repo's emotionalRegisterTags
                },
            },
        })
        self._write(self.repo_path, self._base_repo())

        with self.assertRaises(SystemExit) as ctx:
            self.pf.sync_categories(self.ws_path, self.repo_path, ["test-persona-bad"])
        self.assertEqual(ctx.exception.code, 4, "controlled-vocabulary violation must exit 4")

        # no half-write: the repo categories file must be untouched.
        repo = json.loads(self.repo_path.read_text())
        self.assertNotIn("test-persona-bad", repo["personas"])

    def test_out_of_vocab_conversion_style_rejected(self):
        self._write(self.ws_path, {
            "personas": {
                "test-persona-bad2": {
                    "author": "Test Author", "book": "Test Book",
                    "domain": ["leadership"], "perspective": [], "custom": [],
                    "conversion_style": "guilt-trip-close",  # NOT in the 5-value canonical set
                },
            },
        })
        self._write(self.repo_path, self._base_repo())
        with self.assertRaises(SystemExit) as ctx:
            self.pf.sync_categories(self.ws_path, self.repo_path, ["test-persona-bad2"])
        self.assertEqual(ctx.exception.code, 4)

    # ── 3. NO-WEAKENING — repo-side A-U3 enrichment is never stripped ──────
    def test_repo_side_schema14_enrichment_preserved_when_workspace_lacks_it(self):
        # Workspace entry is an OLDER shape (no A-U3 fields at all) — mirrors
        # a 1.3 workspace box syncing against an already-1.4-enriched repo.
        self._write(self.ws_path, {
            "personas": {
                "test-persona-preserve": {
                    "author": "Test Author", "book": "Test Book",
                    "domain": ["leadership"], "perspective": [], "custom": [],
                },
            },
        })
        repo_seed = self._base_repo()
        repo_seed["personas"]["test-persona-preserve"] = {
            "author": "Test Author", "book": "Test Book",
            "domain": ["leadership"], "perspective": [], "custom": [],
            "emotional_register": "warm-encouragement",
            "audience_resonance": "challenged-to-rise",
            "conversion_style": "challenge-close",
        }
        self._write(self.repo_path, repo_seed)

        self.pf.sync_categories(self.ws_path, self.repo_path, ["test-persona-preserve"])
        repo = json.loads(self.repo_path.read_text())
        entry = repo["personas"]["test-persona-preserve"]
        self.assertEqual(entry.get("emotional_register"), "warm-encouragement",
                          "existing repo-side A-U3 enrichment must NOT be stripped by an "
                          "older-shape workspace sync")
        self.assertEqual(entry.get("conversion_style"), "challenge-close")


if __name__ == "__main__":
    unittest.main(verbosity=2)
