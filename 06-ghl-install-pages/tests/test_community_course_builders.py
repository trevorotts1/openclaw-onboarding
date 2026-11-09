"""Tests for the Skill-6 COMMUNITY / COURSE / CHANNEL browser builders (units
U13/U14/U15) + their router registration (U7) + QC gates.

No network, no browser. Proves: THINK-layer plans (ZHC naming, dedupe, Firebase
rejection), the D8 capture-pending selector gate (a REQUIRED capture-pending anchor
STOP-and-reports; a verified-shared-rail anchor is returned), F6 receipt reduction,
dry-run artifact emission, and that each module's own network-free `--selftest`
passes. Mirrors the shape of the existing form/survey builder tests.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import ghl_object_router as router  # noqa: E402
import ghl_community_builder as cb  # noqa: E402
import ghl_course_builder as course  # noqa: E402


# ── router registration (U7 / §3) ────────────────────────────────────────────
@pytest.mark.parametrize("obj", ["community", "course", "channel"])
def test_router_registers_new_objects(obj):
    r = router.route(obj)
    assert r.object_type == obj
    assert r.create_api_exists is False          # browser is the ONLY create rail
    assert r.rails[0].rail == router.Rail.BROWSER
    assert r.rails[0].tier == router.Tier.BROWSER
    # disclosure line is emitted per spec §3 / Skill 36
    disc = router.tier_disclosure(r.rails[0])
    assert disc.startswith("[GHL tier used: 4")


# ── community THINK layer ─────────────────────────────────────────────────────
def test_community_zhc_and_channel_dedupe():
    plan = cb.plan_community({"community_name": "Founders", "location_id": "L",
                              "privacy": "Private",
                              "channels": ["Welcome", "General", "General"]})
    assert plan["community_name"] == "ZHC Founders"
    assert plan["privacy"] == "private"
    assert [c["name"] for c in plan["channels"]] == ["Welcome", "General"]


def test_community_rejects_firebase_branding():
    with pytest.raises(cb.StopAndReport):
        cb.plan_community({"community_name": "X", "location_id": "L",
                           "branding_image_url": "https://firebasestorage.googleapis.com/x"})


def test_community_preflight_fails_without_zhc_or_location():
    pf = cb._preflight({"community_name": "NoPrefix", "slug": "x", "location_id": "",
                        "description": "", "privacy": "weird", "channels": [],
                        "branding_image_url": ""})
    assert pf["pass"] is False


def test_community_dry_run_writes_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        res = cb.build_community({"community_name": "Founders", "location_id": "L",
                                  "channels": ["Welcome"]}, tmp, dry_run=True)
        assert res["dry_run"] and res["ok"]
        phases = {s["phase"] for s in res["click_list"]["steps"]}
        assert {"C1", "C2", "C3", "C4", "C5"} <= phases
        assert os.path.isfile(os.path.join(tmp, "routing", "community-plan.json"))
        assert os.path.isfile(os.path.join(tmp, "routing", "community-click-list.json"))


# ── D8 capture-pending selector gate ──────────────────────────────────────────
def test_d8_gate_verified_returns_and_capture_pending_stops():
    sels = cb.load_selectors()
    # verified-shared-rail → returns the anchor
    assert cb.anchor(sels, "shared_rail.memberships_left_rail").startswith("getByText")
    # a Phase-B LOCKed anchor → returns the anchor
    assert cb.anchor(sels, "community.list_page.create_group_button").startswith("getByRole")
    # a STILL capture-pending REQUIRED → STOP-and-report (never a guessed CSS)
    with pytest.raises(cb.StopAndReport):
        cb.anchor(sels, "community.create_page.privacy_switch")
    # capture-pending OPTIONAL → '' (soft skip)
    assert cb.anchor(sels, "community.create_page.privacy_switch", required=False) == ""


def test_selector_map_has_no_locked_inarea_targets_yet():
    """Phase B (2026-07-10) LOCKed the in-area community/course anchors from a LIVE
    create-then-clean run. Guard: every LOCKed target carries a real anchor, and the ONLY
    remaining capture-pending in-area targets are the documented not-yet-captured set."""
    sels = cb.load_selectors()
    # Phase B's documented not-yet-captured set (community create flow + course wizard).
    pending_phase_b = {"privacy_switch", "product_type", "lesson_body_editor",
                       "settings_nav", "status_toggle"}
    # WF09 hybrid surfaces added AFTER Phase B: deliberately capture-pending until a
    # live capture locks them (D8 — the live walk STOP-and-reports; nothing is faked).
    wf09_surfaces = {"learning", "update_group", "access", "activate", "members",
                     "content", "group_nav"}
    pending_wf09 = {
        # learning association (WF09-CP01)
        "learning_tab", "association_rows", "add_existing_course_control",
        "course_picker_search", "course_option", "policy_select", "policy_option",
        "save_association", "associations_reload", "detach_confirm",
        # group details / access / activation
        "settings_entry", "details_tab", "name_input", "description_input",
        "branding_url_input", "save_button", "privacy_control", "access_save_confirm",
        "active_option",
        # channels: update / order / settings
        "channel_rows", "channel_edit_control", "channel_rename_input",
        "channel_save_confirm", "channel_settings_control", "channel_private_switch",
        "channel_readonly_switch", "channel_premium_switch", "channel_order_control",
        # member administration
        "members_tab", "member_rows", "member_search_input", "invite_control",
        "invite_email_input", "invite_confirm", "approve_control", "remove_control",
        "ban_control", "role_control", "role_option", "role_confirm",
        "grant_access_control", "revoke_access_control", "confirm_action",
        "member_rows_reload",
        # content / moderation
        "content_tab", "content_rows", "pin_control", "unpin_control", "hide_control",
        "restore_control", "delete_control", "content_reload",
    }
    locked_count = 0
    for top in ("community", "course"):
        for surface, targets in sels[top].items():
            if not isinstance(targets, dict):
                continue
            for tname, t in targets.items():
                if not (isinstance(t, dict) and "status" in t):
                    continue
                if t["status"] == "locked":
                    assert t.get("anchor"), f"{top}.{surface}.{tname} locked but has no anchor"
                    locked_count += 1
                elif t["status"] == "capture-pending":
                    if surface in wf09_surfaces:
                        assert tname in pending_wf09, (
                            f"{top}.{surface}.{tname} is pending but not in the documented "
                            "WF09 pending-by-design set")
                        assert t.get("note"), (
                            f"{top}.{surface}.{tname} pending without an explanatory note")
                    else:
                        assert tname in pending_phase_b, (
                            f"{top}.{surface}.{tname} unexpectedly capture-pending "
                            "(Phase B LOCKed it?)")
    assert locked_count >= 20, f"expected the Phase B LOCKed in-area set, got {locked_count}"


# ── course THINK layer ────────────────────────────────────────────────────────
def test_course_module_lesson_dedupe_and_draft_default():
    task = {"course_name": "Launch", "location_id": "L", "modules": [
        {"title": "Welcome", "lessons": [{"title": "Intro"}, {"title": "Intro"}]},
        {"title": "Welcome", "lessons": []}]}
    plan = course.plan_course(task)
    assert plan["course_name"] == "ZHC Launch"
    assert [m["title"] for m in plan["modules"]] == ["Welcome"]
    assert len(plan["modules"][0]["lessons"]) == 1
    assert plan["publish"] is False                    # default DRAFT


def test_course_publish_requires_approval():
    task = {"course_name": "L", "location_id": "L",
            "modules": [{"title": "M", "lessons": [{"title": "x"}]}]}
    assert course.plan_course({**task, "publish": True})["publish"] is False
    assert course.plan_course({**task, "publish": True, "approval": "approved"})["publish"] is True


def test_course_rejects_firebase_media():
    with pytest.raises(course.StopAndReport):
        course.plan_course({"course_name": "X", "location_id": "L", "modules": [
            {"title": "M", "lessons": [
                {"title": "L", "media_url": "https://firebasestorage.googleapis.com/x"}]}]})


def test_course_dry_run_has_all_phases():
    task = {"course_name": "Launch", "location_id": "L",
            "modules": [{"title": "M", "lessons": [{"title": "L1"}, {"title": "L2"}]}]}
    with tempfile.TemporaryDirectory() as tmp:
        res = course.build_course(task, tmp, dry_run=True)
        assert res["ok"] and res["dry_run"]
        phases = {s["phase"] for s in res["click_list"]["steps"]}
        assert {"M1", "M2", "M3", "M4", "M5", "M6"} <= phases
        assert res["plan"]["lesson_count"] == 2


# ── F6 receipts + resume ──────────────────────────────────────────────────────
def test_receipt_reduction_surfaces_failure():
    with tempfile.TemporaryDirectory() as tmp:
        router.write_receipt(tmp, router.make_receipt("community", "z", "created", verify={"http": 200}))
        router.write_receipt(tmp, router.make_receipt("channel", "gen", "failed", error="miss"))
        summ = router.reduce_receipts(tmp)
        assert summ["all_verified"] is False
        assert "channel:gen" in summ["failed"]


def test_course_resume_detects_done_lessons():
    with tempfile.TemporaryDirectory() as tmp:
        router.write_receipt(tmp, router.make_receipt("lesson", "welcome-intro", "created",
                                                      verify={"present_in_outline": True}))
        done = course._resume_done_lessons(tmp)
        assert "welcome-intro" in done


# ── each module's own network-free selftest passes ────────────────────────────
@pytest.mark.parametrize("script", [
    "ghl_community_builder.py", "ghl_course_builder.py"])
def test_builder_selftest_exit_zero(script):
    cp = subprocess.run([sys.executable, os.path.join(TOOLS, script), "--selftest"],
                        capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr


# ── QC gates selftest ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("gate", ["qc-built-community.sh", "qc-built-course.sh"])
def test_qc_gate_selftest_exit_zero(gate):
    cp = subprocess.run(["bash", os.path.join(SKILL_DIR, gate), "--selftest"],
                        capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr
