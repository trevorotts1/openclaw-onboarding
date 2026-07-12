"""Offline tests for the Skill-6 SURVEY-builder hardening (branch
`skill6-survey-builder-hardening`, builder v1.4.0) — the 5 Fable-plan items:

  1. NAV FIX — `_p2_navigate_create` router.push's to `survey-builder/main` and
     creates via the native "Add survey" click (ghl_ab_executor resolver), NEVER
     the dead left-rail "Sites" item; captures the survey id from the iframe src.
  2. BUILD-FROM-MAIN GUARD — preflight `P4:builder_convergence_capable` HARD-STOPs a
     converge_slide / owner_slide build on a stale (pre-main) checkout.
  3. CROSS-ORIGIN-IFRAME DRAG PLAYBOOK — reusable ghl_iframe_dragdrop helper (tab
     click + coordinate drag ladder) + the TECHNIQUES doc (existence asserted).
  4. SMOKE-TEST-FIRST + CAPTURE-GATED REST FALLBACK — `_p2_smoke_test_drag` proves a
     single tile-drag via the iframe-aware snapshot delta; the rest lane can NEVER
     blind-POST (ghl_survey_rest capture gate + preflight `P5:rest_write_proven`).
  5. VERSION — builder v1.4.0.

No network, no browser: every browser touch is an injected fake.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import ghl_survey_builder as sb          # noqa: E402
import ghl_iframe_dragdrop as idd        # noqa: E402
import ghl_survey_rest as srest          # noqa: E402


# ───────────────────────── fakes ─────────────────────────

def _cp(rc=0, out="✓ Done", err=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


class Recorder:
    """Records _run_cmd argv + _eval JS + _wait/_click targets and serves canned
    responses keyed on JS/argv content."""

    def __init__(self, *, find_fails=False, survey_id="ExAPmAV3Llo0tREenfJy",
                 scan='{"named":false,"shell":false}'):
        self.run_calls = []
        self.eval_js = []
        self.waits = []
        self.clicks = []
        self.find_fails = find_fails
        self.survey_id = survey_id
        self.scan = scan

    def run_cmd(self, session, *args, timeout=30, stdin=None):
        self.run_calls.append(tuple(args))
        if args and args[0] == "find" and self.find_fails:
            return _cp(rc=1, out="", err="Element not found")
        return _cp()

    def eval(self, session, js, timeout=15):
        self.eval_js.append(js)
        if "onLogin" in js:
            return "app:/v2/location/LOC/survey-builder/main"
        if "$router.push" in js:
            return "nav:/v2/location/LOC/survey-builder/main"
        if '"named"' in js and '"shell"' in js:
            return self.scan
        if "survey-builder-v2" in js:
            return self.survey_id
        if ".click()" in js and "Add survey" in js:
            return "CLICKED:Add survey"
        if "innerText.trim() === 'Add survey'" in js:
            return "clicked"
        return ""

    def wait(self, session, text, timeout=25):
        self.waits.append(text)

    def click(self, session, target, timeout=15):
        self.clicks.append(target)

    def snapshot(self, session):
        return ""


@pytest.fixture
def patched(monkeypatch):
    rec = Recorder()

    def _install(r):
        monkeypatch.setattr(sb, "_run_cmd", r.run_cmd)
        monkeypatch.setattr(sb, "_eval", r.eval)
        monkeypatch.setattr(sb, "_wait", r.wait)
        monkeypatch.setattr(sb, "_click", r.click)
        monkeypatch.setattr(sb, "_snapshot", r.snapshot)
        monkeypatch.setattr(sb, "_screenshot", lambda *a, **k: None)
    _install(rec)
    return rec, _install, monkeypatch


# ═══════════════ 1. NAV FIX ═══════════════

def test_nav_fix_router_push_to_survey_list_not_sites(patched):
    rec, _install, _mp = patched
    sid = sb._p2_navigate_create("s", "LOC", "/tmp/ev", [0], survey_name="Fresh Survey")
    router_js = [j for j in rec.eval_js if "$router.push" in j]
    assert router_js, "router.push was never emitted"
    assert any("survey-builder/main" in j for j in router_js), \
        "nav fix must router.push to /survey-builder/main"
    # the dead left-rail 'Sites' click must NEVER happen (browser lane nav fix)
    assert "Sites" not in rec.clicks
    all_run_args = [arg for call in rec.run_calls for arg in call]
    assert not any("Sites" in arg for arg in all_run_args)
    # survey id captured + shape-validated
    assert sid == "ExAPmAV3Llo0tREenfJy"
    assert "Add survey" in rec.waits and "Slide 1" in rec.waits


def test_nav_fix_native_add_survey_click_via_executor(patched):
    """When the find-ladder misses, the survey is created by the native `.click()`
    resolver (ghl_ab_executor) — the REUSED cross-origin click path."""
    rec, install, mp = patched
    rec2 = Recorder(find_fails=True)          # force find→native fallback
    install(rec2)
    sid = sb._p2_navigate_create("s", "LOC", "/tmp/ev", [0], survey_name="Fresh")
    assert sid == "ExAPmAV3Llo0tREenfJy"
    # a native .click() eval for 'Add survey' fired (executor native OR explicit JS)
    assert any(".click()" in j and "Add survey" in j for j in rec2.eval_js) \
        or any("innerText.trim() === 'Add survey'" in j for j in rec2.eval_js)


def test_nav_fix_reuses_existing_named_survey(patched):
    """An existing row titled exactly survey_name is opened (edit-in-place), not
    duplicated — no 'Add survey' create fires."""
    rec, install, mp = patched
    rec2 = Recorder(scan='{"named":true,"shell":false}')
    install(rec2)
    sb._p2_navigate_create("s", "LOC", "/tmp/ev", [0], survey_name="Existing One")
    # no create: neither the native innerText 'Add survey' nor a find role 'Add survey'
    assert not any("innerText.trim() === 'Add survey'" in j for j in rec2.eval_js)


def test_survey_id_shape_gate_rejects_junk(patched):
    rec, install, mp = patched
    rec2 = Recorder(survey_id="../../etc/passwd")
    install(rec2)
    sid = sb._p2_navigate_create("s", "LOC", "/tmp/ev", [0], survey_name="X")
    assert sid == "", "a non-id-shaped capture must be rejected to ''"


# ═══════════════ 2. BUILD-FROM-MAIN GUARD ═══════════════

def test_convergence_guard_pure():
    assert sb._assert_convergence_capable({"survey_name": "x"})[0] is True
    conv = {"converge_slide": "Shared"}
    assert sb._assert_convergence_capable(conv, version="v1.4.0")[0] is True
    assert sb._assert_convergence_capable(conv, version="v1.1.0")[0] is False
    assert sb._assert_convergence_capable(conv, has_primitive=False)[0] is False
    owner = {"conditional_logic": [{"if_field": "Q", "if_value": "A",
                                    "then_slide": "S", "owner_slide": "S0"}]}
    assert sb._assert_convergence_capable(owner, version="v1.1.0")[0] is False


def test_preflight_convergence_guard_passes_on_this_build(tmp_path):
    task = {"survey_name": "C", "title": "C", "location_id": "LOC",
            "field_creation": "browser",
            "survey_fields": [
                {"type": "radio", "label": "Style", "key": "style",
                 "options": ["A", "B"], "required": True, "slide_name": "Pick"},
                {"type": "multiline", "label": "A1", "key": "a1",
                 "required": True, "slide_name": "BranchA"},
                {"type": "multiline", "label": "B1", "key": "b1",
                 "required": True, "slide_name": "BranchB"},
                {"type": "multiline", "label": "S1", "key": "s1",
                 "required": True, "slide_name": "Shared"}],
            "slides": [{"name": "Pick", "fields": ["style"]},
                       {"name": "BranchA", "fields": ["a1"]},
                       {"name": "BranchB", "fields": ["b1"]},
                       {"name": "Shared", "fields": ["s1"]}],
            "conditional_logic": [
                {"if_field": "style", "if_value": "A", "then_slide": "BranchA"},
                {"if_field": "style", "if_value": "B", "then_slide": "BranchB"}],
            "converge_slide": "Shared"}
    pf = sb._run_preflight(task, str(tmp_path))
    assert any(c["check"] == "P4:builder_convergence_capable" and c["pass"]
               for c in pf["checks"])


def test_semver_parse_ordering():
    assert sb._parse_semver("v19.20.0") > sb._parse_semver("v19.19.0")
    assert sb._parse_semver("v1.4.0") > sb._parse_semver("v1.3.0")
    assert sb._parse_semver("v1.3.0") == (1, 3, 0)


# ═══════════════ 3. CROSS-ORIGIN-IFRAME DRAG PLAYBOOK ═══════════════

def test_iframe_helper_selftest_offline():
    assert idd._selftest() == 0


def test_iframe_tab_click_and_coord_drag_js_shape():
    tj = idd.tab_click_js("Add Object Fields")
    assert ".click()" in tj and "Add Object Fields" in tj and "NOTFOUND" in tj
    cj = idd.coord_drag_js("Multi Line", "Slide 2")
    for n in ("pointerdown", "pointerup", "before", "after", "DataTransfer"):
        assert n in cj


def test_iframe_walled_drag_is_not_a_false_pass():
    def fake_ev(session, js, timeout=15):
        return '{"ok":false,"before":0,"after":0}' if "pointerdown" in js else ""
    def fake_ab(session, *a, timeout=15):
        return _cp()
    dd = idd.IframeDragDrop(ab=fake_ab, ev=fake_ev)
    assert dd.drag("s", "Multi Line", "Slide 2", verify_expr="x")["ok"] is False


def test_techniques_doc_present():
    doc = os.path.join(ROOT, "TECHNIQUES-cross-origin-iframe-dragdrop.md")
    assert os.path.exists(doc), "the generalized playbook doc must ship with the skill"
    txt = open(doc, encoding="utf-8").read()
    assert "agent-browser" in txt and "capture-save" in txt.lower()


# ═══════════════ 4. SMOKE-TEST-FIRST + CAPTURE-GATED REST FALLBACK ═══════════════

class _SnapSeq:
    """_snapshot fake returning a programmed sequence of snapshot strings."""
    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0
    def __call__(self, session):
        v = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return v


def test_smoke_drag_ok_when_canvas_gains_the_tile(patched):
    rec, install, mp = patched
    # snapshots: before=1 occurrence, mid/after=2 → tile landed on the canvas
    mp.setattr(sb, "_snapshot", _SnapSeq(["Multi Line",
                                          "Multi Line ... Multi Line",
                                          "Multi Line ... Multi Line"]))
    res = sb._p2_smoke_test_drag("s", "/tmp/ev", [0])
    assert res["ok"] is True
    assert res["before"] == 1 and res["after"] == 2


def test_smoke_drag_walls_when_nothing_lands(patched):
    rec, install, mp = patched
    mp.setattr(sb, "_snapshot", _SnapSeq(["Multi Line"]))   # count never grows
    res = sb._p2_smoke_test_drag("s", "/tmp/ev", [0])
    assert res["ok"] is False


def test_rest_lane_selftest_offline():
    assert srest._selftest() == 0


def test_rest_save_route_never_blind_posts():
    # a captured POST /surveys derives origin/path/verb…
    cap = {"method": "POST",
           "url": "https://backend.leadconnectorhq.com/surveys/abc?locationId=L"}
    origin, path, verb = srest.survey_save_route(cap)
    assert origin == "https://backend.leadconnectorhq.com" and verb == "POST"
    # …but an absent/guessed route HARD-STOPS (anti-blind-POST)
    for bad in ({}, {"method": "POST"}, {"url": "https://x/other", "method": "POST"}):
        with pytest.raises(srest.CaptureRequired):
            srest.survey_save_route(bad)


def test_rest_lane_requires_capture_receipt(tmp_path):
    os.makedirs(tmp_path / "routing")
    # no receipt at all → CaptureRequired before any write
    with pytest.raises(srest.CaptureRequired):
        sb._rest_lane_build("s", "abc", {"form_data": {"slides": []},
                                         "id_token": "x"}, str(tmp_path),
                            sb.RateGovernor())


def test_rest_lane_requires_composed_form_data(tmp_path):
    routing = tmp_path / "routing"
    os.makedirs(routing)
    (routing / srest.CAPTURE_RECEIPT_NAME).write_text(json.dumps(
        {"method": "POST", "url": "https://backend.leadconnectorhq.com/surveys/abc"}))
    # receipt present but NO composed formData → refuse (don't write an empty survey)
    with pytest.raises(RuntimeError):
        sb._rest_lane_build("s", "abc", {"id_token": "x"}, str(tmp_path),
                            sb.RateGovernor())


def test_preflight_rest_gate(tmp_path):
    pf_rest = sb._run_preflight(
        {"survey_name": "R", "title": "R", "location_id": "LOC",
         "field_creation": "browser", "build_method": "rest"}, str(tmp_path))
    assert not pf_rest["pass"]
    assert any(c["check"] == "P5:rest_write_proven" and not c["pass"]
               for c in pf_rest["checks"])


def test_preflight_rest_gate_passes_with_valid_receipt(tmp_path):
    routing = tmp_path / "routing"
    os.makedirs(routing)
    (routing / srest.CAPTURE_RECEIPT_NAME).write_text(json.dumps(
        {"method": "POST", "url": "https://backend.leadconnectorhq.com/surveys/abc"}))
    pf = sb._run_preflight(
        {"survey_name": "R", "title": "R", "location_id": "LOC",
         "field_creation": "browser", "build_method": "rest"}, str(tmp_path))
    assert any(c["check"] == "P5:rest_write_proven" and c["pass"] for c in pf["checks"])


# ═══════════════ 5. VERSION ═══════════════

def test_builder_version_is_1_5_1():
    # v1.5.0 lands U6 (survey-URL fetch-200 receipt, no screenshot fallback),
    # U8 (phase-granular --resume), and U10 (uniform RUN REPORT).
    # v1.5.1 (P3-04 c4): iframe-drag/rename STOPs raise the classified
    # IframeDragStop (CC board-note taxonomy) instead of a bare RuntimeError.
    assert sb.SURVEY_BUILDER_VERSION == "v1.5.1"


def test_skill_version_lockstep():
    sv = open(os.path.join(ROOT, "skill-version.txt"), encoding="utf-8").read().strip()
    assert sv.startswith("v19."), f"unexpected skill version {sv!r}"
    # must be > the current origin/main baseline (v19.19.0)
    assert sb._parse_semver(sv) > sb._parse_semver("v19.19.0")
