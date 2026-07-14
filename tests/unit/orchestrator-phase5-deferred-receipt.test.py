#!/usr/bin/env python3
"""
tests/unit/orchestrator-phase5-deferred-receipt.test.py
─────────────────────────────────────────────────────────────────────────────
A-U8 (Skill 6 v2, book-to-persona embeddings wiring) — proves:

  1. orchestrator.py::classify_phase5_result() is a pure function that maps
     the Phase-5 indexer subprocess's (returncode, stderr) into exactly
     "DONE" / "DEFERRED" / "FAILED", with the DEFERRED message reading
     literally "embedding: deferred (no key / key invalid)" (the exact
     phrase A-U8's acceptance criterion (b) names).

  2. orchestrator.py::_write_embedding_deferred_receipt() writes an honest,
     well-formed embedding-receipt.json (status='deferred', reason,
     indexer_exit_code, persona_id, timestamp) next to the persona blueprint
     — the artifact persona_fleet.py::index-verify and
     persona_embedding_drift_probe.py both read.

  3. End-to-end at the Phase-5 subprocess boundary: a REAL keyless
     gemini-section-indexer.py subprocess run (offline, no key) is classified
     DEFERRED (not FAILED), matching what orchestrator.py's Phase 5 block
     actually receives from `subprocess.run([...gemini-section-indexer.py...])`
     on a client box with no Gemini key configured.

Run:
    python3 tests/unit/orchestrator-phase5-deferred-receipt.test.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_PIPE = _REPO_ROOT / "22-book-to-persona-coaching-leadership-system" / "pipeline"
_INDEXER = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts" / "gemini-section-indexer.py"
sys.path.insert(0, str(_PIPE))

_spec = importlib.util.spec_from_file_location("orchestrator", _PIPE / "orchestrator.py")
orch = importlib.util.module_from_spec(_spec)
sys.modules["orchestrator"] = orch
_spec.loader.exec_module(orch)


class TestClassifyPhase5Result(unittest.TestCase):
    def test_zero_is_done(self):
        status, msg = orch.classify_phase5_result(0, "")
        self.assertEqual(status, "DONE")

    def test_exit_4_is_deferred_with_exact_message(self):
        status, msg = orch.classify_phase5_result(4, "some stderr noise")
        self.assertEqual(status, "DEFERRED")
        self.assertEqual(msg, "embedding: deferred (no key / key invalid)")

    def test_exit_6_is_failed(self):
        status, msg = orch.classify_phase5_result(6, "a real bug traceback")
        self.assertEqual(status, "FAILED")
        self.assertIn("indexer exit 6", msg)
        self.assertIn("a real bug traceback", msg)

    def test_other_nonzero_is_failed(self):
        for rc in (1, 2, 3, 5, 7, 137):
            status, _ = orch.classify_phase5_result(rc, "")
            self.assertEqual(status, "FAILED", f"exit {rc} must NOT be deferral-eligible")


class TestWriteEmbeddingDeferredReceipt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.slug = "fixture-author-fixture-book"
        (base / "personas" / self.slug).mkdir(parents=True)
        self._orig_personas_dir = orch.PERSONAS_DIR
        orch.PERSONAS_DIR = base / "personas"
        # log() (called by _write_embedding_deferred_receipt's except-branch
        # warning in test_receipt_write_failure_does_not_raise) opens the
        # module-level LOG_FILE directly with no mkdir. Left at its
        # production default (BASE / "pipeline-log.txt", BASE resolved via
        # get_openclaw_paths()) it points at a directory that does not exist
        # on a bare CI runner, so the warning-log write itself raises
        # FileNotFoundError. Redirect it into this test's own temp sandbox,
        # matching the same LOG_FILE redirect
        # tests/unit/orchestrator-embed-fail-exit8.test.py already does.
        self._orig_log_file = orch.LOG_FILE
        orch.LOG_FILE = base / "pipeline-log.txt"

    def tearDown(self):
        orch.PERSONAS_DIR = self._orig_personas_dir
        orch.LOG_FILE = self._orig_log_file
        self.tmp.cleanup()

    def test_receipt_is_well_formed(self):
        orch._write_embedding_deferred_receipt(
            self.slug, "embedding: deferred (no key / key invalid)", 4)
        receipt_path = orch.PERSONAS_DIR / self.slug / "embedding-receipt.json"
        self.assertTrue(receipt_path.is_file())
        data = json.loads(receipt_path.read_text())
        self.assertEqual(data["status"], "deferred")
        self.assertEqual(data["persona_id"], self.slug)
        self.assertEqual(data["indexer_exit_code"], 4)
        self.assertEqual(data["reason"], "embedding: deferred (no key / key invalid)")
        self.assertIn("timestamp", data)

    def test_receipt_write_failure_does_not_raise(self):
        # Point PERSONAS_DIR at a location that cannot be written (parent
        # missing) — the receipt writer must swallow + log, never raise
        # (Phase 5 must not crash the pipeline over a receipt-write hiccup).
        orch.PERSONAS_DIR = Path(self.tmp.name) / "does-not-exist"
        try:
            orch._write_embedding_deferred_receipt(self.slug, "reason", 4)
        except Exception as e:  # noqa: BLE001
            self.fail(f"_write_embedding_deferred_receipt raised: {e}")


class TestRealIndexerKeylessRunClassifiesDeferred(unittest.TestCase):
    """End-to-end at the subprocess boundary: run the REAL
    gemini-section-indexer.py with no Gemini key (offline, hermetic) exactly
    as orchestrator.py's Phase 5 block does via subprocess.run(...), and
    assert classify_phase5_result() reads its (returncode, stderr) as
    DEFERRED — this is what makes A-U8 acceptance (b) ("with the key absent,
    the pipeline still completes and writes an embedding: deferred receipt")
    true end-to-end, not just at the pure-function level."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.personas_root = base / "personas"
        (self.personas_root / "testauthor-testbook").mkdir(parents=True)
        (self.personas_root / "testauthor-testbook" / "persona-blueprint.md").write_text(
            "# Test\n\n## Section 3: Coaching Framework\n"
            "This is the coaching framework section of the fixture persona. "
            "It contains enough words to clear the minimum section word floor "
            "used by the section parser so the indexer would emit a row if "
            "it ran to completion.\n"
        )
        self.db_path = base / "gemini-index.sqlite"
        self.sbhome = base / "sbhome"
        (self.sbhome / ".openclaw" / "workspace" / "data").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_keyless_real_subprocess_classifies_deferred(self):
        import os
        env = dict(os.environ)
        for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
            env.pop(k, None)
        env["HOME"] = str(self.sbhome)
        env["OPENCLAW_SANDBOX"] = "1"
        proc = subprocess.run(
            [sys.executable, str(_INDEXER),
             "--db", str(self.db_path),
             "--personas-root", str(self.personas_root),
             "--reindex-all"],
            capture_output=True, text=True, env=env, check=False,
        )
        status, msg = orch.classify_phase5_result(proc.returncode, proc.stderr)
        self.assertEqual(status, "DEFERRED",
                         f"a real keyless indexer run must classify DEFERRED "
                         f"(rc={proc.returncode}, stderr={proc.stderr[-300:]!r})")
        self.assertEqual(msg, "embedding: deferred (no key / key invalid)")
        # And: nothing was written to the index (mirrors the hard-gate test's
        # T1c invariant — a deferred run must not smuggle in a fake vector).
        self.assertFalse(self.db_path.exists(),
                         "a deferred (keyless) run must write NOTHING to the index")


if __name__ == "__main__":
    unittest.main(verbosity=2)
