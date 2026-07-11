"""Tests for the Phase-A COMMUNITY/COURSE live-ready fixes (branch
`skill6-community-course-live-ready`) — the 5 go-forward items that make the browser
builders driveable by agent-browser 0.27.0:

  (a) anchor→executor resolver (ghl_ab_executor): Playwright getBy* → `find …`/native .click()
  (b) list-scan idempotency (communities have NO search box)
  (c) group identity = slug + white-label portal host (not an opaque id)
  (d) HONEST no-group-delete cleanup (Inactive) + true-delete scoped to courses
  (e) render-check on the derived public-or-authenticated portal URL

No network, no browser, no GHL write. Everything is proven with injected fakes; all
in-area selectors stay `capture-pending` (Phase B locks them).
"""
import contextlib
import json
import os
import shlex
import subprocess
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_ab_executor as abx  # noqa: E402
import ghl_community_builder as cb  # noqa: E402
import ghl_course_builder as course  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# (a) anchor→executor resolver — the agent-browser 0.27.0 syntax adapter
# ═══════════════════════════════════════════════════════════════════════════
def test_parse_role_plain_name():
    d = abx.parse_anchor("getByRole('button', { name: 'Create Group' })")
    assert d["strategy"] == "role" and d["role"] == "button" and d["name"] == "Create Group"
    assert d["name_regex"] is None


def test_parse_text_placeholder_label():
    assert abx.parse_anchor("getByText('Memberships')")["value"] == "Memberships"
    assert abx.parse_anchor("getByPlaceholder('Group Name')")["strategy"] == "placeholder"
    assert abx.parse_anchor("getByLabel('Email')")["strategy"] == "label"


def test_parse_ref_and_css_passthrough():
    assert abx.parse_anchor("@e3")["strategy"] == "ref"
    assert abx.parse_anchor("button.primary")["strategy"] == "css"


def test_regex_name_routes_native():
    d = abx.parse_anchor("getByRole('button', { name: /Create|Add/ })")
    assert abx.needs_native(d) is True
    assert abx.to_find_args(d) == []          # can't be a `find --name <plain>` — must go native


def test_to_find_args_click_role():
    args = abx.to_find_args(abx.parse_anchor("getByRole('button', { name: 'Create Group' })"), "click")
    assert args == ["find", "role", "button", "click", "--name", shlex.quote("Create Group")]


def test_to_find_args_click_text():
    assert abx.to_find_args(abx.parse_anchor("getByText('Memberships')"), "click") == \
        ["find", "text", "Memberships", "click"]


def test_to_find_args_fill_placeholder():
    args = abx.to_find_args(abx.parse_anchor("getByPlaceholder('Group Name')"), "fill", "Acme")
    assert args == ["find", "placeholder", shlex.quote("Group Name"), "fill", "Acme"]


def test_multiword_name_survives_browser_cmd_shlex_roundtrip():
    """browser_cmd space-joins args then _ab shlex.splits — a raw multi-word --name would
    be re-split into two tokens. The executor shlex.quotes it so it round-trips as ONE."""
    args = abx.to_find_args(abx.parse_anchor("getByRole('button', { name: 'Create Group' })"), "click")
    joined = "agent-browser --headed false --session s " + " ".join(args)
    assert shlex.split(joined)[-2:] == ["--name", "Create Group"]


def test_native_click_js_has_click_and_label_and_regex():
    js = abx.native_click_js(abx.parse_anchor("getByRole('button', { name: 'CREATE CHANNEL' })"))
    assert ".click()" in js and "CREATE CHANNEL" in js
    rjs = abx.native_click_js(abx.parse_anchor("getByRole('button', { name: /Create/ })"))
    assert "new RegExp" in rjs


def _fake_ab_factory(calls, miss_placeholder=False):
    def fake_ab(session, *args, timeout=15):
        calls.append(args)
        verb = args[0] if args else ""
        if miss_placeholder and verb == "find" and len(args) > 1 and args[1] == "placeholder":
            return subprocess.CompletedProcess(args, 1, "", "Element not found")
        return subprocess.CompletedProcess(args, 0, "✓ Done", "")
    return fake_ab


def test_executor_find_click_path():
    calls = []
    ex = abx.AbExecutor(ab=_fake_ab_factory(calls), ev=lambda s, j, timeout=15: "CLICKED:x")
    r = ex.click("s", "getByRole('button', { name: 'Create Group' })")
    assert r["ok"] and r["path"] == "find"
    assert ("find", "role", "button", "click", "--name", shlex.quote("Create Group")) in calls


def test_executor_native_mode_uses_eval():
    evals = []

    def fake_ev(s, js, timeout=15):
        evals.append(js)
        return "CLICKED:Create Group"
    ex = abx.AbExecutor(ab=_fake_ab_factory([]), ev=fake_ev)
    r = ex.click("s", "getByRole('button', { name: 'Create Group' })", mode="native")
    assert r["ok"] and r["path"] == "native"
    assert any(".click()" in j for j in evals)


def test_executor_find_miss_falls_back_to_native():
    ex = abx.AbExecutor(ab=_fake_ab_factory([], miss_placeholder=True),
                        ev=lambda s, j, timeout=15: "CLICKED:x")
    r = ex.click("s", "getByPlaceholder('Search')")     # find placeholder MISS → native
    assert r["ok"] and r["path"] == "native"


def test_executor_fill_falls_back_to_native_reactive_set():
    ex = abx.AbExecutor(ab=_fake_ab_factory([], miss_placeholder=True),
                        ev=lambda s, j, timeout=15: "FILLED")
    r = ex.fill("s", "getByPlaceholder('Group Name')", "Acme")
    assert r["ok"] and r["path"] == "native"


def test_executor_wait_text_quotes_multiword():
    calls = []
    ex = abx.AbExecutor(ab=_fake_ab_factory(calls), ev=lambda s, j, timeout=15: "")
    ex.wait_text("s", "ZHC Founders Circle")
    assert ("wait", "--", shlex.quote("ZHC Founders Circle")) in calls


def test_executor_selftest_exit_zero():
    cp = subprocess.run([sys.executable, os.path.join(TOOLS, "ghl_ab_executor.py"), "--selftest"],
                        capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr


# ═══════════════════════════════════════════════════════════════════════════
# shared fake-injection helper (community builder owns the browser primitives)
# ═══════════════════════════════════════════════════════════════════════════
@contextlib.contextmanager
def patched_cb(*, snapshot="", eval_fn=None, ab=None):
    """Patch the community-module browser primitives (_ab/_eval/_snapshot) used by the
    shared executor wrappers + list-scan. Both builders route through these."""
    orig = (cb._ab, cb._eval, cb._snapshot)
    try:
        cb._snapshot = (snapshot if callable(snapshot)
                        else (lambda s, timeout=20: snapshot))
        cb._eval = eval_fn or (lambda s, js, timeout=20: "")
        if ab is not None:
            cb._ab = ab
        yield
    finally:
        cb._ab, cb._eval, cb._snapshot = orig


# ═══════════════════════════════════════════════════════════════════════════
# (b) list-scan idempotency — communities list has NO search box
# ═══════════════════════════════════════════════════════════════════════════
def test_community_selectors_have_no_search_box():
    """fix b: the false community search_box (+ false group-delete) anchors are removed."""
    sels = cb.load_selectors()
    assert "search_box" not in sels["community"]["list_page"]
    assert "row_actions" not in sels["community"]["list_page"]
    assert "delete_menuitem" not in sels["community"]["list_page"]


def test_community_click_list_c2_is_list_scan():
    plan = cb.plan_community({"community_name": "Founders", "location_id": "L", "channels": []})
    cl = cb.emit_click_list(plan)
    c2 = [s for s in cl["steps"] if s["phase"] == "C2"][0]
    assert c2["action"] == "list-scan"


def test_list_has_matches_name_and_slug():
    with patched_cb(snapshot="ZHC Alpha | zhc-beta-group | Gamma"):
        assert cb._list_has("s", "ZHC Alpha") is True
        assert cb._list_has("s", "Nope", slug="zhc-beta-group") is True
        assert cb._list_has("s", "Missing", slug="absent") is False


def test_course_search_box_is_optional_not_required():
    sels = cb.load_selectors()
    assert sels["course"]["list_page"]["search_box"].get("required") is False


# ═══════════════════════════════════════════════════════════════════════════
# (c) group identity = slug + white-label portal host
# ═══════════════════════════════════════════════════════════════════════════
def test_capture_group_identity_slug_and_portal_host():
    idjson = json.dumps({"url": "https://portal.example.com/communities/groups/zhc-x/home",
                         "host": "portal.example.com", "slug": "zhc-x"})
    with patched_cb(eval_fn=lambda s, js, timeout=20: idjson):
        ident = cb._capture_group_identity("s", {"slug": "zhc-x"})
    assert ident["slug"] == "zhc-x"
    assert ident["portal_host"] == "portal.example.com"
    assert ident["portal_url"] == "https://portal.example.com/communities/groups/zhc-x/home"


def test_capture_group_identity_app_host_is_not_portal():
    """When location.href is still the app host (no portal nav), portal_host is empty."""
    idjson = json.dumps({"url": "https://app.convertandflow.com/v2/location/L/x",
                         "host": "app.convertandflow.com", "slug": ""})
    with patched_cb(eval_fn=lambda s, js, timeout=20: idjson):
        ident = cb._capture_group_identity("s", {"slug": "fallback-slug"})
    assert ident["portal_host"] == ""
    assert ident["slug"] == "fallback-slug"       # falls back to the planned slug


# ═══════════════════════════════════════════════════════════════════════════
# (d) HONEST no-group-delete: cleanup reality + primitive selection
# ═══════════════════════════════════════════════════════════════════════════
def test_cleanup_reality_community_no_delete_course_delete():
    reality = cb.load_selectors()["_cleanup_reality"]
    assert reality["community_group"]["primitive"] == "inactivate"
    assert reality["community_group"]["has_ui_delete"] is False
    assert reality["community_group"]["has_api_delete"] is False
    assert reality["course"]["primitive"] == "delete"
    assert reality["course"]["has_api_delete"] is True


def test_deactivate_group_is_inactivate_not_delete_and_stops_on_capture_pending():
    """Community cleanup NEVER claims a delete: primitive=inactivate, deleted=False, and the
    capture-pending status toggle STOP is recorded as honest residue (Phase B locks it)."""
    with patched_cb():
        cl = cb._deactivate_group("s", cb.load_selectors(), {"slug": "zhc-x"},
                                  {"slug": "zhc-x", "portal_host": "p", "portal_url": "u"})
    assert cl["cleanup_primitive"] == "inactivate"
    assert cl["deleted"] is False
    assert "stop" in cl                       # capture-pending toggle → recorded, not faked


def test_course_delete_primitive_is_true_delete():
    """Course cleanup IS a real delete (courses are deletable, unlike groups). The
    Memberships rail is actionable so a fake `ab` is injected; the row-delete anchors are
    capture-pending → STOP recorded, but the primitive is 'delete' (not 'inactivate')."""
    with patched_cb(ab=_fake_ab_factory([])):
        cl = course._delete_course("s", cb.load_selectors(),
                                   {"course_name": "ZHC C", "slug": "zhc-c"})
    assert cl["cleanup_primitive"] == "delete"
    assert "stop" in cl                       # row-delete anchors capture-pending → Phase B


# ═══════════════════════════════════════════════════════════════════════════
# (e) render-check on the right URL — public anon vs private authenticated
# ═══════════════════════════════════════════════════════════════════════════
def test_verify_private_uses_authenticated_in_session():
    ident = {"slug": "zhc-x", "portal_host": "portal.example.com",
             "portal_url": "https://portal.example.com/communities/groups/zhc-x/home"}
    authjson = json.dumps({"ready": True, "has": True, "url": ident["portal_url"]})
    with patched_cb(snapshot="ZHC Founders", eval_fn=lambda s, js, timeout=20: authjson):
        vb = cb._verify_community("s", {"community_name": "ZHC Founders", "slug": "zhc-x",
                                        "privacy": "private"}, ident, "/tmp/x")
    assert vb["render_method"] == "authenticated_in_session"
    assert vb["http"] == 200 and vb["marker_in_rendered_dom"] is True
    assert vb["requires_auth"] is True
    assert vb["community_url"] == ident["portal_url"]      # derived member-visible URL


def test_verify_private_defers_when_not_confirmed():
    ident = {"slug": "zhc-x", "portal_host": "p", "portal_url": "u"}
    notfound = json.dumps({"ready": True, "has": False, "url": "u"})
    with patched_cb(snapshot="", eval_fn=lambda s, js, timeout=20: notfound):
        vb = cb._verify_community("s", {"community_name": "ZHC Founders", "slug": "zhc-x",
                                        "privacy": "private"}, ident, "/tmp/x")
    assert vb.get("http") != 200
    assert vb.get("status") == "deferred"                 # honest, not a fake pass


def test_verify_public_defers_without_portal_url():
    ident = {"slug": "zhc-x", "portal_host": "", "portal_url": ""}
    with patched_cb(snapshot="ZHC Founders"):
        vb = cb._verify_community("s", {"community_name": "ZHC Founders", "slug": "zhc-x",
                                        "privacy": "public"}, ident, "/tmp/x")
    assert vb["requires_auth"] is False
    assert vb.get("status") == "deferred"                 # no URL → deferred, never fabricated


def test_verify_public_uses_derived_portal_url():
    """A PUBLIC group with a portal URL runs an anonymous render_check on THAT url (fix e).
    ghl_verify is monkeypatched so the test is offline."""
    ident = {"slug": "zhc-x", "portal_host": "portal.example.com",
             "portal_url": "https://portal.example.com/communities/groups/zhc-x/home"}
    captured = {}
    fake_verify = type(sys)("ghl_verify")
    fake_verify.verify_page = lambda task, run_dir=None, live=False: (
        captured.update(task) or {"http": 200, "marker_in_rendered_dom": True, "render_errors": []})
    sys.modules["ghl_verify"] = fake_verify
    try:
        with patched_cb(snapshot="ZHC Founders"):
            vb = cb._verify_community("s", {"community_name": "ZHC Founders", "slug": "zhc-x",
                                            "privacy": "public"}, ident, "/tmp/x")
    finally:
        sys.modules.pop("ghl_verify", None)
    assert vb["render_method"] == "anonymous_render_check"
    assert captured.get("preview_url") == ident["portal_url"]
    assert vb["http"] == 200


# ═══════════════════════════════════════════════════════════════════════════
# guard: nothing was LOCKed — all in-area targets stay capture-pending (D8)
# ═══════════════════════════════════════════════════════════════════════════
def test_still_no_locked_inarea_targets():
    """Phase B (2026-07-10) LOCKed the in-area anchors from a LIVE create-then-clean run.
    Guard the LOCKed core + the documented still-pending set (a regression that un-locks or
    wrongly-locks trips this)."""
    sels = cb.load_selectors()
    must_be_locked = [
        "community.routes.communities_list", "community.list_page.create_group_button",
        "community.create_page.name_input", "community.create_page.create_confirm",
        "community.group_nav.add_channel_control", "community.group_nav.channel_create_confirm",
        "community.deactivate.status_dropdown", "community.deactivate.confirm",
        "course.routes.courses_list", "course.list_page.create_course_button",
        "course.list_page.create_source", "course.list_page.delete_confirm",
        "course.create_modal.name_input", "course.create_modal.create_confirm",
        "course.outline.add_content", "course.outline.add_module",
        "course.outline.module_create_confirm", "course.outline.add_lesson",
        "course.outline.lesson_create_confirm",
    ]
    for dotted in must_be_locked:
        assert cb._target(sels, dotted)["status"] == "locked", f"{dotted} should be LOCKed (Phase B)"
    for dotted in ("community.create_page.privacy_switch",
                   "course.create_modal.product_type",
                   "course.outline.lesson_body_editor"):
        assert cb._target(sels, dotted)["status"] == "capture-pending", f"{dotted} still pending"
