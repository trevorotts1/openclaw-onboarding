#!/usr/bin/env python3
"""Unit tests for STAR-EMBED-01: semantic_task_fit.py's negative-embed-cache.

Background: semantic_task_fit() and semantic_persona_ids() are each called
ONCE PER CANDIDATE PERSONA in one task selection (persona-selector-v2.py's
compute_layer_scores loop), always with the SAME task_text. Before this fix,
the module-level _TASK_EMBED_CACHE only cached a SUCCESSFUL _embed_text()
call — a failure (429 quota exhausted, or anything else) was retried from
scratch on every candidate, turning 1 wasted API call per task selection
into N (N = candidate-pool size). Confirmed on a live client box: 1,213
observed 429s traced back almost entirely to this path.

This suite proves, with _embed_text mocked (no live network / API key):
  1. A failing embed is attempted exactly ONCE across N persona candidates
     scored against the same task_text (the actual fix).
  2. The failure is shared between semantic_task_fit() and
     semantic_persona_ids() (same cache key) within the same process.
  3. A DIFFERENT task_text still gets its own independent attempt — the
     negative cache is scoped per task_text, not global.
  4. A SUCCESSFUL embed still works exactly as before (feature not broken):
     one real embed call, reused (not re-embedded) across all candidates,
     and semantic_task_fit still returns method="gemini_embedding".

Run:
  python3 -m unittest shared-utils/test_semantic_task_fit_negative_cache.py
  (or)  python3 shared-utils/test_semantic_task_fit_negative_cache.py
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import semantic_task_fit as stf


class NegativeCacheTests(unittest.TestCase):
    def setUp(self):
        # Every test starts from a clean module-level cache — these tests
        # exist specifically to police cross-call cache state.
        stf.clear_cache()
        # Force the "genai import worked" branch without importing the real
        # google-genai SDK (not installed in this sandbox, and irrelevant —
        # we're testing the cache/short-circuit logic around _embed_text,
        # not the SDK call itself).
        stf._GENAI_AVAILABLE = True
        self.paths = {"workspace": "/nonexistent-for-tests"}

    def tearDown(self):
        stf.clear_cache()
        stf._GENAI_AVAILABLE = None

    def _stub_paths(self, tmp_db_path: str):
        # _gemini_index_path() only returns the "workspace"-relative
        # candidate if it .exists() on disk; point it at a real (empty)
        # file so the "db_path.exists()" gate passes without touching a
        # live index.
        return {"workspace": os.path.dirname(tmp_db_path), "gemini_index": tmp_db_path}

    def test_failing_embed_attempted_once_across_many_candidates(self):
        """The core fix: N persona candidates, 1 task_text, embed 429s once."""
        with mock.patch.object(stf, "_get_google_api_key", return_value="fake-key"), \
             mock.patch.object(stf, "_gemini_index_path", return_value=stf.Path(__file__)), \
             mock.patch.object(stf, "_embed_text", return_value=None) as mocked_embed:
            for persona_id in [f"persona-{i}" for i in range(25)]:
                result = stf.semantic_task_fit(persona_id, "the same task text every time", self.paths)
                # Every candidate must still get a real, non-crashing score
                # (graceful degrade to keyword/neutral — feature not broken).
                self.assertIn(result["method"], ("keyword_overlap", "neutral_fallback"))

            self.assertEqual(
                mocked_embed.call_count, 1,
                f"_embed_text must be called exactly once for 25 candidates sharing one "
                f"task_text on a failing embed; got {mocked_embed.call_count} calls "
                f"(this is the STAR-EMBED-01 amplification bug if > 1)",
            )

    def test_failure_shared_between_semantic_task_fit_and_persona_ids(self):
        """Same cache key -> a failure recorded by one function is honored by the other."""
        with mock.patch.object(stf, "_get_google_api_key", return_value="fake-key"), \
             mock.patch.object(stf, "_gemini_index_path", return_value=stf.Path(__file__)), \
             mock.patch.object(stf, "_embed_text", return_value=None) as mocked_embed:
            stf.semantic_task_fit("persona-a", "shared task text", self.paths)
            result = stf.semantic_persona_ids("shared task text", self.paths)
            self.assertIsNone(result, "semantic_persona_ids must return None (never-to-zero contract), not raise")
            self.assertEqual(
                mocked_embed.call_count, 1,
                "a failure cached by semantic_task_fit() must be reused by semantic_persona_ids() "
                "for the identical task_text, not re-attempted",
            )

    def test_different_task_text_gets_its_own_attempt(self):
        """Negative cache is scoped per task_text — a fresh task still tries."""
        with mock.patch.object(stf, "_get_google_api_key", return_value="fake-key"), \
             mock.patch.object(stf, "_gemini_index_path", return_value=stf.Path(__file__)), \
             mock.patch.object(stf, "_embed_text", return_value=None) as mocked_embed:
            stf.semantic_task_fit("persona-a", "task text ONE", self.paths)
            stf.semantic_task_fit("persona-b", "task text TWO", self.paths)
            self.assertEqual(
                mocked_embed.call_count, 2,
                "two DIFFERENT task_texts must each get their own attempt — "
                "the negative cache must not suppress unrelated tasks",
            )

    def test_successful_embed_still_works_and_is_reused(self):
        """Feature not broken: a healthy account still gets real semantic scores,
        embedded once and reused across candidates (pre-existing positive-cache
        behavior, unchanged by this fix)."""
        import numpy as np

        fake_vec = np.ones(8, dtype="float32")

        def fake_persona_vec(persona_id, db_path, top_k=None):
            # Identical vector -> cosine similarity 1.0 for every persona.
            return np.ones(8, dtype="float32")

        with mock.patch.object(stf, "_get_google_api_key", return_value="fake-key"), \
             mock.patch.object(stf, "_gemini_index_path", return_value=stf.Path(__file__)), \
             mock.patch.object(stf, "_embed_text", return_value=fake_vec) as mocked_embed, \
             mock.patch.object(stf, "_persona_embedding_from_index", side_effect=fake_persona_vec):
            results = [
                stf.semantic_task_fit(f"persona-{i}", "same task text", self.paths)
                for i in range(5)
            ]

        for r in results:
            self.assertEqual(r["method"], "gemini_embedding")
            self.assertAlmostEqual(r["score"], 0.98, places=2)  # cos=1.0 clamped to 0.98

        self.assertEqual(
            mocked_embed.call_count, 1,
            "a SUCCESSFUL embed must still be computed once and reused across candidates "
            "(pre-existing positive-cache contract) — this fix must not regress it",
        )


if __name__ == "__main__":
    unittest.main()
