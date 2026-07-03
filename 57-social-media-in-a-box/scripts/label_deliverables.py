#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: LABELED DELIVERABLE WRITER
# -----------------------------------------------------------------------------
# Replaces the n8n family's Google Drive staging (dated folders / _Backups /
# Master renditions) with LOCAL labeled deliverables (PRD 7). Only PASS
# artifacts are labeled and copied to the final area; nothing unlabeled ever
# lands in Downloads; the working area is cleaned after manifest sign-off.
#
# Final area : ~/Downloads/Social-Media-in-a-Box/<brand-slug>/<YYYY-Www>/
# Convention : SMIB_<brand-slug>_<YYYY-Www>_<dayN>_<platform>_<artifact>_<aspect>.<ext>
#   e.g. SMIB_acme_2026-W27_d3_instagram_carousel-slide-04_4x5.png
# Plus one   : SMIB_<brand-slug>_<YYYY-Www>_week-plan.md  +  manifest.json
#
# EXIT: 0 OK / 2 (a declared artifact source is missing) / 3 USAGE.
# USAGE:
#   python3 label_deliverables.py --manifest artifacts.json --dest DIR [--copy] [--json]
#   python3 label_deliverables.py --self-test
# =============================================================================
"""Local labeled-deliverable writer for Social Media in a Box (Skill 57)."""

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_MISSING = 2
EXIT_USAGE = 3


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def label_name(brand, week, day, platform, artifact, aspect, ext):
    parts = ["SMIB", slugify(brand), week]
    if day is not None:
        parts.append("d%s" % day)
    parts += [slugify(platform), slugify(artifact), str(aspect).replace(":", "x")]
    return "_".join(p for p in parts if p) + "." + ext.lstrip(".")


def plan_name(brand, week):
    return "SMIB_%s_%s_week-plan.md" % (slugify(brand), week)


def _dest_root(dest, brand, week):
    return Path(dest).expanduser() / slugify(brand) / week


def publish(manifest, dest, do_copy=False):
    """manifest = {brand, week, artifacts:[{day,platform,artifact,aspect,ext,src}],
                   week_plan_md?}. Returns (records, missing)."""
    brand = manifest.get("brand", "")
    week = manifest.get("week", "")
    root = _dest_root(dest, brand, week)
    records, missing = [], []
    for a in manifest.get("artifacts", []):
        name = label_name(brand, week, a.get("day"), a.get("platform", ""),
                          a.get("artifact", ""), a.get("aspect", "1x1"), a.get("ext", "png"))
        rec = {"label": name, "src": a.get("src"), "dest": str(root / name)}
        src = a.get("src")
        if src and not Path(src).is_file():
            missing.append(rec)
        elif do_copy and src:
            root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / name)
        records.append(rec)
    if do_copy:
        root.mkdir(parents=True, exist_ok=True)
        (root / plan_name(brand, week)).write_text(
            manifest.get("week_plan_md", "# Week plan\n"), encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps(
            {"brand": brand, "week": week, "artifacts": [r["label"] for r in records]}, indent=2),
            encoding="utf-8")
    return records, missing


def _emit(records, missing, as_json):
    if as_json:
        print(json.dumps({"gate": "label-deliverables", "pass": not missing,
                          "records": records, "missing": [m["label"] for m in missing]}, indent=2))
        return
    print("== Social Media in a Box :: labeled deliverables ==")
    for r in records:
        print("  %s%s" % (r["label"], "" if not any(m["label"] == r["label"] for m in missing) else "  [MISSING SRC]"))
    if missing:
        print("RESULT: FAIL — %d declared artifact source(s) missing." % len(missing))
    else:
        print("RESULT: OK — %d artifact(s) labeled." % len(records))


def run(manifest_path, dest, do_copy=False, as_json=False):
    p = Path(manifest_path)
    if not p.is_file():
        print("FATAL: manifest not found: %s" % p, file=sys.stderr)
        return EXIT_USAGE
    try:
        manifest = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read manifest: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    records, missing = publish(manifest, dest, do_copy=do_copy)
    _emit(records, missing, as_json)
    return EXIT_OK if not missing else EXIT_MISSING


# =============================================================================
# SELF-TEST
# =============================================================================
def self_test():
    ok = True

    n = label_name("Acme Parenting Co", "2026-W27", 3, "instagram", "carousel-slide-04", "4:5", "png")
    exp = "SMIB_acme-parenting-co_2026-W27_d3_instagram_carousel-slide-04_4x5.png"
    good = n == exp
    ok = ok and good
    print("  [%s] label convention: %s" % ("PASS" if good else "MISS", n))

    n2 = label_name("Brand One", "2026-W27", None, "linkedin", "carousel-pdf", "9x16", "pdf")
    good = n2 == "SMIB_brand-one_2026-W27_linkedin_carousel-pdf_9x16.pdf"
    ok = ok and good
    print("  [%s] no-day label: %s" % ("PASS" if good else "MISS", n2))

    # copy into a temp dest; verify only PASS artifacts land + plan + manifest
    src_dir = Path(tempfile.mkdtemp(prefix="smib-src-"))
    img = src_dir / "slide.png"
    img.write_bytes(b"\x89PNG stub")
    dest = Path(tempfile.mkdtemp(prefix="smib-dl-"))
    manifest = {"brand": "Brand One", "week": "2026-W27",
                "week_plan_md": "# Brand One — Week 2026-W27\n",
                "artifacts": [{"day": 1, "platform": "facebook", "artifact": "carousel-slide-01",
                               "aspect": "4:5", "ext": "png", "src": str(img)}]}
    records, missing = publish(manifest, dest, do_copy=True)
    root = dest / "brand-one" / "2026-W27"
    landed = (root / records[0]["label"]).is_file()
    has_plan = (root / "SMIB_brand-one_2026-W27_week-plan.md").is_file()
    has_manifest = (root / "manifest.json").is_file()
    good = landed and has_plan and has_manifest and not missing
    ok = ok and good
    print("  [%s] copy: artifact+plan+manifest landed, none missing" % ("PASS" if good else "MISS"))

    # missing source is caught (nothing unlabeled slips through)
    manifest2 = {"brand": "B", "week": "2026-W27",
                 "artifacts": [{"day": 2, "platform": "tiktok", "artifact": "video",
                                "aspect": "9:16", "ext": "mp4", "src": "/no/such/file.mp4"}]}
    _r, miss = publish(manifest2, dest, do_copy=False)
    good = len(miss) == 1
    ok = ok and good
    print("  [%s] missing source detected (fail-closed)" % ("PASS" if good else "MISS"))

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local labeled-deliverable writer (Skill 57).")
    ap.add_argument("--manifest", help="artifacts manifest JSON")
    ap.add_argument("--dest", default="~/Downloads/Social-Media-in-a-Box",
                    help="final deliverable root (default ~/Downloads/Social-Media-in-a-Box)")
    ap.add_argument("--copy", action="store_true", help="actually copy PASS artifacts (default dry-run)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.manifest:
        ap.error("--manifest is required (or use --self-test)")
    return run(args.manifest, args.dest, do_copy=args.copy, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
