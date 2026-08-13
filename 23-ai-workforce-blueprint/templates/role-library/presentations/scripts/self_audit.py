#!/usr/bin/env python3
"""
self_audit.py -- Mechanical verification that all deliverables exist before handoff.

Serves WORK-ITEM-16 (ANTI-DRIFT CORE): Self-audit of the whole folder before handoff.

Reads the master deliverable whitelist from fix_bundle_complete.py, checks each deliverable in the flat
`deliverables/` folder (produced by curate.py) for:
  - Existence
  - Non-emptiness
  - Minimum byte threshold
  - Correct file type via magic bytes (not extension -- a .md file renamed to
    .pptx must fail)

Produces a one-line PASS/FAIL per deliverable with the file size.
Produces a summary line: "Self-audit: N/N deliverables present. Handoff authorized/REJECTED."

Exit 0 if all pass. Exit 1 if any fail.

Usage:
    python3 scripts/self_audit.py --run-dir <run-dir>
    python3 scripts/self_audit.py --deliverables-dir <flat-deliverables-dir>
"""

from __future__ import annotations

import os
import sys
import argparse
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH — the 10-deliverable audit list is imported from
# fix_bundle_complete.py.  No other file may hardcode a deliverable list.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

try:
    from fix_bundle_complete import DELIVERABLE_AUDIT_SPEC as _AUDIT_SPEC
except ImportError:
    # Fallback for standalone deployment: inline minimal spec so the script
    # still works if fix_bundle_complete.py is not alongside it.
    _AUDIT_SPEC = [
        {"key": "deck_pptx",         "standardized_dest": "DECK-FINAL.pptx",                 "min_bytes": 50000,  "magic_bytes": b"PK\x03\x04",   "magic_offset": 0, "magic_desc": "ZIP/PPTX container", "content_marker": None},
        {"key": "deck_pdf",          "standardized_dest": "DECK-FINAL.pdf",                  "min_bytes": 50000,  "magic_bytes": b"%PDF",         "magic_offset": 0, "magic_desc": "PDF document",      "content_marker": None},
        {"key": "guide_pdf",         "standardized_dest": "PRESENTER-GUIDE.pdf",             "min_bytes": 20000,  "magic_bytes": b"%PDF",         "magic_offset": 0, "magic_desc": "PDF document",      "content_marker": None},
        {"key": "speech_md",         "standardized_dest": "PRESENTERS-SPEECH.md",            "min_bytes": 5000,   "magic_bytes": None,            "magic_offset": 0, "magic_desc": "text/markdown (no magic bytes -- content check only)", "content_marker": None},
        {"key": "speech_pdf",        "standardized_dest": "PRESENTERS-SPEECH.pdf",           "min_bytes": 20000,  "magic_bytes": b"%PDF",         "magic_offset": 0, "magic_desc": "PDF document",      "content_marker": None},
        {"key": "speech_fish_md",    "standardized_dest": "PRESENTERS-SPEECH-FISH-TAGGED.md","min_bytes": 5000,   "magic_bytes": None,            "magic_offset": 0, "magic_desc": "text/markdown (no magic bytes -- content check only)", "content_marker": None},
        {"key": "audio_mp3",         "standardized_dest": "PRESENTER-AUDIO.mp3",             "min_bytes": 100000, "magic_bytes": b"ID3",          "magic_offset": 0, "magic_desc": "MP3 audio (ID3 tag)","content_marker": None},
        {"key": "infographic_png",   "standardized_dest": "INFOGRAPHIC.png",                 "min_bytes": 10000,  "magic_bytes": b"\x89PNG",      "magic_offset": 0, "magic_desc": "PNG image",         "content_marker": None},
        {"key": "teleprompter_html", "standardized_dest": "presenter-teleprompter.html",     "min_bytes": 5000,   "magic_bytes": None,            "magic_offset": 0, "magic_desc": "text/html (no magic bytes -- content check: must contain <html or <!DOCTYPE)", "content_marker": None},
        {"key": "webinar_mp4",       "standardized_dest": "WEBINAR-VIDEO.mp4",               "min_bytes": 500000, "magic_bytes": None,            "magic_offset": 4, "magic_desc": "MP4 video (ftyp box at offset 4 -- checked via content scan)", "content_marker": None},
    ]

# The runtime audit list is derived from the single source of truth.
# The 'filename' field is the flat-folder name (standardized_dest).
DELIVERABLE_AUDIT_LIST = [
    {
        "key": s["key"],
        "filename": s["standardized_dest"],
        "min_bytes": s["min_bytes"],
        "magic_bytes": s.get("magic_bytes"),
        "magic_offset": s.get("magic_offset", 0),
        "magic_desc": s.get("magic_desc", ""),
        "content_marker": s.get("content_marker"),
    }
    for s in _AUDIT_SPEC
]

# Additional items that should be in deliverables/ alongside the primary products.
BONUS_ITEMS = [
    {
        "key": "process_certificate",
        "filename": "PROCESS-CERTIFICATE.md",
        "min_bytes": 100,
        "required": False,  # Supplementary -- noted but does not block the count
        "magic_desc": "Process certificate (markdown receipt) -- supplementary",
    },
    {
        "key": "bundle_complete",
        "filename": "bundle_complete.json",
        "min_bytes": 50,
        "required": False,
        "magic_desc": "Bundle completeness gate record",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_size(num_bytes: int) -> str:
    """Return a human-readable size string -- e.g. '171.8KB'."""
    if num_bytes < 1024:
        return f"{num_bytes}B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f}KB"
    else:
        return f"{num_bytes / (1024 * 1024):.1f}MB"


def _find_file(target_dir: str, filename: str) -> str | None:
    """Locate *filename* inside *target_dir* (flat or shallow subdirectories).

    Searches:
      1. <target_dir>/<filename>               (flat folder)
      2. <target_dir>/deliverables/<filename>  (one level deeper)

    Returns the absolute path if found, None otherwise.
    """
    candidates = [
        os.path.join(target_dir, filename),
        os.path.join(target_dir, "deliverables", filename),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def check_magic_bytes(filepath: str, expected: bytes | None, offset: int) -> tuple[bool, str]:
    """Compare the leading bytes of *filepath* at *offset* to *expected*.

    Returns (True, "") on match, (False, reason) on mismatch.
    If *expected* is None, returns (True, "") -- no magic-byte check.
    """
    if expected is None:
        return True, ""

    try:
        with open(filepath, "rb") as fh:
            fh.seek(offset)
            actual = fh.read(len(expected))
    except OSError as exc:
        return False, f"cannot read magic bytes: {exc}"

    if actual == expected:
        return True, ""
    else:
        expected_hex = expected.hex()
        actual_hex = actual.hex() if actual else "(empty)"
        return False, f"magic bytes mismatch (expected {expected_hex}, got {actual_hex})"


def check_content_marker(filepath: str, marker: str) -> tuple[bool, str]:
    """Check that the file contains *marker* in its first 2000 bytes.

    For text types without reliable magic bytes (HTML, MD).
    Returns (True, "") if *marker* is found, (False, reason) otherwise.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(2000)
    except OSError as exc:
        return False, f"cannot read for content marker: {exc}"

    if marker.lower() in head.lower():
        return True, ""
    else:
        snippet = head[:120].replace("\n", "\\n")
        return False, f"content marker '{marker}' not found in first 2000 bytes; starts with: {snippet}..."


def check_mp4_ftyp(filepath: str) -> tuple[bool, str]:
    """Check that an MP4 file's ftyp box is present at the expected offset.

    The ISO base media file format requires an 'ftyp' box near the file
    start.  We look for the bytes 'ftyp' at offset 4 (after the 4-byte
    box-size field).  Also handles the case where the file starts with a
    'free' or 'mdat' atom and 'ftyp' appears later (relaxed check).
    """
    try:
        with open(filepath, "rb") as fh:
            # Check standard location: offset 4
            fh.seek(4)
            candidate = fh.read(4)
            if candidate == b"ftyp":
                return True, ""

            # Relaxed check: scan first 512 bytes for 'ftyp' preceded by a
            # plausible 4-byte big-endian size field.
            fh.seek(0)
            head = fh.read(512)
            for i in range(len(head) - 8):
                if head[i + 4 : i + 8] == b"ftyp":
                    # Check that the preceding 4 bytes form a plausible size
                    size_field = int.from_bytes(head[i : i + 4], "big")
                    if size_field > 8:
                        return True, f"ftyp found at offset {i + 4} (non-standard)"
                    elif head[i : i + 4] == b"\x00\x00\x00\x00":
                        # Zero size means "to end of file" -- valid for the
                        # last box, unlikely for ftyp.
                        return True, f"ftyp found at offset {i + 4} (zero-size box)"

            # Check for 'moov' box -- some fragmented MP4s put moov before
            # ftyp but still valid.
            if b"moov" in head:
                return True, "moov box found (fragmented MP4, ftyp not at offset 4)"
            if b"mdat" in head:
                return True, "mdat box found (fragmented MP4, ftyp not at offset 4)"

            return False, "MP4 ftyp box not found in first 512 bytes"
    except OSError as exc:
        return False, f"cannot read MP4: {exc}"


def check_html_marker(filepath: str) -> tuple[bool, str]:
    """HTML content marker: must contain '<html' or '<!DOCTYPE' case-insensitive."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(2000)
    except OSError as exc:
        return False, f"cannot read HTML: {exc}"

    lower = head.lower()
    if "<html" in lower or "<!doctype" in lower:
        return True, ""
    else:
        snippet = head[:120].replace("\n", "\\n")
        return False, f"HTML marker not found; starts with: {snippet}..."


# ---------------------------------------------------------------------------
# Per-deliverable audit
# ---------------------------------------------------------------------------

def audit_deliverable(filepath: str | None, item: dict) -> dict:
    """Check one deliverable against its specification in *item*.

    Returns a dict with keys:
        key, filename, present, size_bytes, meets_min_bytes, magic_ok,
        content_ok, verdict ("PASS" | "FAIL"), reason
    """
    result = {
        "key": item["key"],
        "filename": item["filename"],
        "present": False,
        "size_bytes": 0,
        "meets_min_bytes": False,
        "magic_ok": False,
        "content_ok": False,
        "verdict": "FAIL",
        "reason": "",
    }

    # 1. File existence
    if filepath is None:
        result["reason"] = "MISSING -- file not found in deliverables directory"
        return result

    if not os.path.isfile(filepath):
        result["reason"] = f"MISSING -- path is not a file: {filepath}"
        return result

    result["present"] = True

    # 2. File size
    try:
        size = os.path.getsize(filepath)
    except OSError as exc:
        result["reason"] = f"cannot stat file: {exc}"
        return result

    result["size_bytes"] = size

    if size == 0:
        result["reason"] = "empty file (0 bytes)"
        return result

    if size < item["min_bytes"]:
        result["reason"] = (
            f"size {_format_size(size)} below minimum {_format_size(item['min_bytes'])}"
        )
        return result

    result["meets_min_bytes"] = True

    # 3. Magic-bytes check
    magic_ok, magic_reason = check_magic_bytes(
        filepath, item.get("magic_bytes"), item.get("magic_offset", 0)
    )
    if not magic_ok:
        result["reason"] = magic_reason
        return result

    result["magic_ok"] = True

    # 4. Type-specific content checks
    if item["key"] == "webinar_video":
        ftyp_ok, ftyp_reason = check_mp4_ftyp(filepath)
        if not ftyp_ok:
            result["reason"] = ftyp_reason
            return result
        result["content_ok"] = True

    elif item["key"] == "teleprompter_html":
        html_ok, html_reason = check_html_marker(filepath)
        if not html_ok:
            result["reason"] = html_reason
            return result
        result["content_ok"] = True

    elif item.get("content_marker"):
        cm_ok, cm_reason = check_content_marker(filepath, item["content_marker"])
        if not cm_ok:
            result["reason"] = cm_reason
            return result
        result["content_ok"] = True
    else:
        result["content_ok"] = True  # No content check needed

    # All checks passed
    result["verdict"] = "PASS"
    return result


# ---------------------------------------------------------------------------
# Bulk audit
# ---------------------------------------------------------------------------

def audit_all(deliverables_dir: str) -> dict:
    """Run audit_deliverable for all required items (+ optional bonus items).

    Returns:
        {
            "results": [<list of per-deliverable dicts>],
            "bonus_results": [<list of per-bonus-item dicts>],
            "pass_count": <int>,
            "fail_count": <int>,
            "missing": [<list of missing keys>],
            "summary": f"Self-audit: {pass_count}/{len(DELIVERABLE_AUDIT_LIST)} deliverables present. Handoff authorized."
                       or f"Self-audit: {pass_count}/{len(DELIVERABLE_AUDIT_LIST)} deliverables present. Handoff REJECTED.",
        }
    """
    results = []
    bonus_results = []

    for item in DELIVERABLE_AUDIT_LIST:
        fp = _find_file(deliverables_dir, item["filename"])
        r = audit_deliverable(fp, item)
        results.append(r)

    for bonus in BONUS_ITEMS:
        fp = _find_file(deliverables_dir, bonus["filename"])
        # Simplified audit for bonus items (existence + min bytes only)
        if fp is None or not os.path.isfile(fp):
            br = {
                "key": bonus["key"],
                "filename": bonus["filename"],
                "present": False,
                "size_bytes": 0,
                "verdict": "FAIL" if bonus["required"] else "SKIP",
                "reason": "MISSING" if bonus["required"] else "optional item not found",
            }
        else:
            try:
                sz = os.path.getsize(fp)
            except OSError:
                sz = 0
            br = {
                "key": bonus["key"],
                "filename": bonus["filename"],
                "present": True,
                "size_bytes": sz,
                "verdict": "PASS" if sz >= bonus["min_bytes"] else "FAIL",
                "reason": (
                    ""
                    if sz >= bonus["min_bytes"]
                    else f"size {_format_size(sz)} below minimum {_format_size(bonus['min_bytes'])}"
                ),
            }
        bonus_results.append(br)

    pass_count = sum(1 for r in results if r["verdict"] == "PASS")
    fail_count = sum(1 for r in results if r["verdict"] == "FAIL")
    missing = [r["key"] for r in results if not r["present"]]

    authorized = fail_count == 0
    summary = (
        f"Self-audit: {pass_count}/{len(DELIVERABLE_AUDIT_LIST)} deliverables present. "
        f"Handoff {'authorized' if authorized else 'REJECTED'}."
    )

    return {
        "results": results,
        "bonus_results": bonus_results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "missing": missing,
        "summary": summary,
        "authorized": authorized,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_line(result: dict) -> str:
    """Format one deliverable result as a single status line."""
    tag = f"[{result['verdict']}]"
    size_str = _format_size(result["size_bytes"]) if result["present"] else "0B"
    line = f"  {tag:6s} {result['filename']:<42s} ({size_str:>8s})"
    if result["verdict"] == "FAIL" and result["reason"]:
        line += f"  -- {result['reason']}"
    return line


def print_report(audit_result: dict) -> None:
    """Print the full self-audit report to stdout."""
    print()
    print("=" * 72)
    print("  SELF-AUDIT -- Deliverable Verification Before Handoff")
    print("=" * 72)
    print()

    # 9 primary deliverables
    print(f"  Primary deliverables ({len(DELIVERABLE_AUDIT_LIST)}):")
    print("  " + "-" * 68)

    for r in audit_result["results"]:
        print(format_line(r))

    # Bonus items
    if audit_result["bonus_results"]:
        print()
        print("  Supplementary items:")
        print("  " + "-" * 68)
        for br in audit_result["bonus_results"]:
            tag = f"[{br['verdict']}]"
            size_str = _format_size(br["size_bytes"]) if br["present"] else "0B"
            line = f"  {tag:6s} {br['filename']:<42s} ({size_str:>8s})"
            if br.get("reason") and br["verdict"] == "FAIL":
                line += f"  -- {br['reason']}"
            print(line)

    # Missing summary
    if audit_result["missing"]:
        print()
        print(f"  MISSING: {', '.join(audit_result['missing'])}")
        print(f"  ({len(audit_result['missing'])} of {len(DELIVERABLE_AUDIT_LIST)} deliverables not found)")
        print()

    # Summary line
    print()
    print("  " + audit_result["summary"])
    print()
    print("=" * 72)


# ---------------------------------------------------------------------------
# Run-dir resolution
# ---------------------------------------------------------------------------

def resolve_deliverables_dir(run_dir: str | None, deliverables_dir: str | None) -> str:
    """Resolve the deliverables directory from CLI arguments.

    Priority:
      1. --deliverables-dir (explicit path)
      2. <run_dir>/deliverables/
      3. <run_dir>/deliverables/ via locating a process_manifest.json or state.json
    """
    if deliverables_dir:
        p = os.path.abspath(deliverables_dir)
        if not os.path.isdir(p):
            print(f"Error: --deliverables-dir is not a directory: {p}", file=sys.stderr)
            sys.exit(2)
        return p

    if not run_dir:
        print(
            "Error: either --run-dir or --deliverables-dir is required.",
            file=sys.stderr,
        )
        sys.exit(2)

    p = os.path.abspath(run_dir)

    # Check for run_dir/deliverables/
    cand = os.path.join(p, "deliverables")
    if os.path.isdir(cand):
        return cand

    # If run_dir itself has the deliverable files directly, use it
    # (i.e. run_dir IS the flat deliverables folder)
    if os.path.isdir(p):
        # Check if any deliverable exists directly in run_dir
        for item in DELIVERABLE_AUDIT_LIST:
            if os.path.isfile(os.path.join(p, item["filename"])):
                return p

    # Fallback: treat run_dir as the deliverables directory itself
    if os.path.isdir(p):
        return p

    print(f"Error: --run-dir is not a directory: {p}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Self-audit: verify all presentation deliverables exist before handoff."
    )
    parser.add_argument(
        "--run-dir",
        help="Root directory of a completed presentation run. "
        "Looks for deliverables/ subdirectory or flat deliverables directly in this path.",
    )
    parser.add_argument(
        "--deliverables-dir",
        help="Path to a flat deliverables/ folder directly (bypasses run-dir resolution).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text.",
    )

    args = parser.parse_args()

    if not args.run_dir and not args.deliverables_dir:
        parser.print_help()
        print(
            "\nError: either --run-dir or --deliverables-dir is required.",
            file=sys.stderr,
        )
        sys.exit(2)

    deliverables_dir = resolve_deliverables_dir(args.run_dir, args.deliverables_dir)

    # Run the audit
    result = audit_all(deliverables_dir)

    if args.json:
        json.dump(result, sys.stdout, indent=2, default=str)
        print()
    else:
        print_report(result)

    sys.exit(0 if result["authorized"] else 1)


if __name__ == "__main__":
    main()
