#!/usr/bin/env python3
"""Build the R71H joint dry-run fixture run (S71-08 P3).

    python3 tests/fixtures/r71h-dry-run/build_fixture.py <target_run_dir>

This is a FIXTURE builder. It writes a fictional install's INPUT
records (intake, funnel-completion, click-through, install receipt,
launch wiring inputs) into the target run directory, then drives the
REAL stage gate (scripts/stage_gate.py, the shipped stage contract)
through the two closes the R71H seam exercises:

  1. ghl-install-test close: the gate's validators re-run against the
     fixture records, the R71H emitter (scripts/automation_handoff.py)
     produces handoff/automation-handoff.json and the dispatch
     envelope handoff/automation-request.json from the records, and
     the gate hash-locks the hand-off in state
     (stages.ghl-install-test.handoff_sha256).
  2. publish-verify close: the publish validator fetches the fixture
     page (served by this builder on 127.0.0.1 for the duration of
     the build only) and the gate verifies the hand-off file against
     the locked hash.

Nothing here is hand-written output: the hand-off, the envelope, the
emission record, the state lock, the browser-hygiene receipts, and
the publish fetch record are all produced by the shipped code from
the fixture input records. The fixture proves the seam's producer
side executes end to end; it is NOT live proof of anything (no real
location, funnel, page, form, or launch exists behind these records,
and nothing is dispatched anywhere).

The fixture location ID value reaches the emitter the same way it
does in a real install: through the environment variable the intake
names (GHL_LOCATION_ID), set by this builder to the fictional value
"fixture-location-001" for the gate subprocesses only.

Exits 0 when both closes pass; exits 1 (printing the gate output)
otherwise. Refuses to build into a non-empty directory.
"""
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[3]
GATE = SKILL_ROOT / "scripts" / "stage_gate.py"
BROWSER = SKILL_ROOT / "scripts" / "browser_sessions.py"
VALIDATE_INSTALL = SKILL_ROOT / "scripts" / "validate_install.py"
PY = sys.executable

LOCATION_ID = "fixture-location-001"
LOCATION_ENV = {"GHL_LOCATION_ID": LOCATION_ID}

FULL_CREDS = {
    "pit": {"variable": "GHL_PRIVATE_INTEGRATION_TOKEN", "present": True},
    "location_id": {"variable": "GHL_LOCATION_ID", "present": True},
    "firebase_refresh_token": {"variable": "GHL_FIREBASE_REFRESH_TOKEN",
                               "present": True},
}

# A real 1x1 PNG, used for the install evidence screenshots.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c62600164000000ffff030000060005"
    "57bfab7a0000000049454e44ae426082")

PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<title>R71H Fixture Page</title></head>
<body>
<h1>Fixture page for the R71H joint dry-run</h1>
<p>This page exists only as the publish target of the Skill 71
R71H seam fixture run. It is fictional, it sells nothing, and it is
served on loopback by the fixture builder only while the fixture's
publish-verify close runs.</p>
</body>
</html>
"""


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def write_json(path: Path, obj):
    write(path, json.dumps(obj, indent=2) + "\n")


def run_cli(script, *args, env=None):
    full_env = {**os.environ, **LOCATION_ENV, **(env or {})}
    return subprocess.run([PY, str(script), *map(str, args)],
                          text=True, capture_output=True, env=full_env)


def funnel_completion():
    return {
        "status": "complete",
        "funnel": {"funnel_id": "F-100", "name": "Fixture Funnel",
                   "created": False, "existence_check": True,
                   "rail": "browser"},
        "steps": [
            {"order": 1, "step_id": "S-1", "name": "Opt-in",
             "type": "optin",
             "binding": {"kind": "ghl_page", "page_id": "P-200"},
             "rail": "browser"},
            {"order": 2, "step_id": "S-2", "name": "Order",
             "type": "order",
             "binding": {"kind": "external_embed",
                         "embed_url": "https://pages.example.com/order",
                         "repo": "op/pages", "deployment_id": "dpl_1"},
             "rail": "browser"},
            {"order": 3, "step_id": "S-3", "name": "Book",
             "type": "booking",
             "binding": {"kind": "ghl_page", "page_id": "P-201"},
             "rail": "browser"},
        ],
        "forms": [
            {"form_id": "FORM-1", "name": "Opt-in form",
             "attached_to_step": "Opt-in",
             "optin_fields": ["name", "email", "phone"],
             "created": True, "existence_check": True, "rail": "browser"},
            {"form_id": "FORM-2", "name": "Order form",
             "attached_to_step": "Order",
             "created": True, "existence_check": True, "rail": "browser"},
            {"form_id": "FORM-3", "name": "Booking form",
             "attached_to_step": "Book",
             "created": False, "existence_check": True, "rail": "browser"},
        ],
        "popups": [
            {"name": "Exit-intent popup", "step": "Opt-in",
             "trigger_element": "exit-intent", "created": False,
             "existence_check": True, "rail": "browser"},
        ],
        "click_actions": [
            {"element": "hero-cta", "step": "Opt-in",
             "verified_by_clickthrough": True, "rail": "browser"},
        ],
        "order_forms": [
            {"step": "Order", "order_form_id": "OF-1",
             "product_ids": ["PR-1"], "bound": True, "rail": "browser"},
        ],
        "products": [
            {"product_id": "PR-1", "name": "Fixture Product",
             "price": 497, "currency": "USD", "created": False,
             "existence_check": True, "rail": "api"},
        ],
        "payment": {"provider_present": True},
    }


def clickthrough():
    return {
        "steps_visited": ["Opt-in", "Order", "Book"],
        "form_submissions": [
            {"form_id": fid, "performed": True, "submissions_count": 1,
             "test_contact_id": "FIXTURE-CONTACT-1",
             "live_charge_made": False}
            for fid in ("FORM-1", "FORM-2", "FORM-3")],
        "live_charge_made": False,
        "order_step": {"rendered": True, "product_id": "PR-1",
                       "price": 497},
        "booking_step": {"rendered": True, "calendar_shown": True},
        "screenshots": ["ghl-install-test/evidence/desktop.png",
                        "ghl-install-test/evidence/mobile.png"],
    }


def write_inputs(run: Path):
    # A fixture brand record: founder-photo verification has nothing
    # to check (no founder photos), and the grade thresholds carry
    # nominal fixture values so the publish grade leg evaluates the
    # fixture on its own recorded terms. No image grading runs in
    # this fixture; the values gate nothing here.
    brand = {"grade": {"min_mean_saturation": 0.10, "min_luma_std": 10.0},
             "founder_photos": [], "font_policy": {}}
    write_json(run / "brand-fixture.json", brand)
    intake = {
        "page_version": "standard",
        "brand_owner": "Fixture",
        "brand_file": "brand-fixture.json",
        "brand_id": "fixture-brand",
        "page_name": "R71H joint dry-run fixture (fictional)",
        "client": "FIXTURE",
        "creative_direction": None,
        "image_cap": 5,
        "image_engine": "kie",
        # The gate refuses a publish-verify PASS close for a run whose
        # intake records test_run true (fix plan Item 6 rule 1: a test
        # run closes publish as not_authorized). This fixture exists to
        # exercise the PASS close's hand-off hash verification, so it
        # follows the same intake shape the P1/P2 test fixtures use.
        # The fixture's nature is carried by its name, its records,
        # and this folder's README, never by this flag.
        "test_run": False,
        "layout_waivers": [
            {"gate": "layout-references",
             "reason": "fixture run: no layout stage closes in this "
                       "fixture; recorded for intake-shape parity with "
                       "the P1/P2 fixtures"}],
        "publish_target": "ghl",
        "automation_scope": "workflows",
        "credentials": FULL_CREDS,
    }
    write_json(run / "intake.json", intake)
    # The launch wiring inputs (doc 02 section 7 / doc 14 Phase B
    # received inputs): launch identity, plan approval reference, and
    # the per-form workflow spec the envelope is built from. FORM-1
    # exercises the contact_tag mechanism, FORM-2 the native Tier 4
    # mechanism, FORM-3 a no_workflow_reason exception entry.
    write_json(run / "page-request.json", {
        "launch_id": "FIXTURE-LNCH-001",
        "plan_approval_ref": "fixture-plan-approval-001",
        "automation": {
            "folder": "FIXTURE / R71H Dry-Run",
            "workflows": [
                {"form_id": "FORM-1", "slug": "fixture-optin-followup",
                 "name": "fixture-optin-followup",
                 "expected_steps": 4, "allow_multiple": False,
                 "mechanism": {"type": "contact_tag",
                               "tag": "fixture-optin-signed-up"}},
                {"form_id": "FORM-2",
                 "slug": "fixture-order-confirmation",
                 "name": "fixture-order-confirmation",
                 "expected_steps": 3, "allow_multiple": True,
                 "mechanism": {"type": "native",
                               "build_method": "tier4-browser-backstop"}},
                {"form_id": "FORM-3",
                 "no_workflow_reason":
                     "fixture launch plan: the booking form's reminders "
                     "are owned by the calendar workflow outside this "
                     "fixture; recorded as an exception so the dry-run "
                     "exercises the exception path"},
            ]}})
    write(run / "ghl-install-test" / "install-steps.md",
          "Fixture install steps: the fictional page was installed "
          "into the fixture funnel F-100 as page P-200; the three "
          "steps were bound and the click-through recorded. This file "
          "is a fixture record for the R71H joint dry-run.\n")
    write_json(run / "ghl-install-test" / "funnel-completion.json",
               funnel_completion())
    write_json(run / "ghl-install-test" / "clickthrough.json",
               clickthrough())
    write(run / "ghl-install-test" / "evidence" / "desktop.png", PNG_BYTES)
    write(run / "ghl-install-test" / "evidence" / "mobile.png", PNG_BYTES)
    write_json(run / "private" / "receipts" / "ghl-install-test.json", {
        "stage": "ghl-install-test", "status": "pass",
        "author_agent": "fixture-builder",
        "author_session": "fixture-session-author",
        "started_at": "2026-10-16T09:00:00+00:00",
        "finished_at": "2026-10-16T09:20:00+00:00",
        "artifacts": [],
        "install": {
            "target": {"kind": "ghl", "funnel_or_site_id": "F-100",
                       "page_id_or_url": "P-200"},
            "journey_checks": {
                "cta_clicks": [
                    {"label": "Hero CTA", "destination": "step:Order",
                     "ok": True}],
                "form_submit_test": {
                    "performed": True, "ok": True,
                    "test_contact_id": "FIXTURE-CONTACT-1",
                    "submissions_count": 1},
                "popup_open_close": {"ok": True},
                "mobile_keyboard_scroll": {"ok": True}},
            "sales_check": {"mode": "test", "live_charge_made": False},
        }})
    write(run / "fixture-page.html", PAGE_HTML)


class _PageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        body = PAGE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def register_session(run: Path, stage: str, name: str, run_id: str):
    proc = run_cli(BROWSER, "register-open", run, "--name", name,
                   "--stage", stage, "--engine", "agent-browser",
                   "--binding", "session", "--run-id", run_id,
                   "--via", "fixture-builder")
    if proc.returncode != 0:
        raise RuntimeError(f"register-open failed: {proc.stdout}")
    proc = run_cli(BROWSER, "register-close", run, "--name", name,
                   "--via", "fixture-builder")
    if proc.returncode != 0:
        raise RuntimeError(f"register-close failed: {proc.stdout}")


def gate_close(run: Path, stage: str):
    proc = run_cli(GATE, "close", run, stage)
    if proc.returncode != 0:
        raise RuntimeError(
            f"gate close {stage} refused:\n{proc.stdout}")
    return proc.stdout


def build(run: Path):
    """Build the fixture run at `run` (created fresh). Returns a dict
    with the gate outputs and the hand-off hash. Raises RuntimeError
    naming the failing step."""
    if run.exists() and any(run.iterdir()):
        raise RuntimeError(f"target run dir is not empty: {run}")
    run.mkdir(parents=True, exist_ok=True)
    write_inputs(run)
    proc = run_cli(GATE, "init", run)
    if proc.returncode != 0:
        raise RuntimeError(f"gate init failed:\n{proc.stdout}")
    state = json.loads((run / "private" / "state.json").read_text())
    run_id = state.get("run_id", "")

    register_session(run, "ghl-install-test", "fixture-install-session",
                     run_id)
    install_out = gate_close(run, "ghl-install-test")
    handoff_path = run / "handoff" / "automation-handoff.json"
    if not handoff_path.is_file():
        raise RuntimeError("install close passed but no hand-off was "
                           "emitted")
    import hashlib
    digest = hashlib.sha256(handoff_path.read_bytes()).hexdigest()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _PageHandler)
    port = server.server_address[1]
    public_url = f"http://127.0.0.1:{port}/"
    try:
        import threading
        thread = threading.Thread(target=server.serve_forever,
                                  daemon=True)
        thread.start()
        write_json(run / "publish-verify" / "receipts"
                   / "loopback-publication.json", {
                       "fixture": True,
                       "served_by": "tests/fixtures/r71h-dry-run/"
                                    "build_fixture.py",
                       "public_url": public_url,
                       "note": "the fixture page (fixture-page.html in "
                               "this run) was served on loopback only "
                               "for the publish-verify close; the URL "
                               "is not live and resolves nowhere after "
                               "the build"})
        write_json(run / "private" / "receipts" / "publish-verify.json", {
            "stage": "publish-verify", "status": "pass",
            "author_agent": "fixture-builder",
            "author_session": "fixture-session-author",
            "started_at": "2026-10-16T09:25:00+00:00",
            "finished_at": "2026-10-16T09:35:00+00:00",
            "artifacts": [],
            "public_url": public_url})
        register_session(run, "publish-verify",
                         "fixture-publish-session", run_id)
        # Generate the fetch record once through the real validator;
        # the gate close re-runs it and overwrites it with the fetch
        # performed during the close itself.
        proc = run_cli(VALIDATE_INSTALL, run, "publish")
        if proc.returncode != 0:
            raise RuntimeError(
                f"publish validator failed before close:\n{proc.stdout}")
        publish_out = gate_close(run, "publish-verify")
    finally:
        server.shutdown()
        server.server_close()
    return {"install_close": install_out, "publish_close": publish_out,
            "handoff_sha256": digest, "public_url": public_url}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: build_fixture.py <target_run_dir>")
        return 2
    run = Path(argv[0]).resolve()
    try:
        result = build(run)
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"BUILT: fixture run at {run}")
    print(f"handoff_sha256: {result['handoff_sha256']}")
    print("ghl-install-test close: PASS (emitter produced the hand-off "
          "and envelope; hash locked in state)")
    print("publish-verify close: PASS (fetch verdict pass; hand-off "
          "verified against the locked hash)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
