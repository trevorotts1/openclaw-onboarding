#!/usr/bin/env python3
"""test_drive_broker_per_doc.py -- offline contract test for the E9 per-Doc + tree
broker path in scripts/drive_adapter.py (and the drive-tree-provision.py participant
tree). Proves, WITHOUT any network, that on a pure client box the whole S0..S8 Drive
path routes through the n8n credential broker -- the local Google service account is
NEVER touched -- and that broker-preflight HOLDs (by name) when the deployed workflow
does not implement every REQUIRED action.

Network-free: drive_adapter._https (the single HTTPS chokepoint) is monkeypatched.

Run: python3 -m pytest 59-anthology-engine/tests/test_drive_broker_per_doc.py -q
"""
import base64
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import drive_adapter as da  # noqa: E402

WEBHOOK_URL = "https://main.blackceoautomations.com/webhook/anthology-drive"
BROKER_TOKEN = "lowPrivBrokerTokenXYZ"


def _broker_env(monkeypatch):
    monkeypatch.setenv(da.N8N_WEBHOOK_URL_ENV, WEBHOOK_URL)
    monkeypatch.setenv(da.N8N_WEBHOOK_TOKEN_ENV, BROKER_TOKEN)


def _router_https(captured, table, status=200):
    """A drive_adapter._https stand-in that records each outbound request and returns a
    canned response chosen by the POSTed `action` (or a fixed status). No socket opens."""
    def fake_https(method, host, path, headers, body=None):
        j = json.loads(body.decode("utf-8")) if body else {}
        captured.append({"method": method, "host": host, "path": path,
                         "headers": dict(headers), "body": j})
        action = j.get("action")
        resp = dict(table.get(action, {"ok": True}))
        st = resp.pop("__status__", status)
        return st, json.dumps(resp).encode("utf-8")
    return fake_https


# --------------------------------------------------------------------------
# create_doc
# --------------------------------------------------------------------------
def test_broker_create_doc_posts_and_normalizes(monkeypatch):
    _broker_env(monkeypatch)
    cap = []
    monkeypatch.setattr(da, "_https", _router_https(cap, {
        "create_doc": {"ok": True, "doc_id": "DOC1", "doc_url": "https://docs/DOC1",
                       "name": "c1-chapter", "share_mode": "edit", "permission_id": "PW"}}))
    res = da.broker_create_doc("c1-chapter", "PARENT", text="the body", share_mode="edit")
    assert cap[0]["body"] == {"action": "create_doc", "parent_folder_id": "PARENT",
                              "name": "c1-chapter", "text": "the body", "share_mode": "edit"}
    assert cap[0]["headers"][da.BROKER_TOKEN_HEADER] == BROKER_TOKEN
    assert cap[0]["host"] == "main.blackceoautomations.com"
    assert res["doc_id"] == "DOC1" and res["doc_url"] == "https://docs/DOC1"
    assert res["via"] == "n8n_broker" and res["edit_shared"] is True
    assert res["view_shared"] is False and res["verified"] is True
    assert BROKER_TOKEN not in json.dumps(res)


def test_broker_create_doc_missing_id_raises(monkeypatch):
    _broker_env(monkeypatch)
    monkeypatch.setattr(da, "_https", _router_https([], {"create_doc": {"ok": True}}))
    with pytest.raises(da.DependencyError):
        da.broker_create_doc("n", "p", text="x", share_mode="edit")


def test_deliver_doc_selects_broker_no_local_sa(monkeypatch):
    _broker_env(monkeypatch)
    monkeypatch.setattr(da, "_https", _router_https([], {
        "create_doc": {"ok": True, "doc_id": "DOC9", "doc_url": "u", "share_mode": "edit"}}))
    monkeypatch.setattr(da, "mint_token", lambda scope=da.FULL_SCOPE: pytest.fail(
        "mint_token (local SA) must not be called when the broker is configured"))
    res = da.deliver_doc("nm", "par", text="t", share_mode="edit")
    assert res["doc_id"] == "DOC9" and res["via"] == "n8n_broker"


# --------------------------------------------------------------------------
# upload_pdf (binary relayed base64)
# --------------------------------------------------------------------------
def test_broker_upload_media_base64_relays(monkeypatch, tmp_path):
    _broker_env(monkeypatch)
    png = tmp_path / "cover.png"
    raw = b"\x89PNG\r\n\x1a\n binary body"
    png.write_bytes(raw)
    cap = []
    monkeypatch.setattr(da, "_https", _router_https(cap, {
        "upload_pdf": {"ok": True, "file_id": "F1", "drive_url": "https://drive/F1",
                       "download_url": "https://dl/F1", "share_mode": "view"}}))
    res = da.deliver_media("cover", "PARENT", str(png), mime="image/png", share_mode="view")
    sent = cap[0]["body"]
    assert sent["action"] == "upload_pdf" and sent["parent_folder_id"] == "PARENT"
    assert sent["mime"] == "image/png"
    assert base64.b64decode(sent["content_b64"]) == raw  # bytes relayed intact
    assert res["file_id"] == "F1" and res["via"] == "n8n_broker"
    assert res["view_shared"] is True and res["download_url"] == "https://dl/F1"


def test_broker_upload_media_missing_source(monkeypatch):
    _broker_env(monkeypatch)
    with pytest.raises(da.ValidationError):
        da.broker_upload_media("x", "P", "/no/such/file.png", mime="image/png")


# --------------------------------------------------------------------------
# share_doc_edit
# --------------------------------------------------------------------------
def test_broker_share_view_and_edit(monkeypatch):
    _broker_env(monkeypatch)
    cap = []
    monkeypatch.setattr(da, "_https", _router_https(cap, {
        "share_doc_edit": {"ok": True, "share_mode": "edit", "permission_id": "PE",
                           "view_url": "https://drive/F"}}))
    res = da.do_share("F", share_mode="edit")
    assert cap[0]["body"] == {"action": "share_doc_edit", "file_id": "F", "share_mode": "edit"}
    assert res["permission_id"] == "PE" and res["via"] == "n8n_broker"
    assert res["view_url"] == "https://drive/F"


def test_broker_share_rejects_unknown_mode(monkeypatch):
    _broker_env(monkeypatch)
    with pytest.raises(da.ValidationError):
        da.broker_share("F", "sideways")


# --------------------------------------------------------------------------
# pull_doc_text
# --------------------------------------------------------------------------
def test_broker_pull_doc_text_byte_exact(monkeypatch):
    _broker_env(monkeypatch)
    body = "The Weight of the Keys\nMy client's own edited line.\n"
    monkeypatch.setattr(da, "_https", _router_https([], {
        "pull_doc_text": {"ok": True, "text": body}}))
    # do_pull_doc_text freezes the exact bytes + sha256 regardless of path.
    res = da.do_pull_doc_text("DOCID")
    assert res["text"] == body
    import hashlib
    assert res["sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert res["byte_len"] == len(body.encode("utf-8"))


def test_broker_pull_doc_text_missing_text_raises(monkeypatch):
    _broker_env(monkeypatch)
    monkeypatch.setattr(da, "_https", _router_https([], {"pull_doc_text": {"ok": True}}))
    monkeypatch.setattr(da, "mint_token", lambda scope=da.FULL_SCOPE: pytest.fail(
        "must not fall through to the local SA in broker mode"))
    with pytest.raises(da.DependencyError):
        da.pull_doc_text("DOCID")


# --------------------------------------------------------------------------
# create_participant_tree (the S0 "on first sight" tree, via drive-tree-provision)
# --------------------------------------------------------------------------
def test_participant_tree_routes_through_broker(monkeypatch):
    _broker_env(monkeypatch)
    cap = []
    monkeypatch.setattr(da, "_https", _router_https(cap, {
        "create_participant_tree": {
            "ok": True, "root_folder_id": "ROOT", "producer_folder_id": "PROD",
            "producer_created": True, "anthology_folder_id": "ANTH",
            "participant_folder_id": "PART"}}))
    monkeypatch.setattr(da, "mint_token", lambda scope=da.FULL_SCOPE: pytest.fail(
        "mint_token (local SA) must not be called in broker mode"))
    # drive-tree-provision.py has a hyphenated filename; load it by path.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dtp_mod", str(SCRIPTS / "drive-tree-provision.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    res = mod.provision("Producer", anthology="Summit", participant="Ada")
    assert cap[0]["body"] == {"action": "create_participant_tree", "producer": "Producer",
                              "anthology": "Summit", "participant": "Ada"}
    assert res["via"] == "n8n_broker"
    assert res["producer"]["id"] == "PROD" and res["participant_folder_id"] == "PART"
    assert res["deepest_folder_id"] == "PART"


# --------------------------------------------------------------------------
# broker-preflight (SHORT E9)
# --------------------------------------------------------------------------
def test_preflight_local_sa_is_clean_pass(monkeypatch):
    monkeypatch.delenv(da.N8N_WEBHOOK_URL_ENV, raising=False)
    monkeypatch.delenv(da.N8N_WEBHOOK_TOKEN_ENV, raising=False)
    pf = da.broker_preflight()
    assert pf["ok"] is True and pf["mode"] == "local_sa" and pf["missing_actions"] == []


def test_preflight_full_capabilities_passes(monkeypatch):
    _broker_env(monkeypatch)
    monkeypatch.setattr(da, "_https", _router_https([], {
        "capabilities": {"ok": True, "implemented_actions": list(da.BROKER_REQUIRED_ACTIONS)}}))
    pf = da.broker_preflight()
    assert pf["ok"] is True and pf["missing_actions"] == []


def test_preflight_short_capabilities_holds_by_name(monkeypatch):
    _broker_env(monkeypatch)
    monkeypatch.setattr(da, "_https", _router_https([], {
        "capabilities": {"ok": True, "implemented_actions": ["create_book_tree"]}}))
    pf = da.broker_preflight()
    assert pf["ok"] is False
    assert set(pf["missing_actions"]) == (set(da.BROKER_DOC_ACTIONS)
                                          | {da.BROKER_PARTICIPANT_ACTION})


def test_preflight_auth_failure_holds(monkeypatch):
    _broker_env(monkeypatch)
    monkeypatch.setattr(da, "_https", _router_https([], {
        "capabilities": {"__status__": 401, "ok": False, "error": "unauthorized"}}))
    pf = da.broker_preflight()
    assert pf["ok"] is False and pf.get("auth_failed") is True
    assert set(pf["missing_actions"]) == set(da.BROKER_REQUIRED_ACTIONS)


def test_preflight_old_broker_probe_fallback(monkeypatch):
    _broker_env(monkeypatch)

    def fake_https(method, host, path, headers, body=None):
        j = json.loads(body.decode("utf-8")) if body else {}
        a = j.get("action")
        if a == "capabilities":
            return 400, json.dumps({"ok": False, "error": "unknown_action"}).encode()
        if a in da.BROKER_DOC_ACTIONS or a == da.BROKER_PARTICIPANT_ACTION:
            return 501, json.dumps({"ok": False, "error": "not_implemented"}).encode()
        # create_book_tree probe is implemented on the old broker
        return 200, json.dumps({"ok": True, "probe": True, "implemented": True}).encode()

    monkeypatch.setattr(da, "_https", fake_https)
    pf = da.broker_preflight()
    assert pf["ok"] is False
    assert "create_book_tree" not in pf["missing_actions"]
    assert set(pf["missing_actions"]) == (set(da.BROKER_DOC_ACTIONS)
                                          | {da.BROKER_PARTICIPANT_ACTION})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
