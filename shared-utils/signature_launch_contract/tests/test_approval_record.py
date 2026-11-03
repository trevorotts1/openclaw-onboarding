"""Tests for approval_record.verify against a real loopback HTTP server (stdlib only)."""
import copy
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import approval_record as ar  # noqa: E402

HASH = "1ef2ba2d" + "0" * 56
FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
RECORD = {
    "schema_version": "1.0", "approval_id": "appr_12345678", "kind": "paid_asset_budget",
    "plan_hash": HASH, "client_identity": "client-a", "source_message_ref": "ghl:msg-1",
    "scope": ["images", "pages"], "cap": {"cap_minor": 5000, "currency": "USD"},
    "expires_at": FUTURE, "revoked": False, "verification_class": "authenticated_platform_record",
}
ASK = dict(kind="paid_asset_budget", plan_hash=HASH, scope=["images"])


@pytest.fixture()
def cc():
    """Loopback Command Center stand-in; serves STATE['record'] for GET /api/launch-approvals/<id>."""
    state = {"record": RECORD, "status": 200, "auth": []}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            state["auth"].append(self.headers.get("Authorization"))
            body = json.dumps(state["record"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["env"] = {"MISSION_CONTROL_URL": "http://127.0.0.1:%d" % srv.server_port, "MC_API_TOKEN": "tok-test"}
    yield state
    srv.shutdown()
    srv.server_close()


def call(cc, **over):
    args = dict(ASK, client_identity="client-a", env=cc["env"])
    args.update(over)
    return ar.verify("appr_12345678", args.pop("kind"), args.pop("plan_hash"), args.pop("scope"), **args)


def mutated(cc, **fields):
    rec = copy.deepcopy(RECORD)
    rec.update(fields)
    cc["record"] = rec


def test_ok_and_bearer_sent(cc):
    out = call(cc)
    assert out["ok"] is True and out["authority"] == "command-center" and out["test_only"] is False
    assert cc["auth"] == ["Bearer tok-test"]


def test_ok_with_cap_within_and_identity_from_company_slug(cc):
    env = dict(cc["env"], COMPANY_SLUG="client-a")
    assert ar.verify("appr_12345678", cap={"cap_minor": 5000, "currency": "USD"}, env=env, **ASK)["ok"]


@pytest.mark.parametrize("field,value,ask,code", [
    ("kind", "page_publication", {}, "APPROVAL-KIND"),
    ("plan_hash", "f" * 64, {}, "APPROVAL-HASH"),
    ("client_identity", "client-b", {}, "APPROVAL-IDENTITY"),
    ("expires_at", (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), {}, "APPROVAL-EXPIRED"),
    ("expires_at", "not-a-date", {}, "APPROVAL-EXPIRED"),
    ("revoked", True, {}, "APPROVAL-REVOKED"),
    ("scope", ["pages"], {}, "APPROVAL-SCOPE"),
    ("cap", {"cap_minor": 100, "currency": "USD"}, {"cap": {"cap_minor": 101, "currency": "USD"}}, "APPROVAL-SCOPE"),
    ("cap", {"cap_minor": 5000, "currency": "EUR"}, {"cap": {"cap_minor": 100, "currency": "USD"}}, "APPROVAL-SCOPE"),
    ("cap", None, {"cap": {"cap_minor": 1, "currency": "USD"}}, "APPROVAL-SCOPE"),
])
def test_each_mismatch_is_a_named_refusal(cc, field, value, ask, code):
    mutated(cc, **{field: value})
    with pytest.raises(ar.ApprovalRefused) as e:
        call(cc, **ask)
    assert e.value.code == code


def test_asked_for_wrong_kind_or_hash_or_identity_or_scope(cc):
    for over, code in [({"kind": "page_publication"}, "APPROVAL-KIND"), ({"plan_hash": "deadbeef"}, "APPROVAL-HASH"),
                       ({"client_identity": "client-b"}, "APPROVAL-IDENTITY"), ({"scope": ["images", "x"]}, "APPROVAL-SCOPE"),
                       ({"client_identity": ""}, "APPROVAL-IDENTITY")]:
        with pytest.raises(ar.ApprovalRefused) as e:
            call(cc, **over)
        assert e.value.code == code


def test_unknown_record_404_and_wrong_id_are_not_from_authority(cc):
    cc["status"] = 404
    with pytest.raises(ar.ApprovalRefused) as e:
        call(cc)
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"
    cc["status"] = 200
    mutated(cc, approval_id="appr_other_id")
    with pytest.raises(ar.ApprovalRefused) as e:
        call(cc)
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"


def test_file_or_dict_as_the_approval_is_refused_on_every_non_test_call(cc, tmp_path):
    f = tmp_path / "approval.json"
    f.write_text(json.dumps(RECORD))
    for forged in (str(f), f, dict(RECORD), "../approval.json", None):
        with pytest.raises(ar.ApprovalRefused) as e:
            ar.verify(forged, env=cc["env"], client_identity="client-a", **ASK)
        assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"
    with pytest.raises(ar.ApprovalRefused) as e:  # a smuggled record= is no approval either
        ar.verify("appr_12345678", record=dict(RECORD), env=cc["env"], client_identity="client-a", **ASK)
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"
    assert cc["auth"] == []  # refused before any network call


@pytest.mark.parametrize("flag", [None, 0, "", [], "yes", 1])
def test_test_only_must_be_exactly_a_bool(cc, flag):
    with pytest.raises(ar.ApprovalRefused) as e:
        ar.verify(dict(RECORD), test_only=flag, client_identity="client-a", env=cc["env"], **ASK)
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"


def test_test_only_accepts_dict_and_file_marked_as_local(cc, tmp_path):
    f = tmp_path / "approval.json"
    f.write_text(json.dumps(RECORD))
    for src in (dict(RECORD), str(f)):
        out = ar.verify(src, test_only=True, client_identity="client-a", env={}, **ASK)
        assert out["ok"] and out["test_only"] is True and out["authority"] == "local-test-record"
    with pytest.raises(ar.ApprovalRefused) as e:  # test mode still enforces every check
        ar.verify(dict(RECORD, revoked=True), test_only=True, client_identity="client-a", env={}, **ASK)
    assert e.value.code == "APPROVAL-REVOKED"
    with pytest.raises(ar.ApprovalRefused) as e:  # and has nothing to verify without a record
        ar.verify("appr_12345678", test_only=True, client_identity="client-a", env={}, **ASK)
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"


def test_command_center_unreachable_or_unconfigured_raises_unavailable(cc):
    with pytest.raises(ar.ApprovalUnavailable):
        call(cc, env={})
    with pytest.raises(ar.ApprovalUnavailable):
        call(cc, env={"MISSION_CONTROL_URL": "http://127.0.0.1:1", "MC_API_TOKEN": "t"})
    with pytest.raises(ar.ApprovalUnavailable):  # token never goes over plain http off-box
        call(cc, env={"MISSION_CONTROL_URL": "http://cc.example.com", "MC_API_TOKEN": "t"})
    cc["status"] = 503
    with pytest.raises(ar.ApprovalUnavailable):
        call(cc)


def test_schema_required_matches_module():
    schema = json.loads((HERE / "approval-record.schema.json").read_text())
    assert tuple(schema["required"]) == ar.REQUIRED
    assert tuple(schema["properties"]["kind"]["enum"]) == ar.KINDS
