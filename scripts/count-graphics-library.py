#!/usr/bin/env python3
"""
count-graphics-library.py — Live image counter for the Graphics department dashboard card.

U136: The graphics department dashboard card queries the image count from a
cached counter that was last updated when the library had ~5,000 images. The
actual library has grown to ~19,000. The stale count is displayed to the
operator as current.

This script performs a LIVE recount of the Design Intelligence Library (Skill
45) assets and writes the count plus a "last counted at" timestamp to a JSON
state file. It is designed to run as a periodic background job (cron or
agent-driven re-run) so the dashboard card never serves another stale number.

WHAT IT COUNTS:
  - Every registered style card in 45-design-intelligence-library/library/
    (identified by INDEX.md table entries and card .md files in category dirs)
  - Design assets: .png, .jpg, .jpeg, .webp, .gif, .avif, .svg files under the
    library tree (actual generated images).
  - Total item count = card count + asset count.

OUTPUT:
  Writes <output_file> (default: $OPENCLAW_CONFIG/state/graphics-library-count.json):

    {
      "card_count": 1234,
      "asset_count": 17890,
      "total": 19124,
      "last_counted_at": "2026-07-23T14:22:05Z",
      "library_root": "/path/to/library",
      "source_version": "1.0.0"
    }

EXIT CODES:
  0 — Success (count written)
  1 — Library directory not found (missing skill install)
  2 — Write failure (disk full, permission denied, filesystem error)
  3 — Usage error (bad arguments)

USAGE:
  python3 scripts/count-graphics-library.py                          # default output
  python3 scripts/count-graphics-library.py --library /custom/path   # custom library
  python3 scripts/count-graphics-library.py --output /tmp/count.json # custom output
  python3 scripts/count-graphics-library.py --self-test              # run self-tests

ATOMICITY:
  The output file is written atomically (tempfile + os.replace), matching the
  pattern established in lib-onboarding-state.sh. A mid-write crash leaves the
  previous (stale) file intact — it never produces a truncated or empty file.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration defaults ─────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_LIBRARY = REPO_ROOT / "45-design-intelligence-library" / "library"
DEFAULT_CONFIG = os.environ.get("OPENCLAW_CONFIG", str(Path.home() / ".openclaw"))
DEFAULT_OUTPUT = Path(DEFAULT_CONFIG) / "state" / "graphics-library-count.json"

# Glob patterns for image assets under the library tree
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg"}

# Directories inside the library that contain style cards (category folders).
# _system/ is configuration, not cards.
NON_CARD_DIRS = {"_system", "templates"}

SCRIPT_VERSION = "1.0.0"


def _utc_now() -> str:
    """Return current UTC time as ISO8601 with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def count_cards(library_root: Path) -> int:
    """
    Count registered style cards in the design library.

    A style card is any .md file inside a category directory (one level below
    library_root) that is NOT named _RULES.md, INDEX.md, README.md, or
    DEPARTMENT-BUILD-BRIEF.md. The _system/ directory and any _-prefixed
    subdirectories are skipped.

    Returns the cardinality of uniquely identified card files.
    """
    if not library_root.is_dir():
        return 0

    cards = set()
    for entry in sorted(library_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in NON_CARD_DIRS:
            continue
        if entry.name.startswith("_"):
            continue

        for card_file in entry.glob("*.md"):
            name = card_file.name
            if name in ("_RULES.md", "INDEX.md", "README.md",
                         "DEPARTMENT-BUILD-BRIEF.md"):
                continue
            if name.startswith("_"):
                continue
            cards.add(str(card_file.relative_to(library_root)))

    return len(cards)


def count_assets(library_root: Path) -> int:
    """
    Count generated image assets under the library tree.

    Scans recursively for files matching IMAGE_EXTENSIONS. Only regular files
    are counted; directories, symlinks, and special files are skipped.
    Paths are deduplicated via set to handle case-insensitive filesystems.
    """
    if not library_root.is_dir():
        return 0

    seen: set[str] = set()
    for entry in library_root.rglob("*"):
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            seen.add(str(entry.resolve()))
    return len(seen)


def atomic_write_json(filepath: Path, data: dict) -> None:
    """
    Atomically write JSON data to filepath.

    Uses tempfile + os.replace — matching the atomic-write pattern in
    lib-onboarding-state.sh. On success the target file is replaced in one
    filesystem operation; on failure the previous file (if any) is intact.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent),
        prefix=".graphics-library-count.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, str(filepath))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count graphics library assets (U136 live counter)",
    )
    parser.add_argument(
        "--library",
        type=Path,
        default=DEFAULT_LIBRARY,
        help="Path to the design-intelligence-library library/ directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write the count JSON file",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in self-tests and exit",
    )
    args = parser.parse_args()

    if args.self_test:
        return _run_self_tests()

    library_root = args.library.resolve()
    output_file = args.output.resolve()

    if not library_root.is_dir():
        print(
            f"[FAIL] Graphics library directory not found: {library_root}",
            file=sys.stderr,
        )
        return 1

    card_count = count_cards(library_root)
    asset_count = count_assets(library_root)
    total = card_count + asset_count
    counted_at = _utc_now()

    result = {
        "card_count": card_count,
        "asset_count": asset_count,
        "total": total,
        "last_counted_at": counted_at,
        "library_root": str(library_root),
        "source_version": SCRIPT_VERSION,
    }

    try:
        atomic_write_json(output_file, result)
    except OSError as exc:
        print(
            f"[FAIL] Could not write count file: {output_file} — {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        f"[OK] Graphics library counted: {card_count} cards + "
        f"{asset_count} assets = {total} total "
        f"(counted at {counted_at}) -> {output_file}"
    )
    return 0


# ── Self-tests ──────────────────────────────────────────────────────────────────

def _run_self_tests() -> int:
    """Run hermetic self-tests with synthetic fixture directories."""
    failed = 0
    passed = 0

    def ok(label: str) -> None:
        nonlocal passed
        passed += 1
        print(f"  ok   — {label}")

    def bad(label: str) -> None:
        nonlocal failed
        failed += 1
        print(f"  FAIL — {label}")

    tmp_root = Path(tempfile.mkdtemp(prefix="u136-self-test-"))
    try:
        # ── Test 1: empty library ───────────────────────────────────────────────
        empty_lib = tmp_root / "empty"
        empty_lib.mkdir()
        c = count_cards(empty_lib)
        a = count_assets(empty_lib)
        if c == 0 and a == 0:
            ok("test 1: empty library returns zero counts")
        else:
            bad(f"test 1: empty library returned cards={c} assets={a}, expected 0/0")

        # ── Test 2: one card in a category directory ────────────────────────────
        one_lib = tmp_root / "one-card"
        one_lib.mkdir()
        cat_dir = one_lib / "single-image-designs"
        cat_dir.mkdir()
        (cat_dir / "SI-001_style.md").write_text("# SI-001 test card")
        (cat_dir / "_RULES.md").write_text("# rules")
        c = count_cards(one_lib)
        a = count_assets(one_lib)
        if c == 1 and a == 0:
            ok("test 2: one card counted, _RULES.md excluded")
        else:
            bad(f"test 2: cards={c} assets={a}, expected cards=1 assets=0")

        # ── Test 3: _system/ and _-prefixed dirs excluded ───────────────────────
        sys_lib = tmp_root / "system-exclude"
        sys_lib.mkdir()
        (sys_lib / "_system").mkdir()
        (sys_lib / "_system" / "MASTER-SOP.md").write_text("# sop")
        (sys_lib / "_system" / "templates").mkdir(parents=True)
        (sys_lib / "_system" / "templates" / "NAMED-STYLES.md").write_text("# styles")
        (sys_lib / "_config").mkdir()
        (sys_lib / "_config" / "secrets.md").write_text("# secrets")
        c = count_cards(sys_lib)
        if c == 0:
            ok("test 3: _system/ and _-prefixed dirs excluded")
        else:
            bad(f"test 3: cards={c}, expected 0")

        # ── Test 4: multiple categories x multiple cards ────────────────────────
        multi_lib = tmp_root / "multi"
        multi_lib.mkdir()
        for cat in ("single-image-designs", "banner-designs", "book-cover-designs"):
            d = multi_lib / cat
            d.mkdir()
            (d / "_RULES.md").write_text("# rules")
            for i in range(1, 4):
                (d / f"card-{i}.md").write_text(f"# {cat} card {i}")
        c = count_cards(multi_lib)
        if c == 9:
            ok("test 4: 3 categories x 3 cards = 9")
        else:
            bad(f"test 4: cards={c}, expected 9")

        # ── Test 5: asset counting (image files) ────────────────────────────────
        asset_lib = tmp_root / "assets"
        asset_lib.mkdir()
        (asset_lib / "banner-designs").mkdir()
        (asset_lib / "banner-designs" / "banner1.png").write_text("fake png")
        (asset_lib / "banner-designs" / "banner2.jpg").write_text("fake jpg")
        (asset_lib / "single-image-designs").mkdir()
        (asset_lib / "single-image-designs" / "hero.webp").write_text("fake webp")
        a = count_assets(asset_lib)
        c = count_cards(asset_lib)
        if a == 3 and c == 0:
            ok("test 5: 3 image assets counted, no cards")
        else:
            bad(f"test 5: assets={a} cards={c}, expected assets=3 cards=0")

        # ── Test 6: atomic write round-trip ─────────────────────────────────────
        write_dir = tmp_root / "output-test"
        write_dir.mkdir()
        out_file = write_dir / "count.json"
        data = {
            "card_count": 42,
            "asset_count": 19000,
            "total": 19042,
            "last_counted_at": "2026-07-23T14:00:00Z",
            "library_root": "/test/path",
            "source_version": "1.0.0",
        }
        try:
            atomic_write_json(out_file, data)
            read_back = json.loads(out_file.read_text())
            if read_back == data:
                ok("test 6: atomic write round-trips correctly")
            else:
                bad(f"test 6: read-back mismatch: {read_back}")
        except Exception as exc:
            bad(f"test 6: atomic write failed: {exc}")

        # ── Test 7: atomic write on unwritable dir ──────────────────────────────
        bad_dir = tmp_root / "unwritable"
        bad_dir.mkdir(mode=0o444)
        try:
            atomic_write_json(bad_dir / "nope.json", {"test": True})
            bad("test 7: unwritable dir should have raised")
        except (OSError, PermissionError):
            ok("test 7: unwritable dir raises OSError")

        # ── Test 8: nonexistent library → 0 counts ──────────────────────────────
        nonexistent = tmp_root / "does-not-exist"
        if count_cards(nonexistent) == 0 and count_assets(nonexistent) == 0:
            ok("test 8: nonexistent library returns 0")
        else:
            bad("test 8: nonexistent library returned non-zero")

        # ── Test 9: top-level non-card files excluded ───────────────────────────
        top_lib = tmp_root / "top-level"
        top_lib.mkdir()
        (top_lib / "INDEX.md").write_text("# index")
        (top_lib / "README.md").write_text("# readme")
        (top_lib / "DEPARTMENT-BUILD-BRIEF.md").write_text("# brief")
        (top_lib / "single-image-designs").mkdir()
        (top_lib / "single-image-designs" / "_RULES.md").write_text("# rules")
        c = count_cards(top_lib)
        if c == 0:
            ok("test 9: top-level docs and _RULES.md excluded")
        else:
            bad(f"test 9: cards={c}, expected 0")

        # ── Test 10: timestamp is valid ISO8601 ─────────────────────────────────
        ts = _utc_now()
        import re as _re
        iso_pattern = _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        if iso_pattern.match(ts):
            ok("test 10: _utc_now() produces valid ISO8601 Z timestamp")
        else:
            bad(f"test 10: _utc_now() returned {ts!r} — not ISO8601 Z")

        # ── Test 11: case-insensitive image extensions ──────────────────────────
        case_lib = tmp_root / "case-lib"
        case_lib.mkdir()
        (case_lib / "facebook-ad-designs").mkdir()
        (case_lib / "facebook-ad-designs" / "ad.PNG").write_text("png")
        (case_lib / "facebook-ad-designs" / "ad.JPG").write_text("jpg")
        a = count_assets(case_lib)
        if a == 2:
            ok("test 11: case-insensitive extensions counted correctly")
        else:
            bad(f"test 11: assets={a}, expected 2")

        # ── Test 12: deeply nested assets counted ───────────────────────────────
        deep_lib = tmp_root / "deep"
        deep_lib.mkdir()
        nested = deep_lib / "powerpoint-designs" / "theme" / "backgrounds"
        nested.mkdir(parents=True)
        (nested / "bg1.png").write_text("bg1")
        (nested / "bg2.png").write_text("bg2")
        a = count_assets(deep_lib)
        if a == 2:
            ok("test 12: deeply nested assets counted")
        else:
            bad(f"test 12: assets={a}, expected 2")

    finally:
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)

    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
