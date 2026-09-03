#!/usr/bin/env python3
"""tests/unit/semantic-task-fit-failure-cache.test.py

Proves the EMBED-FAIL-CACHE fix in shared-utils/semantic_task_fit.py:

  Measured on a client box: 1,213 "[semantic_task_fit] embed failed"
  occurrences from ~79 legitimate selector invocations on a 72-task board.
  semantic_task_fit() is called ONCE PER CANDIDATE PERSONA (8-15x) in the
  same selection loop; the task-embedding cache only ever records a
  SUCCESS, so one quota/billing failure on candidate #1 was re-attempted,
  identically, on every remaining candidate.

This suite proves:
  1. _is_permanent_embedding_failure() classifies 429/quota/prepayment-
     depleted/401/403/API-key exceptions as permanent-ish, and network
     blips/timeouts/5xx as transient.
  2. A permanent-ish failure inside _embed_text() latches
     _EMBEDDING_UNAVAILABLE; a transient one does NOT.
  3. THE FIX: one quota/billing failure short-circuits the REST of an
     8-15-candidate selection loop — the (fake) API is called exactly once,
     not once per candidate.
  4. A transient failure does NOT latch across the loop (no over-suppression
     regression) — the API is still attempted for each candidate.
  5. semantic_persona_ids() (the second call site sharing the same latch)
     also short-circuits once the latch is set.
  6. Fleet-safety regression guard: the HEALTHY path (embeddings working)
     is unchanged — semantic_task_fit() still returns method="gemini_embedding"
     with the same score it always did, embed is called once per distinct
     task text, and the latch never engages.
  7. The keyword-overlap fallback used after a latch produces the EXACT
     SAME score _keyword_overlap_score() would produce directly — the fix
     changes nothing about the fallback itself.

Uses a fake google.genai.Client (no real network / API key needed) so this
suite is fully offline, matching the idiom of the existing
tests/unit/embedding-credential-error-classify.test.py in this repo.

Run:
    python3 tests/unit/semantic-task-fit-failure-cache.test.py
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir()

sys.path.insert(0, str(_SHARED_UTILS))

import semantic_task_fit as m  # noqa: E402


def _fresh_module():
    """Reload for a clean cache + latch between tests (module-level state)."""
    global m
    m = importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# Fake google.genai.Client — no real network, no real API key.
# ---------------------------------------------------------------------------

class _FakeEmbeddingValues:
    def __init__(self, values):
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, values):
        self.embeddings = [_FakeEmbeddingValues(values)]


class _FakeModels:
    """Shared mutable `state` dict is keyed per-test so every genai.Client()
    instantiation (semantic_task_fit.py makes a fresh one per _embed_text
    call) reads/writes the SAME counters."""

    def __init__(self, state):
        self._state = state

    def embed_content(self, **kwargs):
        self._state["calls"] += 1
        exc = self._state.get("exc")
        if exc is not None:
            raise exc
        return _FakeEmbedResponse(self._state.get("vector", [0.1, 0.2, 0.3]))


class _FakeGenaiClient:
    def __init__(self, api_key=None, _state=None):
        self.models = _FakeModels(_state)


def _fake_client_factory(state):
    def _ctor(api_key=None):
        return _FakeGenaiClient(api_key=api_key, _state=state)
    return _ctor


# ---------------------------------------------------------------------------
# 1) Classification: permanent-ish vs transient
# ---------------------------------------------------------------------------

class TestPermanentFailureClassification(unittest.TestCase):
    def setUp(self):
        _fresh_module()

    def test_429_quota_is_permanent(self):
        self.assertTrue(m._is_permanent_embedding_failure(
            Exception("429 RESOURCE_EXHAUSTED: quota exceeded")))

    def test_prepayment_credits_depleted_is_permanent(self):
        self.assertTrue(m._is_permanent_embedding_failure(
            Exception("429 Your prepayment credits are depleted")))

    def test_401_unauthorized_is_permanent(self):
        self.assertTrue(m._is_permanent_embedding_failure(Exception("401 Unauthorized")))

    def test_403_api_key_invalid_is_permanent(self):
        self.assertTrue(m._is_permanent_embedding_failure(
            Exception("API key not valid. Please pass a valid API key.")))

    def test_generic_timeout_is_transient(self):
        self.assertFalse(m._is_permanent_embedding_failure(Exception("Read timed out")))

    def test_connection_reset_is_transient(self):
        self.assertFalse(m._is_permanent_embedding_failure(
            Exception("Connection reset by peer")))

    def test_500_server_error_is_transient(self):
        self.assertFalse(m._is_permanent_embedding_failure(
            Exception("500 Internal Server Error")))

    def test_generic_bug_is_transient(self):
        self.assertFalse(m._is_permanent_embedding_failure(
            KeyError("unexpected response shape")))


# ---------------------------------------------------------------------------
# 2) _embed_text() latches on permanent-ish, not on transient
# ---------------------------------------------------------------------------

class TestEmbedTextLatch(unittest.TestCase):
    def setUp(self):
        _fresh_module()
        os.environ["GOOGLE_API_KEY"] = "test-key-not-real"

    def tearDown(self):
        os.environ.pop("GOOGLE_API_KEY", None)
        _fresh_module()

    def test_permanent_failure_sets_latch(self):
        state = {"calls": 0, "exc": Exception("429 RESOURCE_EXHAUSTED: prepayment credits are depleted")}
        with patch("google.genai.Client", _fake_client_factory(state)):
            result = m._embed_text("task text", "fake-key")
        self.assertIsNone(result)
        self.assertEqual(state["calls"], 1)
        self.assertTrue(m._EMBEDDING_UNAVAILABLE,
                         "a permanent-ish failure (429/quota/billing) must latch _EMBEDDING_UNAVAILABLE")

    def test_transient_failure_does_not_set_latch(self):
        state = {"calls": 0, "exc": TimeoutError("Read timed out")}
        with patch("google.genai.Client", _fake_client_factory(state)):
            result = m._embed_text("task text", "fake-key")
        self.assertIsNone(result)
        self.assertFalse(m._EMBEDDING_UNAVAILABLE,
                          "a transient failure must NOT latch — it may clear on the very next call")

    def test_success_does_not_set_latch(self):
        state = {"calls": 0, "exc": None, "vector": [1.0, 0.0, 0.0]}
        with patch("google.genai.Client", _fake_client_factory(state)):
            result = m._embed_text("task text", "fake-key")
        self.assertIsNotNone(result)
        self.assertFalse(m._EMBEDDING_UNAVAILABLE)


# ---------------------------------------------------------------------------
# 3) THE FIX: one quota/billing failure short-circuits the rest of an
#    8-15-candidate selection loop instead of re-attempting per candidate.
# ---------------------------------------------------------------------------

class TestSelectionLoopAmplification(unittest.TestCase):
    def setUp(self):
        _fresh_module()
        os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
        self.tmp = tempfile.TemporaryDirectory()
        # A real (but empty/schemaless) file satisfies db_path.exists(); the
        # embed call fails before _persona_embedding_from_index is ever reached.
        self.db_path = Path(self.tmp.name) / "gemini-index.sqlite"
        self.db_path.touch()
        self.paths = {"gemini_index": self.db_path, "secrets": Path(self.tmp.name)}

    def tearDown(self):
        os.environ.pop("GOOGLE_API_KEY", None)
        self.tmp.cleanup()
        _fresh_module()

    def test_one_quota_failure_short_circuits_the_whole_loop(self):
        """Mirrors the real bug: the SAME task_text scored against N (8-15)
        candidate personas in one selection. Before the fix, every candidate
        re-attempted the identical doomed embed call."""
        state = {"calls": 0, "exc": Exception("429 RESOURCE_EXHAUSTED: prepayment credits are depleted")}
        task_text = "write a persuasive email sequence for a product launch"
        candidates = [f"persona-{i}" for i in range(12)]  # 8-15 range from the real bug

        with patch("google.genai.Client", _fake_client_factory(state)):
            results = [m.semantic_task_fit(pid, task_text, self.paths) for pid in candidates]

        self.assertEqual(
            state["calls"], 1,
            f"one quota/billing failure must short-circuit the rest of the loop "
            f"(fake API called {state['calls']}x across {len(candidates)} candidates, want 1)"
        )
        self.assertTrue(
            all(r["method"] in ("keyword_overlap", "neutral_fallback") for r in results),
            "every candidate after the latch must still receive a real fallback score"
        )
        self.assertTrue(m._EMBEDDING_UNAVAILABLE)

    def test_transient_failure_does_not_over_suppress_the_loop(self):
        """Regression guard: a transient failure must NOT trip the latch, so
        each candidate still gets its own attempt (no new over-suppression bug)."""
        state = {"calls": 0, "exc": TimeoutError("Read timed out")}
        task_text = "write a persuasive email sequence for a product launch"
        candidates = [f"persona-{i}" for i in range(4)]

        with patch("google.genai.Client", _fake_client_factory(state)):
            for pid in candidates:
                m.semantic_task_fit(pid, task_text, self.paths)

        self.assertEqual(
            state["calls"], len(candidates),
            "a transient failure must not latch — every candidate should still be attempted"
        )
        self.assertFalse(m._EMBEDDING_UNAVAILABLE)

    def test_semantic_persona_ids_also_short_circuits_once_latched(self):
        """semantic_persona_ids() is the SECOND call site sharing the same
        module-level latch (G13: task embedding shared between Layer 5 and
        Stage-C retrieval). Once latched by semantic_task_fit(), it must not
        make its own doomed embed call either."""
        state = {"calls": 0, "exc": Exception("429 RESOURCE_EXHAUSTED: prepayment credits are depleted")}
        task_text = "write a persuasive email sequence for a product launch"

        with patch("google.genai.Client", _fake_client_factory(state)):
            m.semantic_task_fit("persona-0", task_text, self.paths)  # trips the latch
            self.assertEqual(state["calls"], 1)
            result = m.semantic_persona_ids(task_text, self.paths)

        self.assertIsNone(result, "semantic_persona_ids() must return None (caller falls back) once latched")
        self.assertEqual(state["calls"], 1, "semantic_persona_ids() must not make its own doomed embed call")


# ---------------------------------------------------------------------------
# 4) Fleet-safety regression guard: healthy path is byte-identical.
# ---------------------------------------------------------------------------

class TestHealthyPathUnchanged(unittest.TestCase):
    def setUp(self):
        _fresh_module()
        os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "gemini-index.sqlite"
        self.db_path.touch()
        self.paths = {"gemini_index": self.db_path, "secrets": Path(self.tmp.name)}

    def tearDown(self):
        os.environ.pop("GOOGLE_API_KEY", None)
        self.tmp.cleanup()
        _fresh_module()

    def test_successful_embeds_use_gemini_method_and_never_latch(self):
        import numpy as np

        state = {"calls": 0, "exc": None, "vector": [1.0, 0.0, 0.0]}
        persona_vec = np.array([1.0, 0.0, 0.0], dtype="float32")

        with patch("google.genai.Client", _fake_client_factory(state)), \
             patch.object(m, "_persona_embedding_from_index", return_value=persona_vec):
            r1 = m.semantic_task_fit("persona-a", "task text one", self.paths)
            r2 = m.semantic_task_fit("persona-b", "task text two", self.paths)

        self.assertEqual(r1["method"], "gemini_embedding")
        self.assertEqual(r2["method"], "gemini_embedding")
        # cosine(identical unit vectors) = 1.0 -> mapped/clamped score = 0.98
        self.assertEqual(r1["score"], 0.98)
        self.assertEqual(r2["score"], 0.98)
        self.assertEqual(state["calls"], 2, "two DISTINCT task texts must each embed once (cache is per-text)")
        self.assertFalse(m._EMBEDDING_UNAVAILABLE, "the healthy path must never engage the failure latch")

    def test_same_task_text_reuses_the_cache_exactly_as_before(self):
        """Unrelated to the fix, but proves the fix didn't disturb the
        pre-existing G13 task-embedding cache contract."""
        import numpy as np

        state = {"calls": 0, "exc": None, "vector": [0.0, 1.0, 0.0]}
        persona_vec = np.array([0.0, 1.0, 0.0], dtype="float32")

        with patch("google.genai.Client", _fake_client_factory(state)), \
             patch.object(m, "_persona_embedding_from_index", return_value=persona_vec):
            m.semantic_task_fit("persona-a", "identical task text", self.paths)
            m.semantic_task_fit("persona-b", "identical task text", self.paths)
            m.semantic_task_fit("persona-c", "identical task text", self.paths)

        self.assertEqual(state["calls"], 1, "the SAME task text across N candidates must embed exactly once")


# ---------------------------------------------------------------------------
# 5) The fallback path itself is untouched by the fix.
# ---------------------------------------------------------------------------

class TestFallbackUnchanged(unittest.TestCase):
    def setUp(self):
        _fresh_module()
        os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "gemini-index.sqlite"
        self.db_path.touch()
        self.paths = {"gemini_index": self.db_path, "secrets": Path(self.tmp.name)}

    def tearDown(self):
        os.environ.pop("GOOGLE_API_KEY", None)
        self.tmp.cleanup()
        _fresh_module()

    def test_post_latch_score_matches_keyword_overlap_directly(self):
        persona_id = "marketing-copywriter-persona"
        task_text = "write persuasive marketing copy for a product launch campaign"

        # Force the latch WITHOUT touching the classification/embed machinery,
        # to isolate: does the fallback score match _keyword_overlap_score()
        # called directly, byte for byte?
        m._EMBEDDING_UNAVAILABLE = True
        expected = m._keyword_overlap_score(persona_id, task_text, "")

        result = m.semantic_task_fit(persona_id, task_text, self.paths)

        self.assertEqual(result["method"], "keyword_overlap")
        self.assertEqual(result["score"], expected,
                          "fallback score after a latch must be IDENTICAL to calling "
                          "_keyword_overlap_score() directly — the fix must not change "
                          "the fallback's own logic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
