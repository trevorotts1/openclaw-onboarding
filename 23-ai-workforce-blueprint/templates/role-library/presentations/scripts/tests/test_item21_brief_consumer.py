#!/usr/bin/env python3
"""test_item21_brief_consumer.py - FIX-PLAN Item 21 (the page-brief
consumer: brief in, install plan + brief-bound receipts out, Skill 44
gate-form embeds delivered).

Pins, against fixture briefs emitted by page_brief itself and page HTML
built by the real builders' own HTML functions:
  * the end-to-end stub run: plan executed against the stub installer,
    receipts out, Item 20's verifier judges every phase complete, the
    brief binding carried per page, one funnel shared by sales/checkout/
    VSL, the checkout embed + all-required consent read-back in the
    receipt, the VSL gate embed shipped with vsl_builder's native
    capture-nothing form removed;
  * a tampered brief hash fails the binding;
  * a failed read-back (page not a draft) marks that page failed in the
    receipt, never success, and blocks the VSL phase on the one-funnel
    rule;
  * a consent read-back that violates the 2026-10-13 all-required
    posture fails the checkout page;
  * a superseded brief's receipt judges stale via page_brief's
    --verify-receipts semantics;
  * delegated mode: plans + pending receipts carrying the binding, no
    page touched;
  * the approved-checkout-URL reuse path creates no form and embeds
    nothing, and the shipped checkout page routes to the approved URL;
  * the splices fail closed when the native form is absent;
  * a run with no emitted briefs is blocked, not silently passed.

Flat file inside tests/, manages its own import path - matching every
sibling in this directory. Offline and deterministic: no network, no
kie.ai spend, no GHL call.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import ghl_external_installer as gx  # noqa: E402
import page_brief as pb  # noqa: E402
import page_brief_consumer as pbc  # noqa: E402
import sales_checkout_builder as scb  # noqa: E402

LOCATION = "loc-test-1"
APPROVED_URL = "https://pay.acme-brief.shop/acme-brief/checkout"


@pytest.fixture(autouse=True)
def _clean_ghl_env(monkeypatch):
    # gx.shared_funnel_id reads the process env (the installer's own
    # default); keep every test deterministic on any box.
    monkeypatch.delenv("GOHIGHLEVEL_LOCATION_ID", raising=False)
    monkeypatch.delenv("GHL_LOCATION_ID", raising=False)


def _run(tmp_path: Path, name: str = "case") -> Path:
    return pbc._fixture_run(tmp_path / name)


def _consume(run: Path, **kw):
    kw.setdefault("env", {})
    return pbc.consume(run, **kw)


# ---------------------------------------------------------------------------
# 1) The end-to-end stub run
# ---------------------------------------------------------------------------
def test_end_to_end_stub_run(tmp_path):
    run = _run(tmp_path)
    code, results = _consume(run, mode=pbc.MODE_STUB)
    assert code == pbc.EXIT_OK, results
    for phase_id in pbc.PHASE_ORDER:
        assert results[phase_id]["outcome"] == "complete", \
            results[phase_id]

    # Item 20's own verifier judges every phase complete.
    vcode, vres = pb.verify_receipts(run, env={})
    assert vcode == pb.EXIT_OK, vres
    for phase_id in pbc.PHASE_ORDER:
        assert vres[phase_id]["status"] == "complete", vres[phase_id]
        assert vres[phase_id]["binding_errors"] == []

    # One funnel across sales/checkout/VSL (one-funnel rule).
    sales = gx.load_receipt(run, pbc.PHASE_SALES)
    vsl = gx.load_receipt(run, pbc.PHASE_VSL)
    assert sales["remote"]["funnel_id"] == vsl["remote"]["funnel_id"]

    # Receipt return: brief binding per page + urls per installed page.
    for phase_id in pbc.PHASE_ORDER:
        data = gx.load_receipt(run, phase_id)
        assert pb.check_brief_binding(run, phase_id, data) == []
    assert set(sales["urls"]) == {sales["remote"]["sales_page_id"],
                                  sales["remote"]["checkout_page_id"]}
    assert set(vsl["urls"]) == {vsl["remote"]["vsl_page_id"]}

    # The checkout form step: form + workflow ids, consent read-back
    # carried in the receipt, all-required per the 2026-10-13 ruling.
    assert sales["form"]["form_id"].startswith("form_mem_")
    assert sales["workflow"]["workflow_id"].startswith("wf_mem_")
    assert sales["workflow"]["draft_only"] is True
    rb_form = sales["readback"]["form"]
    boxes = rb_form["consent"]["boxes"]
    assert boxes and all(b["required"] is True for b in boxes)
    assert all(b["default_unchecked"] is True for b in boxes)
    assert results[pbc.PHASE_SALES]["form"]["form_id"] == \
        sales["form"]["form_id"]

    # The embeds shipped in the pages; the native forms did not.
    checkout_html = (run / pbc.CHECKOUT_HTML_REL).read_text(
        encoding="utf-8")
    snippet = pbc.stub_embed_snippet(sales["form"]["form_id"],
                                     sales["form"]["name"])
    assert snippet in checkout_html
    assert pbc.CHECKOUT_FORM_MARKER not in checkout_html
    vsl_html = (run / pbc.VSL_HTML_REL).read_text(encoding="utf-8")
    assert pbc.VSL_FORM_MARKER not in vsl_html
    assert "zhc-skill44-embed" in vsl_html
    assert 'id="zhc-vsl-gate-acme-brief"' in vsl_html

    # The gate pair BOTH carry the binding (B30's verifier reads the
    # primary; the pair is the receipt).
    for path in gx.receipt_paths(run, pbc.PHASE_GATE):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert (data.get("brief_binding") or {}).get("briefs"), path

    # Plan + consumer ledger artifacts exist.
    assert (run / pbc.CONSUMER_PLAN_REL).is_file()
    ledger = json.loads((run / pbc.CONSUMER_LEDGER_REL).read_text(
        encoding="utf-8"))
    assert ledger["phases"][pbc.PHASE_SALES]["outcome"] == "complete"


# ---------------------------------------------------------------------------
# 2) Tampered brief hash fails the binding
# ---------------------------------------------------------------------------
def test_tampered_brief_hash_fails_binding(tmp_path):
    run = _run(tmp_path)
    code, _ = _consume(run, mode=pbc.MODE_STUB)
    assert code == pbc.EXIT_OK
    vsl_path, _brief = pb.latest_brief(run, "vsl")
    vsl_path.write_text(vsl_path.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8")
    errs = pb.check_brief_binding(run, pbc.PHASE_VSL,
                                  gx.load_receipt(run, pbc.PHASE_VSL))
    assert errs and any("sha256" in e for e in errs), errs
    vcode, vres = pb.verify_receipts(run, env={})
    assert vcode == pb.EXIT_VERIFY_FAILED
    assert vres[pbc.PHASE_VSL]["status"] == "invalid"


# ---------------------------------------------------------------------------
# 3) A failed read-back marks the page failed
# ---------------------------------------------------------------------------
class _DraftLyingPageAdapter(pbc.StubSkill06PageAdapter):
    """Read-back claims the checkout page is NOT a draft (published
    against the brief's drafts-only posture)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._checkout_pid = None

    def install_page(self, funnel_id, page):
        pid = super().install_page(funnel_id, page)
        if page.get("key") == "checkout":
            self._checkout_pid = pid
        return pid

    def readback_page(self, page_id):
        rb = super().readback_page(page_id)
        if page_id == self._checkout_pid:
            rb["draft"] = False
        return rb


def test_failed_readback_marks_page_failed(tmp_path):
    run = _run(tmp_path)
    code, results = _consume(
        run, mode=pbc.MODE_STUB,
        adapters={"page": _DraftLyingPageAdapter(LOCATION, run)})
    assert code == pbc.EXIT_VERIFY_FAILED, results
    assert results[pbc.PHASE_SALES]["outcome"] == "failed"
    assert any("DRAFT" in f for f in results[pbc.PHASE_SALES]["failures"])

    receipt = gx.load_receipt(run, pbc.PHASE_SALES)
    assert receipt["status"] not in gx.STATUSES_COMPLETE
    rb = receipt["readback"]
    assert rb["ok"] is False
    checkout_pid = receipt["remote"]["checkout_page_id"]
    sales_pid = receipt["remote"]["sales_page_id"]
    assert rb["pages"][checkout_pid]["ok"] is False
    assert "ok" not in rb["pages"][sales_pid] or \
        rb["pages"][sales_pid].get("ok") is not False

    # The unverifiable sales funnel blocks the VSL phase (one funnel).
    assert results[pbc.PHASE_VSL]["outcome"] == "blocked"
    vcode, _vres = pb.verify_receipts(run, env={})
    assert vcode == pb.EXIT_VERIFY_FAILED


# ---------------------------------------------------------------------------
# 4) A consent read-back violating the ruling fails the checkout page
# ---------------------------------------------------------------------------
class _ConsentLyingAdapter(pbc.StubSkill44CheckoutAdapter):
    """Read-back reports a consent box as not required (the superseded
    D3 posture) - the consumer must refuse it."""

    def readback(self, form_id):
        rb = copy.deepcopy(super().readback(form_id))
        rb["consent"]["boxes"][0]["required"] = False
        return rb


def test_consent_readback_tamper_fails_checkout(tmp_path):
    run = _run(tmp_path)
    code, results = _consume(
        run, mode=pbc.MODE_STUB,
        adapters={"checkout": _ConsentLyingAdapter(LOCATION)})
    assert code == pbc.EXIT_VERIFY_FAILED, results
    assert results[pbc.PHASE_SALES]["outcome"] == "failed"
    assert any("consent" in f for f in
               results[pbc.PHASE_SALES]["failures"])
    receipt = gx.load_receipt(run, pbc.PHASE_SALES)
    assert receipt["status"] not in gx.STATUSES_COMPLETE
    checkout_pid = receipt["remote"]["checkout_page_id"]
    assert receipt["readback"]["pages"][checkout_pid]["ok"] is False


# ---------------------------------------------------------------------------
# 5) A superseded brief's receipt judges stale
# ---------------------------------------------------------------------------
def test_superseded_brief_receipt_judges_stale(tmp_path):
    run = _run(tmp_path)
    code, _ = _consume(run, mode=pbc.MODE_STUB)
    assert code == pbc.EXIT_OK
    (run / "working/sales-checkout/copy/sales.md").write_text(
        "# Sales copy v2\nChanged copy for the second emission.\n",
        encoding="utf-8")
    code, _ = pb.emit(run, profile=None, env={})
    assert code == pb.EXIT_OK
    _p, current = pb.latest_brief(run, "sales")
    assert current["version"] == 2
    vcode, vres = pb.verify_receipts(run, env={})
    assert vcode == pb.EXIT_VERIFY_FAILED
    binding_errs = vres[pbc.PHASE_SALES]["binding_errors"]
    assert any("version" in e for e in binding_errs), binding_errs
    assert vres[pbc.PHASE_SALES]["status"] == "invalid"


# ---------------------------------------------------------------------------
# 6) Delegated mode: plans + pending brief-bound receipts, pages untouched
# ---------------------------------------------------------------------------
def test_delegated_mode_pending_receipts_carry_binding(tmp_path):
    run = _run(tmp_path)
    code, results = _consume(run, mode=pbc.MODE_DELEGATED)
    assert code == pbc.EXIT_OK, results
    for phase_id in pbc.PHASE_ORDER:
        assert results[phase_id]["outcome"] == \
            "pending_external_execution"
        data = gx.load_receipt(run, phase_id)
        assert data["status"] == gx.STATUS_PENDING
        assert pb.check_brief_binding(run, phase_id, data) == []
    # No session, no splice: the native forms are exactly as built.
    checkout_html = (run / pbc.CHECKOUT_HTML_REL).read_text(
        encoding="utf-8")
    assert pbc.CHECKOUT_FORM_MARKER in checkout_html
    assert "zhc-skill44-embed" not in checkout_html
    vsl_html = (run / pbc.VSL_HTML_REL).read_text(encoding="utf-8")
    assert pbc.VSL_FORM_MARKER in vsl_html
    # Plans exist for the delegated session (Item 22).
    assert (run / pbc.CONSUMER_PLAN_REL).is_file()
    assert (run / "working/sales-checkout/ghl_install_plan.json").is_file()
    assert (run / "working/vsl/gate_form_skill44_plan.json").is_file()
    # A present-but-pending receipt never judges complete.
    vcode, vres = pb.verify_receipts(run, env={})
    assert vcode == pb.EXIT_VERIFY_FAILED
    assert all(vres[p]["status"] != "complete" for p in pbc.PHASE_ORDER)


# ---------------------------------------------------------------------------
# 7) Approved-URL reuse: no form created, nothing embedded
# ---------------------------------------------------------------------------
def test_approved_url_reuse_creates_no_form(tmp_path):
    run = _run(tmp_path)
    intake_path = run / "working" / "copy" / "intake.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    intake["deck_brief"]["APPROVED_CHECKOUT_URL"] = APPROVED_URL
    intake_path.write_text(json.dumps(intake, indent=2), encoding="utf-8")
    code, _ = pb.emit(run, profile=None, env={})
    assert code == pb.EXIT_OK
    _p, checkout_brief = pb.latest_brief(run, "checkout")
    assert checkout_brief["approved_checkout_url"]["url"] == APPROVED_URL
    # Rebuild the checkout page the way the builders do on the reuse
    # path: its form action IS the approved URL.
    brand = scb.resolve_brand(run, intake)
    brief = intake["deck_brief"]
    fields = scb._content_fields_for_page("checkout", brief,
                                          intake["company"])
    html = scb.build_page_html(
        page_role="checkout", brand=brand, client_name=intake["company"],
        fields=dict(fields, order_line="Momentum Method - $997",
                    reassurance="Secure checkout.", cta_href=APPROVED_URL),
        hero_image_src=None, marker="ZHC-SC-acme-brief",
        deck_slug="acme-brief")
    (run / pbc.CHECKOUT_HTML_REL).write_text(html, encoding="utf-8")

    code, results = _consume(run, mode=pbc.MODE_STUB)
    assert code == pbc.EXIT_OK, results
    sales = gx.load_receipt(run, pbc.PHASE_SALES)
    assert sales["form"]["form_id"] == "reuse:approved-url"
    shipped = (run / pbc.CHECKOUT_HTML_REL).read_text(encoding="utf-8")
    assert "zhc-skill44-embed" not in shipped
    assert APPROVED_URL in shipped
    vcode, _vres = pb.verify_receipts(run, env={})
    assert vcode == pb.EXIT_OK


# ---------------------------------------------------------------------------
# 8) The splices fail closed
# ---------------------------------------------------------------------------
def test_splices_fail_closed_without_native_form():
    with pytest.raises(pbc.SpliceError):
        pbc.splice_checkout_embed("<div>nothing</div>", "SNIP",
                                  "form_mem_0001")
    with pytest.raises(pbc.SpliceError):
        pbc.splice_vsl_gate_embed("<div>nothing</div>", "SNIP",
                                  "form_mem_0001", "acme-brief")


def test_checkout_contract_comes_from_the_brief(tmp_path):
    run = _run(tmp_path)
    _p, checkout = pb.latest_brief(run, "checkout")
    scope = {k: checkout["scope"][k] for k in
             ("deck_slug", "run_id", "company", "location_id")}
    contract = pbc.build_checkout_contract(checkout, scope)
    assert contract["form"]["name"] == "ZHC acme-brief Checkout"
    assert contract["intent"] == "lead_capture"
    boxes = contract["form"]["consent"]["boxes"]
    assert boxes and all(b["required"] is True for b in boxes)
    assert all(b["default_unchecked"] is True for b in boxes)
    assert contract["form"]["consent"]["posture"] == "all_required"


# ---------------------------------------------------------------------------
# 9) No briefs: blocked, never a silent pass
# ---------------------------------------------------------------------------
def test_no_briefs_is_blocked(tmp_path):
    run = tmp_path / "bare-run"
    (run / "working" / "copy").mkdir(parents=True)
    (run / "working" / "copy" / "intake.json").write_text(
        json.dumps({"deck_slug": "bare", "company": "Bare Co"}),
        encoding="utf-8")
    code, results = _consume(run, mode=pbc.MODE_STUB)
    assert code == pbc.EXIT_BLOCKED
    assert all(r["outcome"] == "no_brief" for r in results.values())
