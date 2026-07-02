#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_broken.py — the fail-closed proof for the golden-lumen-rise sample.

Takes the PASSING golden BRAND run and applies FIVE single-defect mutations, each
crafted to trip a DISTINCT AF-AV-* auto-fail across the three fail-closed provers,
and asserts every one is REJECTED (never silently served):

  1  missing-generator        drop the 16-brand-bio artifact      -> AF-AV-STAGE-MISSING   (aa_build_check)
  2  out-of-band-copy         ad-set-7 category drifts to "2"     -> AF-AV-ADSET-CAT        (aa_build_check)
  3  image-prompt-too-short   landing image prompts under band    -> AF-AV-IMG-BAND         (aa_build_check)
  4  book-version-not-routed  version=book, no Book skill present  -> AF-AV-BOOK-SKILL-MISSING (aa_intake_gate)
  5  missing-provenance       artifact edited after its receipt    -> AF-AV-PROVENANCE       (aa_delivery_gate)

Read-only w.r.t. the checked-in golden run (mutations are applied to in-memory
copies). Writes ONLY the REJECTION-RESULTS.json path it is told to (default: next
to this file). stdlib only.

Usage:
  python3 make_broken.py                 # verify all 5 reject; refresh REJECTION-RESULTS.json here
  python3 make_broken.py --results <p>   # write the results ledger to <p> (read-only tree; used by verify.sh)
  python3 make_broken.py --emit          # (re)write the two standalone input fixtures next to this file

Exit 0 = all five rejected with their expected code; 1 = a variant did NOT fail closed.
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent                       # examples/golden-lumen-rise/
SKILL_ROOT = GOLDEN.parents[1]             # 52-avatar-intelligence/
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import aa_build_check as build             # noqa: E402
import aa_intake_gate as intake            # noqa: E402
import aa_delivery_gate as delivery        # noqa: E402

MANIFEST = json.loads((SKILL_ROOT / "AA-PIPELINE-MANIFEST.json").read_text(encoding="utf-8"))


def _load_golden_build_state() -> Dict[str, Any]:
    """The passing content-prover state, loaded from the checked-in run-dir."""
    return build.load_run(str(GOLDEN / "run"))


def _load_golden_delivery_state() -> Dict[str, Any]:
    """Reconstructed from the run-dir artifacts (receipt sha256 == artifact bytes),
    so no large duplicate state file is checked into the fleet repo."""
    import hashlib
    art = {p.stem: p.read_text(encoding="utf-8") for p in (GOLDEN / "run" / "artifacts").glob("*.md")}
    return {"artifacts": art,
            "receipts": {sid: {"sha256": hashlib.sha256(t.encode("utf-8")).hexdigest(), "attested_by": "foreman"}
                         for sid, t in art.items()},
            "content_pass": True, "qc_score": 9.2}


def _book_intake() -> Dict[str, Any]:
    """A well-formed BOOK-version intake (shared answers + book delta, zero brand
    fields) — valid EXCEPT there is no Book skill (53) on the box to route to."""
    return {
        "version": "book", "first_name": "Amara", "last_name": "Vale",
        "ideal_avatar": "women founders in service businesses who feel invisible",
        "niche": "visibility and authority coaching for women founders",
        "primary_goal": "convert proven competence into a fully-booked, visible practice",
        "tone_style_1": "the cadence of classic abolitionist oratory", "tone_style_2": "N/A",
        "book_stories": "The season I stopped hiding my expertise and let the work be seen.",
    }


# ---------------------------------------------------------------------------
# the five variants
# ---------------------------------------------------------------------------
def v1_missing_generator() -> Tuple[int, List[str], str]:
    st = copy.deepcopy(_load_golden_build_state())
    st["artifacts"]["16-brand-bio"] = ""                 # generator produced nothing
    st["receipts"] = [r for r in st["receipts"] if r != "16-brand-bio"]
    vio, _ = build.verify(MANIFEST, st)
    return (2 if vio else 0), sorted({c for c, _ in vio}), _fmt(vio)


def v2_out_of_band_copy() -> Tuple[int, List[str], str]:
    st = copy.deepcopy(_load_golden_build_state())
    st["artifacts"]["28-ad-set-7"] = st["artifacts"]["28-ad-set-7"].replace("category 5", "category 2")
    vio, _ = build.verify(MANIFEST, st)
    return (2 if vio else 0), sorted({c for c, _ in vio}), _fmt(vio)


def v3_image_prompt_too_short() -> Tuple[int, List[str], str]:
    st = copy.deepcopy(_load_golden_build_state())
    st["artifacts"]["40-landing-image-prompts"] = "# Landing Page Image Prompts\n\nOne short prompt only.\n"
    vio, _ = build.verify(MANIFEST, st)
    return (2 if vio else 0), sorted({c for c, _ in vio}), _fmt(vio)


def v4_book_not_routed() -> Tuple[int, List[str], str]:
    vio, _ = intake.verify(_book_intake(), book_skill_present=False)  # no Book skill on box
    return (2 if vio else 0), sorted({c for c, _ in vio}), _fmt(vio)


def v5_missing_provenance() -> Tuple[int, List[str], str]:
    st = copy.deepcopy(_load_golden_delivery_state())
    # edit the artifact bytes AFTER the receipt sha256 was recorded (tamper)
    st["artifacts"]["16-brand-bio"] = st["artifacts"]["16-brand-bio"] + "\nSECRETLY EDITED after attestation.\n"
    vio, _, cert = delivery.verify(MANIFEST, st)
    out = _fmt(vio) + ("" if not cert else "  [!] certificate unexpectedly issued")
    return (2 if vio else 0), sorted({c for c, _ in vio}), out


def _fmt(vio: List[Tuple[str, str]]) -> str:
    return "\n".join(f"VIOLATION [{c}] {m}" for c, m in vio) if vio else "(no violation)"


VARIANTS = [
    ("01_missing_generator", "AF-AV-STAGE-MISSING", "aa_build_check.py", v1_missing_generator),
    ("02_out_of_band_copy", "AF-AV-ADSET-CAT", "aa_build_check.py", v2_out_of_band_copy),
    ("03_image_prompt_too_short", "AF-AV-IMG-BAND", "aa_build_check.py", v3_image_prompt_too_short),
    ("04_book_version_not_routed", "AF-AV-BOOK-SKILL-MISSING", "aa_intake_gate.py", v4_book_not_routed),
    ("05_missing_provenance", "AF-AV-PROVENANCE", "aa_delivery_gate.py", v5_missing_provenance),
]


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed proof for the golden Avatar-Alchemist sample.")
    ap.add_argument("--results", help="path to write REJECTION-RESULTS.json (default: alongside this script)")
    ap.add_argument("--emit", action="store_true", help="(re)write the standalone input fixtures next to this script")
    args = ap.parse_args(argv)

    if args.emit:
        # small standalone browsable fixture for variant 4; variants 1-3 & 5 are
        # single-line mutations of the golden run applied in-memory (see above), so
        # we do NOT check a 360 KB tampered-state copy into the fleet repo.
        (HERE / "book_intake.json").write_text(json.dumps(_book_intake(), indent=2) + "\n", encoding="utf-8")
        print("emitted: book_intake.json")

    results: Dict[str, Any] = {}
    ok = True
    print("== golden-lumen-rise :: broken-variant fail-closed proof ==")
    for name, expected, prover, fn in VARIANTS:
        rc, codes, out = fn()
        rejected = rc != 0 and expected in codes
        results[name] = {"prover": prover, "expected_code": expected, "rc": rc,
                         "rejected": bool(rejected), "got_codes": codes, "out": out}
        if rejected:
            print(f"  [REJECTED] {name:<28} {prover:<20} -> {expected} (rc={rc})")
        else:
            ok = False
            print(f"  [LEAK!]    {name:<28} {prover:<20} expected {expected}, got {codes} (rc={rc})")

    out_path = Path(args.results) if args.results else (HERE / "REJECTION-RESULTS.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {out_path}")
    print("RESULT:", "PASS — all 5 variants fail closed (exit 0)" if ok else "FAIL — a variant leaked (exit 1)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
