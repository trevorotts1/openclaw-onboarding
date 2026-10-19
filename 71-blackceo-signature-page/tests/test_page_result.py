#!/usr/bin/env python3
"""Functional tests for the S71-05 page-result / page-handoff emission
(scripts/page_result.py + scripts/write_page_result.py + the
stage_gate.py report-pass hook).

Fixture runs are TEST ONLY. Covered:
  (a) a recorded verified submission authorizes routing, with the
      next role taken from the route graph (product_selection and
      checkout variants, plus the free_entry journey mode);
  (b) capture-only / pending / failed / absent / forged submission
      records never authorize routing;
  (c) every emitted page-result.json validates against the actual
      schema file references/page-result.schema.json (the builder's
      own validator, cross-checked with the jsonschema package when
      installed), and the validator itself rejects tampered results;
  plus: stale route-graph hash (doc 07 section 10) blocks routing,
  an out-of-vocabulary route target refuses emission, legacy runs
  without a page-request are untouched, and the report pass emits
  the result for launch runs only.

Repair coverage (independent review defects D1-D5):
  D2 a receipt naming a different tenant/launch/request never
     authorizes (receipt binding); a receipt whose identity fields
     all match authorizes and records "bound"; a partial
     contradiction fails closed; an identifier-less receipt (bare
     string, or the contact/form dict shape) authorizes on presence
     alone and records "no_identity_fields";
  D3 a present-but-corrupt page-request.json is an error state
     (writer exit 2 naming the corruption; the report pass prints
     the FAIL line), never the legacy skip;
  D4 a refused emission writes neither artifact (no orphaned
     page-handoff.json);
  D5 a free_entry journey never relabels a purchase-progression
     target (upsell_1/downsell_1) as free_entry: emission refused;
  D1 the handoff's CTA action map attributes sl:interest-capture
     to the popup form's submit, not to the CTA click that opens
     the popup (component source: interest_popup.js onSubmit).
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
SCRIPTS = SKILL_ROOT / "scripts"
SCHEMA_PATH = SKILL_ROOT / "references" / "page-result.schema.json"
sys.path.insert(0, str(SCRIPTS))
import page_result  # noqa: E402

ORDER = ["intake", "copy", "font-action-plan", "desktop-wireframe",
         "mobile-tablet", "visual-mockup", "image-inventory-prompts",
         "image-generation-qc", "image-map-upload", "design-board", "final-mockups",
         "responsive-html", "ghl-install-test", "publish-verify",
         "automation-wiring"]

VERIFIED_SUBMISSION = {
    "event": "interest_verified",
    "state": "verified",
    "receipt": {"contact_id": "TEST-CONTACT-1", "form_id": "TEST-FORM-1",
                "source": "test fixture (TEST ONLY)"},
    "recorded_at": "2026-10-15T00:00:00+00:00",
}
PENDING_SUBMISSION = {
    "event": "interest_capture",
    "state": "pending_verification",
    "recorded_at": "2026-10-15T00:00:00+00:00",
}


def sha(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def route_graph(target_role, target_id):
    return {
        "schema_version": "1.0",
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "nodes": [
            {"page_id": "TEST-LANDING", "role": "landing"},
            {"page_id": target_id, "role": target_role},
            {"page_id": "TEST-THANK-YOU", "role": "thank_you"},
        ],
        "edges": [
            {"from": "TEST-LANDING", "event": "interest_submitted",
             "to": target_id, "guard": "verified_native_contact_submit"},
        ],
        "pending_failed_payment_behavior":
            "retain_current_purchase_state_until_resolved_or_explicit_decline",
        "test_only": True,
    }


def make_run(tmp, *, target_role="product_selection",
             target_id="TEST-SELECTION", submission=None,
             stale_hash=False, install=False, publish_status=None,
             close_through="responsive-html", blocked_stage=None,
             journey_mode=None, with_request=True):
    run = Path(tmp) / "run"
    (run / "private" / "receipts").mkdir(parents=True)
    (run / "private" / "reviews" / "copy").mkdir(parents=True)
    (run / "copy").mkdir()
    copy_files = {}
    for name, content in [
            ("copy/public-copy.md", "# Public copy (TEST ONLY)\n"),
            ("copy/internal-manuscript.md", "# Manuscript (TEST ONLY)\n"),
            ("copy/copy-manifest.json", "{}\n")]:
        (run / name).write_text(content)
        copy_files[name] = sha(content)
    graph_bytes = (json.dumps(route_graph(target_role, target_id),
                              indent=2) + "\n").encode()
    (run / "route-graph.json").write_bytes(graph_bytes)
    if with_request:
        request = {
            "schema_version": "1.0",
            "tenant_id": "TEST-TENANT",
            "location_id": "TEST-LOCATION",
            "launch_id": "TEST-LAUNCH",
            "revision": 1,
            "request_id": "TEST-REQUEST-1",
            "page_id": "TEST-LANDING",
            "page_role": "landing",
            "assigned_skill": 71,
            "approval_ref": "TEST-APPROVAL-1",
            "input_hash": "TEST-INPUT-HASH",
            "brand_ref": "TEST-ONLY-BRAND",
            "brand_hash": "TEST-ONLY-BRAND-HASH",
            "route_graph_ref": "route-graph.json",
            "route_graph_hash": "0" * 64 if stale_hash else sha(graph_bytes),
            "offer_refs": [],
            "copy_profile": "standard",
            "allowed_write_target": "local_only",
            "test_only": True,
        }
        (run / "page-request.json").write_text(json.dumps(request, indent=2))
    if journey_mode:
        (run / "launch.json").write_text(
            json.dumps({"journey_mode": journey_mode}))
    (run / "intake.json").write_text(json.dumps(
        {"page_version": "standard", "test_run": True}))
    stages, receipts = {}, {}
    upto = ORDER.index(close_through)
    for i, stage in enumerate(ORDER):
        if stage == "automation-wiring":
            stages[stage] = {
                "status": "not_applicable",
                "receipt_status": "not_applicable",
                "reason": "intake publish_target/automation_scope do not "
                          "require it (TEST fixture)"}
            continue
        if stage == blocked_stage:
            stages[stage] = {"status": "blocked",
                             "receipt_status": "blocked",
                             "reason": "TEST blocker"}
            receipts[stage] = {"status": "blocked",
                               "blocked_reason": "TEST blocker",
                               "author_session": "author-A"}
            continue
        if i <= upto:
            entry = {"status": "closed", "receipt_status": "pass",
                     "artifact_hashes": {}}
            if stage == "copy":
                entry["artifact_hashes"] = dict(copy_files)
            stages[stage] = entry
            receipts[stage] = {
                "status": "pass", "author_session": "author-A",
                "started_at": "2026-10-15T00:00:00+00:00",
                "finished_at": "2026-10-15T00:01:00+00:00"}
        else:
            stages[stage] = {"status": "working"}
    if install:
        stages["ghl-install-test"] = {
            "status": "closed", "receipt_status": "pass",
            "artifact_hashes": {}}
        receipts["ghl-install-test"] = {
            "status": "pass", "author_session": "author-A",
            "started_at": "2026-10-15T00:02:00+00:00",
            "finished_at": "2026-10-15T00:03:00+00:00"}
        (run / "handoff").mkdir()
        (run / "handoff" / "automation-handoff.json").write_text(json.dumps({
            "location_id": "TEST-LOCATION", "funnel_id": "TEST-FUNNEL",
            "page_id": "TEST-LANDING",
            "forms": [{"form_id": "TEST-FORM-1", "form_name": "Interest",
                       "page_section": "cta",
                       "optin_fields": ["name", "email", "phone"]}],
            "conversational_requirements": {"triggers": ["opt-in"]}}))
    if publish_status:
        stages["publish-verify"] = {
            "status": "closed", "receipt_status": publish_status}
        receipts["publish-verify"] = {
            "status": publish_status, "author_session": "author-A"}
    (run / "private" / "state.json").write_text(json.dumps({
        "run_id": "00000000-0000-4000-8000-0000000000aa",
        "stages": stages, "receipts": {}, "items": {}}))
    for stage, receipt in receipts.items():
        (run / "private" / "receipts" / f"{stage}.json").write_text(
            json.dumps(receipt))
    review = {
        "item": "stage", "artifact": "copy/public-copy.md",
        "artifact_sha256": copy_files["copy/public-copy.md"],
        "author_session": "author-A", "reviewer_session": "reviewer-B",
        "reviewed_at": "2026-10-15T00:00:00+00:00", "criteria": {},
        "verdict": "pass", "automatic_failures": [], "repair_attempt": 0,
        "specific_defects": [],
        "performed_check": "TEST fixture review record",
        "next_current_artifact": "copy/public-copy.md",
        "independent_review": True}
    (run / "private" / "reviews" / "copy" / "stage.review.json").write_text(
        json.dumps(review))
    if submission is not None:
        (run / "interest-submission.json").write_text(json.dumps(submission))
    return run


def run_writer(run):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "write_page_result.py"), str(run)],
        capture_output=True, text=True)


def load(run, name):
    return json.loads((run / name).read_text())


def schema():
    return json.loads(SCHEMA_PATH.read_text())


def assert_valid_result(run):
    result = load(run, "page-result.json")
    errors = page_result.validate_against_schema(result, schema())
    assert not errors, f"page-result violates its schema: {errors}"
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        jsonschema.validate(result, schema())
    return result


def assert_handoff_artifact_hash(run, result):
    refs = {a["path"]: a["sha256"] for a in result["artifacts"]}
    assert "page-handoff.json" in refs, result["artifacts"]
    actual = sha((run / "page-handoff.json").read_bytes())
    assert refs["page-handoff.json"] == actual, \
        "page-result must reference the handoff with its real hash"


def main():
    # The schema validator itself must bite (case c honesty).
    bad = {"schema_version": "1.0", "status": "bogus"}
    assert page_result.validate_against_schema(bad, schema()), \
        "validator must reject a result with missing fields and a bad enum"
    extra = dict(schema_required_fixture())
    extra["next_role"] = "product_selection"
    assert page_result.validate_against_schema(extra, schema()), \
        "validator must reject additional properties (schema is closed)"

    with tempfile.TemporaryDirectory() as tmp:
        # (a) verified submission -> routing authorized, product_selection.
        run = make_run(tmp, submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        assert_handoff_artifact_hash(run, result)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is True, handoff["routing"]
        assert handoff["next_role"] == "product_selection", handoff
        assert handoff["next_page_id"] == "TEST-SELECTION", handoff
        assert handoff["route"]["guard"] == "verified_native_contact_submit"
        assert handoff["route"]["hash_matches"] is True
        assert handoff["form_mapping"]["native_field_map"] == {
            "first_name": "first_name", "last_name": "last_name",
            "email": "email", "phone": "phone"}
        assert handoff["submission"]["state"] == "verified"
        assert result["status"] == "locally_verified", result["status"]
        assert result["author_session"] == "author-A", result
        assert result["reviewer_session"] == "reviewer-B", result
        assert result["independent_review"] is True, result
        assert result["proof_class"] == "L1", result
        assert result["test_only"] is True, result
        assert result["native_bindings_ref"] is None, result

    with tempfile.TemporaryDirectory() as tmp:
        # (a2) verified submission -> checkout next role.
        run = make_run(tmp, target_role="checkout",
                       target_id="TEST-CHECKOUT",
                       submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is True
        assert handoff["next_role"] == "checkout", handoff

    with tempfile.TemporaryDirectory() as tmp:
        # (a3) free-entry journey: target is the thank-you destination,
        # the recorded next role is the approved free-entry value.
        run = make_run(tmp, target_role="thank_you",
                       target_id="TEST-THANK-YOU", journey_mode="free_entry",
                       submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["next_role"] == "free_entry", handoff
        assert handoff["routing"]["authorized"] is True

    with tempfile.TemporaryDirectory() as tmp:
        # (b) capture-only / pending: never routes.
        run = make_run(tmp, submission=PENDING_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False, handoff["routing"]
        assert handoff["submission"]["state"] == "pending_verification"
        assert any("not verified" in b for b in result["blockers"]), \
            result["blockers"]

    with tempfile.TemporaryDirectory() as tmp:
        # (b2) no submission record at all: never routes.
        run = make_run(tmp)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False
        assert handoff["submission"] is None

    with tempfile.TemporaryDirectory() as tmp:
        # (b3) forged: capture event wearing a verified claim.
        forged = dict(VERIFIED_SUBMISSION)
        forged["event"] = "interest_capture"
        run = make_run(tmp, submission=forged)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False, handoff["routing"]
        assert handoff["submission"]["state"] == "pending_verification"

    with tempfile.TemporaryDirectory() as tmp:
        # (b4) verified event without its receipt: never routes.
        bare = {"event": "interest_verified", "state": "verified",
                "recorded_at": "2026-10-15T00:00:00+00:00"}
        run = make_run(tmp, submission=bare)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False, handoff["routing"]

    with tempfile.TemporaryDirectory() as tmp:
        # (b5) failed submission: never routes.
        failed = {"event": "interest_capture", "state": "failed",
                  "recorded_at": "2026-10-15T00:00:00+00:00"}
        run = make_run(tmp, submission=failed)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False
        assert handoff["submission"]["state"] == "failed"

    with tempfile.TemporaryDirectory() as tmp:
        # Stale next-role hash: even a verified submission cannot route.
        run = make_run(tmp, submission=VERIFIED_SUBMISSION, stale_hash=True)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False, handoff["routing"]
        assert handoff["route"]["hash_matches"] is False
        assert any("stale next-role hash" in b for b in result["blockers"]), \
            result["blockers"]

    with tempfile.TemporaryDirectory() as tmp:
        # Installed run: status + native bindings + install executed.
        run = make_run(tmp, submission=VERIFIED_SUBMISSION, install=True)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert result["status"] == "installed_test_verified", result
        assert result["native_bindings_ref"] == \
            "handoff/automation-handoff.json", result
        assert handoff["form_mapping"]["native_form_id"] == "TEST-FORM-1"
        assert handoff["install_request"]["status"] == "executed"

    with tempfile.TemporaryDirectory() as tmp:
        # Install verified, publication held: ready_for_activation.
        run = make_run(tmp, submission=VERIFIED_SUBMISSION, install=True,
                       publish_status="not_authorized")
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        assert result["status"] == "ready_for_activation", result
        assert any("not_authorized" in b for b in result["blockers"]), \
            result["blockers"]

    with tempfile.TemporaryDirectory() as tmp:
        # A blocked stage surfaces as status blocked.
        run = make_run(tmp, blocked_stage="copy",
                       submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        assert result["status"] == "blocked", result

    with tempfile.TemporaryDirectory() as tmp:
        # Out-of-vocabulary route target: emission refused (exit 2).
        run = make_run(tmp, target_role="upsell_1",
                       target_id="TEST-UPSELL", submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert not (run / "page-result.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # Legacy run: no page-request -> writer skips, writes nothing.
        run = make_run(tmp, with_request=False)
        r = run_writer(run)
        assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
        assert not (run / "page-result.json").exists()
        assert not (run / "page-handoff.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # The report pass emits the result for a launch run.
        run = make_run(tmp, submission=VERIFIED_SUBMISSION)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "stage_gate.py"), "report",
             str(run)], capture_output=True, text=True)
        assert (run / "REPORT.md").exists(), r.stdout + r.stderr
        assert (run / "page-result.json").exists(), r.stdout + r.stderr
        assert (run / "page-handoff.json").exists(), r.stdout + r.stderr
        assert "page-result: wrote" in r.stdout, r.stdout
        assert_valid_result(run)

    with tempfile.TemporaryDirectory() as tmp:
        # The report pass leaves a legacy run untouched.
        run = make_run(tmp, with_request=False)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "stage_gate.py"), "report",
             str(run)], capture_output=True, text=True)
        assert (run / "REPORT.md").exists(), r.stdout + r.stderr
        assert not (run / "page-result.json").exists()
        assert not (run / "page-handoff.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # D2: a verified record whose receipt names a DIFFERENT
        # tenant/launch/request is another run's receipt: it never
        # authorizes routing (reviewer probe R4).
        cross_run = {
            "event": "interest_verified", "state": "verified",
            "receipt": {"tenant_id": "OTHER-TENANT",
                        "launch_id": "OTHER-LAUNCH",
                        "request_id": "OTHER-REQUEST",
                        "contact_id": "OTHER-CONTACT",
                        "form_id": "TEST-FORM-1"},
            "recorded_at": "2026-10-15T00:00:00+00:00"}
        run = make_run(tmp, submission=cross_run)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        result = assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False, handoff["routing"]
        assert handoff["submission"]["receipt_binding"] == "contradicted", \
            handoff["submission"]
        assert any("not bound to this run" in b
                   for b in result["blockers"]), result["blockers"]

    with tempfile.TemporaryDirectory() as tmp:
        # D2: a receipt whose identity fields all match the
        # page-request is bound to this run and authorizes.
        bound = {
            "event": "interest_verified", "state": "verified",
            "receipt": {"tenant_id": "TEST-TENANT",
                        "location_id": "TEST-LOCATION",
                        "launch_id": "TEST-LAUNCH",
                        "request_id": "TEST-REQUEST-1",
                        "page_id": "TEST-LANDING",
                        "contact_id": "TEST-CONTACT-9"},
            "recorded_at": "2026-10-15T00:00:00+00:00"}
        run = make_run(tmp, submission=bound)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is True, handoff["routing"]
        assert handoff["submission"]["receipt_binding"] == "bound", \
            handoff["submission"]

    with tempfile.TemporaryDirectory() as tmp:
        # D2: a partial contradiction (one identity field right, one
        # wrong) still fails closed.
        partial = {
            "event": "interest_verified", "state": "verified",
            "receipt": {"tenant_id": "TEST-TENANT",
                        "launch_id": "WRONG-LAUNCH",
                        "contact_id": "TEST-CONTACT-9"},
            "recorded_at": "2026-10-15T00:00:00+00:00"}
        run = make_run(tmp, submission=partial)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is False, handoff["routing"]
        assert handoff["submission"]["receipt_binding"] == "contradicted"

    with tempfile.TemporaryDirectory() as tmp:
        # D2: a bare-string receipt carries no identity fields and is
        # accepted on presence alone (documented choice in
        # scripts/page_result.py), recorded honestly in the handoff.
        string_receipt = {
            "event": "interest_verified", "state": "verified",
            "receipt": "API-RECEIPT-TEST-1",
            "recorded_at": "2026-10-15T00:00:00+00:00"}
        run = make_run(tmp, submission=string_receipt)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        assert_valid_result(run)
        handoff = load(run, "page-handoff.json")
        assert handoff["routing"]["authorized"] is True, handoff["routing"]
        assert handoff["submission"]["receipt_binding"] == \
            "no_identity_fields", handoff["submission"]

    with tempfile.TemporaryDirectory() as tmp:
        # D1: the CTA action map attributes the capture event to the
        # popup form's submit; the CTA click only opens the popup
        # (interest_popup.js dispatches sl:interest-capture inside
        # onSubmit, wired to the form's submit event).
        run = make_run(tmp, submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 0, r.stdout + r.stderr
        handoff = load(run, "page-handoff.json")
        cam = handoff["cta_action_map"]
        click = [e for e in cam if e.get("on") == "cta_click"]
        submit = [e for e in cam if e.get("on") == "form_submit"]
        assert len(click) == 1 and "emits" not in click[0], cam
        assert click[0].get("opens_component") == "interest-popup", cam
        assert len(submit) == 1, cam
        assert submit[0].get("emits") == "sl:interest-capture", cam

    with tempfile.TemporaryDirectory() as tmp:
        # D3: a present-but-corrupt page-request.json is an error
        # state, distinguishable from a legacy run: the writer exits
        # 2 naming the corruption and writes nothing (reviewer E5).
        run = make_run(tmp)
        (run / "page-request.json").write_text("{corrupt json")
        r = run_writer(run)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert "corrupt" in r.stdout, r.stdout
        assert not (run / "page-result.json").exists()
        assert not (run / "page-handoff.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # D3: a page-request that parses but is not a JSON object is
        # likewise corrupt, not legacy.
        run = make_run(tmp)
        (run / "page-request.json").write_text("[1, 2, 3]")
        r = run_writer(run)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        # D3: the report pass surfaces a corrupt page-request as a
        # visible FAIL instead of silently treating the run as
        # non-launch.
        run = make_run(tmp)
        (run / "page-request.json").write_text("{corrupt json")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "stage_gate.py"), "report",
             str(run)], capture_output=True, text=True)
        assert "FAIL: page-result emission" in r.stdout, r.stdout
        assert "corrupt" in r.stdout, r.stdout
        assert not (run / "page-result.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # D4: a schema-invalid result (revision passed through as a
        # string) refuses emission AND leaves no orphaned
        # page-handoff.json behind (reviewer probe E6).
        run = make_run(tmp, submission=VERIFIED_SUBMISSION)
        req = json.loads((run / "page-request.json").read_text())
        req["revision"] = "one"
        (run / "page-request.json").write_text(json.dumps(req))
        r = run_writer(run)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert not (run / "page-result.json").exists()
        assert not (run / "page-handoff.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # D5: in a free_entry journey, an upsell_1 target keeps its
        # own role and is never relabeled free_entry: emission is
        # refused, naming the role (reviewer probe E7).
        run = make_run(tmp, target_role="upsell_1",
                       target_id="TEST-UPSELL", journey_mode="free_entry",
                       submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert "upsell_1" in r.stdout, r.stdout
        assert not (run / "page-result.json").exists()
        assert not (run / "page-handoff.json").exists()

    with tempfile.TemporaryDirectory() as tmp:
        # D5: same refusal for a downsell_1 target under free_entry.
        run = make_run(tmp, target_role="downsell_1",
                       target_id="TEST-DOWNSELL", journey_mode="free_entry",
                       submission=VERIFIED_SUBMISSION)
        r = run_writer(run)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert not (run / "page-result.json").exists()
        assert not (run / "page-handoff.json").exists()

    print("PASS: page-result emission honors the verified-submission "
          "routing rule, the next-role vocabulary and the schema file")
    return 0


def schema_required_fixture():
    """A minimally schema-valid result, for the additionalProperties
    probe in main()."""
    return {
        "schema_version": "1.0", "tenant_id": "T", "location_id": "L",
        "launch_id": "LA", "revision": 1, "request_id": "R",
        "input_hash": "H", "page_id": "P", "status": "authored",
        "artifacts": [], "author_session": "a", "reviewer_session": None,
        "independent_review": False, "proof_class": "L0", "blockers": [],
        "native_bindings_ref": None, "test_only": True,
    }


if __name__ == "__main__":
    sys.exit(main())
