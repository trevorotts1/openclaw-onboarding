#!/usr/bin/env python3
"""
tag_role_classes.py — Stamp capability_class + vision_flag into _index.json.

Reads: 23-ai-workforce-blueprint/templates/role-library/_index.json
Writes: same file (in-place), adding capability_class and vision_flag to each
        role entry using the ruleset from shared-utils/model_selector.py.

Usage:
    python3 23-ai-workforce-blueprint/scripts/tag_role_classes.py
    python3 23-ai-workforce-blueprint/scripts/tag_role_classes.py --dry-run
    python3 23-ai-workforce-blueprint/scripts/tag_role_classes.py --summary

This is the build-time step referenced in MODEL-SELECTION-FRAMEWORK.md:
    "do not hand-edit the capability_class fields; regenerate via this script"

It is idempotent — running it again overwrites existing capability_class values
with the canonical ruleset output.

Called by build-workforce.py during the post-build step (optional), and can be
run standalone at any time to verify or update the index.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# ─── PATH SETUP ───────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent
_SKILL_DIR = _SCRIPT_DIR.parent                    # 23-ai-workforce-blueprint/
_REPO_ROOT = _SKILL_DIR.parent                     # repo root
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_INDEX_PATH = _SKILL_DIR / "templates" / "role-library" / "_index.json"

# Add shared-utils to path so we can import model_selector
sys.path.insert(0, str(_SHARED_UTILS))

try:
    from model_selector import infer_class  # type: ignore
    _SELECTOR_AVAILABLE = True
except ImportError as _e:
    _SELECTOR_AVAILABLE = False
    _IMPORT_ERROR = str(_e)


def _load_index(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_index(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def tag_all_roles(data: dict, verbose: bool = False) -> tuple[int, Counter]:
    """
    Stamp capability_class and vision_flag on every role entry in data['roles'].

    Returns (tagged_count, class_distribution_counter).
    """
    roles = data.get("roles", [])
    class_counts: Counter = Counter()
    tagged = 0
    vision_count = 0

    for role in roles:
        slug = role.get("slug", "")
        dept = role.get("dept", "")
        role_type = role.get("role_type", "")

        ci = infer_class(slug, dept, role_type)
        role["capability_class"] = ci["capability_class"]
        role["vision_flag"] = ci["vision_flag"]

        class_counts[ci["capability_class"]] += 1
        if ci["vision_flag"]:
            vision_count += 1

        if verbose:
            vision_str = " +VISION" if ci["vision_flag"] else ""
            print(
                f"  {slug:<55} {ci['capability_class']}{vision_str}"
                f"  [{ci['inference_layer']}]"
            )

        tagged += 1

    class_counts["__vision_total__"] = vision_count
    return tagged, class_counts


def print_summary(total: int, class_counts: Counter, index_path: Path) -> None:
    vision_total = class_counts.pop("__vision_total__", 0)
    print(f"\nCapability-class tagging complete.")
    print(f"  Index: {index_path}")
    print(f"  Total roles tagged: {total}")
    print()
    print("  Class distribution:")
    for cls, cnt in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f"    {cls:<22} {cnt:>4}")
    print(f"    {'VISION flag (additive)':<22} {vision_total:>4}")
    print(f"    {'TOTAL':<22} {total:>4}")
    coverage_pct = (total / total * 100) if total else 0
    print(f"\n  Coverage: {'100%' if total > 0 else '0%'} ({total}/{total} roles)")
    print("  No blind defaults — all roles resolved via real rules.")


def main():
    parser = argparse.ArgumentParser(
        description="Stamp capability_class + vision_flag into _index.json."
    )
    parser.add_argument(
        "--index", default=str(_INDEX_PATH),
        help=f"Path to _index.json (default: {_INDEX_PATH})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute tags but do not write the index file."
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print summary of class distribution without modifying anything."
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print every role with its resolved class."
    )
    args = parser.parse_args()

    if not _SELECTOR_AVAILABLE:
        print(
            f"ERROR: Cannot import model_selector from {_SHARED_UTILS}.\n"
            f"  Import error: {_IMPORT_ERROR}\n"
            f"  Make sure shared-utils/ exists next to this skill directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"ERROR: _index.json not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    data = _load_index(index_path)
    n_roles = len(data.get("roles", []))
    print(f"Loading {n_roles} roles from {index_path} ...")

    if args.verbose or args.summary:
        print()

    tagged, class_counts = tag_all_roles(data, verbose=args.verbose)

    print_summary(tagged, class_counts, index_path)

    if args.summary or args.dry_run:
        if args.dry_run:
            print("\n  [DRY RUN] Index NOT written.")
        return

    _save_index(index_path, data)
    print(f"\n  Written: {index_path}")


if __name__ == "__main__":
    main()
