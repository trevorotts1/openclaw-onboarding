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


# ── v20.0.80: THE LIVE TREE — the one the REPAIRER actually maintains ────────
# The floor-fill repair pipeline reads and writes exactly ONE departments tree:
#
#     detect-stale-artifacts.py:326  departments_root = Path(workspace) / "departments"
#     floor-fill-driver.py:170-171   /data/.openclaw/workspace/departments  (VPS/Docker)
#                                    $HOME/.openclaw/workspace/departments  (Mac)
#     migrate-existing-workforce.sh:138-140  FF_WS_ROOT/departments
#
# Every candidate in this resolver was zero-human-company-shaped, so QC NEVER
# considered that tree. On a box whose live tree is <workspace>/departments the
# checker measured a DIFFERENT directory than the repairer wrote to and reported
# floor departments "missing" that were present on disk the whole time — measured
# on 13 of 18 reachable boxes, 10 of which the gate failed outright.
#
# A checker that does not measure the repairer's tree cannot audit the repair, so
# when the live tree exists it IS the tree under audit. The zero-human-company
# candidates below remain the fallback for older boxes that never grew one.
# Both helpers live in _qc_paths.py so this checker, department-floor.py and the
# repair pipeline share ONE definition and can never drift apart again.
# script_dir is already on sys.path (inserted above).
from _qc_paths import live_departments_dir as _live_departments_dir  # noqa: E402
from _qc_paths import looks_like_departments_dir as _looks_like_departments_dir  # noqa: E402

zhc_root = None
departments_dir = None
departments_json = None

# Priority 0: the LIVE tree the repairer maintains. When it exists it wins
# outright — see _live_departments_dir() above.
_live = _live_departments_dir()
if _live.is_dir() and not _is_template_path(_live):
    _live_resolved = _live.resolve()
    _ws = _live_resolved.parent
    zhc_root = str(_ws)
    departments_dir = str(_live_resolved)
    departments_json = str(_ws / "departments.json")

# Priority 1: detect_platform's already-resolved active company dir.
# Reject if the resolved path is inside the template tree.
company_dir = paths.get("company_dir")
if company_dir and not zhc_root:
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
                # v20.0.80: re-apply the template guard to the RESOLVED CHILD.
                # The _is_template_path() check above tests the PARENT only, and
                # this branch resolved the child straight past it: a per-company
                # entry that is a SYMLINK into the Downloads template tree (a
                # real, measured layout on a live box) made QC audit the shipped
                # TEMPLATE instead of the client's own workforce. The v12.9.4
                # header promises "guard every candidate" — this child was the
                # one candidate that was never guarded.
                for d in subdirs:
                    rd = d.resolve()
                    if not _is_template_path(rd):
                        zhc_root = str(rd)
                        break
                if zhc_root:
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

# Resolve departments dir — follow symlinks.
# Skipped entirely when Priority 0 already resolved the live tree.
if zhc_root and not departments_dir:
    # Standard layout: <company_root>/departments/
    dept_candidate = Path(zhc_root) / "departments"
    if dept_candidate.resolve().is_dir():
        departments_dir = str(dept_candidate.resolve())
        departments_json = str(Path(zhc_root) / "departments.json")
    else:
        # Non-standard: zhc_root itself may BE the departments dir — but ONLY
        # when it actually looks like one. v20.0.80: this branch previously
        # assigned unconditionally (the "Check if it contains role-like subdirs
        # directly" comment described a check that was never written), so a
        # company dir with no departments/ became the departments root and the
        # whole floor read as missing. _looks_like_departments_dir() is that
        # missing check. When it says no, we report NO departments dir rather
        # than a wrong one — qc-completeness.sh then exits NO_WORKFORCE_FOUND
        # instead of emitting a fabricated floor verdict over the wrong tree.
        zp = Path(zhc_root).resolve()
        if _looks_like_departments_dir(zp):
            departments_dir = str(zp)
            departments_json = str(zp.parent / "departments.json")

print(json.dumps({
    "company_root": zhc_root,
    "departments_dir": departments_dir,
    "departments_json": departments_json,
}))
