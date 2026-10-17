#!/usr/bin/env python3
"""test_b30_brief_registration.py - B30's deferred registration of the
Item 20 page-brief seam phases (recorded in build/b30-page-brief/MANIFEST.md
section 2d item 5 as a post-merge follow-up to PR #2037).

Pins:
  * P-U-BRIEF-SALES and P-U-BRIEF-VSL are registered in the canonical
    manifest with the recorded placement, gates, and executor commands;
  * the registration is VERSION-NEUTRAL: manifest_version and both
    MIN_MANIFEST_VERSION mirrors stay in the lockstep the repo asserts
    (the v71 claim belongs to other PRs under the M13 settlement; a phase
    registration must not move any version number);
  * both phases have a phase_verifiers registry entry and a
    PHASE_BUDGET_MINUTES entry (the two coverage rules every registration
    must satisfy);
  * the brief verifiers judge with the seam's own machinery: an elected
    page with an emitted valid brief passes, a waived page with the
    outcome in the seam ledger passes, an elected page whose brief is
    missing fails;
  * the PRES-011 verify extension: a run that emitted no briefs (the
    legacy path) draws no brief-binding reasons, while a seam run whose
    receipt does not bind the current briefs fails, and a correctly
    bound receipt passes.

Flat file inside tests/, manages its own import path - matching every
sibling in this directory. Offline and deterministic.
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
import phase_verifiers as pv  # noqa: E402


def _manifest() -> dict:
    import run_signature_deck as rsd
    return rsd.load_manifest()


def _phase(manifest: dict, phase_id: str) -> dict:
    return next(p for p in manifest["phases"] if p["id"] == phase_id)


# ---------------------------------------------------------------------------
# 1. The registration itself, exactly as B30's record specifies it.
# ---------------------------------------------------------------------------
def test_brief_phases_registered_with_recorded_shape():
    m = _manifest()
    sales = _phase(m, "P-U-BRIEF-SALES")
    vsl = _phase(m, "P-U-BRIEF-VSL")
    # Placement: each emit phase sits immediately after its branch's
    # design-render phase (B30 record section 2d item 5). Conformed for
    # the Path A retirement (owner ruling 2026-10-15): the design-render
    # anchors are retired phases, so the same placement is asserted
    # against the surviving anchors: both emit phases sit in the upsell
    # seam after copy QC, sales before VSL, and the VSL emit still sits
    # before PF-DESIGN exactly as registered.
    order = {p["id"]: p["order"] for p in m["phases"]}
    assert order["P1Q-COPY-QC"] < sales["order"] < order["P-U-BRIEF-VSL"]
    assert order["P-U-BRIEF-SALES"] < vsl["order"] < order["PF-DESIGN"]
    assert sales["defers_unless"] == 'intake.want_sales_checkout == "yes"'
    assert vsl["defers_unless"] == 'intake.want_vsl_page == "yes"'
    assert sales["executor"] == {
        "kind": "script",
        "cmd": "python3 scripts/page_brief.py --run-dir {run_dir} "
               "--page sales --page checkout",
    }
    assert vsl["executor"] == {
        "kind": "script",
        "cmd": "python3 scripts/page_brief.py --run-dir {run_dir} --page vsl",
    }
    for ph in (sales, vsl):
        assert ph["verifier"] == "phase_verifiers.verify"
        assert ph["client_report"]["start_template"]
        assert ph["client_report"]["done_template"]
        assert isinstance(ph["heartbeat_minutes"], int) \
            and ph["heartbeat_minutes"] > 0


def test_registration_is_version_neutral():
    """No version number moves: the manifest version stays EQUAL to both
    MIN_MANIFEST_VERSION mirrors (the lockstep manifest.py's own comment
    and test_client_package.py assert), and the phase floor still holds."""
    import manifest_assert
    from presentation_job import manifest as job_manifest
    m = _manifest()
    assert m["manifest_version"] == job_manifest.MIN_MANIFEST_VERSION
    assert m["manifest_version"] == manifest_assert.MIN_MANIFEST_VERSION
    assert len(m["phases"]) >= manifest_assert.MIN_MANIFEST_PHASES


def test_registry_and_budget_cover_the_brief_phases():
    from presentation_job.manifest import PHASE_BUDGET_MINUTES
    for pid in ("P-U-BRIEF-SALES", "P-U-BRIEF-VSL"):
        assert pid in pv.PHASE_VERIFIERS, f"{pid} has no verifier"
        assert pid in PHASE_BUDGET_MINUTES, f"{pid} has no budget entry"


# ---------------------------------------------------------------------------
# 2. The brief verifiers, judged on the seam's own fixture machinery
#    (the fixture mirrors test_item20_page_brief.py's local copy).
# ---------------------------------------------------------------------------
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
                "ghl_url": "https://storage.googleapis.com/msgsndr/"
                           "loc-test-1/acme.mp4",
                "deck_slug": "acme-brief"},
            "logo_main": {
                "ghl_url": "https://assets.cdn.filesafe.space/"
                           "loc-test-1/logo.png"},
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


def _emit(run: Path) -> None:
    code, _results = pb.emit(run, profile=PROFILE, env={})
    assert code == pb.EXIT_OK


def test_brief_verifiers_pass_on_emitted_briefs(tmp_path):
    run = _fixture_run(tmp_path)
    _emit(run)
    ok, reasons = pv.verify("P-U-BRIEF-SALES", run)
    assert ok, reasons
    ok, reasons = pv.verify("P-U-BRIEF-VSL", run)
    assert ok, reasons


def test_brief_verifier_passes_waived_page_via_seam_ledger(tmp_path):
    run = _fixture_run(tmp_path, vsl="no",
                       vsl_reason="Client does not need a VSL page.")
    _emit(run)
    ok, reasons = pv.verify("P-U-BRIEF-VSL", run)
    assert ok, reasons


def test_brief_verifier_fails_when_elected_brief_is_missing(tmp_path):
    run = _fixture_run(tmp_path)
    _emit(run)
    for f in (run / "working" / "pages").glob("page-brief-vsl.*"):
        f.unlink()
    ok, reasons = pv.verify("P-U-BRIEF-VSL", run)
    assert not ok
    assert any("no page brief was emitted" in r for r in reasons)


# ---------------------------------------------------------------------------
# 3. The PRES-011 verify extension (the brief binding).
# ---------------------------------------------------------------------------
def test_binding_inapplicable_on_a_legacy_run(tmp_path):
    """No briefs were ever emitted for this run: the legacy path the seam
    preserves draws no binding reasons."""
    run = _fixture_run(tmp_path)  # fixture inputs only; emit never ran
    assert pv._brief_binding_reasons(run, "P-U-GHL-SALES", {}) == []
    assert pv._brief_binding_reasons(run, "P-U-FORM-GATE", {}) == []


def test_binding_bites_on_an_unbound_seam_receipt(tmp_path):
    run = _fixture_run(tmp_path)
    _emit(run)
    errs = pv._brief_binding_reasons(run, "P-U-GHL-SALES",
                                     {"phase_id": "P-U-GHL-SALES"})
    assert errs and any("brief_binding" in e for e in errs)


def test_binding_passes_on_a_correctly_bound_receipt(tmp_path):
    run = _fixture_run(tmp_path)
    _emit(run)
    binding = []
    for page in ("sales", "checkout"):
        path, cur = pb.latest_brief(run, page)
        binding.append({"page_type": page, "brief_id": cur["brief_id"],
                        "version": cur["version"],
                        "sha256": pb._sha256_file(path)})
    receipt = {"brief_binding": {"briefs": binding}}
    assert pv._brief_binding_reasons(run, "P-U-GHL-SALES", receipt) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
