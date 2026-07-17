# test_cc_board_funnel_department_registration_gap.py — documents that the
# operator's 2026-07-16 ruling on Skill-6 funnel routing has been EXECUTED,
# not merely proposed. Kept as the (renamed intent, same filename) fixture
# this session's own predecessor established as the gap-tracking test.
#
# CONTEXT: cc_board.py's ingest_task() stamps department_slug='funnels' for
# every job_type='funnel' card. An earlier session direction proposed
# rerouting to 'marketing' instead (a registered floor department); the
# operator overruled that and ruled the OPPOSITE: keep stamping 'funnels',
# and register 'funnels' as its OWN floor department instead of folding
# funnel work into Marketing — verbatim: "THEN USE THE STANDALONE WORKSPACE
# IF IT ALREADY EXISTS."
#
# THIS TEST NOW PROVES THE FIX, not the gap. As of this change:
#   1. 'funnels' is a mandatory floor department in
#      23-ai-workforce-blueprint/department-naming-map.json (director_title,
#      display_name, emoji, one_liner, loss_warning, suggested_roles_file)
#      and in department-floor.py's HARDCODED_MANDATORY.
#   2. A real suggested-roles catalog ships at
#      23-ai-workforce-blueprint/suggested-roles/funnels-suggested-roles.md
#      (3 roles, each with a full 19-section role-library template under
#      templates/role-library/funnels/), matching the bar set by
#      healer-suggested-roles.md.
#   3. The overlap with Marketing's existing funnel-adjacent roles (role #4
#      "Funnel Strategist", role #20 "Signature Funnel Specialist") and with
#      Web Development's own funnel-adjacent roles (role #1 "Funnel Builder
#      Specialist", role #19/#20 "Signature Funnel Specialist" / "Sales Page
#      Assets Specialist") is documented as a DELIBERATE, operator-ruled
#      overlap in funnels-suggested-roles.md's Department Purpose section —
#      nothing in Marketing's or Web Development's existing catalogs was
#      moved, renamed, or deleted.
#   4. A matching 'funnels' entry + workspace-seed migration ships in the CC
#      repo (blackceo-command-center, a separate repo with its own serial
#      merge-writer — see that repo's own PR for the CC-side leg + its own
#      real fail-then-pass proof against a pre-existing DB shape).
#
# This test proves the ONB-side half end to end with a faithful mirror of
# CC's tier-1 resolveWorkspaceId SQL: a funnel card, on a box seeded strictly
# from the standard mandatory floor (no ad hoc 'funnels' workspace added by
# hand), now resolves to the REAL 'funnels' workspace — not general-task.
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
    looks like, not the operator's own hand-customized one. Now that
    'funnels' is itself a member of HARDCODED_MANDATORY, this fixture seeds
    it like every other mandatory department — no special-casing required.
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

    Returns the resolved workspace id, or None if tier 1 misses — the
    condition under which INGEST-06 takes over and reroutes to general-task.
    """
    slug = department_slug.lower()
    row = conn.execute(
        "SELECT id FROM workspaces WHERE lower(slug) = ? OR lower(id) = ? LIMIT 1",
        (slug, slug),
    ).fetchone()
    return row[0] if row else None


class TestFunnelDepartmentRegistrationFixed:
    def test_producer_still_stamps_funnels(self, rec):
        """The operator's ruling: keep stamping 'funnels' (don't reroute to
        'marketing')."""
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        assert call["payload"]["department_slug"] == "funnels"

    def test_funnels_is_now_a_mandatory_floor_department(self):
        """The registration landed: 'funnels' is a member of the real floor
        list. If this assertion ever flips back to absent, the registration
        has regressed and test_funnel_card_resolves_on_a_floor_standard_box
        below must be revisited."""
        floor = _load_department_floor()
        assert "funnels" in floor.HARDCODED_MANDATORY, (
            "'funnels' is missing from HARDCODED_MANDATORY — the department "
            "registration (department-naming-map.json's mandatory.funnels + "
            "this list) has regressed"
        )

    def test_funnel_card_resolves_on_a_floor_standard_box(self, rec):
        """PROVES THE FIX — not a claim, a run. On a box seeded strictly from
        the standard mandatory floor (no ad hoc 'funnels' workspace added by
        hand, unlike the operator's own pre-existing box), the real producer
        stamp run through a faithful mirror of CC's tier-1 resolution SQL now
        RESOLVES to the real 'funnels' workspace — the card lands in the real
        department, not general-task via INGEST-06's unrecognized-slug tier.
        """
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        stamped_slug = call["payload"]["department_slug"]

        conn = _seed_floor_workspaces_db()
        resolved_id = _resolve_tier1(conn, stamped_slug)

        assert resolved_id == "funnels", (
            f"funnel card (department_slug={stamped_slug!r}) resolved to "
            f"{resolved_id!r} on a floor-standard box — expected 'funnels'. "
            "The registration fix (department-naming-map.json + "
            "department-floor.py's HARDCODED_MANDATORY) is not correctly "
            "wired if this fails."
        )
