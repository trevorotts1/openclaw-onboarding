#!/usr/bin/env python3
"""test_item33a_ghl_ops.py - FIX-PLAN Item 33a (the presentations to
Skill 44 operations seam: ghl-ops-request.json out, ghl-ops-receipt.json
back).

Pins, against fixture runs in a real run-folder layout:
  * the writer emits a schema-valid request for the standard operation
    set (checkout form, checkout workflow trigger coverage, checkout test
    submission, gate form, gate workflow, gate test submission), with the
    Wiring Gate verification expectations named on every operation;
  * the payment-sandbox election adds the product and order-form
    binding operations; live payment is never requested;
  * approved-URL reuse omits the checkout form operations (the
    producer's own posture), waivers emit no request, a gate that fails
    closed exits 3, a missing offer blocks with exit 5;
  * a booking calendar named in intake yields the calendar operation;
  * re-emission increments request_version;
  * the reader judges: absent receipt = pending (exit 0); a complete
    receipt (every read-back present and ok) = complete; a success claim
    WITHOUT its read-back = unverified, never success; a partial
    read-back = partial; a failed claim = failed; a stale
    request_version or a wrong location = invalid.

Schema validation is structural (the shipped schema files' required
keys plus ghl_ops.validate_request): jsonschema is not a repo
dependency, matching the page-brief seam's posture (Item 20).

Flat file inside tests/, manages its own import path - matching every
sibling in this directory. Offline and deterministic: no network, no
GHL call, no caf invocation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import ghl_ops as go  # noqa: E402


def _intake(**brief_over) -> dict:
    brief = {"OFFER_NAME": "Momentum Method", "FINAL_PRICE": "$997"}
    brief.update(brief_over)
    return {"deck_slug": "acme-ops", "company": "Acme Co",
            "GHL_LOCATION_ID": "loc-test-1",
            "pre_presentation_capture": {
                "WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "yes"},
            "deck_brief": brief}


def _mk_run(base: Path, name: str, intake: dict) -> Path:
    run = base / name
    (run / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run / go.INTAKE_REL).write_text(json.dumps(intake), encoding="utf-8")
    return run


def _readback(op: dict, object_id: str, drop: str = "",
              falsify: str = "") -> list:
    entries = []
    for e in op["expect"]:
        if e["check"] == drop:
            continue
        entry = {"check": e["check"],
                 "ok": e["check"] != falsify,
                 "observed": "pytest fixture"}
        if e["check"] == go.CHECK_OBJECT_EXISTS:
            entry["object_id"] = object_id
        entries.append(entry)
    return entries


def _receipt(request: dict, run_name: str, mutate=None) -> dict:
    results = []
    for op in request["operations"]:
        oid = f"obj-{op['op_id']}"
        claimed = "verified" if op["kind"] == go.OP_TEST_SUBMISSION \
            else "created"
        results.append({"op_id": op["op_id"], "kind": op["kind"],
                        "status_claimed": claimed,
                        "remote": {"object_id": oid},
                        "readback": _readback(op, oid)})
    receipt = {"schema": go.RECEIPT_SCHEMA_NAME,
               "schema_version": go.SCHEMA_VERSION,
               "request_id": request["request_id"],
               "request_version": request["request_version"],
               "scope": {"run_id": run_name, "deck_slug": "acme-ops",
                         "location_id": "loc-test-1"},
               "execution": {"execution_id": "gx_pytest000001",
                             "access_tier_used": "tier0_caf_firebase"},
               "results": results}
    if mutate:
        receipt = mutate(receipt)
    return receipt


def _write_receipt(run: Path, receipt: dict) -> None:
    path = run / go.RECEIPT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt), encoding="utf-8")


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------
def test_writer_emits_schema_valid_request_standard_ops(tmp_path):
    run = _mk_run(tmp_path, "run-std", _intake())
    code, req = go.build_request(run, "install")
    assert code == go.EXIT_OK
    assert (run / go.REQUEST_REL).exists()
    assert go.validate_request(req) == []
    schema = json.loads(
        (SCRIPTS / "ghl-ops-request.schema.json").read_text())
    assert set(schema["required"]) <= set(req)
    assert req["schema"] == "ghl-ops-request"
    assert req["executor"]["owner_skill"] == "44-convert-and-flow-operator"
    kinds = [o["kind"] for o in req["operations"]]
    assert kinds == [go.OP_FORM, go.OP_WORKFLOW, go.OP_TEST_SUBMISSION,
                     go.OP_FORM, go.OP_WORKFLOW, go.OP_TEST_SUBMISSION]
    for op in req["operations"]:
        assert op["expect"], "every operation names its read-back checks"
    workflow = req["operations"][1]
    checks = {e["check"] for e in workflow["expect"]}
    assert go.CHECK_TRIGGER_BOUND in checks
    assert workflow["spec"]["trigger"]["type"] == "form_submitted"
    form_checks = {e["check"] for e in req["operations"][0]["expect"]}
    assert {go.CHECK_OBJECT_EXISTS, go.CHECK_ATTACHED,
            go.CHECK_FIELDS_MATCH, go.CHECK_EMBED_LIVE} <= form_checks
    assert req["executor"]["rate_limit"]["daily_cap"] == 200000


def test_writer_sandbox_adds_product_and_binding_ops(tmp_path):
    run = _mk_run(tmp_path, "run-sbx",
                  _intake(CHECKOUT_MODE="payment_sandbox"))
    code, req = go.build_request(run, "install")
    assert code == go.EXIT_OK
    kinds = [o["kind"] for o in req["operations"]]
    assert go.OP_PRODUCT in kinds and go.OP_ORDER_FORM in kinds
    product = next(o for o in req["operations"]
                   if o["kind"] == go.OP_PRODUCT)
    assert product["spec"]["amount_minor"] == 99700
    assert product["spec"]["currency"] == "USD"
    assert "never requested" in product["spec"]["live_payment"]


def test_writer_approved_url_reuse_omits_checkout_ops(tmp_path):
    run = _mk_run(tmp_path, "run-reuse", _intake(
        APPROVED_CHECKOUT_URL="https://payments.acme-co.com/acme-ops"))
    code, req = go.build_request(run, "install")
    assert code == go.EXIT_OK
    ids = [o["op_id"] for o in req["operations"]]
    assert "checkout-form" not in ids and "gate-form" in ids
    assert any("client-approved checkout URL" in n for n in req["notes"])


def test_writer_waived_elections_emit_no_request(tmp_path):
    intake = _intake()
    intake["pre_presentation_capture"] = {
        "WANT_SALES_CHECKOUT": "no",
        "SALES_CHECKOUT_DECLINED_REASON": "we sell on calls only",
        "WANT_VSL_PAGE": "no",
        "VSL_PAGE_DECLINED_REASON": "no video this launch"}
    run = _mk_run(tmp_path, "run-waived", intake)
    code, payload = go.build_request(run, "install")
    assert code == go.EXIT_OK
    assert payload["operations"] == []
    assert not (run / go.REQUEST_REL).exists()


def test_writer_gate_fail_closed_exit3(tmp_path):
    intake = _intake()
    intake["pre_presentation_capture"] = {
        "WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "no"}
    run = _mk_run(tmp_path, "run-fc", intake)
    code, _ = go.build_request(run, "install")
    assert code == go.EXIT_GATE_BLOCKED
    assert not (run / go.REQUEST_REL).exists()


def test_writer_missing_offer_blocked_exit5(tmp_path):
    intake = _intake()
    del intake["deck_brief"]["OFFER_NAME"]
    run = _mk_run(tmp_path, "run-nooffer", intake)
    code, payload = go.build_request(run, "install")
    assert code == go.EXIT_BLOCKED
    assert payload["blocker"]["code"] == "MISSING_OFFER"


def test_writer_calendar_op_when_named(tmp_path):
    intake = _intake()
    intake["CALENDAR_ID"] = "cal-abc-123"
    run = _mk_run(tmp_path, "run-cal", intake)
    code, req = go.build_request(run, "install")
    assert code == go.EXIT_OK
    cal = [o for o in req["operations"] if o["kind"] == go.OP_CALENDAR]
    assert len(cal) == 1
    assert cal[0]["spec"]["calendar_id"] == "cal-abc-123"
    checks = {e["check"] for e in cal[0]["expect"]}
    assert {go.CHECK_CALENDAR_EXISTS,
            go.CHECK_APPOINTMENTS_READ} <= checks


def test_writer_reemission_increments_version(tmp_path):
    run = _mk_run(tmp_path, "run-ver", _intake())
    code, req1 = go.build_request(run, "install")
    assert code == go.EXIT_OK and req1["request_version"] == 1
    code, req2 = go.build_request(run, "delivery")
    assert code == go.EXIT_OK and req2["request_version"] == 2
    assert req2["stage"] == "delivery"
    assert req2["request_id"] != req1["request_id"]


# ---------------------------------------------------------------------------
# Reader / judge
# ---------------------------------------------------------------------------
def _emitted(tmp_path, name="run-judge"):
    run = _mk_run(tmp_path, name, _intake())
    code, req = go.build_request(run, "install")
    assert code == go.EXIT_OK
    return run, req


def test_reader_absent_receipt_is_pending(tmp_path):
    run, _req = _emitted(tmp_path)
    code, verdict = go.judge_receipt(run)
    assert code == go.EXIT_OK
    assert verdict["overall"] == go.OVERALL_ABSENT


def test_reader_complete_receipt_judges_complete(tmp_path):
    run, req = _emitted(tmp_path)
    _write_receipt(run, _receipt(req, "run-judge"))
    code, verdict = go.judge_receipt(run)
    assert code == go.EXIT_OK
    assert verdict["overall"] == go.OVERALL_COMPLETE
    assert all(v["verdict"] == go.VERDICT_VERIFIED
               for v in verdict["operations"])


def test_reader_success_without_readback_judges_unverified(tmp_path):
    run, req = _emitted(tmp_path)

    def strip(r):
        for entry in r["results"]:
            if entry["op_id"] == "checkout-form":
                entry.pop("readback")
        return r

    _write_receipt(run, _receipt(req, "run-judge", strip))
    code, verdict = go.judge_receipt(run)
    by_id = {v["op_id"]: v for v in verdict["operations"]}
    assert by_id["checkout-form"]["verdict"] == go.VERDICT_UNVERIFIED
    assert verdict["overall"] != go.OVERALL_COMPLETE
    assert code == go.EXIT_VERIFY_FAILED


def test_reader_all_bare_claims_judge_unverified(tmp_path):
    run, req = _emitted(tmp_path)

    def strip_all(r):
        for entry in r["results"]:
            entry.pop("readback")
        return r

    _write_receipt(run, _receipt(req, "run-judge", strip_all))
    code, verdict = go.judge_receipt(run)
    assert verdict["overall"] == go.OVERALL_UNVERIFIED
    assert code == go.EXIT_VERIFY_FAILED


def test_reader_partial_readback_judges_partial(tmp_path):
    run, req = _emitted(tmp_path)
    receipt = _receipt(req, "run-judge")
    gate_wf = next(o for o in req["operations"]
                   if o["op_id"] == "gate-workflow")
    for entry in receipt["results"]:
        if entry["op_id"] == "gate-workflow":
            entry["readback"] = _readback(
                gate_wf, "obj-gate-workflow",
                falsify=go.CHECK_TRIGGER_BOUND)
    _write_receipt(run, receipt)
    code, verdict = go.judge_receipt(run)
    by_id = {v["op_id"]: v for v in verdict["operations"]}
    assert by_id["gate-workflow"]["verdict"] == go.VERDICT_PARTIAL
    assert verdict["overall"] == go.OVERALL_PARTIAL
    assert code == go.EXIT_VERIFY_FAILED


def test_reader_failed_claim_judges_failed(tmp_path):
    run, req = _emitted(tmp_path)

    def fail(r):
        for entry in r["results"]:
            if entry["op_id"] == "gate-form":
                entry["status_claimed"] = "failed"
                entry["detail"] = "caf refused the build"
        return r

    _write_receipt(run, _receipt(req, "run-judge", fail))
    code, verdict = go.judge_receipt(run)
    assert verdict["overall"] == go.OVERALL_FAILED
    assert code == go.EXIT_VERIFY_FAILED


def test_reader_missing_entry_judges_missing(tmp_path):
    run, req = _emitted(tmp_path)
    receipt = _receipt(req, "run-judge")
    receipt["results"] = [e for e in receipt["results"]
                          if e["op_id"] != "gate-test-submission"]
    _write_receipt(run, receipt)
    code, verdict = go.judge_receipt(run)
    by_id = {v["op_id"]: v for v in verdict["operations"]}
    assert by_id["gate-test-submission"]["verdict"] == go.VERDICT_MISSING
    assert verdict["overall"] != go.OVERALL_COMPLETE


def test_reader_stale_version_and_wrong_location_invalid(tmp_path):
    run, req = _emitted(tmp_path)

    def stale(r):
        r["request_version"] = 99
        return r

    _write_receipt(run, _receipt(req, "run-judge", stale))
    code, verdict = go.judge_receipt(run)
    assert verdict["overall"] == go.OVERALL_INVALID
    assert code == go.EXIT_VERIFY_FAILED

    def wrong_location(r):
        r["scope"]["location_id"] = "loc-someone-else"
        return r

    _write_receipt(run, _receipt(req, "run-judge", wrong_location))
    code, verdict = go.judge_receipt(run)
    assert verdict["overall"] == go.OVERALL_INVALID


def test_receipt_fixture_matches_receipt_schema_required(tmp_path):
    run, req = _emitted(tmp_path)
    receipt = _receipt(req, "run-judge")
    schema = json.loads(
        (SCRIPTS / "ghl-ops-receipt.schema.json").read_text())
    assert set(schema["required"]) <= set(receipt)
    entry_schema = schema["properties"]["results"]["items"]
    for entry in receipt["results"]:
        assert set(entry_schema["required"]) <= set(entry)
