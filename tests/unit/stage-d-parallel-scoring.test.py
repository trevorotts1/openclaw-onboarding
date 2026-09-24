#!/usr/bin/env python3
"""
Contract test for Stage-D concurrent scoring in
23-ai-workforce-blueprint/scripts/persona-selector-v2.py.

WHAT BROKE. Stage-D scored finalists in a sequential list comprehension. In
`llm` mode each finalist costs four sequential HTTPS chat calls (one per
Layer 1-4), so a --blend run spent 94% of its wall clock (43.7s of 46.6s on
the profiled run; 206s and 258s on others) blocked in llm_score._post_chat.
The Command Center killed the selector at its spawn budget and the blend
never landed. score_personas() overlaps those waits on a thread pool.

Proves, hermetically (score_persona is monkeypatched — no DB, no network):

  1. ORDER IS PRESERVED. executor.map yields in INPUT order, not completion
     order, so downstream stages (variety sampling, bonuses, tie-breaks) see
     exactly the list the old comprehension produced. Forced by making the
     LAST persona the FASTEST — under a completion-ordered implementation it
     would come back first.
  2. THE WAITS OVERLAP. Six personas that each block 0.2s run in two waves at
     the SHIPPED default of 3 workers — ~0.4s, well inside the 0.6s bound
     (1.2s if they were still sequential). The test uses the module default
     rather than pinning a number, so a default that stops overlapping fails
     here instead of passing against a width nothing ships.
  3. THE ESCAPE HATCH IS LITERAL. PERSONA_SCORE_WORKERS=1 runs on the CALLING
     thread — no pool, no worker — so an operator who suspects the threads can
     take a byte-identical sequential path.
  4. scoring_mode IS THREADED THROUGH. The G13 LLM gate's per-selection
     heuristic downgrade must survive the refactor.

Run:
    python3 tests/unit/stage-d-parallel-scoring.test.py
    or: pytest tests/unit/stage-d-parallel-scoring.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent         # repo root
_SCRIPTS = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"
assert _SCRIPTS.is_dir(), f"selector scripts dir not found at {_SCRIPTS}"

sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location(
    "persona_selector_v2", _SCRIPTS / "persona-selector-v2.py")
sel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sel)

BLOCK_SECONDS = 0.2
PERSONAS = [f"persona-{i}" for i in range(6)]


class StageDParallelScoring(unittest.TestCase):

    def setUp(self):
        self._real_score_persona = sel.score_persona
        self._real_workers = sel.PERSONA_SCORE_WORKERS

    def tearDown(self):
        sel.score_persona = self._real_score_persona
        sel.PERSONA_SCORE_WORKERS = self._real_workers

    # ── helpers ─────────────────────────────────────────────────────────────

    def _install_blocking_stub(self):
        """Stand in for the real scorer: block like an HTTPS call would.

        The LAST persona blocks the LEAST, so a completion-ordered
        implementation returns it first and case 1 fails loudly.
        """
        order = {pid: i for i, pid in enumerate(PERSONAS)}

        def stub(persona_id, task_text, owner_profile, department_id,
                 weights, paths, db_path, scoring_mode=None):
            time.sleep(BLOCK_SECONDS * (1.0 - order[persona_id] / 100.0))
            return {"persona_id": persona_id, "score": 0.5,
                    "thread": threading.current_thread().name,
                    "scoring_mode": scoring_mode}

        sel.score_persona = stub

    def _run(self, personas, scoring_mode=None):
        return sel.score_personas(personas, "task text", "owner profile",
                                  "marketing", {}, {}, None,
                                  scoring_mode=scoring_mode)

    # ── 1 + 2: order preserved, waits overlap ───────────────────────────────

    def test_order_preserved_and_waits_overlap(self):
        self._install_blocking_stub()
        # The SHIPPED default, not a pinned 6 — this test guards what runs.
        sel.PERSONA_SCORE_WORKERS = self._real_workers

        started = time.monotonic()
        scored = self._run(PERSONAS)
        elapsed = time.monotonic() - started

        self.assertEqual([s["persona_id"] for s in scored], PERSONAS,
                         "score_personas must return results in INPUT order")
        self.assertLess(
            elapsed, 0.6,
            f"6 personas blocking {BLOCK_SECONDS}s each took {elapsed:.2f}s "
            f"with {self._real_workers} workers — sequential would be ~1.2s")
        self.assertGreater(len({s["thread"] for s in scored}), 1,
                           "work must actually be spread across threads")

    def test_default_width_respects_the_shared_ollama_ceiling(self):
        """The default is 3, not 6.

        Ollama Cloud's concurrency limit is ACCOUNT-WIDE (10) and the
        operator's standing ceiling is 8, shared by every running agent on
        every box. A 6-wide scoring burst queues behind whatever agents are
        already live and step 1 of the chain times out — measured on a client
        Mac, 0 of 3 scoring calls reached ollama-cloud/minimax-m3 and all fell
        through to OpenRouter/Agnes at 4-20s. This pins the shipped width so a
        future "make it faster" edit has to argue with the shared ceiling.
        """
        self.assertEqual(
            self._real_workers, 3,
            "PERSONA_SCORE_WORKERS default must stay at 3 — the Ollama Cloud "
            "concurrency ceiling is account-wide and shared across the fleet")

    # ── 3: the escape hatch creates no thread at all ────────────────────────

    def test_workers_1_runs_on_the_calling_thread(self):
        self._install_blocking_stub()
        sel.PERSONA_SCORE_WORKERS = 1
        caller = threading.current_thread().name

        scored = self._run(PERSONAS[:3])

        self.assertEqual([s["persona_id"] for s in scored], PERSONAS[:3])
        self.assertEqual({s["thread"] for s in scored}, {caller},
                         "PERSONA_SCORE_WORKERS=1 must not create a worker")

    def test_worker_count_never_exceeds_the_persona_count(self):
        """One persona must not spin up a six-thread pool (and zero must not
        ask ThreadPoolExecutor for max_workers=0, which raises)."""
        self._install_blocking_stub()
        sel.PERSONA_SCORE_WORKERS = 6
        caller = threading.current_thread().name

        self.assertEqual(self._run([]), [])
        one = self._run(PERSONAS[:1])
        self.assertEqual([s["persona_id"] for s in one], PERSONAS[:1])
        self.assertEqual(one[0]["thread"], caller,
                         "a single persona takes the no-thread path")

    # ── 4: the G13 gate's per-selection mode still reaches the scorer ───────

    def test_scoring_mode_is_threaded_through(self):
        self._install_blocking_stub()
        for workers in (1, 6):
            with self.subTest(workers=workers):
                sel.PERSONA_SCORE_WORKERS = workers
                scored = self._run(PERSONAS[:2], scoring_mode="heuristic")
                self.assertEqual([s["scoring_mode"] for s in scored],
                                 ["heuristic", "heuristic"])

    # ── an exception must still surface, not be swallowed by the pool ───────

    def test_exception_propagates(self):
        def boom(persona_id, *a, **kw):
            raise RuntimeError(f"scorer blew up on {persona_id}")

        sel.score_persona = boom
        for workers in (1, 6):
            with self.subTest(workers=workers):
                sel.PERSONA_SCORE_WORKERS = workers
                with self.assertRaises(RuntimeError):
                    self._run(PERSONAS[:2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
