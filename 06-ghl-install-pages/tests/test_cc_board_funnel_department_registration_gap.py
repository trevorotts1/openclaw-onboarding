# test_cc_board_funnel_department_registration_gap.py — documents that the
# operator's 2026-07-16 ruling on Skill-6 funnel routing has been EXECUTED,
# not merely proposed. Kept as the gap-tracking test's established filename,
# but the assertions now prove the gap is closed.
#
# CONTEXT: cc_board.py's ingest_task() stamps department_slug='funnels' for
# every job_type='funnel' card. An earlier direction proposed rerouting to
# 'marketing' instead (a registered floor department); the operator reversed
# that direction: keep stamping 'funnels', and register 'funnels' as its OWN
# floor department instead of folding funnel work into Marketing.
#
# THIS TEST PROVES THE ONB-SIDE FIX:
#   1. 'funnels' is a mandatory floor department in
#      23-ai-workforce-blueprint/department-naming-map.json and in
#      department-floor.py's HARDCODED_MANDATORY.
#   2. A real suggested-roles catalog ships at
#      23-ai-workforce-blueprint/suggested-roles/funnels-suggested-roles.md
#      with 3 roles and matching role-library templates.
#   3. The deliberate overlap with Marketing's and Web Development's existing
#      funnel-adjacent roles is documented in the Funnels Department Purpose.
#   4. The consuming Command Center repository has its own separate companion
#      change for workspace registration and migration. This test neither
#      edits nor depends on that repository; it uses a faithful mirror of the
#      consumer's tier-1 slug/id lookup to prove the ONB producer contract.
#
# The fixture seeds a standard mandatory floor with no ad hoc extras. A funnel
# card stamped by the real cc_board.py must now resolve to the real 'funnels'
# workspace rather than missing tier 1 and falling to a general catch-all.
#
# Stdlib + pytest only, zero network, zero client or external-repo dependency.
from __future__ import annotations

import importlib.util as _ilu
import os
import sqlite3
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_FLOOR_SCRIPT_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "23-ai-workforce-blueprint",
        "scripts",
    )
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402

BASE = "https://demo.zerohumanworkforce.com"
ENV = {"MISSION_CONTROL_URL": BASE, "MC_API_TOKEN": "placeholder-token"}


def _load_department_floor():
    """Import department-floor.py by path because its filename is hyphenated."""
    path = os.path.join(_FLOOR_SCRIPT_DIR, "department-floor.py")
    spec = _ilu.spec_from_file_location("department_floor_under_test", path)
    assert spec is not None and spec.loader is not None
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Recorder:
    """Stand-in for cc_board._post_json; records calls and performs no network."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, cfg, method="POST"):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": "TASK-1", "deduped": False, "status": "backlog"}
        return 200, {"ok": True}


@pytest.fixture
def rec(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(cc_board, "_post_json", recorder)
    return recorder


def _seed_floor_workspaces_db():
    """Seed one workspace per real mandatory-floor department.

    The bare id and slug mirror the consuming repository's department seed
    convention. No ad hoc extras are added. Because 'funnels' is now in
    HARDCODED_MANDATORY, it is seeded through the same path as every other
    mandatory department rather than through test-specific special casing.
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
    """Mirror the consumer's tier-1 workspace query.

    SELECT id FROM workspaces
    WHERE lower(slug) = ? OR lower(id) = ?
    LIMIT 1

    None means tier 1 missed and the consumer would need a later fallback.
    """
    slug = department_slug.lower()
    row = conn.execute(
        "SELECT id FROM workspaces WHERE lower(slug) = ? OR lower(id) = ? LIMIT 1",
        (slug, slug),
    ).fetchone()
    return row[0] if row else None


class TestFunnelDepartmentRegistrationFixed:
    def test_producer_still_stamps_funnels(self, rec):
        """Keep the dedicated slug; do not reroute funnel cards to Marketing."""
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        assert call["payload"]["department_slug"] == "funnels"

    def test_funnels_is_now_a_mandatory_floor_department(self):
        """The Skill 23 floor registration is present in the real source list."""
        floor = _load_department_floor()
        assert "funnels" in floor.HARDCODED_MANDATORY, (
            "'funnels' is missing from HARDCODED_MANDATORY — the registration "
            "in department-naming-map.json and department-floor.py regressed"
        )

    def test_funnel_card_resolves_on_a_standard_floor(self, rec):
        """Run the producer stamp through the mirrored tier-1 lookup."""
        cc_board.ingest_task("Signature funnel build", job_type="funnel", env=ENV)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        stamped_slug = call["payload"]["department_slug"]

        conn = _seed_floor_workspaces_db()
        try:
            resolved_id = _resolve_tier1(conn, stamped_slug)
        finally:
            conn.close()

        assert resolved_id == "funnels", (
            f"funnel card (department_slug={stamped_slug!r}) resolved to "
            f"{resolved_id!r} on a standard-floor box — expected 'funnels'. "
            "The Skill 6 producer and Skill 23 floor registration are not "
            "correctly connected if this fails."
        )
