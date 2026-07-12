#!/usr/bin/env python3
"""
net-new-department.py — P2-05 step 2: the interview-close "we uncovered a
department we don't have" → creation path.

WHAT THIS IS:
At interview close, some owner needs map cleanly onto an existing floor/industry
department (preferred — route there, do NOT create). But a genuinely NEW need
(no existing dept covers it) must be able to become a REAL department: a
name/slug + 2–3 seed roles, materialized through the FIXED Skill-32
add-department.sh (which now wires the OpenClaw runtime + the board row together,
so no card sticks in no_specialist_runtime), and only reported as a success once
guard-department-runtime-parity.py confirms the new board row has a runtime
behind it.

THE TWO HARD RULES THIS ENFORCES (spec P2-05 step 2):
  1. NEVER duplicate a canonical slug. A proposed slug that resolves to an
     existing department — a mandatory canonical, a universal-primary vertical,
     a known variant (billing→billing-finance), any vertical-pack dept id
     (listings, engineering, …), OR an existing role-library department — is
     REJECTED. That need already has a home; route to it instead of minting a
     phantom twin. (This is the department-naming-map.json + reconcile-legacy-
     tree.py duplicate logic, reused — never re-implemented.)
  2. NEVER duplicate a department already ON DISK. If any existing
     departments/<dir> resolves to the SAME join key as the proposed slug, the
     dept already exists on this box — REJECTED (the C5 phantom-duplicate class
     reconcile-legacy-tree.py --merge-duplicates would otherwise have to clean).

  3. (creation mode only) the new dept must PASS guard-department-runtime-parity.py
     before this tool reports success — a board row with no runtime is not a
     success.

MODES:
  --check-only   Validate the proposed slug against rules 1 & 2 ONLY. Never
                 creates anything. This is the offline-safe guard the interview
                 runs to decide "route to existing" vs "create net-new", and the
                 mode the CI test exercises.
  (default)      --check-only guard, THEN create via add-department.sh, THEN
                 guard-department-runtime-parity.py. Requires a live box
                 (mission-control.db + openclaw.json); reports success only when
                 the parity guard passes.

USAGE
  python3 net-new-department.py --name "Grant Writing" --check-only \\
      --departments-dir <company>/departments
  python3 net-new-department.py --name "Grant Writing" --roles "Grant Researcher,Proposal Writer" \\
      --add-department-script ../../32-command-center-setup/scripts/add-department.sh

EXIT CODES
  0  clean / created + parity-verified
  2  RULE 1 violation: proposed slug duplicates an existing canonical/known dept
     (route to that dept instead — printed in the verdict)
  3  RULE 2 violation: proposed slug duplicates a department already on disk
  4  creation attempted but add-department.sh or the runtime-parity guard failed
  5  bad usage

Read-only in --check-only mode. Deterministic. Depends only on the stdlib +
the sibling department-floor.py (canonical-slug resolver, single source).
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"
ROLE_INDEX = SKILL_DIR / "templates" / "role-library" / "_index.json"

RC_OK = 0
RC_CANON_DUP = 2
RC_DISK_DUP = 3
RC_CREATE_FAIL = 4
RC_USAGE = 5

# A department slug becomes a filesystem directory name (departments/<slug>) and a
# board/runtime key. Cap it so creation mode can never hand add-department.sh a
# filesystem-hostile / absurd name. 64 chars is comfortably above every real
# canonical slug (longest shipped is well under 20) and safely under the 255-byte
# POSIX filename limit. slugify() already restricts the character set to [a-z0-9-],
# so length is the remaining sanity check.
MAX_SLUG_LEN = 64


def _load_department_floor():
    """Import the sibling department-floor.py for the canonical-slug resolver +
    collision helpers — the SAME single source reconcile-legacy-tree.py uses, so
    the duplicate logic can never fork."""
    fp = SCRIPT_DIR / "department-floor.py"
    spec = importlib.util.spec_from_file_location("department_floor", str(fp))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slugify(raw):
    """Lowercase, hyphen-collapse, trim — IDENTICAL rule to add-department.sh's
    bash normalizer (`tr` + `sed 's/[^a-z0-9]+/-/g'`), so a name that passes here
    produces the same slug there."""
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_naming_map():
    try:
        return json.loads(NAMING_MAP.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def known_department_ids(nm, df):
    """Every department id the repo already KNOWS about — the set a net-new slug
    must NOT collide with:
      * mandatory canonical ids
      * EVERY vertical-pack dept id (universal-primary AND industry-gated, e.g.
        listings/lead-generation — they ship real library roles)
      * every CANONICAL_VARIANT_SLUGS alias (billing, legal-compliance, …)
      * every role-library department directory key (_index.json)
    Returned as a set of NORMALIZED tokens (df._norm space)."""
    ids = set()
    for did in (nm.get("mandatory") or {}):
        ids.add(df._norm(did))
    for pack in (nm.get("vertical_packs") or {}).values():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            did = dept.get("id") if isinstance(dept, dict) else None
            if did:
                ids.add(df._norm(did))
    for cid, variants in df.CANONICAL_VARIANT_SLUGS.items():
        ids.add(df._norm(cid))
        for v in variants:
            ids.add(df._norm(v))
    try:
        idx = json.loads(ROLE_INDEX.read_text())
        for did in (idx.get("departments") or {}):
            ids.add(df._norm(did))
    except (OSError, json.JSONDecodeError):
        pass
    return ids


def _join_key(name, df, nm):
    """The department-floor join key for a dir/slug: its canonical slug if it maps
    to one, else its normalized self (a genuine custom maps to itself)."""
    cid = df.canonical_slug_for(name, nm)
    return df._norm(cid) if cid else df._norm(name)


def check_slug(slug, departments_dir, df, nm, known_ids):
    """Return (rc, verdict_dict) for rules 1 & 2. rc=0 clean."""
    nslug = df._norm(slug)
    verdict = {"slug": slug, "normalized": nslug, "clean": False}

    # RULE 1 — canonical / known-department collision.
    canonical = df.canonical_slug_for(slug, nm)   # mandatory / universal-primary / variant
    if canonical is not None:
        verdict.update({"violation": "canonical-duplicate", "maps_to": canonical,
                        "reason": f"'{slug}' resolves to the existing canonical department "
                                  f"'{canonical}' — route the need there; do NOT create a net-new twin."})
        return RC_CANON_DUP, verdict
    if nslug in known_ids:
        verdict.update({"violation": "known-department-duplicate", "maps_to": slug,
                        "reason": f"'{slug}' is already a known department (naming map / vertical pack / "
                                  f"role library) — route the need there; do NOT create a net-new twin."})
        return RC_CANON_DUP, verdict

    # RULE 2 — already on disk (C5 phantom-duplicate class).
    if departments_dir:
        dd = Path(departments_dir)
        if dd.is_dir():
            proposed_key = _join_key(slug, df, nm)
            live, _backups = df._raw_department_dirs(dd)
            for existing in live:
                if _join_key(existing, df, nm) == proposed_key:
                    verdict.update({"violation": "on-disk-duplicate", "maps_to": existing,
                                    "reason": f"a department already on disk ('{existing}') resolves to the "
                                              f"same slug as '{slug}' — it already exists on this box."})
                    return RC_DISK_DUP, verdict

    verdict["clean"] = True
    verdict["reason"] = f"'{slug}' is a genuine net-new department (no canonical/known/on-disk collision)."
    return RC_OK, verdict


def nearest_library_dept(name, description, nm):
    """Suggest the nearest EXISTING role-library department to seed the new dept's
    base roles from (spec: 'roles seeded from nearest role-library templates').
    Simple, deterministic token-overlap against each dept's one_liner + display
    name. Advisory only — never blocks creation."""
    hay = f"{name} {description}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", hay))
    best, best_score = None, 0
    catalog = []
    for did, d in (nm.get("mandatory") or {}).items():
        catalog.append((did, f"{d.get('display_name','')} {d.get('one_liner','')}"))
    for pack in (nm.get("vertical_packs") or {}).values():
        for d in pack.get("auto_add_departments", []) or []:
            if isinstance(d, dict) and d.get("id"):
                catalog.append((d["id"], f"{d.get('name','')} {d.get('one_liner','')}"))
    for did, text in catalog:
        cand = set(re.findall(r"[a-z0-9]+", text.lower()))
        score = len(tokens & cand)
        if score > best_score:
            best, best_score = did, score
    return best or "general-task"


def propose_roles(name, roles_arg, nearest):
    """Build the 2–3 seed role titles for the new dept. Owner-provided roles win;
    otherwise derive a minimal, real starter set (head + a domain specialist)."""
    if roles_arg:
        out = [r.strip() for r in roles_arg.split(",") if r.strip()]
    else:
        out = [f"Head of {name}", f"{name} Specialist"]
    return out[:3]


def create_department(slug, name, roles, nearest, add_script, guard_script, icon=None):
    """Creation mode: call add-department.sh, then guard-department-runtime-parity.py.
    Returns (rc, info). Success only when the parity guard passes."""
    if not add_script or not Path(add_script).is_file():
        return RC_CREATE_FAIL, {"error": f"add-department.sh not found at {add_script!r}"}
    cmd = ["bash", str(add_script), "--slug", slug, "--name", name,
           "--head-name", f"Head of {name}",
           "--description", f"{name} department (net-new from interview close; "
                            f"seeded from nearest library dept '{nearest}')"]
    if icon:
        cmd += ["--icon", icon]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, Exception) as e:  # noqa: BLE001
        return RC_CREATE_FAIL, {"error": f"add-department.sh failed to run: {e}"}
    info = {"add_department_rc": r.returncode,
            "add_department_tail": (r.stdout or "")[-800:] + (r.stderr or "")[-400:]}
    if r.returncode != 0:
        info["error"] = "add-department.sh exited non-zero"
        return RC_CREATE_FAIL, info

    # Parity guard — the new board row MUST have a runtime behind it.
    if not guard_script or not Path(guard_script).is_file():
        info["error"] = f"guard-department-runtime-parity.py not found at {guard_script!r}"
        return RC_CREATE_FAIL, info
    try:
        g = subprocess.run(["python3", str(guard_script)], capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:  # noqa: BLE001
        info["error"] = f"parity guard failed to run: {e}"
        return RC_CREATE_FAIL, info
    info["parity_guard_rc"] = g.returncode
    info["parity_guard_tail"] = (g.stdout or "")[-400:] + (g.stderr or "")[-400:]
    if g.returncode != 0:
        info["error"] = "runtime-parity guard did NOT pass — the new dept has a board row with no runtime"
        return RC_CREATE_FAIL, info
    return RC_OK, info


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="P2-05 net-new department path: guard against canonical/on-disk "
                    "duplicates, then (unless --check-only) create via add-department.sh "
                    "and verify runtime parity.")
    ap.add_argument("--name", help="human department name (slug derived from it if --slug absent)")
    ap.add_argument("--slug", help="explicit slug (default: slugify(--name))")
    ap.add_argument("--roles", help="comma-separated seed role titles (2-3)")
    ap.add_argument("--icon", help="emoji icon for the department")
    ap.add_argument("--departments-dir", help="company departments/ dir for the on-disk duplicate check")
    ap.add_argument("--check-only", action="store_true",
                    help="validate rules 1&2 only; never create anything")
    ap.add_argument("--add-department-script",
                    default=str(REPO_ROOT / "32-command-center-setup" / "scripts" / "add-department.sh"),
                    help="path to Skill-32 add-department.sh (creation mode)")
    ap.add_argument("--guard-script",
                    default=str(REPO_ROOT / "32-command-center-setup" / "scripts" / "guard-department-runtime-parity.py"),
                    help="path to guard-department-runtime-parity.py (creation mode)")
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = ap.parse_args(argv)

    if not args.name and not args.slug:
        print("ERROR: --name or --slug is required", file=sys.stderr)
        return RC_USAGE

    slug = args.slug or slugify(args.name)
    slug = slugify(slug)
    if not slug:
        print("ERROR: slug normalized to empty — provide a valid --name/--slug", file=sys.stderr)
        return RC_USAGE
    # Sanity cap: a slug becomes a directory name + board/runtime key. Refuse an
    # absurd length up front so creation mode cannot pass a filesystem-hostile name
    # to add-department.sh (a genuine department name is never this long).
    if len(slug) > MAX_SLUG_LEN:
        print(f"ERROR: slug is {len(slug)} chars — exceeds the {MAX_SLUG_LEN}-char sanity cap. "
              f"A department slug becomes a directory/board/runtime key; provide a real, short name.",
              file=sys.stderr)
        return RC_USAGE

    df = _load_department_floor()
    nm = load_naming_map()
    known_ids = known_department_ids(nm, df)

    rc, verdict = check_slug(slug, args.departments_dir, df, nm, known_ids)
    name = args.name or slug
    nearest = nearest_library_dept(name, args.name or "", nm)
    verdict["nearest_library_dept"] = nearest
    verdict["proposed_roles"] = propose_roles(name, args.roles, nearest)

    if rc != RC_OK:
        if args.json:
            print(json.dumps(verdict, ensure_ascii=False, indent=2))
        else:
            print(f"REJECT ({verdict['violation']}): {verdict['reason']}", file=sys.stderr)
        return rc

    if args.check_only:
        verdict["mode"] = "check-only"
        if args.json:
            print(json.dumps(verdict, ensure_ascii=False, indent=2))
        else:
            print(f"OK net-new: {verdict['reason']}")
            print(f"  seed from nearest library dept: {nearest}")
            print(f"  proposed roles: {', '.join(verdict['proposed_roles'])}")
        return RC_OK

    # Creation mode.
    crc, info = create_department(slug, name, verdict["proposed_roles"], nearest,
                                  args.add_department_script, args.guard_script, args.icon)
    verdict["mode"] = "create"
    verdict["create"] = info
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    elif crc == RC_OK:
        print(f"CREATED net-new department '{slug}' — runtime parity verified (guard rc=0).")
    else:
        print(f"CREATE FAILED for '{slug}': {info.get('error')}", file=sys.stderr)
    return crc


if __name__ == "__main__":
    sys.exit(main())
