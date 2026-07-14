#!/usr/bin/env python3
"""
tests/unit/schema14-enrichment-complete.test.py

A-U3 ACCEPT (a): "a validation script over persona-categories.json exits 0
only when N/N (current-count/current-count) personas carry all three new
fields AND validate_catalog_tags().ok == true with the extended vocab."

This IS that validation script (also runnable directly:
`python3 tests/unit/schema14-enrichment-complete.test.py`, or under
pytest/unittest) — not a mock of the acceptance criterion, the actual gate.
It reads the CANONICAL, checked-in persona-categories.json (no fixture, no
monkeypatch) so a regression in the shipped catalog fails THIS file, in CI,
the same way it would fail the operator's own box.

Checks:
  1. every persona in the catalog carries `emotional_register`,
     `audience_resonance`, `conversion_style` as non-empty strings —
     coverage == total persona count (N/N, never hardcoded to 99 so this
     stays green as the persona set grows).
  2. persona_blend.validate_catalog_tags(catalog) reports ok=True with the
     schema-1.4 vocab (emotionalRegisterTags/audienceResonanceTags/
     conversionStyleTags) actually populated and actually enforced — a
     regression that emptied the vocab arrays (silently disabling the
     membership check) is caught by asserting the vocab is non-empty AND
     that every persona's chosen value is drawn from it.
  3. `git grep -c emotional_register persona-categories.json` — reproduced
     here as a plain line-count over the file text (no shell-out needed) —
     is >= the persona count (one occurrence per enriched persona entry).

Run:
    python3 tests/unit/schema14-enrichment-complete.test.py
    or: pytest tests/unit/schema14-enrichment-complete.test.py
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_CATEGORIES = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system" / "persona-categories.json"
_PERSONA_BLEND = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts" / "persona_blend.py"

_SCALAR_FIELDS = ("emotional_register", "audience_resonance", "conversion_style")
_VOCAB_FIELDS = {
    "emotional_register": "emotionalRegisterTags",
    "audience_resonance": "audienceResonanceTags",
    "conversion_style": "conversionStyleTags",
}


def _load_by_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Schema14EnrichmentComplete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert _CATEGORIES.is_file(), f"canonical catalog not found at {_CATEGORIES}"
        cls.catalog = json.loads(_CATEGORIES.read_text())
        cls.raw_text = _CATEGORIES.read_text()
        cls.personas = cls.catalog.get("personas") or {}
        assert isinstance(cls.personas, dict) and cls.personas, \
            "catalog['personas'] must be a non-empty object"
        cls.pb = _load_by_path(_PERSONA_BLEND, "persona_blend_schema14_gate")

    # ── 1. N/N coverage ─────────────────────────────────────────────────────
    def test_every_persona_carries_all_three_fields(self):
        total = len(self.personas)
        missing = []
        for slug, entry in self.personas.items():
            if not isinstance(entry, dict):
                missing.append((slug, "entry is not an object"))
                continue
            for f in _SCALAR_FIELDS:
                v = entry.get(f)
                if not isinstance(v, str) or not v.strip():
                    missing.append((slug, f))
        self.assertEqual(
            missing, [],
            f"{len(missing)} (slug, field) gaps out of {total} personas — "
            f"A-U3 requires N/N coverage: {missing[:10]}{'...' if len(missing) > 10 else ''}"
        )
        complete = sum(
            1 for e in self.personas.values()
            if isinstance(e, dict) and all(
                isinstance(e.get(f), str) and e.get(f).strip() for f in _SCALAR_FIELDS
            )
        )
        self.assertEqual(complete, total, f"coverage must be {total}/{total}, got {complete}/{total}")

    # ── 2. the SAME rulebook the matcher/D6 pipeline enforce, and it agrees ──
    def test_validate_catalog_tags_ok_with_extended_vocab(self):
        for field, vocab_key in _VOCAB_FIELDS.items():
            vocab = self.catalog.get(vocab_key)
            self.assertIsInstance(vocab, list, f"{vocab_key} must be a list")
            self.assertTrue(vocab, f"{vocab_key} must be non-empty (extended vocab actually populated)")

        result = self.pb.validate_catalog_tags(self.catalog)
        self.assertTrue(result["ok"], f"validate_catalog_tags must pass clean: {result['errors']}")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["schema"], "1.4")
        self.assertGreaterEqual(result["checked"], len(self.personas))

        # Every persona's chosen value must actually be a member of its
        # vocab — belt-and-suspenders on top of the gate's own membership
        # check, so a vocab that got emptied AND a value that happened to
        # equal "" wouldn't both silently pass.
        for field, vocab_key in _VOCAB_FIELDS.items():
            vocab = set(self.catalog[vocab_key])
            for slug, entry in self.personas.items():
                v = entry.get(field)
                self.assertIn(v, vocab, f"{slug}: {field}={v!r} not a member of {vocab_key}")

    # ── 3. git-grep-equivalent line count ────────────────────────────────────
    def test_emotional_register_occurrence_count_at_least_persona_count(self):
        occurrences = sum(1 for line in self.raw_text.splitlines() if "emotional_register" in line)
        # +1 tolerates the top-level "emotionalRegisterTags" key line, which
        # also contains the substring "emotional_register"... it does NOT
        # (different string: emotionalRegisterTags vs emotional_register),
        # so no adjustment is actually needed — asserted directly.
        self.assertGreaterEqual(occurrences, len(self.personas),
                                f"expected >= {len(self.personas)} 'emotional_register' lines, got {occurrences}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
