"""WF09 — Course-to-Learning association acceptance tests (A12).

Proves the relationship operator (ghl_learning_association.py) is a SEPARATE,
idempotent, same-location relationship: it attaches an EXISTING course (never
"Create new course"), preserves/verifies the approved policy, writes its own
relationship receipt, and detaches ONLY the relationship without deleting the course.

No network, no browser: the shared Skill-6 executor primitives are injected.
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
import ghl_learning_association as la  # noqa: E402


def task(**over):
    t = {
        "schema_version": "1.0.0", "location_id": "LOC",
        "course_product_id": "COURSE_123", "course_name": "ZHC Launch 101",
        "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                      "portal_host": "portal.example.com"},
        "desired_access": {"mode": "all_members", "policy_ref": "APPROVED_POLICY",
                           "policy_label": "All members"},
        "operation": "attach", "approval_ref": "APPR-1",
    }
    t.update(over)
    return t


def locked_sels():
    sels = copy.deepcopy(cb.load_selectors())
    for name, node in sels["community"]["learning"].items():
        if isinstance(node, dict) and "status" in node:
            node["status"] = "locked"
            node["anchor"] = node.get("anchor") or "getByText('Learning')"
    return sels


class FakeBrowser:
    """Counts every write; lets a test flip the association state after a save."""

    def __init__(self, rows_before, rows_after=None):
        self.rows_before = rows_before
        self.rows_after = rows_before if rows_after is None else rows_after
        self.reads = 0
        self.clicks = []
        self.fills = []

    def _rows_json(self, rows):
        return json.dumps([{"text": r} for r in rows])

    def eval(self, session, js, timeout=12):
        if "data-testid*=association" in js and "JSON.stringify(out)" in js:
            self.reads += 1
            return self._rows_json(self.rows_before if self.reads == 1 else self.rows_after)
        if "NO_ROW" in js and "NO_CTL" in js:
            return "OK"
        return ""

    def ab(self, session, *args, timeout=15, stdin=None):
        return type("CP", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    @property
    def targets(self):
        return [c[0] for c in self.clicks]


def run_live(tmp, t, fake, *, sels=None):
    use_sels = sels if sels is not None else locked_sels()
    orig = (cb._eval, cb._ab, cb._ex_click, cb._ex_fill, cb._list_has,
            cb._snapshot, cb.load_selectors)
    try:
        cb._eval = fake.eval
        cb._ab = fake.ab

        def fake_click(session, s, dotted, **kw):
            fake.clicks.append((dotted, kw))
            return {"ok": True, "path": "find"}

        def fake_fill(session, s, dotted, value, **kw):
            fake.fills.append((dotted, value))
            return {"ok": True, "path": "find"}

        cb._ex_click = fake_click
        cb._ex_fill = fake_fill
        cb._list_has = lambda session, name, slug="": True
        cb._snapshot = lambda s, timeout=20: "ZHC Launch 101"
        cb.load_selectors = lambda path=None: use_sels
        return la.build_association(t, tmp, dry_run=False, session="s")
    finally:
        (cb._eval, cb._ab, cb._ex_click, cb._ex_fill, cb._list_has,
         cb._snapshot, cb.load_selectors) = orig


# ── A12: same location ──────────────────────────────────────────────────────
def test_a12_cross_location_association_is_refused():
    with pytest.raises(la.StopAndReport):
        la.plan_association(task(course_location_id="OTHER_LOC"))
    with pytest.raises(la.StopAndReport):
        la.plan_association(task(group_location_id="OTHER_LOC"))


def test_a12_plan_records_same_location_evidence():
    plan = la.plan_association(task(course_location_id="LOC", group_location_id="LOC"))
    assert plan["same_location"] is True
    assert any("course_location_id=LOC" in e for e in plan["location_evidence"])


# ── A12: existing course only / never create ────────────────────────────────
@pytest.mark.parametrize("bad", [{"course_product_id": ""}, {"course_product_id": "new"},
                                 {"create_course": True}])
def test_a12_attach_requires_resolved_existing_course(bad):
    with pytest.raises(la.StopAndReport):
        la.plan_association(task(**bad))


def test_a12_forbidden_create_control_is_refused():
    with pytest.raises(la.StopAndReport):
        la._click("s", {}, "course.create_modal.create_confirm")
    with pytest.raises(la.StopAndReport):
        la._click("s", {}, "community.learning.create_new_course")


# ── A12: idempotent attach ──────────────────────────────────────────────────
def test_a12_attach_reuses_matching_course_and_policy_without_clicking_create(tmp_path):
    fake = FakeBrowser(["ZHC Launch 101 — COURSE_123 — All members"])
    res = run_live(str(tmp_path), task(), fake)
    assert res["ok"] and res["action"] == "reused"
    # only the Learning-tab navigation was clicked: no add/picker/save at all
    assert fake.targets == ["community.learning.learning_tab"]
    assert not any("course" in t and "add_existing" in t for t in fake.targets)


def test_a12_relationship_receipt_is_separate_from_the_course_receipt(tmp_path):
    fake = FakeBrowser(["ZHC Launch 101 — COURSE_123 — All members"])
    res = run_live(str(tmp_path), task(), fake)
    eco = os.path.join(str(tmp_path), "ecosystem")
    files = sorted(os.listdir(eco))
    assert files == ["learning_association-zhc_launch_101.json"], files
    rec = json.load(open(os.path.join(eco, files[0]), encoding="utf-8"))
    assert rec["object_type"] == "learning_association"
    assert rec["verify"]["ok"] is True
    assert rec["response_id"] == "COURSE_123"
    assert res["receipt_path"].endswith("learning_association-zhc_launch_101.json")


def test_a12_attach_creates_association_when_absent(tmp_path):
    fake = FakeBrowser([], ["ZHC Launch 101 — COURSE_123 — All members"])
    res = run_live(str(tmp_path), task(), fake)
    assert res["ok"] and res["action"] == "created"
    assert "community.learning.add_existing_course_control" in fake.targets
    assert "community.learning.save_association" in fake.targets
    assert not any("create_modal" in t for t in fake.targets)


def test_a12_attach_never_duplicates_and_updates_only_policy(tmp_path):
    fake = FakeBrowser(["ZHC Launch 101 — COURSE_123 — Paid"],
                       ["ZHC Launch 101 — COURSE_123 — All members"])
    res = run_live(str(tmp_path), task(), fake)
    assert res["ok"] and res["action"] == "created"
    assert "community.learning.add_existing_course_control" not in fake.targets
    assert "community.learning.policy_select" in fake.targets


def test_a12_attach_stops_when_policy_not_confirmed_after_save(tmp_path):
    fake = FakeBrowser([], ["ZHC Launch 101 — COURSE_123 — Paid"])
    res = run_live(str(tmp_path), task(), fake)
    assert res["ok"] is False
    assert "attach.policy" in (res.get("error") or "")


def test_a12_attach_stops_when_association_missing_after_save(tmp_path):
    fake = FakeBrowser([], [])
    res = run_live(str(tmp_path), task(), fake)
    assert res["ok"] is False
    assert "attach.verify" in (res.get("error") or "")


# ── A12: detach removes the relationship, never the course ─────────────────
def test_a12_detach_removes_relationship_and_proves_course_survives(tmp_path):
    fake = FakeBrowser(["ZHC Launch 101 — COURSE_123 — All members"], [])
    res = run_live(str(tmp_path), task(operation="detach"), fake)
    assert res["ok"] and res["action"] == "detached"
    art = json.load(open(res["artifact_path"], encoding="utf-8"))
    assert art["operation"] == "detach"
    assert art["verify"]["association_present_after"] is False
    assert art["verify"]["course_deleted"] is False
    assert art["verify"]["course_still_present"] is True
    # no receipt for a detach (receipts describe created objects), and no delete rail
    assert not os.path.isdir(os.path.join(str(tmp_path), "ecosystem"))
    assert not any("delete" in t.lower() for t in fake.targets)


def test_a12_detach_when_absent_is_idempotent_noop(tmp_path):
    fake = FakeBrowser([])
    res = run_live(str(tmp_path), task(operation="detach"), fake)
    assert res["ok"] and res["action"] == "already_absent"
    art = json.load(open(res["artifact_path"], encoding="utf-8"))
    assert art["verify"]["association_present_before"] is False
    assert art["verify"]["course_deleted"] is False


def test_a12_detach_stops_when_relationship_remains(tmp_path):
    fake = FakeBrowser(["ZHC Launch 101 — COURSE_123 — All members"],
                       ["ZHC Launch 101 — COURSE_123 — All members"])
    res = run_live(str(tmp_path), task(operation="detach"), fake)
    assert res["ok"] is False
    assert "detach.verify" in (res.get("error") or "")


# ── policy + approval boundaries ────────────────────────────────────────────
def test_a12_missing_approval_is_refused():
    with pytest.raises(la.StopAndReport):
        la.plan_association(task(approval_ref=""))


def test_a12_paid_mode_rejects_price_fields():
    with pytest.raises(la.StopAndReport):
        la.plan_association(task(desired_access={
            "mode": "paid", "policy_ref": "P", "policy_label": "Paid", "price": 99}))


def test_a12_non_default_mode_requires_policy_ref():
    with pytest.raises(la.StopAndReport):
        la.plan_association(task(desired_access={"mode": "level",
                                                 "policy_label": "Level 2"}))


def test_selftest_exit_zero():
    cp = subprocess.run([sys.executable, os.path.join(TOOLS, "ghl_learning_association.py"),
                         "--selftest"], capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr
