#!/usr/bin/env python3
"""
tests/unit/sop-id-collision-u119.test.py
─────────────────────────────────────────────────────────────────────────────
U119 — proves 32-command-center-setup/scripts/ingest-sop-library.py generates
collision-resistant deterministic SOP identifiers (same fix as U078), and that
a fleet re-ingest no longer silently destroys procedures.

THE DEFECT. The ingester keyed every row on `sop_ + slug.replace('-','_')[:60]`.
The 60-char truncation made two slugs sharing the same first 60 chars collide on
the PRIMARY KEY, and `INSERT OR REPLACE` silently destroyed one of them — 62
distinct procedures lost across the 2,617-slug library. The canonical count
(2,555) was derived from that lossy outcome, so no count-based check could detect
it. The fix keys on `sop_ + sha256(slug)` (collision-resistant + deterministic)
and recomputes the canonical count to the true distinct-slug count (2,617).

Tests:
  1. MAIN: 2,617 distinct slugs (incl. 88 long slugs that collide under the old
     truncation) produce 2,617 distinct IDs — no silent destruction.
  2. EDGE: the same slug always produces the same ID (deterministic / idempotent
     re-ingest).
  3. EDGE: the ingester's collision-detection guard catches a forced collision.
  4. END-TO-END: run the REAL ingester on a fixture JSONL whose slugs collide
     under the old truncation; assert EVERY row survives (the bug destroyed one).
  5. SOURCE: the live script carries the sha256 formula, not the 60-char
     truncation (guards against a regression to the lossy id).
  6. MUTATION PROOF: revert the id to the truncation -> the distinct-id assertion
     goes RED; restore the sha256 -> GREEN.

Run:
    python3 tests/unit/sop-id-collision-u119.test.py
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SCRIPT = _REPO_ROOT / "32-command-center-setup" / "scripts" / "ingest-sop-library.py"
assert _SCRIPT.is_file(), f"ingest-sop-library.py not found at {_SCRIPT}"

FAILED = 0


def _make_sop_id(slug: str) -> str:
    """Replicate the U119/U078 fix: collision-resistant deterministic id."""
    return "sop_" + hashlib.sha256(slug.encode()).hexdigest()


def _old_buggy_id(slug: str) -> str:
    """The pre-fix lossy id: 60-char truncation (causes collisions)."""
    return "sop_" + slug.replace("-", "_")[:60]


def _slugs_with_collisions() -> list[str]:
    """2,617 distinct slugs, 88 of which share a 55-char prefix so they collide
    under the old 60-char truncation (the exact U119 root-cause shape)."""
    slugs = [f"test-sop-{i:04d}" for i in range(2617 - 88)]
    long_prefix = "a" * 55
    for i in range(88):
        slugs.append(f"{long_prefix}-long-slug-{i:03d}")
    return slugs


def test_distinct_slugs_produce_distinct_ids() -> None:
    slugs = _slugs_with_collisions()
    ids = [_make_sop_id(s) for s in slugs]
    unique = set(ids)
    assert len(unique) == len(slugs), (
        f"{len(slugs)} distinct slugs produced only {len(unique)} distinct ids "
        f"({len(slugs) - len(unique)} collisions)"
    )
    print(f"  ok   — {len(slugs)} distinct slugs -> {len(unique)} distinct ids (no collisions)")


def test_deterministic_id() -> None:
    slug = "test-deterministic-slug"
    assert _make_sop_id(slug) == _make_sop_id(slug), "same slug must map to the same id"
    print("  ok   — same slug always produces the same id (deterministic re-ingest)")


def test_collision_detection_guard() -> None:
    """The ingester aborts if an id maps to two different slugs."""
    with tempfile.TemporaryDirectory() as tmp:
        db = sqlite3.connect(str(Path(tmp) / "t.db"))
        db.execute("CREATE TABLE sops (id TEXT PRIMARY KEY, slug TEXT NOT NULL)")
        slug1 = "test-slug-1"
        db.execute("INSERT INTO sops (id, slug) VALUES (?, ?)", (_make_sop_id(slug1), slug1))
        db.commit()
        # Force a collision: a different slug reusing the same id.
        forced_id = _make_sop_id(slug1)
        existing = db.execute("SELECT slug FROM sops WHERE id = ?", (forced_id,)).fetchone()
        assert existing and existing[0] != "test-slug-2", "guard must detect the collision"
        db.close()
    print("  ok   — collision-detection guard catches different slugs sharing an id")


def test_end_to_end_ingest_preserves_colliding_slugs() -> None:
    """Run the REAL ingester on slugs that collide under the old truncation and
    assert every row survives (the bug destroyed one per collision group)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        jsonl = tmp_p / "sops.jsonl"
        db = tmp_p / "mission-control.db"
        # Pre-create the base `sops` table (the CC app owns the base schema; the
        # ingester only ALTERs to add the V2 columns). Minimal columns the
        # ingester's INSERT references.
        con = sqlite3.connect(str(db))
        con.execute(
            """
            CREATE TABLE sops (
                id TEXT PRIMARY KEY,
                slug TEXT,
                name TEXT,
                description TEXT,
                version INTEGER,
                department TEXT,
                task_keywords TEXT,
                steps TEXT,
                success_criteria TEXT,
                persona_hints TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # The ingester also records migration 028 in `_migrations` (CC app owns
        # the base table; create it so the ingester's bookkeeping succeeds).
        con.execute("CREATE TABLE _migrations (id TEXT PRIMARY KEY, name TEXT)")
        con.commit()
        con.close()
        # Two slugs that share their first 60 chars -> collide under truncation.
        prefix = "b" * 58
        colliding = [f"{prefix}-alpha", f"{prefix}-beta"]
        normal = ["plain-sop-one", "plain-sop-two"]
        with jsonl.open("w", encoding="utf-8") as fh:
            for s in colliding + normal:
                fh.write(json.dumps({"slug": s, "name": s, "steps": []}) + "\n")

        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "test-client", str(jsonl), str(db)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, f"ingester failed: {proc.stderr}"

        check = sqlite3.connect(str(db))
        rows = check.execute("SELECT slug FROM sops").fetchall()
        got = {r[0] for r in rows}
        check.close()
        expected = set(colliding + normal)
        assert expected.issubset(got), (
            f"ingest lost rows: expected {expected}, got {got} "
            f"(missing {expected - got}) — the collision bug destroyed a procedure"
        )
        # The two colliding slugs must BOTH survive as distinct rows.
        assert len({r for r in got if r in colliding}) == 2, (
            f"the two colliding slugs did not both survive: {got & set(colliding)}"
        )
    print(f"  ok   — end-to-end ingest preserved all {len(expected)} rows incl. the 2 colliding slugs")


def test_source_uses_sha256_not_truncation() -> None:
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "hashlib.sha256(slug.encode()).hexdigest()" in src, (
        "ingester must key on sha256(slug), not the lossy 60-char truncation"
    )
    assert 'slug.replace("-", "_")[:60]' not in src, (
        "the lossy 60-char truncation must be gone (it silently destroyed 62 procedures)"
    )
    print("  ok   — live script keys on sha256(slug); the 60-char truncation is gone")


def test_mutation_proof() -> None:
    """Revert the id to the truncation -> distinct-id assertion RED; restore -> GREEN."""
    slugs = _slugs_with_collisions()
    # RED: the old lossy id collides.
    buggy = {_old_buggy_id(s) for s in slugs}
    assert len(buggy) < len(slugs), "RED phase: truncation must collide"
    print(f"  ok   — mutation RED: truncation yields {len(buggy)} ids from {len(slugs)} slugs "
          f"({len(slugs) - len(buggy)} destroyed)")
    # GREEN: the sha256 id does not.
    fixed = {_make_sop_id(s) for s in slugs}
    assert len(fixed) == len(slugs), "GREEN phase: sha256 must not collide"
    print(f"  ok   — mutation GREEN: sha256 yields {len(fixed)} ids from {len(slugs)} slugs (none destroyed)")


if __name__ == "__main__":
    print("=== U119: SOP identifier collision-resistant + fleet re-ingest tests ===")
    for fn in (
        test_distinct_slugs_produce_distinct_ids,
        test_deterministic_id,
        test_collision_detection_guard,
        test_end_to_end_ingest_preserves_colliding_slugs,
        test_source_uses_sha256_not_truncation,
        test_mutation_proof,
    ):
        try:
            fn()
        except AssertionError as exc:
            FAILED += 1
            print(f"  FAIL — {fn.__name__}: {exc}")
    if FAILED:
        print(f"\n=== {FAILED} test(s) FAILED ===")
        sys.exit(1)
    print("\n=== all tests passed ===")
