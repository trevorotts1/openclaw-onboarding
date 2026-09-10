#!/usr/bin/env python3
"""test_upsell_verifiers.py — Wave C (C4) phase_verifiers.py coverage for the
four new upsell-branch phases (PIPELINE-MANIFEST.json v51, manifest_version 51,
40 phases): P-U-SALES-BUILD, P-U-CHECKOUT-BUILD, P-U-FORM-CHECKOUT,
P-U-VSL-BUILD.

Ground truth this file pins:
  * All four share the SAME two-flag waiver mechanic (upsell-questions.json
    v1.0.0, U026): defer (flag absent/blank) and waived ("no" + a real client
    quote) are BOTH legitimate non-failure outcomes -- the phase produces
    nothing and that is correct, mirroring how the Signature-Presentation
    (_verify_sp_*) verifiers pass when build_deck's _chk_sp_* wrapper defers
    for a non-signature deck.
  * fail_closed (a self-authored "no" with no reason, or an unrecognized
    WANT_* value) is a REAL failure -- the executor itself refuses to build,
    and the verifier must not paper over that with a pass.
  * "build" (flag == "yes") is a hard FAIL unless the phase's own
    produces_artifact (per PIPELINE-MANIFEST.json) is present, real, and
    carries THIS run's own content marker -- never a vacuous pass. This is
    exactly the class of defect unit B3 fixed for P4-COPY (a verifier that
    returns (True, []) against an empty/missing artifact).
  * P-U-VSL-BUILD additionally hard-fails (AF-VSL-NO-VIDEO) when the P9.6
    webinar video artifact is absent, even when the client elected "yes" and
    the VSL html itself would otherwise be buildable.

Real artifacts are produced by ACTUALLY RUNNING sales_checkout_builder.py /
vsl_builder.py (--skip-design --no-push, pre-seeded placeholder hero PNGs) --
never hand-authored decoy HTML pretending to be the builder's output. No
network, no kie.ai spend (--skip-design skips the kie.ai call entirely; a
1x1 placeholder PNG is pre-seeded so the design step is never reached), no
GHL call (--no-push skips the push-plan/receipt steps entirely).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_webinar_builder.py, test_workbook_builder.py,
etc.).
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import phase_verifiers as pv  # noqa: E402
import sales_checkout_builder as scb  # noqa: E402
import vsl_builder as vb  # noqa: E402
import checkout_form_builder as cfb  # noqa: E402  (PRES-025 real producer)


def _skill06_tools():
    """Import the REAL Skill 06 form builder (06-ghl-install-pages/tools/).

    Resolves the tools dir relative to this repo checkout so the test runs
    from any worktree without hardcoding an absolute path. Snapshot-free:
    saves and restores sys.path / sys.modules around the import so sibling
    tests (VSL, webinar) never see Skill 06's shadow modules."""
    import importlib
    here = Path(__file__).resolve()
    tools = None
    for parent in list(here.parents)[:14]:
        cand = parent / "06-ghl-install-pages" / "tools"
        if (cand / "ghl_form_builder.py").is_file():
            tools = cand
            break
    if tools is None:
        raise FileNotFoundError(
            "06-ghl-install-pages/tools/ghl_form_builder.py not found above "
            f"{here} -- run from a full checkout")
    saved_path = list(sys.path)
    saved_modules = dict(sys.modules)
    try:
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        return importlib.import_module("ghl_form_builder")
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if k not in saved_modules]:
            del sys.modules[key]

# 1x1 transparent PNG -- a real, valid PNG (correct magic bytes), just tiny.
# Used as the pre-seeded "hero render" so --skip-design never needs kie.ai.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

# A minimal-but-real MP4 header (ftyp box at offset 4) -- enough to pass
# ghl_media.verify_video()'s local probe (size>0, <=500MB, ftyp magic).
_FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 256


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
def _intake(tmp_path: Path, pre: dict, deck_slug: str = "acme-widget") -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({
        "deck_slug": deck_slug,
        "pre_presentation_capture": pre,
        "deck_brief": {"OFFER_NAME": "Acme Widget Mastery"},
    }))
    return rd


def _seed_sales_checkout_renders(rd: Path) -> None:
    renders = rd / "working" / "sales-checkout" / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "sales-hero.png").write_bytes(_TINY_PNG)
    (renders / "checkout-hero.png").write_bytes(_TINY_PNG)


def _build_sales_checkout(rd: Path) -> int:
    """Actually run sales_checkout_builder.py's real main() -- never a hand-
    authored decoy. Returns the exit code."""
    _seed_sales_checkout_renders(rd)
    return scb.main(["--run-dir", str(rd), "--skip-design", "--no-push"])


def _seed_webinar_video(rd: Path, deck_slug: str = "acme-widget") -> Path:
    delivery = rd / "working" / "delivery"
    delivery.mkdir(parents=True, exist_ok=True)
    video = delivery / f"{deck_slug}-WEBINAR.mp4"
    video.write_bytes(_FAKE_MP4)
    return video


def _seed_vsl_renders(rd: Path) -> None:
    renders = rd / "working" / "vsl" / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "vsl-hero.png").write_bytes(_TINY_PNG)


def _build_vsl(rd: Path) -> int:
    """Actually run vsl_builder.py's real main() -- never a hand-authored
    decoy. Assumes the P9.6 video artifact already exists in rd."""
    _seed_vsl_renders(rd)
    return vb.main(["--run-dir", str(rd), "--skip-design", "--no-push"])


# ---------------------------------------------------------------------------
# Registry coverage (the two RED tests this unit turns GREEN)
# ---------------------------------------------------------------------------
class TestRegistryCoversUpsellPhases:
    def test_all_four_upsell_ids_registered(self):
        for pid in ("P-U-SALES-BUILD", "P-U-CHECKOUT-BUILD",
                    "P-U-FORM-CHECKOUT", "P-U-VSL-BUILD"):
            assert pid in pv.PHASE_VERIFIERS, f"{pid} has no registered verifier"

    def test_registry_covers_every_manifest_phase_id(self):
        """Mirrors test_client_step_count.py::test_verifier_registry_covers_all_36
        and test_engine_client_report.py's twin -- the whole reason those two
        tests were RED before this unit."""
        import run_signature_deck as rsd
        manifest_ids = {p["id"] for p in rsd.load_manifest()["phases"]}
        registered = set(pv.PHASE_VERIFIERS.keys())
        missing = manifest_ids - registered
        assert not missing, f"phase_verifiers.py is missing verifiers for: {sorted(missing)}"


# ---------------------------------------------------------------------------
# P-U-SALES-BUILD
# ---------------------------------------------------------------------------
class TestSalesBuildVerifier:
    def test_defer_when_flag_absent_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {})
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is True
        assert any("defer" in r for r in reasons)

    def test_defer_when_intake_json_entirely_absent_is_a_pass(self, tmp_path):
        """No working/copy/intake.json at all -- load_intake degrades to {}."""
        rd = tmp_path / "run"
        rd.mkdir()
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is True

    def test_waived_with_real_reason_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "We already have a checkout page we like.",
        })
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is True
        assert any("waived" in r for r in reasons)

    def test_fail_closed_no_without_reason_fails(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "no"})
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is False
        assert any("AF-U-SALES-BUILD" in r and "fail_closed" in r for r in reasons)

    def test_fail_closed_unrecognized_value_fails(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "maybe"})
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is False

    def test_elected_but_nothing_built_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #1: elected (yes) with no artifact at all -> FAIL."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is False
        assert any("not found" in r for r in reasons)

    def test_elected_with_zero_byte_html_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #2: the file exists but is empty."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        html_dir = rd / "working" / "sales-checkout" / "html"
        html_dir.mkdir(parents=True)
        (html_dir / "sales.html").write_bytes(b"")
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is False

    def test_elected_with_placeholder_html_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #3: a real-looking but non-genuine file (no
        marker) -- a decoy renamed to sales.html must not pass."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        html_dir = rd / "working" / "sales-checkout" / "html"
        html_dir.mkdir(parents=True)
        (html_dir / "sales.html").write_text(
            "<html><body><h1>placeholder wireframe background only</h1></body></html>"
            + ("x" * 300)
        )
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is False
        assert any("marker" in r for r in reasons)

    def test_elected_with_real_build_passes(self, tmp_path):
        """The genuine PASS: run the REAL builder script, then verify."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is True, reasons

    def test_checkout_html_alone_is_not_mistaken_for_sales_html(self, tmp_path):
        """A checkout.html copied over sales.html (wrong page_role marker)
        must still fail -- proves the marker check is page-specific, not just
        'any ZHC-SALES-CHECKOUT-BUILDER text'."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        checkout_html = (rd / "working" / "sales-checkout" / "html" / "checkout.html").read_text()
        (rd / "working" / "sales-checkout" / "html" / "sales.html").write_text(checkout_html)
        ok, reasons = pv.verify("P-U-SALES-BUILD", rd)
        assert ok is False
        assert any("page_role=sales" in r for r in reasons)


# ---------------------------------------------------------------------------
# P-U-CHECKOUT-BUILD
# ---------------------------------------------------------------------------
class TestCheckoutBuildVerifier:
    def test_defer_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {})
        ok, _ = pv.verify("P-U-CHECKOUT-BUILD", rd)
        assert ok is True

    def test_waived_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "Building our own with our web team.",
        })
        ok, _ = pv.verify("P-U-CHECKOUT-BUILD", rd)
        assert ok is True

    def test_fail_closed_fails(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "no", "SALES_CHECKOUT_DECLINED_REASON": ""})
        ok, _ = pv.verify("P-U-CHECKOUT-BUILD", rd)
        assert ok is False

    def test_elected_but_nothing_built_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF: elected with no artifact -> FAIL."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        ok, reasons = pv.verify("P-U-CHECKOUT-BUILD", rd)
        assert ok is False
        assert any("not found" in r for r in reasons)

    def test_elected_with_empty_html_fails_hard(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        html_dir = rd / "working" / "sales-checkout" / "html"
        html_dir.mkdir(parents=True)
        (html_dir / "checkout.html").write_text("   ")
        ok, _ = pv.verify("P-U-CHECKOUT-BUILD", rd)
        assert ok is False

    def test_elected_with_real_build_passes(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        ok, reasons = pv.verify("P-U-CHECKOUT-BUILD", rd)
        assert ok is True, reasons


# ---------------------------------------------------------------------------
# P-U-FORM-CHECKOUT
# ---------------------------------------------------------------------------
class TestFormCheckoutVerifier:
    def test_defer_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {})
        ok, _ = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True

    def test_waived_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "Not this quarter, thanks.",
        })
        ok, _ = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True

    def test_fail_closed_fails(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "no"})
        ok, _ = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False

    def test_elected_with_no_receipt_yet_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF (PRES-025 real producer): elected, sales/checkout
        genuinely built, but the form stage has not run -- checkout_form.json
        absent -- must FAIL, not pass, because produces_artifact names the
        form receipt specifically."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        assert not (rd / "working" / "sales-checkout" / "checkout_form.json").exists()
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("checkout_form.json" in r for r in reasons)

    def test_elected_with_plan_emitted_but_no_ids_fails_hard(self, tmp_path):
        """Plan emitted (Skill 44/06 contracts written, no IDs yet) is NOT
        completion -- the delegated execution has not landed."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_OK
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("plan emitted" in r for r in reasons)

    def test_elected_with_dead_checkout_cta_fails_hard(self, tmp_path):
        """A checkout page whose form posts nowhere (action='#') can never
        carry a completing form -- the CTA audit fails the phase first."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        html_path = rd / "working" / "sales-checkout" / "html" / "checkout.html"
        html_path.write_text(
            html_path.read_text(encoding="utf-8").replace('action="/acme-widget-checkout"',
                                                          'action="#"'),
            encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("action" in r or "href" in r or "CTA" in r for r in reasons)

    def test_elected_with_stale_receipt_fails_hard(self, tmp_path):
        """An offer edit after plan-emit invalidates the receipt -- stale form
        proof must FAIL until the stage re-runs."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_OK
        intake_path = rd / "working" / "copy" / "intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["deck_brief"]["OFFER_NAME"] = "Renamed Offer After Plan"
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("STALE" in r for r in reasons)

    def test_elected_lead_complete_passes(self, tmp_path):
        """The genuine lead-capture PASS: form + workflow IDs plus a
        test-location submit proof (one scoped contact + one enrollment,
        validation + duplicates exercised)."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_OK
        receipt_path = rd / "working" / "sales-checkout" / "checkout_form.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["form"]["form_id"] = "form_mem_0001"
        receipt["form"]["action"] = "/acme-widget-checkout"
        receipt["workflow"]["workflow_id"] = "wf_mem_0002"
        receipt["status"] = "complete"
        receipt["proof"] = {
            "kind": "lead_submit", "location_id": "unbound-test",
            "form_id": "form_mem_0001", "workflow_id": "wf_mem_0002",
            "contacts": 1, "enrollments": 1,
            "validation_exercised": True, "duplicate_exercised": True,
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True, reasons

    def test_elected_lead_zero_enrollment_fails_hard(self, tmp_path):
        """A 'complete' lead receipt with zero enrollments proves no workflow
        -- must FAIL."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_OK
        receipt_path = rd / "working" / "sales-checkout" / "checkout_form.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["form"]["form_id"] = "form_mem_0001"
        receipt["workflow"]["workflow_id"] = "wf_mem_0002"
        receipt["status"] = "complete"
        receipt["proof"] = {
            "kind": "lead_submit", "location_id": "unbound-test",
            "form_id": "form_mem_0001", "workflow_id": "wf_mem_0002",
            "contacts": 1, "enrollments": 0,
            "validation_exercised": True, "duplicate_exercised": True,
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("enrollment" in r for r in reasons)

    def test_elected_sandbox_complete_passes(self, tmp_path):
        """The genuine sandbox PASS: product/amount/currency mapping +
        success/cancel routes, zero real charge."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        intake_path = rd / "working" / "copy" / "intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["deck_brief"]["FINAL_PRICE"] = "$997"
        intake["deck_brief"]["CHECKOUT_MODE"] = "payment_sandbox"
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_OK
        receipt_path = rd / "working" / "sales-checkout" / "checkout_form.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["intent"] == cfb.INTENT_PAYMENT_SANDBOX
        receipt["form"]["form_id"] = "form_mem_0001"
        receipt["status"] = "complete"
        receipt["proof"] = {
            "kind": "sandbox_session", "mode": "sandbox",
            "product_id": "prod_mem_0001", "session_id": "sess_mem_0002",
            "amount_minor": 99700, "currency": "USD",
            "success_url": "https://shop.example.test/success",
            "cancel_url": "https://shop.example.test/cancel",
            "real_charge": False,
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True, reasons

    def test_elected_sandbox_real_charge_fails_hard(self, tmp_path):
        """A sandbox proof recording a real charge is refused -- the sandbox
        is structurally incapable of charging."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        intake_path = rd / "working" / "copy" / "intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["deck_brief"]["FINAL_PRICE"] = "$997"
        intake["deck_brief"]["CHECKOUT_MODE"] = "payment_sandbox"
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_OK
        receipt_path = rd / "working" / "sales-checkout" / "checkout_form.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["form"]["form_id"] = "form_mem_0001"
        receipt["status"] = "complete"
        receipt["proof"] = {
            "kind": "sandbox_session", "mode": "sandbox",
            "product_id": "prod_mem_0001", "session_id": "sess_mem_0002",
            "amount_minor": 99700, "currency": "USD",
            "success_url": "https://shop.example.test/success",
            "cancel_url": "https://shop.example.test/cancel",
            "real_charge": True,
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("real charge" in r for r in reasons)

    def test_missing_offer_blocks_soft_not_fail(self, tmp_path):
        """No client-approved offer: the phase BLOCKS (soft NOTE naming
        MISSING_OFFER) -- deck production continues, checkout alone waits."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        intake_path = rd / "working" / "copy" / "intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["deck_brief"] = {}
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_BLOCKED
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True, reasons
        assert any("MISSING_OFFER" in r for r in reasons)

    def test_wrong_location_blocks_soft_not_fail(self, tmp_path, monkeypatch):
        """Intake location disagreeing with the bound location blocks the
        checkout phase softly -- never a cross-client write, never a deck fail."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        intake_path = rd / "working" / "copy" / "intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["GHL_LOCATION_ID"] = "loc_WRONG"
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        monkeypatch.setenv("GOHIGHLEVEL_LOCATION_ID", "loc_BOUND")
        try:
            rc = _build_sales_checkout(rd)
            assert rc == scb.EXIT_OK
            rc2 = cfb.main(["--run-dir", str(rd)])
            assert rc2 == cfb.EXIT_BLOCKED
            ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
            assert ok is True, reasons
            assert any("WRONG_LOCATION" in r for r in reasons)
        finally:
            monkeypatch.delenv("GOHIGHLEVEL_LOCATION_ID", raising=False)

    def test_unsupported_payment_blocks_soft_not_fail(self, tmp_path):
        """Live payment elected with no merchant: explicit actionable
        MISSING_MERCHANT block -- the pipeline never invents a destination."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        intake_path = rd / "working" / "copy" / "intake.json"
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        intake["deck_brief"]["FINAL_PRICE"] = "$997"
        intake["deck_brief"]["CHECKOUT_MODE"] = "payment"
        intake_path.write_text(json.dumps(intake), encoding="utf-8")
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        rc2 = cfb.main(["--run-dir", str(rd)])
        assert rc2 == cfb.EXIT_BLOCKED
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True, reasons
        assert any("MISSING_MERCHANT" in r for r in reasons)


# ---------------------------------------------------------------------------
# PRES-025 repair: frozen-archive runner + live-stub + Skill06 seams
# ---------------------------------------------------------------------------
class TestFix17FrozenArchiveRunner:
    """fix17 archival isolation (repair item a): the 5-failed parity claim is
    re-proven by RUNNING the suite inside frozen git-archive copies of base
    and candidate -- never the live source tree, never a stash.

    Repo-root note: the git top-level is the FULL onboarding checkout, so
    archived paths are repo-relative from the worktree root
    ('23-ai-workforce-blueprint/...'). The fix17 fixture resolves its
    manifest by walking UP from scripts/ to
    universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json -- an
    UNTRACKED working file, so the archive cannot carry it. The runner
    therefore overlays the LIVE manifest path read-only (no live source
    module is imported; the manifest is data, and its version/sha is
    pinned in the assertion)."""

    SUB = "23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
    FIX17_NODE = "tests/test_fix17_verifier_import_failclosed.py"
    # Top-level single-file modules the fix17 fixture imports (sys.path =
    # scripts/): phase_verifiers itself plus everything it pulls at import.
    TOP_MODULES = ("phase_verifiers.py", "sales_checkout_builder.py",
                   "vsl_builder.py", "checkout_form_builder.py",
                   "ghl_media.py", "run_signature_deck.py")

    def _materialize(self, ref: str, dest: Path) -> Path:
        import subprocess
        dest.mkdir(parents=True, exist_ok=True)
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True,
                             cwd=Path(__file__).resolve().parent).stdout.strip()
        paths = [f"{self.SUB}/tests", f"{self.SUB}/presentation_job"]
        have = subprocess.run(
            ["git", "ls-tree", ref, "--name-only", "-r", "--",
             f"{self.SUB}/"], capture_output=True, text=True, check=True,
            cwd=top).stdout.splitlines()
        have = set(have)
        for mod in self.TOP_MODULES:
            if f"{self.SUB}/{mod}" in have:
                paths.append(f"{self.SUB}/{mod}")
        archive = subprocess.run(
            ["git", "archive", ref, *paths],
            capture_output=True, check=True, cwd=top).stdout
        if not archive:
            raise AssertionError(
                f"git archive of {ref} returned empty bytes -- frozen "
                f"materialization impossible (cwd={top})")
        import tarfile
        import io
        with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
            tf.extractall(dest)
        scripts = dest / self.SUB
        assert (scripts / self.FIX17_NODE).is_file(), (
            f"{self.FIX17_NODE} missing in frozen archive of {ref}")
        # Read-only manifest overlay (data only): the fixture walks UP from
        # scripts/ up to 12 levels looking for universal-sops/
        # presentation-slide-craft/PIPELINE-MANIFEST.json. Symlink the live
        # tree at EVERY ancestor level inside the sandbox (dest is a bare
        # tmp dir, so no live source is shadowed). No live SOURCE module is
        # imported by the fixture (sys.path points at the frozen scripts/
        # only); the manifest is data, version/sha pinned below.
        live_craft = Path(top) / "universal-sops" / "presentation-slide-craft"
        assert (live_craft / "PIPELINE-MANIFEST.json").is_file(), (
            "live manifest overlay missing -- cannot run the frozen fixture")
        node = scripts
        for _ in range(12):
            target = node / "universal-sops"
            target.mkdir(parents=True, exist_ok=True)
            link = target / "presentation-slide-craft"
            if not link.exists():
                link.symlink_to(live_craft)
            if node.parent == node:
                break
            node = node.parent
            if dest not in node.parents and node != dest:
                break
        return scripts

    def _run_fix17(self, scripts: Path) -> list:
        import subprocess
        # --rootdir pins pytest's rootdir to the frozen copy: without it,
        # pytest walks UP past the sandbox, finds the LIVE scripts/ rootdir
        # (conftest/ini markers), and imports LIVE modules -- which silently
        # changes the control outcome (6 failed instead of 5 failed).
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", self.FIX17_NODE, "-q",
             "-p", "no:cacheprovider", f"--rootdir={scripts}",
             "-c", "/dev/null"], capture_output=True, text=True,
            cwd=str(scripts), timeout=300)
        if "no tests ran" in (proc.stdout + proc.stderr).lower():
            raise AssertionError(
                f"fix17 collected zero tests in frozen archive at {scripts} "
                f"-- stdout={proc.stdout[-500:]!r} stderr={proc.stderr[-500:]!r}")
        failed = sorted(
            line.split("::", 1)[1].split(" ", 1)[0]
            for line in proc.stdout.splitlines()
            if line.startswith("FAILED "))
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        return failed, tail

    def test_fix17_frozen_archives_match_live_tree_parity(self, tmp_path):
        """Frozen base-vs-candidate archives show the IDENTICAL 5-failed set
        the verdict recorded live -- the delta is pre-existing, proven
        without touching the live tree."""
        import json as _json
        base_scripts = self._materialize("2244b00fe3a26cb8888450c881123ce21adb733e",
                                         tmp_path / "fix17base")
        cand_scripts = self._materialize("HEAD", tmp_path / "fix17cand")
        base_hash = __import__("hashlib").sha256(
            (base_scripts / self.FIX17_NODE).read_bytes()).hexdigest()
        cand_hash = __import__("hashlib").sha256(
            (cand_scripts / self.FIX17_NODE).read_bytes()).hexdigest()
        assert base_hash == cand_hash, (
            "the fix17 suite file itself must be byte-identical base-vs-"
            f"candidate (base {base_hash[:12]} vs cand {cand_hash[:12]}) -- "
            "else 'pre-existing' is unproven")
        overlay_manifest = _json.loads(
            (base_scripts / "universal-sops" / "presentation-slide-craft"
             / "PIPELINE-MANIFEST.json").read_text(encoding="utf-8"))
        assert overlay_manifest.get("manifest_version") == 68, (
            "frozen runs must resolve manifest_version 68 through the overlay")
        assert len(overlay_manifest.get("phases", [])) == 62
        base_failed, base_tail = self._run_fix17(base_scripts)
        cand_failed, cand_tail = self._run_fix17(cand_scripts)
        assert len(base_failed) == 5, f"frozen base must show 5 failed: {base_tail}"
        assert base_failed == cand_failed, (
            f"frozen parity broken -- base {base_failed} vs cand {cand_failed}")
        assert "5 failed, 2 passed" in base_tail, base_tail
        assert "5 failed, 2 passed" in cand_tail, cand_tail


# ---------------------------------------------------------------------------
# PRES-025 prep (W6 WF23 unblock prep, PREP-NOT-FINAL): fixture constants
# ---------------------------------------------------------------------------
class TestPrepFixtureConstants:
    """One synthetic GHL test location + one sandbox merchant path are
    designated as fixture constants -- synthetic, offline, no credentials."""

    def test_fixture_constants_present_and_synthetic(self):
        loc = cfb.FIXTURE_GHL_TEST_LOCATION_ID
        merch = cfb.FIXTURE_SANDBOX_MERCHANT_PATH
        assert isinstance(loc, str) and loc, "fixture location constant"
        assert isinstance(merch, str) and merch, "fixture merchant constant"
        assert "fixture" in loc or "synthetic" in loc or "pres025" in loc, loc
        assert "fixture" in merch or "synthetic" in merch or "pres025" in merch, merch
        for real in ("prod", "live", "client", "pit", "token", "secret", "key"):
            assert real not in loc.lower(), f"fixture location smells real: {loc!r}"
        assert "PREP-NOT-FINAL" in cfb.FIXTURE_DESIGNATION

    def test_same_signatures_as_prior_stubs(self):
        # The prep bodies keep the repair's method signatures exactly: a W6
        # final run can replace bodies without touching callers.
        import inspect
        assert str(inspect.signature(cfb.Skill44LiveAdapter.create_form)) == "(self, contract: 'dict') -> 'str'"
        assert str(inspect.signature(cfb.Skill44LiveAdapter.create_workflow)) == "(self, contract: 'dict', form_id: 'str') -> 'str'"
        assert str(inspect.signature(cfb.Skill44LiveAdapter.submit_lead)) == "(self, form_id: 'str', payload: 'dict') -> 'dict'"
        assert str(inspect.signature(cfb.Skill44LiveAdapter.readback)) == "(self, form_id: 'str') -> 'dict'"
        assert str(inspect.signature(cfb.Skill06LiveTaskRunner.run)) == "(self, task: 'dict', evidence_root: 'str') -> 'dict'"
        assert str(inspect.signature(cfb.ProviderSandboxLiveAdapter.create_product)) == "(self, offer: 'dict') -> 'dict'"
        assert str(inspect.signature(cfb.ProviderSandboxLiveAdapter.checkout_session)) == "(self, product: 'dict', success_url: 'str', cancel_url: 'str') -> 'dict'"
        assert issubclass(cfb.DeferralRequired, RuntimeError)


class TestFixtureAcceptanceProof:
    """QC-PRES-025 checks 2/3 against the designated synthetic fixtures:
    lead-form submit + validation + duplicates (check 2); payment-mode
    product/amount/currency mapping + success/cancel routes, zero real
    charge (check 3). Every ID is fixture-namespace; nothing real."""

    def test_check2_lead_submit_validation_duplicates(self):
        proof = cfb.fixture_acceptance_proof()
        lp = proof["lead_proof"]
        assert lp["kind"] == "lead_submit"
        assert lp["location_id"] == cfb.FIXTURE_GHL_TEST_LOCATION_ID
        assert lp["contacts"] == 1 and lp["enrollments"] == 1
        assert lp["validation_exercised"] and lp["duplicate_exercised"]
        assert proof["lead_validation_errors"], "invalid payload must error"
        assert re.fullmatch(r"fix_(form|wf|contact)_\d{4}",
                            lp["form_id"] or "fix_form_0000"), lp["form_id"]
        assert re.fullmatch(r"fix_(form|wf|contact)_\d{4}",
                            lp["workflow_id"] or "fix_wf_0000"), lp["workflow_id"]
        assert re.fullmatch(r"fix_(form|wf|contact)_\d{4}",
                            lp["contact_id"] or "fix_contact_0000"), lp["contact_id"]
        for fid in (lp["form_id"], lp["workflow_id"], lp["contact_id"]):
            assert "mem_" not in fid and not fid.startswith(("form_", "wf_", "contact_")), fid

    def test_check3_sandbox_mapping_routes_zero_charge(self):
        proof = cfb.fixture_acceptance_proof()
        sp = proof["sandbox_proof"]
        assert sp["kind"] == "sandbox_session" and sp["mode"] == "sandbox"
        assert (sp["amount_minor"], sp["currency"]) == (99700, "USD")
        assert sp["success_url"] == "https://shop.example.test/success"
        assert sp["cancel_url"] == "https://shop.example.test/cancel"
        assert sp["real_charge"] is False
        assert proof["merchant_path"] == cfb.FIXTURE_SANDBOX_MERCHANT_PATH
        assert sp["product_id"].startswith("sbx_fix_product_"), sp["product_id"]
        assert sp["session_id"].startswith("sbx_fix_session_"), sp["session_id"]

    def test_skill06_fixture_task_accepted_by_real_builder_dry_run(self, tmp_path):
        # Same task shape the runner executes: the REAL Skill 06 dry-run
        # plan path accepts it (preflight pass). Live browser never runs.
        proof = cfb.fixture_acceptance_proof()
        assert proof["skill06"]["preflight_pass"] is True
        assert proof["skill06"]["dry_run"] is True

    def test_verifier_accepts_both_fixture_proofs(self, tmp_path):
        # Wire BOTH fixture proofs into a real receipt through the real
        # producers, then verify each mode with the REAL phase verifier.
        # Lead mode.
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        assert _build_sales_checkout(rd) == scb.EXIT_OK
        assert cfb.main(["--run-dir", str(rd)]) == cfb.EXIT_OK
        proof = cfb.fixture_acceptance_proof()
        rp = rd / "working" / "sales-checkout" / "checkout_form.json"
        receipt = json.loads(rp.read_text(encoding="utf-8"))
        receipt["location_id"] = proof["location_id"]
        receipt["scope"] = proof["scope"]
        receipt["form"]["form_id"] = proof["lead_form_id"]
        receipt["form"]["action"] = "/acme-widget-checkout"
        receipt["workflow"]["workflow_id"] = proof["lead_workflow_id"]
        receipt["status"] = "complete"
        receipt["proof"] = proof["lead_proof"]
        rp.write_text(json.dumps(receipt), encoding="utf-8")
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True, reasons
        # Sandbox mode (fresh run dir: intake CHECKOUT_MODE=payment_sandbox).
        rd2 = _intake(tmp_path / "sbx", {"WANT_SALES_CHECKOUT": "yes"})
        ip2 = rd2 / "working" / "copy" / "intake.json"
        intake2 = json.loads(ip2.read_text(encoding="utf-8"))
        intake2["deck_brief"]["FINAL_PRICE"] = "$997"
        intake2["deck_brief"]["CHECKOUT_MODE"] = "payment_sandbox"
        ip2.write_text(json.dumps(intake2), encoding="utf-8")
        assert _build_sales_checkout(rd2) == scb.EXIT_OK
        assert cfb.main(["--run-dir", str(rd2)]) == cfb.EXIT_OK
        sbx_proof = cfb.fixture_acceptance_proof()
        rp2 = rd2 / "working" / "sales-checkout" / "checkout_form.json"
        receipt2 = json.loads(rp2.read_text(encoding="utf-8"))
        assert receipt2["intent"] == cfb.INTENT_PAYMENT_SANDBOX
        receipt2["location_id"] = sbx_proof["location_id"]
        receipt2["scope"] = sbx_proof["scope"]
        receipt2["form"]["form_id"] = "sbx_fix_checkout_form"
        receipt2["status"] = "complete"
        receipt2["proof"] = sbx_proof["sandbox_proof"]
        rp2.write_text(json.dumps(receipt2), encoding="utf-8")
        ok2, reasons2 = pv.verify("P-U-FORM-CHECKOUT", rd2)
        assert ok2 is True, reasons2


class TestLiveAdapterDeferralsFailClosed:
    """Refusal proofs: every seam refuses NON-designated resources -- exact
    owner + action, never a silent pass, never a real write."""

    def test_non_designated_locations_raise_deferral(self):
        messages = cfb.live_adapter_deferrals()
        assert len(messages) == 3, messages
        for msg in messages:
            assert "NO-RAISE (BAD)" not in msg, msg
            assert "W3 WF10 wave owner" in msg, msg
            assert "designate" in msg, msg

    def test_wrong_location_and_merchant_refuse(self):
        import pytest as _pt
        with _pt.raises(cfb.DeferralRequired):
            cfb.Skill44LiveAdapter("loc_REAL")
        with _pt.raises(cfb.DeferralRequired):
            cfb.Skill06LiveTaskRunner("loc_REAL")
        with _pt.raises(cfb.DeferralRequired):
            cfb.ProviderSandboxLiveAdapter("loc_REAL")
        with _pt.raises(cfb.DeferralRequired):
            cfb.ProviderSandboxLiveAdapter(
                cfb.FIXTURE_GHL_TEST_LOCATION_ID,
                merchant_path="real-merchant-path")

    def test_deferral_error_type_is_distinct(self):
        assert issubclass(cfb.DeferralRequired, RuntimeError)
        try:
            cfb.Skill44LiveAdapter("loc_probe")
        except cfb.DeferralRequired as exc:
            assert "synthetic test location" in str(exc)
        else:
            raise AssertionError("Skill44LiveAdapter(wrong-loc) must defer")


class TestSkill06DryRunCompatibility:
    """Repair item: the Skill06 task this stage emits must be ACCEPTED by the
    REAL Skill 06 builder's offline plan path (preflight pass, template plan
    + dependency plan + click list) for BOTH intents -- the seam the live
    Skill06LiveTaskRunner.run() will execute behind dry_run=False once a
    test location is designated."""

    def _run_dry(self, tmp_path: Path, intent: str):
        gfb = _skill06_tools()
        offer = {"name": "Acme Widget Mastery", "price_display": "$997",
                 "amount_minor": 99700, "currency": "USD", "price_mode": ""}
        scope = {"deck_slug": "acme-widget", "run_id": "run",
                 "location_id": "unbound-test", "location_bound": False}
        fields = cfb.build_form_schema(offer=offer, intent=intent,
                                       deck_slug="acme-widget")
        task = cfb.build_skill06_task(offer=offer, intent=intent,
                                      scope=scope, fields=fields)
        evidence = tmp_path / f"skill06-{intent}"
        evidence.mkdir(parents=True, exist_ok=True)
        return gfb.build_form(dict(task), str(evidence), dry_run=True)

    def test_skill06_dry_run_accepts_lead_task(self, tmp_path):
        res = self._run_dry(tmp_path, cfb.INTENT_LEAD)
        assert res.get("error") in (None, ""), res.get("error")
        assert (res.get("preflight") or {}).get("pass") is True, res.get("preflight")
        assert res.get("dry_run") is True
        assert len(res.get("pages") or []) == 5, res.get("pages")

    def test_skill06_dry_run_accepts_sandbox_task(self, tmp_path):
        res = self._run_dry(tmp_path, cfb.INTENT_PAYMENT_SANDBOX)
        assert res.get("error") in (None, ""), res.get("error")
        assert (res.get("preflight") or {}).get("pass") is True, res.get("preflight")
        assert res.get("dry_run") is True
        assert len(res.get("pages") or []) == 6, res.get("pages")


# ---------------------------------------------------------------------------
# P-U-VSL-BUILD
# ---------------------------------------------------------------------------
class TestVslBuildVerifier:
    def test_defer_when_flag_absent_is_a_pass(self, tmp_path):
        """WANT_VSL_PAGE defaults to 'no' but an ABSENT answer is still a
        defer, never an inferred decline (silence is not consent)."""
        rd = _intake(tmp_path, {})
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is True
        assert any("defer" in r for r in reasons)

    def test_waived_with_real_reason_is_a_pass(self, tmp_path):
        rd = _intake(tmp_path, {
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": "We don't want a gated video page.",
        })
        ok, _ = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is True

    def test_fail_closed_no_without_reason_fails(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "no"})
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is False
        assert any("fail_closed" in r for r in reasons)

    def test_elected_but_no_video_fails_hard_af_vsl_no_video(self, tmp_path):
        """NON-VACUOUS PROOF #1: elected (yes) but the P9.6 webinar video does
        not exist yet -- must FAIL with AF-VSL-NO-VIDEO, never a pass, even
        though this is a legitimate elected build in progress."""
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "yes"})
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is False
        assert any("AF-VSL-NO-VIDEO" in r for r in reasons)

    def test_elected_with_video_but_no_page_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #2: video dependency satisfied, but the VSL page
        itself was never built -- must still FAIL."""
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "yes"})
        _seed_webinar_video(rd)
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is False
        assert any("vsl.html" in r and "not found" in r for r in reasons)

    def test_elected_with_video_and_empty_page_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #3: the file exists but is empty."""
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "yes"})
        _seed_webinar_video(rd)
        html_dir = rd / "working" / "vsl" / "html"
        html_dir.mkdir(parents=True)
        (html_dir / "vsl.html").write_bytes(b"")
        ok, _ = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is False

    def test_elected_with_video_and_decoy_page_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #4: a real-looking file with no marker and no
        <video> element -- a decoy is not a real VSL page."""
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "yes"})
        _seed_webinar_video(rd)
        html_dir = rd / "working" / "vsl" / "html"
        html_dir.mkdir(parents=True)
        (html_dir / "vsl.html").write_text("<html><body><h1>decoy</h1></body></html>" + ("x" * 300))
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is False

    def test_elected_with_zero_byte_video_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF #5: the video artifact exists at the right path
        but is zero bytes -- ghl_media.verify_video's own probe must reject it
        (AF-VSL-NO-VIDEO), never a pass on a stub."""
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "yes"})
        delivery = rd / "working" / "delivery"
        delivery.mkdir(parents=True)
        (delivery / "acme-widget-WEBINAR.mp4").write_bytes(b"")
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is False
        assert any("AF-VSL-NO-VIDEO" in r for r in reasons)

    def test_elected_with_video_and_real_build_passes(self, tmp_path):
        """The genuine PASS: seed a real (fake-but-valid-MP4) P9.6 video, run
        the REAL vsl_builder.py, then verify."""
        rd = _intake(tmp_path, {"WANT_VSL_PAGE": "yes"})
        _seed_webinar_video(rd)
        rc = _build_vsl(rd)
        assert rc == vb.EXIT_OK
        ok, reasons = pv.verify("P-U-VSL-BUILD", rd)
        assert ok is True, reasons


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
