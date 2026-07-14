#!/usr/bin/env python3
"""Unit tests for shared-utils/persona_crosswalk.py — the D5 persona-vocabulary reconciliation.

Locks down the closure: every funnel + automation template persona ref resolves to a REAL
canonical persona-categories.json id (0 unresolved), every crosswalk target is itself canonical,
and the short template slugs map to the personas a human would expect. This is the drift guard:
if a new template adds an un-mappable persona slug, this test (and the CI drift gate) fails.

Run:
    python3 tests/unit/persona-crosswalk.test.py
    or: pytest tests/unit/persona-crosswalk.test.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
sys.path.insert(0, str(_SHARED))

_spec = importlib.util.spec_from_file_location("persona_crosswalk", _SHARED / "persona_crosswalk.py")
pc = importlib.util.module_from_spec(_spec)
sys.modules["persona_crosswalk"] = pc
_spec.loader.exec_module(pc)


class TestPersonaCrosswalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = pc.scan()
        cls.canonical = set(cls.res["canonical"])
        cls.crosswalk = pc.load_crosswalk()

    def test_zero_unresolved_refs_across_all_templates(self):
        unresolved = [r for r in self.res["rows"] if not r["ok"]]
        self.assertEqual(unresolved, [], f"unresolved persona refs: {unresolved[:5]}")
        self.assertEqual(self.res["counts"]["unresolved"], 0)

    def test_expected_library_sizes(self):
        c = self.res["counts"]
        self.assertEqual(c["funnel_templates"], 38)
        self.assertEqual(c["automation_templates"], 28)
        self.assertGreater(c["refs"], 100)      # ~181 persona refs across the two libraries

    def test_every_crosswalk_target_is_canonical(self):
        self.assertEqual(self.res["bad_targets"], [])
        for tgt in self.crosswalk["slug_map"].values():
            self.assertIn(tgt, self.canonical, tgt)
        for _, tgt in self.crosswalk["patterns"]:
            self.assertIn(tgt, self.canonical, tgt)

    def test_known_slug_resolutions(self):
        cases = {
            "funnel-architect": "brunson-marketing-secrets-blackbook",
            "copy-closer": "edwards-copywriting-secrets",
            "story-brander": "miller-building-storybrand",
            "traffic-strategist": "russell-brunson-traffic-secrets",
            "storybrand-sb7": "miller-building-storybrand",
        }
        for slug, expected in cases.items():
            target, how = pc.resolve(slug, self.canonical, self.crosswalk)
            self.assertEqual(target, expected, f"{slug} -> {target} ({how})")

    def test_freetext_book_descriptions_resolve(self):
        cases = [
            ("Russell Brunson — Traffic Secrets persona (The Traffic Strategist): Dream 100",
             "russell-brunson-traffic-secrets"),
            ("Network Marketing Secrets (Epiphany Bridge Script)", "brunson-network-marketing-secrets"),
            ("Lead Funnels Swipe File — Follow-Up Funnels", "russell-brunson-lead-funnels"),
            ("The Funnel Hacker's Cookbook (Russell Brunson)", "russell-brunson-the-funnel-hackers-cookbook"),
            ("Copywriting Secrets (Jim Edwards)", "edwards-copywriting-secrets"),
        ]
        for ref, expected in cases:
            target, how = pc.resolve(ref, self.canonical, self.crosswalk)
            self.assertEqual(target, expected, f"{ref!r} -> {target} ({how})")

    def test_canonical_ids_resolve_to_themselves(self):
        for cid in ("russell-brunson-lead-funnels", "edwards-copywriting-secrets",
                    "miller-building-storybrand", "brunson-marketing-secrets-blackbook"):
            target, how = pc.resolve(cid, self.canonical, self.crosswalk)
            self.assertEqual(target, cid)
            self.assertEqual(how, "canonical-id")


# --------------------------------------------------------------------------- #
# D5/B-D1 (RATIFIED 2026-07-14) — B-U4/U18: copy_craft_pool
# --------------------------------------------------------------------------- #
# Kills the old bare 5-surname copy-persona cap. Two-part rule: (a) VOICE is
# catalog-wide (any of the 99 personas, unrestricted); (b) the copy-craft TASK
# slot alone stays restricted to the named `copy_craft_pool` in
# persona-crosswalk.json. These tests pin all three BINARY acceptance criteria
# from the spec (B-U4, master spec line 833):
#   (a) persona_crosswalk.py --validate exits 0 with the pool present, and
#       exits non-zero when a fake pool member is seeded;
#   (b) a targeted search of BOTH SOPs finds zero remaining occurrences of the
#       bare 5-name list;
#   (c) guard-fab-qc-gate.sh fails when copy_craft_pool is deleted.
# Every test here is anti-tautological by construction: each seeds/simulates
# the ABSENCE of the feature and proves the check actually catches it, not
# just that it passes today.

_GUARD_SH = _REPO_ROOT / "scripts" / "guard-fab-qc-gate.sh"
_CROSSWALK_PY_PATH = _SHARED / "persona_crosswalk.py"
_CROSSWALK_JSON_PATH = _SHARED / "persona-crosswalk.json"
_P2_SOP = _REPO_ROOT / "06-ghl-install-pages" / "v2-autonomous-build-sop.md"
_COPY_SOP = _REPO_ROOT / "universal-sops" / "funnel-craft" / "SOP-FUNNEL-02-COPY.md"

# The EXACT bare 5-name enumeration as it read before B-U4 (v2-autonomous-build-sop.md
# :292-293, captured 2026-07-14 for regression proof — see CHANGELOG). Backtick
# immediately follows each bare surname (`bly`, not `bly-copywriters-handbook`), so
# the detector below cannot confuse the killed cap with the new full-slug pool.
_PRE_BU4_FIXTURE = (
    "2. **Verify copy persona log.** Read `working/funnels/<slug>/persona-selection-log.md`.\n"
    "   Confirm an entry exists for the copy task (distinct from the P1 funnel-spec\n"
    "   entry). The copy persona must be one of: `bly`, `wiebe`, `miller`, `hormozi`,\n"
    "   `cialdini`. If the copy persona log entry is missing, HALT and return a\n"
    "   structured handback — the Conversion Copywriter's Gate 1 requires this entry and\n"
    "   its absence means copy QC was incomplete.\n"
)

# Matches the bare, backtick-wrapped 5-name sequence in any whitespace/newline
# layout. Deliberately does NOT match `bly-copywriters-handbook` etc. (a hyphen,
# not a backtick, follows `bly` there) — see test_detector_ignores_full_pool_slugs.
_BARE_FIVE_NAME_RE = re.compile(
    r"`bly`\s*,\s*`wiebe`\s*,\s*`miller`\s*,\s*`hormozi`\s*,\s*`cialdini`"
)


class TestCopyCraftPool(unittest.TestCase):
    """Acceptance (a), first half + the pool's own definition (D5/B-D1)."""

    @classmethod
    def setUpClass(cls):
        cls.crosswalk = pc.load_crosswalk()
        cls.canonical = pc.load_canonical()

    def test_pool_key_present_and_nonempty(self):
        pool = self.crosswalk.get("copy_craft_pool")
        self.assertIsInstance(pool, list, "copy_craft_pool must be a list")
        self.assertGreater(len(pool), 0, "copy_craft_pool must not be empty")

    def test_every_pool_member_is_canonical(self):
        pool = self.crosswalk["copy_craft_pool"]
        non_canonical = [p for p in pool if p not in self.canonical]
        self.assertEqual(non_canonical, [], f"non-canonical pool members: {non_canonical}")
        # Same invariant, via the module's own bad_targets computation (the thing
        # --validate actually checks) — proves the two paths agree.
        res = pc.scan()
        self.assertEqual(res["bad_targets"], [])

    def test_pool_equals_five_plus_edwards_plus_brunson_family(self):
        """Structural re-derivation from the crosswalk's OWN slug_map/patterns
        targets (never a second hardcoded copy of the list) — ties the pool to
        the D5/B-D1 verbatim definition: 'the five... + edwards-* + the
        Brunson-family crosswalk targets', so a future crosswalk edit that adds
        a new Brunson-family target without updating the pool fails HERE."""
        five = {
            "bly-copywriters-handbook", "wiebe-copy-hackers",
            "miller-building-storybrand", "hormozi-100m-offers", "cialdini-influence",
        }
        all_targets = (set(self.crosswalk["slug_map"].values())
                       | {t for _, t in self.crosswalk["patterns"]})
        edwards_targets = {t for t in all_targets if "edwards" in t.lower()}
        brunson_targets = {t for t in all_targets if "brunson" in t.lower()}
        expected = five | edwards_targets | brunson_targets
        self.assertEqual(set(self.crosswalk["copy_craft_pool"]), expected)
        # Sanity: the family checks are not vacuously true (both non-empty).
        self.assertGreater(len(edwards_targets), 0)
        self.assertGreater(len(brunson_targets), 0)


class TestCopyCraftPoolValidateCLI(unittest.TestCase):
    """Acceptance (a): `persona_crosswalk.py --validate` exits 0 with the pool
    present, and exits non-zero when a fake pool member is seeded."""

    def test_validate_exits_zero_against_real_repo_state(self):
        r = subprocess.run(
            [sys.executable, str(_CROSSWALK_PY_PATH), "--validate"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK —", r.stdout)

    def test_validate_exits_nonzero_on_seeded_fake_pool_member(self):
        """Anti-tautology proof: seeds a REAL bad value (a non-canonical id
        appended to copy_craft_pool) into a scratch copy of the crosswalk and
        proves --validate catches it — never touches the committed file."""
        crosswalk = json.loads(_CROSSWALK_JSON_PATH.read_text(encoding="utf-8"))
        crosswalk["copy_craft_pool"] = list(crosswalk["copy_craft_pool"]) + [
            "totally-fake-nonexistent-persona-zzz"
        ]
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(crosswalk, fh)
            tmp_path = fh.name
        try:
            r = subprocess.run(
                [sys.executable, str(_CROSSWALK_PY_PATH), "--validate",
                 "--crosswalk", tmp_path],
                cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=60,
            )
            self.assertNotEqual(r.returncode, 0,
                                 "seeded fake pool member did not fail --validate")
            self.assertIn("totally-fake-nonexistent-persona-zzz", r.stdout)
            self.assertIn("CROSSWALK TARGET ERROR", r.stdout)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestBareFiveNameListRemovedFromBothSOPs(unittest.TestCase):
    """Acceptance (b): a targeted search of BOTH SOPs finds zero remaining
    occurrences of the bare 5-name list."""

    def test_detector_matches_the_known_pre_edit_text(self):
        """Anti-tautology proof of the detector itself: run it against the EXACT
        text that used to live at v2-autonomous-build-sop.md:292-293 and prove
        it matches — a detector that can't catch the known-bad case would make
        the two tests below vacuously true."""
        self.assertRegex(_PRE_BU4_FIXTURE, _BARE_FIVE_NAME_RE)

    def test_detector_ignores_full_pool_slugs(self):
        """The new copy_craft_pool text legitimately names bly/wiebe/miller/
        hormozi/cialdini too (as full canonical slugs) — the detector must NOT
        false-positive on that or every future document would be unrewritable."""
        full_slugs = ("`bly-copywriters-handbook`, `wiebe-copy-hackers`, "
                      "`miller-building-storybrand`, `hormozi-100m-offers`, "
                      "`cialdini-influence`")
        self.assertNotRegex(full_slugs, _BARE_FIVE_NAME_RE)

    def test_v2_autonomous_build_sop_has_zero_bare_list_occurrences(self):
        text = _P2_SOP.read_text(encoding="utf-8")
        matches = _BARE_FIVE_NAME_RE.findall(text)
        self.assertEqual(matches, [], f"bare 5-name list still present: {matches}")

    def test_sop_funnel_02_copy_has_zero_bare_list_occurrences(self):
        text = _COPY_SOP.read_text(encoding="utf-8")
        matches = _BARE_FIVE_NAME_RE.findall(text)
        self.assertEqual(matches, [], f"bare 5-name list still present: {matches}")

    def test_both_sops_reference_the_same_pool_key(self):
        """'referenced by BOTH Standard Operating Procedures' — a half-edit
        (only one doc pointing at copy_craft_pool) fractures the gate."""
        for path in (_P2_SOP, _COPY_SOP):
            text = path.read_text(encoding="utf-8")
            self.assertIn("copy_craft_pool", text, f"{path} does not reference copy_craft_pool")


class TestGuardFabQcGateFailsWhenPoolDeleted(unittest.TestCase):
    """Acceptance (c): guard-fab-qc-gate.sh fails when copy_craft_pool is
    deleted. Mutates the REAL crosswalk file (the guard hardcodes its path,
    same as every other check it runs) and restores it in tearDown no matter
    what — this is the same fixture-mutate-and-restore idiom the repo's other
    adversarial gate tests already use."""

    def setUp(self):
        self._original_bytes = _CROSSWALK_JSON_PATH.read_bytes()

    def tearDown(self):
        _CROSSWALK_JSON_PATH.write_bytes(self._original_bytes)
        self.assertEqual(_CROSSWALK_JSON_PATH.read_bytes(), self._original_bytes,
                          "crosswalk restore verification failed")

    def _run_guard(self):
        return subprocess.run(
            ["bash", str(_GUARD_SH)], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, timeout=120,
        )

    def test_guard_passes_with_pool_present(self):
        r = self._run_guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("copy_craft_pool present", r.stdout)

    def test_guard_fails_when_pool_key_deleted(self):
        crosswalk = json.loads(self._original_bytes.decode("utf-8"))
        del crosswalk["copy_craft_pool"]
        _CROSSWALK_JSON_PATH.write_text(json.dumps(crosswalk, indent=2), encoding="utf-8")

        r = self._run_guard()

        self.assertNotEqual(r.returncode, 0,
                             "guard did not fail when copy_craft_pool was deleted")
        self.assertIn("copy_craft_pool MISSING or empty", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
