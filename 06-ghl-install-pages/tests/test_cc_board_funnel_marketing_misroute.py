# test_cc_board_funnel_marketing_misroute.py — proves a Skill-6 funnel card
# lands on the REAL Marketing workspace end-to-end: the producer's stamp ->
# CC's own tier-1 resolveWorkspaceId SQL -> a workspaces table seeded exactly
# like a standard-floor box.
#
# THE BUG: cc_board.ingest_task(job_type='funnel') stamped the fake slug
# 'funnels' — not a real department anywhere (no id in departments.config.ts,
# no entry in department-floor.py's HARDCODED_MANDATORY). CC's own ingest
# route (src/app/api/tasks/ingest/route.ts's resolveWorkspaceId, tier 1:
# `SELECT id FROM workspaces WHERE lower(slug) = ? OR lower(id) = ? LIMIT 1`,
# mirrored verbatim in _resolve_tier1 below) finds no matching row for
# 'funnels', so INGEST-06's unrecognized-slug tier reroutes the card to the
# honest general-task catch-all instead of Marketing — even though
# departments.config.ts:100/:112 name funnels as Marketing's own purpose and
# routing keyword.
#
# THE FIX: the producer stamps 'marketing' instead — a real floor department
# every box seeds (departments.config.ts id 'marketing'; #1 in
# department-floor.py:116's HARDCODED_MANDATORY; every box's workspaces.slug
# seed writes the BARE id per CC's scripts/sync-departments-from-build-state.py
# :338 dept- prefix strip, :350/:359 slug=dept_id writes) — so tier 1 resolves
# it directly, never reaching the unrecognized-slug fallback.
#
# Proven to FAIL on the pre-fix tree: department_slug='funnels' has no row in
# the floor-seeded workspaces table below, so the tier-1 SQL mirror returns
# None and the "lands on Marketing" assertion fails. PASSES post-fix.
#
# Stdlib + pytest only, zero network, zero client/CC repo dependency (the CC
# SQL is mirrored by citation, not imported — this repo has no path to CC's
# TypeScript source).
from __future__ import annotations

import importlib.util as _ilu
import os
import sqlite3
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_FLOOR_SCRIPT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..",
                 "23-ai-workforce-blueprint", "scripts")
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402

BASE = "https://demo.zerohumanworkforce.com"
ENV = {"MISSION_CONTROL_URL": BASE, "MC_API_TOKEN": "t"}


def _load_department_floor():
    """Import department-floor.py by file path — the hyphenated filename
    isn't a valid module name for a normal `import` statement."""
    path = os.path.join(_FLOOR_SCRIPT_DIR, "department-floor.py")
    spec = _ilu.spec_from_file_location("department_floor_under_test", path)
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Recorder:
    """Stand-in for cc_board._post_json — same contract test_cc_rail_contract.py
    uses. Records every (method, url, payload); zero network."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, cfg, method="POST"):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": "TASK-1", "deduped": False, "status": "backlog"}
        return 200, {"ok": True}


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    monkeypatch.setattr(cc_board, "_post_json", r)
    return r


def _seed_floor_workspaces_db():
    """An in-memory sqlite workspaces table with one row per standard-floor
    department, seeded exactly like a fresh box: bare slug = bare id, per the
    CC repo's scripts/sync-departments-from-build-state.py (:338 strips a
    'dept-' prefix off the build-state id; :350/:359 write slug=dept_id for
    UPDATE/INSERT alike). Deliberately carries NO 'funnels' row — the floor
    has no such department — so this reproduces a standard client box, not
    a hand-customized one that may carry extra ad hoc workspaces.
    """
    floor = _load_department_floor()
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY, slug TEXT, name TEXT)")
    for dept_id in floor.HARDCODED_MANDATORY:
        conn.execute(
            "INSERT INTO workspaces (id, slug, name) VALUES (?, ?, ?)",
            (dept_id, dept_id, dept_id.replace("-", " ").title()),
        )
    conn.commit()
    return conn


def _resolve_tier1(conn: sqlite3.Connection, department_slug: str):
    """A verbatim mirror of resolveWorkspaceId's tier-1 query (CC repo,
    src/app/api/tasks/ingest/route.ts, resolveWorkspaceId(), the
    '1. department_slug -> workspaces.slug (or id)' block):

        SELECT id FROM workspaces WHERE lower(slug) = ? OR lower(id) = ? LIMIT 1

    Returns the resolved workspace id, or None if tier 1 misses — exactly the
    condition under which INGEST-06 takes over and reroutes to general-task.
    """
    slug = department_slug.lower()
    row = conn.execute(
        "SELECT id FROM workspaces WHERE lower(slug) = ? OR lower(id) = ? LIMIT 1",
        (slug, slug),
    ).fetchone()
    return row[0] if row else None


class TestFunnelCardLandsOnMarketing:
    def test_marketing_is_a_floor_department_funnels_is_not(self):
        """Precondition sanity check: 'marketing' really is on the mandatory
        floor (department-floor.py:116, HARDCODED_MANDATORY) and 'funnels' is
        not — if this ever stops being true the routing proof below is
        meaningless."""
        floor = _load_department_floor()
        assert "marketing" in floor.HARDCODED_MANDATORY
        assert "funnels" not in floor.HARDCODED_MANDATORY

    def test_funnel_card_resolves_to_marketing_not_general_task(self, rec):
        """END TO END: the REAL cc_board.ingest_task() stamp, run through a
        faithful mirror of CC's REAL tier-1 resolution SQL, against a
        workspaces table seeded exactly like a standard floor box."""
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        stamped_slug = call["payload"]["department_slug"]

        conn = _seed_floor_workspaces_db()
        resolved_id = _resolve_tier1(conn, stamped_slug)

        assert resolved_id == "marketing", (
            f"funnel card (department_slug={stamped_slug!r}) resolved to "
            f"{resolved_id!r} instead of the real Marketing workspace — it is "
            "landing in general-task (or nowhere) instead"
        )
