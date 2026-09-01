"""FIX-11 — tests for the read-only GHL media-library LIST-BACK (ghl_media.list_media)
and the _verify_ghl_upload list-back proof.

The FIX-11 QC gate requires "Upload returns success AND the deck appears in the
listing." The engine already uploads via ghl_media.upload_media + create_media_folder
(wired through P9.2-GHL-UPLOAD). The missing half was the read-only verification:
proving a just-uploaded deck is genuinely in the GHL library by listing it back.
These tests prove list_media is (a) READ-ONLY (GET, no mutation), (b) correct on the
response shape, and (c) fail-loud on a non-2xx / missing listing — plus the verifier's
fail-soft and fail-on-missing-deck behaviour.

No network: every fixture is a mock opener or files on disk."""

from __future__ import annotations

import json
import pathlib
import sys


# ---------------------------------------------------------------------------
# Helpers — a mock HTTP response + an opener that records the Request it saw
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, code: int, body):
        self._code = code
        self._body = body

    def getcode(self):
        return self._code

    def read(self):
        return self._body if isinstance(self._body, bytes) else self._body.encode()


class _Recorder:
    def __init__(self, code: int = 200, body=None):
        self.requests = []
        self.code = code
        raw = body if body is not None else {"data": []}
        self.body = (raw.encode() if isinstance(raw, str)
                     else json.dumps(raw).encode())

    def __call__(self, req, timeout):
        self.requests.append(req)
        return _Resp(self.code, self.body)


def _mk_media_ledger(base: pathlib.Path, *, pptx_id: str = "file_deck", pptx_name: str = "DECK demo.pptx") -> pathlib.Path:
    ck = base / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    p = ck / "media_library.json"
    p.write_text(json.dumps({
        "ghl_folder_id": "folder-abc",
        "pptx_ghl_media_id": pptx_id,
        "pptx_ghl_remote_name": pptx_name,
        "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}],
    }))
    return p


# ---------------------------------------------------------------------------
# 1. list_media is READ-ONLY: HTTP GET, correct path/params, no mutation
# ---------------------------------------------------------------------------


def test_list_media_is_readonly_get():
    import ghl_media
    rec = _Recorder(200, {"data": [{"name": "deck.pptx", "_id": "file_1", "url": "https://cdn/x"}]})
    res = ghl_media.list_media("loc123", "pit-token", media_type="file", opener=rec)
    assert res["http"] == 200
    assert res["count"] == 1
    assert res["data"][0]["name"] == "deck.pptx"
    req = rec.requests[0]
    assert req.get_method() == "GET", "list_media must be a READ-ONLY GET"
    assert "/medias/files" in req.full_url
    assert "locationId=loc123" in req.full_url
    assert "type=file" in req.full_url


def test_list_media_folder_type_and_query_params():
    import ghl_media
    rec = _Recorder(200, {"data": [{"name": "DECK demo", "_id": "fld_1"}]})
    ghl_media.list_media("loc123", "pit-token", media_type="folder",
                         parent_id="fld_parent", query="demo", opener=rec)
    req = rec.requests[0]
    assert req.get_method() == "GET"
    assert "type=folder" in req.full_url
    assert "parentId=fld_parent" in req.full_url
    assert "query=demo" in req.full_url


def test_list_media_raises_on_non2xx():
    import ghl_media
    import pytest
    rec = _Recorder(401, {"message": "not authorized for this scope"})
    with pytest.raises(RuntimeError) as ei:
        ghl_media.list_media("loc123", "pit-token", opener=rec)
    assert "401" in str(ei.value)


def test_list_media_raises_on_missing_args():
    import ghl_media
    import pytest
    with pytest.raises(ValueError):
        ghl_media.list_media("", "pit-token")
    with pytest.raises(ValueError):
        ghl_media.list_media("loc123", "")


def test_list_media_parses_alternate_key_shapes():
    """The API returns `data`; also tolerate `files` and a bare list (defensive)."""
    import ghl_media
    rec = _Recorder(200, {"files": [{"name": "a", "fileId": "f1"}]})
    res = ghl_media.list_media("loc123", "pit-token", opener=rec)
    assert res["count"] == 1
    assert res["data"][0]["fileId"] == "f1"


# ---------------------------------------------------------------------------
# 2. _verify_ghl_upload does the list-back when env resolves
# ---------------------------------------------------------------------------


def test_verify_ghl_upload_list_back_found(monkeypatch, tmp_path):
    """Ledger present + env resolves + the deck IS in the listing -> PASS."""
    import phase_verifiers as pv
    import ghl_media
    base = tmp_path / "run"
    _mk_media_ledger(base, pptx_id="file_deck", pptx_name="DECK demo.pptx")

    class _FakeResolve:
        def __call__(self):
            return "pit-token"

    def _fake_list_media(loc, pit, **kw):
        return {"http": 200, "count": 1,
                "data": [{"name": "DECK demo.pptx", "_id": "file_deck"}]}

    monkeypatch.setattr(ghl_media, "resolve_location_pit", _FakeResolve())
    monkeypatch.setattr(ghl_media, "resolve_location_id", _FakeResolve())
    monkeypatch.setattr(ghl_media, "list_media", _fake_list_media)
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is True
    hard = [r for r in reasons if not str(r).startswith("NOTE")]
    assert hard == []


def test_verify_ghl_upload_list_back_missing_deck(monkeypatch, tmp_path):
    """Ledger present + env resolves + the deck is NOT in the listing -> FAIL
    (AF-BUNDLE-COMPLETE). This is the QC gate: an upload record that does not survive
    a real list-back is not an upload."""
    import phase_verifiers as pv
    import ghl_media
    base = tmp_path / "run"
    _mk_media_ledger(base, pptx_id="file_deck", pptx_name="DECK demo.pptx")

    class _FakeResolve:
        def __call__(self):
            return "pit-token"

    def _fake_list_media(loc, pit, **kw):
        # The library has OTHER files, but NOT this deck.
        return {"http": 200, "count": 1, "data": [{"name": "unrelated.png", "_id": "x1"}]}

    monkeypatch.setattr(ghl_media, "resolve_location_pit", _FakeResolve())
    monkeypatch.setattr(ghl_media, "resolve_location_id", _FakeResolve())
    monkeypatch.setattr(ghl_media, "list_media", _fake_list_media)
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is False
    assert any("AF-BUNDLE-COMPLETE" in r and "NOT present in the GHL media library" in r
               for r in reasons)


def test_verify_ghl_upload_list_back_fail_soft_no_env(tmp_path):
    """Ledger present + env does NOT resolve -> PASS with a NOTE (never blocks)."""
    import phase_verifiers as pv
    base = tmp_path / "run"
    _mk_media_ledger(base)
    import os
    saved = {k: os.environ.get(k) for k in ("GOHIGHLEVEL_API_KEY", "GHL_API_KEY",
                                            "GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID")}
    for k in saved:
        os.environ.pop(k, None)
    try:
        ok, reasons = pv._verify_ghl_upload(base)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert ok is True
    assert any(str(r).startswith("NOTE") for r in reasons)


def test_verify_ghl_upload_missing_pptx_id(tmp_path):
    """Ledger present but no pptx_ghl_media_id -> FAIL (AF-BUNDLE-COMPLETE)."""
    import phase_verifiers as pv
    base = tmp_path / "run"
    _mk_media_ledger(base, pptx_id="", pptx_name="")
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is False
    assert any("pptx_ghl_media_id" in r for r in reasons)


def test_verify_ghl_upload_no_ledger(tmp_path):
    """No ledger at all -> PASS with a NOTE (deferred; the runner already fails on a
    missing produces_artifact)."""
    import phase_verifiers as pv
    base = tmp_path / "empty"
    ok, reasons = pv._verify_ghl_upload(base)
    assert ok is True
    assert any("media_library.json not found" in str(r) for r in reasons)
