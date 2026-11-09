"""WF12 / A16: the KIE -> GHL course-asset seam.

Offline only: real bytes in a temp dir, no network, no credentials, no provider call.
Each test function is the executable form of one A16 assertion.

Run: python3 -m pytest shared-utils/ghl/test_course_assets_units.py -q
"""
import hashlib
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import course_assets as ca  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"J" * 60
MP4 = b"\x00\x00\x00\x18ftypisom" + b"M" * 60
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"W" * 60
MP3 = b"ID3\x04\x00\x00" + b"A" * 60


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _manifest(role="lesson_image"):
    return ca.new_manifest("launch-101", "welcome", "intro", role)


# ---------------------------------------------------------------- A16: keys
def test_a16_stable_logical_keys_not_titles():
    a = ca.new_manifest("launch-101", "welcome", "intro", "lesson_video")
    b = ca.new_manifest("launch-101", "welcome", "deep-dive", "lesson_video")
    assert a["asset_key"] == "launch-101:welcome:intro:lesson_video"
    assert a["asset_key"] != b["asset_key"]
    # Two lessons sharing a display title stay distinct because the key is the path.
    assert ca.parse_asset_key(a["asset_key"]) == {
        "course_key": "launch-101", "module_key": "welcome",
        "lesson_key": "intro", "role": "lesson_video"}


def test_a16_key_with_separator_or_empty_part_is_refused():
    with pytest.raises(ca.AssetError) as e:
        ca.logical_asset_key("launch:101", "welcome", "intro", "lesson_image")
    assert e.value.code == "bad_key"
    with pytest.raises(ca.AssetError):
        ca.logical_asset_key("launch-101", "", "intro", "lesson_image")
    with pytest.raises(ca.AssetError):
        ca.parse_asset_key("only:three:parts")


def test_a16_manifest_keys_must_agree_with_asset_key():
    m = _manifest()
    m["lesson_key"] = "some-other-lesson"
    errs = ca.validate_manifest(m)
    assert any("does not match its own keys" in x for x in errs), errs


def test_a16_identity_fields_required_in_every_state():
    m = _manifest()
    m["provider"] = None
    assert any(x.startswith("provider: required") for x in ca.validate_manifest(m))


# ---------------------------------------------- A16: true async completion
def test_a16_queued_generation_is_never_completed():
    m = _manifest()
    assert m["generation_state"] == "queued"
    assert ca.validate_manifest(m) == []          # legal to hold, not to deliver
    assert m["sha256"] is None and m["byte_size"] is None and m["local_path"] is None


def test_a16_adapter_queued_and_validated_stay_incomplete():
    m = _manifest()
    assert ca.completion_from_adapter_result({"state": "queued", "task_id": "T1"}, m)["generation_state"] == "running"
    assert ca.completion_from_adapter_result({"state": "running", "task_id": "T1"}, m)["generation_state"] == "running"
    assert ca.completion_from_adapter_result({"state": "validated"}, m)["generation_state"] == "queued"
    assert ca.completion_from_adapter_result({"state": "fail", "error": {"msg": "boom"}}, m)["generation_state"] == "failed"


def test_a16_bounded_poll_deadline_returns_running_never_completed():
    ticks = iter([{"state": "running", "task_id": "T9"}] * 50)
    clock = {"t": 0.0}
    res = ca.bounded_poll(lambda: next(ticks), _manifest(), timeout_seconds=10,
                          interval_seconds=3, sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                          now=lambda: clock["t"])
    assert res["generation_state"] == "running"
    assert res["poll_deadline_reached"] is True
    assert res["provider_task_id"] == "T9"


# ------------------------------------------- A16: bytes, hash, MIME, size
@pytest.mark.parametrize("role,name,data,mime", [
    ("lesson_image", "a.png", PNG, "image/png"),
    ("lesson_image", "a.jpg", JPEG, "image/jpeg"),
    ("lesson_video", "a.mp4", MP4, "video/mp4"),
    ("lesson_audio", "a.wav", WAV, "audio/wav"),
    ("lesson_audio", "a.mp3", MP3, "audio/mpeg"),
])
def test_a16_hash_and_size_come_from_actual_bytes(tmp_path, role, name, data, mime):
    path = _write(tmp_path, name, data)
    done = ca.normalize_completion(_manifest(role), local_path=path, duration_seconds=12.5)
    assert done["sha256"] == hashlib.sha256(data).hexdigest()
    assert done["byte_size"] == len(data)
    assert done["mime_type"] == mime
    assert done["generation_state"] == "completed"
    assert ca.validate_manifest(done) == []


def test_a16_mislabeled_download_is_refused(tmp_path):
    # A .mp4 name on PNG bytes: the extension claims video, the bytes are an image.
    path = _write(tmp_path, "not-a-video.mp4", PNG)
    with pytest.raises(ca.AssetError) as e:
        ca.normalize_completion(_manifest("lesson_video"), local_path=path, duration_seconds=5)
    assert e.value.code == "mime_mismatch", e.value.code

    # A caller-declared type that disagrees with the bytes is the same refusal.
    with pytest.raises(ca.AssetError) as e2:
        ca.normalize_completion(_manifest(), local_path=path, mime_type="video/mp4")
    assert e2.value.code == "mime_mismatch"

    # And a manifest that carries an image MIME under a video role never validates.
    m = _manifest("lesson_video")
    m.update({"generation_state": "completed", "local_path": path, "sha256": "b" * 64,
              "byte_size": 10, "mime_type": "image/png", "duration_seconds": 5})
    assert any("does not match the video role" in x for x in ca.validate_manifest(m))


def test_a16_empty_and_missing_files_are_refused(tmp_path):
    empty = _write(tmp_path, "empty.png", b"")
    with pytest.raises(ca.AssetError) as e:
        ca.normalize_completion(_manifest(), local_path=empty)
    assert e.value.code == "empty_file"
    with pytest.raises(ca.AssetError) as e2:
        ca.normalize_completion(_manifest(), local_path=str(tmp_path / "nope.png"))
    assert e2.value.code == "no_local_file"


def test_a16_per_type_required_fields(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    mp4 = _write(tmp_path, "a.mp4", MP4)
    # image never asked for an invented duration
    assert ca.normalize_completion(_manifest("lesson_image"), local_path=png)["duration_seconds"] is None
    # video/audio must carry one
    for role, path in (("lesson_video", mp4), ("lesson_audio", mp4)):
        with pytest.raises(ca.AssetError) as e:
            ca.normalize_completion(_manifest(role), local_path=path)
        assert "duration_seconds" in e.value.msg


# --------------------------------------------- A16: durable persistence
def test_a16_temp_provider_url_is_never_durable(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    ca.assert_valid(ca.normalize_completion(_manifest(), local_path=png))
    m = ca.normalize_completion(_manifest(), local_path=png)
    m["durable_url"] = "https://tempfile.aiquickdraw.com/abc.png"
    m["storage_access"] = "approved_for_destination"
    errs = ca.validate_manifest(m)
    assert any("temporary provider result URL is not durable" in x for x in errs), errs


def test_a16_approved_storage_without_url_is_refused(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    m = ca.normalize_completion(_manifest(), local_path=png)
    m["storage_access"] = "approved_for_destination"
    assert any("no durable_url" in x for x in ca.validate_manifest(m))
    m["durable_url"] = "https://storage.example/asset.png"
    assert ca.validate_manifest(m) == []


def test_a16_completed_manifest_must_name_a_real_local_file():
    m = _manifest()
    m.update({"generation_state": "completed", "sha256": "a" * 64, "byte_size": 10,
              "mime_type": "image/png", "local_path": None})
    errs = ca.validate_manifest(m)
    assert any(x.startswith("local_path: required") for x in errs), errs


# ------------------------------------------ A16: duplicate callbacks
def test_a16_duplicate_completion_updates_one_record(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    m = _manifest()
    done = ca.normalize_completion(m, local_path=png)
    store = ca.AssetStore()

    first = store.apply(m)
    assert first["changed"] is True and first["duplicate"] is False
    second = store.apply(done)
    assert second["changed"] is True and second["duplicate"] is False
    third = store.apply(done)
    assert third["duplicate"] is True and third["changed"] is False
    assert third["record"]["sha256"] == done["sha256"]
    assert len(store.records) == 1
    assert third["record"]["manifest_revision"] == second["record"]["manifest_revision"]


def test_a16_second_different_completion_is_conflict_not_reupload(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    jpg = _write(tmp_path, "b.jpg", JPEG)
    m = _manifest()
    store = ca.AssetStore()
    store.apply(ca.normalize_completion(m, local_path=png))
    outcome = store.apply(ca.normalize_completion(m, local_path=jpg))
    assert outcome["conflict"] is True
    assert outcome["changed"] is False
    assert outcome["record"]["sha256"] == hashlib.sha256(PNG).hexdigest()
    assert len(store.records) == 1
    assert outcome["record"]["conflict"]["reason"] == "second different completion for one asset_key"


def test_a16_late_failure_never_downgrades_a_completed_asset(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    m = _manifest()
    store = ca.AssetStore()
    done = ca.normalize_completion(m, local_path=png)
    store.apply(done)
    late = store.apply(ca.record_failure(m, "retry noise"))
    assert late["duplicate"] is True and late["changed"] is False
    assert late["record"]["generation_state"] == "completed"


def test_a16_invalid_manifest_never_enters_the_store():
    bad = _manifest()
    bad["role"] = "unknown_role"
    with pytest.raises(ca.AssetError) as e:
        ca.AssetStore().apply(bad)
    assert e.value.code == "invalid_manifest"


# ------------------------------------------------- A16: handoff into WF08
def test_a16_handoff_refuses_incomplete_and_accepts_completed(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    m = _manifest()
    with pytest.raises(ca.AssetError) as e:
        ca.to_wf08_handoff(m)
    assert e.value.code == "not_completed"
    done = ca.normalize_completion(m, local_path=png)
    req = ca.to_wf08_handoff(done)
    assert req["asset_key"] == done["asset_key"]
    assert req["sha256"] == done["sha256"]
    assert req["mime_type"] == "image/png"
    assert req["ghl_binding"]["state"] == "not_started"


def test_a16_handoff_batch_is_all_or_nothing(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    done = ca.normalize_completion(_manifest(), local_path=png)
    video = _manifest("lesson_video")           # still queued
    with pytest.raises(ca.AssetError) as e:
        ca.handoff_batch([done, video])
    assert e.value.code == "invalid_batch"
    assert video["asset_key"] in e.value.msg
    out = ca.handoff_batch([done])
    assert len(out["assets"]) == 1 and out["schema_version"] == ca.SCHEMA_VERSION


# ------------------------------------- A16: Skill 74 / Skill 46 hooks
def test_a16_skill74_url_without_saved_bytes_is_refused(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    m = _manifest()
    with pytest.raises(ca.AssetError) as e:
        ca.completion_from_adapter_result({"state": "success", "result_urls": ["https://x/a.png"]}, m)
    assert e.value.code == "no_persisted_bytes"
    done = ca.completion_from_adapter_result({"state": "success", "saved_paths": [png]}, m)
    assert done["generation_state"] == "completed"
    assert done["sha256"] == hashlib.sha256(PNG).hexdigest()
    skipped = ca.completion_from_adapter_result({"state": "skipped"}, m)
    assert skipped["generation_state"] == "failed"


def test_a16_skill46_record_requires_done_and_urls_and_bytes(tmp_path):
    png = _write(tmp_path, "a.png", PNG)
    m = _manifest()
    assert ca.completion_from_callback_record({"status": "timeout"}, m, local_path=png)["generation_state"] == "failed"
    assert ca.completion_from_callback_record({"status": "done", "resultUrls": []}, m,
                                              local_path=png)["generation_state"] == "failed"
    with pytest.raises(ca.AssetError) as e:
        ca.completion_from_callback_record({"status": "done", "resultUrls": ["https://x/a.png"]}, m,
                                           local_path=None)
    assert e.value.code == "no_local_file"
    done = ca.completion_from_callback_record({"status": "done", "resultUrls": ["https://x/a.png"]},
                                              m, local_path=png)
    assert done["generation_state"] == "completed"
    assert done["sha256"] == hashlib.sha256(PNG).hexdigest()


def test_a16_no_credentials_or_network_in_the_seam():
    # Callback workers and KIE consumers carry no GHL credential and no provider key.
    src = open(os.path.join(_HERE, "course_assets.py"), encoding="utf-8").read()
    for forbidden in ("KIE_API_KEY", "GHL_API_KEY", "import requests", "urllib.request", "http.client"):
        assert forbidden not in src, forbidden
    # Polling is available on its own: a deck's polling policy is never forced onto callbacks.
    res = ca.bounded_poll(lambda: {"state": "success", "saved_paths": []}, _manifest())
    assert res["generation_state"] == "failed"
