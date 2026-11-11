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


# ---------------------------------------------------------------------------
# Contract 2.0: the Command Center wire shape, the actor/tenant split, and the
# effects a stored approval does NOT authorize (F20 / S1 Pair C).
# ---------------------------------------------------------------------------

# The row src/lib/launch-approvals.ts returns at audit anchor b1f3b64b2: kind
# plan_build, scope as one string, flat cap fields, sha256:-prefixed hash,
# tenant_id and client_identity_ref, and NO schema_version / verification_class.
CC = {
    "approval_id": "8f14e45f-ce2a-4c1e-9a1d-1c0f0e5b7a11",
    "tenant_id": "tenant-acme",
    "client_identity_ref": "owner@acme.example",
    "kind": "plan_build",
    "plan_hash": "sha256:" + HASH,
    "scope": "launch_plan_build, pages",
    "cap_minor": None,
    "currency": None,
    "expires_at": FUTURE,
    "revoked": False,
    "source_message_ref": "telegram:msg-77",
    "active": True,
}


def cc_call(cc, **over):
    """Ask as the plan gate does: canonical kind, bare hash, the PERSON's identity."""
    args = dict(kind="launch_plan_build", plan_hash=HASH, scope=["launch_plan_build"],
                client_identity="owner@acme.example", env=cc["env"])
    args.update(over)
    return ar.verify(args.pop("approval_id", "8f14e45f-ce2a-4c1e-9a1d-1c0f0e5b7a11"),
                     args.pop("kind"), args.pop("plan_hash"), args.pop("scope"), **args)


def test_genuine_command_center_approval_is_accepted(cc):
    cc["record"] = dict(CC)
    out = cc_call(cc)
    assert out["ok"] is True
    assert out["contract_version"] == "2.0"
    assert out["record_version"] == "cc-unversioned"
    assert out["kind"] == "launch_plan_build"
    assert out["kind_wire"] == "plan_build"
    assert out["plan_hash"] == HASH and out["plan_hash_wire"].startswith("sha256:")
    assert out["consenting_actor_ref"] == "owner@acme.example"
    assert out["tenant_ref"] == "tenant-acme"
    assert out["identity_binding"] == "actor"
    assert out["verification_class"] == "authenticated_platform_record"
    assert out["authority"] == "command-center"


def test_command_center_publish_maps_to_page_publication_and_string_scope_splits(cc):
    cc["record"] = dict(CC, kind="publish", scope="images, pages")
    out = cc_call(cc, kind="page_publication", scope=["images"])
    assert out["kind"] == "page_publication" and out["kind_wire"] == "publish"
    assert out["scope"] == ["images, pages", "images", "pages"]


def test_command_center_flat_cap_becomes_nested_cap(cc):
    cc["record"] = dict(CC, kind="paid_asset_budget", scope="paid_asset_budget",
                        cap_minor=5000, currency="USD")
    out = cc_call(cc, kind="paid_asset_budget", scope=["paid_asset_budget"],
                  cap={"cap_minor": 4000, "currency": "USD"})
    assert out["cap"] == {"cap_minor": 5000, "currency": "USD"}


def test_a_tenant_slug_in_the_actor_position_fails_closed(cc):
    """The wrong mapping: a company is never silently accepted as the person."""
    cc["record"] = dict(CC)
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc, client_identity="tenant-acme")
    assert e.value.code == "APPROVAL-IDENTITY-KIND"


def test_tenant_binding_is_available_only_when_declared(cc):
    cc["record"] = dict(CC)
    out = cc_call(cc, client_identity="tenant-acme", identity_kind="tenant")
    assert out["ok"] is True and out["identity_binding"] == "tenant"
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc, client_identity="owner@acme.example", identity_kind="tenant")
    assert e.value.code == "APPROVAL-IDENTITY"


def test_cross_client_and_cross_tenant_are_refused(cc):
    cc["record"] = dict(CC)
    for over in ({"client_identity": "owner@other.example"},
                 {"client_identity": "tenant-other", "identity_kind": "tenant"}):
        with pytest.raises(ar.ApprovalRefused) as e:
            cc_call(cc, **over)
        assert e.value.code == "APPROVAL-IDENTITY"


def test_stale_subject_hash_is_refused(cc):
    cc["record"] = dict(CC)
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc, plan_hash="f" * 64)
    assert e.value.code == "APPROVAL-HASH"


def test_expired_and_revoked_command_center_records_are_refused(cc):
    cc["record"] = dict(CC, expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc)
    assert e.value.code == "APPROVAL-EXPIRED"
    cc["record"] = dict(CC, revoked=True)
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc)
    assert e.value.code == "APPROVAL-REVOKED"


def test_an_unknown_kind_is_an_unknown_meaning(cc):
    cc["record"] = dict(CC, kind="teleport_pages")
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc)
    assert e.value.code == "APPROVAL-KIND-UNKNOWN"


def test_an_unknown_record_version_is_refused(cc):
    cc["record"] = dict(CC, schema_version="3.0")
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc)
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"


def test_conflicting_and_half_caps_are_refused(cc):
    cc["record"] = dict(CC, kind="paid_asset_budget", cap={"cap_minor": 5000, "currency": "USD"},
                        cap_minor=9000)
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc, kind="paid_asset_budget", scope=["paid_asset_budget"])
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"
    cc["record"] = dict(CC, kind="paid_asset_budget", cap_minor=5000, currency=None)
    with pytest.raises(ar.ApprovalRefused) as e:
        cc_call(cc, kind="paid_asset_budget", scope=["paid_asset_budget"])
    assert e.value.code == "APPROVAL-NOT-FROM-AUTHORITY"


def test_a_stored_publish_approval_authorizes_no_other_live_effect():
    publish = {"kind": "publish"}
    assert ar.record_authorizes_effect(publish, "page_publication") is True
    for effect in ar.LEGACY_PUBLISH_DOES_NOT_AUTHORIZE:
        assert ar.record_authorizes_effect(publish, effect) is False, effect
    assert all(not implied for implied in ar.IMPLIED_KINDS.values())


def test_a_test_only_record_can_never_report_itself_authenticated(cc):
    out = ar.verify(dict(CC), test_only=True, client_identity="owner@acme.example", env={},
                    **{"kind": "launch_plan_build", "plan_hash": HASH, "scope": ["launch_plan_build"]})
    assert out["verification_class"] == "local_test_record"
    assert out["authority"] == "local-test-record"


def test_the_command_center_contract_data_matches_this_module():
    data = json.loads((HERE / "command-center-launch-contract.v2.json").read_text())
    assert data["contract"] == "command-center-launch" and data["version"] == 2
    assert data["approval"]["command_center_kind_aliases"] == ar.COMMAND_CENTER_KIND_ALIASES
    assert tuple(data["approval"]["canonical_kinds"]) == ar.KINDS
    assert set(data["run_identity"]["immutable_fields"]) <= set(data["run_identity"]["required_fields"])
    assert data["run_identity"]["rebind_policy"] == "reject"
    assert data["current_revision"]["monotonic"] is True
    assert data["stage_registry"]["known_mismatch"]["status"] == "accepted_with_normalization"


def test_stub_render_is_its_own_kind_that_implies_nothing(cc):
    """WP-02 / issue 38: the owner's permission to run PLACEHOLDER wireframes is a kind of its own."""
    assert "stub_render" in ar.KINDS and ar.canonical_kind("stub_render") == "stub_render"
    assert ar.IMPLIED_KINDS["stub_render"] == frozenset() and "stub_render" not in ar.LIVE_EFFECTS
    mutated(cc, kind="stub_render", scope=["stub_render"])
    assert call(cc, kind="stub_render", scope=["stub_render"])["kind"] == "stub_render"
    with pytest.raises(ar.ApprovalRefused) as e:  # it never stands in for another kind
        call(cc, kind="design_board", scope=["stub_render"])
    assert e.value.code == "APPROVAL-KIND"
    mutated(cc, kind="design_board", scope=["stub_render"])
    with pytest.raises(ar.ApprovalRefused) as e:  # and no other kind stands in for it
        call(cc, kind="stub_render", scope=["stub_render"])
    assert e.value.code == "APPROVAL-KIND"


@pytest.mark.parametrize("kind", ["qc_session", "email_deploy"])
def test_qc_session_and_email_deploy_are_kinds_that_verify_and_imply_nothing(cc, kind):
    """Rulings WP-07-1 / WP-05b-1: Command Center mints these; a record of each verifies, and no other kind stands in."""
    assert kind in ar.KINDS and ar.canonical_kind(kind) == kind
    assert ar.IMPLIED_KINDS[kind] == frozenset() and kind not in ar.LIVE_EFFECTS
    schema = json.loads((HERE / "approval-record.schema.json").read_text())
    assert kind in json.dumps(schema)
    data = json.loads((HERE / "command-center-launch-contract.v2.json").read_text())
    assert kind in data["approval"]["canonical_kinds"]
    mutated(cc, kind=kind, scope=[kind])
    assert call(cc, kind=kind, scope=[kind])["kind"] == kind
    with pytest.raises(ar.ApprovalRefused) as e:
        call(cc, kind="design_board", scope=[kind])
    assert e.value.code == "APPROVAL-KIND"


def test_an_unknown_kind_is_still_refused(cc):
    mutated(cc, kind="not_a_real_kind", scope=["not_a_real_kind"])
    with pytest.raises(ar.ApprovalRefused) as e:
        call(cc, kind="not_a_real_kind", scope=["not_a_real_kind"])
    assert e.value.code == "APPROVAL-KIND-UNKNOWN"
