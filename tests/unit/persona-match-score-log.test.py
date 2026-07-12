#!/usr/bin/env python3
"""
tests/unit/persona-match-score-log.test.py — P4-01 step 2: "log match score
distributions so drift is observable".

FAIL-FIRST: against the pre-P4-01 tree, persona_blend.log_match_score,
persona_blend.match_score_distribution and persona_blend._match_score_log_path
do not exist, so every import/attribute access below raises AttributeError
and every test in this file errors. With the P4-01 build they pass.

Proves:
  1. log_match_score() appends a well-formed JSON line to the resolved path
     (OPENCLAW_PERSONA_MATCH_SCORE_LOG override — the same pattern as
     OPENCLAW_PERSONA_CATEGORIES — so this test never touches a live box).
  2. Multiple calls APPEND (never truncate/overwrite) — a real distribution
     needs history, not a single most-recent point.
  3. log_match_score() is BEST-EFFORT: pointed at a path under a location that
     cannot be created (a file where a directory is expected), it returns
     False and raises NOTHING — logging can never break a persona match.
  4. match_score_distribution() correctly summarizes a hand-written log with
     KNOWN scores: count, mean, min, max, and low/mid/high buckets — computed
     independently in this test (not by re-deriving the implementation's own
     arithmetic) so a real bug in the summary math would be caught.
  5. match_score_distribution() on an ABSENT log returns count=0 (never
     raises, never fabricates), and the `dimension` filter genuinely narrows
     the summary (an "audience"-only summary excludes "topic" rows).
  6. NO-WEAKENING — build_bundle() (the real assembler, selector/decompose
     monkeypatched exactly as test-persona-blend-matcher.py does) actually
     WRITES a topic-dimension record via the wiring in build_bundle, so the
     log fills up under real matcher use, not only under a direct unit call.
     Un-wiring the log_match_score call from build_bundle (verified by
     temporarily monkeypatching it to a no-op) demonstrably drops the
     resulting distribution's count to 0 — proving this test would catch a
     silent "the wiring got removed" regression.

Run:
    python3 tests/unit/persona-match-score-log.test.py
    or: pytest tests/unit/persona-match-score-log.test.py
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
_SCRIPTS = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"
assert _SCRIPTS.is_dir(), f"scripts dir not found at {_SCRIPTS}"


def _load_pb():
    spec = importlib.util.spec_from_file_location(
        "persona_blend_score_log_under_test", _SCRIPTS / "persona_blend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pb = _load_pb()

ENV_KEY = "OPENCLAW_PERSONA_MATCH_SCORE_LOG"


def _read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


class MatchScoreLogWrite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_env = os.environ.get(ENV_KEY)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop(ENV_KEY, None)
        else:
            os.environ[ENV_KEY] = self._old_env
        self._tmp.cleanup()

    def test_writes_well_formed_jsonl_record(self):
        log_path = self.tmp / "sub" / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(log_path)
        ok = pb.log_match_score({}, dimension="topic", persona_id="hormozi-100m-offers",
                                 score=4.0, task_category="content", content_task=True)
        self.assertTrue(ok, "log_match_score must report success on a writable path")
        recs = _read_jsonl(log_path)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        for key in ("ts", "dimension", "persona_id", "score", "task_category", "content_task"):
            self.assertIn(key, rec, f"record missing {key!r}")
        self.assertEqual(rec["dimension"], "topic")
        self.assertEqual(rec["persona_id"], "hormozi-100m-offers")
        self.assertEqual(rec["score"], 4.0)

    def test_multiple_calls_append_never_overwrite(self):
        log_path = self.tmp / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(log_path)
        for i in range(5):
            pb.log_match_score({}, dimension="topic", persona_id=f"persona-{i}",
                                score=float(i) / 10, task_category="content")
        recs = _read_jsonl(log_path)
        self.assertEqual(len(recs), 5, "5 calls must produce 5 appended lines, not 1")
        self.assertEqual([r["persona_id"] for r in recs],
                          [f"persona-{i}" for i in range(5)],
                          "records must preserve call order (append, not overwrite)")

    def test_best_effort_never_raises_on_uncreatable_path(self):
        # Make a FILE where log_match_score needs to mkdir a DIRECTORY --
        # forces Path.mkdir to fail (NotADirectoryError/FileExistsError).
        blocker = self.tmp / "blocker"
        blocker.write_text("i am a file, not a directory")
        bad_path = blocker / "nested" / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(bad_path)
        try:
            ok = pb.log_match_score({}, dimension="topic", persona_id="x", score=0.5)
        except Exception as e:  # pragma: no cover - the whole point is this must not happen
            self.fail(f"log_match_score raised {e!r} — logging must be best-effort, never fatal")
        self.assertFalse(ok, "an uncreatable path must report False, not silently claim success")

    def test_no_paths_no_override_returns_false_never_raises(self):
        os.environ.pop(ENV_KEY, None)
        try:
            ok = pb.log_match_score({}, dimension="topic", persona_id="x", score=0.5)
        except Exception as e:  # pragma: no cover
            self.fail(f"log_match_score raised {e!r} with no resolvable path")
        self.assertFalse(ok)


class MatchScoreDistribution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_env = os.environ.get(ENV_KEY)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop(ENV_KEY, None)
        else:
            os.environ[ENV_KEY] = self._old_env
        self._tmp.cleanup()

    def test_absent_log_returns_honest_empty_state(self):
        os.environ[ENV_KEY] = str(self.tmp / "does-not-exist.jsonl")
        dist = pb.match_score_distribution({})
        self.assertEqual(dist["count"], 0)
        self.assertIsNone(dist["mean"])
        self.assertEqual(dist["buckets"], {"low": 0, "mid": 0, "high": 0})

    def test_distribution_math_is_correct_on_known_scores(self):
        log_path = self.tmp / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(log_path)
        # Known scores, hand-picked to land in every bucket:
        # low (<0.3): 0.1, 0.2   mid (0.3-0.6): 0.4, 0.6   high (>0.6): 0.9
        scores = [0.1, 0.2, 0.4, 0.6, 0.9]
        for s in scores:
            pb.log_match_score({}, dimension="topic", persona_id="p", score=s)
        dist = pb.match_score_distribution({})
        self.assertEqual(dist["count"], 5)
        self.assertAlmostEqual(dist["mean"], sum(scores) / len(scores))
        self.assertEqual(dist["min"], 0.1)
        self.assertEqual(dist["max"], 0.9)
        self.assertEqual(dist["buckets"], {"low": 2, "mid": 2, "high": 1})

    def test_dimension_filter_narrows_the_summary(self):
        log_path = self.tmp / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(log_path)
        pb.log_match_score({}, dimension="topic", persona_id="t1", score=0.9)
        pb.log_match_score({}, dimension="topic", persona_id="t2", score=0.9)
        pb.log_match_score({}, dimension="audience", persona_id="a1", score=0.1)
        all_dist = pb.match_score_distribution({})
        self.assertEqual(all_dist["count"], 3)
        aud_dist = pb.match_score_distribution({}, dimension="audience")
        self.assertEqual(aud_dist["count"], 1)
        self.assertEqual(aud_dist["min"], 0.1)
        topic_dist = pb.match_score_distribution({}, dimension="topic")
        self.assertEqual(topic_dist["count"], 2)

    def test_malformed_lines_are_skipped_not_fatal(self):
        log_path = self.tmp / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(log_path)
        pb.log_match_score({}, dimension="topic", persona_id="ok1", score=0.5)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("{not valid json,,,}\n")
            f.write("\n")  # blank line
        pb.log_match_score({}, dimension="topic", persona_id="ok2", score=0.7)
        dist = pb.match_score_distribution({})
        self.assertEqual(dist["count"], 2, "malformed/blank lines must be skipped, not counted or fatal")


class BuildBundleWiring(unittest.TestCase):
    """NO-WEAKENING: build_bundle() actually calls log_match_score under real
    (monkeypatched-selector) use, and un-wiring it is DETECTABLE."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_env = os.environ.get(ENV_KEY)
        self.log_path = self.tmp / "match-score-log.jsonl"
        os.environ[ENV_KEY] = str(self.log_path)

        # Minimal hermetic monkeypatch of the selector/decompose seam, mirroring
        # test-persona-blend-matcher.py's harness (never touches a live DB).
        self._orig_selector = pb._selector
        self._orig_decompose = pb._decompose

        class _FakeSelector:
            @staticmethod
            def get_openclaw_paths():
                return {}

            @staticmethod
            def find_dashboard_db():
                return None

            @staticmethod
            def is_db_found(_):
                return False

            @staticmethod
            def load_company_config(_paths):
                return {}

            @staticmethod
            def infer_task_category(_task):
                return "content"

            @staticmethod
            def _resolve_default_persona_id(_paths):
                return "default-persona", "default_default"

            @staticmethod
            def _resolve_governance_persona_id(_paths):
                return "governance-persona", "governance_default"

            @staticmethod
            def is_mechanical_task(_task):
                return False

            @staticmethod
            def detect_interaction_mode(_task):
                return "leadership"

            @staticmethod
            def get_weights_for_task(_task, _mode):
                return {}

            @staticmethod
            def select_persona(_task, _dept, _mode, _weights, _paths, _db, variety=False):
                return {"persona_id": "hormozi-100m-offers", "funnel": {}, "score": 0.7}

        class _FakeDecompose:
            DECOMP_MAX_SUBTASKS = 6

            @staticmethod
            def combined_select(_task, _dept, use_llm=True, record=True,
                                 max_subtasks=10, variety=True):
                return {"plan": [], "subtask_count": 0, "distinct_persona_count": 0,
                        "decomposition_method": "test", "task_id": "t1"}

        pb._SEL = _FakeSelector()
        pb._DT = _FakeDecompose()

    def tearDown(self):
        pb._SEL = None
        pb._DT = None
        if self._old_env is None:
            os.environ.pop(ENV_KEY, None)
        else:
            os.environ[ENV_KEY] = self._old_env
        self._tmp.cleanup()

    def test_build_bundle_writes_a_topic_score_record(self):
        pb.build_bundle("write an ad for our new high-ticket offer with bonuses",
                         "marketing", paths={}, db_path=None)
        recs = _read_jsonl(self.log_path)
        topic_recs = [r for r in recs if r["dimension"] == "topic"]
        self.assertGreaterEqual(len(topic_recs), 1,
                                 "build_bundle must log at least one topic-dimension record")

    def test_no_weakening_unwiring_the_log_call_drops_count_to_zero(self):
        # Simulate a regression that removes the log_match_score wiring from
        # build_bundle by monkeypatching the MODULE-LEVEL symbol build_bundle
        # calls to a no-op, then proving the resulting log stays empty --
        # i.e. this suite's own count-based assertions WOULD catch that
        # regression if it landed for real.
        orig = pb.log_match_score
        pb.log_match_score = lambda *a, **kw: False
        try:
            pb.build_bundle("write an ad for our new high-ticket offer with bonuses",
                             "marketing", paths={}, db_path=None)
        finally:
            pb.log_match_score = orig
        recs = _read_jsonl(self.log_path)
        self.assertEqual(len(recs), 0,
                          "with logging unwired, the log must stay empty — "
                          "proving the wiring (not a bystander effect) produced the earlier record")


if __name__ == "__main__":
    unittest.main(verbosity=2)
