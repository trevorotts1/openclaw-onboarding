#!/usr/bin/env python3
"""test_ghl_split_variant.py — the native split-test VARIANT operation.

Four properties, in the order they matter:

  A. With a valid captured fixture the plan builds a create-variant request
     and read-back assertions, every value traceable to the capture.
  B. Traffic stays OFF. Mutating the capture to ``traffic_permitted=True``
     must fail; so must any payload that carries a forbidden traffic field or
     a traffic value other than the captured default.
  C. Without a capture the module stays DISABLED and raises CaptureRequired.
     It is not "disabled by construction" — it is disabled by a gate, and the
     gate is reachable, which is what these tests prove.
  D. Two-run idempotency: the second run REUSEs the variant it created.

No network. No GHL. Every id here is fake and every fixture is marked
``_fixture`` so it can never be mistaken for evidence.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_split_variant as sv  # noqa: E402

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "split-variant"
           / "captured-selectors.offline.json")
MODULE = Path(_TOOLS) / "ghl_split_variant.py"
CHECKLIST_SH = Path(_TOOLS) / "ghl_split_variant_capture_checklist.sh"


@pytest.fixture()
def capture():
    """The offline capture, loaded the same way a caller would."""
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def req(capture):
    return sv.VariantRequest(location_id=capture["location_id"],
                             funnel_id="funnel-offline",
                             step_id=capture["step_id"],
                             name="B", slug="b")


@pytest.fixture()
def readback(capture):
    """A read-back payload that satisfies every captured assertion."""
    payload = {k: "x" for k in capture["readback_keys"]}
    payload[capture["variant_relation"]] = capture["control_id_before"]
    payload[capture["traffic_field"]] = capture["traffic_default"]
    return payload


# ── A. The operation builds a real request from the capture ─────────────────

class TestValidCaptureBuildsOperation:
    def test_offline_fixture_passes_the_full_schema(self, capture):
        assert sv.validate_capture(capture) == []
        assert sv.CAPTURE_SCHEMA.keys() == set(sv.REQUIRED_CAPTURE_FIELDS)

    def test_request_uses_every_selector_from_the_capture(self, capture, req):
        body = sv.build_variant_request(req, capture)
        step = body["step"]
        assert body["locationId"] == capture["location_id"]
        assert body["funnelId"] == req.funnel_id
        assert step["id"] == capture["variant_id"]
        assert step["name"] == req.name
        assert step["url"] == req.slug
        # the relation is emitted under the CAPTURED name, pointing at the
        # CAPTURED control id — nothing here was guessed
        assert step[capture["variant_relation"]] == capture["control_id_before"]

    def test_no_selector_is_hardcoded(self, capture, req):
        """Rename every captured selector; the body must follow the capture."""
        renamed = dict(capture,
                       variant_id="step-renamed-v",
                       variant_relation="renamedLink",
                       traffic_field="renamedTraffic")
        body = sv.build_variant_request(req, renamed)
        assert body["step"]["id"] == "step-renamed-v"
        assert body["step"]["renamedLink"] == renamed["control_id_before"]
        assert "renamedTraffic" in body["step"]
        assert capture["variant_relation"] not in body["step"]

    def test_readback_assertions_come_from_the_capture(self, capture):
        a = sv.readback_assertions(capture)
        assert a["must_contain_keys"] == list(capture["readback_keys"])
        assert a["variant_id"] == capture["variant_id"]
        assert a["relation_field"] == capture["variant_relation"]
        assert a["relation_value"] == capture["control_id_before"]
        assert a["traffic_must_equal"] == capture["traffic_default"]
        assert a["control_identity_stable"] is True

    def test_a_matching_readback_passes(self, capture, readback):
        ok, problems = sv.readback_passes(capture, readback)
        assert ok, problems

    def test_readback_that_lost_the_relation_fails(self, capture, readback):
        readback[capture["variant_relation"]] = "some-other-control"
        ok, problems = sv.readback_passes(capture, readback)
        assert not ok
        assert any("not linked" in p for p in problems)

    def test_reviewed_plan_carries_request_and_readback_assertions(
            self, capture, req):
        plan = sv.plan_variant(req, capture, reviewed=True)
        assert plan.enabled is True
        assert plan.state == sv.ENABLED_FOR_REVIEW
        assert plan.request["step"]["id"] == capture["variant_id"]
        assert plan.readback_assertions["variant_id"] == capture["variant_id"]
        assert plan.as_dict()["readback_assertions"] is not None

    def test_plan_without_review_is_still_disabled(self, capture, req):
        plan = sv.plan_variant(req, capture, reviewed=False)
        assert plan.enabled is False
        assert plan.request is None

    def test_location_and_step_must_match_the_capture(self, capture):
        wrong_loc = sv.VariantRequest(location_id="other-location",
                                      funnel_id="f", step_id=capture["step_id"],
                                      name="B", slug="b")
        with pytest.raises(sv.VariantRefused, match="location mismatch"):
            sv.build_variant_request(wrong_loc, capture)
        wrong_step = sv.VariantRequest(location_id=capture["location_id"],
                                       funnel_id="f", step_id="other-step",
                                       name="B", slug="b")
        with pytest.raises(sv.VariantRefused, match="step mismatch"):
            sv.build_variant_request(wrong_step, capture)


# ── B. Traffic is never activated ──────────────────────────────────────────

class TestTrafficStaysOff:
    def test_built_body_writes_only_the_captured_default(self, capture, req):
        step = sv.build_variant_request(req, capture)["step"]
        assert step[capture["traffic_field"]] == capture["traffic_default"]

    def test_flipping_traffic_permitted_true_is_refused(self, capture, req):
        """The mutation this whole capability exists to catch."""
        armed = dict(capture, traffic_permitted=True)
        with pytest.raises(sv.TrafficActivationRefused):
            sv.build_variant_request(req, armed)
        with pytest.raises(sv.TrafficActivationRefused):
            sv.readback_assertions(armed)
        # and it can never enable the capability either
        assert sv.capability_state(armed, reviewed=True)["enabled"] is False
        assert sv.validate_capture(armed) != []

    def test_traffic_permitted_must_be_literally_false(self, capture):
        for sneaky in (True, 1, "false", "no", None, [], {}):
            bad = dict(capture, traffic_permitted=sneaky)
            assert sv.validate_capture(bad), f"{sneaky!r} must not validate"

    def test_forbidden_traffic_field_in_the_payload_is_refused(
            self, capture, req):
        body = sv.build_variant_request(req, capture)
        for key in sv.FORBIDDEN_UNTIL_CAPTURE:
            tampered = json.loads(json.dumps(body))
            tampered["step"][key] = 50
            with pytest.raises(sv.TrafficActivationRefused, match=key):
                sv.assert_no_traffic_activation(tampered, capture)

    def test_a_nested_traffic_field_is_still_refused(self, capture, req):
        body = sv.build_variant_request(req, capture)
        body["step"]["settings"] = {"traffic_weight": 50}
        with pytest.raises(sv.TrafficActivationRefused, match="traffic_weight"):
            sv.assert_no_traffic_activation(body, capture)

    def test_traffic_value_other_than_default_is_refused(self, capture, req):
        body = sv.build_variant_request(req, capture)
        body["step"][capture["traffic_field"]] = 50
        with pytest.raises(sv.TrafficActivationRefused,
                           match="captured default"):
            sv.assert_no_traffic_activation(body, capture)

    def test_readback_that_moved_traffic_fails(self, capture, readback):
        readback[capture["traffic_field"]] = "activated"
        ok, problems = sv.readback_passes(capture, readback)
        assert not ok
        assert any("traffic must stay" in p for p in problems)

    def test_traffic_field_may_not_be_a_forbidden_name(self, capture):
        bad = dict(capture, traffic_field="traffic_weight")
        assert sv.validate_capture(bad)


# ── C. No capture → disabled, and CaptureRequired ──────────────────────────

class TestCaptureGate:
    def test_no_capture_means_pending_and_disabled(self):
        state = sv.capability_state()
        assert state["state"] == sv.PENDING_LIVE_SELECTOR_CAPTURE
        assert state["enabled"] is False
        assert sorted(state["missing_capture_fields"]) == \
            sorted(sv.REQUIRED_CAPTURE_FIELDS)

    def test_operation_raises_capture_required_without_a_capture(self, req):
        with pytest.raises(sv.CaptureRequired):
            sv.build_variant_request(req, None)
        with pytest.raises(sv.CaptureRequired):
            sv.readback_assertions(None)
        with pytest.raises(sv.CaptureRequired):
            sv.reuse_decision(None, [], req)

    def test_plan_without_a_capture_is_a_refusal_not_a_noop(self, req):
        plan = sv.plan_variant(req, None, reviewed=True)
        assert plan.enabled is False
        assert plan.request is None
        assert plan.state == sv.PENDING_LIVE_SELECTOR_CAPTURE
        assert sorted(plan.missing_capture_fields) == \
            sorted(sv.REQUIRED_CAPTURE_FIELDS)

    def test_each_missing_field_keeps_it_disabled(self, capture, req):
        for field in sv.REQUIRED_CAPTURE_FIELDS:
            partial = {k: v for k, v in capture.items() if k != field}
            assert sv.capability_state(partial)["state"] == \
                sv.PENDING_LIVE_SELECTOR_CAPTURE
            with pytest.raises(sv.CaptureRequired):
                sv.build_variant_request(req, partial)

    def test_plausible_but_malformed_capture_cannot_enable(self, capture, req):
        """Right SHAPE, wrong VALUES — must stay disabled, not round up."""
        malformed = dict(capture, capture_evidence="I-saw-it-happen")
        state = sv.capability_state(malformed, reviewed=True)
        assert state["enabled"] is False
        assert state["schema_valid"] is False
        assert any("capture_evidence" in p for p in state["schema_problems"])
        with pytest.raises(sv.CaptureInvalid):
            sv.build_variant_request(req, malformed)

    def test_synthetic_fixture_is_never_evidence(self, capture):
        assert sv.is_synthetic_capture(capture) is True
        with pytest.raises(sv.CaptureRequired, match="synthetic"):
            sv.load_capture(str(FIXTURE))
        assert sv.is_synthetic_capture(sv.SYNTHETIC_COMPLETE_CAPTURE) is True

    def test_a_capture_without_the_fixture_marker_is_not_synthetic(self,
                                                                  capture):
        assert sv.is_synthetic_capture(
            {k: v for k, v in capture.items() if k != "_fixture"}) is False

    def test_capture_checklist_covers_every_required_field(self):
        names = [f["name"] for f in sv.capture_checklist()["fields"]]
        assert names == list(sv.REQUIRED_CAPTURE_FIELDS)
        for field in sv.capture_checklist()["fields"]:
            assert field["required"] is True
            assert field["rule"].strip()

    def test_unreadable_capture_path_is_capture_required(self, tmp_path):
        with pytest.raises(sv.CaptureRequired):
            sv.load_capture(str(tmp_path / "does-not-exist.json"))


# ── D. Two-run idempotency ────────────────────────────────────────────────

class TestReuseShape:
    def test_first_run_creates(self, capture, req):
        decision = sv.reuse_decision(capture, [], req)
        assert decision["action"] == "CREATE"
        assert decision["variant_id"] is None

    def test_second_run_reuses_the_same_variant(self, capture, req):
        created = {"id": capture["variant_id"], "name": req.name,
                   "url": req.slug,
                   capture["variant_relation"]: capture["control_id_before"]}
        first = sv.reuse_decision(capture, [], req)
        second = sv.reuse_decision(capture, [created], req)
        assert first["action"] == "CREATE"
        assert second["action"] == "REUSE"
        assert second["variant_id"] == capture["variant_id"]
        assert second["matched_on"]["relation_field"] == \
            capture["variant_relation"]

    def test_a_variant_linked_to_another_control_is_not_reused(
            self, capture, req):
        other = {"id": "v-other", "name": req.name, "url": req.slug,
                 capture["variant_relation"]: "a-different-control"}
        assert sv.reuse_decision(capture, [other], req)["action"] == "CREATE"

    def test_a_different_name_is_not_reused(self, capture, req):
        other = {"id": "v-other", "name": "C", "url": req.slug,
                 capture["variant_relation"]: capture["control_id_before"]}
        assert sv.reuse_decision(capture, [other], req)["action"] == "CREATE"

    def test_a_different_slug_is_not_reused(self, capture, req):
        other = {"id": "v-other", "name": req.name, "url": "z",
                 capture["variant_relation"]: capture["control_id_before"]}
        assert sv.reuse_decision(capture, [other], req)["action"] == "CREATE"

    def test_matching_is_never_by_list_position(self, capture, req):
        """A non-matching row at index 0 must not be reused just for being first."""
        rows = [{"id": "v-decoy", "name": "X", "url": "x",
                 capture["variant_relation"]: "elsewhere"}]
        assert sv.reuse_decision(capture, rows, req)["action"] == "CREATE"


# ── CLI / checklist script contracts ──────────────────────────────────────

class TestCliSurface:
    def _run(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-I", str(MODULE), *args],
                              capture_output=True, text=True, env=env)

    def test_selftest_passes(self):
        proc = self._run("--selftest")
        assert proc.returncode == 0, proc.stderr
        assert "PASS" in proc.stdout

    def test_state_defaults_to_pending_and_disabled(self):
        proc = self._run("--state")
        assert proc.returncode == 0, proc.stderr
        state = json.loads(proc.stdout)
        assert state["enabled"] is False
        assert state["state"] == sv.PENDING_LIVE_SELECTOR_CAPTURE

    def test_cli_refuses_a_synthetic_capture_cleanly(self):
        proc = self._run("--state", "--capture", str(FIXTURE))
        assert proc.returncode == 1
        assert "REFUSE" in proc.stderr
        assert "Traceback" not in proc.stderr

    def test_checklist_script_prints_the_schema(self):
        proc = subprocess.run([str(CHECKLIST_SH), "checklist"],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        fields = [f["name"] for f in json.loads(proc.stdout)["fields"]]
        assert fields == list(sv.REQUIRED_CAPTURE_FIELDS)

    def test_checklist_script_state_reports_pending_with_rc_3(self):
        proc = subprocess.run([str(CHECKLIST_SH), "state"],
                              capture_output=True, text=True)
        assert proc.returncode == 3, proc.stderr
        assert "enabled=False" in proc.stdout

    def test_checklist_script_rejects_the_synthetic_fixture(self):
        proc = subprocess.run([str(CHECKLIST_SH), "validate", str(FIXTURE)],
                              capture_output=True, text=True)
        assert proc.returncode == 1
        assert "INVALID" in proc.stderr


# ── The invariant that must survive any future refactor ───────────────────

def test_default_capability_is_still_disabled_at_import():
    """Guard against a future edit that 'helpfully' enables the capability.

    No capture ships in the tree (the only fixture is marked _fixture and is
    refused by load_capture), so the honest default must be DISABLED.
    """
    state = sv.capability_state()
    assert state["enabled"] is False
    assert state["state"] == sv.PENDING_LIVE_SELECTOR_CAPTURE
