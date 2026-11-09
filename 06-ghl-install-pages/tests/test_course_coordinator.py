"""WF07 coordinator / router tests — the API-first course coordinator (doc 1 s8),
the D02 router split, plan validation and the aggregate delivery reducer.

MOCK-ONLY: an injected fake public adapter (WF06 seam), a fake media binder
(WF08 seam) and a fake association (WF09 seam). No network, no browser, no GHL
write of any kind.

Acceptance covered here:
  A08 (coordinator side) — the course shell/modules/lessons use public DTOs and
       no invented course draft/media fields; the build starts no browser.
  A09                   — duplicate display titles remain distinct with stable
       logical keys; a rerun does not duplicate objects.
  A10 (coordinator side) — required lesson content/media that is not actually
       bound cannot reach a delivered state.
  B01 (Skill 6 side)     — router object types, method-decision classes and the
       builder agree; no parallel client/router.
  IG-COURSE-02           — plan is validated before any write (duplicate keys,
       unknown parent, cycle, missing content, cross-location IDs, invalid
       visibility rejected; duplicate titles allowed).
  IG-COURSE-03           — modules are created parent-before-child and final
       sequencing is applied and read back.
  IG-COURSE-05           — a standalone course requires no group; a group
       association happens only when the plan requests it.
"""
import json
import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_course_builder as course  # noqa: E402
import ghl_course_delivery as delivery  # noqa: E402
import ghl_method_decision as method_decision  # noqa: E402
import ghl_object_router as router  # noqa: E402


# ── fake public adapter (WF06 seam) ──────────────────────────────────────────
class FakeCoursesAdapter:
    """Records every call so DTO shape can be asserted, and mints stable ids."""

    def __init__(self, list_lessons_reverse=False):
        self.calls = []
        self._n = 0
        self.courses = {}
        self.lessons = []
        self.list_lessons_reverse = list_lessons_reverse

    def _id(self, prefix):
        self._n += 1
        return f"{prefix}_{self._n}"

    def create_course(self, *, location_id, payload):
        self.calls.append(("create_course", payload))
        cid = self._id("course")
        self.courses[cid] = dict(payload)
        return {"id": cid}

    def get_course(self, *, location_id, course_id):
        return {"id": course_id} if course_id in self.courses else None

    def create_category(self, *, location_id, payload):
        self.calls.append(("create_category", payload))
        return {"id": self._id("cat")}

    def create_lesson(self, *, location_id, payload):
        self.calls.append(("create_lesson", payload))
        lid = self._id("les")
        self.lessons.append(lid)
        return {"id": lid}

    def list_lessons(self, *, location_id, course_id):
        return [{"id": i} for i in (
            list(reversed(self.lessons)) if self.list_lessons_reverse else self.lessons)]

    def sequence(self, *, location_id, course_id, ordering):
        self.calls.append(("sequence", ordering))
        return {"ok": True}

    def kinds(self):
        return [c[0] for c in self.calls]


def _task(**over):
    base = {
        "course_name": "Launch 101",
        "location_id": "LOC_SYNTH",
        "modules": [
            {"module_key": "welcome", "title": "Welcome", "position": 1, "lessons": [
                {"lesson_key": "intro-a", "title": "Introduction", "position": 1,
                 "body": "Welcome aboard."},
                {"lesson_key": "intro-b", "title": "Introduction", "position": 2,
                 "body": "A second page with the same title."},
            ]},
            {"module_key": "build", "parent_module_key": "welcome", "title": "Build",
             "position": 2, "lessons": [
                 {"lesson_key": "first", "title": "First page", "position": 1,
                  "body": "Build your first page."}]},
        ],
    }
    base.update(over)
    return base


def _build(tmp_path, adapter, **kw):
    return course.build_course(_task(), str(tmp_path), dry_run=False,
                               adapter=adapter, **kw)


# ── A08: public DTOs, no browser ─────────────────────────────────────────────
def test_a08_outline_build_uses_public_dtos_and_starts_no_browser(tmp_path):
    adapter = FakeCoursesAdapter()
    res = _build(tmp_path, adapter)

    assert res["ok"], res
    assert res["mode"] == "api"
    assert res["browser_started"] is False
    assert "create_course" in adapter.kinds()

    created_course = next(p for k, p in adapter.calls if k == "create_course")
    # The create DTO must NOT carry identity/source/processing fields (s8.3).
    for forbidden in ("locationId", "userId", "id", "originId", "source", "processing"):
        assert forbidden not in created_course, f"invented field {forbidden!r} in {created_course}"
    assert created_course["title"] == "ZHC Launch 101"

    for kind in ("create_category", "create_lesson"):
        for k, payload in adapter.calls:
            if k != kind:
                continue
            for forbidden in ("locationId", "userId", "productId", "originId"):
                assert forbidden not in payload, f"{kind} invented {forbidden!r}"
    lesson_payloads = [p for k, p in adapter.calls if k == "create_lesson"]
    assert all("categoryId" in p for p in lesson_payloads)

    apf = json.loads((tmp_path / "routing" / "course-api-preflight.json").read_text())
    assert apf["browser_required"] is False and apf["pass"] is True


def test_a08_build_course_still_defaults_to_browser_without_an_adapter(tmp_path):
    """Backwards compatibility: no adapter supplied -> the managed-browser path."""
    res = course.build_course(_task(), str(tmp_path), dry_run=True)
    assert res["execution_mode"] == "browser"
    assert res["browser_required"] is True


# ── A09: identity, not titles; resume does not duplicate ─────────────────────
def test_a09_same_title_lessons_remain_distinct(tmp_path):
    adapter = FakeCoursesAdapter()
    res = _build(tmp_path, adapter)
    assert res["ok"], res
    lesson_payloads = [p for k, p in adapter.calls if k == "create_lesson"]
    assert len(lesson_payloads) == 3, "all three lessons (two titled 'Introduction') must exist"
    assert [p["title"] for p in lesson_payloads] == ["Introduction", "Introduction", "First page"]
    keys = sorted(l["logical_key"] for l in res["delivery"]["lessons"])
    assert keys == ["build/first", "welcome/intro-a", "welcome/intro-b"]


def test_a09_rerun_reconciles_by_recorded_id_and_creates_nothing(tmp_path):
    adapter = FakeCoursesAdapter()
    first = _build(tmp_path, adapter)
    assert first["ok"], first
    created_before = adapter.kinds().count("create_lesson")

    adapter2 = FakeCoursesAdapter()
    second = _build(tmp_path, adapter2)
    assert second["ok"], second
    assert adapter2.kinds().count("create_lesson") == 0, \
        "resume must reconcile by the recorded ID manifest, never recreate"


def test_a09_resume_with_phase_state_skips_completed_lessons(tmp_path, monkeypatch):
    """A per-lesson checkpoint is what makes a long course resumable: the lessons
    whose phases already completed are NOT re-created, the rest are."""
    monkeypatch.setenv("GHL_RUN_STATE_ROOT", str(tmp_path / "state"))
    import ghl_run_state as rs
    specs = [rs.PhaseSpec("plan", resumable=False),
             rs.PhaseSpec("preflight", resumable=False),
             rs.PhaseSpec("click_list", resumable=False),
             rs.PhaseSpec("api_course_shell"),
             rs.PhaseSpec("module:welcome"),
             rs.PhaseSpec("module:build"),
             rs.PhaseSpec("lesson:welcome/intro-a"),
             rs.PhaseSpec("lesson:welcome/intro-b"),
             rs.PhaseSpec("lesson:build/first")]
    st = rs.RunState.start("ghl_course_builder", specs,
                           state_root=str(tmp_path / "state"),
                           evidence_root=str(tmp_path))
    for p in ("api_course_shell", "module:welcome", "module:build",
              "lesson:welcome/intro-a"):
        rs.run_phase(st, p, lambda: {"id": "prior-id"})
    st.save()

    adapter = FakeCoursesAdapter()
    res = course.build_course(_task(), str(tmp_path), dry_run=False,
                              adapter=adapter, state=st)
    assert res["mode"] == "api"
    # The already-completed shell/module/lesson were NOT re-created.
    assert "create_course" not in adapter.kinds()
    assert adapter.kinds().count("create_category") == 0
    assert adapter.kinds().count("create_lesson") == 2, \
        "only the two unfinished lessons may be created on resume"


# ── A10: required content must actually be bound ─────────────────────────────
def test_a10_required_media_unbound_cannot_be_delivered(tmp_path):
    task = _task()
    task["modules"][0]["lessons"][0]["asset_refs"] = ["assets/welcome-video.json"]
    res = course.build_course(task, str(tmp_path), dry_run=False,
                              adapter=FakeCoursesAdapter(),
                              media_binder=lambda **kw: {
                                  "asset_persisted": True,
                                  "native_content_ready": False,
                                  "lesson_association_verified": False,
                                  "learner_render_verified": False})
    assert res["ok"] is False
    assert res["delivery"]["state"] == delivery.DELIVERY_INCOMPLETE
    assert any("association-verified" in b for b in res["delivery"]["blocking"])


def test_a10_no_media_binder_is_reported_not_faked(tmp_path):
    task = _task()
    task["modules"][0]["lessons"][0]["asset_refs"] = ["assets/welcome-video.json"]
    res = course.build_course(task, str(tmp_path), dry_run=False,
                              adapter=FakeCoursesAdapter())
    assert res["ok"] is False
    assert any("no WF08 media binder" in w for w in res["warnings"])


# ── IG-COURSE-02: plan validation happens before any write ───────────────────
@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["modules"].append(
        {"module_key": "welcome", "title": "Dup", "lessons": []}), "duplicate module_key"),
    (lambda p: p["modules"][0]["lessons"].append(
        {"lesson_key": "intro-a", "title": "Dup", "body": "x"}), "duplicate lesson_key"),
    (lambda p: p["modules"][1].update(parent_module_key="ghost"), "unknown parent"),
    (lambda p: p["modules"][0].update(parent_module_key="build"), None),
    (lambda p: p["modules"][0]["lessons"].append(
        {"lesson_key": "noc", "title": "No content", "required_for_delivery": True}), "content reference"),
    (lambda p: p["modules"][0].update(visibility="hidden"), "visibility"),
    (lambda p: p["modules"][0].update(
        existing_category_id={"id": "c1", "location_id": "OTHER"}), "cross-location"),
])
def test_ig_course_02_plan_validation_rejects_before_any_write(mutate, needle):
    plan = course.plan_course(_task())
    mutate(plan)
    errors = delivery.validate_plan(plan)
    assert errors, "invalid plan must be rejected"
    if needle:
        assert any(needle in e for e in errors), errors


def test_ig_course_02_duplicate_display_titles_are_allowed():
    plan = course.plan_course(_task())
    titles = [l["title"] for l in plan["modules"][0]["lessons"]]
    assert titles.count("Introduction") == 2
    assert delivery.validate_plan(plan) == []


# ── IG-COURSE-03: parent-before-child + deterministic sequencing readback ────
def test_ig_course_03_parent_created_before_child(tmp_path):
    adapter = FakeCoursesAdapter()
    res = _build(tmp_path, adapter)
    assert res["ok"], res
    cats = [p for k, p in adapter.calls if k == "create_category"]
    assert "parentCategory" not in cats[0], "the root module has no parent"
    assert cats[1]["parentCategory"], "the child module must carry the resolved parent id"


def test_ig_course_03_sequencing_applied_and_read_back(tmp_path):
    adapter = FakeCoursesAdapter()
    res = _build(tmp_path, adapter)
    seq = next(o for k, o in adapter.calls if k == "sequence")
    lesson_ids = [o["id"] for o in seq if o["object_type"] == "lesson"]
    assert lesson_ids == adapter.lessons, "final order must follow the plan, not creation luck"
    assert res["sequencing"]["applied"] is True
    assert res["sequencing"]["readback_present"] is True
    assert res["sequencing"]["order_matches"] is True


def test_ig_course_03_readback_mismatch_is_reported_not_hidden(tmp_path):
    adapter = FakeCoursesAdapter(list_lessons_reverse=True)
    res = _build(tmp_path, adapter)
    assert res["sequencing"]["readback_present"] is True
    assert res["sequencing"]["order_matches"] is False


# ── IG-COURSE-05: standalone course needs no group; association on request ──
def test_ig_course_05_standalone_course_needs_no_group(tmp_path):
    called = {"n": 0}

    def _assoc(**kw):
        called["n"] += 1
        return {"state": "verified"}

    res = _build(tmp_path, FakeCoursesAdapter(), association=_assoc)
    assert res["ok"], res
    assert called["n"] == 0, "a standalone course must not create a group association"
    assert res["delivery"]["community"]["state"] == "not_requested"


def test_ig_course_05_association_runs_only_when_requested(tmp_path):
    task = _task(community={"required": True, "group_ref": "community/plan.json"})
    calls = {"n": 0}

    def _assoc(**kw):
        calls["n"] += 1
        return {"state": "verified", "group_id": "grp_1", "access_policy": "all_members"}

    res = course.build_course(task, str(tmp_path), dry_run=False,
                              adapter=FakeCoursesAdapter(), association=_assoc)
    assert res["ok"], res
    assert calls["n"] == 1
    assert res["delivery"]["community"]["state"] == "verified"


def test_ig_course_05_requested_association_missing_blocks_delivery(tmp_path):
    task = _task(community={"required": True})
    res = course.build_course(task, str(tmp_path), dry_run=False,
                              adapter=FakeCoursesAdapter())
    assert res["ok"] is False
    assert res["delivery"]["community"]["required"] is True


# ── aggregate delivery receipt ───────────────────────────────────────────────
def test_delivery_receipt_written_and_reduced_from_artifacts(tmp_path):
    res = _build(tmp_path, FakeCoursesAdapter())
    path = tmp_path / "routing" / "course-delivery-receipt.json"
    assert path.is_file()
    receipt = json.loads(path.read_text())
    assert receipt["schema_version"] == delivery.RECEIPT_SCHEMA
    assert receipt["state"] == delivery.DELIVERY_DELIVERED
    assert receipt["counts"] == {"modules_expected": 2, "modules_verified": 2,
                                 "lessons_expected": 3, "lessons_verified": 3}
    # four proof fields exist separately — an asset URL proves only persistence
    assert set(receipt["content"]) == {
        "asset_persisted", "native_content_ready",
        "lesson_association_verified", "learner_render_verified"}


# ── B01 (Skill 6 side): router / method-decision / builder agree ─────────────
def test_b01_router_and_method_decision_cover_every_builder_object(tmp_path):
    adapter = FakeCoursesAdapter()
    res = _build(tmp_path, adapter)
    for object_type in ("course", "course_module", "course_lesson"):
        assert router.route(object_type).rails, f"router has no route for {object_type}"
        assert object_type in method_decision.OBJECT_TYPE_OPERATION_CLASS, \
            f"method-decision has no operation class for {object_type}"
        # The router may only NAME operation rows the central registry contains;
        # rows that do not exist yet are carried as pending_registry (CR to WF00).
        assert router.pending_registry_operations(object_type), \
            f"{object_type} names no public operation rows to request from WF00"
    # The builder's emitted receipt object types are exactly the routed ones.
    emitted_types = {e.get("object_type") for e in
                     __import__("ghl_receipts").list_receipts(str(tmp_path))}
    assert {"course", "course_module", "course_lesson"} <= emitted_types
    assert res["ok"]



def test_b01_course_and_community_do_not_share_public_routes():
    for obj in ("community", "community_group", "channel"):
        routes = router.public_operation_route(obj)
        assert routes["routed"] == () and routes["declared"] == ()


# ── central construction registration (dispatcher) ───────────────────────────
def test_dispatcher_registers_course_and_community_builders():
    import v2_dispatcher as disp
    assert disp._resolve_builder_for_task({"job_type": "course"}) is disp._course_builder
    assert disp._resolve_builder_for_task({"job_type": "community"}) is disp._community_builder
    assert disp._resolve_builder_for_task({"job_type": "channel"}) is disp._community_builder
    assert disp._resolve_builder_for_task({"job_type": "nonsense"}) is None


def test_dispatcher_route_hook_registration_overrides_and_is_auditable():
    import v2_dispatcher as disp
    sentinel = lambda task, root: {"ok": True}  # noqa: E731
    out = disp.register_construction_route(["widget"], sentinel, owner="WF31")
    try:
        assert out["registered"] == ["widget"]
        assert disp._resolve_builder_for_task({"job_type": "widget"}) is sentinel
        assert disp.CONSTRUCTION_ROUTE_HOOKS["widget"]["owner"] == "WF31"
    finally:
        disp.CONSTRUCTION_ROUTE_HOOKS.pop("widget", None)


# ── no-network selftests ─────────────────────────────────────────────────────
def test_course_delivery_selftest_exit_zero():
    import subprocess
    cp = subprocess.run([sys.executable, os.path.join(TOOLS, "ghl_course_delivery.py"),
                         "--selftest"], capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr
