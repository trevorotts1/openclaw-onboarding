"""WF09 — hybrid group/channel operations for ghl_community_builder.py.

Covers: role checks, approval requirements, exact requested-fields updates, access
changes, activation, channel update/order/settings, the single browser writer per
tenant, and A13 cleanup honesty (a reused group is preserved; a created scratch group
is deactivated with recorded inactive residue — never a fake delete).

No network, no browser: the shared executor primitives are injected.
"""
import copy
import json
import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_community_builder as cb  # noqa: E402


def op_task(**over):
    t = {
        "location_id": "LOC", "operation": "update",
        "community_name": "Founders",
        "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                      "portal_host": "portal.example.com"},
        "operator_role": "admin", "approval_ref": "",
        "changes": {"description": "new description"},
        "scratch_group": True,
    }
    t.update(over)
    return t


def locked_sels():
    sels = copy.deepcopy(cb.load_selectors())
    for surface in ("update_group", "access", "activate", "group_nav", "learning"):
        for name, node in sels["community"].get(surface, {}).items():
            if isinstance(node, dict) and "status" in node:
                node["status"] = "locked"
                node["anchor"] = node.get("anchor") or "getByText('x')"
    return sels


class FakeUI:
    def __init__(self, state=None, nav="General | Announcements"):
        self.state = state or {"name": "ZHC Founders", "description": "old",
                               "branding_image_url": None, "privacy": "public",
                               "status": "active"}
        self.nav = nav
        self.clicks = []
        self.fills = []

    def eval(self, session, js, timeout=12):
        if "input[placeholder*='Group Name'" in js:
            return json.dumps({k: self.state.get(k) for k in
                               ("name", "description", "branding_image_url", "privacy")})
        if "Active|Inactive" in js:
            return self.state["status"]
        if "present" in js and "JSON.stringify" in js:
            return json.dumps({"present": True, "row": "General", "rows": 2})
        if "NO_CARD" in js or "NO_CTL" in js or "NO_ROW" in js:
            return "OK"
        return ""

    def click(self, session, sels, dotted, **kw):
        self.clicks.append(dotted)
        if dotted == "community.access.privacy_control":
            self.state["privacy"] = "private"
        if dotted == "community.deactivate.inactive_option":
            self.state["status"] = "inactive"
        if dotted == "community.activate.active_option":
            self.state["status"] = "active"
        return {"ok": True, "path": "find"}

    def fill(self, session, sels, dotted, value, **kw):
        self.fills.append((dotted, value))
        if dotted.endswith("name_input"):
            self.state["name"] = value
        if dotted.endswith("description_input"):
            self.state["description"] = value
        if dotted.endswith("branding_url_input"):
            self.state["branding_image_url"] = value
        return {"ok": True, "path": "find"}


class _CP:
    returncode = 0
    stdout = ""
    stderr = ""


def run(fn, task, fake, sels=None):
    use_sels = sels if sels is not None else locked_sels()
    orig = (cb._eval, cb._ex_click, cb._ex_fill, cb._ex_wait_text, cb._snapshot,
            cb.load_selectors, cb._ab)
    try:
        cb._ab = lambda *a, **k: _CP()
        cb._eval = fake.eval
        cb._ex_click = fake.click
        cb._ex_fill = fake.fill
        cb._ex_wait_text = lambda *a, **k: None
        cb._snapshot = lambda s, timeout=20: fake.nav
        cb.load_selectors = lambda path=None: use_sels
        return fn(task)
    finally:
        (cb._eval, cb._ex_click, cb._ex_fill, cb._ex_wait_text, cb._snapshot,
         cb.load_selectors, cb._ab) = orig


# ── role + approval gates ───────────────────────────────────────────────────
def test_update_requires_admin_role():
    pf = cb.preflight_group_operation(
        cb.plan_group_operation(op_task(operator_role="member")))
    assert pf["pass"] is False
    assert "role" in pf["stop_reason"].lower()
    assert cb.preflight_group_operation(
        cb.plan_group_operation(op_task(operator_role="admin")))["pass"] is True


def test_change_access_requires_approval_and_valid_target():
    with pytest.raises(cb.StopAndReport):
        cb.plan_group_operation(op_task(operation="change_access",
                                        changes={"privacy": "private"}))
    plan = cb.plan_group_operation(op_task(operation="change_access", approval_ref="APPR",
                                           changes={"privacy": "private"}))
    assert plan["changes"] == {"privacy": "private"}
    with pytest.raises(cb.StopAndReport):
        cb.plan_group_operation(op_task(operation="change_access", approval_ref="APPR",
                                        changes={"privacy": "visible"}))


def test_channel_settings_reject_billing_changes():
    with pytest.raises(cb.StopAndReport):
        cb.plan_group_operation(op_task(operation="channel_settings", approval_ref="APPR",
                                        changes={"channel": "General", "premium": True,
                                                 "price": 9}))
    plan = cb.plan_group_operation(op_task(operation="channel_settings", approval_ref="APPR",
                                           changes={"channel": "General", "premium": True}))
    assert plan["changes"]["premium"] is True


def test_deactivate_real_group_needs_approval_but_scratch_does_not():
    with pytest.raises(cb.StopAndReport):
        cb.plan_group_operation(op_task(operation="deactivate", scratch_group=False))
    plan = cb.plan_group_operation(op_task(operation="deactivate", scratch_group=True))
    assert plan["operation"] == "deactivate"


def test_update_rejects_unsupported_fields():
    with pytest.raises(cb.StopAndReport):
        cb.plan_group_operation(op_task(changes={"privacy": "private"}))
    with pytest.raises(cb.StopAndReport):
        cb.plan_group_operation(op_task(changes={}))


# ── exact requested-fields update ───────────────────────────────────────────
def test_update_writes_only_requested_fields_and_verifies_them():
    fake = FakeUI()
    plan = cb.plan_group_operation(op_task(changes={"description": "new description"}))
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["changed_fields"] == ["description"]
    assert res["after"]["description"] == "new description"
    # the name/branding were NOT rewritten
    assert not any("name_input" in f[0] for f in fake.fills)
    assert not any("branding_url_input" in f[0] for f in fake.fills)
    assert res["before"]["name"] == "ZHC Founders"


def test_update_stops_when_saved_value_is_not_confirmed():
    fake = FakeUI()
    # a fill that silently fails to bind (Naive-UI) leaves the old value
    orig_fill = fake.fill

    def no_bind(session, sels, dotted, value, **kw):
        fake.fills.append((dotted, value))
        return {"ok": True, "path": "find"}
    fake.fill = no_bind
    plan = cb.plan_group_operation(op_task(changes={"description": "new description"}))
    with pytest.raises(cb.StopAndReport):
        run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    fake.fill = orig_fill


def test_change_access_verifies_privacy():
    fake = FakeUI()
    plan = cb.plan_group_operation(op_task(operation="change_access", approval_ref="APPR",
                                           changes={"privacy": "private"}))
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["after"]["privacy"] == "private"
    assert res["member_consequences"] == "not_measured"


# ── activation / deactivation ───────────────────────────────────────────────
def test_deactivate_records_inactive_residue_and_no_delete():
    fake = FakeUI()
    plan = cb.plan_group_operation(op_task(operation="deactivate", scratch_group=True))
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["status"] == "inactive"
    assert res["deleted"] is False
    assert res["inactivated"] is True
    assert res["group_url"] == "https://portal.example.com/communities/groups/zhc-founders/home"
    assert res["residue"]


def test_activate_verifies_active_state():
    fake = FakeUI(state={"name": "ZHC Founders", "description": "", "branding_image_url": None,
                         "privacy": "private", "status": "inactive"})
    plan = cb.plan_group_operation(op_task(operation="activate"))
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["status"] == "active" and res["deleted"] is False


# ── channels ────────────────────────────────────────────────────────────────
def test_channel_update_verifies_presence():
    fake = FakeUI(nav="General | Announcements")
    plan = cb.plan_group_operation(op_task(
        operation="channel_update", changes={"channel": "General", "name": "General Chat"}))
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["new_name"] == "General Chat"
    assert res["observed"]["present"] is True


def test_channel_order_verifies_rendered_order():
    plan = cb.plan_group_operation(op_task(
        operation="channel_order", changes={"order": ["General", "Announcements"]}))
    fake = FakeUI(nav="General | Announcements")
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["positions"] == sorted(res["positions"])
    fake2 = FakeUI(nav="Announcements | General")
    with pytest.raises(cb.StopAndReport):
        run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake2)


def test_channel_settings_applies_toggles_without_billing():
    plan = cb.plan_group_operation(op_task(
        operation="channel_settings", approval_ref="APPR",
        changes={"channel": "General", "private": True, "read_only": True}))
    fake = FakeUI()
    res = run(lambda t: cb.execute_group_operation("s", locked_sels(), t), plan, fake)
    assert res["applied"] == {"private": True, "read_only": True}
    assert res["billing_unchanged"] is True


# ── single browser writer per tenant/session ────────────────────────────────
def test_one_browser_writer_per_location():
    cb.release_browser_writer("LOC-W")
    assert cb.acquire_browser_writer("LOC-W", "first") == "first"
    with pytest.raises(cb.StopAndReport):
        cb.acquire_browser_writer("LOC-W", "second")
    cb.release_browser_writer("LOC-W")
    assert cb.acquire_browser_writer("LOC-W", "third") == "third"
    cb.release_browser_writer("LOC-W")
    assert cb.active_writer("LOC-W") is None


def test_writer_lock_is_per_location():
    cb.release_browser_writer("LOC-A")
    cb.release_browser_writer("LOC-B")
    cb.acquire_browser_writer("LOC-A")
    cb.acquire_browser_writer("LOC-B")   # different tenant → independent
    assert cb.active_writer("LOC-A") and cb.active_writer("LOC-B")
    cb.release_browser_writer("LOC-A")
    cb.release_browser_writer("LOC-B")


def test_writer_context_manager_releases_on_error():
    cb.release_browser_writer("LOC-C")
    with pytest.raises(RuntimeError):
        with cb.browser_writer("LOC-C", "x"):
            raise RuntimeError("boom")
    assert cb.active_writer("LOC-C") is None


# ── A13: cleanup honesty ────────────────────────────────────────────────────
def test_a13_reused_group_is_preserved_never_deleted():
    d = cb.cleanup_decision("reused", identity_present=False)
    assert d["cleanup_primitive"] == "preserve"
    assert d["deleted"] is False
    assert d["reused_resources_preserved"] is True


def test_a13_created_scratch_group_is_deactivated_not_deleted():
    d = cb.cleanup_decision("created", identity_present=True)
    assert d["cleanup_primitive"] == "inactivate"
    assert d["deleted"] is False


def test_a13_deactivate_group_result_carries_residue_coordinates():
    fake = FakeUI()
    locked = locked_sels()
    res = run(lambda t: cb._deactivate_group("s", locked, {"slug": "zhc-founders"},
                                             {"slug": "zhc-founders",
                                              "portal_host": "portal.example.com",
                                              "portal_url": "u"}, "LOC"),
              {}, fake)
    assert res["cleanup_primitive"] == "inactivate"
    assert res["deleted"] is False
    assert res["inactivated"] is True
    assert res["group_url"].endswith("/zhc-founders/home")


# ── dry-run dispatch ────────────────────────────────────────────────────────
def test_operation_dry_run_returns_plan_without_browser(tmp_path):
    res = cb.build_community(op_task(operation="update"), str(tmp_path), dry_run=True)
    assert res["ok"] is True and res["dry_run"] is True
    assert res["plan"]["operation"] == "update"
    assert os.path.isfile(os.path.join(str(tmp_path), "routing", "group-operation-plan.json"))
