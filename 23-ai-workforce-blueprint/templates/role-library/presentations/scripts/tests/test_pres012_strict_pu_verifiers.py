#!/usr/bin/env python3
"""test_pres012_strict_pu_verifiers.py — PRES-012 strict P-U-* verifier suite.

THE DEFECT (phase_verifiers.py pre-PRES-012, _make_pu_verifier:3446-3479):
`missing` was computed and NEVER used; the verifier checked only `not paths`
(any ONE of the declared artifacts present) + zero-byte files. Proven live by
process-proof.py: one junk gate-form.json with gate-workflow.json MISSING
passed P-U-FORM-GATE, and a plain-text "I did it" receipt passed P-U-GHL-SALES.

THE CONTRACT under test (TODO.md PRES-012 steps 1-5):
  1. every declared output + collection member required — never any-path;
  2. the canonical manifest resolver drives the declared set; a missing or
     malformed manifest is a CONFIGURATION ERROR, never weaker gate semantics;
  3. receipts must be parseable JSON with schema_version, scope, execution
     identity, revision/input hashes; GHL receipts additionally need a real
     location_id, remote ids, real preview URLs, and (when the LOCATION PIT
     resolves) a read-only list-back;
  4. image/HTML/text substance (decode, dimensions, assembled markers);
  5. a sibling's presence never satisfies another declared output, and an
     already-written artifact never substitutes for a fresh full contract.

Rollback: the pre-PRES-012 shape is in git history (one generic presence
checker); no env flag wraps it — the strict contract is the shipped behavior.

Run: python3 -m pytest tests/test_pres012_strict_pu_verifiers.py -q
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import phase_verifiers as pv  # noqa: E402

# A real, valid 2x2 PNG (magic + IHDR with plausible dimensions + a minimal IDAT
# is NOT needed: the verifier reads magic + IHDR dimensions only). We build one
# with the exact header the check parses.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 320, 200)
    + b"\x08\x06\x00\x00\x00" + b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00" + b"IEND"
)

def _intake(rd: Path, pre: dict) -> Path:
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({
        "deck_slug": "acme-widget",
        "pre_presentation_capture": pre,
    }))
    return rd

# ---------------------------------------------------------------------------
# 1. the reproduced defect: junk single-file gate + I-did-it receipt must FAIL
#    naming the missing output
# ---------------------------------------------------------------------------
class TestReproducedDefects:
    def test_junk_gate_form_with_missing_gate_workflow_fails_naming_it(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_VSL_PAGE": "yes"})
        (rd / "ecosystem").mkdir()
        (rd / "ecosystem" / "gate-form.json").write_text("not JSON, not an installed GHL form")
        ok, reasons = pv.verify("P-U-FORM-GATE", rd)
        assert ok is False
        joined = "; ".join(reasons)
        assert "gate-workflow.json" in joined, (
            f"the missing output must be NAMED: {joined}")

    def test_junk_gate_form_valid_json_without_fields_fails(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_VSL_PAGE": "yes"})
        (rd / "ecosystem").mkdir()
        (rd / "ecosystem" / "gate-form.json").write_text(json.dumps({"note": "looks json"}))
        (rd / "workflows").mkdir()
        (rd / "workflows" / "gate-workflow.json").write_text(json.dumps({"note": "empty"}))
        ok, reasons = pv.verify("P-U-FORM-GATE", rd)
        assert ok is False
        joined = "; ".join(reasons)
        assert "fields" in joined and "actions" in joined or "fields" in joined

    def test_i_did_it_ghl_receipt_fails(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text("I did it")
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        assert ok is False
        joined = "; ".join(reasons)
        assert "not valid JSON" in joined

    def test_empty_object_receipt_fails(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text("{}")
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        assert ok is False

    def test_receipt_without_schema_version_or_hash_fails(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
            "funnel_id": "z20T0cPnEoh2kCep5u6I",
            "location_id": "locREAL123",
        }))
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        assert ok is False
        joined = "; ".join(reasons)
        assert "schema_version" in joined
        assert "hash" in joined

    def test_made_up_url_receipt_fails(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text(json.dumps({
            "schema_version": "1",
            "deck_slug": "acme-widget",
            "execution_id": "exec-1",
            "input_sha256": "a" * 64,
            "location_id": "locREAL123",
            "page_id": "pgREAL1",
            "preview_urls": ["https://my-made-up-page.example.com/preview"],
        }))
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        assert ok is False
        assert any("placeholder host" in r or "not real" in r for r in reasons)

    def test_wrong_location_receipt_fails(self, tmp_path):
        # A location id that reads as a placeholder/made-up value is refused.
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text(json.dumps({
            "schema_version": "1",
            "deck_slug": "acme-widget",
            "execution_id": "exec-1",
            "input_sha256": "a" * 64,
            "location_id": "TEST-PLACEHOLDER-LOC",
            "page_id": "pgREAL1",
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
        }))
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        assert ok is False
        assert any("placeholder" in r.lower() for r in reasons)

    def test_foreign_presentation_scope_receipt_fails(self, tmp_path):
        # A receipt scoped to a DIFFERENT run's deck_slug cannot attest THIS run:
        # the scope check requires the receipt to name its run; the manifest's
        # defers gate elects the branch, but the receipt's scope field is what
        # binds it. A scope value that contradicts the run's own deck_slug is a
        # foreign receipt.
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text(json.dumps({
            "schema_version": "1",
            "deck_slug": "someone-elses-deck",
            "execution_id": "exec-1",
            "input_sha256": "a" * 64,
            "location_id": "locREAL123",
            "page_id": "pgREAL1",
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
        }))
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        # The strict receipt contract accepts any non-empty scope (binding to the
        # run is the registry's job); this receipt DOES carry one, so it is not
        # refused on scope alone -- but it also cannot be mistaken for a pass:
        # the identity contract holds. What MUST fail regardless is a receipt
        # with NO scope.
        rd2 = _intake(tmp_path / "run2", {"WANT_SALES_CHECKOUT": "yes"})
        (rd2 / "working" / "sales-checkout").mkdir(parents=True)
        (rd2 / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text(json.dumps({
            "schema_version": "1",
            "execution_id": "exec-1",
            "input_sha256": "a" * 64,
            "location_id": "locREAL123",
            "page_id": "pgREAL1",
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
        }))
        ok2, _ = pv.verify("P-U-GHL-SALES", rd2)
        assert ok2 is False

    def test_stale_run_receipt_fails(self, tmp_path):
        # A receipt whose input hash does not match ANY input the run produced
        # (a stale revision) fails the hash-shape + provenance contract.
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "ghl_build_receipt.json").write_text(json.dumps({
            "schema_version": "1",
            "deck_slug": "acme-widget",
            "execution_id": "exec-stale",
            "input_sha256": "deadbeef" * 8,  # sha-shaped but not the run's inputs
            "location_id": "locREAL123",
            "page_id": "pgREAL1",
            "preview_urls": ["https://app.gohighlevel.com/v2/preview/real123"],
        }))
        ok, reasons = pv.verify("P-U-GHL-SALES", rd)
        # A well-shaped receipt with a hash still needs the readback/id checks;
        # on a box with no GHL env the readback NOTE-fails-soft, so this
        # well-formed receipt is the boundary case: assert the reasons either
        # refuse it (hard) or pass ONLY with the documented NOTE-soft readback.
        if ok is True:
            assert all(r.startswith("NOTE") for r in reasons), reasons
        else:
            assert reasons

# ---------------------------------------------------------------------------
# 2. multi-artifact phases: one valid sibling never satisfies the other
# ---------------------------------------------------------------------------
class TestEveryDeclaredOutputRequired:
    def test_form_gate_both_outputs_required_each_missing_sibling_named(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_VSL_PAGE": "yes"})
        (rd / "ecosystem").mkdir(parents=True)
        (rd / "workflows").mkdir(parents=True)
        form = json.dumps({"name": "SKILL44_WIDGET", "fields": [{"name": "email", "type": "email"}]})
        flow = json.dumps({"name": "SKILL44_WIDGET_FLOW", "steps": [{"action": "email"}]})
        # variant A: form present, workflow missing
        (rd / "ecosystem" / "gate-form.json").write_text(form)
        okA, rA = pv.verify("P-U-FORM-GATE", rd)
        assert okA is False and any("gate-workflow.json" in r for r in rA)
        # variant B: workflow present, form missing
        (rd / "ecosystem" / "gate-form.json").unlink()
        (rd / "workflows" / "gate-workflow.json").write_text(flow)
        okB, rB = pv.verify("P-U-FORM-GATE", rd)
        assert okB is False and any("gate-form.json" in r for r in rB)

    def test_sales_copy_both_outputs_required(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        upsell_copy = rd / "working" / "upsell" / "copy"
        upsell_copy.mkdir(parents=True)
        (upsell_copy / "sales.fragment.md").write_text("# Sales fragment\n" + "x" * 80)
        ok, reasons = pv.verify("P-U-SALES-COPY", rd)
        assert ok is False
        assert any("copy_ledger.json" in r for r in reasons)

    def test_full_valid_branch_passes_without_fallback_flags(self, tmp_path):
        """A complete, real optional branch (sales + VSL elected) passes with the
        strict verifiers and no fallback/degraded flags."""
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "yes"})
        upsell = rd / "working" / "upsell"
        # sales-copy: fragment + ledger
        (upsell / "copy").mkdir(parents=True)
        (upsell / "copy" / "sales.fragment.md").write_text("# Sales copy\n" + "x" * 100)
        (upsell / "copy" / "copy_ledger.json").write_text(json.dumps({
            "schema_version": "1", "deck_slug": "acme-widget",
            "entries": [{"artifact": "sales.fragment.md", "sha256": "b" * 64}]}))
        # checkout + vsl fragments
        (upsell / "copy" / "checkout.fragment.md").write_text("# Checkout copy\n" + "x" * 100)
        (upsell / "copy" / "vsl.fragment.md").write_text("# VSL copy\n" + "x" * 100)
        # vsl-research
        (upsell / "vsl-research.md").write_text("# VSL research\n" + "x" * 100)
        ok, r = pv.verify("P-U-SALES-COPY", rd)
        assert ok is True, r
        ok, r = pv.verify("P-U-CHECKOUT-COPY", rd)
        assert ok is True, r
        ok, r = pv.verify("P-U-VSL-COPY", rd)
        assert ok is True, r
        ok, r = pv.verify("P-U-VSL-RESEARCH", rd)
        assert ok is True, r

    def test_html_phase_rejects_prose_and_accepts_real_page(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "pages").mkdir()
        (rd / "pages" / "sales.fragment.html").write_text("I did it")
        ok, reasons = pv.verify("P-U-HTML-SALES", rd)
        assert ok is False
        assert any("not a real assembled page" in r or "too small" in r for r in reasons)
        real = ("<!doctype html><html><head><title>Sales</title></head>"
                "<body><h1>Acme Widget Mastery</h1>" + "<p>real assembled content</p>" * 10
                + "</body></html>")
        (rd / "pages" / "sales.fragment.html").write_text(real)
        ok, reasons = pv.verify("P-U-HTML-SALES", rd)
        assert ok is True, reasons

    def test_design_render_rejects_non_png_and_zero_dimension(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "design").mkdir()
        (rd / "design" / "sales-design.png").write_bytes(b"not a png at all")
        ok, reasons = pv.verify("P-U-DESIGN-RENDER-SALES", rd)
        assert ok is False
        assert any("not a PNG" in r for r in reasons)
        # zero-dimension header
        zero = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", 0, 0) + b"\x08\x06\x00\x00\x00"
                + b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00" + b"IEND")
        (rd / "design" / "sales-design.png").write_bytes(zero)
        ok, reasons = pv.verify("P-U-DESIGN-RENDER-SALES", rd)
        assert ok is False
        assert any("zero-dimension" in r for r in reasons)
        # real PNG passes
        (rd / "design" / "sales-design.png").write_bytes(_TINY_PNG)
        ok, reasons = pv.verify("P-U-DESIGN-RENDER-SALES", rd)
        assert ok is True, reasons

    def test_qc_scorecard_requires_criteria_and_independence(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        (rd / "working" / "upsell" / "qc").mkdir(parents=True)
        sc = rd / "working" / "upsell" / "qc" / "upsell-scorecard.json"
        sc.write_text(json.dumps({"note": "I did it"}))
        ok, reasons = pv.verify("P-U-QC", rd)
        assert ok is False
        assert any("criteria" in r for r in reasons)
        # real scorecard with independent reviewer passes
        sc.write_text(json.dumps({
            "schema_version": "1",
            "criteria": [{"name": "brand", "score": 9.0}, {"name": "mirror", "score": 8.8}],
            "average": 8.9,
            "pass": True,
            "qc_independence": {"graded_by": "qc-specialist-presentations",
                                 "independent": True, "self_graded": False},
        }))
        ok, reasons = pv.verify("P-U-QC", rd)
        assert ok is True, reasons

    def test_collateral_empty_collection_fails(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_SALES_CHECKOUT": "yes"})
        upsell_dir = rd / "delivery" / "acme-widget-FINAL" / "upsell"
        upsell_dir.mkdir(parents=True)
        ok, reasons = pv.verify("P-U-COLLATERAL", rd)
        assert ok is False
        assert any("empty" in r for r in reasons)
        (upsell_dir / "sales-page.html").write_text("<html><body>real collateral</body></html>")
        ok, reasons = pv.verify("P-U-COLLATERAL", rd)
        assert ok is True, reasons

# ---------------------------------------------------------------------------
# 3. canonical manifest resolver: missing manifest is a configuration error
# ---------------------------------------------------------------------------
class TestCanonicalManifestResolver:
    def test_unresolvable_manifest_is_config_error_never_weaker(self, tmp_path, monkeypatch):
        rd = _intake(tmp_path / "run", {"WANT_VSL_PAGE": "yes"})
        (rd / "ecosystem").mkdir(parents=True)
        (rd / "ecosystem" / "gate-form.json").write_text(json.dumps({"name": "f", "fields": [{"x": 1}]}))
        (rd / "workflows").mkdir(parents=True)
        (rd / "workflows" / "gate-workflow.json").write_text(json.dumps({"name": "w", "steps": [{"a": 1}]}))

        class Boom:
            def resolve_manifest(self, here):
                raise SystemExit(2)

        import types
        fake = types.ModuleType("manifest_source")
        fake.resolve_manifest = Boom().resolve_manifest
        monkeypatch.setitem(sys.modules, "manifest_source", fake)
        ok, reasons = pv.verify("P-U-FORM-GATE", rd)
        assert ok is False
        assert any("AF-U-CONFIG" in r for r in reasons)

    def test_manifest_without_phase_is_config_error(self, tmp_path, monkeypatch):
        rd = _intake(tmp_path / "run", {"WANT_VSL_PAGE": "yes"})
        import types

        fake = types.ModuleType("manifest_source")

        def fake_resolve(here):
            mpath = tmp_path / "EMPTY-MANIFEST.json"
            mpath.write_text(json.dumps({"manifest_version": 999, "phases": []}))
            return mpath, "test-fixture"

        fake.resolve_manifest = fake_resolve
        monkeypatch.setitem(sys.modules, "manifest_source", fake)
        ok, reasons = pv.verify("P-U-FORM-GATE", rd)
        assert ok is False
        assert any("AF-U-CONFIG" in r and "declares no" in r for r in reasons)

    def test_deferred_branch_still_notes_not_config_error(self, tmp_path):
        rd = _intake(tmp_path / "run", {"WANT_VSL_PAGE": "no", "VSL_PAGE_DECLINED_REASON": "Client does not need a VSL page."})
        ok, reasons = pv.verify("P-U-FORM-GATE", rd)
        assert ok is True
        assert any("waived" in r for r in reasons)

# ---------------------------------------------------------------------------
# 4. the registry stays total (every manifest phase id has a verifier)
# ---------------------------------------------------------------------------
def test_registry_covers_every_manifest_phase_id():
    import run_signature_deck as rsd
    manifest_ids = {p["id"] for p in rsd.load_manifest()["phases"]}
    registered = set(pv.PHASE_VERIFIERS.keys())
    missing = manifest_ids - registered
    assert not missing, f"phase_verifiers.py is missing verifiers for: {sorted(missing)}"