#!/usr/bin/env python3
"""test_item20_page_brief.py - FIX-PLAN Item 20 (the page-brief.json seam,
presentations side).

Pins, against fixture phase outputs in a real run-folder layout:
  * brief emission for each elected page type (sales, checkout, vsl);
  * a declined election emits NO brief and the run record (the seam ledger)
    carries the client's verbatim waiver;
  * a defer (question never answered) emits none and is not a decline;
  * a gate fail-closed ("no" with no verbatim reason) emits none, exit 3;
  * the write-time validator rejects incomplete briefs fail-closed;
  * immutability/versioning: a re-emission writes the next version and the
    earlier brief file is byte-identical;
  * the model fields keep selection and recommendation distinct (a
    recommendation never lands in selections; source='recommended' is
    refused by the validator);
  * the receipt brief-binding check (missing / matching / stale).

Flat file inside tests/, manages its own import path - matching every
sibling in this directory. Offline and deterministic: no network, no kie.ai
spend, no GHL call.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import page_brief as pb  # noqa: E402


def _fixture_run(base: Path, *, sales: str = "yes", vsl: str = "yes",
                 sales_reason: str = "", vsl_reason: str = "") -> Path:
    run = base / "run-acme"
    for rel in ("working/copy", "working/sales-checkout/copy",
                "working/sales-checkout/renders", "working/vsl/copy",
                "working/vsl/renders", "working/upsell/copy",
                "working/checkpoints", "working/delivery"):
        (run / rel).mkdir(parents=True, exist_ok=True)
    pre: dict = {}
    if sales:
        pre["WANT_SALES_CHECKOUT"] = sales
    if sales_reason:
        pre["SALES_CHECKOUT_DECLINED_REASON"] = sales_reason
    if vsl:
        pre["WANT_VSL_PAGE"] = vsl
    if vsl_reason:
        pre["VSL_PAGE_DECLINED_REASON"] = vsl_reason
    intake = {
        "deck_slug": "acme-brief",
        "company": "Acme Co",
        "GHL_LOCATION_ID": "loc-test-1",
        "pre_presentation_capture": pre,
        "deck_brief": {
            "OFFER_NAME": "Momentum Method",
            "FINAL_PRICE": "$997",
            "TRANSFORMATION_PROMISE": "Go from stuck to shipped in 30 days.",
            "AUDIENCE": "overwhelmed solo founders",
            "CTA_ACTION": "Enroll Now",
            "HOOK_SEED": "You don't need more time. You need momentum.",
            "PRIMARY_OBJECTION": "I don't have time for another program.",
            "PROOF_ASSETS": "312 founders shipped their first launch.",
            "TONE": "warm, direct",
            "BRAND_PRIMARY": "#1a2b6d",
        },
    }
    (run / pb.INTAKE_REL).write_text(json.dumps(intake, indent=2),
                                     encoding="utf-8")
    (run / "working/sales-checkout/copy/sales.md").write_text(
        "# Sales copy\nMomentum Method for overwhelmed solo founders.\n",
        encoding="utf-8")
    (run / "working/sales-checkout/copy/checkout.md").write_text(
        "# Checkout copy\nComplete your order: Momentum Method, $997.\n",
        encoding="utf-8")
    (run / "working/vsl/copy/vsl.md").write_text(
        "# VSL copy\nWatch the Momentum Method training.\n",
        encoding="utf-8")
    (run / "working/upsell/copy/sales.fragment.md").write_text(
        "Sales fragment copy.\n", encoding="utf-8")
    (run / "working/checkpoints/media_library.json").write_text(
        json.dumps({
            "webinar_mp4": {
                "ghl_url": "https://storage.googleapis.com/msgsndr/loc-test-1/acme.mp4",
                "deck_slug": "acme-brief"},
            "logo_main": {
                "ghl_url": "https://assets.cdn.filesafe.space/loc-test-1/logo.png"},
        }), encoding="utf-8")
    (run / "working/checkpoints/webinar_timing.json").write_text(
        json.dumps({"total_audio_sec": 1200.0, "timing": [
            {"slide": 1, "audio_start": 0.0},
            {"slide": 5, "audio_start": 300.0},
            {"slide": 9, "audio_start": 700.0}]}), encoding="utf-8")
    (run / "working" / "delivery" / "acme-brief-WEBINAR.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
        b"\x00\x00\x00\x08free")
    return run


PROFILE = {
    "model_choices": [
        {"provider_family": "openrouter",
         "selection": {"model": "client-picked-model", "source": "selected",
                       "recorded_at": "2026-10-14T00:00:00Z"},
         "recommendations_shown": [
             {"model": "other-model", "reason": "shown as an alternative",
              "shown_at": "2026-10-14T00:00:00Z", "response": "declined"}]},
        {"provider_family": "ollama-cloud",
         "selection": None,
         "recommendations_shown": [
             {"model": "rec-only-model",
              "reason": "no provider cap; the machine is the only limit",
              "shown_at": "2026-10-14T00:00:00Z", "response": "offered"}]},
        {"provider_family": "deepseek-direct",
         "selection": {"model": "configured-model",
                       "source": "configured-default",
                       "recorded_at": "2026-10-14T00:00:00Z"},
         "recommendations_shown": []},
    ]
}


def test_emission_for_each_elected_page_type(tmp_path):
    run = _fixture_run(tmp_path)
    code, results = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK, results
    for page in pb.PAGE_TYPES:
        path, brief = pb.latest_brief(run, page)
        assert path is not None and brief is not None, page
        assert pb.validate_brief(brief) == [], page
        assert brief["version"] == 1
        assert brief["provenance"]["run_id"] == run.name
        assert brief["election"]["decision"] == "build"
        assert brief["page_set"]["pages_elected"] == ["sales", "checkout",
                                                       "vsl"]
        assert brief["page_set"]["shared_funnel"] is True
    checkout_path, checkout = pb.latest_brief(run, "checkout")
    assert checkout["offer"]["amount_minor"] == 99700
    assert checkout["offer"]["currency"] == "USD"
    assert checkout["form"]["intent"] == "lead_capture"
    vsl_path, vsl = pb.latest_brief(run, "vsl")
    assert vsl["vsl"]["gate"]["timestamp_seconds"] == 300.0
    assert vsl["vsl"]["video"]["hosted"] is True


def test_checkout_consent_is_all_required(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    _p, checkout = pb.latest_brief(run, "checkout")
    consent = checkout["consent"]
    assert consent["posture"] == "all_required"
    assert consent["boxes"], "checkout brief must carry consent boxes"
    for box in consent["boxes"]:
        assert box["required"] is True
        assert box["default_unchecked"] is True


def test_declined_election_emits_none_and_records_waiver(tmp_path):
    run = _fixture_run(tmp_path, sales="no", vsl="no",
                       sales_reason="We already have a checkout page.",
                       vsl_reason="We don't have a video yet.")
    code, results = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    for page in pb.PAGE_TYPES:
        assert pb.existing_brief_versions(run, page) == []
        assert results[page]["outcome"] == "waived"
    ledger = pb._read_json(run / pb.LEDGER_REL)
    sales_last = ledger["pages"]["sales"]["last"]
    assert sales_last["election"]["declined_reason"] == \
        "We already have a checkout page."
    vsl_last = ledger["pages"]["vsl"]["last"]
    assert vsl_last["election"]["declined_reason"] == \
        "We don't have a video yet."


def test_defer_emits_none_and_is_not_a_decline(tmp_path):
    run = _fixture_run(tmp_path, sales="", vsl="")
    code, results = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    for page in pb.PAGE_TYPES:
        assert pb.existing_brief_versions(run, page) == []
        assert results[page]["outcome"] == "defer"


def test_gate_fail_closed_emits_none(tmp_path):
    run = _fixture_run(tmp_path, vsl="no")  # no verbatim reason
    code, results = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_GATE_BLOCKED
    assert results["vsl"]["outcome"] == "fail_closed"
    assert pb.existing_brief_versions(run, "vsl") == []


def test_validator_rejects_incomplete_briefs(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    _p, good = pb.latest_brief(run, "sales")

    no_offer = json.loads(json.dumps(good))
    no_offer["offer"]["name"] = ""
    assert pb.validate_brief(no_offer)

    no_copy = json.loads(json.dumps(good))
    no_copy["copy_blocks"] = []
    assert pb.validate_brief(no_copy)

    no_provenance = json.loads(json.dumps(good))
    no_provenance["provenance"]["source_artifacts"] = []
    assert pb.validate_brief(no_provenance)

    # Write-time refusal: nothing is written for an invalid brief.
    run2 = _fixture_run(tmp_path / "second")
    with pytest.raises(pb.BriefValidationError):
        pb.write_brief(run2, no_offer)
    assert pb.existing_brief_versions(run2, "sales") == []

    _pc, checkout = pb.latest_brief(run, "checkout")
    optional_box = json.loads(json.dumps(checkout))
    optional_box["consent"]["boxes"][0]["required"] = False
    assert pb.validate_brief(optional_box)


def test_immutability_and_versioning(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    v1_path, _v1 = pb.latest_brief(run, "sales")
    v1_bytes = v1_path.read_bytes()
    (run / "working/sales-checkout/copy/sales.md").write_text(
        "# Sales copy v2\nChanged copy for the second emission.\n",
        encoding="utf-8")
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    assert pb.existing_brief_versions(run, "sales") == [1, 2]
    assert v1_path.read_bytes() == v1_bytes
    _p2, v2 = pb.latest_brief(run, "sales")
    assert v2["version"] == 2
    assert v2["supersedes"] == "working/pages/page-brief-sales.v1.json"
    with pytest.raises(FileExistsError):
        pb._write_new_file(run / pb.brief_rel_path("sales", 1), "{}")


def test_model_selection_and_recommendation_stay_distinct(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    _p, sales = pb.latest_brief(run, "sales")
    model = sales["model"]
    selections = {(s["provider_family"], s["model"], s["source"])
                  for s in model["selections"]}
    assert ("openrouter", "client-picked-model", "selected") in selections
    assert ("deepseek-direct", "configured-model",
            "configured-default") in selections
    # The recommendation-only family's model never appears as a selection.
    assert all(m != "rec-only-model" for _f, m, _s in selections)
    recommendations = {r["model"] for r in model["recommendations"]}
    assert "rec-only-model" in recommendations
    # And the validator refuses a recommendation smuggled in as a selection.
    smuggled = json.loads(json.dumps(sales))
    smuggled["model"]["selections"].append(
        {"provider_family": "ollama-cloud", "model": "rec-only-model",
         "source": "recommended", "recorded_at": None})
    assert pb.validate_brief(smuggled)


def test_model_block_without_choices_record_is_honest(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile={"model_plan": {"workhorse": {}}},
                       env={})
    assert code == pb.EXIT_OK
    _p, sales = pb.latest_brief(run, "sales")
    assert sales["model"]["selections"] == []
    assert "not present" in sales["model"]["record_status"]


def test_receipt_binding_match_stale_missing(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    assert pb.check_brief_binding(run, "P-U-GHL-SALES", {})
    binding = []
    for page in ("sales", "checkout"):
        path, cur = pb.latest_brief(run, page)
        binding.append({"page_type": page, "brief_id": cur["brief_id"],
                        "version": cur["version"],
                        "sha256": pb._sha256_file(path)})
    receipt = {"brief_binding": {"briefs": binding}}
    assert pb.check_brief_binding(run, "P-U-GHL-SALES", receipt) == []
    binding[0]["sha256"] = "0" * 64
    assert pb.check_brief_binding(run, "P-U-GHL-SALES", receipt)


def test_verify_receipts_pending_is_not_failure(tmp_path):
    run = _fixture_run(tmp_path)
    code, _ = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK
    code, results = pb.verify_receipts(run, env={})
    assert code == pb.EXIT_OK
    assert results["P-U-GHL-SALES"]["status"] == "pending"
