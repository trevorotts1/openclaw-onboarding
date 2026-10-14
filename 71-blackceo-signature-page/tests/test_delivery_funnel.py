"""S5 delivery and funnel tests (fix plan Items 5, 6, 31, 32, 34).

Synthetic run fixtures only: local HTTP server for the publish fetch layer,
hand-built receipts and state transitions through the real gate CLI with a
reduced fixture contract. No live GHL, Vercel, or network access.
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
GATE = ROOT / "scripts" / "stage_gate.py"
VALIDATE_INSTALL = ROOT / "scripts" / "validate_install.py"
VALIDATE_FUNNEL = ROOT / "scripts" / "validate_funnel_completion.py"
CHECK_DELIVERABLES = ROOT / "scripts" / "check_deliverables.py"
WRITE_INTAKE = ROOT / "scripts" / "write_intake.py"
WRITE_REVIEW = ROOT / "scripts" / "write_review.py"

FOUNDER_BYTES = b"founder-photo-bytes"
FOUNDER_SHA = hashlib.sha256(FOUNDER_BYTES).hexdigest()
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
LONG_NOTE = "checked against the recorded evidence in the run folder, line by line"


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


def make_run(td: Path, intake_extra=None, grade=None):
    run = td / "run"
    run.mkdir(parents=True, exist_ok=True)
    brand = {
        "grade": grade if grade is not None else
                 {"min_mean_saturation": None, "min_luma_std": None},
        "founder_photos": [f"sha256:{FOUNDER_SHA}"],
        "font_policy": {"when_brand_fonts_missing": "derive-document"},
    }
    write_json(run / "brand-fixture.json", brand)
    intake = {"page_version": "standard", "brand_owner": "Fixture",
              "brand_file": "brand-fixture.json", "creative_direction": None,
              "image_cap": 5, "image_engine": "kie", "test_run": False,
              # Assembly fix (S8): the Item 13 layout gate (S3 Request 2,
              # applied at assembly) refuses layout-stage closes without
              # the owner-supplied reference files or a recorded waiver;
              # these fixtures predate the gate, so they record the waiver.
              "layout_waivers": [
                  {"gate": "layout-references",
                   "reason": "test fixture: owner-supplied Item 13 reference files absent"}]}
    intake.update(intake_extra or {})
    write_json(run / "intake.json", intake)
    write(run / "founder.jpg", FOUNDER_BYTES)
    return run


def good_install_block(kind="ghl"):
    return {
        "target": {"kind": kind, "funnel_or_site_id": "F-100",
                   "page_id_or_url": "P-200"},
        "journey_checks": {
            "cta_clicks": [{"label": "Book now", "destination": "step-2", "ok": True}],
            "form_submit_test": {"performed": True, "test_contact_id": "TC-1",
                                 "submissions_count": 1, "ok": True},
            "popup_open_close": {"ok": True},
            "mobile_keyboard_scroll": {"ok": True},
        },
        "sales_check": {"mode": "test", "live_charge_made": False, "ok": True},
        "founder_photo": {"path": "founder.jpg", "sha256": FOUNDER_SHA},
    }


def put_install_receipt(run, block=None, kind="ghl"):
    receipt = {"stage": "ghl-install-test", "status": "pass",
               "author_agent": "builder", "author_session": "sess-author-1",
               "install": block if block is not None else good_install_block(kind)}
    write_json(run / "private" / "receipts" / "ghl-install-test.json", receipt)
    write(run / "ghl-install-test" / "evidence" / "desktop.png", PNG_BYTES)
    write(run / "ghl-install-test" / "evidence" / "mobile.png", PNG_BYTES)
    return receipt


class InstallValidatorTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-install-"))
        self.run = make_run(self.td)

    def validate(self):
        return run_cli(VALIDATE_INSTALL, self.run, "install")

    def test_good_install_passes(self):
        put_install_receipt(self.run)
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_cta_not_ok_fails(self):
        block = good_install_block()
        block["journey_checks"]["cta_clicks"][0]["ok"] = False
        put_install_receipt(self.run, block)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("CTA click check not ok", proc.stdout)

    def test_form_submitted_twice_fails_once_only_rule(self):
        block = good_install_block()
        block["journey_checks"]["form_submit_test"]["submissions_count"] = 2
        put_install_receipt(self.run, block)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("exactly 1", proc.stdout)

    def test_form_not_performed_without_reason_fails(self):
        block = good_install_block()
        block["journey_checks"]["form_submit_test"] = {"performed": False}
        put_install_receipt(self.run, block)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not_applicable_reason", proc.stdout)

    def test_missing_evidence_screenshot_fails(self):
        put_install_receipt(self.run)
        (self.run / "ghl-install-test" / "evidence" / "mobile.png").unlink()
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("evidence/mobile.png", proc.stdout)

    def test_founder_photo_hash_mismatch_fails(self):
        block = good_install_block()
        block["founder_photo"] = {"path": "founder.jpg", "sha256": "0" * 64}
        put_install_receipt(self.run, block)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("founder photo SHA-256 mismatch", proc.stdout)

    def test_live_charge_fails(self):
        block = good_install_block()
        block["sales_check"]["live_charge_made"] = True
        put_install_receipt(self.run, block)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("live charge", proc.stdout)

    def test_vercel_embed_requires_embedded_layer(self):
        block = good_install_block("vercel-embed")
        put_install_receipt(self.run, block, kind="vercel-embed")
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("embedded_checks", proc.stdout)
        block["embedded_checks"] = {
            "iframe_sizing": {"ok": True}, "popup_visibility": {"ok": True},
            "scroll_behavior": {"ok": True}, "performed_in": "ghl_embed"}
        put_install_receipt(self.run, block, kind="vercel-embed")
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout)


GOOD_PAGE = """<!doctype html><html><head>
<!-- skill71-build run_id=run-test-1 commit=abc1234 -->
<title>Welcome</title></head><body>
<h1>Welcome</h1><p>Book your call with the team.</p>
<form><input type="email" name="email"></form>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        route = self.routes.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        kind, payload = route
        if kind == "redirect":
            self.send_response(302)
            self.send_header("Location", payload)
            self.end_headers()
            return
        body = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PublishValidatorTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-publish-"))
        self.run = make_run(self.td)
        _Handler.routes = {
            "/page": ("html", GOOD_PAGE),
            "/placeholder": ("html", "<html><body><p>TODO wire this</p></body></html>"),
            "/label": ("html", "<html><body><h1>Big Bold Claim</h1></body></html>"),
            "/old": ("redirect", "/page"),
        }
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def put_publish_receipt(self, public_url):
        write_json(self.run / "private" / "receipts" / "publish-verify.json",
                   {"stage": "publish-verify", "status": "pass",
                    "author_agent": "builder", "author_session": "sess-author-1",
                    "public_url": public_url})

    def validate(self):
        return run_cli(VALIDATE_INSTALL, self.run, "publish")

    def fetch_record(self):
        return json.loads((self.run / "publish-verify" / "fetch-record.json").read_text())

    def test_good_page_passes_and_writes_fetch_record(self):
        self.put_publish_receipt(self.url("/page"))
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        record = self.fetch_record()
        self.assertEqual(record["verdict"], "pass")
        self.assertEqual(record["status"], 200)
        self.assertEqual(record["build_marker"],
                         {"run_id": "run-test-1", "commit_sha": "abc1234"})

    def test_placeholder_fails(self):
        self.put_publish_receipt(self.url("/placeholder"))
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("placeholder", proc.stdout)
        self.assertEqual(self.fetch_record()["verdict"], "fail")

    def test_private_label_fails(self):
        self.put_publish_receipt(self.url("/label"))
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("private framework label", proc.stdout)

    def test_redirect_final_url_mismatch_fails(self):
        self.put_publish_receipt(self.url("/old"))
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("final URL", proc.stdout)

    def test_unreachable_is_blocked_never_pass(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
        sock.close()
        self.put_publish_receipt(f"http://127.0.0.1:{dead_port}/page")
        proc = self.validate()
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("BLOCKED", proc.stdout)
        self.assertEqual(self.fetch_record()["verdict"], "blocked")

    def test_provenance_bindings(self):
        self.put_publish_receipt(self.url("/page"))
        write_json(self.run / "deliverables" / "provenance.json", {
            "run_id": "run-test-1",
            "github": {"owner": "op", "repo": "pages", "branch": "main",
                       "commit_sha": "abc1234"},
            "vercel": {"project_id": "prj_1", "deployment_id": "dpl_1",
                       "url": self.url("/page")},
            "ghl": {"location_id": "loc_1", "funnel_id": "F-100"}})
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        prov = json.loads((self.run / "deliverables" / "provenance.json").read_text())
        prov["vercel"]["url"] = self.url("/other")
        write_json(self.run / "deliverables" / "provenance.json", prov)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("provenance", proc.stdout)


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
        "popups": [{"name": "Exit popup", "step": "Opt-in",
                    "trigger_element": "hero-cta", "created": False,
                    "existence_check": True, "rail": "browser"}],
        "click_actions": [{"step": "Opt-in", "element": "hero-cta",
                           "action": "open_popup", "target_ref": "Exit popup",
                           "verified_by_clickthrough": True, "rail": "browser"}],
        "order_forms": [{"step": "Order", "order_form_id": "OF-1",
                         "product_ids": ["PR-1"], "bound": True, "rail": "browser"}],
        "products": [{"product_id": "PR-1", "name": "Signature Program",
                      "price": 497, "currency": "USD", "created": True,
                      "existence_check": True, "rail": "api"}],
        "payment": {"provider_present": True},
    }


def good_clickthrough():
    return {
        "steps_visited": ["Opt-in", "Order", "Book"],
        "form_submission": {"performed": True, "submissions_count": 1,
                            "test_contact_id": "TC-1"},
        "live_charge_made": False,
        "order_step": {"rendered": True, "product_id": "PR-1", "price": 497},
        "booking_step": {"rendered": True, "calendar_shown": True},
        "screenshots": ["ghl-install-test/evidence/desktop.png"],
    }


class FunnelCompletionTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-funnel-"))
        self.run = make_run(self.td, intake_extra={"publish_target": "ghl"})

    def put_funnel(self, fc=None, ct=None):
        write_json(self.run / "ghl-install-test" / "funnel-completion.json",
                   fc if fc is not None else good_funnel_completion())
        write_json(self.run / "ghl-install-test" / "clickthrough.json",
                   ct if ct is not None else good_clickthrough())
        write(self.run / "ghl-install-test" / "evidence" / "desktop.png", PNG_BYTES)

    def validate(self):
        return run_cli(VALIDATE_FUNNEL, self.run)

    def test_good_funnel_passes(self):
        self.put_funnel()
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_product_on_browser_rail_fails(self):
        fc = good_funnel_completion()
        fc["products"][0]["rail"] = "browser"
        self.put_funnel(fc)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn('rail must be "api"', proc.stdout)

    def test_create_without_existence_check_fails(self):
        fc = good_funnel_completion()
        fc["products"][0]["existence_check"] = False
        self.put_funnel(fc)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("existence check", proc.stdout)

    def test_unclicked_action_fails(self):
        fc = good_funnel_completion()
        fc["click_actions"][0]["verified_by_clickthrough"] = False
        self.put_funnel(fc)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("verified_by_clickthrough", proc.stdout)

    def test_order_step_price_mismatch_fails(self):
        ct = good_clickthrough()
        ct["order_step"]["price"] = 1
        self.put_funnel(ct=ct)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("price", proc.stdout)

    def test_not_applicable_requires_non_ghl_target(self):
        write_json(self.run / "intake.json",
                   {**json.loads((self.run / "intake.json").read_text()),
                    "publish_target": "vercel"})
        write_json(self.run / "ghl-install-test" / "funnel-completion.json",
                   {"status": "not_applicable",
                    "reason": "no funnel on the vercel route"})
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        write_json(self.run / "intake.json",
                   {**json.loads((self.run / "intake.json").read_text()),
                    "publish_target": "ghl"})
        proc = self.validate()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not_applicable", proc.stdout)


class WriteIntakeDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-intake-"))
        self.run = self.td / "run"
        self.run.mkdir(parents=True)

    def intake(self, *extra):
        return run_cli(WRITE_INTAKE, self.run, "--page-version", "standard",
                       "--brand-owner", "Fixture", "--creative-direction", "x",
                       "--image-cap", "5", *extra)

    def test_legacy_invocation_unchanged(self):
        proc = self.intake()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads((self.run / "intake.json").read_text())
        self.assertNotIn("publish_target", data)

    def test_workflows_on_non_ghl_target_refused(self):
        proc = self.intake("--publish-target", "vercel-embed",
                           "--automation-scope", "workflows")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("REFUSED", proc.stdout)
        self.assertFalse((self.run / "intake.json").exists())

    def test_ghl_target_without_credentials_refused(self):
        proc = self.intake("--publish-target", "ghl",
                           "--ghl-pit-absent", "--ghl-location-absent")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("REFUSED", proc.stdout)
        self.assertIn("GHL_PRIVATE_INTEGRATION_TOKEN", proc.stdout)

    def test_workflows_without_firebase_needs_a_recorded_choice(self):
        proc = self.intake("--publish-target", "ghl", "--automation-scope", "workflows",
                           "--ghl-pit-present", "--ghl-location-present",
                           "--ghl-firebase-absent")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("firebase-choice", proc.stdout)

    def test_backstop_choice_records_presence_booleans_only(self):
        proc = self.intake("--publish-target", "ghl", "--automation-scope", "workflows",
                           "--ghl-pit-present", "--ghl-location-present",
                           "--ghl-firebase-absent", "--firebase-choice", "backstop")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads((self.run / "intake.json").read_text())
        self.assertTrue(data["firebase_backstop_declared"])
        self.assertEqual(data["credentials"]["firebase_refresh_token"],
                         {"variable": "GHL_FIREBASE_REFRESH_TOKEN", "present": False})
        self.assertTrue(data["credentials"]["pit"]["present"])

    def test_drop_choice_records_dropped_scope(self):
        proc = self.intake("--publish-target", "ghl", "--automation-scope", "workflows",
                           "--ghl-pit-present", "--ghl-location-present",
                           "--ghl-firebase-absent", "--firebase-choice", "drop")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads((self.run / "intake.json").read_text())
        self.assertEqual(data["automation_scope"], "none")
        self.assertIn("automation_scope_dropped", data)


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
        "automation-wiring": st(["publish-verify"], artifacts=[
            {"glob": "automation-wiring/checklist-*.md", "min_count": 1}],
            review_required=True, min_scores={"each": 8}),
    }
    contract = {"version": 1, "description": "s5 fixture",
                "stage_order": list(stages), "stages": stages}
    path = td / "fixture-contract.json"
    write_json(path, contract)
    return path


def put_receipt(run, stage, **kw):
    receipt = {"stage": stage, "status": "pass", "author_agent": "builder-agent",
               "author_session": "sess-author-1",
               "started_at": "2026-10-13T10:00:00+00:00",
               "finished_at": "2026-10-13T10:30:00+00:00", "artifacts": []}
    receipt.update(kw)
    write_json(run / "private" / "receipts" / f"{stage}.json", receipt)
    return receipt


def gate(contract, *args):
    return run_cli(GATE, *args, env={"STAGE_GATE_CONTRACT": str(contract)})


WAIVER = [{"rule": "uncalibrated_grade_thresholds",
           "reason": "gold set calibration session scheduled with the owner",
           "approved_by": "owner"}]

FULL_CREDS = {
    "pit": {"variable": "GHL_PRIVATE_INTEGRATION_TOKEN", "present": True},
    "location_id": {"variable": "GHL_LOCATION_ID", "present": True},
    "firebase_refresh_token": {"variable": "GHL_FIREBASE_REFRESH_TOKEN",
                               "present": True},
}


class GatePublishRulesTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-gate-"))
        self.contract = fixture_contract(self.td)

    def build_run(self, intake_extra=None):
        run = make_run(self.td, intake_extra=intake_extra)
        gate(self.contract, "init", run)
        for stage in ("intake", "font-action-plan", "visual-mockup", "responsive-html"):
            put_receipt(run, stage)
            proc = gate(self.contract, "close", run, stage)
            self.assertEqual(proc.returncode, 0, f"{stage}: {proc.stdout}")
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        put_receipt(run, "ghl-install-test")
        proc = gate(self.contract, "close", run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        return run

    def test_uncalibrated_thresholds_refuse_production_close(self):
        run = self.build_run()
        put_receipt(run, "publish-verify", public_url="https://example.com/p")
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("uncalibrated", proc.stdout)
        self.assertIn("owner-ordered", proc.stdout)

    def test_owner_waiver_allows_close_and_prints_in_report(self):
        run = self.build_run()
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        gate(self.contract, "report", run)
        report = (run / "REPORT.md").read_text()
        self.assertIn("publish-verify waiver accepted", report)

    def test_test_run_cannot_close_as_production_pass(self):
        run = self.build_run(intake_extra={"test_run": True})
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("test run", proc.stdout)

    def test_derived_fonts_need_independent_font_reviewer(self):
        run = self.build_run()
        write_json(run / "visual-mockup" / "page-visual-bible.json",
                   {"fonts_source": "derived", "font_reviewer": "sess-author-1"})
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("font_reviewer", proc.stdout)
        write_json(run / "visual-mockup" / "page-visual-bible.json",
                   {"fonts_source": "derived", "font_reviewer": "sess-font-reviewer"})
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 0, proc.stdout)


def write_handoff(run, page_id="P-200"):
    write_json(run / "handoff" / "automation-handoff.json", {
        "location_id": "loc_1", "funnel_id": "F-100", "page_id": page_id,
        "forms": [{"form_id": "FORM-1", "form_name": "Opt-in form",
                   "page_section": "hero", "optin_fields": ["email"]}],
        "conversational_requirements": {"triggers": ["opt-in", "purchase", "booking"]}})


def playbook(trigger, source_id, name):
    return {"trigger": trigger, "source_id": source_id, "workflow_id": "WF-1",
            "playbook": {"system": "38-conversational-ai-system",
                         "playbook_name": name, "channels": ["sms", "email"],
                         "attached_via": "skill44", "doc_artifact": None}}


class GateAutomationWiringTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-wiring-"))
        self.contract = fixture_contract(self.td)

    def test_not_applicable_recorded_and_reported(self):
        run = make_run(self.td)
        gate(self.contract, "init", run)
        proc = gate(self.contract, "close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("NOT APPLICABLE", proc.stdout)
        state = json.loads((run / "private" / "state.json").read_text())
        entry = state["stages"]["automation-wiring"]
        self.assertEqual(entry["status"], "not_applicable")
        self.assertIn("publish_target", entry["reason"])
        gate(self.contract, "report", run)
        report = (run / "REPORT.md").read_text()
        self.assertIn("automation-wiring | NOT APPLICABLE", report)
        self.assertIn("automation-wiring NOT APPLICABLE", report)

    def build_wired_run(self):
        run = make_run(self.td, intake_extra={
            "publish_target": "ghl", "automation_scope": "workflows",
            "credentials": FULL_CREDS})
        gate(self.contract, "init", run)
        for stage in ("intake", "font-action-plan", "visual-mockup", "responsive-html"):
            put_receipt(run, stage)
            proc = gate(self.contract, "close", run, stage)
            self.assertEqual(proc.returncode, 0, f"{stage}: {proc.stdout}")
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        write_json(run / "ghl-install-test" / "funnel-completion.json",
                   good_funnel_completion())
        write_json(run / "ghl-install-test" / "clickthrough.json", good_clickthrough())
        write_handoff(run)
        put_receipt(run, "ghl-install-test")
        proc = gate(self.contract, "close", run, "ghl-install-test")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        return run

    def test_handoff_tamper_fails_publish_close(self):
        run = self.build_wired_run()
        write_handoff(run, page_id="P-999")
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("carried forward unchanged", proc.stdout)
        write_handoff(run)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_full_wiring_close(self):
        run = self.build_wired_run()
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        write(run / "automation-wiring" / "checklist-wf-1.md", "WF checklist complete")
        put_receipt(run, "automation-wiring",
                    ghl_pack_version="ghl-pack-1.0.0",
                    workflows=[{
                        "workflow_id": "WF-1", "name": "Opt-in follow-up",
                        "trigger": {"type": "form_submitted", "form_id": "FORM-1"},
                        "build_method": "caf-cli",
                        "qc": {"script": "qc-built-workflow.sh", "exit_code": 0,
                               "checklist_instance": "automation-wiring/checklist-wf-1.md",
                               "checklist_complete": True, "wf_items": "21/21"},
                        "readback": {"exists": True, "status": "active"}}],
                    conversational=[
                        playbook("opt-in", "FORM-1", "Opt-in follow-up"),
                        playbook("purchase", "OF-1", "Purchase confirmation and onboarding"),
                        playbook("booking", "S-3", "Booking confirmation and reminders")],
                    conversational_not_present=[])
        env = {k: v for k, v in os.environ.items()
               if "SESSION_ID" not in k}
        env["OPENCLAW_SESSION_ID"] = "sess-reviewer-9"
        env["STAGE_GATE_CONTRACT"] = str(self.contract)
        proc = subprocess.run(
            [PY, str(WRITE_REVIEW), str(run), "automation-wiring", "stage",
             "--scores", json.dumps({"wiring": {"score": 9, "note": LONG_NOTE}}),
             "--verdict", "pass", "--artifact", "automation-wiring/checklist-wf-1.md",
             # Assembly fix (S8): S1's delta writer requires the SOP
             # evidentiary fields (Item 2); this fixture predates them.
             "--performed-check",
             "Opened the workflow checklist and the wiring receipt itself and checked every covered form and trigger against them.",
             "--next-current-artifact", "the automation-wiring stage receipt",
             "--author-session", "sess-author-1"],
            text=True, capture_output=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = gate(self.contract, "close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_uncovered_form_and_trigger_fail_close(self):
        run = self.build_wired_run()
        put_receipt(run, "publish-verify", public_url="https://example.com/p",
                    publish_waivers=WAIVER)
        gate(self.contract, "close", run, "publish-verify")
        write(run / "automation-wiring" / "checklist-wf-1.md", "WF checklist complete")
        put_receipt(run, "automation-wiring", workflows=[], conversational=[],
                    conversational_not_present=["purchase", "booking"],
                    ghl_pack_version="ghl-pack-1.0.0")
        proc = gate(self.contract, "close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("neither", proc.stdout)
        self.assertIn("conversational trigger", proc.stdout)


PROVENANCE = {
    "run_id": "run-test-1",
    "github": {"owner": "op", "repo": "pages", "branch": "main",
               "commit_sha": "abc1234"},
    "vercel": {"project_id": "prj_1", "deployment_id": "dpl_1",
               "url": "https://pages.example.com/"},
    "ghl": {"location_id": "loc_1", "funnel_id": "F-100"},
}


def build_deliverables(run, extra=None, skip_manifest_entry=None, unlisted_extra=None):
    files = {
        "page/index.html": "<html><body>page</body></html>",
        "assets/hero.png": PNG_BYTES,
        "copy/public-copy.md": "approved copy",
        "reports/REPORT.md": "run report",
        "reports/REPORT.json": "{}",
        "handoffs/automation-handoff.json": "{}",
        "receipts/intake.json": "{}",
        "provenance.json": json.dumps(PROVENANCE, indent=2),
    }
    files.update(extra or {})
    for rel, data in files.items():
        write(run / "deliverables" / rel, data)
    for rel, data in (unlisted_extra or {}).items():
        write(run / "deliverables" / rel, data)
    listed = sorted(set(files) | {"manifest.json"})
    if skip_manifest_entry:
        listed.remove(skip_manifest_entry)
    write_json(run / "deliverables" / "manifest.json",
               {"run_id": "run-test-1", "files": listed})
    return files


class DeliverablesCheckerTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-deliv-"))
        self.run = make_run(self.td)

    def check(self):
        return run_cli(CHECK_DELIVERABLES, self.run)

    def test_clean_folder_passes(self):
        build_deliverables(self.run)
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("manifest verified", proc.stdout)

    def test_unlisted_file_fails_by_name(self):
        build_deliverables(self.run, unlisted_extra={"assets/stray-notes.txt": "loose"})
        proc = self.check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stray-notes.txt", proc.stdout)

    def test_manifest_entry_missing_on_disk_fails(self):
        build_deliverables(self.run)
        (self.run / "deliverables" / "assets" / "hero.png").unlink()
        proc = self.check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("hero.png", proc.stdout)

    def test_browser_profile_dir_fails(self):
        build_deliverables(self.run)
        write(self.run / "deliverables" / "assets" / "chrome-profile" / "Cookies", "x")
        proc = self.check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("chrome-profile", proc.stdout)

    def test_credential_material_fails_without_printing_value(self):
        build_deliverables(self.run, extra={
            "copy/notes.md": "token: FIREBASE_REFRESH_TOKEN = 'supersecretvalue123'"})
        proc = self.check()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FIREBASE_REFRESH_TOKEN", proc.stdout)
        self.assertNotIn("supersecretvalue123", proc.stdout)


class GateReportDeliverablesTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s5-report-"))
        self.contract = fixture_contract(self.td)

    def complete_run(self, test_run=False):
        run = make_run(self.td, intake_extra={"test_run": test_run})
        gate(self.contract, "init", run)
        for stage in ("intake", "font-action-plan", "visual-mockup",
                      "responsive-html"):
            put_receipt(run, stage)
            proc = gate(self.contract, "close", run, stage)
            self.assertEqual(proc.returncode, 0, f"{stage}: {proc.stdout}")
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        put_receipt(run, "ghl-install-test")
        gate(self.contract, "close", run, "ghl-install-test")
        if test_run:
            put_receipt(run, "publish-verify", status="not_authorized")
        else:
            put_receipt(run, "publish-verify", public_url="https://example.com/p",
                        publish_waivers=WAIVER)
        proc = gate(self.contract, "close", run, "publish-verify")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        proc = gate(self.contract, "close", run, "automation-wiring")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        return run

    def test_report_refused_while_deliverables_fail(self):
        run = self.complete_run()
        proc = gate(self.contract, "report", run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("report refused", proc.stdout)
        self.assertFalse((run / "REPORT.md").exists())

    def test_report_carries_deliverables_line_when_clean(self):
        run = self.complete_run()
        build_deliverables(run)
        proc = gate(self.contract, "report", run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        report = (run / "REPORT.md").read_text()
        self.assertIn("Deliverables: complete (", report)
        self.assertIn("manifest verified", report)
        self.assertIn("**RUN COMPLETE**", report)

    def test_test_run_report_line(self):
        run = self.complete_run(test_run=True)
        build_deliverables(run)
        proc = gate(self.contract, "report", run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        report = (run / "REPORT.md").read_text()
        self.assertIn("**TEST RUN, NOT A PRODUCTION DELIVERY**", report)


if __name__ == "__main__":
    unittest.main()
