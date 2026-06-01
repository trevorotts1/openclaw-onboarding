#!/usr/bin/env python3
"""
department-floor.py — the ONE source of truth for the HARD department floor.

WHY THIS EXISTS (the bug it kills):
Clients kept landing with HEAVILY-REDUCED workforces (Cassandra 3 depts, others
3-per-dept / 6-dept / legacy) DESPITE the repo carrying 216 role templates, 16
mandatory canonical departments, and 7 industry vertical packs. Diagnosis found
THREE places that trusted the build-state JSON as proof of completion instead of
counting REAL departments on disk:
  1. verify-zhc-standard.sh step-2 read `.departments[]` from the build-state
     JSON, so a hand-seeded 3-dept JSON (Cassandra's seeded fiction) reported
     "all canonical present" and passed the floor.
  2. qc-completeness.sh measured per-dept staffing of whatever was ON DISK but
     had NO floor concept at all — 3 well-staffed depts returned PASS.
  3. run-closeout.sh / resume-workforce-build.sh self-completed on JSON
     status=done / closeoutStatus=done with zero disk verification.

THE FIX (this module): compute the EXPECTED floor =
    16 mandatory canonical departments
    + the vertical-pack departments matched to the client's industry
    − any department the client EXPLICITLY declined (recorded as an explicit
      decline in build-state canonicalReconciliation.decisions == "no")
…and then count the REAL department directories ON DISK and FAIL hard when disk
is below the floor or a mandatory/vertical dept is missing from disk. The
build-state JSON is NEVER trusted as proof of floor compliance — only disk is.

Reads the SAME source of truth as build-workforce.py:
    23-ai-workforce-blueprint/department-naming-map.json  (.mandatory + .vertical_packs)

USAGE
  python3 department-floor.py --json            # machine-readable verdict to stdout
  python3 department-floor.py                   # human summary to stderr
EXIT CODES
  0  floor met (on disk >= mandatory(−declines) + matched vertical packs)
  3  floor NOT met (missing mandatory or matched-vertical depts on disk)
  7  no workforce / cannot resolve company on disk

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

# Hardcoded mandatory fallback — IDENTICAL to build-workforce.load_canonical_floor()
# so the floor is still enforced on a broken install that lost the naming map.
HARDCODED_MANDATORY = [
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement",
]

# Known legacy aliases + variant slugs a canonical dept can appear under on disk.
# Mirrors build-workforce.CANONICAL_ID_ALIASES + CANONICAL_VARIANT_SLUGS so a
# dept that exists under a different folder name still counts as "present".
CANONICAL_VARIANT_SLUGS = {
    "billing-finance": ["finance", "finance-ops", "billing", "finance-billing", "accounting"],
    "customer-support": ["support", "customer-service", "cs", "client-success"],
    "web-development": ["web-dev", "webdev", "website", "web"],
    "app-development": ["app-dev", "appdev", "mobile", "application-development"],
    "legal": ["legal-compliance", "compliance", "legal-ops"],
    "graphics": ["graphics-design", "design", "creative", "graphic-design"],
    "openclaw-maintenance": ["openclaw", "maintenance", "ops", "platform-maintenance"],
    "paid-advertisement": ["paid-ads", "paid-advertising", "ads", "advertising", "paid-media"],
    "social-media": ["social", "smm", "social-media-management"],
    "crm": ["crm-ops", "customer-relationship-management"],
    "communications": ["comms", "communication", "pr", "public-relations"],
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


def matched_vertical_pack_departments(nm, core_answers):
    """
    Return the list of vertical-pack department ids that match the client's
    industry signal, using the SAME keyword-match logic as
    build-workforce._detect_vertical_packs(). Deterministic + de-duped.
    """
    packs = nm.get("vertical_packs") or {}
    haystack = " ".join([
        str(core_answers.get("industry", "") or ""),
        str(core_answers.get("company_description", "") or ""),
        str(core_answers.get("biggest_challenge", "") or ""),
        str(core_answers.get("tools", "") or ""),
    ]).lower()
    matched_dept_ids = []
    seen = set()
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
                matched_dept_ids.append(did)
    return matched_dept_ids


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
    """
    for libp in (SKILL_DIR / "lib", SKILL_DIR.parent / "shared-utils", SKILL_DIR / "shared-utils"):
        sys.path.insert(0, str(libp))
    zhc_root = None
    try:
        from detect_platform import get_openclaw_paths  # type: ignore
        paths = get_openclaw_paths()
        zhc_root = paths.get("active_zhc_company") or paths.get("zhc_company_root")
        workspace = paths.get("workspace_root") or paths.get("clawd_root")
    except Exception:
        workspace = None
    if not zhc_root:
        ws = Path(workspace) if workspace else Path(os.path.expanduser("~/clawd"))
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
    return dd if dd.is_dir() else None


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

    Returns a verdict dict:
      {
        "rc": 0|3|7,
        "departments_dir": str|None,
        "mandatory": [...], "declined": [...],
        "matched_vertical_departments": [...],
        "expected_floor": [...],            # mandatory(−declined) + matched verticals
        "expected_floor_count": int,
        "on_disk_count": int,
        "missing_mandatory": [...],         # mandatory not found on disk (not declined)
        "missing_vertical": [...],          # matched-vertical not found on disk
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
            "mandatory": [], "declined": [], "matched_vertical_departments": [],
            "expected_floor": [], "expected_floor_count": 0, "on_disk_count": 0,
            "missing_mandatory": [], "missing_vertical": [],
        }

    if core_answers is None:
        core_answers = read_core_answers(build_state, departments_dir)

    mand = mandatory_ids(nm)
    declined = declined_set(build_state)
    matched_verticals = matched_vertical_pack_departments(nm, core_answers)
    present = departments_on_disk(departments_dir)

    expected_mand = [c for c in mand if _norm(c) not in declined]
    expected_verticals = [v for v in matched_verticals if _norm(v) not in declined]
    expected_floor = expected_mand + expected_verticals

    missing_mandatory = [c for c in expected_mand if not _present(c, present)]
    missing_vertical = [v for v in expected_verticals if not _present(v, present)]

    floor_met = (not missing_mandatory) and (not missing_vertical)
    rc = 0 if floor_met else 3

    reason = "floor met"
    if not floor_met:
        bits = []
        if missing_mandatory:
            bits.append("missing mandatory: " + ", ".join(missing_mandatory))
        if missing_vertical:
            bits.append("missing matched-vertical: " + ", ".join(missing_vertical))
        reason = " | ".join(bits)

    return {
        "rc": rc,
        "departments_dir": str(departments_dir),
        "mandatory": mand,
        "declined": sorted(declined),
        "matched_vertical_departments": matched_verticals,
        "expected_floor": expected_floor,
        "expected_floor_count": len(expected_floor),
        "on_disk_count": len(present),
        "missing_mandatory": missing_mandatory,
        "missing_vertical": missing_vertical,
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
        print("============================================", file=sys.stderr)
        print("department-floor.py — HARD floor verdict", file=sys.stderr)
        print(f"departments_dir = {verdict['departments_dir']}", file=sys.stderr)
        print(f"expected floor  = {verdict['expected_floor_count']} "
              f"({len(verdict['mandatory'])} mandatory − {len(verdict['declined'])} declined "
              f"+ {len(verdict['matched_vertical_departments'])} matched-vertical)", file=sys.stderr)
        print(f"on disk         = {verdict['on_disk_count']} departments", file=sys.stderr)
        if verdict["missing_mandatory"]:
            print(f"MISSING mandatory: {', '.join(verdict['missing_mandatory'])}", file=sys.stderr)
        if verdict["missing_vertical"]:
            print(f"MISSING vertical : {', '.join(verdict['missing_vertical'])}", file=sys.stderr)
        print(f"RESULT: {'FLOOR MET' if verdict['floor_met'] else 'FLOOR NOT MET'} "
              f"(rc={verdict['rc']})", file=sys.stderr)
    return verdict["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
