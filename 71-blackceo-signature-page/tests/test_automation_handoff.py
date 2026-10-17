"""R71H producer-side tests (fix plan Item 31 emitter, S71-08 P1).

Synthetic run fixtures only, mirroring tests/test_delivery_funnel.py's
reduced fixture contract and the real gate CLI. The emitter under test
is scripts/automation_handoff.py plus the stage_gate.py close hook.
Covered: exact-shape emission with the hash-lock recorded in state,
form-ID disagreement in both directions refusing the close by name, a
form ID from anywhere except Item 32's funnel-completion array never
entering the hand-off, the envelope's draft-only refusal, the envelope
carrying the hand-off's real hash, and no_workflow_reason producing an
exception entry rather than a build entry. No live GHL, no dispatch,
no network.
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
GATE = ROOT / "scripts" / "stage_gate.py"
EMITTER = ROOT / "scripts" / "automation_handoff.py"

_spec = importlib.util.spec_from_file_location("automation_handoff", EMITTER)
ah = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ah)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
LOCATION_ENV = {"GHL_LOCATION_ID": "loc_1"}

FULL_CREDS = {
    "pit": {"variable": "GHL_PRIVATE_INTEGRATION_TOKEN", "present": True},
    "location_id": {"variable": "GHL_LOCATION_ID", "present": True},
    "firebase_refresh_token": {"variable": "GHL_FIREBASE_REFRESH_TOKEN",
                               "present": True},
}


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def write_json(path: Path, obj):
    write(path, json.dumps(obj, indent=2) + "\n")


def run_cli(script, *args, env=None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run([PY, str(script), *map(str, args)],
                          text=True, capture_output=True, env=full_env)


def fixture_contract(td: Path) -> Path:
    def st(deps, artifacts=None, **kw):
        d = {"depends_on": deps, "requires_artifacts": [], "artifacts": artifacts or [],
             "validators": [], "review_required": False, "min_scores": None,
             "reads": [], "may_be_not_authorized": True}
        d.update(kw)
        return d
    stages = {
        "intake": st([]),
        "font-action-plan": st(["intake"]),
        "visual-mockup": st(["font-action-plan"]),
        "responsive-html": st(["visual-mockup"]),
        "ghl-install-test": st(["responsive-html"], artifacts=[
            {"glob": "ghl-install-test/install-steps.md", "min_count": 1}]),
        "publish-verify": st(["ghl-install-test"]),
        "automation-wiring": st(["publish-verify"]),
    }
    contract = {"version": 1, "description": "r71h fixture",
                "stage_order": list(stages), "stages": stages}
    path = td / "fixture-contract.json"
    write_json(path, contract)
    return path


def make_run(td: Path, intake_extra=None):
    run = td / "run"
    run.mkdir(parents=True, exist_ok=True)
    brand = {"grade": {"min_mean_saturation": None, "min_luma_std": None},
             "founder_photos": [], "font_policy": {}}
    write_json(run / "brand-fixture.json", brand)
    intake = {"page_version": "standard", "brand_owner": "Fixture",
              "brand_file": "brand-fixture.json", "creative_direction": None,
              "image_cap": 5, "image_engine": "kie", "test_run": False,
              # The Item 13 layout gate refuses layout-stage closes
              # without the owner-supplied reference files or a recorded
              # waiver; these fixtures record the waiver (the same
              # pattern tests/test_delivery_funnel.py uses).
              "layout_waivers": [
                  {"gate": "layout-references",
                   "reason": "test fixture: owner-supplied Item 13 reference files absent"}],
              "publish_target": "ghl", "automation_scope": "workflows",
              "credentials": FULL_CREDS}
    intake.update(intake_extra or {})
    write_json(run / "intake.json", intake)
    return run


def put_receipt(run, stage, **kw):
    receipt = {"stage": stage, "status": "pass", "author_agent": "builder-agent",
               "author_session": "sess-author-1",
               "started_at": "2026-10-16T10:00:00+00:00",
               "finished_at": "2026-10-16T10:30:00+00:00", "artifacts": []}
    receipt.update(kw)
    write_json(run / "private" / "receipts" / f"{stage}.json", receipt)
    return receipt


def put_install_receipt(run):
    receipt = {"stage": "ghl-install-test", "status": "pass",
               "author_agent": "builder", "author_session": "sess-author-1",
               "install": {"target": {"kind": "ghl",
                                      "funnel_or_site_id": "F-100",
                                      "page_id_or_url": "P-200"}}}
    write_json(run / "private" / "receipts" / "ghl-install-test.json", receipt)
    return receipt


def good_funnel_completion():
    return {
        "status": "complete",
        "funnel": {"funnel_id": "F-100", "name": "Main Funnel", "created": False,
                   "existence_check": True, "rail": "browser"},
        "steps": [
            {"order": 1, "step_id": "S-1", "name": "Opt-in", "type": "optin",
             "binding": {"kind": "ghl_page", "page_id": "P-200"}, "rail": "browser"},
            {"order": 2, "step_id": "S-2", "name": "Order", "type": "order",
             "binding": {"kind": "external_embed",
                         "embed_url": "https://pages.example.com/order",
                         "repo": "op/pages", "deployment_id": "dpl_1"},
             "rail": "browser"},
            {"order": 3, "step_id": "S-3", "name": "Book", "type": "booking",
             "binding": {"kind": "ghl_page", "page_id": "P-201"}, "rail": "browser"},
        ],
        "forms": [{"form_id": "FORM-1", "name": "Opt-in form",
                   "attached_to_step": "Opt-in", "created": True,
                   "existence_check": True, "rail": "browser"}],
        "popups": [],
        "click_actions": [],
        "order_forms": [{"step": "Order", "order_form_id": "OF-1",
                         "product_ids": ["PR-1"], "bound": True, "rail": "browser"}],
        "products": [],
        "payment": {"provider_present": True},
    }


def good_clickthrough():
    return {
        "steps_visited": ["Opt-in", "Order", "Book"],
        "form_submission": {"form_id": "FORM-1", "performed": True,
                            "submissions_count": 1, "test_contact_id": "TC-1"},
        "live_charge_made": False,
        "order_step": {"rendered": True, "product_id": "PR-1", "price": 497},
        "booking_step": {"rendered": True, "calendar_shown": True},
        "screenshots": ["ghl-install-test/evidence/desktop.png"],
    }


EXPECTED_HANDOFF = {
    "location_id": "loc_1",
    "funnel_id": "F-100",
    "page_id": "P-200",
    "forms": [{"form_id": "FORM-1", "form_name": "Opt-in form",
               "page_section": "Opt-in"}],
    "conversational_requirements": {"triggers": ["opt-in", "purchase", "booking"]},
}


class EmitterGateTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="r71h-"))
        self.contract = fixture_contract(self.td)

    def gate(self, *args, env=None):
        full = {"STAGE_GATE_CONTRACT": str(self.contract)}
        full.update(env or {})
        return run_cli(GATE, *args, env=full)

    def build_run(self, intake_extra=None, fc=None):
        run = make_run(self.td, intake_extra=intake_extra)
        proc = self.gate("init", run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        # Act 6 / Item 16 parity evidence: the composed gate refuses a
        # responsive-html close without the parity sheets and a passing
        # drift report, so the fixture seeds them before that close.
        write(run / "responsive-html" / "compare" / "compare-1440-fixture.png",
              PNG_BYTES)
        write(run / "responsive-html" / "compare" / "compare-390-fixture.png",
              PNG_BYTES)
        write_json(run / "responsive-html" / "compare" / "compare-report.json",
                   {"drift": {"status": "pass"}})
        for stage in ("intake", "font-action-plan", "visual-mockup",
                      "responsive-html"):
            put_receipt(run, stage)
            proc = self.gate("close", run, stage)
            self.assertEqual(proc.returncode, 0, f"{stage}: {proc.stdout}")
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        write_json(run / "ghl-install-test" / "funnel-completion.json",
                   fc if fc is not None else good_funnel_completion())
        write_json(run / "ghl-install-test" / "clickthrough.json",
                   good_clickthrough())
        write(run / "ghl-install-test" / "evidence" / "desktop.png", PNG_BYTES)
        put_install_receipt(run)
        return run

    def close_install(self, run, env=None):
        full = dict(LOCATION_ENV)
        full.update(env or {})
        return self.gate("close", run, "ghl-install-test", env=full)

    def test_emission_exact_shape_and_hash_lock(self):
        run = self.build_run()
        proc = self.close_install(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        handoff_path = run / "handoff" / "automation-handoff.json"
        data = handoff_path.read_bytes()
        self.assertEqual(json.loads(data), EXPECTED_HANDOFF)
        digest = hashlib.sha256(data).hexdigest()
        state = json.loads((run / "private" / "state.json").read_text())
        entry = state["stages"]["ghl-install-test"]
        self.assertEqual(entry["status"], "closed")
        self.assertEqual(entry["handoff_sha256"], digest)
        record = json.loads((run / "handoff" / "emission-record.json").read_text())
        self.assertEqual(record["handoff_sha256"], digest)
        self.assertEqual(record["handoff_origin"], "emitted")
        self.assertIsNone(record["envelope"])
        self.assertIn("launch_id", record["envelope_note"])
        self.assertFalse((run / "handoff" / "automation-request.json").exists())

    def test_external_handoff_extra_form_refused_by_name(self):
        run = self.build_run()
        external = dict(EXPECTED_HANDOFF)
        external["forms"] = EXPECTED_HANDOFF["forms"] + [
            {"form_id": "FORM-EXTRA", "form_name": "Sneaky",
             "page_section": "hero", "optin_fields": ["email"]}]
        write_json(run / "handoff" / "automation-handoff.json", external)
        before = (run / "handoff" / "automation-handoff.json").read_bytes()
        proc = self.close_install(run)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FORM-EXTRA", proc.stdout)
        self.assertIn("do not equal", proc.stdout)
        # The externally authored file is never overwritten.
        self.assertEqual(
            (run / "handoff" / "automation-handoff.json").read_bytes(), before)

    def test_external_handoff_missing_form_refused_by_name(self):
        fc = good_funnel_completion()
        fc["forms"] = fc["forms"] + [
            {"form_id": "FORM-2", "name": "Second form",
             "attached_to_step": "Order", "created": True,
             "existence_check": True, "rail": "browser"}]
        run = self.build_run(fc=fc)
        write_json(run / "handoff" / "automation-handoff.json", EXPECTED_HANDOFF)
        before = (run / "handoff" / "automation-handoff.json").read_bytes()
        proc = self.close_install(run)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("FORM-2", proc.stdout)
        self.assertIn("do not equal", proc.stdout)
        self.assertEqual(
            (run / "handoff" / "automation-handoff.json").read_bytes(), before)

    def test_form_without_id_in_funnel_record_refused(self):
        fc = good_funnel_completion()
        fc["forms"] = [{"name": "Ghost form", "attached_to_step": "Opt-in",
                        "created": True, "existence_check": True,
                        "rail": "browser"}]
        run = self.build_run(fc=fc)
        proc = self.close_install(run)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("Ghost form", proc.stdout)
        self.assertIn("carries no form_id", proc.stdout)
        self.assertFalse((run / "handoff" / "automation-handoff.json").exists())

    def test_form_id_from_intake_cannot_enter_handoff(self):
        run = self.build_run(intake_extra={
            "forms": [{"form_id": "FORM-BOGUS", "name": "Planted"}]})
        proc = self.close_install(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        text = (run / "handoff" / "automation-handoff.json").read_text()
        self.assertNotIn("FORM-BOGUS", text)
        self.assertEqual(json.loads(text)["forms"],
                         EXPECTED_HANDOFF["forms"])

    def test_location_value_unsourced_refuses_write(self):
        run = self.build_run()
        failures, record = ah.emit_handoff(run, env={}, deploy_mode="draft-only",
                       requesting_room="S71")
        self.assertIsNone(record)
        self.assertTrue(any("GHL_LOCATION_ID" in f for f in failures),
                        failures)
        self.assertFalse((run / "handoff" / "automation-handoff.json").exists())

    def test_non_ghl_run_noops(self):
        run = make_run(self.td, intake_extra={"publish_target": "vercel"})
        failures, record = ah.emit_handoff(run, env=dict(LOCATION_ENV),
                       deploy_mode="draft-only", requesting_room="S71")
        self.assertEqual(failures, [])
        self.assertIsNone(record)
        self.assertFalse((run / "handoff").exists())

    def test_emitter_owned_regenerates_external_does_not(self):
        run = self.build_run()
        failures, record = ah.emit_handoff(run, env=dict(LOCATION_ENV),
                       deploy_mode="draft-only", requesting_room="S71")
        self.assertEqual(failures, [])
        fc = good_funnel_completion()
        fc["forms"] = fc["forms"] + [
            {"form_id": "FORM-2", "name": "Second form",
             "attached_to_step": "Order", "created": True,
             "existence_check": True, "rail": "browser"}]
        write_json(run / "ghl-install-test" / "funnel-completion.json", fc)
        failures, record = ah.emit_handoff(run, env=dict(LOCATION_ENV),
                       deploy_mode="draft-only", requesting_room="S71")
        self.assertEqual(failures, [])
        handoff = json.loads(
            (run / "handoff" / "automation-handoff.json").read_text())
        self.assertEqual([f["form_id"] for f in handoff["forms"]],
                         ["FORM-1", "FORM-2"])
        # Tamper with the emitted file: it is no longer emitter-owned,
        # and the disagreement with the records refuses by name.
        handoff["page_id"] = "P-999"
        write_json(run / "handoff" / "automation-handoff.json", handoff)
        failures, record = ah.emit_handoff(run, env=dict(LOCATION_ENV),
                       deploy_mode="draft-only", requesting_room="S71")
        self.assertTrue(any("P-999" in f for f in failures), failures)

    def test_gate_close_writes_envelope_with_launch_inputs(self):
        run = self.build_run()
        write_json(run / "page-request.json", {
            "launch_id": "LNCH-71-001",
            "plan_approval_ref": "approval-record-2026-10-16",
            "automation": {
                "folder": "Signature Launch / LNCH-71-001",
                "workflows": [
                    {"form_id": "FORM-1", "slug": "optin-followup",
                     "expected_steps": 4, "allow_multiple": False,
                     "mechanism": {"type": "contact_tag",
                                   "tag": "sl-optin"}}]}})
        proc = self.close_install(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        env_path = run / "handoff" / "automation-request.json"
        envelope = json.loads(env_path.read_text())
        self.assertEqual(set(envelope), set(ah.ENVELOPE_FIELDS))
        self.assertRegex(envelope["request_id"], r"^gxo_[0-9a-f]{12}$")
        self.assertEqual(envelope["request_version"], 1)
        self.assertEqual(envelope["location_id"], "loc_1")
        self.assertEqual(envelope["launch_id"], "LNCH-71-001")
        self.assertEqual(envelope["requesting_room"], "S71")
        self.assertEqual(envelope["deploy_mode"], "draft-only")
        self.assertEqual(envelope["approval"]["ref"],
                         "approval-record-2026-10-16")
        plan_hash = hashlib.sha256(ah.canonical_bytes(envelope["plan"])).hexdigest()
        self.assertEqual(envelope["approval"]["plan_hash"], plan_hash)
        digest = hashlib.sha256(
            (run / "handoff" / "automation-handoff.json").read_bytes()).hexdigest()
        self.assertEqual(envelope["handoff_sha256"], digest)
        self.assertEqual(envelope["workflows"][0]["origin"],
                         {"type": "form_submitted", "form_id": "FORM-1"})
        self.assertEqual(envelope["workflows"][0]["mechanism"],
                         {"type": "contact_tag", "tag": "sl-optin"})
        record = json.loads((run / "handoff" / "emission-record.json").read_text())
        self.assertEqual(record["request_id"], envelope["request_id"])
        self.assertEqual(record["envelope"], "handoff/automation-request.json")

    def test_cli_without_deploy_mode_flag_is_usage_error(self):
        run = self.build_run()
        proc = run_cli(EMITTER, run, env=dict(LOCATION_ENV))
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("usage", proc.stdout)
        self.assertFalse(
            (run / "handoff" / "automation-handoff.json").exists())

    def test_cli_deploy_mode_flag_without_value_is_usage_error(self):
        run = self.build_run()
        proc = run_cli(EMITTER, run, "--deploy-mode",
                       env=dict(LOCATION_ENV))
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("usage", proc.stdout)
        self.assertFalse(
            (run / "handoff" / "automation-handoff.json").exists())

    def test_cli_live_deploy_mode_refused_and_emits_nothing(self):
        run = self.build_run()
        proc = run_cli(EMITTER, run, "--deploy-mode", "live",
                       env=dict(LOCATION_ENV))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("draft-only", proc.stdout)
        self.assertFalse(
            (run / "handoff" / "automation-handoff.json").exists())

    def test_cli_explicit_draft_only_emits(self):
        run = self.build_run()
        proc = run_cli(EMITTER, run, "--deploy-mode", "draft-only",
                       env=dict(LOCATION_ENV))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("EMITTED", proc.stdout)
        data = (run / "handoff" / "automation-handoff.json").read_bytes()
        self.assertEqual(json.loads(data), EXPECTED_HANDOFF)


class EnvelopeConstructionTest(unittest.TestCase):
    def handoff(self):
        return {"location_id": "loc_1", "funnel_id": "F-100",
                "page_id": "P-200",
                "forms": [{"form_id": "FORM-1", "form_name": "Opt-in form",
                           "page_section": "Opt-in"},
                          {"form_id": "FORM-2", "form_name": "Second form",
                           "page_section": "Order"}],
                "conversational_requirements": {"triggers": ["opt-in"]}}

    def specs(self):
        return [
            {"form_id": "FORM-1", "slug": "optin-followup",
             "expected_steps": 4, "allow_multiple": False,
             "mechanism": {"type": "contact_tag", "tag": "sl-optin"}},
            {"form_id": "FORM-2",
             "no_workflow_reason": "receipt-only form; the launch plan "
                                   "assigns no workflow"},
        ]

    def build(self, handoff=None, digest=None, **over):
        handoff = handoff or self.handoff()
        kw = {"launch_id": "LNCH-71-001", "requesting_room": "S71",
              "approval_ref": "approval-record-1",
              "folder": "Signature Launch / LNCH-71-001",
              "workflow_specs": self.specs(),
              "deploy_mode": "draft-only",
              "request_id": "gxo_0123456789ab", "request_version": 1}
        kw.update(over)
        if digest is None:
            digest = ah.sha256_bytes(ah.serialize(handoff))
        return ah.build_envelope(handoff, digest, **kw)

    def test_deploy_mode_refusals(self):
        with self.assertRaises(ah.EnvelopeError):
            self.build(deploy_mode="live")
        with self.assertRaises(ah.EnvelopeError):
            self.build(deploy_mode=None)
        with self.assertRaises(ah.EnvelopeError):
            self.build(deploy_mode="")
        failures, record = ah.emit_handoff(
            Path(tempfile.mkdtemp()), deploy_mode="live",
            requesting_room="S71")
        self.assertTrue(any("draft-only" in f for f in failures))

    def test_envelope_carries_the_handoff_hash(self):
        handoff = self.handoff()
        envelope = self.build(handoff=handoff)
        digest = ah.sha256_bytes(ah.serialize(handoff))
        self.assertEqual(envelope["handoff_sha256"], digest)
        self.assertEqual(ah.validate_envelope(envelope, handoff, digest), [])
        with self.assertRaises(ah.EnvelopeError):
            self.build(handoff=handoff, digest="0" * 64)

    def test_no_workflow_reason_is_an_exception_entry(self):
        envelope = self.build()
        by_form = {}
        for w in envelope["workflows"]:
            fid = w.get("form_id") or w["origin"]["form_id"]
            by_form[fid] = w
        self.assertEqual(by_form["FORM-2"],
                         {"form_id": "FORM-2",
                          "no_workflow_reason": "receipt-only form; the "
                                                "launch plan assigns no "
                                                "workflow"})
        self.assertNotIn("slug", by_form["FORM-2"])
        self.assertEqual(set(envelope["plan"]),
                         {"folder", "optin-followup"})
        self.assertEqual(by_form["FORM-1"]["mechanism"],
                         {"type": "contact_tag", "tag": "sl-optin"})
        self.assertEqual(by_form["FORM-1"]["expected_steps"], 4)
        self.assertIs(by_form["FORM-1"]["allow_multiple"], False)

    def test_uncovered_form_and_unknown_field_refused(self):
        with self.assertRaises(ah.EnvelopeError) as ctx:
            self.build(workflow_specs=self.specs()[:1])
        self.assertIn("FORM-2", str(ctx.exception))
        envelope = self.build()
        envelope["surprise"] = True
        problems = ah.validate_envelope(
            envelope, self.handoff(),
            ah.sha256_bytes(ah.serialize(self.handoff())))
        self.assertTrue(any("unknown field" in p for p in problems), problems)

    def test_tampered_plan_fails_validation(self):
        handoff = self.handoff()
        envelope = self.build(handoff=handoff)
        envelope["plan"]["folder"] = "Somewhere Else"
        problems = ah.validate_envelope(
            envelope, handoff, ah.sha256_bytes(ah.serialize(handoff)))
        self.assertTrue(any("plan_hash" in p for p in problems), problems)

    def test_contact_tag_requires_verbatim_tag(self):
        specs = self.specs()
        specs[0] = {"form_id": "FORM-1", "slug": "optin-followup",
                    "expected_steps": 4, "allow_multiple": False,
                    "mechanism": {"type": "contact_tag"}}
        with self.assertRaises(ah.EnvelopeError):
            self.build(workflow_specs=specs)


class DeployModeEntryPointTest(unittest.TestCase):
    """D1 cure probes (independent review of S71-08 P1): deploy_mode is
    a required argument at the emit entry point, never defaulted there
    either; the same holds for requesting_room. Every explicitly
    supplied non-"draft-only" value is refused at emit level too."""

    def test_emit_omitting_deploy_mode_raises(self):
        with self.assertRaises(TypeError):
            ah.emit_handoff(Path(tempfile.mkdtemp()),
                            requesting_room="S71")

    def test_emit_omitting_requesting_room_raises(self):
        with self.assertRaises(TypeError):
            ah.emit_handoff(Path(tempfile.mkdtemp()),
                            deploy_mode="draft-only")

    def test_emit_refuses_non_draft_only_values(self):
        for bad in (None, "", "live", "DRAFT-ONLY", " draft-only"):
            failures, record = ah.emit_handoff(
                Path(tempfile.mkdtemp()), deploy_mode=bad,
                requesting_room="S71")
            self.assertIsNone(record)
            self.assertTrue(
                any("draft-only" in f for f in failures), (bad, failures))


if __name__ == "__main__":
    unittest.main()
