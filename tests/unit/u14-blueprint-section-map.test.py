#!/usr/bin/env python3
"""tests/unit/u14-blueprint-section-map.test.py — U14 (A-U14, master-spec v2
§A.1.3 / D-A4 Option A, RATIFIED): Blueprint-generation reconciliation.

Proves the shipped crosswalk fixes the Section-4 load-contract hazard:

  (a) `personas/_section-map.json` maps ALL 99 blueprints (100% coverage,
      including the 4 em-dash-heading off-template blueprints) to their
      template generation + governance-section number, and the committed
      file is byte-identical to what the generator produces right now (no
      hand-edited drift).

  (b) a doer loading "Section 4" via the shared entry point
      (`shared-utils/persona_for_job.py::section4_excerpt`) receives the
      real Agent Governance Framework material under BOTH template
      generations — fixture-tested per generation against real, committed
      blueprints (Template A -> Section 8; Template B -> Section 4) — not
      the wrong section ("Key Principles") that a naive literal-"Section 4"
      grab would return for Template A.

  (c) Skill 23's CHANGELOG.md names `persona_blend.py`, W7, P4-01, and P4-02
      with their versions (documentation-debt backfill).

Run:
    python3 tests/unit/u14-blueprint-section-map.test.py
    or: pytest tests/unit/u14-blueprint-section-map.test.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent         # repo root
_SKILL22 = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system"
_PERSONA_ROOT = _SKILL22 / "personas"
_MAP_PATH = _PERSONA_ROOT / "_section-map.json"
_GENERATOR = _SKILL22 / "scripts" / "build-section-map.py"
_SHARED = _REPO_ROOT / "shared-utils"
_SKILL23_CHANGELOG = _REPO_ROOT / "23-ai-workforce-blueprint" / "CHANGELOG.md"

assert _PERSONA_ROOT.is_dir(), f"persona root not found at {_PERSONA_ROOT}"
assert _MAP_PATH.exists(), f"_section-map.json not found at {_MAP_PATH}"
assert _GENERATOR.exists(), f"generator not found at {_GENERATOR}"

sys.path.insert(0, str(_SHARED))
_spec = importlib.util.spec_from_file_location("persona_for_job", _SHARED / "persona_for_job.py")
pfj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pfj)


class SectionMapCoverage(unittest.TestCase):
    """(a) 100% coverage of the 99 blueprints, including the 4 off-template
    (em-dash) blueprints, and the map is not hand-edited drift."""

    @classmethod
    def setUpClass(cls):
        cls.section_map = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
        cls.persona_dirs = sorted(
            p.name for p in _PERSONA_ROOT.iterdir()
            if p.is_dir() and (p / "persona-blueprint.md").exists())

    def test_every_blueprint_on_disk_has_a_map_entry(self):
        mapped = set(self.section_map["personas"].keys())
        missing = [p for p in self.persona_dirs if p not in mapped]
        self.assertEqual(missing, [], f"blueprints missing from _section-map.json: {missing}")

    def test_map_has_no_stale_entries(self):
        on_disk = set(self.persona_dirs)
        mapped = set(self.section_map["personas"].keys())
        stale = sorted(mapped - on_disk)
        self.assertEqual(stale, [], f"map entries with no on-disk blueprint: {stale}")

    def test_total_is_99(self):
        self.assertEqual(len(self.persona_dirs), 99)
        self.assertEqual(self.section_map["_meta"]["total_personas"], 99)

    def test_template_counts_match_spec_inventory(self):
        # master-spec v2 §A.1.3: 28 Template-A, 67 Template-B (hyphen) + 4
        # Template-B em-dash variant = 71 total under "B".
        counts = self.section_map["_meta"]["template_counts"]
        self.assertEqual(counts.get("A"), 28)
        self.assertEqual(counts.get("B"), 71)
        self.assertNotIn("off-template", counts,
                          "the 4 em-dash blueprints must resolve to template B "
                          "(structural match), not remain unclassified")

    def test_four_em_dash_blueprints_inventoried_and_resolved(self):
        em_dash_ids = {"brunson-marketing-secrets-blackbook", "opara-color-works",
                        "rohde-the-sketchnote-workbook",
                        "russell-brunson-the-funnel-hackers-cookbook"}
        for pid in em_dash_ids:
            entry = self.section_map["personas"].get(pid)
            self.assertIsNotNone(entry, f"{pid} missing from map")
            self.assertEqual(entry["heading_style"], "em-dash")
            self.assertEqual(entry["template"], "B")
            self.assertEqual(entry["governance_section"], 4)

    def test_governance_section_resolves_for_98_of_99(self):
        # 1 documented edge case (butow-ultimate-guide-social-media-marketing,
        # a 7-section compact variant with no A-D governance subsections)
        # legitimately has no governance_section; every other persona must
        # resolve one — an unexplained gap is a real coverage regression.
        unresolved = [pid for pid, e in self.section_map["personas"].items()
                      if e.get("governance_section") is None]
        self.assertEqual(unresolved, ["butow-ultimate-guide-social-media-marketing"],
                          f"unexpected unresolved governance_section entries: {unresolved}")

    def test_committed_map_matches_generator_output(self):
        """The generator's --check mode is the drift lock: fails loudly if the
        committed file was hand-edited out of sync with the blueprints."""
        proc = subprocess.run([sys.executable or "python3", str(_GENERATOR), "--check"],
                              capture_output=True, text=True, cwd=str(_REPO_ROOT))
        self.assertEqual(proc.returncode, 0,
                          f"_section-map.json is stale vs the generator:\n{proc.stdout}\n{proc.stderr}")


class LoadContractHazardFixture(unittest.TestCase):
    """(b) a doer loading "Section 4" receives governance material under
    BOTH generations — one fixture case per generation, against real
    committed blueprints (not synthetic fixtures — the real 99-blueprint
    library IS the fixture set here)."""

    def test_template_a_section4_excerpt_resolves_to_governance_not_key_principles(self):
        # aliche-get-good-with-money: Template A, Section 4 = "Key
        # Principles" (WRONG target), Section 8 = the real Agent Governance
        # Framework (RIGHT target, 8A-8D lettered subsections present).
        excerpt = pfj.section4_excerpt("aliche-get-good-with-money", max_chars=6000)
        self.assertTrue(excerpt, "empty excerpt for a Template-A persona with a known governance section")
        self.assertIn("Section 8", excerpt)
        self.assertIn("Agent Governance Framework", excerpt)
        self.assertIn("8A", excerpt)
        self.assertNotIn("Key Principles", excerpt,
                          "hazard regression: literal Section 4 ('Key Principles') "
                          "leaked instead of the resolved governance section")

    def test_template_b_section4_excerpt_still_resolves_to_section_4(self):
        # hormozi-100m-offers: Template B, Section 4 IS the Agent Governance
        # Framework already — must stay unchanged (byte-for-byte target).
        excerpt = pfj.section4_excerpt("hormozi-100m-offers", max_chars=6000)
        self.assertTrue(excerpt)
        self.assertIn("Section 4", excerpt)
        self.assertIn("Agent Governance Framework", excerpt)
        self.assertIn("4A", excerpt)

    def test_em_dash_template_b_variant_also_resolves_correctly(self):
        excerpt = pfj.section4_excerpt("brunson-marketing-secrets-blackbook", max_chars=6000)
        self.assertTrue(excerpt)
        self.assertIn("Agent Governance Framework", excerpt)
        self.assertIn("4A", excerpt)

    def test_edge_case_persona_degrades_honestly_never_crashes(self):
        # butow-ultimate-guide-social-media-marketing has no governance
        # section at all (documented). Must not raise, must not fabricate
        # governance content that isn't in the file — falls back to literal
        # Section 4 ("Coaching Mode" prose, honestly labeled by the map).
        excerpt = pfj.section4_excerpt("butow-ultimate-guide-social-media-marketing", max_chars=6000)
        self.assertTrue(excerpt, "edge-case persona must still degrade to SOME real "
                                  "on-file content, never an exception or silent empty "
                                  "string when literal Section 4 exists")
        self.assertIn("Section 4", excerpt)

    def test_persona_absent_from_map_falls_back_to_literal_section_4(self):
        # Back-compat path: an id with no map entry at all behaves exactly
        # like pre-U14 code (byte-for-byte the old literal-grab behavior).
        excerpt = pfj.section4_excerpt("no-such-persona-id-at-all", max_chars=6000)
        self.assertEqual(excerpt, "", "unresolvable persona must return empty, not raise")

    def test_map_absent_entirely_degrades_to_pre_u14_behavior(self):
        """Simulate an older/back-compat checkout with no _section-map.json:
        point the module's seed persona root at a temp copy of ONE real
        Template-A blueprint with the map file deleted, and confirm
        section4_excerpt falls back to the literal Section 4 grab (the
        exact pre-U14 shape) instead of raising or silently returning
        governance content it has no map-based right to claim."""
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_root = Path(d) / "personas"
            tmp_root.mkdir()
            src = _PERSONA_ROOT / "aliche-get-good-with-money"
            dst = tmp_root / "aliche-get-good-with-money"
            shutil.copytree(src, dst)
            # deliberately do NOT copy _section-map.json into tmp_root

            orig_seed_root = pfj._SEED_PERSONA_ROOT
            orig_seed_map = pfj._SEED_SECTION_MAP
            orig_cache = pfj._SECTION_MAP_CACHE
            try:
                pfj._SEED_PERSONA_ROOT = tmp_root
                pfj._SEED_SECTION_MAP = tmp_root / "_section-map.json"
                pfj._SECTION_MAP_CACHE = None  # force a fresh (miss) load
                excerpt = pfj.section4_excerpt("aliche-get-good-with-money", max_chars=6000)
                self.assertIn("Section 4", excerpt)
                self.assertIn("Key Principles", excerpt,
                              "map-absent back-compat path must reproduce the exact "
                              "pre-U14 literal-Section-4 grab")
            finally:
                pfj._SEED_PERSONA_ROOT = orig_seed_root
                pfj._SEED_SECTION_MAP = orig_seed_map
                pfj._SECTION_MAP_CACHE = orig_cache


class Skill23ChangelogBackfill(unittest.TestCase):
    """(c) Skill 23's CHANGELOG.md names persona_blend.py, W7, P4-01, and
    P4-02 with their versions — closing the documentation-debt gap recorded
    in master-spec v2 §A.1.8 ("zero hits" pre-U14)."""

    @classmethod
    def setUpClass(cls):
        assert _SKILL23_CHANGELOG.exists(), f"Skill 23 CHANGELOG.md not found at {_SKILL23_CHANGELOG}"
        cls.text = _SKILL23_CHANGELOG.read_text(encoding="utf-8", errors="replace")

    def test_persona_blend_named(self):
        self.assertIn("persona_blend.py", self.text)

    def test_w7_named(self):
        self.assertIn("W7", self.text)

    def test_p4_01_named(self):
        self.assertIn("P4-01", self.text)

    def test_p4_02_named(self):
        self.assertIn("P4-02", self.text)

    def test_each_backfilled_entry_carries_a_version_heading(self):
        # every backfilled marker must have AT LEAST ONE occurrence that sits
        # under a real "## [vX.Y.Z]" release heading (i.e. inside a genuine
        # dated entry body, not just mentioned in prose/comments ABOVE the
        # first heading — a dangling reference with no version context).
        version_heading_re = re.compile(r"^##\s+\[?v\d+\.\d+\.\d+\]?", re.MULTILINE)
        headings = [m.start() for m in version_heading_re.finditer(self.text)]
        self.assertTrue(headings, "CHANGELOG.md has no versioned '## vX.Y.Z' headings at all")
        for marker in ("persona_blend.py", "W7", "P4-01", "P4-02"):
            occurrences = [m.start() for m in re.finditer(re.escape(marker), self.text)]
            self.assertTrue(occurrences, f"{marker!r} not found in CHANGELOG.md")
            under_a_heading = [idx for idx in occurrences if any(h < idx for h in headings)]
            self.assertTrue(under_a_heading,
                             f"no occurrence of {marker!r} sits under a versioned heading")


if __name__ == "__main__":
    unittest.main(verbosity=2)
