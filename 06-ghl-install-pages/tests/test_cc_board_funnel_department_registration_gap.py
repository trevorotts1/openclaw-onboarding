# test_cc_board_funnel_department_registration_gap.py — documents the OPEN,
# UNRESOLVED gap left by the operator's 2026-07-16 ruling on Skill-6 funnel
# routing.
#
# CONTEXT: cc_board.py's ingest_task() stamps department_slug='funnels' for
# every job_type='funnel' card. An earlier session direction proposed
# rerouting to 'marketing' instead (a registered floor department); the
# operator overruled that and ruled the OPPOSITE: keep stamping 'funnels',
# and register 'funnels' as its OWN floor department instead of folding
# funnel work into Marketing.
#
# THIS TEST DOES NOT CLAIM THE BUG IS FIXED. It documents the current,
# still-open state: 'funnels' is NOT YET a registered department anywhere
# (no id in departments.config.ts, no entry in department-floor.py's
# HARDCODED_MANDATORY). On a box seeded strictly from the standard floor (no
# ad hoc 'funnels' workspace added by hand, unlike the operator's own box),
# CC's tier-1 exact-slug match (ingest/route.ts's resolveWorkspaceId, mirrored
# verbatim in _resolve_tier1 below) still MISSES 'funnels', so INGEST-06's
# unrecognized-slug tier still reroutes the card to general-task.
#
# COMPLETING THE FIX requires (not done by this test, not done by this
# session — flagged as an operator content decision):
#   1. A 'funnels' entry in 23-ai-workforce-blueprint/department-naming-map.json
#      (director_title, display_name, emoji, one_liner, loss_warning,
#      suggested_roles_file) + department-floor.py's HARDCODED_MANDATORY.
#   2. A real suggested-roles catalog for the new department — genuine
#      content (roles, SOPs, persona traits), not a placeholder.
#   3. Reconciling the overlap with TWO roles that already live inside
#      Marketing's own catalog (23-ai-workforce-blueprint/suggested-roles/
#      marketing-suggested-roles.md): role #4 "Funnel Strategist" and role
#      #20 "Signature Funnel Specialist" ("the marketing door onto the ...
#      Skill 49 [engine]") — do they move, stay, or coexist?
#   4. A matching 'funnels' entry in the CC repo's departments.config.ts
#      (a separate repo, its own serial merge-writer — not touched here)
#      plus a workspace-seed migration there.
#
# Once that landscape is registered, THIS TEST'S ASSERTION MUST FLIP (funnel
# cards will resolve to the real 'funnels' workspace, not None) — that flip
# is the signal the registration work is actually done and wired.
#
# Stdlib + pytest only, zero network, zero client/CC repo dependency.
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
    department (real HARDCODED_MANDATORY, bare id=slug, mirroring the CC
    repo's scripts/sync-departments-from-build-state.py dept- prefix strip).
    Deliberately carries NO ad hoc extras — this is what a FRESH client box
    looks like, not the operator's own hand-customized one.
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


class TestFunnelDepartmentRegistrationGap:
    def test_producer_still_stamps_funnels(self, rec):
        """The operator's ruling: keep stamping 'funnels' (don't reroute to
        'marketing')."""
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        assert call["payload"]["department_slug"] == "funnels"

    def test_funnels_is_not_yet_a_floor_department(self):
        """Precondition / open-gap marker: 'funnels' is absent from the real
        floor list. If this assertion ever flips to 'in', the registration
        work has landed and test_KNOWN_GAP below must be revisited."""
        floor = _load_department_floor()
        assert "funnels" not in floor.HARDCODED_MANDATORY, (
            "'funnels' now appears in HARDCODED_MANDATORY — the department "
            "registration has landed; update/remove this gap-tracking test "
            "and test_KNOWN_GAP_funnel_card_does_not_resolve_on_a_floor_standard_box"
        )

    def test_KNOWN_GAP_funnel_card_does_not_resolve_on_a_floor_standard_box(self, rec):
        """DOCUMENTS THE OPEN BUG — does not claim it is fixed. On a box
        seeded strictly from the standard floor (no ad hoc 'funnels'
        workspace), the real producer stamp run through a faithful mirror of
        CC's tier-1 resolution SQL still MISSES — the card still lands in
        general-task via INGEST-06, not a real department. This assertion is
        EXPECTED TO FLIP once 'funnels' is properly registered (see the
        module docstring for what that requires)."""
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        stamped_slug = call["payload"]["department_slug"]

        conn = _seed_floor_workspaces_db()
        resolved_id = _resolve_tier1(conn, stamped_slug)

        assert resolved_id is None, (
            f"funnel card (department_slug={stamped_slug!r}) resolved to "
            f"{resolved_id!r} on a floor-standard box — the registration gap "
            "this test tracks appears to be CLOSED; if so, update this test "
            "to assert the real resolution instead of documenting the gap"
        )
