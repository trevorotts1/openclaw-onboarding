"""WF08 — native course content / asset binding seam tests (offline).

Covers the acceptance this lane owns:
  A10   required lesson content/media is actually BOUND, not just listed in a plan
  A11   import processing is never reported as a completed course
  IG-COURSE-03  media matches the approved plan (asset validation + role/type)
  IG-COURSE-06  learner navigation/content/media at FIXTURE level only —
                live is NOT RUN in this lane (no live canary here)

No network, no browser, no GHL writes. The public course adapter and the
managed-browser actions are fakes injected through the frozen WF08-CP01 seam.
"""
import hashlib
import json
import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_course_media_binding as binding  # noqa: E402
import ghl_media  # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 24
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _manifest(**over):
    m = {
        "schema_version": "1.0.0",
        "asset_key": "launch101:welcome:intro:video",
        "course_key": "launch-101",
        "module_key": "welcome",
        "lesson_key": "intro",
        "role": "lesson_video",
        "provider": "kie",
        "model_id": "resolved-existing-model",
        "provider_task_id": "task_real_1",
        "generation_state": "completed",
        "local_path": "",
        "sha256": "a" * 64,
        "mime_type": "video/mp4",
        "byte_size": 12,
        "duration_seconds": 42.5,
        "durable_url": "https://storage.example/asset.mp4",
        "storage_access": "approved_for_destination",
        "qc": {"state": "passed", "receipt_ref": "QC-RECEIPT-1"},
        "ghl_binding": {"state": "not_started", "content_id": None, "lesson_id": None},
    }
    m.update(over)
    return m


class FakeCourseAdapter:
    """WF06 public course adapter fake (frozen WF08-CP01 method names)."""

    def __init__(self, readback=None, import_response=None):
        self.calls = []
        self._readback = readback or {}
        self._import = import_response or {}

    def attach_lesson_content(self, location_id, lesson_id, content_id, content_type):
        self.calls.append(("attach", location_id, lesson_id, content_id, content_type))
        return {"ok": True}

    def read_lesson(self, location_id, lesson_id):
        self.calls.append(("read", location_id, lesson_id))
        return self._readback

    def submit_course_import(self, location_id, payload):
        self.calls.append(("import", location_id, payload))
        return self._import


class FakeResponse:
    def __init__(self, code, body):
        self._code = code
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def getcode(self):
        return self._code

    def read(self):
        return self._body


# ── A10: the four proofs are separate and readback-earned ────────────────────
def test_a10_asset_persisted_does_not_imply_native_content(tmp_path):
    path = _write(tmp_path, "v.mp4", MP4_BYTES)
    sha = hashlib.sha256(MP4_BYTES).hexdigest()
    asset = binding.validate_asset_manifest(
        _manifest(local_path=path, sha256=sha, byte_size=len(MP4_BYTES))
    )
    proof = binding.empty_proof()
    binding.note_asset_persisted(proof, asset)
    assert proof["asset_persisted"] is True
    # A persisted file proves NOTHING about native content or association.
    assert proof["native_content_ready"] is False
    assert proof["lesson_association_verified"] is False
    assert proof["learner_render_verified"] is False
    assert binding.binding_complete(proof) is False


def test_a10_a_durable_url_alone_is_never_binding_complete():
    asset = binding.validate_asset_manifest(_manifest(durable_url="https://x/y.mp4"))
    proof = binding.empty_proof()
    binding.note_asset_persisted(proof, asset)
    assert binding.binding_complete(proof) is False


def test_a10_path_a_attaches_then_reads_association_back():
    adapter = FakeCourseAdapter(readback={"lesson": {"contentId": "cnt_9", "contentStatus": "ready"}})
    asset = binding.validate_asset_manifest(_manifest())
    res = binding.attach_existing_native_content(
        adapter, location_id="loc1", course_id="crs1", lesson_id="les1",
        content_id="cnt_9", content_type="video", asset=asset,
    )
    assert [c[0] for c in adapter.calls] == ["attach", "read"]
    assert res["proof"]["native_content_ready"] is True
    assert res["proof"]["lesson_association_verified"] is True
    # An attach + read on a lesson never proves a learner render.
    assert res["proof"]["learner_render_verified"] is False
    assert binding.binding_complete(res["proof"]) is False


def test_a10_path_a_mismatched_readback_is_not_verified():
    adapter = FakeCourseAdapter(readback={"lesson": {"contentId": "cnt_OTHER"}})
    res = binding.attach_existing_native_content(
        adapter, location_id="loc1", course_id="crs1", lesson_id="les1",
        content_id="cnt_9", content_type="video",
    )
    assert res["proof"]["lesson_association_verified"] is False
    assert res["proof"]["native_content_ready"] is False


def test_a10_path_a_refuses_cross_location_content():
    with pytest.raises(binding.BindingRefused) as exc:
        binding.select_binding_path(
            asset=_manifest(),
            native_content={"content_id": "cnt", "content_type": "video", "same_location": False},
        )
    assert "same-location" in str(exc.value)


def test_a10_learner_render_requires_learner_context():
    proof = binding.empty_proof()
    with pytest.raises(binding.BindingRefused):
        binding.note_learner_render_verified(proof, context="admin_preview", marker_in_dom=True)
    binding.note_learner_render_verified(proof, context="learner", marker_in_dom=True,
                                         evidence="learner portal DOM")
    assert proof["learner_render_verified"] is True


# ── A11: import processing is not a completed course ────────────────────────
def test_a11_import_processing_never_reports_complete():
    adapter = FakeCourseAdapter(import_response={"processing": True, "processingId": "imp_1"})
    res = binding.submit_course_import(adapter, location_id="loc1",
                                       payload={"course": {"title": "Launch 101"}})
    assert res["state"] == "processing"
    assert res["complete"] is False
    assert binding.import_is_complete(res["state"]) is False
    assert binding.import_is_complete("processing") is False
    assert binding.import_is_complete("content_verified") is True


def test_a11_import_lifecycle_refuses_skipping_completion():
    state = "planned"
    for event in ("submitted", "processing", "reconciled", "content_verified"):
        state = binding.import_lifecycle_step(state, event)
    assert state == "content_verified"
    # processing -> content_verified is illegal: reconcile must happen first.
    with pytest.raises(binding.BindingRefused):
        binding.import_lifecycle_step("processing", "content_verified")


def test_a11_bind_asset_path_b_returns_unverified_proof():
    adapter = FakeCourseAdapter(import_response={"processing": True, "processingId": "imp_2"})
    res = binding.bind_asset(
        _manifest(), client=adapter, location_id="loc1", course_id="crs1", lesson_id="les1",
        import_supported=True, course_is_new=True,
        import_payload={"course": {"title": "ZHC Launch 101"}},
    )
    assert res["path"] == binding.PATH_B
    assert res["complete"] is False
    assert res["proof"]["lesson_association_verified"] is False


# ── IG-COURSE-03: media matches the approved plan ───────────────────────────
def test_ig_course_03_manifest_validation_rejects_bad_sha_and_role():
    with pytest.raises(binding.AssetValidationError):
        binding.validate_asset_manifest(_manifest(sha256="not-a-hash"))
    with pytest.raises(binding.AssetValidationError):
        binding.validate_asset_manifest(_manifest(role="lesson_video", mime_type="application/pdf"))
    with pytest.raises(binding.AssetValidationError):
        binding.validate_asset_manifest(_manifest(role="lesson_image", mime_type="video/mp4"))


def test_ig_course_03_public_storage_is_refused_for_a_paid_course():
    with pytest.raises(binding.AssetValidationError) as exc:
        binding.validate_asset_manifest(_manifest(storage_access="public"))
    assert "publicly discoverable" in str(exc.value)
    with pytest.raises(binding.AssetValidationError):
        binding.validate_asset_manifest(_manifest(storage_access=""))


def test_ig_course_03_local_bytes_must_match_the_manifest(tmp_path):
    path = _write(tmp_path, "v.mp4", MP4_BYTES)
    good_sha = hashlib.sha256(MP4_BYTES).hexdigest()
    ok = binding.validate_asset_manifest(
        _manifest(local_path=path, sha256=good_sha, byte_size=len(MP4_BYTES))
    )
    assert ok["local_inspection"]["magic_verified"] is True
    with pytest.raises(binding.AssetValidationError):
        binding.validate_asset_manifest(
            _manifest(local_path=path, sha256="c" * 64, byte_size=len(MP4_BYTES))
        )


def test_ig_course_03_selector_is_deterministic_and_refuses_mixed_import():
    a = binding.select_binding_path(
        asset=_manifest(),
        native_content={"content_id": "cnt_1", "content_type": "video", "same_location": True},
    )
    assert a["path"] == binding.PATH_A
    b = binding.select_binding_path(asset=_manifest(), import_supported=True, course_is_new=True)
    assert b["path"] == binding.PATH_B
    mixed = binding.select_binding_path(asset=_manifest(), import_supported=True,
                                        course_is_new=True, hierarchy_created_by_api=True)
    assert mixed["path"] == binding.PATH_C and mixed["mixed_import_refused"] is True
    c = binding.select_binding_path(asset=_manifest(), public_ingest_available=False)
    assert c["path"] == binding.PATH_C


# ── narrow upload exception (never general browser upload) ──────────────────
def test_native_upload_exception_is_narrow():
    ok = binding.native_course_upload_exception(
        purpose="native_course_content", public_ingest_available=False, asset=_manifest())
    assert ok["allowed"] is True and ok["rail"] == "managed_browser_native_course_upload"
    for bad in ("page_media", "ad_media", "funnel_media", "branding", "thumbnail"):
        with pytest.raises(binding.BindingRefused):
            binding.native_course_upload_exception(purpose=bad, public_ingest_available=False)
    with pytest.raises(binding.BindingRefused):
        binding.native_course_upload_exception(
            purpose="native_course_content", public_ingest_available=True)


# ── bounded, resumable processing wait ──────────────────────────────────────
def test_processing_wait_is_bounded_and_resumable():
    ticks = {"t": 0.0}
    clock = lambda: ticks["t"]

    def pending_poll(_cursor):
        ticks["t"] += 1.0
        return "pending"

    out = binding.poll_processing(pending_poll, deadline_s=100.0, interval_s=0.0,
                                  max_polls=2, clock=clock, sleep=lambda s: None)
    assert out["state"] == "timeout"
    assert out["reason"] == "max_polls_reached"
    assert out["resumable"] is True and out["bounded"] is True
    assert out["polls"] == 2

    # Resume with the token: the poll count continues, it does not restart.
    again = binding.poll_processing(lambda _c: "ready", state=out, deadline_s=100.0,
                                    interval_s=0.0, clock=clock, sleep=lambda s: None)
    assert again["state"] == "ready"
    assert again["polls"] == out["polls"] + 1

    # A real deadline also stops the wait instead of spinning forever.
    ticks["t"] = 500.0
    hard = binding.poll_processing(pending_poll, state=out, interval_s=0.0,
                                   clock=clock, sleep=lambda s: None)
    assert hard["state"] == "timeout" and hard["reason"] == "deadline_reached"


# ── IG-COURSE-06 (FIXTURE level): one video fixture through the chosen path ──
def _managed_actions(*, processing="ready", observed_content_id="cnt_777",
                    pending_editor=False):
    def navigate(step, cursor):
        return {"ok": True, "navigated_to": step["target"]["course_id"]}
    def open_editor(step, _cursor):
        return {"ok": True}
    def attach(step, _cursor):
        return {"ok": True, "content_id": observed_content_id}
    def save(_step, _cursor):
        return {"ok": True}
    def wait(_step, _cursor):
        return {"ok": True, "wait_state": processing}
    def readback(_step, _cursor):
        return {"readback": {"lesson": {"contentId": observed_content_id,
                                        "contentStatus": "ready"}}}
    def resolve_anchor(step, _cursor):
        # Simulates a WF09 anchor row; the capture-pending case is opt-in.
        if pending_editor and step["selector"] == binding.SELECTOR_LESSON_EDITOR:
            raise binding.BindingRefused(
                "course.outline.lesson_body_editor is capture-pending — STOP, never guess CSS")
        return {"anchor": "anchor:" + str(step["selector"])}
    return {
        "navigate_exact_object": navigate,
        "open_lesson_editor": open_editor,
        "attach_validated_asset": attach,
        "save": save,
        "wait_processing": wait,
        "readback_association": readback,
        "resolve_anchor": resolve_anchor,
    }


def test_ig_course_06_managed_fixture_reads_association_back(tmp_path):
    path = _write(tmp_path, "v.mp4", MP4_BYTES)
    sha = hashlib.sha256(MP4_BYTES).hexdigest()
    asset = binding.validate_asset_manifest(
        _manifest(local_path=path, sha256=sha, byte_size=len(MP4_BYTES)))
    steps = binding.managed_binding_steps(asset, course_id="crs1", lesson_id="les1")
    res = binding.apply_managed_ui_binding(steps, _managed_actions(), asset=asset)
    assert res["path"] == binding.PATH_C
    assert res["proof"]["asset_persisted"] is True
    assert res["proof"]["native_content_ready"] is True
    assert res["proof"]["lesson_association_verified"] is True
    assert res["proof"]["learner_render_verified"] is False   # no learner observation


def test_ig_course_06_missing_association_blocks_only_that_lesson(tmp_path):
    path = _write(tmp_path, "v.mp4", MP4_BYTES)
    sha = hashlib.sha256(MP4_BYTES).hexdigest()
    asset = binding.validate_asset_manifest(
        _manifest(local_path=path, sha256=sha, byte_size=len(MP4_BYTES)))
    steps = binding.managed_binding_steps(asset, course_id="crs1", lesson_id="les1")

    acts = _managed_actions(observed_content_id="cnt_777")
    acts["readback_association"] = lambda _s, _c: {
        "readback": {"lesson": {"contentId": "cnt_DIFFERENT"}}}
    blocked = binding.apply_managed_ui_binding(steps, acts, asset=asset)
    assert blocked["proof"]["asset_persisted"] is True
    assert blocked["proof"]["lesson_association_verified"] is False
    assert binding.binding_complete(blocked["proof"]) is False

    # A different lesson's proof is a separate object — unaffected.
    other = binding.apply_managed_ui_binding(steps, _managed_actions(), asset=asset)
    assert other["proof"]["lesson_association_verified"] is True


def test_ig_course_06_capture_pending_editor_stops_without_claiming(tmp_path):
    path = _write(tmp_path, "v.mp4", MP4_BYTES)
    sha = hashlib.sha256(MP4_BYTES).hexdigest()
    asset = binding.validate_asset_manifest(
        _manifest(local_path=path, sha256=sha, byte_size=len(MP4_BYTES)))
    steps = binding.managed_binding_steps(asset, course_id="crs1", lesson_id="les1")
    with pytest.raises(binding.BindingRefused) as exc:
        binding.apply_managed_ui_binding(steps, _managed_actions(pending_editor=True),
                                         asset=asset)
    assert "capture-pending" in str(exc.value)


# ── ghl_media narrow change: validated course-asset upload ──────────────────
def test_ghl_media_course_asset_upload_validates_bytes(tmp_path):
    path = _write(tmp_path, "v.mp4", MP4_BYTES)
    sha = hashlib.sha256(MP4_BYTES).hexdigest()
    captured = {}

    def opener(req, _timeout):
        captured["auth"] = req.get_header("Authorization")
        captured["ctype"] = req.get_header("Content-type") or req.get_header("Content-Type")
        return FakeResponse(200, {"fileId": "f_1", "url": "https://cdn/x.mp4"})

    res = ghl_media.upload_course_asset(
        path, "loc1", "launch101-intro.mp4", "not-a-real-token",
        expected_mime="video/mp4", sha256=sha, byte_size=len(MP4_BYTES), opener=opener)
    assert res["fileId"] == "f_1" and res["sha256"] == sha
    assert captured["ctype"].startswith("multipart/form-data; boundary=")

    with pytest.raises(ValueError):
        ghl_media.upload_course_asset(
            path, "loc1", "n.mp4", "not-a-real-token", expected_mime="video/mp4",
            sha256="d" * 64, byte_size=len(MP4_BYTES), opener=opener)


def test_ghl_media_png_rail_is_unchanged(tmp_path):
    png = _write(tmp_path, "a.png", PNG_BYTES)
    mp4 = _write(tmp_path, "b.mp4", MP4_BYTES)
    assert ghl_media.verify_png(png) is True
    assert ghl_media.verify_png(mp4) is False
    with pytest.raises(ValueError):
        ghl_media.upload_media(mp4, "loc1", "x", "not-a-real-token",
                               opener=lambda r, t: FakeResponse(200, {}))
    with pytest.raises(ValueError):
        ghl_media.inspect_course_asset(png, "video/mp4")


# ── contract drift guard ────────────────────────────────────────────────────
def test_contract_file_matches_the_module():
    contract = binding.load_contract()
    assert contract["contract_id"] == "WF08-CP01"
    assert tuple(contract["proof_fields"]) == binding.PROOF_FIELDS
    assert contract["module"].endswith("ghl_course_media_binding.py")
    assert contract["import_lifecycle_states"] == list(binding.IMPORT_STATES)
    for name in contract["seam_functions"]:
        assert hasattr(binding, name), f"contract names {name}() but the module does not"
