#!/usr/bin/env python3
"""
sop-boundary-gate.py — PRD 2.12 canonical-library boundary guard.

PURPOSE
-------
Protects token economics by ensuring canonical departments ALWAYS resolve
their SOPs from the 233-template role/SOP library (copy + token-personalise)
and NEVER enter the LLM authoring path.

A "canonical department" is any department whose role templates exist in the
  23-ai-workforce-blueprint/templates/role-library/
tree.  That tree IS the 233-template library and is the single source of
truth for canonicity.  Mandatory/universal-primary status from
department-naming-map.json is NOT required here — if the library has
templates for a dept, the copy path is cheaper and deterministic, so
authoring is refused for it.

BOUNDARY RULE (hard — token-economics gate):
  1. REFUSE authoring  — if a dept_id resolves to the canonical library,
     populate-sops-from-manifest.py MUST NOT author SOPs for it.  It MUST
     copy from the library instead (via _instantiate_role_from_library in
     build-workforce.py).  The authoring path raises CanonicalDeptAuthError
     when called for a canonical dept.
  2. BUILD GATE assertion — verify-library-gate.sh calls
     assert_no_canonical_in_authoring_path(manifest_path) and exits rc=7
     when a canonical dept is found in the authoring manifest.

USAGE (import)
--------------
  from sop_boundary_gate import (
      CANONICAL_LIBRARY_DEPT_IDS,
      is_canonical_dept,
      refuse_if_canonical,
      assert_no_canonical_in_authoring_path,
      classify_manifest_depts,
  )

USAGE (CLI)
-----------
  python3 sop-boundary-gate.py --check-dept marketing
  python3 sop-boundary-gate.py --check-manifest /path/to/sop-research-manifest.json
  python3 sop-boundary-gate.py --list-canonical

EXIT CODES (CLI)
  0  all checks pass (or informational list)
  1  argument error
  7  boundary violation found (canonical dept in authoring path)

Import-safe: all heavy work is inside functions; the module-level
CANONICAL_LIBRARY_DEPT_IDS constant is computed once at import time from the
role-library directory tree (never from a hard-coded list, so it stays in sync
automatically as the library grows).

Read-only. Never writes. Idempotent.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ── canonical library path ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ROLE_LIBRARY_DIR = SKILL_DIR / "templates" / "role-library"

# Skip-list: dirs inside role-library that are not operational dept templates.
_LIBRARY_SKIP_DIRS = frozenset({"_stage1_drafts", "master-orchestrator"})

# ── CANONICAL_LIBRARY_DEPT_IDS ────────────────────────────────────────────────
# Computed at import time from the role-library directory tree.  Any directory
# that:
#   - is a direct child of ROLE_LIBRARY_DIR
#   - is a real directory
#   - does NOT start with "_"
#   - is NOT in _LIBRARY_SKIP_DIRS
# is a canonical library department.
def _load_canonical_library_dept_ids() -> frozenset:
    """Return frozenset of canonical dept IDs from the role-library tree."""
    if not ROLE_LIBRARY_DIR.is_dir():
        print(
            f"[SOP-BOUNDARY-GATE] WARNING: role-library directory not found at "
            f"{ROLE_LIBRARY_DIR} — cannot determine canonical depts; boundary gate "
            f"is DISABLED (unsafe: authoring may proceed unchecked).",
            file=sys.stderr,
        )
        return frozenset()
    ids = set()
    for child in ROLE_LIBRARY_DIR.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        if child.name in _LIBRARY_SKIP_DIRS:
            continue
        ids.add(child.name)
    return frozenset(ids)


CANONICAL_LIBRARY_DEPT_IDS: frozenset = _load_canonical_library_dept_ids()

# Alias map: some clients store a canonical dept under a variant slug.
# Mirrors build-workforce.CANONICAL_VARIANT_SLUGS + CANONICAL_ID_ALIASES.
# The boundary check normalises via this map before lookup.
_CANONICAL_ALIASES: dict = {
    "billing-finance": "billing",
    "billing_finance": "billing",
    "legal": "legal-compliance",
    "legal-compliance": "legal-compliance",
    "customer-service": "customer-support",
    "cust-support": "customer-support",
    "support-service": "customer-support",
}


def _normalise_dept_id(dept_id: str) -> str:
    """
    Normalise a dept_id for canonical lookup.
    Strips 'dept-' prefix / '-dept' suffix, lowercases, maps known aliases.
    """
    if not dept_id or not isinstance(dept_id, str):
        return ""
    s = dept_id.strip().lower()
    if s.startswith("dept-"):
        s = s[5:]
    if s.endswith("-dept"):
        s = s[:-5]
    return _CANONICAL_ALIASES.get(s, s)


# ── PUBLIC API ────────────────────────────────────────────────────────────────

class CanonicalDeptAuthError(RuntimeError):
    """
    Raised when the authoring path is invoked for a canonical library dept.

    Authoring canonical-dept SOPs burns tokens on work already done and stored
    in the pre-written library.  Token economics mandate: COPY, don't AUTHOR.
    """
    pass


def is_canonical_dept(dept_id: str) -> bool:
    """
    Return True if dept_id maps to a canonical library department.

    A dept is canonical when its (alias-normalised) id is present in
    CANONICAL_LIBRARY_DEPT_IDS.  This is the single-source-of-truth check —
    no hard-coded list, just the role-library directory tree.
    """
    if not CANONICAL_LIBRARY_DEPT_IDS:
        # Library not found at import time — gate is disabled (loud warning
        # already printed; let the call succeed rather than silently break builds).
        return False
    return _normalise_dept_id(dept_id) in CANONICAL_LIBRARY_DEPT_IDS


def refuse_if_canonical(dept_id: str, role_name: str = "") -> None:
    """
    Raise CanonicalDeptAuthError if dept_id is canonical.

    Call this at the start of any SOP authoring path (populate-sops, inline
    queue writer, sub-agent spawn for a specific dept) BEFORE doing any LLM
    work.  The exception message carries the loud reason and copy instruction.

    Args:
        dept_id:   Department identifier.
        role_name: Optional role name for richer error context.
    """
    if is_canonical_dept(dept_id):
        norm = _normalise_dept_id(dept_id)
        lib_path = ROLE_LIBRARY_DIR / norm
        role_clause = f" (role: {role_name})" if role_name else ""
        raise CanonicalDeptAuthError(
            f"[SOP-BOUNDARY-GATE] REFUSE authoring for canonical dept '{dept_id}'{role_clause}. "
            f"Pre-written templates exist at {lib_path}. "
            f"CORRECT ACTION: copy + token-personalise via "
            f"_instantiate_role_from_library(role_name, '{dept_id}', interview_answers) "
            f"in build-workforce.py — do NOT run LLM authoring on canonical work. "
            f"Token economics gate: canonical SOPs are pre-written precisely to avoid "
            f"burning tokens on standard work."
        )


def classify_manifest_depts(manifest_path) -> dict:
    """
    Classify every department in a sop-research-manifest.json as canonical or custom.

    Returns a dict:
      {
        "canonical": [{"dept_id": ..., "norm_id": ..., "sop_file_count": ...}, ...],
        "custom":    [{"dept_id": ..., "norm_id": ..., "sop_file_count": ...}, ...],
        "violation": bool,   # True when any canonical dept is present in the manifest
        "violation_reason": str,
      }

    A canonical dept appearing in the manifest is a boundary violation because
    the manifest is the input to the authoring path (populate-sops-from-manifest.py).
    If any canonical dept is present, it means build-workforce.py failed to copy
    from the library and instead queued it for LLM authoring — that is the bug
    this gate catches.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return {
            "canonical": [],
            "custom": [],
            "violation": False,
            "violation_reason": f"manifest not found at {manifest_path}",
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "canonical": [],
            "custom": [],
            "violation": False,
            "violation_reason": f"manifest JSON parse error: {e}",
        }

    depts = manifest.get("departments", [])
    canonical = []
    custom = []
    for entry in depts:
        dept_id = entry.get("dept_id", "")
        norm_id = _normalise_dept_id(dept_id)
        sop_count = len(entry.get("sop_files", []))
        row = {"dept_id": dept_id, "norm_id": norm_id, "sop_file_count": sop_count}
        if is_canonical_dept(dept_id):
            canonical.append(row)
        else:
            custom.append(row)

    violation = bool(canonical)
    violation_reason = ""
    if violation:
        names = ", ".join(d["dept_id"] for d in canonical)
        violation_reason = (
            f"CANONICAL depts in authoring manifest (must COPY, not AUTHOR): {names}. "
            f"Root cause: build-workforce.py failed to instantiate these from the "
            f"role-library before writing the SOP research manifest.  "
            f"Fix: re-run build-workforce.py; it will call _instantiate_role_from_library "
            f"and skip these depts in write_sop_research_manifest()."
        )

    return {
        "canonical": canonical,
        "custom": custom,
        "violation": violation,
        "violation_reason": violation_reason,
    }


def assert_no_canonical_in_authoring_path(manifest_path) -> int:
    """
    Assert that no canonical dept appears in the authoring manifest.

    Prints a LOUD diagnostic if a violation is found.
    Returns 0 on pass, 7 on violation.

    Called by verify-library-gate.sh (via python3 sop-boundary-gate.py
    --check-manifest <path>) and by populate-sops-from-manifest.py
    at startup.
    """
    result = classify_manifest_depts(manifest_path)
    if result["violation"]:
        print(
            f"[SOP-BOUNDARY-GATE] BOUNDARY VIOLATION: {result['violation_reason']}",
            file=sys.stderr,
        )
        print(
            f"[SOP-BOUNDARY-GATE] Canonical depts that must be COPIED instead of authored:",
            file=sys.stderr,
        )
        for d in result["canonical"]:
            norm = d["norm_id"]
            lib_path = ROLE_LIBRARY_DIR / norm
            print(
                f"  - {d['dept_id']} (norm={norm}) | {d['sop_file_count']} SOP stubs queued | "
                f"library path: {lib_path}",
                file=sys.stderr,
            )
        print(
            f"[SOP-BOUNDARY-GATE] Custom depts eligible for authoring: "
            f"{[d['dept_id'] for d in result['custom']]}",
            file=sys.stderr,
        )
        return 7
    if result["custom"]:
        print(
            f"[SOP-BOUNDARY-GATE] PASS: {len(result['custom'])} custom dept(s) eligible for authoring: "
            f"{[d['dept_id'] for d in result['custom']]}",
            file=sys.stderr,
        )
    else:
        print(
            f"[SOP-BOUNDARY-GATE] PASS: manifest has 0 custom depts queued for authoring "
            f"(all depts were canonical and instantiated from the library — correct).",
            file=sys.stderr,
        )
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli(argv):
    parser = argparse.ArgumentParser(
        description="PRD 2.12 SOP boundary gate — canonical-library dept check.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  pass / informational
  1  argument error
  7  boundary violation (canonical dept in authoring path)
""",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check-dept",
        metavar="DEPT_ID",
        help="Check whether a single dept_id is canonical.",
    )
    group.add_argument(
        "--check-manifest",
        metavar="PATH",
        help="Check sop-research-manifest.json for boundary violations.",
    )
    group.add_argument(
        "--list-canonical",
        action="store_true",
        help="List all canonical library dept IDs and exit 0.",
    )
    args = parser.parse_args(argv)

    if args.list_canonical:
        print(f"[SOP-BOUNDARY-GATE] Canonical library depts ({len(CANONICAL_LIBRARY_DEPT_IDS)}):")
        for did in sorted(CANONICAL_LIBRARY_DEPT_IDS):
            lib_path = ROLE_LIBRARY_DIR / did
            print(f"  {did:<35}  {lib_path}")
        return 0

    if args.check_dept:
        dept_id = args.check_dept
        canonical = is_canonical_dept(dept_id)
        norm = _normalise_dept_id(dept_id)
        status = "CANONICAL (copy from library)" if canonical else "CUSTOM (authoring eligible)"
        print(f"[SOP-BOUNDARY-GATE] dept '{dept_id}' (norm='{norm}') → {status}")
        if canonical:
            lib_path = ROLE_LIBRARY_DIR / norm
            print(f"  Library path: {lib_path}")
        return 0

    if args.check_manifest:
        rc = assert_no_canonical_in_authoring_path(args.check_manifest)
        if rc == 0:
            result = classify_manifest_depts(args.check_manifest)
            print(
                f"[SOP-BOUNDARY-GATE] Manifest: {args.check_manifest} | "
                f"canonical={len(result['canonical'])} custom={len(result['custom'])} | PASS"
            )
        return rc

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
