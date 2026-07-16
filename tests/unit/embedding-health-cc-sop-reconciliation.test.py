#!/usr/bin/env python3
"""
tests/unit/embedding-health-cc-sop-reconciliation.test.py
─────────────────────────────────────────────────────────────────────────────
P4-03 step 5 — proves shared-utils/embedding_health.py::check_cc_sop_index()
no longer reports a false PASS on a box that has SOP content loaded (`sops`
table populated) but ZERO sop_embeddings rows — the exact "two health surfaces
disagree" bug: 32-command-center-setup/scripts/heartbeat-embedding-probe.py
correctly screams `dark` for this state (sops_total>0, sop_embeddings empty),
while embedding_health.py::check_cc_sop_index previously treated
`leg_b_stamp_match is None` (no stamp table — CC never creates one) as NOT a
failure (`res["pass"]` only required `is not False`).

FAIL-FIRST: TestDarkBoxNowFails reproduces the EXACT scenario from the P4-03
root-cause writeup — a box with SOP content loaded and an empty
sop_embeddings table — and asserts `pass is False`. On the pre-fix tree this
assertion FAILS (the bug: pass was True).

Run:
    python3 tests/unit/embedding-health-cc-sop-reconciliation.test.py
"""
from __future__ import annotations

import importlib.util
import sqlite3
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

_spec = importlib.util.spec_from_file_location("embedding_health", _SHARED_UTILS / "embedding_health.py")
assert _spec is not None
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore

check_cc_sop_index = mod.check_cc_sop_index

SCHEMA = """
CREATE TABLE sops (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
  description TEXT, version INTEGER DEFAULT 1, department TEXT,
  task_keywords TEXT, steps TEXT NOT NULL, success_criteria TEXT,
  persona_hints TEXT, deleted_at TEXT
);
CREATE TABLE sop_embeddings (
  sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL,
  embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
  embedding_dims INTEGER NOT NULL DEFAULT 1536,
  embedded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _make_cc_dir(sops_rows: int, embedded_rows: int, model="gemini-embedding-2", dims=3072) -> Path:
    cc_dir = Path(tempfile.mkdtemp())
    db_path = cc_dir / "mission-control.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    for i in range(sops_rows):
        conn.execute(
            "INSERT INTO sops (id, name, slug, steps) VALUES (?, ?, ?, '[]')",
            (f"sop_{i}", f"SOP {i}", f"sop-{i}"),
        )
    for i in range(embedded_rows):
        conn.execute(
            "INSERT INTO sop_embeddings (sop_id, embedding, embedding_model, embedding_dims) VALUES (?, ?, ?, ?)",
            (f"sop_{i}", b"\x00" * (dims * 4), model, dims),
        )
    conn.commit()
    conn.close()
    return cc_dir


GOOGLE_JSON = {"env": {"vars": {"GOOGLE_API_KEY": "fake-google-key-for-test-only-not-real"}}}


class TestDarkBoxNowFails(unittest.TestCase):
    """The exact P4-03 root-cause scenario: box has SOP content, zero embeddings."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_sops_loaded_but_sop_embeddings_empty_is_now_a_fail(self, _mock_smoke):
        cc_dir = _make_cc_dir(sops_rows=25, embedded_rows=0)
        res = check_cc_sop_index(cc_dir, GOOGLE_JSON, generative_provider="anthropic")

        self.assertFalse(
            res["pass"],
            "REGRESSION: a box with 25 SOPs loaded and ZERO sop_embeddings rows must FAIL — "
            "this is the exact false-PASS bug the heartbeat probe already caught as `dark`.",
        )
        self.assertFalse(res["leg_b_stamp_match"])
        self.assertTrue(res["needs_reindex"])
        self.assertTrue(any("sop_embeddings is EMPTY" in e for e in res["errors"]))

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_agrees_with_heartbeat_probe_dark_semantics(self, _mock_smoke):
        """heartbeat-embedding-probe.py's own dark_reason for this exact state is
        'sop_embeddings table exists but is empty — embeddings never ran'.
        Both surfaces must now independently conclude failure for the SAME box."""
        cc_dir = _make_cc_dir(sops_rows=10, embedded_rows=0)
        res = check_cc_sop_index(cc_dir, GOOGLE_JSON, generative_provider="anthropic")
        # heartbeat probe's own row-count read would show sops_total=10,
        # sop_embeddings_count=0 -> status="dark". Reproduce that read here to
        # prove BOTH surfaces read the identical ground truth and BOTH fail.
        conn = sqlite3.connect(str(cc_dir / "mission-control.db"))
        sops_total = conn.execute("SELECT COUNT(*) FROM sops").fetchone()[0]
        emb_count = conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        conn.close()
        heartbeat_would_be_dark = sops_total > 0 and emb_count == 0
        self.assertTrue(heartbeat_would_be_dark)
        self.assertFalse(res["pass"], "embedding_health.py must agree with the heartbeat probe's dark verdict")


class TestFreshBoxStillPassesInformationally(unittest.TestCase):
    """sops_total==0 is legitimately 'not yet provisioned' — must NOT be
    treated as a dark/fail condition (no rows exist to embed yet)."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_empty_sops_table_does_not_force_a_fail(self, _mock_smoke):
        cc_dir = _make_cc_dir(sops_rows=0, embedded_rows=0)
        res = check_cc_sop_index(cc_dir, GOOGLE_JSON, generative_provider="anthropic")
        self.assertTrue(res["pass"], "a fresh box with NO sops loaded yet must not be forced to fail leg-b")


class TestHealthyBoxStillPasses(unittest.TestCase):
    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_sops_and_matching_embeddings_present_passes(self, _mock_smoke):
        cc_dir = _make_cc_dir(sops_rows=5, embedded_rows=5, model="gemini-embedding-2", dims=3072)
        res = check_cc_sop_index(cc_dir, GOOGLE_JSON, generative_provider="anthropic")
        self.assertTrue(res["pass"], res)
        self.assertFalse(res["needs_reindex"])


class TestActiveModelMismatchStillFails(unittest.TestCase):
    """Rows exist but none match the currently-capable provider's model —
    e.g. every row is a stale/openai model while Google is now configured."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_rows_present_but_wrong_model_still_fails(self, _mock_smoke):
        cc_dir = _make_cc_dir(sops_rows=5, embedded_rows=5, model="text-embedding-3-small", dims=1536)
        res = check_cc_sop_index(cc_dir, GOOGLE_JSON, generative_provider="anthropic")
        self.assertFalse(res["pass"])
        self.assertTrue(res["needs_reindex"])


if __name__ == "__main__":
    unittest.main()
