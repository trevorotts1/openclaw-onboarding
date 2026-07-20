#!/usr/bin/env python3
"""
tests/unit/sop-library-coverage-gate.test.py
─────────────────────────────────────────────────────────────────────────────
Proves shared-utils/embedding_health.py::check_cc_sop_index() can now SEE an
under-populated SOP table.

THE BLIND SPOT UNDER TEST. Every pre-existing leg of this health check tests
INTERNAL CONSISTENCY -- "do the embeddings match the rows?". A box whose `sops`
table holds nothing but the Command Center's autoSeedStarterSOPs demo fixture
is perfectly self-consistent, so a live box carrying 24 rows against a
canonical library of 2555 reported `overall: pass` while its semantic SOP
search covered 0.9% of the corpus. Consistency is not coverage. That
false-green is exactly what let a never-wired-into-the-updater SOP ingestion
survive unnoticed.

FAIL-FIRST: TestDemoFixtureSizedTableNowFails reproduces the live box state
(a demo-fixture-sized table with matching embeddings, so every other leg is
green) and asserts `pass is False`. On the pre-fix tree that assertion FAILS,
because leg-d did not exist and the box reported pass.

Offline: no network, no embedding API calls, no real box.

Run:
    python3 tests/unit/sop-library-coverage-gate.test.py
"""
from __future__ import annotations

import importlib.util
import json
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

MANIFEST = _SHARED_UTILS / "sop-library" / "SOP-LIBRARY-MANIFEST.json"

SCHEMA = """
CREATE TABLE sops (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
  description TEXT, version INTEGER DEFAULT 1, department TEXT,
  task_keywords TEXT, steps TEXT NOT NULL, success_criteria TEXT,
  persona_hints TEXT, source TEXT, deleted_at TEXT
);
CREATE TABLE sop_embeddings (
  sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL,
  embedding_model TEXT NOT NULL DEFAULT 'gemini-embedding-2',
  embedding_dims INTEGER NOT NULL DEFAULT 3072,
  embedded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

GOOGLE_JSON = {"env": {"vars": {"GOOGLE_API_KEY": "fake-google-key-for-test-only-not-real"}}}


def _make_cc_dir(sops_rows: int, embedded_rows: int) -> Path:
    """A box with `sops_rows` SOPs, `embedded_rows` of them embedded on the
    ACTIVE model -- so legs a/b/c are all green and only coverage can differ."""
    cc_dir = Path(tempfile.mkdtemp())
    conn = sqlite3.connect(str(cc_dir / "mission-control.db"))
    conn.executescript(SCHEMA)
    for i in range(sops_rows):
        conn.execute("INSERT INTO sops (id, name, slug, steps) VALUES (?, ?, ?, '[]')",
                     (f"sop_{i}", f"SOP {i}", f"sop-{i}"))
    for i in range(embedded_rows):
        conn.execute(
            "INSERT INTO sop_embeddings (sop_id, embedding, embedding_model, embedding_dims) "
            "VALUES (?, ?, 'gemini-embedding-2', 3072)",
            (f"sop_{i}", b"\x00" * 16),
        )
    conn.commit()
    conn.close()
    return cc_dir


class TestManifestPin(unittest.TestCase):
    """The canonical population must come from ONE committed pin, so the
    updater, the ingester and this health check cannot disagree."""

    def test_manifest_exists_and_pins_a_canonical_count(self):
        self.assertTrue(MANIFEST.is_file(), f"missing manifest: {MANIFEST}")
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(data["canonical_sop_count"], 2555)
        self.assertEqual(data["release_tag"], "v10.13.29")
        self.assertEqual(data["asset"], "sops-library-v2.jsonl.gz")
        self.assertEqual(len(data["sha256"]), 64)

    def test_health_check_reads_the_same_pin(self):
        self.assertEqual(mod._canonical_sop_count(), 2555)


class TestDemoFixtureSizedTableNowFails(unittest.TestCase):
    """FAIL-FIRST: the exact live box state -- 24 rows, fully self-consistent."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_24_row_demo_fixture_box_is_no_longer_a_pass(self, _m):
        cc_dir = _make_cc_dir(sops_rows=24, embedded_rows=24)
        res = check_cc_sop_index(cc_dir, GOOGLE_JSON, generative_provider="anthropic")

        # Every consistency leg is green -- which is precisely why this box
        # used to report overall pass.
        self.assertTrue(res["leg_a_provider_capable"])
        self.assertIsNot(res["leg_b_stamp_match"], False)
        self.assertTrue(res["leg_c_generative_not_embedding"])
        self.assertFalse(res["needs_reindex"])

        # ...and yet it must now FAIL on coverage.
        self.assertIs(res["leg_d_sop_coverage"], False)
        self.assertFalse(
            res["pass"],
            "REGRESSION: a box holding a 24-row demo fixture against a 2555-row canonical "
            "library must never report overall pass.",
        )
        joined = " ".join(res["errors"])
        self.assertIn("coverage", joined.lower())
        self.assertIn("24", joined)
        self.assertIn("2555", joined)
        self.assertIn("DEMO-FIXTURE-SIZED", joined)

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_error_names_the_remedy_and_the_embedding_cost_boundary(self, _m):
        res = check_cc_sop_index(_make_cc_dir(24, 24), GOOGLE_JSON, generative_provider="anthropic")
        joined = " ".join(res["errors"])
        self.assertIn("ingest-sop-library.sh", joined)
        self.assertIn("U6c", joined)
        # An operator reading this must not conclude the fix bills the client.
        self.assertIn("CONTENT ONLY", joined)
        self.assertIn("costs nothing", joined)


class TestPartiallyPopulatedAlsoFails(unittest.TestCase):
    """A half-ingested box is still under-populated -- no silent tolerance band."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_half_the_library_still_fails(self, _m):
        res = check_cc_sop_index(_make_cc_dir(1200, 1200), GOOGLE_JSON, generative_provider="anthropic")
        self.assertIs(res["leg_d_sop_coverage"], False)
        self.assertFalse(res["pass"])
        # Not labelled a demo fixture -- that wording is reserved for tiny tables.
        self.assertNotIn("DEMO-FIXTURE-SIZED", " ".join(res["errors"]))


class TestFullyPopulatedBoxPasses(unittest.TestCase):
    """A correctly-rolled box (library + starters) must stay green -- the gate
    must not punish the boxes that are already right."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_2578_row_box_passes_coverage(self, _m):
        # 2578 = 2555 library + 23 CC starter seeds, the real populated-box number.
        res = check_cc_sop_index(_make_cc_dir(2578, 2578), GOOGLE_JSON, generative_provider="anthropic")
        self.assertIs(res["leg_d_sop_coverage"], True)
        self.assertTrue(res["pass"], res)

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_exactly_canonical_passes(self, _m):
        res = check_cc_sop_index(_make_cc_dir(2555, 2555), GOOGLE_JSON, generative_provider="anthropic")
        self.assertIs(res["leg_d_sop_coverage"], True)
        self.assertTrue(res["pass"], res)


class TestNoVerdictInvented(unittest.TestCase):
    """The gate must be honest about what it cannot know."""

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_empty_table_is_not_a_coverage_failure(self, _m):
        """sops_total==0 is 'not provisioned yet', not 'under-populated' --
        preserving the pre-existing fresh-box semantics."""
        res = check_cc_sop_index(_make_cc_dir(0, 0), GOOGLE_JSON, generative_provider="anthropic")
        self.assertIsNone(res["leg_d_sop_coverage"])
        self.assertTrue(res["pass"])

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_unreadable_manifest_yields_no_verdict_rather_than_a_guess(self, _m):
        with patch.object(mod, "_canonical_sop_count", return_value=None):
            res = check_cc_sop_index(_make_cc_dir(24, 24), GOOGLE_JSON, generative_provider="anthropic")
        self.assertIsNone(res["leg_d_sop_coverage"])
        self.assertIn("canonical population unknown", res["leg_d_detail"])

    @patch.object(mod, "_attempt_smoke_embed", return_value=(True, "smoke ok (mocked)"))
    def test_explicit_expected_count_overrides_the_pin(self, _m):
        res = check_cc_sop_index(_make_cc_dir(24, 24), GOOGLE_JSON,
                                 generative_provider="anthropic", expected_sop_count=24)
        self.assertIs(res["leg_d_sop_coverage"], True)
        self.assertTrue(res["pass"], res)


if __name__ == "__main__":
    unittest.main(verbosity=2)
