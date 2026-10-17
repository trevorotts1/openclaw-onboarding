#!/usr/bin/env python3
"""Propose Signature grade floors from a gold set (Skill 71, Item 8, as
redesigned by the Calibration Redesign, Rulings 1 and 2, 2026-10-14).

Trevor supplies accepted anchor images: calibration anchors and
validation for the documented look (the look itself is defined by the
governing documents, not by these images). The gold set is committed
under assets/brand/gold-set/ with a gold-set.json manifest. This script
runs the EXACT measurements of scripts/validate_image_grade.py over the
gold set (imported, never reimplemented, so the proposal can never
drift from the screen it calibrates) and proposes floors PER FAMILY and
PER POSTURE CLASS (the pre-redesign pooled brand-level floor is gone):

  - FULL class (per family): color floors (mean_saturation,
    colorfulness) = 5th percentile x 0.95 of that family's FULL
    anchors only. Minimum 4 FULL anchors; fewer is refused by name
    (a 5th percentile of a smaller set is effectively its minimum).
  - ADAPT class (per family): a two-sided band instead of a floor:
    saturation and colorfulness each get [5th pct x 0.95, 95th pct x
    1.05] of the ADAPT subset, plus a luma_std tonal floor (5th pct x
    0.95) - Guide section 13, check 1: ADAPT replaces hero color with an
    equally deliberate tonal or limited-palette authority. 4+ anchors:
    binding band. 1 to 3 anchors: the band is printed PROVISIONAL and
    the class is recorded uncalibrated (the validator WARNs for it).
    0 anchors: uncalibrated, nothing derived.
  - SUPPRESS class: no color floors or bands are ever computed (Guide
    section 13: SUPPRESS is N/A and must not be reintroduced merely to
    chase a higher score). SUPPRESS anchors still contribute luma_std
    and sharpness to their family's non-color floors.
  - Non-color floors (per family): luma_std and sharpness at 5th
    percentile x 0.95, pooled across ALL of the family's anchors
    (every posture class, including unrecorded postures).
  - Option B ceiling proposal (per family, Ruling 3): the protected-
    region saturation ceiling = 95th percentile x 1.05 of the family's
    FULL anchors' protected-region mean saturation. Printed as a
    proposal only; the metric is WARN-only, and remains WARN-only after
    a ceiling is approved and written into the brand file (owner ruling
    S71-OPTION-B, Resolution A, 2026-10-16).

Percentile method: linear interpolation between closest ranks (the
numpy 'linear' default), computed here with the standard library only.

Family span (Ruling 2): brand calibration requires per-family anchors
for EVERY family the brand uses. The used families are read from the
brand file's grade.families_used when declared, else from the gold
manifest's top-level families_used, else all three Router families.
A run that cannot derive a floor set for a used family REFUSES
(exit 2), naming each such family and its counts. There is NO
family-scoped calibration mode: a partial proposal table is printed
for diagnosis, but the run does not certify the families it derived
as a brand calibration. One recorded exception: a family whose
governing posture is not FULL may be declared in the manifest's
family_exceptions (Trevor's designation-time record); such a family
derives from its governing class instead of a FULL class.

Gold-set validity (Amendment 6, Part D, Items 8 and 9 delta): at least
one entry must be a definingly monochrome or restrained-style case (its
manifest entry's style_case says so, or its blend profile SUPPRESSes
hero_color_chroma). A saturation floor calibrated without such a case
is INVALID BY CONSTRUCTION: it would encode "correct monochrome work
is a failure" into the floor, so this script refuses (exit 2). Under
the redesign the restrained case lands in the ADAPT or SUPPRESS class
by construction, so it can never drag the FULL floors down.

Manifest entries must record active_family (one of photographic,
cinematic, visual-artist) and style_case; blend_profile records the
entry's posture class (keyed on hero_color_chroma). An entry with no
blend_profile is posture class UNRECORDED: it is excluded from every
color-floor computation, listed by name, and still contributes its
non-color measurements to its family. Postures are never assigned by
inspection here; an unrecorded posture is an honest gap, not a guess.

If --bad names a folder of known-bad images, each bad image is
measured and the table shows which derivable families' FULL floor sets
it would fail.

THIS SCRIPT PROPOSES ONLY. It never writes the brand file, or any
other file. Trevor approves or adjusts the proposed numbers; only then
does a builder write them into the brand file's grade block (nested
grade.floors, plus the photographic FULL floors mirrored to the legacy
flat keys for the production gate's transition) and record the
calibration date and gold-set manifest hash in the calibration record.

Usage:
  calibrate_grade.py --brand <brand.json> --gold <dir> [--bad <dir>]

Exit codes: 0 complete proposal printed for every used family,
2 unreadable input, invalid gold set, or a used family underivable.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_image_grade as vig  # noqa: E402  (the screen being calibrated)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

COLOR_METRICS = [
    ("mean_saturation", "min_mean_saturation"),
    ("colorfulness", "min_colorfulness"),
]
NONCOLOR_METRICS = [
    ("luma_std", "min_luma_std"),
    ("sharpness", "min_sharpness"),
]
MIN_CLASS_ANCHORS = 4  # below this a percentile is the subset minimum


def percentile(values, pct):
    """pct-th percentile by linear interpolation between closest ranks."""
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + frac * (ordered[high] - ordered[low])


def floor_of(values):
    """The standard floor derivation: 5th percentile x 0.95."""
    return percentile(values, 5) * 0.95


def posture_class_of(entry):
    """FULL, ADAPT, SUPPRESS, or UNRECORDED for a gold manifest entry.

    Keyed on the hero_color_chroma dimension of the entry's recorded
    blend profile, exactly as the validator resolves posture. No
    profile recorded: UNRECORDED (never guessed).
    """
    mode = vig.blend_profile_of(entry).get(vig.COLOR_DIMENSION)
    return mode if mode in ("FULL", "ADAPT", "SUPPRESS") else "UNRECORDED"


def family_of_entry(entry, name):
    """The entry's recorded active_family, refusing when invalid."""
    fam = entry.get("active_family")
    if not isinstance(fam, str) or fam.strip().lower() not in vig.FAMILIES:
        raise SystemExit(
            f"FAIL: gold-set entry {name}: active_family is required and "
            f"must be one of {', '.join(vig.FAMILIES)} (recorded: {fam!r}). "
            "Calibration is per family (Ruling 2); an anchor with no "
            "recorded family cannot be placed.")
    return fam.strip().lower()


def gold_entries(gold_dir):
    """(image path, manifest entry dict) pairs for the gold set.

    Manifest-listed when gold-set.json exists (entries keep their
    recorded active_family, style_case, and blend profile); otherwise
    every image file in the folder, with empty entries. Manifest
    entries are validated here: active_family and style_case are
    required (Redesign 1.2) and a refusal names the offending entry.
    Returns (pairs, has_manifest, manifest_data).
    """
    gold_dir = Path(gold_dir)
    manifest = gold_dir / "gold-set.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"FAIL: could not read gold-set manifest {manifest}: {exc}")
        entries = data.get("images") if isinstance(data, dict) else data
        if not isinstance(entries, list) or not entries:
            raise SystemExit(
                f"FAIL: gold-set manifest {manifest} lists no images; "
                "Trevor's gold anchor images are not in place yet (Item 8 "
                "is blocked on owner assets until they are).")
        pairs = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise SystemExit(f"FAIL: gold-set manifest entry is not an object: {entry!r}")
            name = entry.get("file")
            if not name:
                raise SystemExit(f"FAIL: gold-set manifest entry has no file: {entry!r}")
            family_of_entry(entry, name)
            if not str(entry.get("style_case") or "").strip():
                raise SystemExit(
                    f"FAIL: gold-set entry {name}: style_case is required "
                    "(name the case this anchor represents, e.g. "
                    "'full-color hero portrait' or 'monochrome restrained "
                    "case'). The case record is what the Amendment 6 "
                    "validity rule and the class audit read.")
            pairs.append((gold_dir / name, entry))
        return pairs, True, data if isinstance(data, dict) else {}
    return [(p, {}) for p in sorted(gold_dir.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES], False, {}


def is_restrained_case(entry):
    """True if a manifest entry records a definingly monochrome or
    restrained-style case (Amendment 6 gold-set validity rule)."""
    case = str(entry.get("style_case") or "").lower()
    if "monochrome" in case or "restrained" in case or "grayscale" in case \
            or "grey" in case or "pastel" in case:
        return True
    tags = entry.get("tags") or []
    if isinstance(tags, list):
        joined = " ".join(str(t).lower() for t in tags)
        if "monochrome" in joined or "restrained" in joined:
            return True
    profile = vig.blend_profile_of(entry)
    if profile.get(vig.COLOR_DIMENSION) == "SUPPRESS":
        return True
    return False


def measure_all(paths, label):
    rows = []
    for path in paths:
        try:
            m = vig.measure(path)
        except Exception as exc:
            print(f"FAIL: could not read {label} image {path}: {exc}")
            raise SystemExit(2)
        rows.append((path.name, m))
    return rows


def fmt(value):
    return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"


def used_families(brand_path, manifest_data):
    """The families the brand uses, for the span rule (Ruling 2).

    The brand file's grade.families_used declaration wins; then the
    gold manifest's top-level families_used; absent both, all three
    Router families. Unknown names are refused, not ignored.
    """
    try:
        brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"FAIL: could not read brand file {brand_path}: {exc}")
    declared = None
    grade = brand.get("grade") if isinstance(brand, dict) else None
    if isinstance(grade, dict) and isinstance(grade.get("families_used"), list):
        declared = grade["families_used"]
    elif isinstance(manifest_data.get("families_used"), list):
        declared = manifest_data["families_used"]
    if declared is None:
        return list(vig.FAMILIES), "default: all three Router families"
    out = []
    for fam in declared:
        key = str(fam).strip().lower()
        if key not in vig.FAMILIES:
            raise SystemExit(
                f"FAIL: families_used names an unknown family: {fam!r} "
                f"(known: {', '.join(vig.FAMILIES)})")
        if key not in out:
            out.append(key)
    if not out:
        raise SystemExit("FAIL: families_used is declared but empty.")
    return out, "declared"


def compute_floors(gold_pairs, measures):
    """Per-family, per-class floor derivation (Redesign Parts 1 and 2).

    gold_pairs: [(path, entry)]; measures: {filename: measures dict}.
    Returns {family: {
        "total": n, "classes": {posture: [names]},
        "full": {metric_key: floor}|None,
        "adapt": {"band": {...}, "provisional": bool}|None,
        "noncolor": {metric_key: floor}|None,
        "ceiling": proposed Option B ceiling|None,
    }} for every family in vig.FAMILIES.
    """
    out = {}
    for family in vig.FAMILIES:
        members = [(p, e) for p, e in gold_pairs
                   if str(e.get("active_family") or "").strip().lower() == family]
        classes = {}
        for posture in ("FULL", "ADAPT", "SUPPRESS", "UNRECORDED"):
            classes[posture] = [p.name for p, e in members
                                if posture_class_of(e) == posture]
        fam = {"total": len(members), "classes": classes,
               "full": None, "adapt": None, "noncolor": None, "ceiling": None}

        def values(names, metric_key):
            return [measures[n][metric_key] for n in names]

        full_names = classes["FULL"]
        if len(full_names) >= MIN_CLASS_ANCHORS:
            fam["full"] = {mk: floor_of(values(full_names, mk))
                           for mk, _gk in COLOR_METRICS}
            protected = [measures[n]["protected_sat"] for n in full_names
                         if measures[n]["protected_sat"] is not None]
            if protected:
                fam["ceiling"] = percentile(protected, 95) * 1.05
        adapt_names = classes["ADAPT"]
        if adapt_names:
            band = {}
            for mk, gk in COLOR_METRICS:
                band[f"min_{gk[4:]}"] = floor_of(values(adapt_names, mk))
                band[f"max_{gk[4:]}"] = percentile(values(adapt_names, mk), 95) * 1.05
            band["min_luma_std"] = floor_of(values(adapt_names, "luma_std"))
            fam["adapt"] = {"band": band,
                            "provisional": len(adapt_names) < MIN_CLASS_ANCHORS}
        all_names = [p.name for p, _e in members]
        if len(all_names) >= MIN_CLASS_ANCHORS:
            fam["noncolor"] = {mk: floor_of(values(all_names, mk))
                               for mk, _gk in NONCOLOR_METRICS}
        out[family] = fam
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Propose Signature grade floors from a gold set (Item 8, "
                    "Calibration Redesign). Prints a proposal only; never "
                    "writes the brand file.")
    parser.add_argument("--brand", type=Path, required=True,
                        help="brand file to read current thresholds from (read-only)")
    parser.add_argument("--gold", type=Path, required=True,
                        help="folder of Trevor-approved gold anchor images")
    parser.add_argument("--bad", type=Path, default=None,
                        help="optional folder of known-bad images to test the "
                             "proposed floors against")
    args = parser.parse_args()

    if vig.Image is None:
        print("FAIL: Pillow is required (pip install Pillow).")
        return 2
    if not args.gold.is_dir():
        print(f"FAIL: gold folder not found: {args.gold}")
        return 2

    # Read-only: current grade block, shown beside the proposal.
    try:
        grade = vig.load_grade(args.brand)
        current_plan = vig.floor_plan(grade)
    except SystemExit as exc:
        print(exc)
        return 2

    try:
        gold_pairs, has_manifest, manifest_data = gold_entries(args.gold)
    except SystemExit as exc:
        print(exc)
        return 2
    if not gold_pairs:
        print(f"FAIL: no gold images found in {args.gold}. Item 8 calibration "
              "is blocked on owner assets: Trevor supplies accepted anchor "
              "images (see assets/brand/gold-set/README.md).")
        return 2

    if not has_manifest:
        # Legacy folder mode: no families or postures are recorded, so
        # no per-family calibration can be derived or audited. Keep the
        # historical pooled measurement table as a diagnostic only.
        print("WARN: no gold-set.json manifest; families, postures, style "
              "span, and the monochrome/restrained case cannot be audited, "
              "and no per-family calibration can be derived from bare "
              "files. The pooled table below is a diagnostic, NOT a "
              "calibration proposal. Use the manifest format "
              "(assets/brand/gold-set/README.md).")
        gold_paths = [p for p, _e in gold_pairs]
        gold_rows = measure_all(gold_paths, "gold")
        print(f"\nGold set: {len(gold_rows)} image(s) from {args.gold}")
        for name, m in gold_rows:
            print(f"{name:<30} sat={m['mean_saturation']:.4f} "
                  f"luma_std={m['luma_std']:.2f} "
                  f"sharpness={m['sharpness']:.2f} "
                  f"colorfulness={m['colorfulness']:.2f}")
        print("\nPROPOSAL ONLY: nothing was written, and no calibration "
              "was derived (no manifest).")
        return 0

    # Gold-set validity (Amendment 6): unchanged in force.
    if not any(is_restrained_case(entry) for _p, entry in gold_pairs):
        print("FAIL: INVALID GOLD SET: no entry is a definingly monochrome "
              "or restrained-style case (record one via style_case or a "
              "blend profile SUPPRESSing hero_color_chroma). A saturation "
              "floor calibrated without such a case is invalid by "
              "construction: it would encode 'correct monochrome work is "
              "a failure' into the floor (Amendment 6, Part D).")
        return 2

    try:
        families_used, used_source = used_families(args.brand, manifest_data)
    except SystemExit as exc:
        print(exc)
        return 2
    exceptions = manifest_data.get("family_exceptions")
    if not isinstance(exceptions, dict):
        exceptions = {}

    gold_paths = [p for p, _e in gold_pairs]
    entry_by_name = {p.name: e for p, e in gold_pairs}
    gold_rows = measure_all(gold_paths, "gold")
    measures = {name: m for name, m in gold_rows}

    print(f"Gold set: {len(gold_rows)} image(s) from {args.gold}")
    header = (f"{'image':<30} {'sat':>8} {'luma_std':>9} {'sharpness':>11} "
              f"{'colorful':>9} {'family':<14} {'posture':<10} {'style_case':<18}")
    print(header)
    print("-" * len(header))
    for name, m in gold_rows:
        entry = entry_by_name.get(name, {})
        print(f"{name:<30} {m['mean_saturation']:>8.4f} {m['luma_std']:>9.2f} "
              f"{m['sharpness']:>11.2f} {m['colorfulness']:>9.2f} "
              f"{str(entry.get('active_family') or '-'):<14} "
              f"{posture_class_of(entry):<10} "
              f"{str(entry.get('style_case') or '-'):<18}")
    cases = sorted({str(e.get('style_case') or '-') for _p, e in gold_pairs})
    print(f"Gold-set style span (recorded): {', '.join(cases)}")
    unrecorded = [p.name for p, e in gold_pairs
                  if posture_class_of(e) == "UNRECORDED"]
    if unrecorded:
        print("UNRECORDED posture (excluded from every color-floor "
              "computation; non-color measurements still count toward "
              f"their family): {', '.join(unrecorded)}")

    computed = compute_floors(gold_pairs, measures)

    print("\nProposed floors (per family, per posture class; color "
          "floors and non-color floors at the 5th percentile x 0.95, "
          "ADAPT bands two-sided):")
    print(f"Families the brand uses ({used_source}): "
          f"{', '.join(families_used)}")
    problems = []
    for family in vig.FAMILIES:
        fam = computed[family]
        counts = fam["classes"]
        print(f"\nFamily: {family} "
              f"(anchors: {fam['total']}; FULL {len(counts['FULL'])}, "
              f"ADAPT {len(counts['ADAPT'])}, SUPPRESS {len(counts['SUPPRESS'])}, "
              f"UNRECORDED {len(counts['UNRECORDED'])})")
        cur = current_plan.get(family, {})
        if fam["full"] is not None:
            for mk, gk in COLOR_METRICS:
                cur_v = (cur.get("full") or {}).get(gk)
                print(f"  FULL grade.floors.{family}.full.{gk:<22} "
                      f"current {'null' if cur_v is None else fmt(cur_v):>10} "
                      f"proposed {fmt(fam['full'][mk]):>10} "
                      f"(n={len(counts['FULL'])})")
            if fam["ceiling"] is not None:
                cur_c = vig.protected_ceiling(grade, current_plan, family)
                print(f"  FULL grade.floors.{family}.full.max_protected_saturation "
                      f"current {'null' if cur_c is None else fmt(cur_c):>10} "
                      f"proposed {fmt(fam['ceiling']):>10} "
                      "(Option B ceiling, p95 x 1.05 of FULL anchors)")
        if fam["adapt"] is not None:
            band = fam["adapt"]["band"]
            state = ("PROVISIONAL (1 to 3 anchors; recorded uncalibrated, "
                     "validator WARNs)" if fam["adapt"]["provisional"]
                     else "binding")
            print(f"  ADAPT band [{state}] (n={len(counts['ADAPT'])}): "
                  f"saturation [{band['min_mean_saturation']:.4f}, "
                  f"{band['max_mean_saturation']:.4f}], colorfulness "
                  f"[{band['min_colorfulness']:.2f}, "
                  f"{band['max_colorfulness']:.2f}], luma_std tonal floor "
                  f"{band['min_luma_std']:.2f}")
        if fam["noncolor"] is not None:
            for mk, gk in NONCOLOR_METRICS:
                cur_v = (cur.get("noncolor") or {}).get(gk)
                print(f"  NONCOLOR grade.floors.{family}.noncolor.{gk:<18} "
                      f"current {'null' if cur_v is None else fmt(cur_v):>10} "
                      f"proposed {fmt(fam['noncolor'][mk]):>10} "
                      f"(pooled across postures, n={fam['total']})")

        if family not in families_used:
            continue
        # Span rule (Ruling 2): this used family must derive a floor set.
        if fam["total"] == 0:
            problems.append(
                f"family {family}: 0 gold anchors recorded")
        elif fam["total"] < MIN_CLASS_ANCHORS:
            problems.append(
                f"family {family}: {fam['total']} gold anchor(s); at least "
                f"{MIN_CLASS_ANCHORS} are required to derive any floor")
        elif fam["full"] is None and family not in exceptions:
            n_full = len(counts["FULL"])
            if 0 < n_full < MIN_CLASS_ANCHORS:
                problems.append(
                    f"POSTURE CLASS TOO SMALL: class FULL in family "
                    f"{family} has {n_full} recorded anchor(s); at least "
                    f"{MIN_CLASS_ANCHORS} are required to derive a floor. "
                    "Add anchors for this class, or record the class "
                    "uncalibrated at designation. No floor is derived "
                    "from fewer.")
            else:
                problems.append(
                    f"family {family}: no derivable FULL class "
                    f"({n_full} FULL anchor(s) recorded); record a "
                    "family_exceptions entry at designation if this "
                    "family's governing posture is not FULL")
        elif fam["full"] is None and family in exceptions:
            governing_ok = (fam["adapt"] is not None
                            and not fam["adapt"]["provisional"]) \
                or fam["noncolor"] is not None
            if not governing_ok:
                problems.append(
                    f"family {family}: family_exceptions recorded "
                    f"({exceptions[family]!r}) but its governing class "
                    "derives nothing binding (ADAPT band provisional or "
                    "absent, non-color floors underivable)")

    if problems:
        counts_text = "; ".join(
            f"{f} {computed[f]['total']} (FULL "
            f"{len(computed[f]['classes']['FULL'])})"
            for f in families_used)
        print("\nFAIL: FAMILY SPAN: brand-wide calibration requires "
              "per-family gold anchors, including a derivable FULL "
              "class, in each family the brand uses "
              f"({', '.join(families_used)}). This set records: "
              f"{counts_text}. There is no family-scoped calibration "
              "mode (Ruling 2): supply anchors for the underivable "
              "families. (Amendment 6, Part D; Calibration Redesign "
              "Part 2 as amended.)")
        for problem in problems:
            print(f"FAIL: {problem}")
        print("\nPROPOSAL ONLY: nothing was written. The per-family "
              "tables above are diagnostic until every used family "
              "derives.")
        return 2

    if args.bad:
        if not Path(args.bad).is_dir():
            print(f"FAIL: bad folder not found: {args.bad}")
            return 2
        bad_paths = sorted(p for p in Path(args.bad).iterdir()
                           if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
        bad_rows = measure_all(bad_paths, "bad")
        print(f"\nBad set: {len(bad_rows)} image(s) from {args.bad}")
        derivable = [f for f in families_used if computed[f]["full"] is not None]
        for name, m in bad_rows:
            verdicts = []
            for family in derivable:
                fam = computed[family]
                failed = [gk for mk, gk in COLOR_METRICS
                          if m[mk] < fam["full"][mk]]
                if fam["noncolor"] is not None:
                    failed += [gk for mk, gk in NONCOLOR_METRICS
                               if m[mk] < fam["noncolor"][mk]]
                verdicts.append(f"{family}: "
                                + (("would FAIL: " + ", ".join(failed))
                                   if failed else "would PASS"))
            print(f"{name:<36} sat={m['mean_saturation']:.4f} "
                  f"luma_std={m['luma_std']:.2f} "
                  f"sharpness={m['sharpness']:.2f} "
                  f"colorfulness={m['colorfulness']:.2f}  -> "
                  + ("; ".join(verdicts) if verdicts
                     else "no derivable FULL floor set to test against"))

    print("\nPROPOSAL ONLY: nothing was written. Trevor approves or "
          "adjusts these floors; the approved numbers are then written "
          "into the brand file's grade block by hand (nested "
          "grade.floors per family and posture class, with the "
          "photographic FULL floors mirrored to the legacy flat keys), "
          "with the calibration date and the gold-set manifest hash "
          "recorded per brand.schema.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
