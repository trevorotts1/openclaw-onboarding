#!/usr/bin/env python3
"""
tests/unit/sop-embed-once-hash-skip.test.py
─────────────────────────────────────────────────────────────────────────────
P4-03 step 1 — proves shared-utils/sop-embed-once/embed_sop_library.py's
HASH-SKIP incremental contract, the embed-text construction (parity with
sop-embeddings.ts::buildSOPEmbedText), and the REAL-VECTOR HARD GATE.

FAIL-FIRST: every test in this file asserts behavior that did NOT exist
before P4-03 (the module itself is new) — run against the pre-fix tree these
tests fail with ImportError (module absent); against the fix they pass.

No live API key / network required — a fake embed_fn stands in for the real
Gemini call, mirroring the existing repo pattern of testing gate/HASH-SKIP
logic in isolation from live network calls (e.g.
tests/unit/provision-idempotency.test.sh, shared-utils/test-embedding-engine-gemini-ga.sh).

Run:
    python3 tests/unit/sop-embed-once-hash-skip.test.py
    or: pytest tests/unit/sop-embed-once-hash-skip.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_MODULE_DIR = _REPO_ROOT / "shared-utils" / "sop-embed-once"
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _MODULE_DIR.is_dir(), f"shared-utils/sop-embed-once not found at {_MODULE_DIR}"

sys.path.insert(0, str(_SHARED_UTILS))
sys.path.insert(0, str(_MODULE_DIR))

_spec = importlib.util.spec_from_file_location("embed_sop_library", _MODULE_DIR / "embed_sop_library.py")
assert _spec is not None, "Could not load embed_sop_library.py"
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore

build_sop_embed_text = mod.build_sop_embed_text
sop_id_from_slug = mod.sop_id_from_slug
embed_delta = mod.embed_delta
verify_real_vectors = mod.verify_real_vectors
ensure_schema = mod.ensure_schema
# NB: bind under a non-`GEMINI_MODEL` name — the PRD 1.8 CI guard greps
# `^GEMINI_MODEL\s*=` across all *.py to enforce a single model definition in
# shared-utils/embedding_engine.py, and a top-level `GEMINI_MODEL =` alias here
# (even one that just re-reads mod.GEMINI_MODEL) trips it as a false duplicate.
EMBED_MODEL = mod.GEMINI_MODEL
GEMINI_OUTPUT_DIM = mod.GEMINI_OUTPUT_DIM


def _fake_embed(dim: int = GEMINI_OUTPUT_DIM, seed: float = 0.1):
    """A deterministic fake embed_fn(text) -> list[float] of the right dim."""

    def _fn(text: str):
        # Deterministic but text-dependent so different SOPs get different
        # (fake) vectors — proves per-row content flows through, not a shared
        # constant.
        base = (len(text) % 7) * 0.01 + seed
        return [base] * dim

    return _fn


def _wrong_dim_embed(dim: int = 768):
    def _fn(text: str):
        return [0.05] * dim

    return _fn


SOP_A = {
    "slug": "test-onboard-new-client",
    "name": "Onboard New Client",
    "description": "Walks through the full client onboarding checklist.",
    "task_keywords": "onboarding, client, kickoff",
    "steps": [{"name": "Collect intake form"}, {"name": "Schedule kickoff call"}],
}
SOP_B = {
    "slug": "test-close-monthly-books",
    "name": "Close Monthly Books",
    "description": "Reconcile and close the books at month end.",
    "task_keywords": "finance, bookkeeping, close",
    "steps": [{"name": "Reconcile bank feeds"}, {"name": "Post adjusting entries"}],
}


class TestBuildSopEmbedText(unittest.TestCase):
    def test_matches_ts_construction_shape(self):
        text = build_sop_embed_text(SOP_A)
        self.assertIn("Onboard New Client", text)
        self.assertIn("Walks through the full client onboarding checklist.", text)
        self.assertIn("onboarding, client, kickoff", text)
        self.assertIn("Collect intake form", text)
        self.assertIn("Schedule kickoff call", text)
        # '|'-joined top-level parts, mirroring buildSOPEmbedText()
        self.assertIn(" | ", text)

    def test_first_eight_steps_only(self):
        sop = dict(SOP_A)
        sop["steps"] = [{"name": f"Step {i}"} for i in range(12)]
        text = build_sop_embed_text(sop)
        self.assertIn("Step 0", text)
        self.assertIn("Step 7", text)
        self.assertNotIn("Step 8", text)
        self.assertNotIn("Step 11", text)

    def test_sop_id_derivation_matches_ingester(self):
        # Mirrors ingest-sop-library.py: "sop_" + slug.replace("-","_")[:60]
        self.assertEqual(sop_id_from_slug("test-onboard-new-client"), "sop_test_onboard_new_client")


class TestHashSkip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_first_run_embeds_every_sop(self):
        stats = embed_delta(self.conn, [SOP_A, SOP_B], embed_fn=_fake_embed())
        self.assertEqual(stats["embedded"], 2)
        self.assertEqual(stats["skipped_unchanged"], 0)
        rows = self.conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        self.assertEqual(rows, 2)

    def test_second_run_unchanged_content_skips_everything(self):
        embed_delta(self.conn, [SOP_A, SOP_B], embed_fn=_fake_embed())
        stats = embed_delta(self.conn, [SOP_A, SOP_B], embed_fn=_fake_embed())
        self.assertEqual(stats["embedded"], 0)
        self.assertEqual(stats["skipped_unchanged"], 2)

    def test_changed_content_reembeds_only_that_row(self):
        embed_delta(self.conn, [SOP_A, SOP_B], embed_fn=_fake_embed())
        changed_a = dict(SOP_A)
        changed_a["description"] = "COMPLETELY REWRITTEN description text."
        stats = embed_delta(self.conn, [changed_a, SOP_B], embed_fn=_fake_embed())
        self.assertEqual(stats["embedded"], 1, "only the changed SOP should re-embed — HASH-SKIP the rest")
        self.assertEqual(stats["skipped_unchanged"], 1)

    def test_new_sop_added_embeds_only_the_delta(self):
        embed_delta(self.conn, [SOP_A], embed_fn=_fake_embed())
        sop_c = {
            "slug": "test-brand-new-sop",
            "name": "Brand New SOP",
            "description": "Added in a later library revision.",
            "task_keywords": "new",
            "steps": [],
        }
        stats = embed_delta(self.conn, [SOP_A, sop_c], embed_fn=_fake_embed())
        self.assertEqual(stats["embedded"], 1, "adding SOP N+1 must embed exactly ONE row, never the full library")
        self.assertEqual(stats["skipped_unchanged"], 1)

    def test_force_reembeds_unchanged_rows(self):
        embed_delta(self.conn, [SOP_A], embed_fn=_fake_embed())
        stats = embed_delta(self.conn, [SOP_A], embed_fn=_fake_embed(), force=True)
        self.assertEqual(stats["embedded"], 1)
        self.assertEqual(stats["skipped_unchanged"], 0)

    def test_only_slugs_scopes_to_requested_sop(self):
        stats = embed_delta(self.conn, [SOP_A, SOP_B], embed_fn=_fake_embed(), only_slugs={SOP_A["slug"]})
        self.assertEqual(stats["embedded"], 1)
        self.assertEqual(stats["skipped_not_selected"], 1)

    def test_dry_run_never_writes_rows(self):
        stats = embed_delta(self.conn, [SOP_A, SOP_B], dry_run=True)
        self.assertEqual(stats["embedded"], 2, "dry-run still COUNTS what would embed")
        rows = self.conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        self.assertEqual(rows, 0, "dry-run must never write a real row")


class TestRealVectorHardGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_correct_dim_vectors_pass_the_gate(self):
        embed_delta(self.conn, [SOP_A, SOP_B], embed_fn=_fake_embed(dim=GEMINI_OUTPUT_DIM))
        ok, bad_count, detail = verify_real_vectors(self.conn, EMBED_MODEL, GEMINI_OUTPUT_DIM)
        self.assertTrue(ok, detail)
        self.assertEqual(bad_count, 0)

    def test_wrong_dim_vector_is_refused_by_the_gate(self):
        # embed_delta itself stores whatever embed_fn returns (it trusts the
        # injected fn for test isolation) — the HARD GATE is the publish-side
        # assertion (verify_real_vectors) that must catch a wrong-dim vector
        # BEFORE an asset is ever published. This proves the gate, not the
        # writer, is what refuses a bad vector.
        embed_delta(self.conn, [SOP_A], embed_fn=_wrong_dim_embed(dim=768))
        ok, bad_count, detail = verify_real_vectors(self.conn, EMBED_MODEL, GEMINI_OUTPUT_DIM)
        self.assertFalse(ok, "a 768-dim vector must NEVER pass the gemini/3072 hard gate")
        self.assertEqual(bad_count, 1)
        self.assertIn("test_onboard_new_client", detail.replace("-", "_"))


class TestLoadSopsJsonl(unittest.TestCase):
    def test_loads_valid_lines_skips_blank(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps(SOP_A) + "\n")
            fh.write("\n")
            fh.write(json.dumps(SOP_B) + "\n")
            path = fh.name
        try:
            sops = mod.load_sops_jsonl(path)
            self.assertEqual(len(sops), 2)
            self.assertEqual({s["slug"] for s in sops}, {SOP_A["slug"], SOP_B["slug"]})
        finally:
            Path(path).unlink(missing_ok=True)


class TestTruncationCollapseInvariant(unittest.TestCase):
    """The publish gate in build-and-publish.sh must expect DISTINCT sop_id
    count, not raw jsonl line count.

    sop_id is "sop_" + slug.replace("-","_")[:60] — the SAME 60-char truncation
    ingest-sop-library.py applies. In the real v10.13.29 library that collapses
    2,618 records onto 2,555 rows (27 colliding ids absorbing 63 records), and
    the client's own `sops` table collapses identically, so the asset is
    COMPLETE at 2,555. A gate that compared row_count against the 2,618 line
    count would refuse to publish a correct asset after paying the full embed
    cost. These tests pin the invariant that makes the gate's denominator
    correct.
    """

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_slugs_differing_only_past_60_chars_share_one_sop_id(self):
        base = "a" * 60  # first 60 chars identical -> divergence lands PAST the cap
        slug_1, slug_2 = f"{base}-xx", f"{base}-yy"
        self.assertNotEqual(slug_1, slug_2)
        self.assertEqual(sop_id_from_slug(slug_1), sop_id_from_slug(slug_2))

    def test_two_colliding_records_collapse_to_one_embedded_row(self):
        base = "a" * 60
        sops = [
            {**SOP_A, "slug": f"{base}-xx", "name": "First"},
            {**SOP_A, "slug": f"{base}-yy", "name": "Second"},
        ]
        stats = embed_delta(self.conn, sops, embed_fn=_fake_embed())
        rows = self.conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        # Both records are embedded (distinct content -> distinct md5), but the
        # PRIMARY KEY collapses them onto ONE row. row_count < record_count here
        # is CORRECT, not an incomplete asset.
        self.assertEqual(stats["embedded"], 2)
        self.assertEqual(rows, 1)

    def test_expected_row_count_is_distinct_sop_ids_not_record_count(self):
        base = "a" * 60
        sops = [
            {**SOP_A, "slug": f"{base}-xx"},
            {**SOP_A, "slug": f"{base}-yy"},
            {**SOP_B, "slug": "test-unique-slug"},
        ]
        expected = len({sop_id_from_slug(s["slug"]) for s in sops})
        embed_delta(self.conn, sops, embed_fn=_fake_embed())
        actual = self.conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        self.assertEqual(expected, 2)
        self.assertEqual(actual, expected, "publish gate denominator must be distinct sop_id count")
        self.assertLess(expected, len(sops), "fixture must actually exercise a collision")


if __name__ == "__main__":
    unittest.main()
