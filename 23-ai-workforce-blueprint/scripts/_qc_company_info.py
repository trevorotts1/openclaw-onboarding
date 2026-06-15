#!/usr/bin/env python3
# _qc_company_info.py — extracted from qc-completeness.sh COMPANY_INFO heredoc.
#
# Externalized v11.18.4 for stock-macOS bash 3.2.57 compatibility: bash 3.2
# mis-parses python-in-$() heredocs (counts quotes inside the command
# substitution -> "unexpected EOF while looking for matching \"" at parse time,
# aborting the whole script). Logic is byte-equivalent to the former inline
# heredoc. Reads SCRIPT_DIR / OPENCLAW_COMPANY_SLUG from the environment
# (exported by qc-completeness.sh), prints the company-info JSON to stdout.
#
# v12.9.4 FIX (fix/gate-company-dir-resolution):
#   BEFORE: the sys.path.insert loop inserted lib/ first (loop order) but each
#   successive insert(0,...) pushes the previous to position 1, so the LAST item
#   in the loop ends up at position 0 (highest priority). script_dir was last,
#   then skill_dir/shared-utils, then skill_dir.parent.parent/shared-utils —
#   so shared-utils/detect_platform.py loaded instead of lib/detect_platform.py.
#   The shared-utils version (PRD 1.9) sets
#       company_root = master_files / "zero-human-company"
#   which on Mac resolves to
#       ~/Downloads/openclaw-master-files/zero-human-company
#   — the TEMPLATE dir, not the real workforce. That template path then appeared
#   FIRST in parent_candidates (as paths.get("company_root")), and if the
#   template dir contained any subdirectories (template company folders), the
#   subdir scan picked them and broke out early — NEVER reaching the real
#   workforce at ~/clawd/zero-human-company. Result: every Mac box with a built
#   workforce exited NO_WORKFORCE_FOUND and the gate silently short-circuited.
#
#   FIX (three parts):
#     1. Reorder sys.path.insert so lib/detect_platform.py has highest priority
#        (it maps company_root correctly to ~/clawd/zero-human-company on Mac).
#     2. Reorder parent_candidates to put REAL workforce locations FIRST,
#        template/master-files locations LAST, and guard every candidate with
#        _is_template_path() so a Downloads path can never win over a real one.
#     3. Fail-loud guard: if resolution returns no zhc_root but a known real
#        workforce root exists on disk, emit a "gate_bug" error key so
#        qc-completeness.sh can log the failure loudly rather than silently
#        exiting NO_WORKFORCE_FOUND (which looks like "no workforce" to the
#        operator, hiding the resolver regression).
import json, os, sys
from pathlib import Path

script_dir = Path(os.environ.get("SCRIPT_DIR", ".")).resolve()
skill_dir = script_dir.parent.resolve()

# v12.9.4: fix sys.path priority so lib/detect_platform.py (which has the
# correct legacy Mac clawd paths) is imported instead of shared-utils/.
# sys.path.insert(0, x) pushes x to position 0; the LAST insert call wins.
# Insert lib/ LAST so it lands at position 0 = highest priority.
for p in (skill_dir.parent.parent / "shared-utils",
          skill_dir / "shared-utils",
          script_dir,
          skill_dir / "lib"):   # inserted last -> position 0 -> highest priority
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

# v12.9.4: guard — return True if a path lives inside the master-files /
# Downloads template tree.  A path inside that tree is NEVER a real built
# workforce: it is the shipped template that qc-completeness should NEVER scan.
def _is_template_path(p: Path) -> bool:
    """Return True if p resolves into the master-files / Downloads template tree."""
    try:
        parts = Path(p).resolve().parts
        return "openclaw-master-files" in parts
    except Exception:
        return False

zhc_root = None

# Priority 1: detect_platform's already-resolved active company dir.
# Reject if the resolved path is inside the template tree.
company_dir = paths.get("company_dir")
if company_dir:
    cdp = Path(company_dir).resolve()
    if cdp.is_dir() and not _is_template_path(cdp):
        zhc_root = str(cdp)

# Priority 2: scan well-known candidate paths (follow symlinks).
# v12.9.4: REAL workforce locations come FIRST; template/fallback paths LAST.
# Previously paths.get("company_root") (the Downloads template) appeared first
# and the scan broke out early on template subdirectories.
if not zhc_root:
    slug = os.environ.get("OPENCLAW_COMPANY_SLUG", "")

    # Slug-specific candidates (real locations only).
    candidates = []
    if slug:
        candidates += [
            Path("/data/.openclaw/workspace/zero-human-company") / slug,
            Path("/data/clawd/zero-human-company") / slug,
            Path.home() / "clawd" / "zero-human-company" / slug,
            Path.home() / ".openclaw" / "workspace" / "zero-human-company" / slug,
        ]

    # Parent-dir scan — REAL roots first, then template root as final fallback.
    # paths.get("company_root") from shared-utils/detect_platform.py (PRD 1.9)
    # is master_files/zero-human-company on Mac — a template path.  It is kept
    # as a last resort only and is filtered by _is_template_path().
    parent_candidates = [
        # VPS real paths
        Path("/data/.openclaw/workspace/zero-human-company"),
        Path("/data/.openclaw/workspace/departments"),
        Path("/data/clawd/zero-human-company"),
        # Mac real paths (legacy + new install)
        Path.home() / "clawd" / "zero-human-company",
        Path.home() / ".openclaw" / "workspace" / "zero-human-company",
        # detect_platform company_root — may be the Downloads template when
        # shared-utils/detect_platform.py (PRD 1.9) is in effect.  Placed last
        # and guarded by _is_template_path() so it can never shadow real paths.
        paths.get("company_root"),
    ]

    for cand in candidates:
        if cand:
            cp = Path(cand).resolve()
            if cp.is_dir() and not _is_template_path(cp):
                zhc_root = str(cp)
                break

    if not zhc_root:
        for parent in parent_candidates:
            if not parent:
                continue
            p = Path(parent).resolve()
            # v12.9.4: skip template/master-files paths entirely.
            if _is_template_path(p):
                continue
            # If the candidate IS the departments dir directly (non-standard layout)
            if p.is_dir() and (p / "departments").resolve().is_dir():
                zhc_root = str(p)
                break
            # Scan for per-company subdirs (most-recently-modified wins)
            if p.is_dir():
                subdirs = sorted(
                    (d for d in p.iterdir()
                     if d.is_dir() and not d.name.startswith(("_", "."))),
                    key=lambda d: d.stat().st_mtime, reverse=True
                )
                if subdirs:
                    zhc_root = str(subdirs[0].resolve())
                    break

# v12.9.4 FAIL-LOUD GUARD: if resolution returned no zhc_root, check whether
# a known real workforce root exists on disk.  If one does, the failure is a
# resolver BUG — emit a gate_bug error key so qc-completeness.sh logs it
# loudly instead of silently short-circuiting with exit code 4
# (NO_WORKFORCE_FOUND), which the operator reads as "no workforce built yet".
if not zhc_root:
    real_roots = [
        Path("/data/.openclaw/workspace/zero-human-company"),
        Path("/data/clawd/zero-human-company"),
        Path.home() / "clawd" / "zero-human-company",
        Path.home() / ".openclaw" / "workspace" / "zero-human-company",
    ]
    existing_real = [str(r) for r in real_roots if r.is_dir()]
    if existing_real:
        print(json.dumps({
            "error": (
                "GATE_BUG: company-dir resolution returned no result but real "
                "workforce root(s) exist on disk: "
                + ", ".join(existing_real)
                + ". This is a resolver bug, not a missing workforce. "
                "Check detect_platform paths and parent_candidates order."
            ),
            "gate_bug": True,
            "existing_real_roots": existing_real,
            "company_root": None,
            "departments_dir": None,
            "departments_json": None,
        }))
        sys.exit(0)

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
