"""WF04 compiler-gate tests: intent -> supported definition, proven only.

Covers the WF04 acceptance ids with real assertions on the compiler's own
decisions:

* A04 - a vendor ``valid: false`` and a business-critical note/no-op downgrade
  refuse completion (they never read as success).
* A07 - an ambiguous write is never repeated on another rail.
* IG-WF-09 - the existing identity/dependency/trigger/termination/nonempty
  gates still pass and still fail.
* IG-WF-10 - a read-back mismatch or a missing validator result cannot issue a
  completion certificate.
* IG-WF-11 - the approved private fallback is named and works without a
  browser, and a dead public credential is never "fixed" by one.

Every test is offline: the clients and adapters are recording fakes; no token,
location id or network call is real.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ENGINE = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_identity as wi  # noqa: E402

LOC = "loc_synthetic_wf04"
GOAL = {"id": "g1", "type": "workflow_goal", "name": "Goal",
        "attributes": {"goal": "done"}}
SMS = {"id": "s1", "type": "sms", "name": "SMS one",
       "attributes": {"body": "hello"}}


def _terminated_graph():
    return [
        {"id": "s1", "type": "sms", "name": "SMS one",
         "attributes": {"body": "hello"}, "next": "g1"},
        {"id": "g1", "type": "workflow_goal", "name": "Goal",
         "attributes": {"goal": "done"}, "parentKey": "s1", "next": None},
    ]


# ---------------------------------------------------------------------------
# trigger logic and trigger-filter completeness
# ---------------------------------------------------------------------------


def test_intended_and_is_refused_on_the_public_rail_only():
    wf_def = {
        "name": "And flow",
        "templates": [SMS],
        "requested_trigger": {"type": "tag_added", "relation": "and",
                              "conditions": [{"relation": "and"}]},
    }
    public = wb.compile_gate_findings(wf_def, public_route=True)
    private = wb.compile_gate_findings(wf_def, public_route=False)
    assert "trigger_and_not_preservable_public" in [f["code"] for f in public]
    assert "trigger_and_not_preservable_public" not in [f["code"] for f in private]

    logic = wb.trigger_logic(wf_def["requested_trigger"])
    assert logic["intended"] == "and"
    assert logic["declared"]


def test_an_undeclared_trigger_relation_is_unknown_not_or():
    assert wb.trigger_logic({"type": "tag_added"})["intended"] is None
    assert wb.trigger_logic({"relation": "and", "logic": "or"})["intended"] is None


def test_incomplete_trigger_filter_refuses_the_compile():
    findings = wb.compile_gate_findings(
        {"name": "Filtered", "templates": [SMS],
         "requested_trigger": {"type": "tag_added", "filtersComplete": False,
                               "incompleteFields": ["country"]}},
        public_route=False,
    )
    codes = [f["code"] for f in findings]
    assert codes.count("trigger_filter_incomplete") == 2


def test_incomplete_trigger_filter_keeps_a_proven_current_configuration():
    proven = {"type": "tag_added", "filtersComplete": True,
              "filter": {"op": "equals", "value": "US"}}
    current = {"name": "Flow", "trigger": proven}
    desired = {"name": "Flow",
               "trigger": {"type": "tag_added", "filtersComplete": False}}
    intent = wb.intent_from_definition(current, desired)
    assert intent.set_fields["trigger"] is proven

    with pytest.raises(ContractViolation) as caught:
        wb.intent_from_definition({"name": "Flow"}, desired)
    assert caught.value.rule == "trigger_filter_incomplete_no_proven_configuration"


# ---------------------------------------------------------------------------
# asset references and builder-only enforcement
# ---------------------------------------------------------------------------


def test_asset_references_resolve_before_submit_and_keep_provider_field_names():
    step = {"id": "m1", "type": "email", "name": "Mail",
            "attributes": {"subject": "s"},
            "assetReferences": [
                {"kind": "media", "ref": "cover", "field": "mediaId"},
                {"kind": "template", "ref": "tpl-1"}]}
    resolved, findings = wb.resolve_asset_references(
        [step], lambda kind, ref: {"media": "media-123",
                                   "template": "tpl-999"}[kind])
    assert findings == []
    body = resolved[0]
    assert body["attributes"]["mediaId"] == "media-123"
    assert body["attributes"]["subject"] == "s"
    assert [item["id"] for item in body["resolvedAssetReferences"]] == [
        "media-123", "tpl-999"]
    assert body["resolvedAssetReferences"][1]["kind"] == "template"


def test_unresolved_asset_reference_refuses_the_compile():
    step = {"id": "m1", "type": "email", "name": "Mail",
            "assetReferences": [{"kind": "media", "ref": "missing",
                                 "field": "mediaId"}]}
    resolved, findings = wb.resolve_asset_references([step], None)
    assert [f["code"] for f in findings] == ["asset_reference_unresolved"]
    assert "mediaId" not in resolved[0]["attributes"]
    gate = wb.compile_gate_findings(
        {"name": "Mail", "templates": resolved,
         "asset_reference_findings": findings}, public_route=False)
    assert "asset_reference_unresolved" in [f["code"] for f in gate]


def test_builder_only_required_enforcement_needs_client_side_proof():
    unproven = {"id": "s1", "type": "sms", "name": "SMS",
                "requiredEnforcement": "builder-only",
                "attributes": {"body": "hi"}}
    assert [f["code"] for f in wb.builder_only_findings([unproven])] == [
        "builder_only_proof_missing"]

    partial = {"id": "s1", "type": "sms", "name": "SMS",
               "requiredEnforcement": "builder-only",
               "requiredFields": ["fromNumber", "body"],
               "attributes": {"body": "hi"}}
    assert [f.get("field") for f in wb.builder_only_findings([partial])] == [
        "fromNumber"]

    proven = {"id": "s1", "type": "sms", "name": "SMS",
              "requiredEnforcement": "builder-only",
              "requiredFields": ["fromNumber"],
              "attributes": {"body": "hi", "fromNumber": "+10000000000"}}
    assert wb.builder_only_findings([proven]) == []


# ---------------------------------------------------------------------------
# A04 / IG-WF-10: the validator verdict and the certificate
# ---------------------------------------------------------------------------


def test_vendor_200_valid_false_is_a_failure():
    verdict = wb.validator_verdict({"valid": False, "warnings": [{"code": "x"}]})
    assert verdict["state"] == "invalid"
    certificate = wb.completion_certificate(
        local_graph={"available": True, "verdict": "PASS", "blocking": []},
        validator=verdict,
        readback={"state": "matched"},
    )
    assert certificate["certified"] is False
    assert "vendor_validator:invalid" in certificate["reasons"]


def test_missing_validator_result_and_readback_mismatch_cannot_certify():
    certificate = wb.completion_certificate(
        local_graph={"available": True, "verdict": "PASS", "blocking": []},
        validator=None,
        readback={"state": "mismatch"},
    )
    assert certificate["certified"] is False
    assert "vendor_validator:missing" in certificate["reasons"]
    assert "readback:mismatch" in certificate["reasons"]

    blocked = wb.completion_certificate(
        local_graph={"available": True, "verdict": "FAIL",
                     "blocking": [{"kind": "DANGLING"}]},
        validator={"state": "valid"},
        readback={"state": "matched"},
    )
    assert "local_graph_blocking:DANGLING" in blocked["reasons"]


def test_noop_downgrade_refuses_completion_even_with_a_valid_verdict():
    authored = [SMS, GOAL]
    provider = [{"id": "g1", "type": "workflow_goal", "name": "Goal"}]  # sms lost
    downgrades = wb.noop_downgrades(
        authored, provider,
        [{"code": "action_converted_to_note", "stepId": "s1",
          "message": "unsupported action converted to a note"}])
    assert [d["step_id"] for d in downgrades] == ["s1", "s1"]
    certificate = wb.completion_certificate(
        local_graph={"available": True, "verdict": "PASS", "blocking": []},
        validator={"state": "valid"},
        readback={"state": "matched"},
        downgrades=downgrades,
    )
    assert certificate["certified"] is False
    assert any(reason.startswith("noop_downgrade:") for reason in certificate["reasons"])


def test_logical_ids_map_to_returned_provider_ids():
    authored = [{"id": "logical-a", "type": "sms", "name": "A"},
                {"id": "logical-b", "type": "workflow_goal", "name": "B"}]
    provider = [{"id": "prov-1", "type": "sms", "name": "A"},
                {"id": "prov-2", "type": "workflow_goal", "name": "B"}]
    mapping = wb.logical_to_provider_map(authored, provider)
    assert mapping["map"] == {"logical-a": "prov-1", "logical-b": "prov-2"}
    assert mapping["unmatched"] == []


def test_missing_authored_step_is_unmatched_not_invented():
    mapping = wb.logical_to_provider_map([{"id": "a", "type": "sms", "name": "A"}], [])
    assert mapping["map"] == {}
    assert mapping["unmatched"] == ["a"]


# ---------------------------------------------------------------------------
# IG-WF-09: existing gates still pass and still fail
# ---------------------------------------------------------------------------


def test_existing_gates_still_fail_closed():
    campaign = {"w": {"name": "Bad", "templates": [
        {"id": "a", "type": "not_a_verified_action", "name": "X"}]}}
    assert wb.validate_campaign(campaign)
    assert wb._contract_errors({"w": {"unit_key": "u", "templates": []}}) == [
        "w: compiled workflow has no templates"]

    duplicate = [{"id": "a", "type": "sms", "name": "A"},
                 {"id": "a", "type": "workflow_goal", "name": "B"}]
    assert wi.plan_identity_refusals({"w": {"name": "Dup", "templates": duplicate}})

    unlinked = [{"id": "if1", "type": "if_else", "name": "Cond"}]
    _, unlinked_ids = wb.link_steps(unlinked)
    assert unlinked_ids == ["if1"]

    result = wb.compile_launch_builds(
        {"draft_only": True, "builds": [
            {"id": "b1", "state": "ready", "workflows": []}]})
    assert [r["code"] for r in result.refusals] == [wb.NO_BUILDABLE_WORKFLOW]
    assert result == {}, "a zero-workflow build must not contribute a workflow"


def test_existing_gates_still_pass_a_well_formed_plan():
    assert wb.validate_campaign({"w": {"name": "OK", "templates": [SMS, GOAL]}}) == []
    assert wi.plan_identity_refusals(
        {"w": {"name": "OK", "templates": _terminated_graph()}}) == []
    report = wb.local_graph_verdict(_terminated_graph())
    assert report["available"] is True
    assert report["verdict"] == "PASS"


def test_local_graph_rules_refuse_a_structurally_unsound_graph():
    orphaned = [{"id": "a", "type": "sms", "name": "A"},
                {"id": "b", "type": "workflow_goal", "name": "B",
                 "parentKey": None}]
    report = wb.local_graph_verdict([{**orphaned[0], "parentKey": "ghost"},
                                     orphaned[1]])
    assert report["verdict"] == "FAIL"
    assert report["blocking"]


# ---------------------------------------------------------------------------
# IG-WF-11: the approved private fallback is named and needs no browser
# ---------------------------------------------------------------------------


def test_private_fallback_is_named_and_never_starts_a_browser(monkeypatch):
    route = wb.workflow_route(None, "create")
    assert route.route == wb.WORKFLOW_ROUTE_PRIVATE
    assert "private fallback" in route.reason

    def _boom(*_a, **_k):
        raise AssertionError("a browser must never be selected for a credential gap")

    monkeypatch.setattr(wb, "resolve_browser_executor", _boom)
    for key in ("GHL_API_KEY", "GHL_LOCATION_ID", "GHL_PIT_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    adapter, reason = wb.load_public_v4(LOC)
    assert adapter is None
    assert "public credential unavailable" in reason or "public V4 package unavailable" in reason


# ---------------------------------------------------------------------------
# A07: an ambiguous write never repeats on another rail
# ---------------------------------------------------------------------------


class _FakeCapability:
    enabled = True
    activation_blocked = None


class _RecordingClient:
    """Records every call; only the idempotency listing GET is allowed."""

    def __init__(self):
        self.location_id = LOC
        self.calls = []
        self.call_count = 0

    def request(self, method, path, body=None, workflow_name="", **kw):
        self.calls.append((method, path, body))
        self.call_count += 1
        if method == "GET":
            return []
        raise AssertionError("a write reached the private rail: %s %s" % (method, path))

    def create_location_tag(self, tag, workflow_name=""):
        raise AssertionError("a private tag write fired after the public write")


class _UnknownOutcomeV4:
    def __init__(self):
        self.create_calls = 0

    def capability(self, operation, *, tenant=None):
        return _FakeCapability()

    def create_workflow(self, **_kw):
        self.create_calls += 1
        return SimpleNamespace(status=Status.unknown_outcome,
                               receipt_id="gxo_res_synthetic",
                               evidence={})


class _LandedV4:
    def __init__(self):
        self.reads = 0

    def capability(self, operation, *, tenant=None):
        return _FakeCapability()

    def create_workflow(self, **_kw):
        return SimpleNamespace(status=Status.ok, receipt_id="gxo_res_synthetic",
                               evidence={"workflow_v4": {"workflow_id": "wf_pub_1"}},
                               error=None)

    def read_definition_document(self, *, tenant, workflow_id, attempt=1):
        self.reads += 1
        payload = {"definition": {"actions": list(_terminated_graph())}}
        return (SimpleNamespace(status=Status.ok, receipt_id="gxo_res_read"), payload)


def _campaign():
    return {"w1": {"name": "Synthetic flow",
                   "templates": _terminated_graph()}}


def test_ambiguous_write_is_never_repeated_on_the_private_rail(monkeypatch, tmp_path):
    monkeypatch.setenv("CAF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAF_ALLOWED_LOCATION_IDS", LOC)
    monkeypatch.setenv("CAF_APPROVAL_TOKEN", "test-token")
    monkeypatch.setitem(os.environ, "CAF_INTERNAL_MAX_WORKERS", "1")
    client = _RecordingClient()
    v4 = _UnknownOutcomeV4()
    stats = wb.CampaignBuilder(client, v4=v4).build(_campaign(), "caf-build")
    assert v4.create_calls == 1
    # Only the pre-write idempotency listing GET ran on the private rail.
    assert [call[0] for call in client.calls] == ["GET"]
    joined = " ".join(stats["errors"])
    assert "unknown_outcome" in joined
    assert "private fallback was NOT used" in joined
    assert stats["needs_reconcile"]


def test_landed_public_create_without_a_validator_cannot_certify(monkeypatch, tmp_path):
    monkeypatch.setenv("CAF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAF_ALLOWED_LOCATION_IDS", LOC)
    monkeypatch.setenv("CAF_APPROVAL_TOKEN", "test-token")
    monkeypatch.setitem(os.environ, "CAF_INTERNAL_MAX_WORKERS", "1")
    client = _RecordingClient()
    v4 = _LandedV4()
    stats = wb.CampaignBuilder(client, v4=v4).build(_campaign(), "caf-build")
    assert v4.reads == 1
    # The readback compared the returned graph and matched it.
    assert [call[0] for call in client.calls] == ["GET"]
    certificate = stats["certificate"]["w1"]
    assert certificate["readback"]["state"] == "matched"
    assert certificate["certified"] is False
    assert "vendor_validator:missing" in certificate["reasons"]
    joined = " ".join(stats["errors"])
    assert "no completion certificate was issued" in joined
    assert "private fallback was NOT used" in joined


class _PrivateClient:
    """Minimal private rail: listing GET, create POST, save/sync PUT, readback."""

    def __init__(self):
        self.location_id = LOC
        self.calls = []
        self.call_count = 0
        self.templates = None

    def request(self, method, path, body=None, workflow_name="", **kw):
        self.calls.append((method, path, body))
        self.call_count += 1
        if method == "GET" and path == "/workflow/%s" % LOC:
            return []
        if method == "POST":
            return {"id": "wf_private_1"}
        if method == "PUT":
            data = (body or {}).get("workflowData") or {}
            if isinstance(data.get("templates"), list):
                self.templates = data["templates"]
            return {"ok": True}
        if method == "GET" and path == "/workflow/%s/wf_private_1" % LOC:
            return {"version": 1, "workflowData": {"templates": self.templates or []}}
        raise AssertionError("unexpected call %s %s" % (method, path))

    def create_location_tag(self, tag, workflow_name=""):
        return {"id": "tag_1"}


def test_require_certificate_reports_a_missing_validator_on_the_private_rail(
        monkeypatch, tmp_path):
    monkeypatch.setenv("CAF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAF_ALLOWED_LOCATION_IDS", LOC)
    monkeypatch.setenv("CAF_APPROVAL_TOKEN", "test-token")
    monkeypatch.setitem(os.environ, "CAF_INTERNAL_MAX_WORKERS", "1")
    client = _PrivateClient()
    campaign = {"w1": {"name": "Synthetic private flow",
                       "templates": _terminated_graph(),
                       "require_certificate": True}}
    stats = wb.CampaignBuilder(client).build(campaign, "caf-build")
    certificate = stats["certificate"]["w1"]
    assert certificate["readback"]["state"] == "matched"
    assert certificate["vendor_validator"]["state"] == "missing"
    assert certificate["certified"] is False
    assert any("completion certificate not issued" in err for err in stats["errors"])
