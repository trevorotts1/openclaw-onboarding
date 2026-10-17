"""R71H receipt-filing tests (fix plan Item 31, S71-08 P2).

Synthetic run fixtures only, mirroring tests/test_automation_handoff.py's
reduced fixture contract and the real gate CLI. Covered: the stage-14
receipt filed on acceptance with the packet section 4 shape (build
method mapped from the recorded provenance, the filled checklist
instance filed under automation-wiring/, the WF item count verbatim);
a refusal receipt filed with its reason verbatim and the
automation-wiring stage left open at gate close; publish-verify's
hash gate (success on a match; refusal naming both hashes on a
one-byte change; refusal on a missing hand-off; refusal on a missing
locked hash); and an outcome whose handoff_sha256 disagrees with the
locked hash flagged at filing, never silently filed. No live GHL, no
dispatch, no network.
"""
import hashlib
import importlib.util
import json
import os
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
RECEIPT_PATH = "private/receipts/automation-wiring.json"
WAIVER = [{"rule": "uncalibrated_grade_thresholds",
           "reason": "gold set calibration session scheduled with the owner",
           "approved_by": "owner"}]

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
    contract = {"version": 1, "description": "r71h p2 fixture",
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


def playbook(trigger, source_id, name):
    return {"trigger": trigger, "source_id": source_id, "workflow_id": "WF-1",
            "playbook": {"system": "38-conversational-ai-system",
                         "playbook_name": name, "channels": ["sms", "email"],
                         "attached_via": "skill44", "doc_artifact": None}}


def accepted_outcome(**over):
    outcome = {
        "outcome": "accepted",
        "author_agent": "skill44-receiver", "author_session": "sess-s44-1",
        "started_at": "2026-10-16T11:00:00+00:00",
        "finished_at": "2026-10-16T11:20:00+00:00",
        "ghl_pack_version": "ghl-pack-1.2.0",
        "workflows": [{
            "workflow_id": "WF-1", "name": "Opt-in follow-up",
            "origin": {"type": "form_submitted", "form_id": "FORM-1"},
            "mechanism": {"type": "contact_tag", "tag": "sl-optin"},
            "provenance": "tier0-caf",
            "qc": {"script": "qc-built-workflow.sh", "exit_code": 0,
                   "checklist_instance": "handoff/checklist-wf-1.md",
                   "checklist_complete": True, "wf_items": "22/22"},
            "readback": {"exists": True, "status": "active"}}],
        "conversational": [
            playbook("opt-in", "FORM-1", "Opt-in follow-up"),
            playbook("purchase", "OF-1", "Purchase confirmation and onboarding"),
            playbook("booking", "S-3", "Booking confirmation and reminders")],
        "conversational_not_present": [],
    }
    outcome.update(over)
    return outcome


class ReceiptFilingTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="r71h-p2-"))
        self.contract = fixture_contract(self.td)

    def gate(self, *args, env=None):
        full = {"STAGE_GATE_CONTRACT": str(self.contract)}
        full.update(env or {})
        return run_cli(GATE, *args, env=full)

    def build_dispatched_run(self, with_launch_inputs=True):
        run = make_run(self.td)
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
                   good_funnel_completion())
        write_json(run / "ghl-install-test" / "clickthrough.json",
                   good_clickthrough())
        write(run / "ghl-install-test" / "evidence" / "desktop.png", PNG_BYTES)
        put_receipt(run, "ghl-install-test", install={
            "target": {"kind": "ghl", "funnel_or_site_id": "F-100",
                       "page_id_or_url": "P-200"}})
        if with_launch_inputs:
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
        proc = self.gate("close", run, "ghl-install-test",
                         env=dict(LOCATION_ENV))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        state = json.loads((run / "private" / "state.json").read_text())
        self.locked = state["stages"]["ghl-install-test"]["handoff_sha256"]
        return run

    def close_publish(self, run):
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        return self.gate("close", run, "publish-verify")

    # -- filing: acceptance --------------------------------------------

    def test_acceptance_filed_with_section4_shape(self):
        run = self.build_dispatched_run()
        write(run / "handoff" / "checklist-wf-1.md",
              "WF-1..WF-22 all checked\n")
        failures, filed = ah.file_dispatch_receipt(run, accepted_outcome())
        self.assertEqual(failures, [])
        receipt = json.loads((run / RECEIPT_PATH).read_text())
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["outcome"], "accepted")
        envelope = json.loads(
            (run / "handoff" / "automation-request.json").read_text())
        self.assertEqual(receipt["request_id"], envelope["request_id"])
        self.assertEqual(receipt["request_version"], 1)
        self.assertEqual(receipt["handoff_sha256"], self.locked)
        self.assertEqual(receipt["ghl_pack_version"], "ghl-pack-1.2.0")
        self.assertEqual(receipt["form_exceptions"], [])
        wf = receipt["workflows"][0]
        self.assertEqual(wf["workflow_id"], "WF-1")
        self.assertEqual(wf["trigger"],
                         {"type": "form_submitted", "form_id": "FORM-1"})
        self.assertEqual(wf["mechanism"],
                         {"type": "contact_tag", "tag": "sl-optin"})
        # Provenance tier 0 caf maps to the receipt's build_method.
        self.assertEqual(wf["build_method"], "caf-cli")
        self.assertEqual(wf["qc"]["script"], "qc-built-workflow.sh")
        self.assertEqual(wf["qc"]["exit_code"], 0)
        self.assertIs(wf["qc"]["checklist_complete"], True)
        # The WF item count is carried verbatim, never hardcoded.
        self.assertEqual(wf["qc"]["wf_items"], "22/22")
        self.assertEqual(wf["qc"]["checklist_instance"],
                         "automation-wiring/checklist-wf-1.md")
        filed_checklist = run / "automation-wiring" / "checklist-wf-1.md"
        self.assertTrue(filed_checklist.is_file())
        self.assertEqual(filed_checklist.read_bytes(),
                         (run / "handoff" / "checklist-wf-1.md").read_bytes())
        self.assertEqual(wf["readback"], {"exists": True, "status": "active"})
        self.assertEqual(len(receipt["conversational"]), 3)

    def test_acceptance_native_tier4_mapping(self):
        run = self.build_dispatched_run()
        write(run / "handoff" / "checklist-wf-1.md", "checked\n")
        outcome = accepted_outcome()
        outcome["workflows"][0]["provenance"] = "tier4-browser"
        outcome["workflows"][0]["mechanism"] = {
            "type": "native", "build_method": "tier4-browser-backstop"}
        failures, filed = ah.file_dispatch_receipt(run, outcome)
        self.assertEqual(failures, [])
        wf = filed["workflows"][0]
        self.assertEqual(wf["build_method"], "tier4-browser-backstop")
        self.assertEqual(wf["mechanism"],
                         {"type": "native",
                          "build_method": "tier4-browser-backstop"})

    def test_filed_acceptance_closes_the_stage(self):
        run = self.build_dispatched_run()
        write(run / "handoff" / "checklist-wf-1.md", "checked\n")
        failures, _ = ah.file_dispatch_receipt(run, accepted_outcome())
        self.assertEqual(failures, [])
        proc = self.close_publish(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        proc = self.gate("close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["automation-wiring"]["status"],
                         "closed")

    def test_cli_files_acceptance(self):
        run = self.build_dispatched_run()
        write(run / "handoff" / "checklist-wf-1.md", "checked\n")
        outcome_path = self.td / "outcome.json"
        write_json(outcome_path, accepted_outcome())
        proc = run_cli(EMITTER, run, "--outcome", outcome_path)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("FILED", proc.stdout)
        self.assertTrue((run / RECEIPT_PATH).is_file())

    # -- filing: refusal / failure --------------------------------------

    def test_refusal_filed_verbatim_and_stage_stays_open(self):
        run = self.build_dispatched_run()
        reason = ("blocked-auth: the Firebase refresh token is absent "
                  "for this location and no Tier 4 backstop is declared")
        outcome = {"outcome": "refused",
                   "refusal": {"code": "blocked-auth", "reason": reason}}
        failures, filed = ah.file_dispatch_receipt(run, outcome)
        self.assertEqual(failures, [])
        receipt = json.loads((run / RECEIPT_PATH).read_text())
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["outcome"], "refused")
        self.assertEqual(receipt["dispatch_refusal"]["reason"], reason)
        self.assertEqual(receipt["dispatch_refusal"]["code"], "blocked-auth")
        self.assertEqual(receipt["handoff_sha256"], self.locked)
        self.assertNotIn("workflows", receipt)
        proc = self.gate("close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(reason, proc.stdout)
        self.assertIn("leaves the stage open", proc.stdout)
        state = json.loads((run / "private" / "state.json").read_text())
        entry = state.get("stages", {}).get("automation-wiring", {})
        self.assertNotEqual(entry.get("status"), "closed")

    def test_refusal_without_reason_is_not_filed(self):
        run = self.build_dispatched_run()
        failures, filed = ah.file_dispatch_receipt(
            run, {"outcome": "refused", "refusal": {"code": "blocked-auth"}})
        self.assertIsNone(filed)
        self.assertTrue(any("verbatim" in f for f in failures), failures)
        self.assertFalse((run / RECEIPT_PATH).exists())

    def test_failed_outcome_filed_and_close_refused(self):
        run = self.build_dispatched_run()
        reason = "receiver transport failure: the delegated task timed out"
        failures, filed = ah.file_dispatch_receipt(
            run, {"outcome": "failed", "failure": {"reason": reason}})
        self.assertEqual(failures, [])
        receipt = json.loads((run / RECEIPT_PATH).read_text())
        self.assertEqual(receipt["status"], "fail")
        self.assertEqual(receipt["dispatch_failure"]["reason"], reason)
        proc = self.gate("close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        state = json.loads((run / "private" / "state.json").read_text())
        entry = state.get("stages", {}).get("automation-wiring", {})
        self.assertNotEqual(entry.get("status"), "closed")

    # -- filing: binding flags ------------------------------------------

    def test_wrong_handoff_hash_flagged_not_filed(self):
        run = self.build_dispatched_run()
        write(run / "handoff" / "checklist-wf-1.md", "checked\n")
        outcome = accepted_outcome(handoff_sha256="0" * 64)
        failures, filed = ah.file_dispatch_receipt(run, outcome)
        self.assertIsNone(filed)
        self.assertTrue(any("0" * 64 in f and self.locked in f
                            for f in failures), failures)
        self.assertFalse((run / RECEIPT_PATH).exists())
        outcome_path = self.td / "outcome.json"
        write_json(outcome_path, outcome)
        proc = run_cli(EMITTER, run, "--outcome", outcome_path)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertFalse((run / RECEIPT_PATH).exists())

    def test_filing_refused_without_a_dispatch(self):
        run = self.build_dispatched_run(with_launch_inputs=False)
        write(run / "handoff" / "checklist-wf-1.md", "checked\n")
        self.assertFalse((run / "handoff" / "automation-request.json").exists())
        failures, filed = ah.file_dispatch_receipt(run, accepted_outcome())
        self.assertIsNone(filed)
        self.assertTrue(any("no dispatch envelope" in f
                            for f in failures), failures)
        self.assertFalse((run / RECEIPT_PATH).exists())

    def test_filing_refused_for_wrong_request(self):
        run = self.build_dispatched_run()
        outcome = accepted_outcome(request_id="gxo_ffffffffffff")
        failures, filed = ah.file_dispatch_receipt(run, outcome)
        self.assertIsNone(filed)
        self.assertTrue(any("request_id" in f for f in failures), failures)
        self.assertFalse((run / RECEIPT_PATH).exists())

    # -- publish-verify hash gate ----------------------------------------

    def test_publish_close_succeeds_when_hash_matches(self):
        run = self.build_dispatched_run()
        proc = self.close_publish(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_publish_refused_on_one_byte_change_names_both_hashes(self):
        run = self.build_dispatched_run()
        hp = run / "handoff" / "automation-handoff.json"
        data = hp.read_bytes() + b" "
        hp.write_bytes(data)
        actual = hashlib.sha256(data).hexdigest()
        proc = self.close_publish(run)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("carried forward unchanged", proc.stdout)
        self.assertIn(self.locked, proc.stdout)
        self.assertIn(actual, proc.stdout)

    def test_publish_refused_on_missing_handoff(self):
        run = self.build_dispatched_run()
        (run / "handoff" / "automation-handoff.json").unlink()
        proc = self.close_publish(run)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("handoff/automation-handoff.json is missing",
                      proc.stdout)

    def test_publish_refused_on_missing_locked_hash(self):
        run = self.build_dispatched_run()
        state_path = run / "private" / "state.json"
        state = json.loads(state_path.read_text())
        del state["stages"]["ghl-install-test"]["handoff_sha256"]
        write_json(state_path, state)
        proc = self.close_publish(run)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("no hand-off hash is locked", proc.stdout)
        self.assertIn("handoff_sha256 is absent", proc.stdout)


if __name__ == "__main__":
    unittest.main()
