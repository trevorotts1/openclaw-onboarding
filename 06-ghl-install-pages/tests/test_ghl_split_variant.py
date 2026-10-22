#!/usr/bin/env python3
"""test_ghl_split_variant.py — the native split-test VARIANT operation.

Five properties, in the order they matter:

  A. With a capture BOUND to a real artifact (bytes on disk, hashed from the
     file, signed by an independent receipt) the plan builds a create-variant
     request and read-back assertions, every value traceable to the capture.
  B. Traffic stays OFF. Mutating the capture to ``traffic_permitted=True``
     must fail; so must any payload that carries a forbidden traffic field or
     a traffic value other than the captured default.
  C. BINDING IS NOT SHAPE. A capture carrying all 11 selector fields — even
     with the synthetic marker stripped — is refused unless its artifact
     exists AND hashes to the declared digest AND an independent receipt signs
     that digest. Self-reported metadata alone never enables anything.
  D. Without a capture the module stays DISABLED and raises CaptureRequired.
  E. Two-run idempotency: the second run REUSEs the variant it created.

No network. No GHL. Every id here is fake, and the artifact is generated
locally at test time — proving the STRUCTURE of the contract, never making a
claim about GoHighLevel.
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

import ghl_evidence  # noqa: E402
import ghl_split_variant as sv  # noqa: E402

MODULE = Path(_TOOLS) / "ghl_split_variant.py"
CHECKLIST_SH = Path(_TOOLS) / "ghl_split_variant_capture_checklist.sh"

REV = "b" * 40
COMPANY = "co-offline-0001"
CAPTURED_AT = "2026-10-22T12:00:00Z"
ARTIFACT_BYTES = b"<html><body>offline capture artifact</body></html>\n"


def _selectors(**overrides):
    """The 11 selector results, all fake, with optional overrides.

    No ``_fixture`` marker: these tests need to prove that a capture WITHOUT
    the marker still fails when it is unbound. That is the attack the marker
    check used to miss.
    """
    sel = {
        "location_id": "loc-offline-0001",
        "step_id": "step-offline-control",
        "control_id_before": "step-offline-control",
        "control_id_after": "step-offline-control",
        "variant_id": "step-offline-variant",
        "variant_relation": "variationOf",
        "traffic_field": "control_traffic",
        "traffic_permitted": False,
        "traffic_default": 100,
        "readback_keys": ["id", "name", "url", "variationOf", "control_traffic"],
        "capture_evidence": "fixture://offline sha256:" + "0" * 64,
    }
    sel.update(overrides)
    return sel


@pytest.fixture()
def bundle(tmp_path):
    """A BOUND capture built in a private temp dir: artifact + capture +
    receipt. This is what "captured" means now."""
    return sv.write_capture_bundle(
        str(tmp_path), _selectors(), ARTIFACT_BYTES,
        company_id=COMPANY,
        captured_at=CAPTURED_AT,
        session_id="sess-offline-1",
        candidate_revision=REV,
        reviewer="offline-reviewer",
        reviewed_at="2026-10-22T12:05:00Z",
    )


@pytest.fixture()
def capture(bundle):
    """The bound capture, loaded the same way a caller must."""
    return sv.load_capture(bundle["capture_path"])


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
    def test_a_bound_capture_passes_the_full_schema(self, capture, bundle):
        assert sv.validate_capture(
            capture, capture_path=bundle["capture_path"]) == []
        assert sv.CAPTURE_SCHEMA.keys() == set(sv.REQUIRED_CAPTURE_FIELDS)

    def test_request_uses_every_selector_from_the_capture(self, capture, req,
                                                          bundle):
        body = sv.build_variant_request(req, capture,
                                        capture_path=bundle["capture_path"])
        step = body["step"]
        assert body["locationId"] == capture["location_id"]
        assert body["funnelId"] == req.funnel_id
        assert step["id"] == capture["variant_id"]
        assert step["name"] == req.name
        assert step["url"] == req.slug
        # the relation is emitted under the CAPTURED name, pointing at the
        # CAPTURED control id — nothing here was guessed
        assert step[capture["variant_relation"]] == capture["control_id_before"]

    def test_no_selector_is_hardcoded(self, capture, req, bundle):
        """Re-CAPTURE with every selector renamed; the body must follow it."""
        renamed_sel = {k: capture[k] for k in sv.SELECTOR_FIELDS}
        renamed_sel.update(variant_id="step-renamed-v",
                           variant_relation="renamedLink",
                           traffic_field="renamedTraffic")
        renamed_bundle = sv.write_capture_bundle(
            str(Path(bundle["capture_path"]).parent), renamed_sel,
            ARTIFACT_BYTES,
            company_id=COMPANY, captured_at=CAPTURED_AT,
            session_id="sess-offline-3", candidate_revision=REV,
            reviewer="offline-reviewer",
            artifact_name="a3.bin", capture_name="c3.json",
            receipt_name="r3.json")
        renamed = sv.load_capture(renamed_bundle["capture_path"])
        body = sv.build_variant_request(req, renamed,
                                        capture_path=renamed_bundle["capture_path"])
        assert body["step"]["id"] == "step-renamed-v"
        assert body["step"]["renamedLink"] == renamed["control_id_before"]
        assert "renamedTraffic" in body["step"]
        assert capture["variant_relation"] not in body["step"]

    def test_readback_assertions_come_from_the_capture(self, capture, bundle):
        a = sv.readback_assertions(capture,
                                   capture_path=bundle["capture_path"])
        assert a["must_contain_keys"] == list(capture["readback_keys"])
        assert a["variant_id"] == capture["variant_id"]
        assert a["relation_field"] == capture["variant_relation"]
        assert a["relation_value"] == capture["control_id_before"]
        assert a["traffic_must_equal"] == capture["traffic_default"]
        assert a["control_identity_stable"] is True

    def test_a_matching_readback_passes(self, capture, readback, bundle):
        ok, problems = sv.readback_passes(
            capture, readback, capture_path=bundle["capture_path"])
        assert ok, problems

    def test_readback_that_lost_the_relation_fails(self, capture, readback,
                                                   bundle):
        readback[capture["variant_relation"]] = "some-other-control"
        ok, problems = sv.readback_passes(
            capture, readback, capture_path=bundle["capture_path"])
        assert not ok
        assert any("not linked" in p for p in problems)

    def test_reviewed_plan_carries_request_and_readback_assertions(
            self, capture, req, bundle):
        plan = sv.plan_variant(req, capture, reviewed=True,
                               capture_path=bundle["capture_path"])
        assert plan.enabled is True
        assert plan.state == sv.ENABLED_FOR_REVIEW
        assert plan.request["step"]["id"] == capture["variant_id"]
        assert plan.readback_assertions["variant_id"] == capture["variant_id"]
        assert plan.as_dict()["readback_assertions"] is not None

    def test_plan_without_review_is_still_disabled(self, capture, req, bundle):
        plan = sv.plan_variant(req, capture, reviewed=False,
                               capture_path=bundle["capture_path"])
        assert plan.enabled is False
        assert plan.request is None

    def test_location_and_step_must_match_the_capture(self, capture, bundle):
        wrong_loc = sv.VariantRequest(location_id="other-location",
                                      funnel_id="f", step_id=capture["step_id"],
                                      name="B", slug="b")
        with pytest.raises(sv.VariantRefused, match="location mismatch"):
            sv.build_variant_request(wrong_loc, capture,
                                     capture_path=bundle["capture_path"])
        wrong_step = sv.VariantRequest(location_id=capture["location_id"],
                                       funnel_id="f", step_id="other-step",
                                       name="B", slug="b")
        with pytest.raises(sv.VariantRefused, match="step mismatch"):
            sv.build_variant_request(wrong_step, capture,
                                     capture_path=bundle["capture_path"])


# ── B. Traffic is never activated ──────────────────────────────────────────

class TestTrafficStaysOff:
    def test_built_body_writes_only_the_captured_default(self, capture, req,
                                                         bundle):
        step = sv.build_variant_request(
            req, capture, capture_path=bundle["capture_path"])["step"]
        assert step[capture["traffic_field"]] == capture["traffic_default"]

    def test_flipping_traffic_permitted_true_is_refused(self, capture, req,
                                                        bundle):
        """The mutation this whole capability exists to catch."""
        armed = dict(capture, traffic_permitted=True)
        with pytest.raises(sv.TrafficActivationRefused):
            sv.build_variant_request(req, armed,
                                     capture_path=bundle["capture_path"])
        with pytest.raises(sv.TrafficActivationRefused):
            sv.readback_assertions(armed,
                                   capture_path=bundle["capture_path"])
        # and it can never enable the capability either
        assert sv.capability_state(armed, reviewed=True,
                                   capture_path=bundle["capture_path"]
                                   )["enabled"] is False
        assert sv.validate_capture(armed, capture_path=bundle["capture_path"])

    def test_traffic_permitted_must_be_literally_false(self, capture):
        for sneaky in (True, 1, "false", "no", None, [], {}):
            bad = dict(capture, traffic_permitted=sneaky)
            assert sv.validate_capture(bad), f"{sneaky!r} must not validate"

    def test_forbidden_traffic_field_in_the_payload_is_refused(
            self, capture, req, bundle):
        body = sv.build_variant_request(
            req, capture, capture_path=bundle["capture_path"])
        for key in sv.FORBIDDEN_UNTIL_CAPTURE:
            tampered = json.loads(json.dumps(body))
            tampered["step"][key] = 50
            with pytest.raises(sv.TrafficActivationRefused, match=key):
                sv.assert_no_traffic_activation(tampered, capture)

    def test_a_nested_traffic_field_is_still_refused(self, capture, req,
                                                     bundle):
        body = sv.build_variant_request(
            req, capture, capture_path=bundle["capture_path"])
        body["step"]["settings"] = {"traffic_weight": 50}
        with pytest.raises(sv.TrafficActivationRefused, match="traffic_weight"):
            sv.assert_no_traffic_activation(body, capture)

    def test_traffic_value_other_than_default_is_refused(self, capture, req,
                                                         bundle):
        body = sv.build_variant_request(
            req, capture, capture_path=bundle["capture_path"])
        body["step"][capture["traffic_field"]] = 50
        with pytest.raises(sv.TrafficActivationRefused,
                           match="captured default"):
            sv.assert_no_traffic_activation(body, capture)

    def test_readback_that_moved_traffic_fails(self, capture, readback, bundle):
        readback[capture["traffic_field"]] = "activated"
        ok, problems = sv.readback_passes(
            capture, readback, capture_path=bundle["capture_path"])
        assert not ok
        assert any("traffic must stay" in p for p in problems)

    def test_traffic_field_may_not_be_a_forbidden_name(self, capture):
        bad = dict(capture, traffic_field="traffic_weight")
        assert sv.validate_capture(bad)


# ── C. BINDING: shape is not evidence ──────────────────────────────────────

class TestCaptureIsBoundToItsArtifact:
    """Every test here is an ATTACK that must FAIL.

    The de-markered-fixture attack is the headline: take a capture that has
    all 11 selector fields, strip the ``_fixture`` marker, and hand it to
    ``load_capture``. Before the hardening that passed. It must not now,
    because there is no artifact behind it.
    """

    def test_de_markered_fixture_is_refused_for_want_of_an_artifact(
            self, tmp_path):
        """The exact attack Trevor named: shape + no marker, no artifact."""
        fake = _selectors()  # no _fixture key anywhere
        fake.update({
            "company_id": COMPANY, "captured_at": CAPTURED_AT,
            "session_id": "sess-attacker", "candidate_revision": REV,
            "capture_artifact": "never-written.png",
            "capture_artifact_sha256": "0" * 64,
            "selector_results_sha256": sv.selector_results_digest(fake),
            "review_receipt": "",
        })
        path = tmp_path / "capture.json"
        path.write_text(json.dumps(fake), encoding="utf-8")

        assert sv.is_synthetic_capture(fake) is False  # marker gone
        problems = sv.validate_capture(fake, capture_path=str(path))
        assert problems, "an artifact-less capture must NOT validate"
        assert any("capture_artifact" in p for p in problems)
        with pytest.raises(sv.CaptureInvalid):
            sv.load_capture(str(path))

    def test_a_selector_only_dict_can_never_enable(self):
        """Right shape, every field present, no path: still not evidence."""
        sel = _selectors()
        state = sv.capability_state(sel, reviewed=True)
        assert state["enabled"] is False
        assert state["bindings_valid"] is False

    def test_artifact_absent_from_disk_is_refused(self, capture, bundle):
        gone = dict(capture, capture_artifact="no-such-file.png")
        problems = sv.validate_bindings(gone, bundle["capture_path"])
        assert any("capture_artifact" in p for p in problems)

    def test_artifact_hash_mismatch_is_refused(self, capture, bundle, tmp_path):
        """Rewrite the artifact bytes; the declared digest no longer holds."""
        tampered = tmp_path / "tampered.bin"
        tampered.write_bytes(b"totally different bytes")
        problems = sv.validate_bindings(
            dict(capture, capture_artifact=str(tampered)),
            bundle["capture_path"])
        assert any("hashes to" in p for p in problems)

    def test_selector_edited_after_capture_is_refused(self, capture, bundle):
        """Change one selector; its digest no longer matches the signed one."""
        moved = dict(capture, variant_relation="someOtherRelation")
        problems = sv.validate_bindings(moved, bundle["capture_path"])
        assert any("selector_results_sha256" in p for p in problems)

    def test_review_receipt_missing_is_refused(self, capture, bundle):
        assert sv.validate_bindings(
            dict(capture, review_receipt=""), bundle["capture_path"])

    def test_review_receipt_that_signs_another_artifact_is_refused(
            self, capture, bundle, tmp_path):
        """A reviewer who signed DIFFERENT bytes has not approved these."""
        other = tmp_path / "receipt-other.json"
        other.write_text(json.dumps({
            "reviewer": "offline-reviewer",
            "reviewed_at": "2026-10-22T12:05:00Z",
            "artifact_sha256": "f" * 64,
            "candidate_revision": REV,
            "selector_results_sha256": capture["selector_results_sha256"],
            "verdict": "approved",
        }), encoding="utf-8")
        problems = sv.validate_bindings(
            dict(capture, review_receipt=str(other)), bundle["capture_path"])
        assert any("did not approve THESE bytes" in p for p in problems)

    def test_review_receipt_verdict_must_be_approved(self, capture, bundle,
                                                     tmp_path):
        r = tmp_path / "receipt-rejected.json"
        r.write_text(json.dumps({
            "reviewer": "offline-reviewer",
            "reviewed_at": "2026-10-22T12:05:00Z",
            "artifact_sha256": capture["capture_artifact_sha256"],
            "candidate_revision": REV,
            "selector_results_sha256": capture["selector_results_sha256"],
            "verdict": "rejected",
        }), encoding="utf-8")
        problems = sv.validate_bindings(
            dict(capture, review_receipt=str(r)), bundle["capture_path"])
        assert any("verdict" in p for p in problems)

    def test_review_receipt_for_another_revision_is_refused(self, capture,
                                                            bundle, tmp_path):
        r = tmp_path / "receipt-old-rev.json"
        r.write_text(json.dumps({
            "reviewer": "offline-reviewer",
            "reviewed_at": "2026-10-22T12:05:00Z",
            "artifact_sha256": capture["capture_artifact_sha256"],
            "candidate_revision": "c" * 40,
            "selector_results_sha256": capture["selector_results_sha256"],
            "verdict": "approved",
        }), encoding="utf-8")
        problems = sv.validate_bindings(
            dict(capture, review_receipt=str(r)), bundle["capture_path"])
        assert any("candidate_revision" in p for p in problems)

    def test_review_must_be_independent_of_the_capture(self, capture, bundle,
                                                      tmp_path):
        r = tmp_path / "receipt-self.json"
        r.write_text(json.dumps({
            "reviewer": capture["session_id"],   # same session captured it
            "reviewed_at": "2026-10-22T12:05:00Z",
            "artifact_sha256": capture["capture_artifact_sha256"],
            "candidate_revision": REV,
            "selector_results_sha256": capture["selector_results_sha256"],
            "verdict": "approved",
        }), encoding="utf-8")
        problems = sv.validate_bindings(
            dict(capture, review_receipt=str(r)), bundle["capture_path"])
        assert any("independent" in p for p in problems)

    def test_reviewed_flag_alone_never_enables(self, capture, bundle):
        """Trevor's second attack: flip the boolean, approve nothing."""
        unreviewed = sv.write_capture_bundle(
            str(Path(bundle["capture_path"]).parent), _selectors(),
            ARTIFACT_BYTES,
            company_id=COMPANY, captured_at=CAPTURED_AT,
            session_id="sess-offline-2", candidate_revision=REV,
            artifact_name="a2.bin", capture_name="c2.json",
            receipt_name="r2.json")  # no reviewer -> no receipt
        with open(unreviewed["capture_path"], encoding="utf-8") as fh:
            cap2 = json.load(fh)
        state = sv.capability_state(cap2, reviewed=True,
                                    capture_path=unreviewed["capture_path"])
        assert state["enabled"] is False
        assert state["bindings_valid"] is False
        with pytest.raises(sv.CaptureInvalid):
            sv.load_capture(unreviewed["capture_path"])

    def test_a_dict_without_its_path_cannot_be_proven(self, capture):
        """Self-reported metadata with no way to re-hash is not proof."""
        with pytest.raises(sv.CaptureRequired, match="without its path"):
            sv.assert_capture_proven(capture)

    def test_the_bound_bundle_writes_private_modes(self, bundle):
        """Reuses ghl_evidence's 0600/0700 default, not a new policy."""
        for key in ("capture_path", "artifact_path", "receipt_path"):
            mode = os.stat(bundle[key]).st_mode & 0o777
            assert mode == ghl_evidence.FILE_MODE, f"{key} mode {oct(mode)}"

    def test_the_artifact_digest_is_the_file_digest(self, bundle):
        """The stored digest is the hash of the bytes, not of a claim."""
        assert bundle["artifact_sha256"] == \
            ghl_evidence.sha256_file(bundle["artifact_path"])


# ── D. No capture → disabled, and CaptureRequired ──────────────────────────

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

    def test_each_missing_field_keeps_it_disabled(self, capture, req, bundle):
        for field in sv.REQUIRED_CAPTURE_FIELDS:
            partial = {k: v for k, v in capture.items() if k != field}
            assert sv.capability_state(partial)["state"] == \
                sv.PENDING_LIVE_SELECTOR_CAPTURE
            with pytest.raises(sv.CaptureRequired):
                sv.build_variant_request(req, partial,
                                         capture_path=bundle["capture_path"])

    def test_plausible_but_malformed_capture_cannot_enable(self, capture, req,
                                                           bundle):
        """Right SHAPE, wrong VALUES — must stay disabled, not round up."""
        malformed = dict(capture, capture_evidence="I-saw-it-happen")
        state = sv.capability_state(malformed, reviewed=True,
                                    capture_path=bundle["capture_path"])
        assert state["enabled"] is False
        assert state["schema_valid"] is False
        assert any("capture_evidence" in p for p in state["schema_problems"])
        with pytest.raises(sv.CaptureInvalid):
            sv.build_variant_request(req, malformed,
                                     capture_path=bundle["capture_path"])

    def test_synthetic_marker_is_still_refused(self):
        assert sv.is_synthetic_capture(sv.SYNTHETIC_COMPLETE_CAPTURE) is True
        assert sv.is_synthetic_capture(sv.OFFLINE_SELECTOR_RESULTS) is True
        with pytest.raises(sv.CaptureRequired, match="synthetic"):
            sv.plan_variant_from_real_capture(
                sv.VariantRequest(location_id="l", funnel_id="f", step_id="s",
                                  name="B", slug="b"),
                sv.SYNTHETIC_COMPLETE_CAPTURE)

    def test_capture_checklist_covers_every_required_field(self):
        names = [f["name"] for f in sv.capture_checklist()["fields"]]
        assert names == list(sv.REQUIRED_CAPTURE_FIELDS)
        for field in sv.capture_checklist()["fields"]:
            assert field["required"] is True
            assert field["rule"].strip()

    def test_unreadable_capture_path_is_capture_required(self, tmp_path):
        with pytest.raises(sv.CaptureRequired):
            sv.load_capture(str(tmp_path / "does-not-exist.json"))


# ── E. Two-run idempotency ────────────────────────────────────────────────

class TestReuseShape:
    def test_first_run_creates(self, capture, req, bundle):
        decision = sv.reuse_decision(capture, [], req,
                                     capture_path=bundle["capture_path"])
        assert decision["action"] == "CREATE"
        assert decision["variant_id"] is None

    def test_second_run_reuses_the_same_variant(self, capture, req, bundle):
        created = {"id": capture["variant_id"], "name": req.name,
                   "url": req.slug,
                   capture["variant_relation"]: capture["control_id_before"]}
        first = sv.reuse_decision(capture, [], req,
                                  capture_path=bundle["capture_path"])
        second = sv.reuse_decision(capture, [created], req,
                                   capture_path=bundle["capture_path"])
        assert first["action"] == "CREATE"
        assert second["action"] == "REUSE"
        assert second["variant_id"] == capture["variant_id"]
        assert second["matched_on"]["relation_field"] == \
            capture["variant_relation"]

    def test_a_variant_linked_to_another_control_is_not_reused(
            self, capture, req, bundle):
        other = {"id": "v-other", "name": req.name, "url": req.slug,
                 capture["variant_relation"]: "a-different-control"}
        assert sv.reuse_decision(capture, [other], req,
                                 capture_path=bundle["capture_path"]
                                 )["action"] == "CREATE"

    def test_a_different_name_is_not_reused(self, capture, req, bundle):
        other = {"id": "v-other", "name": "C", "url": req.slug,
                 capture["variant_relation"]: capture["control_id_before"]}
        assert sv.reuse_decision(capture, [other], req,
                                 capture_path=bundle["capture_path"]
                                 )["action"] == "CREATE"

    def test_a_different_slug_is_not_reused(self, capture, req, bundle):
        other = {"id": "v-other", "name": req.name, "url": "z",
                 capture["variant_relation"]: capture["control_id_before"]}
        assert sv.reuse_decision(capture, [other], req,
                                 capture_path=bundle["capture_path"]
                                 )["action"] == "CREATE"

    def test_matching_is_never_by_list_position(self, capture, req, bundle):
        """A non-matching row at index 0 must not be reused just for being first."""
        rows = [{"id": "v-decoy", "name": "X", "url": "x",
                 capture["variant_relation"]: "elsewhere"}]
        assert sv.reuse_decision(capture, rows, req,
                                 capture_path=bundle["capture_path"]
                                 )["action"] == "CREATE"


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

    def test_cli_refuses_an_artifact_less_capture_cleanly(self, tmp_path):
        fake = _selectors()
        fake.update({
            "company_id": COMPANY, "captured_at": CAPTURED_AT,
            "session_id": "sess-attacker", "candidate_revision": REV,
            "capture_artifact": "never-written.png",
            "capture_artifact_sha256": "0" * 64,
            "selector_results_sha256": sv.selector_results_digest(fake),
            "review_receipt": "",
        })
        p = tmp_path / "capture.json"
        p.write_text(json.dumps(fake), encoding="utf-8")
        proc = self._run("--state", "--capture", str(p))
        assert proc.returncode == 1
        assert "REFUSE" in proc.stderr
        assert "Traceback" not in proc.stderr

    def test_state_accepts_a_bound_bundle(self, bundle):
        proc = self._run("--state", "--capture", bundle["capture_path"])
        assert proc.returncode == 0, proc.stderr
        state = json.loads(proc.stdout)
        assert state["bindings_valid"] is True
        assert state["enabled"] is False  # review is still owed, via the flag

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

    def test_checklist_script_rejects_an_unbound_capture(self, tmp_path):
        fake = _selectors()
        fake.update({
            "company_id": COMPANY, "captured_at": CAPTURED_AT,
            "session_id": "sess-attacker", "candidate_revision": REV,
            "capture_artifact": "never-written.png",
            "capture_artifact_sha256": "0" * 64,
            "selector_results_sha256": sv.selector_results_digest(fake),
            "review_receipt": "",
        })
        p = tmp_path / "capture.json"
        p.write_text(json.dumps(fake), encoding="utf-8")
        proc = subprocess.run([str(CHECKLIST_SH), "validate", str(p)],
                              capture_output=True, text=True)
        assert proc.returncode == 1
        assert "INVALID" in proc.stderr


# ── The invariant that must survive any future refactor ───────────────────

def test_default_capability_is_still_disabled_at_import():
    """Guard against a future edit that 'helpfully' enables the capability.

    No bound capture ships in the tree (the only fixture is a selector set
    with the synthetic marker, refused by load_capture), so the honest default
    must be DISABLED.
    """
    state = sv.capability_state()
    assert state["enabled"] is False
    assert state["state"] == sv.PENDING_LIVE_SELECTOR_CAPTURE
