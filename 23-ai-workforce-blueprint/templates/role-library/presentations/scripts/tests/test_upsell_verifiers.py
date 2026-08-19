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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import phase_verifiers as pv  # noqa: E402
import sales_checkout_builder as scb  # noqa: E402
import vsl_builder as vb  # noqa: E402

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
        """NON-VACUOUS PROOF: elected, sales/checkout genuinely built, but the
        delegated GHL push receipt has not landed yet -- must FAIL, not pass,
        because produces_artifact names build_receipt.json specifically."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        assert not (rd / "working" / "sales-checkout" / "build_receipt.json").exists()
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("build_receipt.json" in r for r in reasons)

    def test_elected_with_fabricated_receipt_fails_hard(self, tmp_path):
        """NON-VACUOUS PROOF: a PRESENT but placeholder receipt (example.com
        preview url) must FAIL, not pass -- a caller-authored preview proves
        no page was really built."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        sc_dir = rd / "working" / "sales-checkout"
        (sc_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://example.com/fake"],
            "funnel_id": "abc123",
        }))
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("placeholder" in r for r in reasons)

    def test_elected_with_receipt_missing_funnel_id_fails_hard(self, tmp_path):
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        sc_dir = rd / "working" / "sales-checkout"
        (sc_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
        }))
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is False
        assert any("funnel_id" in r for r in reasons)

    def test_elected_with_real_receipt_passes(self, tmp_path):
        """The genuine PASS: a real-shaped receipt (real host, non-empty
        funnel_id) verifies via the SAME verify_push_receipt() the executor
        itself calls."""
        rd = _intake(tmp_path, {"WANT_SALES_CHECKOUT": "yes"})
        rc = _build_sales_checkout(rd)
        assert rc == scb.EXIT_OK
        sc_dir = rd / "working" / "sales-checkout"
        (sc_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
            "funnel_id": "z20T0cPnEoh2kCep5u6I",
        }))
        ok, reasons = pv.verify("P-U-FORM-CHECKOUT", rd)
        assert ok is True, reasons


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
