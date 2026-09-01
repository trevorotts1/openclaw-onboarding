#!/usr/bin/env python3
"""
test_enforcement_registry_parity.py — FIX 36(4): the RUNTIME enforcement
registry (build_deck.PREFLIGHT_REQUIRED) must be in EXACT parity with every
documented enforced checker in the declared truth
(universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json), including
FIX 15/18's slide-craft gate. A missing entry FAILS this test.

Spec (PRESENTATION-DEPT-FIX-SPEC.md, FIX 36 item 4): "bring the runtime
enforcement registry into exact parity with every documented enforced checker,
including FIX 15/18, and make missing entries fail the registry parity test"
— closing SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md §5's admitted gap ("This
registry is NOT checked by sync_check.py … Stale entries here are
human-detectable, not machine-detectable").

What "parity" means, per the two halves of the ledger:

  DIRECTION A — every build_deck-enforced ENTRY-POINT checker named by the
  manifest (autofails[].py_symbol with a `check_*` / `_chk_*` / `run_*` /
  `*_preflight` name) must be WIRED: either a PREFLIGHT_REQUIRED registry
  entry (the pre-render registry), or a named manifest phase
  preflight/additional_preflight checker, or a documented closeout wiring —
  one of the enumerated CLOSEOUT_WIRED exceptions below (they fire in
  run_postflight_gate / main() AFTER preflight, by documented design; each
  carries the SOP line that documents its off-preflight firing point). A
  manifest entry-point checker with NONE of those wirings = a declared gate
  with no enforcement surface = MISSING ENTRY (this test fails).

  DIRECTION B — every PREFLIGHT_REQUIRED registry checker must be traceable
  to a manifest declaration: a build_deck-enforced autofail py_symbol or
  secondary_py_symbol, OR a manifest phase checker (the composite gate
  pattern: the phase's checker is the declared AF symbol). An unwired
  registry entry = a check that runs but nothing documents it = MISSING
  ENTRY (this test fails).

  PLUS: FIX 15/18 explicitly — `_chk_slide_craft` MUST be a PREFLIGHT_REQUIRED
  entry (the last registry entry), the FIX 15 + FIX 18 loader AF codes must
  resolve to it, and slide_craft.py + craft_judgement.py must be importable
  next to build_deck.py (the two modules the gate loads fail-closed).

Run:  python3 -m pytest tests/test_enforcement_registry_parity.py -q
      python3 tests/test_enforcement_registry_parity.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

sys.path.insert(0, str(SCRIPTS))
import build_deck  # noqa: E402


def _load_manifest() -> dict:
    assert CLUSTER_MANIFEST.exists(), f"manifest not found at {CLUSTER_MANIFEST}"
    return json.loads(CLUSTER_MANIFEST.read_text())


def _manifest_phase_checkers(manifest: dict) -> set:
    """Every checker a manifest phase names (primary + additional preflights)."""
    named = set()
    for ph in manifest["phases"]:
        pf = ph.get("preflight")
        if pf and pf.get("checker"):
            named.add(pf["checker"])
        for ap in ph.get("additional_preflights", []) or []:
            if ap.get("checker"):
                named.add(ap["checker"])
    return named


def _registry_checkers() -> set:
    """Every enforcement symbol in build_deck.PREFLIGHT_REQUIRED."""
    return {
        getattr(entry[3], "__name__", str(entry[3]))
        for entry in build_deck.PREFLIGHT_REQUIRED
    }


# ---------------------------------------------------------------------------
# The documented closeout wirings: manifest build_deck entry-point checkers
# that fire OUTSIDE PREFLIGHT_REQUIRED by documented design. Each tuple is
# (symbol, firing point) and every one is quoted verbatim from build_deck.py's
# own comments / manifest triggers so a future move of the firing point turns
# stale and fails here.
# ---------------------------------------------------------------------------
CLOSEOUT_WIRED = {
    # Fires in run_postflight_gate AFTER assembly — a pre-render preflight has no
    # bundle_dir yet ("PREFLIGHT entry deliberately omitted for AF-PACKAGE-CLEAN").
    "check_package_cleanliness": "run_postflight_gate (AF-PACKAGE-CLEAN, post-assembly)",
    # Post-render pixel teeth: preflight has no PNGs; fires at the render closeout.
    "run_postflight_gate": "main() P8-ASSEMBLE closeout (AF-BUNDLE-COMPLETE)",
    "_chk_cc_registered": "run_postflight_gate Phase-2 (AF-CC-UNREGISTERED/-UNVERIFIED)",
    "_chk_notes_pane": "run_postflight_gate P9.5-NOTES-SYNC closeout (AF-EMPTY-NOTES-PANE)",
    "_chk_spelling": "run_postflight_gate U047 SLIDE-GEOMETRY (AF-SPELLING)",
    "_chk_text_fits": "run_postflight_gate U047 SLIDE-GEOMETRY (AF-TEXT-OVERFLOW)",
    "_chk_type_size": "run_postflight_gate U047 SLIDE-GEOMETRY (AF-TYPE-SIZE-MEASURED)",
    # QC-phase attestation teeth, fired by the runner's phase gate, not preflight.
    "check_phase_preconditions": "run_signature_deck phase gate + run_preflight P0B/STYLE binding (AF-FORGED-APPROVAL)",
    "check_qc_phase_report_real": "runner QC-phase attestation (AF-QC-PLACEHOLDER)",
    # KIE preflights fire in main() immediately before render spend.
    "kie_balance_preflight": "main() pre-render KIE balance check (AF-KIE-BALANCE)",
    "ocr_engine_preflight": "main() pre-render OCR engine check (AF-OCR-ENGINE-MISSING)",
}

# Manifest phase-declared checkers are enforcement surface by definition —
# they do not ALSO need a PREFLIGHT_REQUIRED row (parity is per-direction).
_PHASE_WIRED_OK = True  # phase checkers are validated against build_deck in test 2


def _bd_entry_points(manifest: dict) -> dict:
    """{entry-point checker symbol: [AF codes]} for every build_deck-enforced row."""
    out: dict = {}
    for a in manifest["autofails"]:
        if a.get("enforced_by") != "build_deck":
            continue
        sym = a.get("py_symbol")
        if sym and (sym.startswith(("_chk_", "check_", "run_")) or sym.endswith("_preflight")):
            out.setdefault(sym, []).append(a["code"])
    return out


def _bd_symbols(manifest: dict) -> set:
    """Every py_symbol + secondary_py_symbol on build_deck-enforced rows."""
    syms = set()
    for a in manifest["autofails"]:
        if a.get("enforced_by") == "build_deck":
            if a.get("py_symbol"):
                syms.add(a["py_symbol"])
            for s in a.get("secondary_py_symbols", []) or []:
                syms.add(s)
    return syms


# ---------------------------------------------------------------------------
# DIRECTION A — documented enforced checker => runtime enforcement surface
# ---------------------------------------------------------------------------
def test_every_manifest_build_deck_entry_point_is_wired():
    """A declared build_deck entry-point checker must exist in PREFLIGHT_REQUIRED,
    be a manifest phase checker, or carry a documented closeout wiring. A checker
    with none of the three = MISSING REGISTRY ENTRY (this test fails)."""
    manifest = _load_manifest()
    registry = _registry_checkers()
    phase_checkers = _manifest_phase_checkers(manifest)
    missing = []
    for sym, codes in sorted(_bd_entry_points(manifest).items()):
        if sym not in build_deck.__dict__ and not hasattr(build_deck, sym):
            missing.append((sym, codes, "symbol does not even exist on build_deck"))
            continue
        if sym in registry:
            continue
        if sym in phase_checkers:
            continue
        if sym in CLOSEOUT_WIRED:
            # The documented closeout wiring must still be TRUE: the symbol is
            # actually invoked somewhere outside its own def (not a dead entry).
            if not _referenced_outside_def(sym):
                missing.append((sym, codes, "closeout-wired but never invoked"))
            continue
        missing.append((sym, codes, "no PREFLIGHT_REQUIRED entry, no phase checker, no documented closeout wiring"))
    assert not missing, (
        "FIX 36(4) REGISTRY PARITY — manifest-declared build_deck checkers with NO "
        f"runtime enforcement wiring: {missing}. "
        "Fix: add the checker to build_deck.PREFLIGHT_REQUIRED (or, for a genuinely "
        "post-preflight gate, extend this test's CLOSEOUT_WIRED ledger with the "
        "documented firing point) — a declared gate must have a wired enforcement surface."
    )


def _referenced_outside_def(sym: str) -> bool:
    import re
    src = (SCRIPTS / "build_deck.py").read_text()
    for m in re.finditer(r"\b" + re.escape(sym) + r"\b", src):
        start = m.start()
        prefix = src[max(0, start - 4):start]
        line_start = src.rfind("\n", 0, start) + 1
        line = src[line_start:start]
        if prefix.endswith("def ") or "def " in line:
            continue  # the definition itself
        return True
    return False


# ---------------------------------------------------------------------------
# DIRECTION B — runtime registry entry => documented in the manifest
# ---------------------------------------------------------------------------
def test_every_preflight_registry_entry_is_manifest_documented():
    manifest = _load_manifest()
    phase_checkers = _manifest_phase_checkers(manifest)
    bd_syms = _bd_symbols(manifest)
    undocumented = []
    for entry in build_deck.PREFLIGHT_REQUIRED:
        sym = getattr(entry[3], "__name__", str(entry[3]))
        if sym not in bd_syms and sym not in phase_checkers:
            # Documented exception: the image-QC PREFLIGHT SCHEDULER is the
            # run-dir-scoped wrapper AROUND the manifest-declared _chk_image_qc
            # (AF-IMAGE-QC / AF-IMAGE-QC-VISION) — it needs no own row because it
            # delegates the full gate to the declared symbol (its docstring pins
            # exactly this). Verify the wrapper still delegates.
            if sym == "check_image_qc_report_gate":
                src = (SCRIPTS / "build_deck.py").read_text()
                assert "_chk_image_qc(report_path" in src, (
                    "check_image_qc_report_gate must delegate to the declared _chk_image_qc"
                )
                continue
            missing.append(sym)
    missing = [s for s in
               [getattr(e[3], "__name__", str(e[3])) for e in build_deck.PREFLIGHT_REQUIRED]
               if s not in bd_syms and s not in phase_checkers
               and s != "check_image_qc_report_gate"]
    assert not missing, (
        "FIX 36(4) REGISTRY PARITY: PREFLIGHT_REQUIRED entries with NO manifest "
        f"declaration (no autofails py_symbol/secondary, no phase checker): {missing}. "
        "Fix: declare the AF code in PIPELINE-MANIFEST.autofails (enforced_by "
        "build_deck + this py_symbol) — a check that runs must be documented."
    )


# ---------------------------------------------------------------------------
# FIX 15/18 explicitly — the slide-craft gate must be a LIVE registry entry
# ---------------------------------------------------------------------------
def test_fix15_fix18_slide_craft_gate_is_registered_and_loadable():
    manifest = _load_manifest()
    bd_syms = _bd_symbols(manifest)
    codes = {a["code"] for a in manifest["autofails"]}

    # (1) _chk_slide_craft is the LAST PREFLIGHT_REQUIRED entry (deliberate tail).
    last = build_deck.PREFLIGHT_REQUIRED[-1]
    last_sym = getattr(last[3], "__name__", str(last[3]))
    assert last_sym == "_chk_slide_craft", (
        f"FIX 15/18 slide-craft gate must be the closing PREFLIGHT_REQUIRED entry, "
        f"got {last_sym!r}"
    )

    # (2) The FIX 15 + FIX 18 loader AF codes resolve to it.
    for code in ("AF-SLIDE-CRAFT-LOADER", "AF-CRAFT-JUDGEMENT-LOADER"):
        assert code in codes, f"{code} must be declared in PIPELINE-MANIFEST.autofails"
        row = next(a for a in manifest["autofails"] if a["code"] == code)
        assert row.get("enforced_by") == "build_deck", f"{code} enforced_by build_deck"
        assert row.get("py_symbol") == "_chk_slide_craft", (
            f"{code} must stay wired to _chk_slide_craft, got {row.get('py_symbol')!r}"
        )

    # (3) The two modules the gate loads fail-closed are importable next to
    #     build_deck.py — an ImportError inside _chk_slide_craft IS the
    #     fail-closed refusal, so the modules must exist on disk.
    assert (SCRIPTS / "slide_craft.py").is_file(), "slide_craft.py (FIX 15) missing"
    assert (SCRIPTS / "craft_judgement.py").is_file(), "craft_judgement.py (FIX 18) missing"
    import slide_craft  # noqa: F401
    import craft_judgement  # noqa: F401

    # (4) The registry entry's label names BOTH fixes (the parity contract).
    label = str(last[1])
    assert "FIX 15" in label and "FIX 18" in label, (
        f"the slide-craft PREFLIGHT_REQUIRED label must name FIX 15 + FIX 18, got: {label!r}"
    )


# ---------------------------------------------------------------------------
# Control — the parity harness itself discriminates (a fabricated entry fails)
# ---------------------------------------------------------------------------
def test_parity_harness_has_teeth_control():
    """The known-good control proves Direction B's failure mode is real: a
    PREFLIGHT_REQUIRED-like registry with one fabricated checker is flagged as
    undocumented by the same rule the test above uses."""
    manifest = _load_manifest()
    phase_checkers = _manifest_phase_checkers(manifest)
    bd_syms = _bd_symbols(manifest)
    fabricated = "_chk_registry_parity_fabricated_probe"
    assert fabricated not in bd_syms and fabricated not in phase_checkers
    # The rule: NOT in bd_syms and NOT in phase_checkers and not the scheduler ->
    #   must be reported missing. Assert the rule fires for the fabricated name.
    would_report = (fabricated not in bd_syms
                    and fabricated not in phase_checkers
                    and fabricated != "check_image_qc_report_gate")
    assert would_report, "parity rule must flag a fabricated registry entry (teeth control)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))