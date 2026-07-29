#!/usr/bin/env python3
"""
test_autofail_registry.py — standing check for U049 (retire AF-NO-VISION-QC).

AF-NO-VISION-QC was declared in PIPELINE-MANIFEST.json with `enforced_by:
"closeout_gate"` and `py_symbol: null`. No `closeout_gate` script exists
anywhere in this repository, and its detection input
(`working/qc/vision_qc_log.json`) is written and read by nothing. It was
retired, not implemented — its condition was already covered twice over,
deterministically, by `AF-IMAGE-QC` (no image-QC pass at all) and
`AF-IMAGE-QC-VISION` (a pixel-blind pass), both `enforced_by: "build_deck"`
with resolving `py_symbol`s.

This module pins six invariants so the retirement cannot silently regress:

  1. AF-NO-VISION-QC is absent from PIPELINE-MANIFEST.autofails.
  2. AF-NO-VISION-QC is absent from the Section-5 table in BOTH the
     canonical ruleset and the role-library mirror (the file a deployed
     client box actually parses — see sync_check.py's `_first_existing`).
  3. Its two successors, AF-IMAGE-QC and AF-IMAGE-QC-VISION, are still
     registered, still `enforced_by: "build_deck"`, and their `py_symbol`s
     still resolve on the imported `build_deck` module.
  4. The BEHAVIOUR, not just the registry: a run dir with a real render and
     no report fires AF-IMAGE-QC; the same dir with a self-typed report
     fires AF-IMAGE-QC-VISION; the same dir with a declared vision engine
     and a per-slide observation passes clean. This is the test that would
     have caught a "successor removed along with the retired code" defect.
  5. The A3 blind-spot invariant that made AF-NO-VISION-QC possible in the
     first place: every row `enforced_by == "build_deck"` has a resolving
     `py_symbol`, and the set of rows with `py_symbol is None` equals the
     set of rows with `enforced_by != "build_deck"`. Printed with its
     denominator, not asserted from memory.
  6. `manifest_version` is an integer greater than 25 (it must have been
     bumped by this retirement, whatever else has landed since).

Run:  python3 -m pytest test_autofail_registry.py -q
      python3 test_autofail_registry.py   (manual run, same assertions)
"""
import importlib.util
import json
import random
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CLUSTER_MANIFEST = (
    HERE.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)
CANONICAL_RULESET = (
    HERE.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "MASTER-QC-AUTOFAIL-RULESET.md"
)
MIRROR_RULESET = HERE.parent / "sops" / "SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md"

sys.path.insert(0, str(HERE))
import build_deck  # noqa: E402


def _load_manifest() -> dict:
    assert CLUSTER_MANIFEST.exists(), f"manifest not found at {CLUSTER_MANIFEST}"
    return json.loads(CLUSTER_MANIFEST.read_text())


def _load_sync_check():
    """Import sync_check.py fresh each time so mutating MASTER_RULESET on one
    import never leaks into another test."""
    spec = importlib.util.spec_from_file_location(
        "sync_check_u049", str(HERE / "sync_check.py")
    )
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    return sc


# ---------------------------------------------------------------------------
# 1. AF-NO-VISION-QC absent from PIPELINE-MANIFEST.autofails.
# ---------------------------------------------------------------------------
def test_af_no_vision_qc_absent_from_manifest():
    manifest = _load_manifest()
    codes = {a["code"] for a in manifest["autofails"]}
    assert "AF-NO-VISION-QC" not in codes, (
        "AF-NO-VISION-QC must be RETIRED (absent) from PIPELINE-MANIFEST.autofails; "
        f"found it among {len(codes)} registered codes"
    )


# ---------------------------------------------------------------------------
# 2. AF-NO-VISION-QC absent from BOTH Section-5 tables — canonical AND mirror.
#    This is the test that would have caught the client-box drift: a box has
#    no universal-sops tree, so it parses the mirror, not the canonical file.
# ---------------------------------------------------------------------------
def test_af_no_vision_qc_absent_from_both_section5_tables():
    sc = _load_sync_check()
    assert CANONICAL_RULESET.exists(), f"canonical ruleset not found at {CANONICAL_RULESET}"
    sc.MASTER_RULESET = CANONICAL_RULESET
    canonical_codes = sc.parse_master_ruleset_section5()
    assert "AF-NO-VISION-QC" not in canonical_codes, (
        "AF-NO-VISION-QC still present in the CANONICAL Section-5 table "
        f"({len(canonical_codes)} codes)"
    )

    assert MIRROR_RULESET.exists(), f"role-library mirror not found at {MIRROR_RULESET}"
    sc.MASTER_RULESET = MIRROR_RULESET
    mirror_codes = sc.parse_master_ruleset_section5()
    assert "AF-NO-VISION-QC" not in mirror_codes, (
        "AF-NO-VISION-QC still present in the MIRROR Section-5 table "
        f"({len(mirror_codes)} codes) — every deployed client box parses this file, "
        "not the canonical one, and would still report the retired code"
    )


# ---------------------------------------------------------------------------
# 3. The successors are still registered, build_deck-enforced, and resolve.
#    A retirement that also removed the successor is the failure mode this
#    test exists for.
# ---------------------------------------------------------------------------
def test_successors_still_registered_and_resolve():
    manifest = _load_manifest()
    by_code = {a["code"]: a for a in manifest["autofails"]}

    for code in ("AF-IMAGE-QC", "AF-IMAGE-QC-VISION"):
        assert code in by_code, f"{code} must remain registered in PIPELINE-MANIFEST.autofails"
        row = by_code[code]
        assert row.get("enforced_by") == "build_deck", (
            f"{code}.enforced_by is {row.get('enforced_by')!r}, expected 'build_deck'"
        )
        sym = row.get("py_symbol")
        assert sym, f"{code} must carry a non-null py_symbol"
        assert hasattr(build_deck, sym), (
            f"{code}'s py_symbol {sym!r} does not resolve on the imported build_deck module"
        )


# ---------------------------------------------------------------------------
# 4. THE BEHAVIOUR, not the registry. Both halves of AF-NO-VISION-QC's old
#    condition — "the pass never happened" and "the pass was pixel-blind" —
#    are proven live against the real checker functions.
# ---------------------------------------------------------------------------
def _make_run_dir_with_render() -> Path:
    d = Path(tempfile.mkdtemp(prefix="u049_autofail_registry_"))
    (d / "renders").mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow is not installed — cannot synthesize a render for this test")
    im = Image.new("RGB", (2048, 1152))
    px = im.load()
    rnd = random.Random(3)
    for y in range(0, 1152, 2):
        for x in range(0, 2048, 2):
            px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
    im.save(d / "renders" / "slide-01.png")
    return d


def test_no_report_fires_af_image_qc():
    # [A] genuinely pre-render (no renders, no report) -> defer, not a fail.
    empty_dir = Path(tempfile.mkdtemp(prefix="u049_autofail_registry_empty_"))
    pre_render = build_deck.check_image_qc_report_gate(empty_dir)
    assert pre_render == "", (
        f"a run dir with no renders and no report must DEFER (''), got: {pre_render!r}"
    )

    # [B] a render exists, no report -> AF-IMAGE-QC must fire ("the pass never happened").
    run_dir = _make_run_dir_with_render()
    rendered_bytes = (run_dir / "renders" / "slide-01.png").stat().st_size
    assert rendered_bytes > 51_200, "synthetic render must clear the placeholder-bake floor"
    result = build_deck.check_image_qc_report_gate(run_dir)
    assert result, "a rendered deck with NO image-QC report must FAIL, but the gate passed"
    assert "AF-IMAGE-QC" in result, f"expected AF-IMAGE-QC in the failure, got: {result!r}"


def test_self_typed_report_fires_af_image_qc_vision():
    # [C] a report exists but is pixel-blind (no vision engine, no per-slide
    # observation) -> AF-IMAGE-QC-VISION must fire ("the pass was pixel-blind").
    run_dir = _make_run_dir_with_render()
    qc_dir = run_dir / "working" / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    (qc_dir / "image_qc_report.json").write_text(
        json.dumps({"score": 9.4, "verdict": "pass"})
    )
    result = build_deck.check_image_qc_vision(run_dir)
    assert result, (
        "a self-typed report with no declared vision engine and no per-slide "
        "observation must FAIL, but the gate passed"
    )
    assert "AF-IMAGE-QC-VISION" in result, (
        f"expected AF-IMAGE-QC-VISION in the failure, got: {result!r}"
    )


def test_real_vision_report_passes():
    # [D] a report with a declared vision engine plus a per-slide observation
    # -> PASS. A successor that rejects a legitimate report is a gate that
    # fails good work and would be switched off; this pins the honest floor.
    run_dir = _make_run_dir_with_render()
    qc_dir = run_dir / "working" / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    (qc_dir / "image_qc_report.json").write_text(json.dumps({
        "vision_model": "a-multimodal-model",
        "slides": [{"index": 1, "observed_text": "REAL REVENUE GROWTH"}],
    }))
    result = build_deck.check_image_qc_vision(run_dir)
    assert result == "", (
        f"a report with a declared vision engine and a per-slide observation "
        f"must PASS (''), got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 5. THE A3 BLIND-SPOT INVARIANT — measured, not assumed. This is the schema
#    fact that let AF-NO-VISION-QC (and 63 other codes) go unpoliced: a row
#    attributed to anything other than "build_deck" may carry py_symbol: null
#    forever, and sync_check's A3 check never looks at it.
# ---------------------------------------------------------------------------
def test_a3_blind_spot_invariant_with_denominator():
    manifest = _load_manifest()
    autofails = manifest["autofails"]
    total = len(autofails)

    null_symbol_codes = {a["code"] for a in autofails if a.get("py_symbol") is None}
    not_build_deck_codes = {a["code"] for a in autofails if a.get("enforced_by") != "build_deck"}

    print(
        f"A3 blind-spot invariant: py_symbol-null={len(null_symbol_codes)} / "
        f"not-build_deck={len(not_build_deck_codes)} / total={total}"
    )

    assert null_symbol_codes == not_build_deck_codes, (
        "{py_symbol is null} must equal {enforced_by != 'build_deck'} — "
        f"null-only: {sorted(null_symbol_codes - not_build_deck_codes)}, "
        f"not-build-deck-only: {sorted(not_build_deck_codes - null_symbol_codes)}"
    )

    build_deck_rows = [a for a in autofails if a.get("enforced_by") == "build_deck"]
    for row in build_deck_rows:
        sym = row.get("py_symbol")
        assert sym, f"{row['code']} is enforced_by build_deck but has no py_symbol"
        assert hasattr(build_deck, sym), (
            f"{row['code']}'s py_symbol {sym!r} does not resolve on build_deck"
        )


# ---------------------------------------------------------------------------
# 6. manifest_version was bumped by this retirement.
# ---------------------------------------------------------------------------
def test_manifest_version_bumped():
    manifest = _load_manifest()
    version = manifest["manifest_version"]
    assert isinstance(version, int), f"manifest_version must be an int, got {type(version)}"
    assert version > 25, (
        f"manifest_version is {version}; this retirement (and U047/U009 before it) "
        "must have bumped it past the slice's baseline of 25"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
