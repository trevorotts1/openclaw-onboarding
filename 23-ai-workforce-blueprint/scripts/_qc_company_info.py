#!/usr/bin/env python3
# _qc_company_info.py — extracted from qc-completeness.sh COMPANY_INFO heredoc.
#
# Externalized v11.18.4 for stock-macOS bash 3.2.57 compatibility: bash 3.2
# mis-parses python-in-$() heredocs (counts quotes inside the command
# substitution -> "unexpected EOF while looking for matching \"" at parse time,
# aborting the whole script). Logic is byte-equivalent to the former inline
# heredoc. Reads SCRIPT_DIR / OPENCLAW_COMPANY_SLUG from the environment
# (exported by qc-completeness.sh), prints the company-info JSON to stdout.
import json, os, sys
from pathlib import Path

script_dir = Path(os.environ.get("SCRIPT_DIR", ".")).resolve()
skill_dir = script_dir.parent.resolve()
# Mirror the sys.path setup from post-build-role-workspaces.py
for p in (skill_dir / "lib",
          skill_dir.parent.parent / "shared-utils",
          skill_dir / "shared-utils",
          script_dir):
    sys.path.insert(0, str(p))

try:
    from detect_platform import get_openclaw_paths
except ImportError as e:
    print(json.dumps({"error": f"detect_platform import failed: {e}"}))
    sys.exit(0)

try:
    paths = get_openclaw_paths()
except Exception as e:
    print(json.dumps({"error": f"detect_platform: {e}"}))
    sys.exit(0)

# "company_dir" is the resolved active company slug dir (same key post-build uses).
# "company_root" is the parent zero-human-company/ dir.
# Previous code looked for non-existent keys "active_zhc_company"/"zhc_company_root".
zhc_root = None

# Priority 1: detect_platform's already-resolved active company dir
company_dir = paths.get("company_dir")
if company_dir and Path(company_dir).resolve().is_dir():
    zhc_root = str(Path(company_dir).resolve())

# Priority 2: scan well-known candidate paths (follow symlinks)
if not zhc_root:
    slug = os.environ.get("OPENCLAW_COMPANY_SLUG", "")
    candidates = []
    if slug:
        candidates += [
            Path("/data/.openclaw/workspace/zero-human-company") / slug,
            Path.home() / ".openclaw" / "workspace" / "zero-human-company" / slug,
            Path("/data/clawd/zero-human-company") / slug,
            Path.home() / "clawd" / "zero-human-company" / slug,
        ]
    # Also scan parent dirs and pick the most-recently-modified child
    parent_candidates = [
        paths.get("company_root"),
        Path("/data/.openclaw/workspace/zero-human-company"),
        Path("/data/.openclaw/workspace/departments"),
        Path("/data/clawd/zero-human-company"),
        Path.home() / ".openclaw" / "workspace" / "zero-human-company",
        Path.home() / "clawd" / "zero-human-company",
    ]
    for cand in candidates:
        if cand and Path(cand).resolve().is_dir():
            zhc_root = str(Path(cand).resolve())
            break
    if not zhc_root:
        for parent in parent_candidates:
            if not parent:
                continue
            p = Path(parent).resolve()
            # If the candidate IS the departments dir directly (non-standard layout)
            if p.is_dir() and (p / "departments").resolve().is_dir():
                zhc_root = str(p)
                break
            # Scan for per-company subdirs
            if p.is_dir():
                subdirs = sorted(
                    (d for d in p.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))),
                    key=lambda d: d.stat().st_mtime, reverse=True
                )
                if subdirs:
                    zhc_root = str(subdirs[0].resolve())
                    break

# Resolve departments dir — follow symlinks
departments_dir = None
departments_json = None
if zhc_root:
    # Standard layout: <company_root>/departments/
    dept_candidate = Path(zhc_root) / "departments"
    if dept_candidate.resolve().is_dir():
        departments_dir = str(dept_candidate.resolve())
        departments_json = str(Path(zhc_root) / "departments.json")
    else:
        # Non-standard: zhc_root itself may be the departments dir
        if Path(zhc_root).resolve().is_dir():
            # Check if it contains role-like subdirs directly
            departments_dir = str(Path(zhc_root).resolve())
            departments_json = str(Path(zhc_root).parent / "departments.json")

print(json.dumps({
    "company_root": zhc_root,
    "departments_dir": departments_dir,
    "departments_json": departments_json,
}))
