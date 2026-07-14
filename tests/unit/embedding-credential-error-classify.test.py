#!/usr/bin/env python3
"""
tests/unit/embedding-credential-error-classify.test.py
─────────────────────────────────────────────────────────────────────────────
A-U8 (Skill 6 v2, book-to-persona embeddings wiring) — proves:

  1. shared-utils/embedding_engine.py::is_credential_error() correctly
     classifies auth/credential-shaped exceptions (401/403/permission/API key)
     as credential errors, and a generic exception (e.g. a KeyError from
     malformed content) as NOT a credential error.

  2. 23-ai-workforce-blueprint/scripts/gemini-section-indexer.py's main()
     routes a MID-RUN credential-shaped exception (key present but rejected
     by the API) to exit code 4 (the SAME code the upfront "no key" preflight
     already used) — the deferral-eligible signal orchestrator.py Phase 5
     reads — while a genuine non-credential exception routes to exit code 6
     (still fail-loud, distinct from 4).

Offline: never calls any embedding API; needs python3 + sqlite3 (stdlib) only.

Run:
    python3 tests/unit/embedding-credential-error-classify.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_INDEXER_DIR = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"
assert _SHARED_UTILS.is_dir()
assert _INDEXER_DIR.is_dir()

sys.path.insert(0, str(_SHARED_UTILS))

_eng_spec = importlib.util.spec_from_file_location(
    "embedding_engine", _SHARED_UTILS / "embedding_engine.py")
assert _eng_spec is not None
engine = importlib.util.module_from_spec(_eng_spec)
sys.modules["embedding_engine"] = engine
assert _eng_spec.loader is not None
_eng_spec.loader.exec_module(engine)  # type: ignore

_idx_spec = importlib.util.spec_from_file_location(
    "gemini_section_indexer", _INDEXER_DIR / "gemini-section-indexer.py")
assert _idx_spec is not None
indexer_mod = importlib.util.module_from_spec(_idx_spec)
assert _idx_spec.loader is not None
_idx_spec.loader.exec_module(indexer_mod)  # type: ignore


class TestIsCredentialError(unittest.TestCase):
    def test_401_is_credential_error(self):
        self.assertTrue(engine.is_credential_error(Exception("401 Unauthorized")))

    def test_403_permission_denied_is_credential_error(self):
        self.assertTrue(engine.is_credential_error(
            Exception("403 PERMISSION_DENIED: The caller does not have permission")))

    def test_api_key_not_valid_is_credential_error(self):
        self.assertTrue(engine.is_credential_error(
            Exception("API key not valid. Please pass a valid API key.")))

    def test_generic_bug_is_not_credential_error(self):
        self.assertFalse(engine.is_credential_error(KeyError("unexpected shape")))
        self.assertFalse(engine.is_credential_error(
            RuntimeError("embedding returned 0 instead of a 3072-dim vector")))

    def test_quota_error_is_not_credential_error(self):
        # Quota/timeout is a DIFFERENT classified family (_is_quota_or_timeout);
        # is_credential_error must not double-claim it.
        self.assertFalse(engine.is_credential_error(
            Exception("429 RESOURCE_EXHAUSTED: quota exceeded")))


class TestIndexerExitCodeRouting(unittest.TestCase):
    """Exercises gemini-section-indexer.py's main() exception-handler branch
    directly (never over the network) by monkeypatching embed_section to
    raise a controlled exception, with an --allow-fake-embeddings-shaped
    resolved embedder substituted so main() reaches the indexing loop without
    ever needing a real key."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.personas_root = base / "personas"
        (self.personas_root / "testauthor-testbook").mkdir(parents=True)
        (self.personas_root / "testauthor-testbook" / "persona-blueprint.md").write_text(
            "# Test\n\n## Section 3: Coaching Framework\n"
            "This is the coaching framework section of the fixture persona. "
            "It contains enough words to clear the minimum section word floor "
            "used by the section parser so the indexer emits a row.\n"
        )
        self.db_path = base / "drift.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def _run_main_with_embed_exception(self, exc: Exception) -> int:
        argv = ["gemini-section-indexer.py",
                "--db", str(self.db_path),
                "--personas-root", str(self.personas_root),
                "--reindex-all"]
        # gemini-section-indexer.py's main() RETURNS an int (sys.exit(main())
        # only happens under the __main__ guard) — call it directly and read
        # the return value; also tolerate a raised SystemExit defensively.
        with patch.object(sys, "argv", argv), \
             patch.object(indexer_mod, "resolve_real_embedder",
                          return_value=("gemini", object(), "gemini-embedding-2")), \
             patch.object(indexer_mod, "get_embedding", side_effect=exc):
            try:
                rc = indexer_mod.main()
            except SystemExit as e:
                return int(e.code) if e.code is not None else 0
            return int(rc) if rc is not None else 0

    def test_credential_shaped_exception_exits_4(self):
        rc = self._run_main_with_embed_exception(
            RuntimeError("403 PERMISSION_DENIED: API key not valid"))
        self.assertEqual(rc, 4,
                         "a credential-shaped mid-run failure must exit 4 "
                         "(the SAME deferral-eligible code as the no-key preflight)")

    def test_generic_exception_exits_6(self):
        rc = self._run_main_with_embed_exception(ValueError("unexpected shape"))
        self.assertEqual(rc, 6,
                         "a non-credential mid-run failure must exit 6 "
                         "(distinct from 4 — NOT deferral-eligible, stays fail-loud)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
