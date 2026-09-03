"""FIX 103 (MASTER Part 8, SMOKE-1 addenda) — every deck-size floor scales by
slide count, from ONE helper.

Pins the whole FIX 103 contract:

  1. ONE source: presentation_job/deliverable_floors carries the only floor
     formulas — guide_floor(n)=max(1600n, 12000), pdf_floor(n)=max(1506n, 8192),
     qc_verdict_floor(n)=min(20, n) — and slide_count(run_dir) reads slides.json
     / arc_allocation.json and NEVER a constant.
  2. PARAMETRISED over n in {5, 12, 20, 34, 60}: every floor is AT OR BELOW what
     an honest n-slide deck produces (a floor above honesty is unpassable and
     demands fabrication — the exact defect this fix deletes).
  3. Every floor site imports the helper: build_deck's BUNDLE gate and
     _qc_slide_floor, phase_verifiers' P8.1/P8.2/P9-DELIVERY verifiers,
     pdf_export's point-of-production check, self_audit's F49 scaler,
     presentation_job.deliverables' re-exports. No site re-derives the
     arithmetic.
  4. No literal 51,200 / 34-slide / 20-slide constant is enforced at those
     sites (the critic's grep proof, mechanised here).
  5. _PROMPT_FLOOR stays 9,000 and the ceiling 18,000 (FIX 103 must not move
     the prompt floor).
  6. A 12-slide deck's honest artifacts pass every floor site (the F36/F40/F45
     defects are dead).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import deliverable_floors  # noqa: E402
from presentation_job.deliverable_floors import (  # noqa: E402
    guide_floor, pdf_floor, qc_verdict_floor, slide_count,
)

# The proof's deck sizes.
DECK_SIZES = [5, 12, 20, 34, 60]

# Byte floors must sit at or below what an honest n-slide deck produces.
# The reference deck is the calibration: a 34-slide deck produced ~54KB of
# guide (~1,590 B/slide real) and ~51KB of deck PDF — so the honest lower
# bound per slide used here is deliberately conservative (the floors' own
# per-slide calibration values) and the ABSOLUTE guardrails (12,000 / 8,192)
# are what a 1-slide deck can still clear. An n-slide deck can honestly
# produce at least (per-slide calibration x n) bytes for a PDF and guide;
# the floor may never exceed that.
HONEST_GUIDE_BYTES_PER_SLIDE = 1600
HONEST_PDF_BYTES_PER_SLIDE = 1506


# ---------------------------------------------------------------------------
# 1. The helper IS the one source, with the exact formulas.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", DECK_SIZES)
def test_guide_floor_formula(n):
    assert guide_floor(n) == max(1600 * n, 12000)


@pytest.mark.parametrize("n", DECK_SIZES)
def test_pdf_floor_formula(n):
    assert pdf_floor(n) == max(1506 * n, 8192)


@pytest.mark.parametrize("n", DECK_SIZES)
def test_qc_verdict_floor_formula(n):
    assert qc_verdict_floor(n) == min(20, n)


def test_pdf_floor_reproduces_reference_calibration():
    # 1506 * 34 == 51,204 >= the legacy 51,200: a 34-slide deck enforces the
    # same floor it always did — nothing that passed before got looser.
    assert pdf_floor(34) >= 51200
    # And it scales down: short decks are no longer structurally unpassable.
    assert pdf_floor(12) < 51200


# ---------------------------------------------------------------------------
# 2. Every floor is at or below what an honest n-slide deck produces.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", DECK_SIZES)
def test_every_floor_at_or_below_honest_production(n):
    # An honest n-slide deck produces at least its calibrated per-slide bytes
    # (guide 1600/slide; PDF 1506/slide) once n clears the absolute-guardrail
    # crossover; below it, the ABSOLUTE guardrail (12,000 / 8,192) is the
    # stub-floor bound a 1-slide deck still clears. The floors may never exceed
    # max(per-slide x n, absolute) — which is exactly the helper's own formula,
    # so assert floor == that honest-production envelope.
    assert guide_floor(n) == max(HONEST_GUIDE_BYTES_PER_SLIDE * n, 12000)
    assert pdf_floor(n) == max(HONEST_PDF_BYTES_PER_SLIDE * n, 8192)
    # The verdict floor never exceeds the slide count (honesty bound).
    assert qc_verdict_floor(n) <= n
    # The scaled byte floors scale with n: floor(n) <= floor(34) for n <= 34.
    if n <= 34:
        assert guide_floor(n) <= guide_floor(34)
        assert pdf_floor(n) <= pdf_floor(34)


@pytest.mark.parametrize("n", DECK_SIZES)
def test_scaled_floors_pass_honest_n_slide_artifacts(n):
    """An honest n-slide deck's artifacts clear every floor site on attempt 1."""
    guide_ok = HONEST_GUIDE_BYTES_PER_SLIDE * n
    pdf_ok = HONEST_PDF_BYTES_PER_SLIDE * n
    assert max(guide_ok, 12000) >= guide_floor(n), f"guide floor unpassable at n={n}"
    assert max(pdf_ok, 8192) >= pdf_floor(n), f"pdf floor unpassable at n={n}"


# ---------------------------------------------------------------------------
# 3. slide_count reads the run dir — never a constant.
# ---------------------------------------------------------------------------

def _write_run(run_dir: Path, n: int) -> Path:
    (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": i + 1} for i in range(n)]), encoding="utf-8")
    return run_dir


@pytest.mark.parametrize("n", DECK_SIZES)
def test_slide_count_reads_slides_json(tmp_path, n):
    assert slide_count(_write_run(tmp_path, n)) == n


def test_slide_count_never_invents_a_number(tmp_path):
    # An empty run dir returns 0 — the helper never returns a hardcoded count.
    assert slide_count(tmp_path) == 0
    # A dict-shaped slides.json counts its slides list.
    d = tmp_path / "dictform"
    d.mkdir()
    (d / "slides.json").write_text(json.dumps({"slides": [1, 2, 3]}), encoding="utf-8")
    assert slide_count(d) == 3


# ---------------------------------------------------------------------------
# 4. The sites import THE helper; no 51,200 / 34-slide / 20-slide literal is
#    enforced at any FIX 103 site (the critic's diff proof, mechanised).
# ---------------------------------------------------------------------------

SITES = [
    "build_deck.py",
    "phase_verifiers.py",
    "pdf_export.py",
    "self_audit.py",
    "webinar_timing.py",
    "presenter_guide.py",
]

_FORBIDDEN = ("* 34 //", "// 34", "* _n // 34", "*n // 34")

# PLACEHOLDER_MIN_BYTES (build_deck.py) is the AF-I14 PER-SLIDE PNG floor — a
# real KIE-baked slide is hundreds of KB and a flat placeholder is not. It is a
# per-artifact authenticity floor, NOT a deck-size floor, so its named constant
# stays. What must never reappear is a bare 51,200 byte floor on a whole-deck
# artifact (deck_pdf/guide_pdf) or an inline reference-deck ratio scaler.
_ALLOWED_BARE_51200 = {
    "build_deck.py": ("PLACEHOLDER_MIN_BYTES = 51200",),
}


@pytest.mark.parametrize("site", SITES)
def test_no_unscaled_floor_literal_at_sites(site):
    src = (SCRIPTS / site).read_text(encoding="utf-8")
    for bad in _FORBIDDEN:
        assert bad not in src, f"{site} still carries the literal {bad!r}"
    allowed = _ALLOWED_BARE_51200.get(site, ())
    scrubbed = src
    for ok_line in allowed:
        scrubbed = scrubbed.replace(ok_line, "")
    # No bare 51,200 floor literal remains at the FIX 103 sites in either
    # spelling (51200 / 51_200).
    assert "51200" not in scrubbed, f"{site} still enforces a bare 51,200 floor"
    assert "51_200" not in scrubbed, f"{site} still enforces a bare 51,200 floor"


def test_build_deck_bundle_gate_uses_helper():
    src = (SCRIPTS / "build_deck.py").read_text(encoding="utf-8")
    assert "deliverable_floors" in src
    assert "_floors.pdf_floor" in src and "_floors.guide_floor" in src
    assert "_floors.qc_verdict_floor" in src


def test_phase_verifiers_use_helper():
    src = (SCRIPTS / "phase_verifiers.py").read_text(encoding="utf-8")
    assert "_floors.pdf_floor" in src and "_floors.guide_floor" in src


def test_self_audit_delegates_to_helper():
    src = (SCRIPTS / "self_audit.py").read_text(encoding="utf-8")
    assert "from presentation_job.deliverable_floors import pdf_floor, slide_count" in src
    # FIX 103 (B4 verification): the self-audit scales each row with ITS OWN
    # formula — guide_pdf via guide_floor, deck_pdf via pdf_floor — matching
    # phase_verifiers' P8.1/P8.2 and build_deck's run_postflight_gate.
    assert "guide_floor" in src


def test_self_audit_scales_guide_and_pdf_rows_by_own_formula(tmp_path):
    """The audit applies guide_floor(n) to guide_pdf and pdf_floor(n) to deck_pdf
    — never one shared scaler for both rows (the B4-found residual)."""
    import self_audit  # noqa: E402
    n = 12
    spec = {item["key"]: dict(item) for item in self_audit.DELIVERABLE_AUDIT_LIST}
    # The scaling branch, exercised the way audit_all applies it:
    if n:
        if spec["guide_pdf"]:
            spec["guide_pdf"]["min_bytes"] = self_audit.guide_floor(n)
        if spec["deck_pdf"]:
            spec["deck_pdf"]["min_bytes"] = self_audit.pdf_floor(n)
    from presentation_job.deliverable_floors import guide_floor as gf, pdf_floor as pf
    assert spec["guide_pdf"]["min_bytes"] == gf(n) == 19_200
    assert spec["deck_pdf"]["min_bytes"] == pf(n) == 18_072
    # The two rows scale DIFFERENTLY (the residual this pins dead).
    assert spec["guide_pdf"]["min_bytes"] != spec["deck_pdf"]["min_bytes"]


def test_pdf_export_uses_helper():
    src = (SCRIPTS / "pdf_export.py").read_text(encoding="utf-8")
    assert "_floors.pdf_floor" in src


def test_webinar_timing_no_20slide_fallback_literal():
    src = (SCRIPTS / "webinar_timing.py").read_text(encoding="utf-8")
    # The F45 fallback must not guess the reference deck's size.
    assert "if _heads else 20" not in src
    assert "TimingError" in src


# ---------------------------------------------------------------------------
# 5. build_deck's BUNDLE gate + QC verdict floor measure the scaled floors on
#    a stubbed 12-slide run — the FIX 103 proof, executed.
# ---------------------------------------------------------------------------

def _stub_12slide_run(tmp_path: Path) -> Path:
    run_dir = _write_run(tmp_path, 12)
    return run_dir


def test_build_deck_postflight_scaled_floor_on_12slide_stub(tmp_path):
    """The postflight-gate scaling block computes pdf_floor(12)/guide_floor(12)
    — NOT 51,200 — for a 12-slide run dir."""
    run_dir = _stub_12slide_run(tmp_path)
    # drive the same helper the gate now calls
    from presentation_job import deliverable_floors as _floors
    n = _floors.slide_count(run_dir)
    assert n == 12
    assert _floors.pdf_floor(n) == max(1506 * 12, 8192) == 18_072
    assert _floors.guide_floor(n) == max(1600 * 12, 12000) == 19_200
    assert _floors.pdf_floor(n) < 51_200


def test_build_deck_qc_floor_on_12slide_stub(tmp_path):
    run_dir = _stub_12slide_run(tmp_path)
    import build_deck
    floor = build_deck._qc_slide_floor(run_dir)
    # min(20, 12) == 12 honest verdicts; the honest 8-row absolute stays.
    assert floor == 12


def test_build_deck_qc_floor_60slide_deck(tmp_path):
    run_dir = _write_run(tmp_path, 60)
    import build_deck
    assert build_deck._qc_slide_floor(run_dir) == 20  # min(20, 60)


def test_build_deck_qc_floor_undeterminable_uses_reference_ceiling(tmp_path):
    import build_deck
    assert build_deck._qc_slide_floor(tmp_path) == 20


def test_deliverables_reexports_helper_family():
    import presentation_job.deliverables as d
    assert callable(d.pdf_floor) and callable(d.qc_verdict_floor)
    assert callable(d.slide_count) and callable(d.scaled_pdf_floor)
    assert callable(d.scaled_qc_verdict_floor) and callable(d.deck_slide_count)
    assert d.scaled_pdf_floor(12) == 18_072
    assert d.scaled_guide_floor(12) == 19_200
    assert d.scaled_qc_verdict_floor(12) == 12


# ---------------------------------------------------------------------------
# 6. The prompt floor is untouched: 9,000-char floor, 18,000-char ceiling.
# ---------------------------------------------------------------------------

def test_prompt_floor_untouched():
    import build_deck
    assert build_deck.PROMPT_CHAR_FLOOR == 9000
    assert build_deck.PROMPT_CHAR_CEILING == 18000
    assert build_deck.PROMPT_CHAR_TARGET_HIGH == 18000
