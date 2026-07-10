#!/usr/bin/env python3
"""test_drive_broker.py -- offline contract test for the n8n Drive CREDENTIAL BROKER
path in scripts/drive_adapter.py.

WHY THIS EXISTS
  The fleet Drive model routes the PRIVILEGED per-book folder-tree creation + producer
  editor share through an n8n webhook. Trevor's Google service-account key lives ONLY
  inside n8n; a client box holds NO Google key -- only the webhook URL + a low-privilege
  shared token. This test proves, WITHOUT any network, that:
    1. broker_create_book_tree POSTs the correct action + payload to the webhook, with the
       low-privilege token in the header (over https), and USES the folder ids n8n returns.
    2. provision_book_tree SELECTS the broker when it is configured (the local Google SA is
       never touched), and FALLS BACK to the local SA when it is not (operator's own box).
    3. the per-Doc broker actions are STUBBED (flagged, not faked).
    4. the low-privilege token authenticates the call but is never surfaced in the result.

Network-free: drive_adapter._https (the single HTTPS chokepoint) is monkeypatched, so no
live n8n or Google is touched.

Run: python3 -m pytest 59-anthology-engine/tests/test_drive_broker.py -q
"""
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import drive_adapter as da  # noqa: E402

WEBHOOK_URL = "https://main.blackceoautomations.com/webhook/anthology-drive"
BROKER_TOKEN = "lowPrivBrokerTokenXYZ"  # low-privilege shared webhook token (test value)

# The ids n8n returns after creating the per-client/producer/book tree in Trevor's Drive.
BROKER_RETURN = {
    "ok": True, "action": "create_book_tree", "via": "n8n",
    "root_folder_id": "ROOT_ANTHOLOGY", "client_folder_id": "CLIENT_FOLDER_1",
    "producer_folder_id": "PRODUCER_FOLDER_1", "book_folder_id": "BOOK_FOLDER_1",
    "producer_editor_shared": True,
}


def _broker_env(monkeypatch):
    monkeypatch.setenv(da.N8N_WEBHOOK_URL_ENV, WEBHOOK_URL)
    monkeypatch.setenv(da.N8N_WEBHOOK_TOKEN_ENV, BROKER_TOKEN)


def _no_broker_env(monkeypatch):
    monkeypatch.delenv(da.N8N_WEBHOOK_URL_ENV, raising=False)
    monkeypatch.delenv(da.N8N_WEBHOOK_TOKEN_ENV, raising=False)


def _capture_https(captured, status=200, body=None):
    """A drive_adapter._https stand-in that records the outbound request and returns a
    canned (status, bytes) response -- no socket is opened."""
    payload = BROKER_RETURN if body is None else body

    def fake_https(method, host, path, headers, body=None):
        captured["method"] = method
        captured["host"] = host
        captured["path"] = path
        captured["headers"] = dict(headers)
        captured["body"] = json.loads(body.decode("utf-8")) if body else None
        return status, json.dumps(payload).encode("utf-8")

    return fake_https


def test_broker_create_book_tree_posts_action_and_payload_and_uses_returned_ids(monkeypatch):
    _broker_env(monkeypatch)
    captured = {}
    monkeypatch.setattr(da, "_https", _capture_https(captured))

    res = da.broker_create_book_tree(
        client_key="client-alpha",
        producer_email="producer@example.com",
        book_title="The Weight of the Keys",
        co_author="coauthor@example.com",
    )

    # 1. the correct ACTION + PAYLOAD were POSTed as JSON
    assert captured["method"] == "POST"
    assert captured["host"] == "main.blackceoautomations.com"
    assert captured["path"] == "/webhook/anthology-drive"
    assert captured["body"] == {
        "action": "create_book_tree",
        "client_key": "client-alpha",
        "producer_email": "producer@example.com",
        "book_title": "The Weight of the Keys",
        "co_author": "coauthor@example.com",
    }
    # 2. the low-privilege token authenticates the call in the header, over https
    assert captured["headers"][da.BROKER_TOKEN_HEADER] == BROKER_TOKEN
    assert captured["headers"]["Content-Type"] == "application/json"
    # 3. the folder ids n8n RETURNED are the ones used (not locally invented)
    assert res["book_folder_id"] == "BOOK_FOLDER_1"
    assert res["producer_folder_id"] == "PRODUCER_FOLDER_1"
    assert res["client_folder_id"] == "CLIENT_FOLDER_1"
    assert res["via"] == "n8n_broker"
    # 4. the token is never surfaced in the RESULT the engine consumes/logs
    assert BROKER_TOKEN not in json.dumps(res)


def test_provision_book_tree_selects_broker_when_configured(monkeypatch):
    _broker_env(monkeypatch)
    captured = {}
    monkeypatch.setattr(da, "_https", _capture_https(captured))
    # The local Google SA must NOT be touched in broker mode.
    monkeypatch.setattr(da, "mint_token", lambda scope=da.FULL_SCOPE: pytest.fail(
        "mint_token (local SA) must not be called when the broker is configured"))

    res = da.provision_book_tree("client-alpha", "producer@example.com", "Bk")
    assert res["via"] == "n8n_broker"
    assert res["book_folder_id"] == "BOOK_FOLDER_1"
    assert captured["body"]["action"] == "create_book_tree"


def test_provision_book_tree_falls_back_to_local_sa_when_broker_absent(monkeypatch):
    _no_broker_env(monkeypatch)
    assert da.broker_configured() is False

    # Mock the local-SA primitives so no network is touched; capture the producer share.
    monkeypatch.setattr(da, "mint_token", lambda scope=da.FULL_SCOPE: "FAKE_SA_TOKEN")
    made = {"folders": []}

    def fake_goc(token, parent_id, name):
        made["folders"].append((parent_id, name))
        return {"id": "F-%s" % name, "name": name}, True

    shared = {}

    def fake_share(token, file_id, email, role="writer", notify=False):
        shared["file_id"] = file_id
        shared["email"] = email
        shared["role"] = role
        return {"id": "perm-1", "type": "user", "role": role}

    monkeypatch.setattr(da, "get_or_create_folder", fake_goc)
    monkeypatch.setattr(da, "share_user_role", fake_share)

    res = da.provision_book_tree("client-alpha", "producer@example.com", "MyBook",
                                 root_folder_id="ROOT_SA")
    assert res["via"] == "local_sa"
    # the tree was built top-down under the SA root: client -> producer -> book
    assert made["folders"] == [
        ("ROOT_SA", "client-alpha"),
        ("F-client-alpha", "producer@example.com"),
        ("F-producer@example.com", "MyBook"),
    ]
    assert res["book_folder_id"] == "F-MyBook"
    # producer = editor (writer) on the BOOK folder (Trevor's access model)
    assert shared["file_id"] == "F-MyBook"
    assert shared["role"] == "writer"
    assert shared["email"] == "producer@example.com"


def test_per_doc_broker_actions_are_stubbed_not_faked():
    for action in da.BROKER_STUB_ACTIONS:
        with pytest.raises(da.DependencyError):
            da.broker_stub(action)


def test_broker_rejects_bad_token_and_missing_ids(monkeypatch):
    _broker_env(monkeypatch)
    # 401 from n8n (bad token) surfaces as a DependencyError, not a silent success.
    captured = {}
    monkeypatch.setattr(da, "_https", _capture_https(captured, status=401,
                                                     body={"ok": False, "error": "unauthorized"}))
    with pytest.raises(da.DependencyError):
        da.broker_create_book_tree("c", "p@example.com", "b")

    # A 200 that omits the folder ids also fails loudly (the broker MUST return ids).
    monkeypatch.setattr(da, "_https", _capture_https(captured, status=200,
                                                     body={"ok": True}))
    with pytest.raises(da.DependencyError):
        da.broker_create_book_tree("c", "p@example.com", "b")


def test_broker_requires_https(monkeypatch):
    monkeypatch.setenv(da.N8N_WEBHOOK_URL_ENV, "http://insecure.example/webhook/x")
    monkeypatch.setenv(da.N8N_WEBHOOK_TOKEN_ENV, BROKER_TOKEN)
    with pytest.raises(da.ValidationError):
        da._broker_post("create_book_tree", {})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
