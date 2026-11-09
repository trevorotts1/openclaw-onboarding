"""WF12 / A16: the 66/67/68 consumer hooks reach the shared normalizer, or degrade to None.

Offline: real bytes in a temp dir, bridge subprocess never called, no key, no network.
Run: python3 -m pytest shared-utils/ghl/test_course_consumer_hooks.py -q
"""
import hashlib
import importlib.util
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypisom" + b"M" * 64
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"W" * 64


def _bridge(skill):
    path = os.path.join(_REPO, skill, "scripts", "adapter_bridge.py")
    spec = importlib.util.spec_from_file_location("bridge_" + skill.split("-")[0], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("skill,role", [
    ("66-kie-image", "lesson_image"),
    ("67-kie-video", "lesson_video"),
    ("68-kie-audio", "lesson_audio"),
])
def test_manifest_is_queued_with_logical_keys(skill, role):
    br = _bridge(skill)
    m = br.course_manifest("launch-101", "welcome", "intro", role,
                           model_id="model-x", task_id="TASK-1")
    assert m is not None, "shared-utils/ghl/course_assets.py not reachable from " + skill
    assert m["asset_key"] == "launch-101:welcome:intro:" + role
    assert m["generation_state"] == "queued"
    assert m["model_id"] == "model-x" and m["provider_task_id"] == "TASK-1"


@pytest.mark.parametrize("skill", ["66-kie-image", "67-kie-video", "68-kie-audio"])
def test_bad_key_returns_none_never_raises(skill):
    br = _bridge(skill)
    assert br.course_manifest("launch:101", "welcome", "intro", "lesson_image") is None
    assert br.course_manifest("", "m", "l", "lesson_image") is None


def test_image_completion_from_real_bytes(tmp_path):
    br = _bridge("66-kie-image")
    p = tmp_path / "a.png"
    p.write_bytes(PNG)
    m = br.course_manifest("c", "m", "l", "lesson_image")
    done = br.course_completion(m, local_path=str(p))
    assert done["generation_state"] == "completed"
    assert done["sha256"] == hashlib.sha256(PNG).hexdigest()
    assert done["mime_type"] == "image/png"
    assert done["duration_seconds"] is None


def test_url_alone_and_mislabelled_bytes_return_none(tmp_path):
    br = _bridge("66-kie-image")
    m = br.course_manifest("c", "m", "l", "lesson_image")
    assert br.course_completion(m, local_path=None) is None
    bad = tmp_path / "a.mp4"
    bad.write_bytes(PNG)
    video = br.course_manifest("c", "m", "l", "lesson_video")
    assert br.course_completion(video, local_path=str(bad), duration_seconds=5) is None


def test_video_and_audio_need_duration(tmp_path):
    cases = (("67-kie-video", "lesson_video", "a.mp4", MP4), ("68-kie-audio", "lesson_audio", "a.wav", WAV))
    for skill, role, name, data in cases:
        p = tmp_path / name
        p.write_bytes(data)
        br = _bridge(skill)
        m = br.course_manifest("c", "m", "l", role)
        assert br.course_completion(m, local_path=str(p)) is None
        done = br.course_completion(m, local_path=str(p), duration_seconds=42.5)
        assert done["duration_seconds"] == 42.5 and done["generation_state"] == "completed"


def test_completion_of_none_manifest_is_none():
    br = _bridge("68-kie-audio")
    assert br.course_completion(None, local_path="x") is None
