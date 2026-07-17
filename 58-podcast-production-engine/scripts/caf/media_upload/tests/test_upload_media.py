"""Unit tests for the Podcast Engine media upload layer (PRD Step 14).

Every test is hermetic. No live CRM or CDN is ever contacted: all HTTP goes
through an injected fake transport that records its calls. A test that reaches
the real network is a hard failure by construction (the real transport is never
passed in).

Run:
    python3 -m pytest test_upload_media.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import upload_media as mu  # noqa: E402


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class FakeResp:
    def __init__(self, status_code: int, body: Any = None,
                 headers: Dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Recorder:
    """A transport that returns scripted responses and records every call."""

    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _tmpfile(suffix: str = ".bin", data: bytes = b"x") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return path


# --------------------------------------------------------------------------- #
# Filenames
# --------------------------------------------------------------------------- #

def test_sanitize_strict_underscores_single_ext():
    assert mu.sanitize_strict("Sample Speaker!", "The Power of Marketing", "jpg") == \
        "Sample_Speaker_The_Power_of_Marketing.jpg"


def test_sanitize_strict_no_double_period():
    name = mu.sanitize_strict("A.B", "C.D", "jpg")
    assert name.count(".") == 1 and name.endswith(".jpg")


def test_sanitize_strict_empty_falls_back():
    assert mu.sanitize_strict("", "", "jpg") == "podcast_episode.jpg"


def test_sanitize_loose_client_first_with_spaces():
    assert mu.sanitize_loose("Sample Speaker", "The Power of Marketing", "mp3") == \
        "Sample Speaker - The Power of Marketing.mp3"


def test_sanitize_loose_strips_illegal_chars():
    assert mu.sanitize_loose("A/B*C", "D:E", "pdf") == "A B C - D E.pdf"


# --------------------------------------------------------------------------- #
# Secrecy
# --------------------------------------------------------------------------- #

def test_redact_removes_secret():
    out = mu.redact("Authorization: Bearer pit-abc123", "pit-abc123")
    assert "pit-abc123" not in out and mu.REDACTION in out


def test_credential_report_has_no_value():
    cred = mu.Credential(present=True, value="pit-secret", alias="GHL_API_KEY",
                         prefix_ok=True, length=10)
    report = json.dumps(cred.report())
    assert "pit-secret" not in report
    assert "SET" in report and "GHL_API_KEY" in report


# --------------------------------------------------------------------------- #
# Credential resolution
# --------------------------------------------------------------------------- #

def test_resolve_pit_precedence_canonical_first():
    env = {"GHL_API_KEY": "pit-second", "GOHIGHLEVEL_API_KEY": "pit-first"}
    cred = mu.resolve_pit(env)
    assert cred.present and cred.alias == "GOHIGHLEVEL_API_KEY"
    assert cred.prefix_ok is True


def test_resolve_pit_convertflow_alias():
    cred = mu.resolve_pit({"CONVERTFLOW_API_KEY": "pit-cf"})
    assert cred.present and cred.alias == "CONVERTFLOW_API_KEY"


def test_resolve_pit_missing():
    cred = mu.resolve_pit({})
    assert not cred.present and cred.report()["status"] == "NOT SET"


def test_resolve_location_mismatch_is_tenant_abort():
    with pytest.raises(mu.CredentialError):
        mu.resolve_location_id({"GHL_LOCATION_ID": "LOC_A"},
                               payload_location_id="LOC_B")


def test_resolve_location_from_payload_when_env_absent():
    assert mu.resolve_location_id({}, payload_location_id="LOC_X") == "LOC_X"


# --------------------------------------------------------------------------- #
# Folder lookup / ensure
# --------------------------------------------------------------------------- #

CRED = mu.Credential(present=True, value="pit-test", alias="GHL_API_KEY",
                     prefix_ok=True, length=8)


def test_list_folders_non_200_returns_empty():
    rec = Recorder([FakeResp(500)])
    assert mu.list_folders(CRED, "LOC", transport=rec) == []


def test_ensure_folders_finds_all_three():
    body = {"files": [
        {"id": "P", "name": "podcast", "type": "folder", "createdAt": "1"},
        {"id": "I", "name": "Podcast Images", "type": "folder", "createdAt": "2"},
        {"id": "E", "name": "podcast episodes ", "type": "folder", "createdAt": "3"},
    ]}
    rec = Recorder([FakeResp(200, body)])
    folders = mu.ensure_folders(CRED, "LOC", transport=rec)
    assert folders[mu.PARENT_FOLDER] == "P"
    assert folders[mu.IMAGES_FOLDER] == "I"
    assert folders[mu.EPISODES_FOLDER] == "E"
    assert folders["_warnings"] == []


def test_ensure_folders_missing_child_warns_and_degrades():
    body = {"files": [{"id": "P", "name": "podcast", "type": "folder",
                       "createdAt": "1"}]}
    rec = Recorder([FakeResp(200, body)])
    folders = mu.ensure_folders(CRED, "LOC", transport=rec)
    assert folders[mu.IMAGES_FOLDER] is None
    assert any("podcast images" in w for w in folders["_warnings"])
    assert mu._pick_parent(folders, mu.IMAGES_FOLDER) == "P"


def test_ensure_folders_duplicate_picks_oldest():
    body = {"files": [
        {"id": "NEW", "name": "podcast", "type": "folder", "createdAt": "2026-02"},
        {"id": "OLD", "name": "Podcast", "type": "folder", "createdAt": "2026-01"},
    ]}
    rec = Recorder([FakeResp(200, body)])
    folders = mu.ensure_folders(CRED, "LOC", transport=rec)
    assert folders[mu.PARENT_FOLDER] == "OLD"
    assert any("Duplicate" in w for w in folders["_warnings"])


def test_ensure_folders_cache_hit_skips_network():
    state = {"folders": {mu.PARENT_FOLDER: "P", mu.IMAGES_FOLDER: "I",
                         mu.EPISODES_FOLDER: "E"}}
    rec = Recorder([])  # empty; any network call would IndexError
    folders = mu.ensure_folders(CRED, "LOC", state=state, transport=rec)
    assert folders["_source"] == "state-cache"
    assert rec.calls == []


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #

def test_upload_file_happy_path():
    path = _tmpfile(".mp3")
    rec = Recorder([FakeResp(200, {"fileId": "F1", "url": "https://cdn/x.mp3"})])
    out = mu.upload_file(path, "x.mp3", "PARENT", CRED, "LOC", transport=rec)
    assert out == {"fileId": "F1", "url": "https://cdn/x.mp3"}
    # multipart form carried the required fields
    call = rec.calls[0]
    assert call["data"]["locationId"] == "LOC"
    assert call["data"]["hosted"] == "false"
    assert call["data"]["parentId"] == "PARENT"
    os.unlink(path)


def test_upload_file_201_is_success_no_retry():
    # GHL's /medias/upload-file returns 201 Created on a real successful upload
    # (confirmed live, S58-U19 proof run). A 201 must be accepted on the first
    # response, exactly like 200, with no retry and therefore no double-upload.
    path = _tmpfile(".mp3")
    rec = Recorder([FakeResp(201, {"fileId": "F3", "url": "https://cdn/z.mp3"})])
    out = mu.upload_file(path, "z.mp3", None, CRED, "LOC", transport=rec)
    assert out == {"fileId": "F3", "url": "https://cdn/z.mp3"}
    assert len(rec.calls) == 1
    os.unlink(path)


def test_upload_file_retries_once_then_succeeds():
    path = _tmpfile(".jpg")
    rec = Recorder([
        FakeResp(200, {}),  # empty body -> retry
        FakeResp(200, {"fileId": "F2", "url": "https://cdn/y.jpg"}),
    ])
    out = mu.upload_file(path, "y.jpg", None, CRED, "LOC", transport=rec)
    assert out["fileId"] == "F2"
    assert len(rec.calls) == 2
    os.unlink(path)


def test_upload_file_429_raises_no_retry():
    path = _tmpfile(".mp3")
    rec = Recorder([mu.RateLimited("429", retry_after=30.0)])
    with pytest.raises(mu.RateLimited) as exc:
        mu.upload_file(path, "x.mp3", None, CRED, "LOC", transport=rec)
    assert exc.value.retry_after == 30.0
    assert len(rec.calls) == 1
    os.unlink(path)


def test_upload_file_auth_failure_raises():
    path = _tmpfile(".mp3")
    rec = Recorder([FakeResp(401, {})])
    with pytest.raises(mu.UploadFailed):
        mu.upload_file(path, "x.mp3", None, CRED, "LOC", transport=rec)
    os.unlink(path)


def test_upload_file_missing_file_raises():
    with pytest.raises(mu.UploadFailed):
        mu.upload_file("/no/such/file.mp3", "x.mp3", None, CRED, "LOC",
                       transport=Recorder([]))


# --------------------------------------------------------------------------- #
# Reachability
# --------------------------------------------------------------------------- #

def test_verify_public_url_head_ok():
    rec = Recorder([FakeResp(200, headers={"Content-Type": "image/jpeg"})])
    res = mu.verify_public_url("https://cdn/x.jpg", "image/", transport=rec)
    assert res["ok"] and res["method"] == "HEAD" and res["warnings"] == []


def test_verify_public_url_head_fails_get_ranged_ok():
    rec = Recorder([
        FakeResp(405),  # HEAD not allowed
        FakeResp(206, headers={"Content-Type": "audio/mpeg"}),
    ])
    res = mu.verify_public_url("https://cdn/x.mp3", "audio/", transport=rec)
    assert res["ok"] and res["method"] == "GET" and res["status"] == 206


def test_verify_public_url_html_is_hard_fail():
    rec = Recorder([FakeResp(200, headers={"Content-Type": "text/html"})])
    with pytest.raises(mu.ReachabilityError):
        mu.verify_public_url("https://cdn/login", "image/", transport=rec)


def test_verify_public_url_octet_stream_warns():
    rec = Recorder([FakeResp(200, headers={"Content-Type": "application/octet-stream"})])
    res = mu.verify_public_url("https://cdn/x.mp3", "audio/", transport=rec)
    assert res["ok"] and res["warnings"]


def test_verify_public_url_404_hard_fail():
    rec = Recorder([FakeResp(404), FakeResp(404)])
    with pytest.raises(mu.ReachabilityError):
        mu.verify_public_url("https://cdn/missing", "image/", transport=rec)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def _upload_ok(url: str, ctype: str):
    return [
        FakeResp(200, {"fileId": "id", "url": url}),       # upload
        FakeResp(200, headers={"Content-Type": ctype}),    # HEAD verify
    ]


def test_store_media_interview_with_teaser():
    cover = _tmpfile(".jpg")
    mp3 = _tmpfile(".mp3")
    pdf = _tmpfile(".pdf")
    folders_body = {"files": [
        {"id": "P", "name": "podcast", "type": "folder", "createdAt": "1"},
        {"id": "I", "name": "podcast images", "type": "folder", "createdAt": "2"},
        {"id": "E", "name": "podcast episodes", "type": "folder", "createdAt": "3"},
    ]}
    responses = (
        [FakeResp(200, folders_body)]
        + _upload_ok("https://cdn/cover.jpg", "image/jpeg")
        + _upload_ok("https://cdn/ep.mp3", "audio/mpeg")
        + _upload_ok("https://cdn/teaser.pdf", "application/pdf")
    )
    rec = Recorder(responses)
    job = {"mode": mu.INTERVIEW_MODE, "client_name": "Sample Speaker",
           "episode_title": "The Power of Marketing", "cover_path": cover,
           "mp3_path": mp3, "teaser_path": pdf}
    result = mu.store_media(job, CRED, "LOC", transport=rec)
    assert set(result["assets"]) == {"cover", "mp3", "teaser"}
    assert result["assets"]["cover"]["parent_id"] == "I"
    assert result["assets"]["mp3"]["parent_id"] == "E"
    assert result["assets"]["teaser"]["parent_id"] == "P"
    assert result["assets"]["mp3"]["url"] == "https://cdn/ep.mp3"
    for path in (cover, mp3, pdf):
        os.unlink(path)


def test_store_media_personal_skips_teaser():
    cover = _tmpfile(".jpg")
    mp3 = _tmpfile(".mp3")
    pdf = _tmpfile(".pdf")
    state = {"folders": {mu.PARENT_FOLDER: "P", mu.IMAGES_FOLDER: "I",
                         mu.EPISODES_FOLDER: "E"}}
    responses = (
        _upload_ok("https://cdn/cover.jpg", "image/jpeg")
        + _upload_ok("https://cdn/ep.mp3", "audio/mpeg")
    )
    rec = Recorder(responses)
    job = {"mode": mu.PERSONAL_MODE, "client_name": "Solo Host",
           "episode_title": "Week One", "cover_path": cover, "mp3_path": mp3,
           "teaser_path": pdf}
    result = mu.store_media(job, CRED, "LOC", state=state, transport=rec)
    assert "teaser" not in result["assets"]
    assert any("teaser skipped" in w for w in result["warnings"])
    for path in (cover, mp3, pdf):
        os.unlink(path)


def test_store_media_reachability_failure_propagates_before_podbean():
    cover = _tmpfile(".jpg")
    state = {"folders": {mu.PARENT_FOLDER: "P", mu.IMAGES_FOLDER: "I",
                         mu.EPISODES_FOLDER: "E"}}
    rec = Recorder([
        FakeResp(200, {"fileId": "id", "url": "https://cdn/cover.jpg"}),
        FakeResp(200, headers={"Content-Type": "text/html"}),  # login page
        FakeResp(200, headers={"Content-Type": "text/html"}),  # GET fallback
    ])
    job = {"mode": mu.PERSONAL_MODE, "client_name": "X", "episode_title": "Y",
           "cover_path": cover}
    with pytest.raises(mu.ReachabilityError):
        mu.store_media(job, CRED, "LOC", state=state, transport=rec)
    os.unlink(cover)


def test_store_media_missing_credential_refuses():
    with pytest.raises(mu.CredentialError):
        mu.store_media({"mode": mu.PERSONAL_MODE, "client_name": "X",
                        "episode_title": "Y"},
                       mu.Credential(present=False), "LOC")


def test_self_test_passes():
    assert mu._self_test() is True
