"""WF09 — Community member administration (scope, approvals, access read-back).

Proves: exact-person scoping, approval gates for removal/ban/role elevation, the routine
onboarding automation authorization, that a workflow enrollment is recorded as NOT access
proof, and that every action is verified against the member's own row (no false success).
No network, no browser.
"""
import copy
import json
import os
import subprocess
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_community_builder as cb  # noqa: E402
import ghl_community_members as cm  # noqa: E402


def task(**over):
    t = {"location_id": "LOC", "operation": "invite",
         "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                       "portal_host": "portal.example.com"},
         "member": {"member_contact_id": "CONTACT_1", "email": "student@example.com"}}
    t.update(over)
    return t


def locked_sels():
    sels = copy.deepcopy(cb.load_selectors())
    for name, node in sels["community"]["members"].items():
        if isinstance(node, dict) and "status" in node:
            node["status"] = "locked"
            node["anchor"] = node.get("anchor") or "getByText('Members')"
    return sels


class FakeRows:
    def __init__(self, rows=None, effect=None):
        self.rows = rows if rows is not None else [
            {"text": "Student One student@example.com CONTACT_1 member"}]
        self.effect = effect

    def eval(self, session, js, timeout=12):
        return json.dumps(self.rows)

    def click(self, session, sels, dotted, **kw):
        if dotted == "community.members.role_confirm":
            self.rows = [{"text": "Student One student@example.com CONTACT_1 admin"}]
        if dotted == "community.members.confirm_action" and self.effect == "remove":
            self.rows = []
        return {"ok": True}

    def fill(self, *a, **k):
        return {"ok": True}


def run(fn, t, fake):
    sels = locked_sels()
    orig = (cb._eval, cb._ex_click, cb._ex_fill, cb._ex_wait_text, cb.load_selectors)
    try:
        cb._eval = fake.eval
        cb._ex_click = fake.click
        cb._ex_fill = fake.fill
        cb._ex_wait_text = lambda *a, **k: None
        cb.load_selectors = lambda path=None: sels
        return fn(t)
    finally:
        (cb._eval, cb._ex_click, cb._ex_fill, cb._ex_wait_text, cb.load_selectors) = orig


# ── plan gates ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    {"operation": "teleport"},
    {"location_id": ""},
    {"group_ref": {}},
    {"member": {}},
    {"operation": "remove", "approval_ref": ""},
    {"operation": "ban", "approval_ref": ""},
    {"operation": "role_change", "new_role": "admin", "approval_ref": ""},
    {"operation": "role_change", "new_role": "staff"},
    {"member": {"member_contact_id": "C", "ambiguous_matches": ["a", "b"]}},
    {"access_scope": "everything", "operation": "grant_access", "approval_ref": "A"},
])
def test_unsafe_member_plans_are_refused(bad):
    with pytest.raises(cm.StopAndReport):
        cm.plan_member_operation(task(**bad))


def test_routine_onboarding_may_use_automation_authorization():
    plan = cm.plan_member_operation(task(operation="approve", automation_authorized=True))
    assert plan["operation"] == "approve"
    assert plan["workflow_enrollment_is_not_access_proof"]


def test_role_change_requires_approval_even_without_elevation():
    with pytest.raises(cm.StopAndReport):
        cm.plan_member_operation(task(operation="role_change", new_role="moderator"))


def test_plan_records_scope_and_approval():
    p = cm.plan_member_operation(task(operation="remove", approval_ref="APPR-9"))
    assert p["access_scope"] == "group"
    assert p["approval_ref"] == "APPR-9"
    assert p["same_location"] is True


# ── read + row-scoped actions ───────────────────────────────────────────────
def test_list_members_matches_exact_person():
    fake = FakeRows()
    plan = cm.plan_member_operation(task())
    rows = run(lambda t: cm.list_members("s", locked_sels(), t), plan, fake)
    assert len(rows) == 1
    assert rows[0]["matches_contact_id"] is True
    assert rows[0]["matches_email"] is True


def test_role_change_is_verified_from_the_row(tmp_path):
    fake = FakeRows()
    plan = cm.plan_member_operation(task(operation="role_change", new_role="admin",
                                         approval_ref="APPR"))
    res = run(lambda t: cm.build_member_operation(t, str(tmp_path), dry_run=False, session="s"),
              task(operation="role_change", new_role="admin", approval_ref="APPR"), fake)
    assert res["ok"] is True
    assert res["verify"]["role_after"] == "admin"


def test_remove_is_verified_and_never_claims_access_elsewhere(tmp_path):
    fake = FakeRows(effect="remove")
    res = run(lambda t: cm.build_member_operation(t, str(tmp_path), dry_run=False, session="s"),
              task(operation="remove", approval_ref="APPR"), fake)
    assert res["ok"] is True
    assert res["verify"]["member_present_after"] is False
    assert res["verify"]["access_revoked"] is True


def test_remove_stops_when_the_member_is_still_present(tmp_path):
    fake = FakeRows(effect=None)
    res = run(lambda t: cm.build_member_operation(t, str(tmp_path), dry_run=False, session="s"),
              task(operation="remove", approval_ref="APPR"), fake)
    assert res["ok"] is False
    assert "remove.verify" in res["error"]


def test_grant_records_group_vs_course_offer_access(tmp_path):
    fake = FakeRows()
    res = run(lambda t: cm.build_member_operation(t, str(tmp_path), dry_run=False, session="s"),
              task(operation="grant_access", approval_ref="APPR"), fake)
    assert res["ok"] is True
    v = res["verify"]
    assert v["access_granted"] is True
    assert v["group_access"] is True
    assert v["course_offer_access"] == "unknown"
    assert v["workflow_enrollment_is_not_access_proof"]


def test_action_stops_when_the_member_is_absent(tmp_path):
    fake = FakeRows(rows=[{"text": "Someone Else other@example.com X_9 member"}])
    res = run(lambda t: cm.build_member_operation(t, str(tmp_path), dry_run=False, session="s"),
              task(operation="remove", approval_ref="APPR"), fake)
    assert res["ok"] is False
    assert "member.missing" in res["error"]


def test_invite_verifies_presence_and_does_not_claim_access(tmp_path):
    fake = FakeRows(rows=[{"text": "student@example.com CONTACT_1 invited"}])

    def click(session, sels, dotted, **kw):
        return {"ok": True}
    fake.click = click
    res = run(lambda t: cm.build_member_operation(t, str(tmp_path), dry_run=False, session="s"),
              task(operation="invite"), fake)
    assert res["ok"] is True
    assert res["verify"]["member_present"] is True
    assert res["verify"]["access_granted"] is False


def test_selftest_exit_zero():
    cp = subprocess.run([sys.executable, os.path.join(TOOLS, "ghl_community_members.py"),
                         "--selftest"], capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr
