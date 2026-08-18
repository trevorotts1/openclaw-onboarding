#!/usr/bin/env python3
"""
curate.py -- WORK-ITEM-13: assemble a flat 10-file deliverables/ folder at the run root.

WHY THIS EXISTS:
The 2026-08-09 run delivered 213 process artifacts spread across 14 directories. The
`delivery/` subdirectory was empty. The `deliverables/` subdirectory held 2 markdown
text plans, not products. Nothing filters or assembles a client-facing subset. The
operator opened the folder and saw 213 files, none of which were the actual products.

This module assembles a flat `deliverables/` folder at the run root containing exactly
the client-facing products (10 for the full bundle per fix_bundle_complete.py), plus
PROCESS-CERTIFICATE.md and bundle_complete.json. The working/ tree is NEVER presented
as the delivery.

WHERE IT RUNS:
  * Inside the engine's close() path, after all 6 gates pass, before terminal DONE.
  * Standalone:  python3 -m presentation_job.curate --run-dir <dir>
  * Standalone:  python3 presentation_job/curate.py --run-dir <dir>

EXIT CODES:
  0 -- all deliverables present and copied to flat folder.
  1 -- one or more deliverables missing (AF-BUNDLE-INCOMPLETE).
  2 -- run dir missing/unreadable or state.json absent.
  3 -- prior curation detected and flat folder complete (idempotency guard,
       FIX-6 R2 — pass --force to override).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import the canonical deliverable list from presentation_job/deliverables.py
# (U05 — the single source of truth every consumer imports from).
try:
    _HERE = Path(__file__).resolve().parent  # presentation_job/
    _SCRIPTS = _HERE.parent                   # scripts/
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    from presentation_job.deliverables import (
        DELIVERABLE_AUDIT_SPEC,
        REQUIRED_DELIVERABLES,
        REQUIRED_KEYS,
        _expand_filename,
        BUNDLE_COMPLETE_FILENAME,
        AF_BUNDLE_INCOMPLETE,
    )
except ImportError:
    raise ImportError(
        "curate.py requires presentation_job/deliverables.py (the single-source "
        "deliverable whitelist). Cannot resolve the canonical deliverable whitelist."
    )

# Derived from the SINGLE SOURCE OF TRUTH (DELIVERABLE_AUDIT_SPEC) — never edit by hand.
DESTINATION_FILENAMES: Dict[str, str] = {
    s["key"]: s["standardized_dest"] for s in DELIVERABLE_AUDIT_SPEC
}

# Subdirectories within the run tree to search for deliverable files, in priority order.
SEARCH_SUBDIRS = [
    "working/deliverables",
    "working",
    "renders",
    "working/presenter-speech",
    "working/WORKBOOK",
    "working/checkpoints",
    "working/copy",
    "",
]

# The gate artifact produced by fix_bundle_complete.py when the full bundle is complete.
BUNDLE_COMPLETE_FILENAME = BUNDLE_COMPLETE_FILENAME

# Suffix added to the destination name when multiple candidates are found for one deliverable.
NAME_CONFLICT_SUFFIX = ".alt"

# Marker consulted by the idempotency guard (FIX-6 R2): a prior curation run is
# detected by the curation manifest in working/checkpoints/. Writing the manifest
# into checkpoints (not deliverables/) is FIX-4 R2; the guard relies on that
# location so the flat folder itself stays a pure client-facing surface.
IDEMPOTENCY_MARKER = "curation_manifest.json"

# The file that records the source path of every copied file. Written into
# working/checkpoints/ (NOT into the flat deliverables/ folder — the flat folder
# must contain ONLY client-facing products + PROCESS-CERTIFICATE.md + bundle_complete.json).
CURATION_MANIFEST = "curation_manifest.json"


def _resolve_destination_name(key: str) -> str:
    """Return the standardized flat-folder filename for a deliverable key."""
    if key in DESTINATION_FILENAMES:
        return DESTINATION_FILENAMES[key]
    # Fallback: use the last segment of whatever template produces.
    spec = next((d for d in REQUIRED_DELIVERABLES if d["key"] == key), None)
    if spec:
        return Path(_expand_filename(spec["filename"], "deck")).name
    return key


class CurateAlreadyRan(RuntimeError):
    """Raised by the idempotency guard (FIX-6 R2) when a prior curation run is
    detected (curation_manifest.json present in working/checkpoints/) and the
    full deliverable set is already assembled. A double close() must not produce
    *.alt duplicates."""


class AFBundleIncomplete(RuntimeError):
    """Raised when a deliverable in the whitelist is missing and not covered
    by an owner_skip_approval token. The exception message lists every
    missing file by key and filename."""

    def __init__(self, missing_keys: List[str], details: List[str] = None):
        self.missing_keys = list(missing_keys)
        self.details = list(details or [])
        lines = [
            f"AF-BUNDLE-INCOMPLETE: {len(missing_keys)} deliverable(s) missing",
        ]
        for d in (details or missing_keys):
            lines.append(f"  - {d}")
        super().__init__("\n".join(lines))


def locate_deliverable(run_dir: str | Path, key: str, template_filename: str) -> Optional[str]:
    """Search the run directory tree for a file matching the key+filename.

    Searches known subdirectories in priority order. Returns the absolute path
    if found, None if absent. A file named '<anything>.md' that is NOT the
    expected file type will not match (e.g., a .md plan file will not match
    when .pptx or .pdf is expected).

    Args:
        run_dir: The job run directory root.
        key: The deliverable key (e.g. 'deck_pptx', 'speech_pdf').
        template_filename: The filename as expanded from the deck_slug template.
    """
    run = Path(run_dir)
    expected_name = template_filename.lower().rsplit(".", 1)[0]
    expected_suffix = Path(template_filename).suffix.lower()

    candidates: List[Tuple[int, Path]] = []

    for subdir in SEARCH_SUBDIRS:
        search_root = run / subdir if subdir else run
        if not search_root.is_dir():
            continue

        # First try exact name match.
        exact = search_root / template_filename
        if exact.is_file() and not exact.is_symlink():
            try:
                if exact.stat().st_size > 0:
                    if expected_suffix and _name_matches_type(exact.name, key):
                        return str(exact.resolve())
            except OSError:
                pass

        # Then try case-insensitive match.
        try:
            for child in search_root.iterdir():
                if not child.is_file() or child.is_symlink():
                    continue
                if child.name.lower() == template_filename.lower():
                    try:
                        if child.stat().st_size > 0:
                            if _name_matches_type(child.name, key):
                                return str(child.resolve())
                    except OSError:
                        pass
        except OSError:
            pass

    return None


def _name_matches_type(filename: str, key: str) -> bool:
    """Reject obvious type mismatches (e.g., .md file when .pptx expected)."""
    suffix = Path(filename).suffix.lower()
    spec = next((s for s in DELIVERABLE_AUDIT_SPEC if s["key"] == key), None)
    if spec is None:
        return True
    expected = spec.get("expected_suffix", "")
    # Allow .html and .htm for teleprompter
    if expected == ".html":
        return suffix in (".html", ".htm")
    if not expected:
        return True
    return suffix == expected.lower()


def copy_to_flat(source_path: str, dest_dir: str, dest_name: str) -> Tuple[str, int]:
    """Copy (or hardlink) the source file into dest_dir with the given filename.

    Returns (destination_path, byte_count). Verifies the copy is non-empty and
    matches the source's byte count.

    Conflict policy (WI-13 R2): a destination that already exists is OVERWRITTEN
    in place — never renamed to `*.alt`. The idempotency guard (curate force=False)
    prevents a normal double-close from reaching here; when an explicit re-curate
    (--force) does reach it, the correct semantics are "refresh the primary name",
    not "grow a pile of *.alt duplicates". An *.alt name is produced ONLY for a
    genuine same-key multi-source conflict, which is impossible by construction
    (one source per key) — so `*.alt` files never appear in a curated flat folder.
    """
    src = Path(source_path)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    dest_path = dest / dest_name

    src_size = src.stat().st_size

    # Try hardlink first (same filesystem, zero copy cost). Remove the stale
    # destination BEFORE linking (a stale hardlink to the same inode would
    # otherwise defeat the unlink-on-conflict intent).
    try:
        if dest_path.exists():
            dest_path.unlink()
        os.link(str(src), str(dest_path))
    except (OSError, PermissionError):
        # Fall back to copy.
        shutil.copy2(str(src), str(dest_path))

    # Verify.
    if not dest_path.is_file():
        raise OSError(f"copy failed: {dest_path} does not exist after copy")
    dest_size = dest_path.stat().st_size
    if dest_size == 0:
        dest_path.unlink()
        raise OSError(f"copy produced a zero-byte file: {dest_path}")
    if dest_size != src_size:
        dest_path.unlink()
        raise OSError(
            f"copy size mismatch: source {src_size} bytes, destination {dest_size} bytes"
        )

    return str(dest_path.resolve()), dest_size


def _read_owner_skip_approvals(run_dir: Path) -> set:
    """Read owner_skip_approval tokens from the run's process manifest or waivers.

    Returns a set of deliverable keys that the owner has explicitly approved for skipping.
    """
    approved: set = set()

    # Check process_manifest.json
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    try:
        if pm.is_file():
            obj = json.loads(pm.read_text(encoding="utf-8"))
            skips = obj.get("owner_skip_approval") or []
            if isinstance(skips, list):
                for s in skips:
                    if isinstance(s, str):
                        approved.add(s)
                    elif isinstance(s, dict):
                        approved.add(s.get("key", ""))
    except (json.JSONDecodeError, OSError):
        pass

    # Check waivers.json for skipped deliverables
    wf = run_dir / "working" / "waivers.json"
    try:
        if wf.is_file():
            obj = json.loads(wf.read_text(encoding="utf-8"))
            for w in obj if isinstance(obj, list) else []:
                if isinstance(w, dict) and w.get("rule") in REQUIRED_KEYS:
                    approved.add(w["rule"])
    except (json.JSONDecodeError, OSError):
        pass

    return approved


def curate(run_dir: str | Path, deck_slug: str = "deck", force: bool = False) -> dict:
    """Assemble the flat deliverables/ folder at the run root.

    Called from the engine's close() path after all 6 gates pass and after
    the PROCESS-CERTIFICATE is minted.

    Idempotency (FIX-6 R2): if a prior curation run is detected (manifest in
    working/checkpoints/) and the full deliverable set is already in the flat
    folder, this raises CurateAlreadyRan instead of re-running (a double close()
    must not produce *.alt duplicates). Pass force=True to re-curate anyway.

    1. Creates run_dir/deliverables/ if it does not exist.
    2. For each item in REQUIRED_DELIVERABLES:
       a. locate_deliverable() -- find the file in the working/ tree
          using BOTH the standardized destination name AND the
          deck-slug-templated source name.
       b. If found: copy_to_flat() into deliverables/ with the
          standardized destination name.
       c. If missing: record it in the missing list.
    3. If any deliverable is missing AND not covered by an
       owner_skip_approval token: raise AFBundleIncomplete.
    4. Copy PROCESS-CERTIFICATE.md from working/checkpoints/ to deliverables/.
    5. Copy bundle_complete.json from working/checkpoints/ to deliverables/
       (written by fix_bundle_complete.py).
    6. Write curation_manifest.json into working/checkpoints/ recording the
       source path of every file (never into the flat deliverables/ folder).

    Returns a dict with the curation result.
    """
    run_dir = Path(run_dir)
    deliverables_dir = run_dir / "deliverables"
    deliverables_dir.mkdir(parents=True, exist_ok=True)

    # Idempotency guard (FIX-6 R2): if a prior curation run already produced the
    # manifest AND every standardized destination file exists in the flat folder,
    # refuse to re-curate instead of duplicating/renaming files (the copy_to_flat
    # conflict path would otherwise create *.alt duplicates on a double close).
    # A partial flat folder still re-curates (self-healing); --force overrides.
    _prior = run_dir / "working" / "checkpoints" / IDEMPOTENCY_MARKER
    if not force and _prior.is_file():
        _have_all = all(
            (deliverables_dir / _resolve_destination_name(key)).is_file()
            for key in REQUIRED_KEYS
        )
        if _have_all:
            raise CurateAlreadyRan(
                f"curate: prior curation detected ({_prior}) and the full deliverable "
                f"set is already present in {deliverables_dir} — refusing to re-curate. "
                f"Re-running would duplicate files as *{NAME_CONFLICT_SUFFIX}. Use "
                f"--force to override."
            )

    owner_skip = _read_owner_skip_approvals(run_dir)

    curated: List[Dict[str, str]] = []
    missing: List[Dict[str, str]] = []

    for spec in REQUIRED_DELIVERABLES:
        key = spec["key"]
        if key in owner_skip:
            curated.append({
                "key": key,
                "label": spec["label"],
                "source": None,
                "dest": None,
                "status": "skipped-by-owner",
            })
            continue

        # The destination name in the flat folder.
        dest_name = _resolve_destination_name(key)

        # Try finding the file: first by the standardized destination name,
        # then by the deck-slug-templated source name, then by any filename
        # that fuzzy-matches the key's expected suffix pattern.
        source_path = None

        # Search pass 1: standardized destination name.
        source_path = locate_deliverable(run_dir, key, dest_name)

        # Search pass 2: deck-slug-templated source filename.
        if source_path is None and deck_slug != "deck":
            src_name = _expand_filename(spec["filename"], deck_slug)
            if src_name != dest_name:
                source_path = locate_deliverable(run_dir, key, src_name)

        # Search pass 3: default deck slug template.
        if source_path is None and deck_slug != "deck":
            src_name = _expand_filename(spec["filename"], "deck")
            if src_name != dest_name:
                source_path = locate_deliverable(run_dir, key, src_name)

        # Search pass 4: fuzzy search by suffix pattern in the whole tree.
        if source_path is None:
            source_path = _fuzzy_locate(run_dir, key)

        if source_path is None:
            missing.append({"key": key, "label": spec["label"], "expected_name": dest_name})
            continue

        try:
            dest_path, byte_count = copy_to_flat(source_path, str(deliverables_dir), dest_name)
        except OSError as exc:
            missing.append({
                "key": key,
                "label": spec["label"],
                "expected_name": dest_name,
                "copy_error": str(exc),
            })
            continue

        curated.append({
            "key": key,
            "label": spec["label"],
            "source": source_path,
            "dest": dest_path,
            "dest_name": dest_name,
            "bytes": byte_count,
            "status": "curated",
        })

    # Copy PROCESS-CERTIFICATE.md
    cert_src = run_dir / "working" / "checkpoints" / "process-certificate.md"
    cert_dest = None
    if cert_src.is_file():
        try:
            cert_dest_path, cert_bytes = copy_to_flat(
                str(cert_src), str(deliverables_dir), "PROCESS-CERTIFICATE.md"
            )
            cert_dest = cert_dest_path
            curated.append({
                "key": "process_certificate",
                "label": "PROCESS-CERTIFICATE.md",
                "source": str(cert_src),
                "dest": cert_dest,
                "dest_name": "PROCESS-CERTIFICATE.md",
                "bytes": cert_bytes,
                "status": "curated",
            })
        except OSError:
            pass

    # Copy bundle_complete.json
    bundle_src = None
    for loc in [
        run_dir / "working" / "checkpoints" / BUNDLE_COMPLETE_FILENAME,
        run_dir / BUNDLE_COMPLETE_FILENAME,
    ]:
        if loc.is_file():
            bundle_src = loc
            break

    if bundle_src is None:
        # Generate a bundle_complete.json as the gate record if none exists
        # but curation succeeded (all deliverables present).
        if not missing:
            bundle_record = {
                "gate": BUNDLE_COMPLETE_FILENAME,
                "complete": True,
                "deliverable_count": len(REQUIRED_DELIVERABLES),
                "deliverables": {
                    k: _resolve_destination_name(k) for k in REQUIRED_KEYS
                },
                "curated_at": _now_utc(),
                "note": "generated by curate.py -- no prior bundle_complete.json found",
            }
            bundle_dest = deliverables_dir / BUNDLE_COMPLETE_FILENAME
            bundle_dest.write_text(json.dumps(bundle_record, indent=2))
            bundle_src_path = str(bundle_dest)
            curated.append({
                "key": "bundle_complete",
                "label": BUNDLE_COMPLETE_FILENAME,
                "source": None,
                "dest": str(bundle_dest),
                "dest_name": BUNDLE_COMPLETE_FILENAME,
                "status": "generated-by-curate",
            })
        else:
            bundle_src_path = None
    else:
        try:
            bundle_dest_path, bundle_bytes = copy_to_flat(
                str(bundle_src), str(deliverables_dir), BUNDLE_COMPLETE_FILENAME
            )
            bundle_src_path = bundle_dest_path
            curated.append({
                "key": "bundle_complete",
                "label": BUNDLE_COMPLETE_FILENAME,
                "source": str(bundle_src),
                "dest": bundle_dest_path,
                "dest_name": BUNDLE_COMPLETE_FILENAME,
                "bytes": bundle_bytes,
                "status": "curated",
            })
        except OSError:
            bundle_src_path = None

    # Write curation manifest into working/checkpoints/ — NOT into the flat
    # deliverables/ folder. The flat folder must contain ONLY client-facing
    # products + PROCESS-CERTIFICATE.md + bundle_complete.json (FIX-4 R2).
    checkpoints_dir = run_dir / "working" / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "curated_at": _now_utc(),
        "deck_slug": deck_slug,
        "deliverables_dir": str(deliverables_dir),
        "total_required": len(REQUIRED_DELIVERABLES),
        "curated_count": sum(1 for c in curated if c.get("status") == "curated"),
        "skipped_count": sum(1 for c in curated if c.get("status") == "skipped-by-owner"),
        "missing_count": len(missing),
        "files": curated,
    }
    manifest_path = checkpoints_dir / CURATION_MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    result: Dict[str, Any] = {
        "deliverables_dir": str(deliverables_dir),
        "curated_count": manifest["curated_count"],
        "skipped_count": manifest["skipped_count"],
        "missing_count": manifest["missing_count"],
        "missing": missing,
        "files": [c.get("dest") for c in curated if c.get("dest")],
        "curation_manifest": str(manifest_path),
    }

    # Hard-fail on missing deliverables not covered by owner skip.
    if missing:
        non_skipped_missing = [
            m for m in missing
            if m["key"] not in owner_skip
        ]
        if non_skipped_missing:
            details = [
                f"{m['key']}: {m.get('label', m['key'])} (expected: {m.get('expected_name', '?')})"
                + (f" -- {m['copy_error']}" if m.get("copy_error") else "")
                for m in non_skipped_missing
            ]
            raise AFBundleIncomplete(
                missing_keys=[m["key"] for m in non_skipped_missing],
                details=details,
            )

    return result


def _fuzzy_locate(run_dir: Path, key: str) -> Optional[str]:
    """Fallback: search the entire run tree for a file matching the key's
    expected suffix and size floor (from DELIVERABLE_AUDIT_SPEC). Returns the first match."""
    spec = next((s for s in DELIVERABLE_AUDIT_SPEC if s["key"] == key), None)
    if spec is None:
        return None
    suffix = spec.get("expected_suffix", "")
    min_sz = spec.get("min_bytes", 5000)

    if not suffix:
        return None

    deliveries_target = run_dir / "deliverables"
    matches: List[Tuple[int, Path]] = []
    for root, _dirs, files in os.walk(str(run_dir)):
        # Skip ONLY the run-root deliverables/ folder (not subdirs named deliverables/).
        if Path(root) == deliveries_target:
            continue
        for fname in files:
            if not fname.lower().endswith(suffix):
                continue
            # Skip known non-deliverable patterns.
            if fname.startswith(".") or fname.endswith(".tmp"):
                continue
            fpath = Path(root) / fname
            try:
                if fpath.is_file() and not fpath.is_symlink():
                    sz = fpath.stat().st_size
                    if sz >= min_sz:
                        # Prefer files with names that contain the key slug.
                        score = 1000 if key in fname.lower() else 0
                        score += sz  # prefer larger files
                        matches.append((score, fpath))
            except OSError:
                pass

    if not matches:
        return None

    # Return the highest-scoring match.
    matches.sort(key=lambda x: x[0], reverse=True)
    return str(matches[0][1].resolve())


def verify_flat_folder(deliverables_dir: str | Path) -> Tuple[bool, List[str]]:
    """Post-curation check: the deliverables/ folder must contain ONLY the
    whitelisted files + cert + bundle json. The curation manifest lives in
    working/checkpoints/, never in the flat folder (FIX-4 R2).

    Returns (is_clean, list_of_unexpected_paths).
    """
    deliverables_dir = Path(deliverables_dir)
    if not deliverables_dir.is_dir():
        return False, ["deliverables/ does not exist"]

    expected_names: set = set()
    for key in REQUIRED_KEYS:
        expected_names.add(_resolve_destination_name(key).lower())
    expected_names.add("process-certificate.md")
    expected_names.add(BUNDLE_COMPLETE_FILENAME.lower())

    unexpected = []
    for child in deliverables_dir.iterdir():
        if child.name.lower() not in expected_names:
            unexpected.append(str(child))

    return len(unexpected) == 0, unexpected


def _resolve_deck_slug(run_dir: Path) -> str:
    """Resolve the deck_slug for filename expansion.

    D8 FIX: read from the ENGINE-UPKEPT copy (working/copy/intake.json) FIRST,
    before falling back to the frozen state.json snapshot.  state.json.intake
    is frozen at --new time, before deck_slug is written into
    working/copy/intake.json by the engine's intake phase.  A missing deck_slug
    in state.json caused _fuzzy_locate to pick the wrong file
    (WORKBOOK-FILLABLE.pdf, 10.7 MB).

    Resolution chain:
      1. working/copy/intake.json["deck_slug"]   -- engine-upkept (LIVE)
      2. working/copy/intake.json["title"]        -- fallback for slugless decks
      3. state.json["intake"]["deck_slug"]         -- frozen snapshot (STALE)
      4. state.json["intake"]["title"]             -- last fallback
      5. run_dir.name                              -- ultimate fallback
    After resolution the string is slugified to alphanumeric + hyphens.
    """
    import re as _re
    slug = None

    # Pass 1: engine-upkept copy (LIVE — this is the fix).
    engine_copy = run_dir / "working" / "copy" / "intake.json"
    try:
        obj = json.loads(engine_copy.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            slug = obj.get("deck_slug") or obj.get("title") or None
    except (json.JSONDecodeError, OSError):
        pass

    # Pass 2: frozen state.json (STALE — fallback only).
    if not slug:
        state_file = run_dir / "state.json"
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            intake = state.get("intake") or {}
            slug = intake.get("deck_slug") or intake.get("title") or None
        except (json.JSONDecodeError, OSError):
            pass

    # Pass 3: ultimate fallback.
    if not slug:
        slug = run_dir.name

    slug = str(slug)
    slug = _re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "deck"
    return slug


def _now_utc() -> str:
    try:
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="WORK-ITEM-13: assemble the flat 10-file deliverables/ folder"
    )
    ap.add_argument("--run-dir", type=Path, required=True,
                    help="the job run directory")
    ap.add_argument("--deck-slug", default=None,
                    help="deck slug for templated filenames (auto-detected if omitted)")
    ap.add_argument("--verify-only", action="store_true",
                    help="verify the flat folder without assembling it")
    ap.add_argument("--force", action="store_true",
                    help="re-curate even when a prior curation run is detected "
                         "(idempotency guard override)")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON result")
    args = ap.parse_args(argv)

    run_dir = args.run_dir.expanduser().resolve()
    if not run_dir.is_dir():
        print(f"curate: run dir not a directory: {run_dir}", file=sys.stderr)
        return 2

    # Auto-detect deck slug.
    # D8 FIX: read deck_slug from the ENGINE-UPKEPT copy (working/copy/intake.json)
    # BEFORE falling back to the frozen state.json snapshot.  state.json.intake is
    # frozen at --new time, before deck_slug is written into working/copy/intake.json
    # by the engine's intake phase.  A missing deck_slug in state.json caused
    # _fuzzy_locate to pick the wrong file (WORKBOOK-FILLABLE.pdf, 10.7 MB) when the
    # correct source file (e.g. spaulding-45min-FINAL.pdf) was present and named.
    deck_slug = args.deck_slug
    if deck_slug is None:
        deck_slug = _resolve_deck_slug(run_dir)

    if args.verify_only:
        deliverables_dir = run_dir / "deliverables"
        is_clean, unexpected = verify_flat_folder(deliverables_dir)
        if args.json:
            print(json.dumps({"clean": is_clean, "unexpected": unexpected}, indent=2))
        elif is_clean:
            print(f"deliverables/ is clean: {deliverables_dir}")
        else:
            print(f"deliverables/ has unexpected files: {deliverables_dir}")
            for u in unexpected:
                print(f"  UNEXPECTED: {u}")
        return 0 if is_clean else 1

    try:
        result = curate(run_dir, deck_slug=deck_slug, force=args.force)
    except CurateAlreadyRan as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"IDEMPOTENT: {exc}", file=sys.stderr)
        return 3
    except AFBundleIncomplete as exc:
        if args.json:
            print(json.dumps({
                "ok": False,
                "error": str(exc),
                "missing_keys": exc.missing_keys,
            }, indent=2))
        else:
            print(f"FATAL [{AF_BUNDLE_INCOMPLETE}]: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"ok": True, **result}, indent=2))
    else:
        print(f"CURATED: {result['curated_count']} deliverable(s) assembled in {result['deliverables_dir']}")
        for f in result.get("files", []):
            print(f"  {f}")
        if result.get("skipped_count"):
            print(f"  ({result['skipped_count']} skipped by owner approval)")
        if result.get("missing_count"):
            print(f"  WARNING: {result['missing_count']} missing (owner-approved skip)")
        print(f"  curation manifest: {result['curation_manifest']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
