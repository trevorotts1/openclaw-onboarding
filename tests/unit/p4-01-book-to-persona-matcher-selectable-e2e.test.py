#!/usr/bin/env python3
"""
tests/unit/p4-01-book-to-persona-matcher-selectable-e2e.test.py

P4-01 step 3: "Book-to-persona pipeline hardening: end-to-end test — feed a
sample book through Skill 22 → persona catalog entry with correct schema-1.3
fields + duality tags (voice-capable/topic-capable flags) → matcher can
select it. Any gap found becomes a scoped fix in the same branch."

WHY THIS TEST EXISTS (the actual gap this closes)
--------------------------------------------------
tests/unit/persona-duality-tags-pipeline.test.sh (D6/ONB22-DUALITY-TAGS)
thoroughly proves the ORCHESTRATOR-SIDE half: a well-formed '## Duality Tags'
block in a synthesized persona-blueprint.md gets stamped onto the persona's
persona-categories.json entry. It does NOT prove the other half: that the
Skill-23 matcher (persona_blend.py) can actually SELECT the resulting entry.
No existing test connects the orchestrator's WRITE path to the matcher's READ
path in one round trip — this file is that missing link, run as ONE process
against ONE temp catalog file, so a schema drift between what Skill 22 writes
and what Skill 23 reads would be caught HERE, not discovered live.

FAIL-FIRST: this exercises real, already-shipped code (orchestrator.py +
persona_blend.py) — the "would fail if the code were wrong" proof is the
NO-WEAKENING cases (malformed duality never becomes selectable) plus a
direct field-corruption probe (case 3) that DOES fail against the
unmodified matcher/orchestrator contract if that contract regresses.

Cases:
  1. HAPPY PATH — a synthesized book with a well-formed Duality Tags block
     produces a catalog entry that:
       (a) validates clean under persona_blend.validate_catalog_tags()
           (schema-1.3, 0 errors);
       (b) is the WINNING pick from match_topic_persona() for a task whose
           text overlaps its topics[];
       (c) is the WINNING pick from match_audience_persona() for a label
           overlapping its audiences[] (usable_as includes 'audience');
       (d) never wins when usable_as omits 'audience' (task-only voice
           demoted correctly to topic-only candidacy).
  2. NO-WEAKENING — a book with NO Duality Tags block (pre-enrichment) is
     NEVER selected by match_audience_persona/match_topic_persona (it has no
     audiences[]/topics[] to rank on) — proving the pipeline's own contract
     (absence = NO-OP, never a half-populated ghost candidate).
  3. NO-WEAKENING — a book with a MALFORMED Duality Tags block (out-of-vocab
     audience tag, rejected by the orchestrator's own gate) is likewise never
     selectable — the rejection is not merely logged, it actually keeps the
     persona OUT of the matcher's candidate universe.
  4. validate_catalog_tags() on the round-tripped catalog reports 0 errors —
     the SAME rulebook (persona_blend.validate_catalog_tags) the orchestrator
     gates writes through and the matcher reads through agree with each
     other on the SAME file (one rulebook, not two silently-drifting ones).

Run:
    python3 tests/unit/p4-01-book-to-persona-matcher-selectable-e2e.test.py
    or: pytest tests/unit/p4-01-book-to-persona-matcher-selectable-e2e.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent         # repo root
_SKILL22 = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system"
_SCRIPTS = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"
_PIPELINE_DIR = _SKILL22 / "pipeline"
for p in (_SCRIPTS, _PIPELINE_DIR):
    assert p.is_dir(), f"required dir not found at {p}"


def _load_by_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pb = _load_by_path(_SCRIPTS / "persona_blend.py", "persona_blend_e2e_under_test")

# orchestrator.py imports its Skill-22 siblings by relative/package-adjacent
# path — load it the same way the existing sh test does (sys.path insert),
# so its own internal imports resolve exactly as in production.
sys.path.insert(0, str(_PIPELINE_DIR))
import orchestrator as orch  # noqa: E402  (import after sys.path mutation, by design)


class BookToPersonaMatcherSelectableE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.personas_dir = self.tmp / "personas"
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        self.catpath = self.tmp / "persona-categories.json"

        # Redirect the orchestrator's write targets into the sandbox (same
        # technique as tests/unit/persona-duality-tags-pipeline.test.sh).
        self._orig_personas_dir = orch.PERSONAS_DIR
        self._orig_cat_path_fn = orch._persona_categories_path
        self._orig_log_file = orch.LOG_FILE
        self._orig_status_file = orch.STATUS_FILE
        orch.PERSONAS_DIR = self.personas_dir
        orch._persona_categories_path = lambda: self.catpath
        orch.LOG_FILE = self.tmp / "pipeline-log.txt"
        orch.STATUS_FILE = self.tmp / "pipeline-status.json"
        orch._DUALITY_TAG_WRITE_FAILURES.clear()
        orch._CATEGORIES_WRITE_FAILURES.clear()

        # Round-trip seam: point persona_blend.load_catalog at the EXACT SAME
        # file the orchestrator writes, via the same override env var
        # resolve_audience()/build_bundle() honor in production.
        self._old_env = os.environ.get("OPENCLAW_PERSONA_CATEGORIES")
        os.environ["OPENCLAW_PERSONA_CATEGORIES"] = str(self.catpath)

        self.book = {"author": "Test Author", "title": "Regression Test Book"}

    def tearDown(self):
        orch.PERSONAS_DIR = self._orig_personas_dir
        orch._persona_categories_path = self._orig_cat_path_fn
        orch.LOG_FILE = self._orig_log_file
        orch.STATUS_FILE = self._orig_status_file
        if self._old_env is None:
            os.environ.pop("OPENCLAW_PERSONA_CATEGORIES", None)
        else:
            os.environ["OPENCLAW_PERSONA_CATEGORIES"] = self._old_env
        self._tmp.cleanup()

    # ── helpers ─────────────────────────────────────────────────────────────
    def _seed_categories(self, audience_tags=None, topic_tags=None):
        self.catpath.write_text(json.dumps({
            "schemaVersion": "1.3",
            "domainTags": ["leadership", "coaching"],
            "perspectiveTags": ["mens-challenges", "womens-challenges"],
            "audienceTags": audience_tags or [],
            "topicTags": topic_tags or [],
            "personas": {},
        }, indent=2))

    def _mk_blueprint(self, folder, duality_json=None, body="leadership coaching guidance"):
        d = self.personas_dir / folder
        d.mkdir(parents=True, exist_ok=True)
        text = f"# {folder}\n\n{body}\n"
        if duality_json is not None:
            text += (
                "\n## Duality Tags (Machine-Readable)\n\n```json\n"
                + json.dumps(duality_json, indent=2) + "\n```\n"
            )
        (d / "persona-blueprint.md").write_text(text)

    def _load_catalog_via_persona_blend(self) -> dict:
        """The MATCHER-side read of the file the orchestrator just wrote —
        real load_catalog(), not a re-parse of the same JSON another way."""
        return pb.load_catalog({"persona_categories": self.catpath})

    # ── 1. HAPPY PATH ───────────────────────────────────────────────────────
    def test_well_formed_book_is_selectable_by_topic_matcher(self):
        self._seed_categories(
            audience_tags=["e2e-regression-test-audience"],
            topic_tags=["e2e-regression-test-topic"])
        self._mk_blueprint("e2e-happy-path", duality_json={
            "audiences": ["e2e-regression-test-audience"],
            "topics": ["e2e-regression-test-topic"],
            "voice_style": {"summary": "Direct, evidence-first, no fluff."},
            "usable_as": ["audience", "topic", "task"],
        })
        outcome = orch._phase6_register_categories(
            self.book, "e2e-happy-path", appendix_status="COMPLETE")
        self.assertEqual(outcome, "ok")

        catalog = self._load_catalog_via_persona_blend()
        entry = catalog["personas"].get("e2e-happy-path")
        self.assertIsNotNone(entry, "orchestrator-written entry must be readable via load_catalog()")
        self.assertEqual(entry.get("audiences"), ["e2e-regression-test-audience"])
        self.assertEqual(entry.get("topics"), ["e2e-regression-test-topic"])

        # (b) topic matcher actually SELECTS it.
        topic_pick = pb.match_topic_persona(
            catalog, "Write about e2e-regression-test-topic for our newsletter")
        self.assertIsNotNone(topic_pick, "topic matcher must return a candidate")
        self.assertEqual(topic_pick["persona_id"], "e2e-happy-path",
                          "the newly-synthesized persona must WIN the topic match "
                          "(not merely exist in the catalog)")

        # (c) audience matcher actually SELECTS it.
        aud_pick = pb.match_audience_persona(catalog, "e2e-regression-test-audience")
        self.assertIsNotNone(aud_pick, "audience matcher must return a candidate")
        self.assertEqual(aud_pick["persona_id"], "e2e-happy-path",
                          "the newly-synthesized persona must WIN the audience match")

    def test_usable_as_without_audience_never_wins_audience_match(self):
        self._seed_categories(
            audience_tags=["e2e-task-only-audience"],
            topic_tags=["e2e-task-only-topic"])
        self._mk_blueprint("e2e-task-only", duality_json={
            "audiences": ["e2e-task-only-audience"],
            "topics": ["e2e-task-only-topic"],
            "voice_style": {"summary": "x"},
            "usable_as": ["topic", "task"],  # NOTE: no 'audience'
        })
        orch._phase6_register_categories(self.book, "e2e-task-only", appendix_status="COMPLETE")
        catalog = self._load_catalog_via_persona_blend()

        # topic side still wins (usable_as includes 'topic').
        topic_pick = pb.match_topic_persona(catalog, "content about e2e-task-only-topic")
        self.assertEqual(topic_pick["persona_id"], "e2e-task-only")

        # audience side must NEVER select it, even though audiences[] is
        # populated — usable_as gates the audience-voice candidacy.
        aud_pick = pb.match_audience_persona(catalog, "e2e-task-only-audience")
        self.assertIsNone(aud_pick,
                           "a persona whose usable_as omits 'audience' must never win "
                           "an audience-voice match, even with a populated audiences[]")

    # ── 2. NO-WEAKENING: absent block never becomes a ghost candidate ──────
    def test_no_duality_block_never_selectable(self):
        self._seed_categories(topic_tags=["e2e-noop-topic"])
        self._mk_blueprint("e2e-noop", duality_json=None)  # plain, no block
        outcome = orch._phase6_register_categories(self.book, "e2e-noop", appendix_status="COMPLETE")
        self.assertEqual(outcome, "ok")
        catalog = self._load_catalog_via_persona_blend()
        entry = catalog["personas"].get("e2e-noop")
        self.assertIsNotNone(entry)
        self.assertNotIn("topics", entry)
        self.assertNotIn("audiences", entry)

        topic_pick = pb.match_topic_persona(catalog, "content about e2e-noop-topic")
        self.assertIsNone(
            topic_pick,
            "a pre-enrichment entry (no topics[] written) must never win a topic "
            "match — it has nothing to rank on, so it must be absent from the "
            "candidate universe, not silently present with an empty score")

    # ── 3. NO-WEAKENING: rejected/malformed block never becomes selectable ──
    def test_out_of_vocab_rejection_never_selectable(self):
        # Populated vocab that does NOT include the blueprint's claimed tag —
        # the orchestrator's own vocab-first gate must reject this.
        self._seed_categories(audience_tags=["some-other-audience"],
                               topic_tags=["some-other-topic"])
        self._mk_blueprint("e2e-rejected", duality_json={
            "audiences": ["e2e-rejected-audience"],   # NOT in the seeded vocab
            "topics": ["e2e-rejected-topic"],          # NOT in the seeded vocab
            "voice_style": {"summary": "x"},
            "usable_as": ["audience", "topic", "task"],
        })
        outcome = orch._phase6_register_categories(self.book, "e2e-rejected", appendix_status="COMPLETE")
        self.assertEqual(outcome, "ok", "core registration must survive a duality rejection")
        self.assertIn("e2e-rejected", orch._DUALITY_TAG_WRITE_FAILURES,
                       "the rejection must be recorded loudly")

        catalog = self._load_catalog_via_persona_blend()
        entry = catalog["personas"].get("e2e-rejected")
        self.assertIsNotNone(entry, "core domain entry must still exist (never-to-zero)")
        self.assertNotIn("audiences", entry)
        self.assertNotIn("topics", entry)

        # The matcher must never surface it for either dimension.
        topic_pick = pb.match_topic_persona(catalog, "content about e2e-rejected-topic")
        self.assertIsNone(topic_pick if topic_pick and topic_pick["persona_id"] == "e2e-rejected" else None,
                           "rejected entry must not win a topic match (sanity: not equal implies pass)")
        if topic_pick is not None:
            self.assertNotEqual(topic_pick["persona_id"], "e2e-rejected")
        aud_pick = pb.match_audience_persona(catalog, "e2e-rejected-audience")
        self.assertIsNone(aud_pick, "rejected entry has no audiences[] to rank on — must be absent")

    # ── 5. A-U3 (schema-1.4): scalar fields ride the SAME block end-to-end ──
    def test_schema14_scalar_fields_stamped_on_new_persona(self):
        """A-U3 ACCEPT (b): 'the Continuous-Integration end-to-end synthesis
        test produces a NEW persona carrying all three fields.' A synthesized
        book whose '## Duality Tags' block includes emotional_register/
        audience_resonance/conversion_style (vocab-first, chosen from a
        populated catalog vocab) lands all three on the orchestrator-written
        entry, round-trips through load_catalog(), and validates clean under
        the SAME persona_blend.validate_catalog_tags rulebook the matcher
        reads through at select-time."""
        self._seed_categories(
            audience_tags=["e2e-schema14-audience"], topic_tags=["e2e-schema14-topic"])
        self.catpath.write_text(json.dumps({
            **json.loads(self.catpath.read_text()),
            "schemaVersion": "1.4",
            "emotionalRegisterTags": ["tough-love"],
            "audienceResonanceTags": ["challenged-to-rise"],
            "conversionStyleTags": ["challenge-close"],
        }, indent=2))
        self._mk_blueprint("e2e-schema14", duality_json={
            "audiences": ["e2e-schema14-audience"],
            "topics": ["e2e-schema14-topic"],
            "voice_style": {"summary": "Direct, unsentimental, demanding."},
            "usable_as": ["audience", "topic", "task"],
            "emotional_register": "tough-love",
            "audience_resonance": "challenged-to-rise",
            "conversion_style": "challenge-close",
        })
        outcome = orch._phase6_register_categories(
            self.book, "e2e-schema14", appendix_status="COMPLETE")
        self.assertEqual(outcome, "ok")

        catalog = self._load_catalog_via_persona_blend()
        entry = catalog["personas"].get("e2e-schema14")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.get("emotional_register"), "tough-love")
        self.assertEqual(entry.get("audience_resonance"), "challenged-to-rise")
        self.assertEqual(entry.get("conversion_style"), "challenge-close")

        result = pb.validate_catalog_tags(catalog)
        self.assertTrue(result["ok"], f"must validate clean: {result['errors']}")
        self.assertEqual(result["schema"], "1.4")

    def test_schema14_out_of_vocab_scalar_never_selectable_nor_written(self):
        """NO-WEAKENING twin of case 3, for the new scalar fields: an
        out-of-vocab emotional_register is rejected — the WHOLE duality
        block is omitted (all-or-nothing, matching the pre-A-U3 contract),
        not just the offending field."""
        self._seed_categories(
            audience_tags=["e2e-s14-bad-audience"], topic_tags=["e2e-s14-bad-topic"])
        self.catpath.write_text(json.dumps({
            **json.loads(self.catpath.read_text()),
            "emotionalRegisterTags": ["warm-encouragement"],  # does NOT include 'tough-love'
        }, indent=2))
        self._mk_blueprint("e2e-schema14-bad", duality_json={
            "audiences": ["e2e-s14-bad-audience"],
            "topics": ["e2e-s14-bad-topic"],
            "voice_style": {"summary": "x"},
            "usable_as": ["audience", "topic", "task"],
            "emotional_register": "tough-love",  # NOT in the seeded vocab
        })
        outcome = orch._phase6_register_categories(
            self.book, "e2e-schema14-bad", appendix_status="COMPLETE")
        self.assertEqual(outcome, "ok", "core registration must survive a schema-1.4 rejection")
        self.assertIn("e2e-schema14-bad", orch._DUALITY_TAG_WRITE_FAILURES)

        catalog = self._load_catalog_via_persona_blend()
        entry = catalog["personas"].get("e2e-schema14-bad")
        self.assertIsNotNone(entry)
        # all-or-nothing: even the IN-vocab audiences/topics are omitted too.
        self.assertNotIn("emotional_register", entry)
        self.assertNotIn("audiences", entry)

        topic_pick = pb.match_topic_persona(catalog, "content about e2e-s14-bad-topic")
        self.assertIsNone(topic_pick, "rejected entry has no topics[] to rank on — must be absent")

    # ── 4. one rulebook, not two ────────────────────────────────────────────
    def test_round_tripped_catalog_validates_clean_under_the_same_rulebook(self):
        self._seed_categories(
            audience_tags=["e2e-validate-audience"], topic_tags=["e2e-validate-topic"])
        self._mk_blueprint("e2e-validate", duality_json={
            "audiences": ["e2e-validate-audience"],
            "topics": ["e2e-validate-topic"],
            "voice_style": {"summary": "Warm, direct."},
            "usable_as": ["audience", "topic", "task"],
        })
        orch._phase6_register_categories(self.book, "e2e-validate", appendix_status="COMPLETE")
        catalog = self._load_catalog_via_persona_blend()
        result = pb.validate_catalog_tags(catalog)
        self.assertTrue(result["ok"], f"validate_catalog_tags must pass clean: {result['errors']}")
        self.assertEqual(result["errors"], [])
        self.assertGreaterEqual(result["checked"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
