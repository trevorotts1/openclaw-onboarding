"""WF09 — Community UI content/moderation gaps.

Proves the route split (public post/comment → WF10; only pin/moderate/delete is UI here),
moderation approvals and roles, exact-content scoping, and verified state read-back.
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
import ghl_community_content as cc  # noqa: E402


def task(**over):
    t = {"location_id": "LOC", "operation": "pin", "content_id": "POST_1",
         "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                       "portal_host": "portal.example.com"},
         "operator_role": "moderator", "approval_ref": ""}
    t.update(over)
    return t


def locked_sels():
    sels = copy.deepcopy(cb.load_selectors())
    for name, node in sels["community"]["content"].items():
        if isinstance(node, dict) and "status" in node:
            node["status"] = "locked"
            node["anchor"] = node.get("anchor") or "getByText('Content')"
    return sels


class FakeContent:
    def __init__(self, rows=None, effect=None):
        self.rows = rows if rows is not None else [
            {"text": "POST_1 welcome everyone", "content_id": "POST_1"}]
        self.effect = effect

    def eval(self, session, js, timeout=12):
        return json.dumps(self.rows)

    def click(self, session, sels, dotted, **kw):
        if dotted == "community.content.confirm_action":
            if self.effect == "hidden":
                self.rows = [{"text": "POST_1 hidden post", "content_id": "POST_1"}]
            elif self.effect == "deleted":
                self.rows = []
        return {"ok": True}


def run(fn, t, fake):
    sels = locked_sels()
    orig = (cb._eval, cb._ex_click, cb._ex_wait_text, cb.load_selectors)
    try:
        cb._eval = fake.eval
        cb._ex_click = fake.click
        cb._ex_wait_text = lambda *a, **k: None
        cb.load_selectors = lambda path=None: sels
        return fn(t)
    finally:
        (cb._eval, cb._ex_click, cb._ex_wait_text, cb.load_selectors) = orig


# ── route split ─────────────────────────────────────────────────────────────
def test_public_post_intents_route_to_wf10():
    r = cc.classify_route({"intent": "post_create"})
    assert r["route"] == "public_social_planner" and r["owner"] == "WF10"
    assert r["supported_here"] is False


def test_moderation_routes_here_and_unknown_is_unavailable():
    assert cc.classify_route({"intent": "moderate"})["supported_here"] is True
    assert cc.classify_route({"intent": "teleport"})["route"] == "feature_unavailable"


# ── plan gates ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    {"operation": "hide", "approval_ref": ""},
    {"operation": "delete", "approval_ref": ""},
    {"operation": "pin", "operator_role": "member"},
    {"content_id": "", "permalink": ""},
    {"operation": "nope"},
    {"operation": "verify_view", "viewer": {}},
])
def test_unsafe_content_plans_are_refused(bad):
    with pytest.raises(cc.StopAndReport):
        cc.plan_content_operation(task(**bad))


def test_moderate_alias_maps_to_effect():
    p = cc.plan_content_operation(task(operation="moderate", effect="hide",
                                       approval_ref="APPR"))
    assert p["operation"] == "hide"


# ── queue read + verified actions ───────────────────────────────────────────
def test_list_moderation_queue_reads_state():
    fake = FakeContent(rows=[{"text": "POST_1 hidden post", "content_id": "POST_1"}])
    plan = cc.plan_content_operation(task(operation="list_pending"))
    rows = run(lambda t: cc.list_moderation_queue("s", locked_sels(), t), plan, fake)
    assert rows[0]["state"] == "hidden"


def test_pin_verifies_state():
    fake = FakeContent(rows=[{"text": "POST_1 welcome", "content_id": "POST_1"}],
                       effect=None)
    plan = cc.plan_content_operation(task(operation="pin"))
    # pin state must be observable after the action
    fake.rows = [{"text": "POST_1 welcome", "content_id": "POST_1"}]
    orig_click = fake.click

    def click(session, sels, dotted, **kw):
        fake.rows = [{"text": "POST_1 pinned", "content_id": "POST_1"}]
        return orig_click(session, sels, dotted, **kw)
    fake.click = click
    res = run(lambda t: cc.execute_content_operation("s", locked_sels(), t), plan, fake)
    assert res["verify"]["state_after"] == "pinned"


def test_hide_stops_when_state_is_not_confirmed():
    fake = FakeContent()          # confirm leaves the row visible
    plan = cc.plan_content_operation(task(operation="hide", approval_ref="APPR"))
    with pytest.raises(cc.StopAndReport):
        run(lambda t: cc.execute_content_operation("s", locked_sels(), t), plan, fake)


def test_delete_verifies_absence(tmp_path):
    fake = FakeContent(effect="deleted")
    res = run(lambda t: cc.build_content_operation(
        t, str(tmp_path), dry_run=False, session="s"),
        task(operation="delete", approval_ref="APPR"), fake)
    assert res["ok"] is True
    assert res["verify"]["content_present_after"] is False


def test_view_check_fails_when_viewer_cannot_see_content():
    fake = FakeContent(rows=[])
    plan = cc.plan_content_operation(task(operation="verify_view",
                                          viewer={"email": "student@example.com"}))
    with pytest.raises(cc.StopAndReport):
        run(lambda t: cc.execute_content_operation("s", locked_sels(), t), plan, fake)


def test_selftest_exit_zero():
    cp = subprocess.run([sys.executable, os.path.join(TOOLS, "ghl_community_content.py"),
                         "--selftest"], capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr
