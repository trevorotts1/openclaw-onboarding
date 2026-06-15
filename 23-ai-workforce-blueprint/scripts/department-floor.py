#!/usr/bin/env python3
"""
department-floor.py - the ONE source of truth for the HARD department floor.

FLOOR (computed live from department-naming-map.json v2.6.0): 29 departments =
22 mandatory canonical + 7 universal-primary vertical-pack (one per pack). The
count is ALWAYS derived at runtime from len(HARDCODED_MANDATORY) + the count of
universal-primary pack depts, so no integer is hardcoded as a gate. Below the
floor is only ever reached by an EXPLICIT recorded decline (a mandatory dept, a
universal-primary vertical, or a custom dept the owner declined in Phase 5.5).

WHY THIS EXISTS (the bug it kills):
Clients kept landing with HEAVILY-REDUCED workforces (one client 3 depts, others
3-per-dept / 6-dept / legacy) DESPITE the repo carrying 216 role templates,
the mandatory canonical departments, and 7 industry vertical packs. Diagnosis
found THREE places that trusted the build-state JSON as proof of completion
instead of counting REAL departments on disk:
  1. verify-zhc-standard.sh step-2 read `.departments[]` from the build-state
     JSON, so a hand-seeded 3-dept JSON (a seeded-fiction build-state) reported
     "all canonical present" and passed the floor.
  2. qc-completeness.sh measured per-dept staffing of whatever was ON DISK but
     had NO floor concept at all - 3 well-staffed depts returned PASS.
  3. run-closeout.sh / resume-workforce-build.sh self-completed on JSON
     status=done / closeoutStatus=done with zero disk verification.

THE FIX (this module): compute the EXPECTED floor =
    len(HARDCODED_MANDATORY) mandatory canonical departments
    + len(universal_primary_vertical_departments(...)) universal-primary
      vertical-pack departments (one per pack, marked universal_primary=true in
      department-naming-map.json - these fire for EVERY client regardless of
      industry, giving the universal-primary floor)
    − any department the client EXPLICITLY declined (recorded as an explicit
      decline in build-state canonicalReconciliation.decisions == "no")

    Industry keyword matching STILL adds additional pack departments on top of
    the computed floor, but those extras are not gating - the gate only checks
    for the universal primaries (plus the mandatory set). exit 3 fires when disk
    is below the computed floor or a specific mandatory/universal-primary dept is
    missing. Exit 3 never fires for missing EXTRA (keyword-matched) pack depts -
    those are flavor, not floor.

    NOTE: the computed floor count is ALWAYS derived at runtime from the live
    data (len(HARDCODED_MANDATORY) + count of universal-primary pack depts) so
    the reported number can NEVER drift from what evaluate_floor() enforces.
    No integer floor counts are hardcoded in any human-readable string.

…and then count the REAL department directories ON DISK and FAIL hard when disk
is below the floor or a mandatory/universal-primary dept is missing from disk.
The build-state JSON is NEVER trusted as proof of floor compliance - only disk
is.

Reads the SAME source of truth as build-workforce.py:
    23-ai-workforce-blueprint/department-naming-map.json  (.mandatory + .vertical_packs)

USAGE
  python3 department-floor.py --json            # machine-readable verdict to stdout
  python3 department-floor.py                   # human summary to stderr
EXIT CODES
  0  floor met (all mandatory(−declines) + all universal primaries(−declines) on disk)
  3  floor NOT met (below computed floor or a mandatory/universal-primary dept missing)
  7  no workforce / cannot resolve company on disk

The exact floor count is computed dynamically from HARDCODED_MANDATORY +
universal_primary_vertical_departments(); print it with --json or the default
human summary to see the live count.

This module is import-safe: `from department_floor import evaluate_floor`
(after adding the scripts dir to sys.path) returns the verdict dict directly.
Read-only. Never writes. Idempotent.
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"

# Hardcoded mandatory fallback - IDENTICAL to build-workforce.load_canonical_floor()
# so the floor is still enforced on a broken install that lost the naming map.
# v11.1.0: added general-task + project-architecture-office, floor 24→26.
# Bugs + Healer (self-repair immune system) added as mandatory, floor 26→28.
# Quality Control (owns and runs the system analyzer) added as mandatory, floor 28→29.
HARDCODED_MANDATORY = [
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office",
    "bugs", "healer", "quality-control",
]

# Known legacy aliases + variant slugs a canonical dept can appear under on disk.
# Mirrors build-workforce.CANONICAL_ID_ALIASES + CANONICAL_VARIANT_SLUGS so a
# dept that exists under a different folder name still counts as "present".
CANONICAL_VARIANT_SLUGS = {
    "billing-finance": ["finance", "finance-ops", "billing", "finance-billing", "accounting"],
    "customer-support": ["support", "customer-service", "cs", "client-success"],
    "web-development": ["web-dev", "webdev", "website", "web"],
    "app-development": ["app-dev", "appdev", "mobile", "application-development"],
    "legal": ["legal-compliance", "compliance", "legal-ops", "risk-compliance"],
    "graphics": ["graphics-design", "design", "creative", "graphic-design"],
    "openclaw-maintenance": ["openclaw", "maintenance", "ops", "platform-maintenance"],
    "paid-advertisement": ["paid-ads", "paid-advertising", "ads", "advertising", "paid-media"],
    "social-media": ["social", "smm", "social-media-management"],
    "crm": ["crm-ops", "customer-relationship-management"],
    "communications": ["comms", "communication", "pr", "public-relations"],
    "video": ["video-production", "video-content", "video-editing"],
    "audio": ["audio-production", "audio-content", "sound", "podcast"],
}


def _norm(s):
    """Normalize a slug for membership comparison: lowercase, strip hyphens."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def load_naming_map():
    try:
        return json.load(open(NAMING_MAP))
    except (OSError, json.JSONDecodeError):
        return {}


def mandatory_ids(nm):
    m = list((nm.get("mandatory") or {}).keys())
    return m or list(HARDCODED_MANDATORY)


def universal_primary_vertical_departments(nm):
    """
    Return the list of universal primary vertical-pack department ids - one per
    pack, the department marked universal_primary=true (always the first dept in
    auto_add_departments). These are added to EVERY client regardless of industry,
    giving the len(HARDCODED_MANDATORY) + len(result) mandatory floor (computed at
    runtime - no integer is hardcoded here).

    If a pack has no dept marked universal_primary=true, the first dept in
    auto_add_departments is treated as the universal primary (backward-compatible
    with naming maps that predate the universal_primary field).
    """
    packs = nm.get("vertical_packs") or {}
    primary_ids = []
    seen = set()
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        depts = pack.get("auto_add_departments", []) or []
        if not depts:
            continue
        # Find the universal_primary dept; fall back to first if not flagged.
        primary = None
        for dept in depts:
            if isinstance(dept, dict) and dept.get("universal_primary"):
                primary = dept
                break
        if primary is None:
            primary = depts[0] if isinstance(depts[0], dict) else None
        if primary:
            did = primary.get("id")
            if did and did not in seen:
                seen.add(did)
                primary_ids.append(did)
    return primary_ids


def matched_vertical_pack_departments(nm, core_answers):
    """
    Return the list of vertical-pack department ids for the client - includes:
      1. All universal primary departments (one per pack, always present for every
         client - these are the universal primaries that form the top layer of the
         computed mandatory floor alongside HARDCODED_MANDATORY).
      2. Additional pack departments that match the client's industry keywords
         (flavor/extras on top of the computed floor, not gating).

    De-duped. Deterministic. Uses the SAME keyword-match logic as
    build-workforce._detect_vertical_packs().
    """
    packs = nm.get("vertical_packs") or {}
    haystack = " ".join([
        str(core_answers.get("industry", "") or ""),
        str(core_answers.get("company_description", "") or ""),
        str(core_answers.get("biggest_challenge", "") or ""),
        str(core_answers.get("tools", "") or ""),
    ]).lower()

    # Phase 1: always add the universal primary from every pack.
    all_dept_ids = []
    seen = set()
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        depts = pack.get("auto_add_departments", []) or []
        if not depts:
            continue
        primary = None
        for dept in depts:
            if isinstance(dept, dict) and dept.get("universal_primary"):
                primary = dept
                break
        if primary is None:
            primary = depts[0] if isinstance(depts[0], dict) else None
        if primary:
            did = primary.get("id") if isinstance(primary, dict) else None
            if did and did not in seen:
                seen.add(did)
                all_dept_ids.append(did)

    # Phase 2: keyword-match extras (additional pack depts beyond the primary).
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        hit = False
        for kw in pack.get("auto_add_keywords", []) or []:
            k = str(kw).strip().lower()
            if not k:
                continue
            if " " in k:
                if k in haystack:
                    hit = True
                    break
            elif re.search(r"\b" + re.escape(k) + r"\b", haystack):
                hit = True
                break
        if not hit:
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            did = dept.get("id") if isinstance(dept, dict) else None
            if did and did not in seen:
                seen.add(did)
                all_dept_ids.append(did)
    return all_dept_ids


def declined_set(build_state):
    """
    The ONLY way to be below the mandatory floor: an EXPLICIT recorded decline.
    Source of truth: build_state.canonicalReconciliation.decisions[cid] == "no"
    OR a top-level build_state.declinedDepartments[] list (interview/config).
    """
    declined = set()
    bs = build_state or {}
    recon = bs.get("canonicalReconciliation", {}) or {}
    for cid, dec in (recon.get("decisions", {}) or {}).items():
        if str(dec).strip().lower() == "no":
            declined.add(_norm(cid))
    for cid in (bs.get("declinedDepartments", []) or []):
        declined.add(_norm(cid))
    return declined


def resolve_departments_dir():
    """
    Resolve the active company's departments/ dir ON DISK. Uses detect_platform
    when available, else falls back to the most-recently-modified company under
    ~/clawd/zero-human-company/. Returns Path or None.

    BUG FIX: use detect_platform keys "company_dir" / "company_root" (the keys
    the working qc-completeness.sh uses), NOT the stale "active_zhc_company" /
    "zhc_company_root" keys that never existed. When configured company_root does
    NOT exist, prefer a directly-present <workspace>/departments/ dir rather than
    descending into the first subdir (which may be a single dept folder like
    personal-assistant, causing the whole departments/ tree to be walked as if it
    were the company root -> false floor fail).
    """
    # BUG 2 FIX: sys.path.insert(0, ...) order matters — the LAST insert wins
    # (each call pushes the previous one down).  The old loop inserted lib FIRST,
    # so shared-utils ended up at position 0 and its detect_platform (which returns
    # company_root=~/Downloads/openclaw-master-files/zero-human-company and
    # company_dir=None on the ~/clawd layout) silently shadowed the lib/ version
    # (which correctly resolves company_dir for ~/clawd).  Result: false rc=7.
    # Fix: insert shared-utils first (fallback), then lib/ LAST so lib/ ends at
    # position 0 — exactly the resolution order that qc-completeness.sh uses via
    # the same lib/ detect_platform and that returns a working company_dir.
    for libp in (SKILL_DIR.parent / "shared-utils", SKILL_DIR / "shared-utils", SKILL_DIR / "lib"):
        sys.path.insert(0, str(libp))
    zhc_root = None
    workspace = None
    try:
        from detect_platform import get_openclaw_paths  # type: ignore
        paths = get_openclaw_paths()
        # Priority: already-resolved active company dir (same key qc-completeness uses)
        company_dir = paths.get("company_dir")
        if company_dir and Path(company_dir).resolve().is_dir():
            zhc_root = str(Path(company_dir).resolve())
        # Fallback: parent zero-human-company/ + slug scan
        if not zhc_root:
            zhc_root = paths.get("company_root")
            if zhc_root and not Path(zhc_root).is_dir():
                zhc_root = None
        workspace = paths.get("workspace_root") or paths.get("clawd_root")
    except Exception:
        pass
    if not zhc_root:
        ws = Path(workspace) if workspace else Path(os.path.expanduser("~/clawd"))
        # Prefer a directly-present departments/ dir under the workspace root.
        # This avoids descending into a single dept folder (e.g. personal-assistant)
        # and mistaking it for the company root -> false floor fail.
        for direct_depts in (ws / "departments",
                             ws / "zero-human-company" / "departments",
                             Path("/data/.openclaw/workspace/departments")):
            if direct_depts.is_dir():
                return direct_depts
        # Fall back to most-recently-modified subdir under zero-human-company/
        zhc_dir = ws / "zero-human-company"
        if zhc_dir.is_dir():
            cands = sorted(
                (d for d in zhc_dir.iterdir() if d.is_dir() and not d.name.startswith("_")),
                key=lambda d: d.stat().st_mtime, reverse=True,
            )
            if cands:
                zhc_root = str(cands[0])
    if not zhc_root:
        return None
    dd = Path(zhc_root) / "departments"
    if dd.is_dir():
        return dd
    # Non-standard layout: zhc_root itself may be the departments dir
    # (e.g. when detect_platform returns the departments/ path directly)
    zp = Path(zhc_root)
    if zp.is_dir():
        # Only treat it as a departments dir if it contains role-like subdirs,
        # NOT if it looks like a single department (contains role folders only).
        # Heuristic: if it has at least 2 non-hidden subdirs and no how-to.md
        # directly inside, treat as departments root.
        subdirs = [d for d in zp.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))]
        how_to_direct = (zp / "how-to.md").exists()
        if len(subdirs) >= 2 and not how_to_direct:
            return zp
    return None


def departments_on_disk(departments_dir):
    """Return the set of normalized department folder names actually on disk."""
    present = set()
    if not departments_dir or not departments_dir.is_dir():
        return present
    for d in departments_dir.iterdir():
        if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_"):
            present.add(_norm(d.name))
    return present


def _present(cid, present_norm):
    """True if canonical/vertical id `cid` is on disk under id or any variant."""
    if _norm(cid) in present_norm:
        return True
    for v in CANONICAL_VARIANT_SLUGS.get(cid, []):
        if _norm(v) in present_norm:
            return True
    return False


def read_core_answers(build_state, departments_dir):
    """
    Resolve the industry signal needed to compute matched vertical packs.
    Prefer build-state companyIndustry/industry fields; fall back to the
    company-discovery answers file on disk if present.
    """
    bs = build_state or {}
    ca = {
        "industry": bs.get("companyIndustry") or bs.get("industry") or "",
        "company_description": bs.get("companyDescription") or bs.get("company_description") or "",
        "biggest_challenge": bs.get("biggestChallenge") or "",
        "tools": bs.get("tools") or "",
    }
    if any(ca.values()):
        return ca
    # Fallback: scan the company-discovery answers doc for free-text signal.
    if departments_dir:
        company_dir = departments_dir.parent
        for cand in list(company_dir.glob("**/workforce-interview-answers.md")) + \
                    list(company_dir.glob("**/*workforce-proposal.md")):
            try:
                txt = cand.read_text(errors="ignore")
                ca["company_description"] = (ca["company_description"] + " " + txt)[:20000]
                return ca
            except Exception:
                continue
    return ca


def load_build_state():
    candidates = [
        "/data/.openclaw/workspace/.workforce-build-state.json",
        os.path.join(os.path.expanduser("~"), ".openclaw", "workspace", ".workforce-build-state.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                return json.load(open(p))
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


def evaluate_floor(departments_dir=None, build_state=None, core_answers=None):
    """
    Compute the HARD department floor and compare it to REAL on-disk departments.

    The floor = len(HARDCODED_MANDATORY) mandatory + len(universal_primary_vertical_departments())
    universal-primary vertical-pack departments. Both counts are derived at runtime
    from the live data so the reported floor ALWAYS equals what this function enforces.
    Additional keyword-matched pack departments are tracked but do NOT gate the floor.

    Returns a verdict dict:
      {
        "rc": 0|3|7,
        "departments_dir": str|None,
        "mandatory": [...],              # canonical mandatory dept ids
        "declined": [...],
        "universal_primary_vertical": [...],  # universal pack primaries (always required)
        "matched_vertical_departments": [...],  # universal primaries + keyword extras
        "expected_floor": [...],         # mandatory(−declined) + universal primaries(−declined)
        "expected_floor_count": int,     # computed floor minus any explicit declines
        "on_disk_count": int,
        "missing_mandatory": [...],      # mandatory not found on disk (not declined)
        "missing_universal_primary": [...],  # universal-primary depts missing from disk
        "floor_met": bool,
        "reason": str,
      }
    """
    nm = load_naming_map()
    if build_state is None:
        build_state = load_build_state()
    if departments_dir is None:
        departments_dir = resolve_departments_dir()
    if departments_dir is None:
        return {
            "rc": 7, "departments_dir": None, "floor_met": False,
            "reason": "no workforce / cannot resolve departments dir on disk",
            "mandatory": [], "declined": [], "universal_primary_vertical": [],
            "matched_vertical_departments": [],
            "expected_floor": [], "expected_floor_count": 0, "on_disk_count": 0,
            "missing_mandatory": [], "missing_universal_primary": [],
        }

    if core_answers is None:
        core_answers = read_core_answers(build_state, departments_dir)

    mand = mandatory_ids(nm)
    declined = declined_set(build_state)
    universal_primaries = universal_primary_vertical_departments(nm)
    matched_verticals = matched_vertical_pack_departments(nm, core_answers)
    present = departments_on_disk(departments_dir)

    expected_mand = [c for c in mand if _norm(c) not in declined]
    # Floor gate: only the universal primaries (one per pack, not all keyword-matched extras).
    expected_universal_primary = [v for v in universal_primaries if _norm(v) not in declined]
    expected_floor = expected_mand + expected_universal_primary

    missing_mandatory = [c for c in expected_mand if not _present(c, present)]
    missing_universal_primary = [v for v in expected_universal_primary if not _present(v, present)]

    floor_met = (not missing_mandatory) and (not missing_universal_primary)
    rc = 0 if floor_met else 3

    # Reason string uses the live computed floor count - never a hardcoded integer.
    _expected_floor_count = len(expected_mand) + len(expected_universal_primary)
    reason = (
        f"floor met ({_expected_floor_count}-department standard: "
        f"{len(mand)} mandatory + {len(universal_primaries)} universal-primary-vertical"
        f" − {len(declined)} declined)"
    )
    if not floor_met:
        bits = []
        if missing_mandatory:
            bits.append("missing mandatory: " + ", ".join(missing_mandatory))
        if missing_universal_primary:
            bits.append("missing universal-primary vertical: " + ", ".join(missing_universal_primary))
        reason = " | ".join(bits)

    return {
        "rc": rc,
        "departments_dir": str(departments_dir),
        "mandatory": mand,
        "declined": sorted(declined),
        "universal_primary_vertical": universal_primaries,
        "matched_vertical_departments": matched_verticals,
        "expected_floor": expected_floor,
        "expected_floor_count": len(expected_floor),
        "on_disk_count": len(present),
        "missing_mandatory": missing_mandatory,
        "missing_universal_primary": missing_universal_primary,
        "floor_met": floor_met,
        "reason": reason,
    }


def main(argv):
    as_json = "--json" in argv
    # Allow an explicit --departments-dir for the smoke test.
    dd = None
    for i, a in enumerate(argv):
        if a == "--departments-dir" and i + 1 < len(argv):
            dd = Path(argv[i + 1])
    verdict = evaluate_floor(departments_dir=dd)
    if as_json:
        print(json.dumps(verdict, indent=2))
    else:
        _floor_label = (
            f"{verdict['expected_floor_count']}-department standard"
            f" ({len(verdict['mandatory'])} mandatory"
            f" + {len(verdict['universal_primary_vertical'])} universal-primary-vertical"
            f" − {len(verdict['declined'])} declined)"
        )
        print("============================================", file=sys.stderr)
        print(f"department-floor.py - HARD floor verdict ({_floor_label})", file=sys.stderr)
        print(f"departments_dir = {verdict['departments_dir']}", file=sys.stderr)
        print(f"expected floor  = {verdict['expected_floor_count']} "
              f"({len(verdict['mandatory'])} mandatory "
              f"+ {len(verdict['universal_primary_vertical'])} universal-primary-vertical "
              f"− {len(verdict['declined'])} declined)", file=sys.stderr)
        print(f"on disk         = {verdict['on_disk_count']} departments", file=sys.stderr)
        if verdict["missing_mandatory"]:
            print(f"MISSING mandatory         : {', '.join(verdict['missing_mandatory'])}", file=sys.stderr)
        if verdict["missing_universal_primary"]:
            print(f"MISSING universal-primary : {', '.join(verdict['missing_universal_primary'])}", file=sys.stderr)
        print(f"RESULT: {'FLOOR MET' if verdict['floor_met'] else 'FLOOR NOT MET'} "
              f"(rc={verdict['rc']})", file=sys.stderr)
    return verdict["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
